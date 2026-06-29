from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_position_manager_service import build_autonomous_position_manager
from services.autonomous_safety_supervisor_service import build_autonomous_safety_supervisor
from services.autonomous_capital_allocator_service import build_autonomous_capital_allocator
from services.trade_quality_feedback_service import build_trade_quality_feedback


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_performance_sentinel") if isinstance(settings.get("autonomous_performance_sentinel"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_trade_sample": max(1, min(200, _safe_int(raw.get("min_trade_sample"), 5))),
        "target_win_rate_pct": _clamp(_safe_float(raw.get("target_win_rate_pct"), 54.0), 1.0, 95.0),
        "min_profit_factor": _clamp(_safe_float(raw.get("min_profit_factor"), 1.05), 0.1, 10.0),
        "max_drawdown_pct": _clamp(_safe_float(raw.get("max_drawdown_pct"), 2.0), 0.1, 50.0),
        "daily_profit_lock_pct": _clamp(_safe_float(raw.get("daily_profit_lock_pct"), 0.8), 0.05, 20.0),
        "cooldown_loss_streak": max(1, min(20, _safe_int(raw.get("cooldown_loss_streak"), 3))),
        "read_only": True,
        "auto_apply": False,
    }


def _trades(data: dict, limit: int = 100) -> list[dict]:
    buckets: list[dict] = []
    for key in ("closed_trades", "trades", "trade_history", "paper_trades", "real_trades"):
        value = data.get(key)
        if isinstance(value, list):
            buckets.extend(item for item in value if isinstance(item, dict))
    return buckets[-limit:]


def _wallet(data: dict) -> dict:
    wallet = data.get("wallet") if isinstance(data.get("wallet"), dict) else {}
    equity = _safe_float(wallet.get("total_usdt", wallet.get("equity_usdt", data.get("equity_usdt", 0.0))))
    today = _safe_float(wallet.get("today_pnl_usdt", data.get("today_pnl_usdt", 0.0)))
    return {"equity_usdt": equity, "today_pnl_usdt": today}


def _performance_stats(data: dict, settings: dict) -> dict:
    policy = _policy(settings)
    trades = _trades(data)
    sample = trades[-policy["min_trade_sample"]:] if trades else []
    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    streak = 0
    worst_streak = 0
    equity_curve = [0.0]
    running = 0.0
    for trade in sample:
        pnl = _safe_float(trade.get("pnl_usdt", trade.get("pnl", trade.get("profit_usdt", 0.0))))
        running += pnl
        equity_curve.append(running)
        if pnl > 0:
            wins += 1
            gross_profit += pnl
            streak = 0 if streak < 0 else streak + 1
        elif pnl < 0:
            losses += 1
            gross_loss += abs(pnl)
            streak = -1 if streak > 0 else streak - 1
            worst_streak = min(worst_streak, streak)
    peak = equity_curve[0] if equity_curve else 0.0
    max_drawdown_usdt = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_drawdown_usdt = max(max_drawdown_usdt, peak - value)
    wallet = _wallet(data)
    equity = wallet["equity_usdt"]
    drawdown_pct = (max_drawdown_usdt / equity * 100.0) if equity > 0 else 0.0
    win_rate = (wins / len(sample) * 100.0) if sample else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)
    today_pct = (wallet["today_pnl_usdt"] / equity * 100.0) if equity > 0 else 0.0
    return {
        "sample_size": len(sample),
        "win_count": wins,
        "loss_count": losses,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "max_drawdown_pct": round(drawdown_pct, 4),
        "today_pnl_usdt": round(wallet["today_pnl_usdt"], 6),
        "today_pnl_pct": round(today_pct, 4),
        "loss_streak": abs(worst_streak),
        "gross_profit_usdt": round(gross_profit, 6),
        "gross_loss_usdt": round(gross_loss, 6),
    }


def _sentinel_decision(stats: dict, policy: dict, safety: dict, capital: dict, position_manager: dict, quality: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not policy["enabled"]:
        return "MONITOR_ONLY", ["performance_sentinel_disabled"]
    if safety.get("kill_switch_active") or safety.get("safe_mode_required"):
        return "STOP_AND_PROTECT", ["safety_supervisor_requires_stop"]
    if stats["sample_size"] < policy["min_trade_sample"]:
        reasons.append("insufficient_trade_sample")
        return "PAPER_OBSERVE", reasons
    if stats["loss_streak"] >= policy["cooldown_loss_streak"]:
        reasons.append("loss_streak_cooldown")
    if stats["max_drawdown_pct"] >= policy["max_drawdown_pct"]:
        reasons.append("drawdown_limit_reached")
    if stats["win_rate_pct"] < policy["target_win_rate_pct"]:
        reasons.append("win_rate_below_target")
    if stats["profit_factor"] and stats["profit_factor"] < policy["min_profit_factor"]:
        reasons.append("profit_factor_below_target")
    if position_manager.get("protective_action_count", 0) > 0:
        reasons.append("open_positions_require_protection")
    if capital.get("allocation_state") == "BLOCKED":
        reasons.append("capital_allocator_blocked")
    if reasons:
        if any(reason in reasons for reason in ("drawdown_limit_reached", "loss_streak_cooldown", "capital_allocator_blocked")):
            return "COOLDOWN", sorted(set(reasons))
        return "TIGHTEN", sorted(set(reasons))
    if stats["today_pnl_pct"] >= policy["daily_profit_lock_pct"]:
        return "LOCK_PROFIT", ["daily_profit_lock_reached"]
    if quality.get("status") == "ok" and stats["profit_factor"] >= policy["min_profit_factor"] and stats["win_rate_pct"] >= policy["target_win_rate_pct"]:
        return "CONTINUE", ["performance_targets_met"]
    return "WATCH", ["neutral_performance"]


def build_autonomous_performance_sentinel(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev75 read-only performance sentinel.

    Converts recent realized performance into autonomous day-level guidance: continue,
    tighten, cooldown, profit-lock, or paper-observe. It never places orders and never
    persists runtime state; it only provides the next supervisory decision for Summary.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    stats = _performance_stats(data, settings)
    safety = build_autonomous_safety_supervisor(data, settings, auth_store, username)
    capital = build_autonomous_capital_allocator(data, settings, auth_store, username)
    position_manager = build_autonomous_position_manager(data, settings, auth_store, username)
    quality = build_trade_quality_feedback(data, settings)
    decision, reasons = _sentinel_decision(stats, policy, safety, capital, position_manager, quality)
    status = "ok" if decision in {"CONTINUE", "WATCH", "LOCK_PROFIT"} else ("review" if decision in {"TIGHTEN", "PAPER_OBSERVE", "MONITOR_ONLY"} else "blocked")
    return {
        "status": status,
        "revision": 75,
        "engine": "autonomous_performance_sentinel",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "performance_state": decision,
        "recommended_action": decision,
        "reasons": reasons,
        "stats": stats,
        "inputs": {
            "safety_state": safety.get("safety_state"),
            "kill_switch_active": safety.get("kill_switch_active"),
            "allocation_state": capital.get("allocation_state"),
            "position_lifecycle_state": position_manager.get("lifecycle_state"),
            "protective_action_count": position_manager.get("protective_action_count"),
            "quality_score": quality.get("quality_score"),
        },
        "policy": policy,
        "command_preview": {
            "type": "performance_sentinel_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "writes_runtime_state": False,
            "source_revision": 75,
            "action": decision,
        },
    }


def build_summary_autonomous_performance_sentinel(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_performance_sentinel(data, settings, auth_store, username)
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 75,
        "engine": "autonomous_performance_sentinel_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "performance_state": payload.get("performance_state"),
        "recommended_action": payload.get("recommended_action"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "win_rate_pct": stats.get("win_rate_pct", 0.0),
        "profit_factor": stats.get("profit_factor", 0.0),
        "max_drawdown_pct": stats.get("max_drawdown_pct", 0.0),
        "today_pnl_pct": stats.get("today_pnl_pct", 0.0),
        "reason_count": len(payload.get("reasons") or []),
    }


def build_autonomous_performance_sentinel_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_performance_sentinel(data, settings, auth_store, username)
    summary = build_summary_autonomous_performance_sentinel(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_75": payload.get("revision") == 75 and summary.get("revision") == 75,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "performance_stats_visible": isinstance(payload.get("stats"), dict) and "win_rate_pct" in payload.get("stats", {}),
        "source_chain_visible": isinstance(payload.get("inputs"), dict) and "position_lifecycle_state" in payload.get("inputs", {}),
        "summary_minimal": set(["performance_state", "recommended_action", "win_rate_pct", "profit_factor", "attention_required"]).issubset(summary.keys()),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "signed_payload" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 75,
        "engine": "autonomous_performance_sentinel_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "performance_state": payload.get("performance_state"),
        "status_source": payload.get("status"),
    }
