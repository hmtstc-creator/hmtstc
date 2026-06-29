from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_safety_supervisor_service import build_autonomous_safety_supervisor


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if value is None:
        return fallback
    return bool(value)


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_evidence_learning_memory") if isinstance(settings.get("autonomous_evidence_learning_memory"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "max_recent_trades": max(3, min(200, _safe_int(raw.get("max_recent_trades"), 30))),
        "min_sample_size": max(1, min(50, _safe_int(raw.get("min_sample_size"), 5))),
        "learning_score_target": max(0.0, min(100.0, _safe_float(raw.get("learning_score_target"), 65.0))),
        "persist_memory": False,
        "read_only": True,
    }


def _extract_trades(data: dict, limit: int) -> list[dict]:
    trades = data.get("closed_trades") if isinstance(data.get("closed_trades"), list) else []
    normalized: list[dict] = []
    for idx, trade in enumerate(trades[-limit:]):
        if not isinstance(trade, dict):
            continue
        entry_q = _safe_float(trade.get("entry_quality_score", trade.get("entry_quality", 0.0)))
        exit_q = _safe_float(trade.get("exit_quality_score", trade.get("exit_quality", 0.0)))
        align_q = _safe_float(trade.get("strategy_alignment_score", trade.get("strategy_alignment", 0.0)))
        pnl = _safe_float(trade.get("pnl_usdt", trade.get("pnl", 0.0)))
        quality_values = [v for v in [entry_q, exit_q, align_q] if v > 0]
        avg_quality = sum(quality_values) / len(quality_values) if quality_values else (60.0 if pnl >= 0 else 40.0)
        normalized.append({
            "index": idx,
            "symbol": str(trade.get("symbol") or "UNKNOWN"),
            "strategy": str(trade.get("strategy") or trade.get("primary_strategy") or "unknown"),
            "pnl_usdt": round(pnl, 6),
            "entry_quality_score": round(entry_q, 2),
            "exit_quality_score": round(exit_q, 2),
            "strategy_alignment_score": round(align_q, 2),
            "quality_score": round(avg_quality, 2),
            "won": pnl > 0,
        })
    return normalized


def _aggregate_by(items: list[dict], key: str) -> list[dict]:
    buckets: dict[str, dict[str, Any]] = {}
    for item in items:
        name = str(item.get(key) or "unknown")
        bucket = buckets.setdefault(name, {"name": name, "count": 0, "wins": 0, "pnl_usdt": 0.0, "quality_sum": 0.0})
        bucket["count"] += 1
        bucket["wins"] += 1 if item.get("won") else 0
        bucket["pnl_usdt"] += _safe_float(item.get("pnl_usdt"))
        bucket["quality_sum"] += _safe_float(item.get("quality_score"))
    rows: list[dict] = []
    for bucket in buckets.values():
        count = max(1, bucket["count"])
        rows.append({
            "name": bucket["name"],
            "count": bucket["count"],
            "win_rate": round((bucket["wins"] / count) * 100.0, 2),
            "pnl_usdt": round(bucket["pnl_usdt"], 6),
            "quality_score": round(bucket["quality_sum"] / count, 2),
        })
    rows.sort(key=lambda row: (row["quality_score"], row["pnl_usdt"], row["count"]), reverse=True)
    return rows


def _decision_quality(supervisor: dict, trades: list[dict], policy: dict) -> tuple[float, list[str], list[str]]:
    strengths: list[str] = []
    gaps: list[str] = []
    quality_values = [_safe_float(item.get("quality_score")) for item in trades]
    avg_quality = sum(quality_values) / len(quality_values) if quality_values else 0.0
    win_rate = (sum(1 for item in trades if item.get("won")) / len(trades) * 100.0) if trades else 0.0
    base = avg_quality if trades else 50.0
    if supervisor.get("kill_switch_active"):
        base -= 15.0
        gaps.append("safety_kill_switch_recently_active")
    if supervisor.get("safe_mode_required"):
        base -= 8.0
        gaps.append("safe_mode_required")
    if len(trades) < policy["min_sample_size"]:
        base -= 10.0
        gaps.append("sample_size_low")
    if win_rate >= 55.0 and avg_quality >= policy["learning_score_target"]:
        base += 8.0
        strengths.append("recent_trade_set_is_repeatable")
    if supervisor.get("safety_state") in {"ARMED", "MONITOR"}:
        base += 5.0
        strengths.append("safety_state_stable")
    score = max(0.0, min(100.0, base))
    if score < policy["learning_score_target"]:
        gaps.append("learning_score_below_target")
    return round(score, 2), sorted(set(strengths)), sorted(set(gaps))


def _recommendations(score: float, supervisor: dict, trades: list[dict], strategy_rows: list[dict], symbol_rows: list[dict]) -> list[dict]:
    recs: list[dict] = []
    if supervisor.get("kill_switch_active"):
        recs.append({"priority": "critical", "action": "keep_kill_switch", "reason": "Safety supervisor hard blocker aktif."})
    elif supervisor.get("safe_mode_required"):
        recs.append({"priority": "high", "action": "stay_in_safe_mode", "reason": "Kalite veya güven düşük; gerçek işlem hattı beklemeli."})
    if trades and score >= 70 and strategy_rows:
        recs.append({"priority": "medium", "action": "prefer_best_repeatable_strategy", "reason": f"{strategy_rows[0]['name']} son örnekte en güçlü strateji kümesi."})
    if symbol_rows and symbol_rows[0].get("count", 0) >= 2 and symbol_rows[0].get("pnl_usdt", 0) > 0:
        recs.append({"priority": "medium", "action": "keep_symbol_in_watchlist", "reason": f"{symbol_rows[0]['name']} pozitif tekrar sinyali verdi."})
    if not recs:
        recs.append({"priority": "low", "action": "collect_more_evidence", "reason": "Karar hafızası için daha fazla kapalı işlem örneği gerekli."})
    return recs[:5]


def build_autonomous_evidence_learning_memory(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev72 read-only evidence and learning memory layer.

    This layer does not place orders and does not persist secrets or runtime state.
    It converts the autonomous chain outputs and recent closed trades into a compact
    evidence packet: why the current safety/action decision exists, which patterns
    are repeatable, and what the next safe learning action should be.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    supervisor = build_autonomous_safety_supervisor(data, settings, auth_store, username)
    trades = _extract_trades(data, policy["max_recent_trades"])
    strategy_rows = _aggregate_by(trades, "strategy")
    symbol_rows = _aggregate_by(trades, "symbol")
    score, strengths, gaps = _decision_quality(supervisor, trades, policy)
    recommendations = _recommendations(score, supervisor, trades, strategy_rows, symbol_rows)
    status = "ok" if score >= policy["learning_score_target"] and not supervisor.get("kill_switch_active") else "review"
    if supervisor.get("kill_switch_active"):
        status = "blocked"

    return {
        "status": status,
        "revision": 72,
        "engine": "autonomous_evidence_learning_memory",
        "generated_at": now_iso(),
        "read_only": True,
        "persist_memory": False,
        "learning_score": score,
        "sample_size": len(trades),
        "strengths": strengths,
        "learning_gaps": gaps,
        "recommendations": recommendations,
        "evidence_packet": {
            "safety_state": supervisor.get("safety_state"),
            "safety_action": supervisor.get("safety_action"),
            "can_execute": supervisor.get("can_execute"),
            "kill_switch_active": supervisor.get("kill_switch_active"),
            "safe_mode_required": supervisor.get("safe_mode_required"),
            "hard_blockers": supervisor.get("hard_blockers") or [],
            "warnings": supervisor.get("warnings") or [],
            "control_loop": supervisor.get("control_loop") or {},
        },
        "memory_preview": {
            "top_strategies": strategy_rows[:5],
            "top_symbols": symbol_rows[:5],
            "recent_trade_quality": trades[-10:],
        },
        "policy": policy,
        "command_preview": {
            "type": "record_learning_evidence",
            "read_only": True,
            "requires_execution_guard": True,
            "writes_runtime_state": False,
            "source_revision": 72,
        },
    }


def build_summary_autonomous_evidence_learning_memory(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_evidence_learning_memory(data, settings, auth_store, username)
    recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
    return {
        "status": payload.get("status"),
        "revision": 72,
        "engine": "autonomous_evidence_learning_memory_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "learning_score": payload.get("learning_score"),
        "sample_size": payload.get("sample_size"),
        "safety_state": (payload.get("evidence_packet") or {}).get("safety_state"),
        "next_learning_action": (recommendations[0] or {}).get("action") if recommendations else "collect_more_evidence",
        "attention_required": payload.get("status") in {"review", "blocked"},
        "gap_count": len(payload.get("learning_gaps") or []),
        "strength_count": len(payload.get("strengths") or []),
    }


def build_autonomous_evidence_learning_memory_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_evidence_learning_memory(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    evidence = payload.get("evidence_packet") if isinstance(payload.get("evidence_packet"), dict) else {}
    memory = payload.get("memory_preview") if isinstance(payload.get("memory_preview"), dict) else {}
    checks = {
        "revision_72": payload.get("revision") == 72,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "no_runtime_persistence": payload.get("persist_memory") is False and command.get("writes_runtime_state") is False,
        "safety_source_visible": evidence.get("safety_state") in {"ARMED", "MONITOR", "SAFE_MODE", "KILL_SWITCH"},
        "learning_score_available": isinstance(payload.get("learning_score"), (int, float)),
        "memory_preview_available": isinstance(memory.get("top_strategies"), list) and isinstance(memory.get("top_symbols"), list),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "signed_payload" not in str(payload).lower(),
        "execution_guard_required": command.get("requires_execution_guard") is True,
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 72,
        "engine": "autonomous_evidence_learning_memory_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "learning_score": payload.get("learning_score"),
        "sample_size": payload.get("sample_size"),
        "status_source": payload.get("status"),
    }
