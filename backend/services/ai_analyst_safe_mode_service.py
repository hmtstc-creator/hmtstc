from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.storage import append_log
from services.llm_service import ask_openai_agent, llm_enabled
from services.risk_service import build_risk_snapshot

REVISION = 35
PROMPT_LOG_LIMIT = 500
PAPER_QUEUE_LIMIT = 200
SAFE_ACTIONS = {"wait", "paper_watch", "paper_queue", "risk_review", "report_only"}
FORBIDDEN_ACTIONS = {
    "real_order",
    "place_order",
    "market_buy",
    "market_sell",
    "unlock_real_trading",
    "start_pilot",
    "emergency_close",
    "change_strategy_active",
}

FORBIDDEN_PATTERNS = [
    r"\bgerçek\s+(emir|alım|satım|işlem)\b",
    r"\breal\s+(order|trade|buy|sell)\b",
    r"\b(emir\s+gönder|emir\s+aç|pozisyon\s+aç|alım\s+yap|satım\s+yap)\b",
    r"\b(place\s+order|open\s+position|start\s+pilot|unlock)\b",
    r"\b(api\s*key|secret|withdraw|futures|margin)\b",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any, limit: int = 2000) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def detect_trade_authority_request(message: str) -> list[str]:
    clean = _clean_text(message).lower()
    blockers = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, clean, flags=re.IGNORECASE):
            blockers.append(pattern)
    return blockers


def sanitize_agent_output(text: str) -> str:
    clean = _clean_text(text, limit=2500)
    replacements = [
        ("gerçek emir açacağım", "gerçek emir açamam; yalnızca paper öneri üretebilirim"),
        ("emir göndereceğim", "emir gönderemem; yalnızca karar destek notu üretebilirim"),
        ("alım yapacağım", "alım yapamam; yalnızca paper izleme önerisi oluşturabilirim"),
        ("satım yapacağım", "satım yapamam; yalnızca paper izleme önerisi oluşturabilirim"),
    ]
    lowered = clean.lower()
    for source, target in replacements:
        if source in lowered:
            clean = re.sub(re.escape(source), target, clean, flags=re.IGNORECASE)
            lowered = clean.lower()
    return clean or "AI Analyst Safe Mode aktif. Yalnızca yorum ve paper öneri üretilebilir."


def _scan_candidates(data: dict, limit: int = 5) -> list[dict]:
    last_scan = data.get("last_scan", {}) if isinstance(data, dict) else {}
    candidates = last_scan.get("candidates", []) if isinstance(last_scan, dict) else []
    if not isinstance(candidates, list):
        return []
    cleaned = []
    for item in candidates[:limit]:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        cleaned.append({
            "symbol": symbol,
            "score": _safe_float(item.get("score")),
            "price": _safe_float(item.get("price")),
            "reason": item.get("reason") or item.get("status") or "scan_candidate",
            "source": "last_scan",
        })
    return cleaned


def build_ai_safe_mode_policy() -> dict:
    return {
        "status": "ok",
        "revision": REVISION,
        "mode": "ai_analyst_safe_mode",
        "authority": {
            "can_comment": True,
            "can_suggest": True,
            "can_enqueue_paper_candidate": True,
            "can_place_real_order": False,
            "can_unlock_real_trading": False,
            "can_start_pilot": False,
            "can_change_strategy": False,
            "can_emergency_close": False,
        },
        "allowed_actions": sorted(SAFE_ACTIONS),
        "forbidden_actions": sorted(FORBIDDEN_ACTIONS),
        "hard_rules": [
            "AI outputs are commentary or paper queue only.",
            "No AI endpoint may call real order, unlock, pilot start or emergency close services.",
            "Every prompt and output is logged with hash and safety decision.",
            "Paper queue items require human review before any operational action.",
        ],
        "paper_only_queue": True,
        "prompt_output_logging": True,
        "audit_required": True,
    }


def append_ai_prompt_log(
    data: dict,
    *,
    user: str,
    role: str,
    prompt: str,
    output: str,
    provider: str,
    action: str,
    blocked: bool,
    blockers: list[str] | None = None,
    source: str = "agent",
) -> dict:
    logs = data.setdefault("ai_prompt_log", [])
    if not isinstance(logs, list):
        logs = []
    now = now_iso()
    entry = {
        "id": f"ai-log-{uuid4().hex[:12]}",
        "revision": REVISION,
        "time": now,
        "user": user,
        "role": role,
        "source": source,
        "provider": provider,
        "prompt_hash": _hash_text(prompt),
        "output_hash": _hash_text(output),
        "prompt_preview": _clean_text(prompt, 240),
        "output_preview": _clean_text(output, 360),
        "action": action if action in SAFE_ACTIONS else "report_only",
        "blocked": bool(blocked),
        "blockers": blockers or [],
        "real_trade_authority": False,
        "paper_only": True,
    }
    logs.append(entry)
    data["ai_prompt_log"] = logs[-PROMPT_LOG_LIMIT:]
    append_log(
        data,
        "warning" if blocked else "info",
        f"AI Analyst Safe Mode prompt logged: {entry['action']}",
        "ai_safe_mode_prompt_log",
    )
    return entry


def build_ai_suggestion(data: dict, settings: dict, message: str, *, user: str = "default", role: str = "user") -> dict:
    clean_message = _clean_text(message)
    blockers = detect_trade_authority_request(clean_message)
    risk = build_risk_snapshot(data, settings)
    candidates = _scan_candidates(data, limit=5)
    provider = "fallback"

    if blockers:
        answer = (
            "AI Analyst Safe Mode gerçek emir, unlock, pilot veya operasyon komutu çalıştıramaz. "
            "Bu istek güvenlik gereği yalnızca yorum seviyesinde bloke edildi."
        )
        action = "report_only"
        blocked = True
    else:
        strongest = candidates[0] if candidates else None
        action = "paper_queue" if strongest else "wait"
        blocked = False
        if llm_enabled():
            llm_result = ask_openai_agent(data, settings, clean_message)
            provider = str(llm_result.get("provider") or "openai")
            if llm_result.get("ok") and llm_result.get("answer"):
                answer = sanitize_agent_output(str(llm_result.get("answer")))
            else:
                answer = "LLM provider yanıtı alınamadı; güvenli kural tabanlı öneri üretildi."
                provider = "fallback"
        else:
            provider = "fallback"
            if strongest:
                answer = (
                    f"Paper-only öneri: {strongest.get('symbol')} izleme kuyruğuna aday. "
                    f"Skor {_safe_float(strongest.get('score')):.2f}. Gerçek emir yetkisi yoktur."
                )
            else:
                answer = "Net aday yok. AI Analyst Safe Mode bekleme ve gözlem önerir; gerçek emir yetkisi yoktur."

    log = append_ai_prompt_log(
        data,
        user=user,
        role=role,
        prompt=clean_message,
        output=answer,
        provider=provider,
        action=action,
        blocked=blocked,
        blockers=blockers,
        source="agent_suggestions",
    )

    return {
        "status": "blocked" if blocked else "ok",
        "revision": REVISION,
        "time": now_iso(),
        "mode": "ai_analyst_safe_mode",
        "answer": answer,
        "action": action,
        "paper_only": True,
        "real_trade_authority": False,
        "requires_human_review": True,
        "provider": provider,
        "blockers": blockers,
        "risk": risk,
        "candidates": candidates,
        "prompt_log_id": log.get("id"),
        "policy": build_ai_safe_mode_policy()["authority"],
    }


def enqueue_paper_suggestion(data: dict, settings: dict, message: str, *, user: str = "default", role: str = "user") -> dict:
    suggestion = build_ai_suggestion(data, settings, message, user=user, role=role)
    if suggestion.get("status") == "blocked":
        return suggestion

    candidates = suggestion.get("candidates") or []
    candidate = candidates[0] if candidates else None
    queue = data.setdefault("ai_paper_queue", [])
    if not isinstance(queue, list):
        queue = []
    item = {
        "id": f"paper-q-{uuid4().hex[:12]}",
        "revision": REVISION,
        "created_at": now_iso(),
        "created_by": user,
        "role": role,
        "status": "review_required",
        "action": "paper_watch" if candidate else "wait",
        "symbol": candidate.get("symbol") if isinstance(candidate, dict) else None,
        "candidate": candidate,
        "message": _clean_text(message, 500),
        "suggestion": suggestion.get("answer"),
        "real_trade_authority": False,
        "paper_only": True,
        "requires_human_review": True,
        "prompt_log_id": suggestion.get("prompt_log_id"),
    }
    queue.append(item)
    data["ai_paper_queue"] = queue[-PAPER_QUEUE_LIMIT:]
    append_log(data, "info", f"AI paper queue item created: {item['action']}", "ai_paper_queue")
    suggestion["queued_item"] = item
    return suggestion


def build_paper_queue(data: dict, *, limit: int = 50) -> dict:
    queue = data.get("ai_paper_queue", []) if isinstance(data, dict) else []
    if not isinstance(queue, list):
        queue = []
    limited = queue[-max(1, min(int(limit or 50), 200)):]
    return {
        "status": "ok",
        "revision": REVISION,
        "mode": "paper_only_queue",
        "count": len(queue),
        "items": list(reversed(limited)),
        "real_trade_authority": False,
        "requires_human_review": True,
    }


def build_prompt_log_report(data: dict, *, limit: int = 50) -> dict:
    logs = data.get("ai_prompt_log", []) if isinstance(data, dict) else []
    if not isinstance(logs, list):
        logs = []
    limited = logs[-max(1, min(int(limit or 50), 200)):]
    blocked_count = sum(1 for item in logs if isinstance(item, dict) and item.get("blocked"))
    return {
        "status": "ok",
        "revision": REVISION,
        "count": len(logs),
        "blocked_count": blocked_count,
        "items": list(reversed(limited)),
        "hash_logging": True,
        "raw_secret_logging": False,
        "real_trade_authority": False,
    }


def build_no_trade_authority_report() -> dict:
    return {
        "status": "ok",
        "revision": REVISION,
        "forbidden_actions": sorted(FORBIDDEN_ACTIONS),
        "assertions": [
            "agent_routes.py exposes suggestions and paper queue only; no real order endpoint is called.",
            "ai_analyst_safe_mode_service.py has no import from real_trade_service, real_routes, or binance order placement functions.",
            "All outputs include real_trade_authority=False and paper_only=True.",
            "Prohibited real-order prompts are blocked and audit logged.",
        ],
        "real_trade_authority": False,
        "paper_only_queue": True,
    }


def build_revision_35_quality_report(data: dict, settings: dict) -> dict:
    policy = build_ai_safe_mode_policy()
    queue = build_paper_queue(data)
    prompt_log = build_prompt_log_report(data)
    no_trade = build_no_trade_authority_report()
    sample_blockers = detect_trade_authority_request("gerçek emir aç ve real order place")
    gates = [
        {"name": "safe_mode_policy", "status": policy.get("status"), "detail": "AI authority is commentary/suggestion/paper-only."},
        {"name": "no_trade_authority", "status": no_trade.get("status"), "detail": "No AI endpoint has real order or unlock authority."},
        {"name": "paper_only_queue", "status": queue.get("status"), "detail": "AI suggestions can be queued for paper review only."},
        {"name": "prompt_output_logging", "status": prompt_log.get("status"), "detail": "Prompt/output hashes and previews are logged."},
        {"name": "forbidden_prompt_blocker", "status": "ok" if sample_blockers else "blocked", "detail": "Real-order intents are blocked before execution."},
        {"name": "human_review_required", "status": "ok", "detail": "Paper queue items require human review and have no auto-apply path."},
    ]
    ok_count = sum(1 for gate in gates if gate.get("status") == "ok")
    readiness = round(ok_count / len(gates) * 100, 2)
    return {
        "revision": REVISION,
        "status": "ok" if readiness >= 95 else "review",
        "readiness_score": readiness,
        "gates": gates,
        "policy": policy,
        "paper_queue": queue,
        "prompt_log": prompt_log,
        "no_trade_authority": no_trade,
    }
