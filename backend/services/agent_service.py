from __future__ import annotations

from typing import Any

from core.storage import append_log, now_iso
from services.risk_service import build_risk_snapshot
from services.llm_service import ask_openai_agent, llm_enabled
from services.ai_analyst_safe_mode_service import append_ai_prompt_log, sanitize_agent_output, detect_trade_authority_request, build_ai_safe_mode_policy


MAX_AGENT_CHAT_MESSAGES = 80
MAX_AGENT_REPORTS = 60


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _clean_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _latest_items(items: Any, limit: int = 5) -> list[dict]:
    if not isinstance(items, list):
        return []

    cleaned = [item for item in items if isinstance(item, dict)]
    return cleaned[-limit:]


def _scan_candidates(data: dict, limit: int = 8) -> list[dict]:
    last_scan = data.get("last_scan", {}) if isinstance(data, dict) else {}
    candidates = last_scan.get("candidates", []) if isinstance(last_scan, dict) else []

    if not isinstance(candidates, list):
        return []

    cleaned: list[dict] = []

    for item in candidates[:limit]:
        if not isinstance(item, dict):
            continue

        cleaned.append({
            "symbol": item.get("symbol"),
            "score": _safe_float(item.get("score")),
            "price": _safe_float(item.get("price")),
            "reason": item.get("reason") or item.get("status") or "scan_candidate",
            "strategy": item.get("strategy") or item.get("type") or "market_scan",
        })

    return cleaned


def build_agent_status(data: dict, settings: dict) -> dict:
    last_scan = data.get("last_scan", {}) if isinstance(data, dict) else {}
    positions = data.get("open_positions", []) if isinstance(data, dict) else []
    history = data.get("history", []) if isinstance(data, dict) else []
    reports = data.get("agent_reports", []) if isinstance(data, dict) else []
    chat = data.get("agent_chat", []) if isinstance(data, dict) else []

    if not isinstance(last_scan, dict):
        last_scan = {}

    candidates = _scan_candidates(data, limit=6)
    risk = build_risk_snapshot(data, settings)

    bot_running = bool(data.get("bot_running", False))
    scan_live = bool(last_scan.get("live", False))

    if bot_running and scan_live:
        mood = "active_scanning"
        headline = "Jarvis piyasayı aktif tarıyor."
    elif bot_running:
        mood = "scan_waiting"
        headline = "Jarvis aktif, canlı veri bekliyor."
    else:
        mood = "standby"
        headline = "Jarvis beklemede. Bot pasif."

    if candidates:
        headline = f"Jarvis {len(candidates)} potansiyel aday izliyor."

    return {
        "status": "ok",
        "agent": "jarvis",
        "version": "0.1-shadow",
        "time": now_iso(),
        "mood": mood,
        "headline": headline,
        "bot_running": bot_running,
        "engine_status": data.get("engine_status", "unknown"),
        "mode": data.get("mode", "shadow"),
        "scan_live": scan_live,
        "last_scan_time": last_scan.get("time"),
        "last_scan_error": last_scan.get("error"),
        "scanned": _safe_int(last_scan.get("scanned"), 0),
        "candidates_count": _safe_int(last_scan.get("candidates_count"), len(candidates)),
        "open_positions_count": len(positions) if isinstance(positions, list) else 0,
        "history_count": len(history) if isinstance(history, list) else 0,
        "risk": risk,
        "top_candidates": candidates,
        "latest_report": reports[-1] if isinstance(reports, list) and reports else None,
        "chat_count": len(chat) if isinstance(chat, list) else 0,
        "providers": {
            "binance": "active" if scan_live else "waiting",
            "x_twitter": "adapter_ready_no_key",
            "polymarket": "adapter_ready_no_key",
            "voice": "frontend_browser_api"
        }
    }


def build_agent_report(data: dict, settings: dict, persist: bool = False) -> dict:
    last_scan = data.get("last_scan", {}) if isinstance(data, dict) else {}
    positions = data.get("open_positions", []) if isinstance(data, dict) else []
    candidates = _scan_candidates(data, limit=10)
    risk = build_risk_snapshot(data, settings)

    if not isinstance(last_scan, dict):
        last_scan = {}

    strongest = candidates[0] if candidates else None
    risk_status = risk.get("risk_status", "unknown")

    if strongest and risk_status == "ok":
        action = "paper_watch"
        title = f"{strongest.get('symbol')} izleme listesine alındı."
        summary = (
            f"En güçlü aday {strongest.get('symbol')} görünüyor. "
            f"Skor: {_safe_float(strongest.get('score')):.2f}. "
            "Bu aşamada gerçek emir yok; sadece shadow/paper karar kaydı üretilir."
        )
    elif risk_status != "ok":
        action = "risk_blocked"
        title = "Risk limiti nedeniyle yeni fırsat beklemeye alındı."
        summary = "Risk kontrolü yeni paper fırsat üretimini bloke ediyor."
    else:
        action = "wait"
        title = "Net alım fırsatı yok."
        summary = "Mevcut taramada yeterli skora sahip aday oluşmadı. Bekleme modu korunuyor."

    report = {
        "id": f"jarvis-{now_iso()}",
        "status": "ok",
        "time": now_iso(),
        "action": action,
        "title": title,
        "summary": summary,
        "confidence": min(
            95,
            max(
                10,
                _safe_float(strongest.get("score"), 0) if strongest else 25
            )
        ),
        "paper_trade": {
            "enabled": True,
            "real_order": False,
            "candidate": strongest,
            "decision": action,
            "reason": summary,
        },
        "market": {
            "scan_live": bool(last_scan.get("live", False)),
            "last_scan_time": last_scan.get("time"),
            "scanned": _safe_int(last_scan.get("scanned"), 0),
            "candidates_count": len(candidates),
            "top_candidates": candidates[:5],
        },
        "positions": {
            "open_count": len(positions) if isinstance(positions, list) else 0,
            "items": _latest_items(positions, limit=5),
        },
        "risk": risk,
        "external_context": {
            "x_twitter": {
                "status": "adapter_ready",
                "note": "API anahtarı/provider bağlanınca haber-sentiment skoru üretilecek."
            },
            "polymarket": {
                "status": "adapter_ready",
                "note": "Provider bağlanınca olay bazlı piyasa ihtimali rapora eklenecek."
            }
        }
    }

    if persist:
        reports = data.setdefault("agent_reports", [])

        if isinstance(reports, list):
            reports.append(report)
            data["agent_reports"] = reports[-MAX_AGENT_REPORTS:]

        append_log(
            data,
            "info",
            f"Jarvis raporu üretildi: {action}",
            "agent_report"
        )

    return report


def build_chat_answer(data: dict, settings: dict, message: str) -> str:
    text = _clean_text(message).lower()

    if not text:
        return "Mesaj boş geldi. Bana market, risk, pozisyon veya fırsat durumunu sorabilirsin."

    if llm_enabled():
        llm_result = ask_openai_agent(data, settings, message)

        if llm_result.get("ok") and llm_result.get("answer"):
            return sanitize_agent_output(llm_result["answer"])

    status = build_agent_status(data, settings)
    report = build_agent_report(data, settings, persist=False)

    if any(word in text for word in ["fırsat", "alim", "alım", "buy", "coin"]):
        if report["paper_trade"].get("candidate"):
            candidate = report["paper_trade"]["candidate"]

            return (
                f"Şu an en güçlü paper aday {candidate.get('symbol')}. "
                f"Skor {_safe_float(candidate.get('score')):.2f}. "
                "Gerçek emir yok; izleme ve shadow karar modu aktif."
            )

        return "Şu an net alım fırsatı yok. Aday skoru veya risk/scan koşulları yeterli görünmüyor."

    if any(word in text for word in ["risk", "zarar", "limit", "bütçe", "butce"]):
        risk = status.get("risk", {})

        return (
            "Risk özeti: "
            f"aktif kullanım {risk.get('active_usdt', 0)} USDT, "
            f"bütçe {risk.get('allocated_usdt', 0)} USDT, "
            f"günlük PnL {risk.get('daily_pnl', 0)} USDT, "
            f"durum {risk.get('risk_status', 'unknown')}."
        )

    if any(word in text for word in ["pozisyon", "position", "açık", "acik"]):
        count = status.get("open_positions_count", 0)

        if count <= 0:
            return "Açık shadow pozisyon yok. Jarvis yeni aday oluşursa paper karar raporu üretecek."

        return f"Şu anda {count} açık shadow pozisyon var. Detayları pozisyonlar panelinden takip edebilirsin."

    if any(word in text for word in ["twitter", "x", "haber", "polymarket", "poly"]):
        return (
            "Haber/sentiment katmanı için adaptör hazır. "
            "X/Twitter ve Polymarket provider anahtarları bağlanınca rapora dış veri skoru ekleyeceğim."
        )

    if any(word in text for word in ["durum", "status", "ne yapıyorsun", "çalışıyor", "calisiyor"]):
        return status.get("headline", "Jarvis durum bilgisi hazır.")

    return (
        "Jarvis aktif. Şu anda market tarama, risk, açık pozisyon ve paper fırsat durumunu okuyabiliyorum. "
        "OpenAI bağlantısı aktif değilse kural tabanlı cevap veririm; API anahtarı bağlanınca daha akıllı analiz yaparım."
    )


def chat_with_agent(data: dict, settings: dict, message: str) -> dict:
    clean_message = _clean_text(message)
    answer = build_chat_answer(data, settings, clean_message)
    blockers = detect_trade_authority_request(clean_message)
    if blockers:
        answer = "AI Analyst Safe Mode gerçek emir/operasyon komutunu bloke etti. Yalnızca yorum ve paper öneri üretilebilir."
    chat = data.setdefault("agent_chat", [])

    if not isinstance(chat, list):
        chat = []

    now = now_iso()

    user_message = {
        "role": "user",
        "time": now,
        "message": clean_message,
    }

    assistant_message = {
        "role": "assistant",
        "time": now,
        "message": answer,
    }

    chat.extend([user_message, assistant_message])
    data["agent_chat"] = chat[-MAX_AGENT_CHAT_MESSAGES:]

    prompt_log = append_ai_prompt_log(
        data,
        user=str(data.get("username") or "default"),
        role="user",
        prompt=clean_message,
        output=answer,
        provider="openai" if llm_enabled() else "fallback",
        action="report_only" if blockers else "paper_queue",
        blocked=bool(blockers),
        blockers=blockers,
        source="agent_chat",
    )

    append_log(
        data,
        "info",
        "Jarvis sohbet yanıtı üretildi. AI Safe Mode loglandı.",
        "agent_chat"
    )

    return {
        "status": "ok",
        "time": now,
        "answer": answer,
        "messages": data["agent_chat"][-12:],
        "report": build_agent_report(data, settings, persist=False),
        "safe_mode": build_ai_safe_mode_policy(),
        "prompt_log_id": prompt_log.get("id"),
    }