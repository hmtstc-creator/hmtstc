from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from services.autonomous_market_scanner_service import build_tradeability_decision
from services.real_trade_state_service import ensure_real_trade_state, is_unlock_valid, open_real_positions
from services.portfolio_allocation_final_service import build_active_risk_budget, build_usdt_reserve_policy


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _auto_policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    auto = settings.get("auto_bot_mode") if isinstance(settings.get("auto_bot_mode"), dict) else {}
    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    bot = settings.get("bot") if isinstance(settings.get("bot"), dict) else {}
    return {
        "enabled": bool(auto.get("enabled", True)),
        "allow_micro_real": bool(auto.get("allow_micro_real", False)),
        "allow_real": bool(auto.get("allow_real", False)),
        "min_micro_confidence": _safe_float(auto.get("min_micro_confidence"), 72.0),
        "min_paper_confidence": _safe_float(auto.get("min_paper_confidence"), 58.0),
        "max_warning_count": _safe_int(auto.get("max_warning_count"), 3),
        "max_blocker_count": _safe_int(auto.get("max_blocker_count"), 0),
        "max_open_positions": _safe_int(auto.get("max_open_positions") or bot.get("max_open_positions"), 5),
        "preferred_usdt_reserve_pct": _safe_float(auto.get("preferred_usdt_reserve_pct") or risk.get("preferred_usdt_reserve_pct"), 70.0),
        "daily_loss_stop_pct": _safe_float(auto.get("daily_loss_stop_pct") or risk.get("daily_loss_stop_pct"), 2.0),
        "paper_first": bool(auto.get("paper_first", True)),
    }


def _recent_realized_pnl(data: dict) -> list[float]:
    history = data.get("history") if isinstance(data.get("history"), list) else []
    values: list[float] = []
    for item in history[-50:]:
        if not isinstance(item, dict):
            continue
        pnl = item.get("pnl") or item.get("realized_pnl") or item.get("profit")
        if pnl is not None:
            values.append(_safe_float(pnl))
    real_state = ensure_real_trade_state(data)
    for item in (real_state.get("orders") or [])[-50:]:
        if isinstance(item, dict) and item.get("realized_pnl") is not None:
            values.append(_safe_float(item.get("realized_pnl")))
    return values[-50:]


def _performance_state(data: dict) -> dict:
    pnl_values = _recent_realized_pnl(data)
    losing_streak = 0
    for value in reversed(pnl_values):
        if value < 0:
            losing_streak += 1
        else:
            break
    wins = len([v for v in pnl_values if v > 0])
    losses = len([v for v in pnl_values if v < 0])
    win_rate = wins / max(wins + losses, 1) * 100
    return {
        "sample_size": len(pnl_values),
        "avg_recent_pnl": round(mean(pnl_values), 6) if pnl_values else 0.0,
        "losing_streak": losing_streak,
        "win_rate": round(win_rate, 2),
    }


def _mode_rank(mode: str) -> int:
    order = {
        "EMERGENCY_STOP": 0,
        "SAFE_MODE": 1,
        "OFF": 2,
        "WATCH": 3,
        "PAPER": 4,
        "MICRO_REAL": 5,
        "REAL": 6,
    }
    return order.get(str(mode or "WATCH"), 3)


def _lower_mode(mode: str, target: str) -> str:
    return target if _mode_rank(target) < _mode_rank(mode) else mode


def _decision_text(mode: str, reasons: list[str], symbols: list[str]) -> str:
    if mode == "EMERGENCY_STOP":
        return "Acil risk veya kilit aktif; bot tüm yeni işlemleri durdurmalı."
    if mode == "SAFE_MODE":
        return "Risk yüksek; bot sadece koruma ve izleme modunda kalmalı."
    if mode == "OFF":
        return "Otonom mod kapalı veya piyasa uygun değil; bot kapalı kalmalı."
    if mode == "WATCH":
        return "Piyasa net değil; bot beklemeli ve yeni taramaları izlemeli."
    if mode == "PAPER":
        return "Piyasa denenebilir; bot paper modda sinyalleri doğrulamalı."
    if mode == "MICRO_REAL":
        return f"Mikro gerçek işlem izni verilebilir; öncelikli adaylar: {', '.join(symbols[:3]) or 'aday yok'}."
    if mode == "REAL":
        return "Real mod teorik olarak uygun; yine de mevcut plan mikro gerçek işlemi önceliklendirir."
    return "Bot modu karar motoru beklemede."


def build_auto_bot_mode_decision(data: dict | None, settings: dict | None = None) -> dict:
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _auto_policy(settings)
    tradeability = build_tradeability_decision(data, settings)
    real_state = ensure_real_trade_state(data)
    reserve = build_usdt_reserve_policy(data, settings)
    risk_budget = build_active_risk_budget(data, settings)
    performance = _performance_state(data)
    blockers = set(tradeability.get("blockers") or [])
    warnings = set(tradeability.get("warnings") or [])
    reasons: list[str] = []

    open_positions = open_real_positions(real_state)
    confidence = _safe_float(tradeability.get("confidence"), 0.0)
    market_mode = str(tradeability.get("market_mode") or "WAIT")
    bot_running = bool(data.get("bot_running"))
    current_engine_status = str(data.get("engine_status") or "stopped")

    if not policy["enabled"]:
        blockers.add("auto_bot_mode_disabled")
        reasons.append("auto_bot_mode_disabled")
    if real_state.get("emergency_lock") or data.get("emergency_lock"):
        blockers.add("emergency_lock")
        reasons.append("emergency_lock")
    if real_state.get("manual_attention_required"):
        blockers.add("manual_attention_required")
        reasons.append("manual_attention_required")
    if len(open_positions) >= policy["max_open_positions"]:
        blockers.add("max_open_positions_reached")
        reasons.append("max_open_positions_reached")
    if str(reserve.get("status") or "").lower() == "blocked":
        blockers.add("usdt_reserve_blocked")
        reasons.append("usdt_reserve_blocked")
    elif str(reserve.get("status") or "").lower() == "review":
        warnings.add("usdt_reserve_review")
    if str(risk_budget.get("status") or "").lower() == "blocked":
        blockers.add("risk_budget_blocked")
        reasons.append("risk_budget_blocked")
    elif str(risk_budget.get("status") or "").lower() == "review":
        warnings.add("risk_budget_review")
    if abs(_safe_float(real_state.get("daily_pnl"), 0.0)) >= policy["daily_loss_stop_pct"] and _safe_float(real_state.get("daily_pnl"), 0.0) < 0:
        blockers.add("daily_loss_stop_reached")
        reasons.append("daily_loss_stop_reached")
    if performance["losing_streak"] >= 3:
        warnings.add("recent_losing_streak")
        reasons.append("recent_losing_streak")

    mode = "WATCH"
    action = "keep_watching"
    if blockers:
        mode = "SAFE_MODE"
        action = "pause_new_entries"
        if "emergency_lock" in blockers:
            mode = "EMERGENCY_STOP"
            action = "stop_all_new_entries"
    elif market_mode == "DANGER":
        mode = "SAFE_MODE"
        action = "pause_new_entries"
        reasons.append("market_danger")
    elif market_mode == "TRADE" and confidence >= policy["min_micro_confidence"] and tradeability.get("best_symbols"):
        if policy["allow_real"] and policy["allow_micro_real"] and is_unlock_valid(real_state) and not real_state.get("dry_run", True):
            mode = "MICRO_REAL"
            action = "allow_micro_real_entries"
        elif policy["paper_first"] or real_state.get("dry_run", True) or not is_unlock_valid(real_state):
            mode = "PAPER"
            action = "allow_paper_validation"
            warnings.add("real_requires_owner_unlock_or_policy")
        else:
            mode = "WATCH"
            action = "wait_for_real_unlock"
    elif market_mode in {"TRADE", "WATCH"} and confidence >= policy["min_paper_confidence"]:
        mode = "PAPER"
        action = "allow_paper_validation"
    elif market_mode in {"WAIT", "WATCH"}:
        mode = "WATCH"
        action = "keep_watching"
    else:
        mode = "OFF"
        action = "stay_off"

    if len(warnings) > policy["max_warning_count"] and mode in {"PAPER", "MICRO_REAL", "REAL"}:
        mode = _lower_mode(mode, "WATCH")
        action = "downgrade_to_watch_due_to_warnings"
        reasons.append("too_many_warnings")
    if len(blockers) > policy["max_blocker_count"] and mode not in {"SAFE_MODE", "EMERGENCY_STOP"}:
        mode = "SAFE_MODE"
        action = "pause_new_entries"
        reasons.append("blocker_threshold_exceeded")

    symbols = [str(item) for item in (tradeability.get("best_symbols") or []) if item]
    status = "blocked" if mode in {"SAFE_MODE", "EMERGENCY_STOP"} else ("review" if mode in {"WATCH", "PAPER"} or warnings else "ok")
    return {
        "status": status,
        "revision": 61,
        "engine": "auto_bot_mode_decision",
        "generated_at": now_iso(),
        "read_only": True,
        "current_state": {
            "bot_running": bot_running,
            "engine_status": current_engine_status,
            "owner_unlocked": bool(real_state.get("owner_unlocked")),
            "unlock_valid": bool(is_unlock_valid(real_state)),
            "dry_run": bool(real_state.get("dry_run", True)),
            "open_real_positions": len(open_positions),
        },
        "recommended_mode": mode,
        "recommended_action": action,
        "market_mode": market_mode,
        "confidence": round(_clamp(confidence), 2),
        "best_symbols": symbols[:5],
        "primary_strategy": tradeability.get("primary_strategy"),
        "blockers": sorted(blockers),
        "warnings": sorted(warnings),
        "reasons": sorted(set(reasons)) or ["policy_evaluated"],
        "policy": policy,
        "risk_budget": risk_budget,
        "usdt_reserve_policy": reserve,
        "performance_state": performance,
        "decision_text": _decision_text(mode, sorted(set(reasons)), symbols),
        "tradeability_decision": {
            "status": tradeability.get("status"),
            "recommended_bot_mode": tradeability.get("recommended_bot_mode"),
            "market_mode": tradeability.get("market_mode"),
            "confidence": tradeability.get("confidence"),
        },
    }


def build_summary_auto_bot_mode(data: dict | None, settings: dict | None = None) -> dict:
    decision = build_auto_bot_mode_decision(data, settings)
    return {
        "status": decision.get("status"),
        "revision": 61,
        "read_only": True,
        "bot_mode": decision.get("recommended_mode"),
        "action": decision.get("recommended_action"),
        "market_mode": decision.get("market_mode"),
        "confidence": decision.get("confidence"),
        "best_symbols": decision.get("best_symbols") or [],
        "risk_status": (decision.get("risk_budget") or {}).get("status", "review"),
        "blocker_count": len(decision.get("blockers") or []),
        "warning_count": len(decision.get("warnings") or []),
        "decision_text": decision.get("decision_text"),
        "updated_at": decision.get("generated_at"),
    }


def build_auto_bot_mode_quality(data: dict | None, settings: dict | None = None) -> dict:
    decision = build_auto_bot_mode_decision(data, settings)
    summary = build_summary_auto_bot_mode(data, settings)
    checks = {
        "decision_read_only": decision.get("read_only") is True,
        "revision_61": decision.get("revision") == 61,
        "mode_contract": decision.get("recommended_mode") in {"OFF", "WATCH", "PAPER", "MICRO_REAL", "REAL", "SAFE_MODE", "EMERGENCY_STOP"},
        "action_contract": bool(decision.get("recommended_action")),
        "risk_inputs_present": isinstance(decision.get("risk_budget"), dict) and isinstance(decision.get("usdt_reserve_policy"), dict),
        "summary_minimal": set(summary.keys()).issuperset({"bot_mode", "action", "market_mode", "confidence", "decision_text"}),
        "real_mode_guarded": decision.get("recommended_mode") != "MICRO_REAL" or (decision.get("policy", {}).get("allow_micro_real") is True and decision.get("current_state", {}).get("unlock_valid") is True),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "status": "ok" if not failed else "review",
        "revision": 61,
        "engine": "auto_bot_mode_decision_quality",
        "checks": checks,
        "failed_checks": failed,
        "coverage": [
            "market_tradeability_input",
            "bot_mode_recommendation",
            "real_trade_guardrails",
            "risk_budget_awareness",
            "summary_minimal_mode_output",
        ],
        "read_only": True,
        "generated_at": now_iso(),
    }
