from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.auto_bot_mode_decision_service import build_auto_bot_mode_decision
from services.strategy_selection_engine_service import build_strategy_selection_engine


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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _risk_policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    bot = settings.get("bot") if isinstance(settings.get("bot"), dict) else {}
    brain = settings.get("risk_brain") if isinstance(settings.get("risk_brain"), dict) else {}
    allocated = _safe_float(bot.get("allocated_usdt"), _safe_float(risk.get("capital_usdt"), 1000.0))
    return {
        "enabled": bool(brain.get("enabled", True)),
        "capital_usdt": max(0.0, allocated),
        "min_usdt_reserve_pct": _safe_float(brain.get("min_usdt_reserve_pct"), _safe_float(risk.get("min_usdt_reserve_pct"), 85.0)),
        "max_daily_loss_pct": _safe_float(brain.get("max_daily_loss_pct"), _safe_float(risk.get("daily_loss_limit_percent"), 2.0)),
        "max_active_risk_pct": _safe_float(brain.get("max_active_risk_pct"), _safe_float(risk.get("max_portfolio_risk_percent"), 10.0)),
        "base_order_pct": _safe_float(brain.get("base_order_pct"), 0.35),
        "max_order_pct": _safe_float(brain.get("max_order_pct"), 1.25),
        "min_confidence": _safe_float(brain.get("min_confidence"), 60.0),
        "max_open_positions": _safe_int(brain.get("max_open_positions"), _safe_int(bot.get("max_open_positions"), 5)),
        "loss_streak_safe_mode": _safe_int(brain.get("loss_streak_safe_mode"), 3),
        "profit_lock_step_pct": _safe_float(brain.get("profit_lock_step_pct"), 0.5),
    }


def _wallet_usdt(data: dict) -> tuple[float, float]:
    real_trade = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    wallet = real_trade.get("wallet") if isinstance(real_trade.get("wallet"), dict) else {}
    usdt = wallet.get("USDT") if isinstance(wallet.get("USDT"), dict) else {}
    free = _safe_float(usdt.get("free"), _safe_float(data.get("usdt_free"), 0.0))
    locked = _safe_float(usdt.get("locked"), _safe_float(data.get("usdt_locked"), 0.0))
    return max(0.0, free), max(0.0, locked)


def _position_notional(position: dict) -> float:
    return max(
        _safe_float(position.get("notional_usdt")),
        _safe_float(position.get("quote_qty")),
        _safe_float(position.get("quote_order_qty")),
        _safe_float(position.get("value_usdt")),
    )


def _positions(data: dict) -> list[dict]:
    candidates: list[dict] = []
    for key in ("positions", "paper_positions", "real_positions"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    real_trade = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    value = real_trade.get("positions")
    if isinstance(value, list):
        candidates.extend([item for item in value if isinstance(item, dict)])
    return candidates


def _pnl_summary(data: dict) -> dict:
    perf = data.get("performance") if isinstance(data.get("performance"), dict) else {}
    reconciliation = data.get("reconciliation") if isinstance(data.get("reconciliation"), dict) else {}
    today = _safe_float(perf.get("today_pnl_usdt"), _safe_float(reconciliation.get("today_pnl_usdt"), _safe_float(data.get("today_pnl_usdt"), 0.0)))
    realized = _safe_float(perf.get("realized_pnl_usdt"), _safe_float(reconciliation.get("realized_pnl_usdt"), 0.0))
    unrealized = _safe_float(perf.get("unrealized_pnl_usdt"), _safe_float(reconciliation.get("unrealized_pnl_usdt"), 0.0))
    return {"today_pnl_usdt": round(today, 4), "realized_pnl_usdt": round(realized, 4), "unrealized_pnl_usdt": round(unrealized, 4)}


def _loss_streak(data: dict) -> int:
    history = data.get("history") or data.get("trades") or []
    if not isinstance(history, list):
        return 0
    streak = 0
    for item in reversed(history[-25:]):
        if not isinstance(item, dict):
            continue
        pnl = _safe_float(item.get("pnl_usdt"), _safe_float(item.get("pnl"), 0.0))
        if pnl < 0:
            streak += 1
        elif pnl > 0:
            break
    return streak


def build_risk_brain(data: dict | None, settings: dict | None = None) -> dict:
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _risk_policy(settings)
    strategy = build_strategy_selection_engine(data, settings)
    bot_mode = build_auto_bot_mode_decision(data, settings)
    mode = str(strategy.get("recommended_mode") or bot_mode.get("recommended_mode") or "WATCH")
    primary = strategy.get("selected_strategies", [{}])[0] if strategy.get("selected_strategies") else {}
    confidence = _safe_float(strategy.get("confidence"), _safe_float(bot_mode.get("confidence"), 0.0))

    free_usdt, locked_usdt = _wallet_usdt(data)
    capital = policy["capital_usdt"] or max(free_usdt + locked_usdt, 1.0)
    positions = _positions(data)
    active_usdt = sum(_position_notional(item) for item in positions)
    active_risk_pct = (active_usdt / capital * 100) if capital else 0.0
    reserve_pct = (free_usdt / capital * 100) if capital else 0.0
    pnl = _pnl_summary(data)
    today_loss_pct = abs(min(0.0, pnl["today_pnl_usdt"])) / capital * 100 if capital else 0.0
    loss_streak = _loss_streak(data)

    blockers = set(strategy.get("blockers") or []) | set(bot_mode.get("blockers") or [])
    warnings = set(strategy.get("warnings") or []) | set(bot_mode.get("warnings") or [])
    if not policy["enabled"]:
        blockers.add("risk_brain_disabled")
    if mode in {"OFF", "SAFE_MODE", "EMERGENCY_STOP"}:
        blockers.add("bot_mode_blocks_new_risk")
    if strategy.get("primary_strategy") in {None, "NO_TRADE"}:
        blockers.add("no_strategy_for_risk")
    if confidence < policy["min_confidence"]:
        warnings.add("confidence_below_risk_threshold")
    if reserve_pct < policy["min_usdt_reserve_pct"]:
        blockers.add("usdt_reserve_below_policy")
    if active_risk_pct >= policy["max_active_risk_pct"]:
        blockers.add("active_risk_budget_full")
    if today_loss_pct >= policy["max_daily_loss_pct"]:
        blockers.add("daily_loss_limit_reached")
    if len(positions) >= policy["max_open_positions"]:
        blockers.add("max_open_positions_reached")
    if loss_streak >= policy["loss_streak_safe_mode"]:
        blockers.add("loss_streak_safe_mode")

    confidence_factor = _clamp(confidence / 100.0, 0.25, 1.0)
    reserve_factor = _clamp((reserve_pct - policy["min_usdt_reserve_pct"]) / 15.0, 0.0, 1.0)
    drawdown_factor = 1.0 - _clamp(today_loss_pct / max(policy["max_daily_loss_pct"], 0.1), 0.0, 1.0)
    raw_order_pct = policy["base_order_pct"] * confidence_factor * max(0.35, reserve_factor) * max(0.25, drawdown_factor)
    order_pct = min(policy["max_order_pct"], raw_order_pct)
    remaining_risk_usdt = max(0.0, capital * policy["max_active_risk_pct"] / 100.0 - active_usdt)
    suggested_order_usdt = min(capital * order_pct / 100.0, remaining_risk_usdt, free_usdt)

    if blockers:
        status = "blocked"
        action = "do_not_open_new_trade"
        risk_status = "DANGER" if any(x in blockers for x in {"daily_loss_limit_reached", "loss_streak_safe_mode", "bot_mode_blocks_new_risk"}) else "WAIT"
        suggested_order_usdt = 0.0
    elif warnings:
        status = "review"
        action = "micro_size_only"
        risk_status = "CAUTION"
    else:
        status = "ok"
        action = "allow_micro_risk"
        risk_status = "NORMAL"

    return {
        "status": status,
        "revision": 63,
        "engine": "risk_brain",
        "generated_at": now_iso(),
        "read_only": True,
        "risk_status": risk_status,
        "recommended_action": action,
        "recommended_mode": mode,
        "primary_symbol": strategy.get("primary_symbol") or primary.get("symbol"),
        "primary_strategy": strategy.get("primary_strategy") or primary.get("strategy"),
        "confidence": round(confidence, 2),
        "capital_usdt": round(capital, 4),
        "free_usdt": round(free_usdt, 4),
        "locked_usdt": round(locked_usdt, 4),
        "active_usdt": round(active_usdt, 4),
        "reserve_pct": round(reserve_pct, 2),
        "active_risk_pct": round(active_risk_pct, 2),
        "today_pnl_usdt": pnl["today_pnl_usdt"],
        "today_loss_pct": round(today_loss_pct, 3),
        "loss_streak": loss_streak,
        "open_positions": len(positions),
        "remaining_risk_usdt": round(remaining_risk_usdt, 4),
        "suggested_order_usdt": round(max(0.0, suggested_order_usdt), 4),
        "max_order_usdt": round(capital * policy["max_order_pct"] / 100.0, 4),
        "blockers": sorted(blockers),
        "warnings": sorted(warnings),
        "policy": policy,
        "decision_text": _decision_text(status, risk_status, action, blockers, strategy),
        "source": {
            "strategy_revision": strategy.get("revision"),
            "auto_bot_revision": bot_mode.get("revision"),
        },
    }


def _decision_text(status: str, risk_status: str, action: str, blockers: set[str], strategy: dict) -> str:
    if status == "blocked":
        if "daily_loss_limit_reached" in blockers:
            return "Günlük zarar limiti doldu; sistem yeni risk almamalı."
        if "usdt_reserve_below_policy" in blockers:
            return "USDT rezervi düşük; sistem nakitte kalmalı."
        if "loss_streak_safe_mode" in blockers:
            return "Ardışık zarar limiti aşıldı; sistem güvenli moda geçmeli."
        return "Risk beyni yeni işlem açılmasını blokladı."
    if status == "review":
        return "Risk beyni sadece düşük mikro pozisyon öneriyor."
    symbol = strategy.get("primary_symbol") or "seçili sembol"
    strategy_name = strategy.get("primary_strategy") or "seçili strateji"
    return f"{symbol} için {strategy_name} düşük riskli mikro işlem bütçesiyle uygun."


def build_summary_risk_brain(data: dict | None, settings: dict | None = None) -> dict:
    decision = build_risk_brain(data, settings)
    return {
        "status": decision.get("status"),
        "revision": 63,
        "read_only": True,
        "risk_status": decision.get("risk_status"),
        "action": decision.get("recommended_action"),
        "bot_mode": decision.get("recommended_mode"),
        "primary_symbol": decision.get("primary_symbol"),
        "primary_strategy": decision.get("primary_strategy"),
        "suggested_order_usdt": decision.get("suggested_order_usdt"),
        "reserve_pct": decision.get("reserve_pct"),
        "active_risk_pct": decision.get("active_risk_pct"),
        "today_pnl_usdt": decision.get("today_pnl_usdt"),
        "blocker_count": len(decision.get("blockers") or []),
        "warning_count": len(decision.get("warnings") or []),
        "decision_text": decision.get("decision_text"),
        "updated_at": decision.get("generated_at"),
    }


def build_risk_brain_quality(data: dict | None, settings: dict | None = None) -> dict:
    decision = build_risk_brain(data, settings)
    summary = build_summary_risk_brain(data, settings)
    checks = {
        "decision_read_only": decision.get("read_only") is True,
        "revision_63": decision.get("revision") == 63,
        "risk_status_contract": decision.get("risk_status") in {"NORMAL", "CAUTION", "WAIT", "DANGER"},
        "suggested_order_non_negative": _safe_float(decision.get("suggested_order_usdt")) >= 0,
        "blocks_when_policy_blocks": bool(decision.get("blockers")) == (decision.get("status") == "blocked") or decision.get("status") == "review",
        "summary_contract": summary.get("revision") == 63 and summary.get("read_only") is True,
        "source_linked": decision.get("source", {}).get("strategy_revision") == 62,
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 63,
        "engine": "risk_brain_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "decision_status": decision.get("status"),
        "risk_status": decision.get("risk_status"),
        "blockers": decision.get("blockers", []),
        "warnings": decision.get("warnings", []),
    }
