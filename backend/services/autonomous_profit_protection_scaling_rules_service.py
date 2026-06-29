from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_fully_autonomous_small_capital_mode_service import (
    build_autonomous_fully_autonomous_small_capital_mode,
)


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
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled", "allow", "auto"}
    if value is None:
        return fallback
    return bool(value)


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_profit_protection_scaling_rules") if isinstance(settings.get("autonomous_profit_protection_scaling_rules"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 97,
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "direct_order_enabled": _safe_bool(raw.get("direct_order_enabled"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "real_submit_enabled": _safe_bool(raw.get("real_submit_enabled"), False),
        "profit_reserve_enabled": _safe_bool(raw.get("profit_reserve_enabled"), True),
        "withdrawal_recommendation_enabled": _safe_bool(raw.get("withdrawal_recommendation_enabled"), True),
        "anti_overtrade_enabled": _safe_bool(raw.get("anti_overtrade_enabled"), True),
        "min_source_autonomy_score": max(1.0, min(100.0, _safe_float(raw.get("min_source_autonomy_score"), 78.0))),
        "profit_reserve_pct": max(0.0, min(95.0, _safe_float(raw.get("profit_reserve_pct"), 40.0))),
        "daily_profit_lock_trigger_usdt": max(0.1, _safe_float(raw.get("daily_profit_lock_trigger_usdt"), 3.0)),
        "withdrawal_trigger_usdt": max(1.0, _safe_float(raw.get("withdrawal_trigger_usdt"), 15.0)),
        "base_notional_usdt": max(5.0, _safe_float(raw.get("base_notional_usdt"), 12.0)),
        "max_scaled_notional_usdt": max(5.0, _safe_float(raw.get("max_scaled_notional_usdt"), 25.0)),
        "scale_up_step_pct": max(0.0, min(50.0, _safe_float(raw.get("scale_up_step_pct"), 10.0))),
        "scale_down_step_pct": max(0.0, min(80.0, _safe_float(raw.get("scale_down_step_pct"), 25.0))),
        "min_monthly_score_for_scale_up": max(1.0, min(100.0, _safe_float(raw.get("min_monthly_score_for_scale_up"), 72.0))),
        "min_profit_factor_for_scale_up": max(0.1, _safe_float(raw.get("min_profit_factor_for_scale_up"), 1.25)),
        "max_drawdown_pct_for_scale_up": max(0.1, _safe_float(raw.get("max_drawdown_pct_for_scale_up"), 4.0)),
        "max_daily_trade_cap": max(1, _safe_int(raw.get("max_daily_trade_cap"), 3)),
        "cooldown_after_loss_streak": max(1, _safe_int(raw.get("cooldown_after_loss_streak"), 2)),
        "scale_up_after_win_streak": max(1, _safe_int(raw.get("scale_up_after_win_streak"), 4)),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_fully_autonomous_small_capital_mode") if isinstance(data.get("autonomous_fully_autonomous_small_capital_mode"), dict) else None
    if raw and raw.get("revision") == 97 and "command_preview" in raw:
        return raw
    return build_autonomous_fully_autonomous_small_capital_mode(data, settings, auth_store, username)


def _performance_metrics(data: dict) -> dict:
    perf = data.get("micro_real_performance") if isinstance(data.get("micro_real_performance"), dict) else {}
    monthly = data.get("monthly_performance") if isinstance(data.get("monthly_performance"), dict) else {}
    today_pnl = _safe_float(data.get("today_real_pnl_usdt", data.get("today_pnl_usdt", perf.get("today_pnl_usdt"))), 0.0)
    month_pnl = _safe_float(monthly.get("net_pnl_usdt", perf.get("month_pnl_usdt", data.get("month_real_pnl_usdt"))), 0.0)
    win_rate = _safe_float(monthly.get("win_rate", perf.get("win_rate", data.get("micro_real_win_rate"))), 0.0)
    profit_factor = _safe_float(monthly.get("profit_factor", perf.get("profit_factor", data.get("micro_real_profit_factor"))), 1.0)
    drawdown_pct = abs(_safe_float(monthly.get("max_drawdown_pct", perf.get("max_drawdown_pct", data.get("micro_real_drawdown_pct"))), 0.0))
    trades = _safe_int(monthly.get("trade_count", perf.get("trade_count", data.get("micro_real_trade_count"))), 0)
    daily_trades = _safe_int(data.get("today_real_trade_count", data.get("daily_real_trade_count")), 0)
    win_streak = _safe_int(data.get("consecutive_real_wins", perf.get("consecutive_wins")), 0)
    loss_streak = _safe_int(data.get("consecutive_real_losses", perf.get("consecutive_losses")), 0)
    return {
        "today_pnl_usdt": today_pnl,
        "month_pnl_usdt": month_pnl,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_pct": drawdown_pct,
        "trade_count": trades,
        "daily_trades": daily_trades,
        "consecutive_wins": win_streak,
        "consecutive_losses": loss_streak,
    }


def _monthly_score(metrics: dict) -> float:
    score = 50.0
    score += min(18.0, max(-8.0, metrics["month_pnl_usdt"] * 0.6))
    score += min(14.0, max(0.0, (metrics["win_rate"] - 45.0) * 0.45))
    score += min(14.0, max(-10.0, (metrics["profit_factor"] - 1.0) * 20.0))
    score -= min(18.0, metrics["max_drawdown_pct"] * 2.4)
    score += min(6.0, metrics["trade_count"] * 0.25)
    score += min(5.0, metrics["consecutive_wins"] * 1.0)
    score -= min(12.0, metrics["consecutive_losses"] * 4.0)
    return round(max(0.0, min(100.0, score)), 2)


def build_autonomous_profit_protection_scaling_rules(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev98 profit protection and scaling controller.

    This layer does not execute orders. It converts Rev97 small-capital readiness
    plus realized micro-real performance into reserve, lock, withdrawal and size
    scaling recommendations.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    metrics = _performance_metrics(data)
    monthly_score = _monthly_score(metrics)
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("profit_protection_scaling_rules_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_small_capital_revision_mismatch")
    if source.get("status") not in {"ok", "review"}:
        blockers.append("source_small_capital_not_available")
    if source.get("decision") == "stop":
        blockers.append("source_small_capital_stop_decision")
    if _safe_float(source.get("autonomy_score"), 0.0) < policy["min_source_autonomy_score"]:
        warnings.append("source_autonomy_score_below_scaling_minimum")

    if policy["network_calls_allowed"]:
        blockers.append("network_calls_must_remain_disabled_for_rev98")
    if policy["direct_order_enabled"]:
        blockers.append("direct_order_must_remain_disabled_for_rev98")
    if policy["runtime_write_enabled"]:
        blockers.append("runtime_write_must_remain_disabled_for_rev98")
    if policy["real_submit_enabled"]:
        blockers.append("real_submit_must_remain_disabled_for_rev98")

    if policy["anti_overtrade_enabled"] and metrics["daily_trades"] >= policy["max_daily_trade_cap"]:
        warnings.append("anti_overtrade_daily_trade_cap_reached")
    if metrics["consecutive_losses"] >= policy["cooldown_after_loss_streak"]:
        blockers.append("loss_streak_cooldown_required")
    if metrics["max_drawdown_pct"] > policy["max_drawdown_pct_for_scale_up"] * 1.5:
        blockers.append("drawdown_requires_reduce_or_stop")

    source_notional = _safe_float((source.get("small_capital_constraints") or {}).get("preview_notional_usdt") if isinstance(source.get("small_capital_constraints"), dict) else 0.0, 0.0)
    current_notional = source_notional or policy["base_notional_usdt"]
    profit_reserve_usdt = max(0.0, metrics["today_pnl_usdt"]) * policy["profit_reserve_pct"] / 100.0 if policy["profit_reserve_enabled"] else 0.0
    available_profit_after_reserve = max(0.0, metrics["today_pnl_usdt"] - profit_reserve_usdt)

    if metrics["today_pnl_usdt"] >= policy["daily_profit_lock_trigger_usdt"]:
        profit_lock_action = "LOCK_DAILY_PROFIT_AND_LIMIT_NEW_RISK"
        warnings.append("daily_profit_lock_triggered")
    else:
        profit_lock_action = "NO_DAILY_PROFIT_LOCK"

    if policy["withdrawal_recommendation_enabled"] and metrics["month_pnl_usdt"] >= policy["withdrawal_trigger_usdt"]:
        withdrawal_action = "RECOMMEND_PROFIT_WITHDRAWAL_OR_RESERVE_TRANSFER"
    else:
        withdrawal_action = "NO_WITHDRAWAL_ACTION"

    can_scale_up = (
        monthly_score >= policy["min_monthly_score_for_scale_up"]
        and metrics["profit_factor"] >= policy["min_profit_factor_for_scale_up"]
        and metrics["max_drawdown_pct"] <= policy["max_drawdown_pct_for_scale_up"]
        and metrics["consecutive_wins"] >= policy["scale_up_after_win_streak"]
        and not blockers
    )
    if blockers:
        decision = "stop" if "loss_streak_cooldown_required" in blockers or "drawdown_requires_reduce_or_stop" in blockers else "reduce"
        scaling_action = "REDUCE_SIZE_OR_STOP_NEW_ENTRIES"
        next_notional = max(5.0, current_notional * (1.0 - policy["scale_down_step_pct"] / 100.0))
        status = "blocked"
    elif can_scale_up:
        decision = "increase"
        scaling_action = "INCREASE_SIZE_BY_CONTROLLED_STEP"
        next_notional = min(policy["max_scaled_notional_usdt"], current_notional * (1.0 + policy["scale_up_step_pct"] / 100.0))
        status = "ok"
    elif warnings:
        decision = "hold"
        scaling_action = "HOLD_SIZE_PROTECT_PROFIT"
        next_notional = current_notional
        status = "review"
    else:
        decision = "hold"
        scaling_action = "HOLD_SIZE_COLLECT_MORE_EVIDENCE"
        next_notional = current_notional
        status = "ok"

    protection_id = "pps_" + sha256(f"{username}|{decision}|{monthly_score}|{metrics}|{now_iso()}".encode("utf-8")).hexdigest()[:20]
    return {
        "status": status,
        "revision": 98,
        "engine": "autonomous_profit_protection_scaling_rules",
        "generated_at": now_iso(),
        "user": username,
        "source_revision": source.get("revision"),
        "source_decision": source.get("decision"),
        "source_autonomy_score": source.get("autonomy_score"),
        "decision": decision,
        "scaling_action": scaling_action,
        "profit_lock_action": profit_lock_action,
        "withdrawal_action": withdrawal_action,
        "monthly_performance_score": monthly_score,
        "current_notional_usdt": round(current_notional, 6),
        "next_notional_usdt": round(next_notional, 6),
        "profit_protection": {
            "profit_reserve_enabled": policy["profit_reserve_enabled"],
            "profit_reserve_pct": policy["profit_reserve_pct"],
            "profit_reserve_usdt": round(profit_reserve_usdt, 6),
            "available_profit_after_reserve_usdt": round(available_profit_after_reserve, 6),
            "daily_profit_lock_trigger_usdt": policy["daily_profit_lock_trigger_usdt"],
            "withdrawal_trigger_usdt": policy["withdrawal_trigger_usdt"],
        },
        "performance_metrics": metrics,
        "size_scaling_rules": {
            "base_notional_usdt": policy["base_notional_usdt"],
            "max_scaled_notional_usdt": policy["max_scaled_notional_usdt"],
            "scale_up_step_pct": policy["scale_up_step_pct"],
            "scale_down_step_pct": policy["scale_down_step_pct"],
            "min_monthly_score_for_scale_up": policy["min_monthly_score_for_scale_up"],
            "min_profit_factor_for_scale_up": policy["min_profit_factor_for_scale_up"],
            "max_drawdown_pct_for_scale_up": policy["max_drawdown_pct_for_scale_up"],
        },
        "anti_overtrade_rules": {
            "enabled": policy["anti_overtrade_enabled"],
            "max_daily_trade_cap": policy["max_daily_trade_cap"],
            "daily_trades": metrics["daily_trades"],
            "cooldown_after_loss_streak": policy["cooldown_after_loss_streak"],
            "scale_up_after_win_streak": policy["scale_up_after_win_streak"],
        },
        "safety_contract": {
            "network_calls_allowed": policy["network_calls_allowed"],
            "direct_order_enabled": policy["direct_order_enabled"],
            "runtime_write_enabled": policy["runtime_write_enabled"],
            "real_submit_enabled": policy["real_submit_enabled"],
            "contains_secret": False,
        },
        "audit_evidence": {
            "protection_id": protection_id,
            "source_loop_id": (source.get("audit_evidence") or {}).get("loop_id") if isinstance(source.get("audit_evidence"), dict) else None,
            "source_revision": source.get("revision"),
            "decision": decision,
            "no_network_call": True,
            "no_order_placement": True,
            "no_runtime_write": True,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": policy,
        "command_preview": {
            "type": "profit_protection_scaling_rules_preview",
            "source_revision": 98,
            "decision": decision,
            "scaling_action": scaling_action,
            "profit_lock_action": profit_lock_action,
            "withdrawal_action": withdrawal_action,
            "protection_id": protection_id,
            "current_notional_usdt": round(current_notional, 6),
            "next_notional_usdt": round(next_notional, 6),
            "read_only": True,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "direct_submit_enabled": False,
            "real_submit_enabled": False,
            "auto_apply_enabled": False,
            "source_command_is_read_only": command.get("read_only") is True,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 98,
        "engine": "autonomous_profit_protection_scaling_rules_summary",
        "generated_at": payload.get("generated_at"),
        "decision": payload.get("decision"),
        "monthly_performance_score": payload.get("monthly_performance_score"),
        "scaling_action": payload.get("scaling_action"),
        "profit_lock_action": payload.get("profit_lock_action"),
        "withdrawal_action": payload.get("withdrawal_action"),
        "current_notional_usdt": payload.get("current_notional_usdt"),
        "next_notional_usdt": payload.get("next_notional_usdt"),
        "profit_reserve_usdt": (payload.get("profit_protection") or {}).get("profit_reserve_usdt") if isinstance(payload.get("profit_protection"), dict) else None,
        "daily_trades": (payload.get("performance_metrics") or {}).get("daily_trades") if isinstance(payload.get("performance_metrics"), dict) else None,
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "read_only": True,
        "dry_run": True,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_profit_protection_scaling_rules(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_profit_protection_scaling_rules(data, settings, auth_store, username))


def build_autonomous_profit_protection_scaling_rules_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    sample = data or {
        "autonomous_fully_autonomous_small_capital_mode": {
            "revision": 97,
            "status": "ok",
            "decision": "start_preview",
            "autonomy_score": 88,
            "small_capital_constraints": {"preview_notional_usdt": 12.0},
            "audit_evidence": {"loop_id": "quality_loop"},
            "command_preview": {"read_only": True, "places_order": False, "sends_exchange_request": False, "writes_runtime_state": False},
        },
        "today_real_pnl_usdt": 2.0,
        "today_real_trade_count": 1,
        "micro_real_performance": {"month_pnl_usdt": 10, "win_rate": 62, "profit_factor": 1.35, "max_drawdown_pct": 2.0, "trade_count": 24, "consecutive_wins": 3},
    }
    payload = build_autonomous_profit_protection_scaling_rules(sample, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_is_98": payload.get("revision") == 98,
        "source_small_capital_chain_present": payload.get("source_revision") == 97,
        "decision_is_controlled": payload.get("decision") in {"increase", "hold", "reduce", "stop"},
        "profit_protection_present": isinstance(payload.get("profit_protection"), dict) and "profit_reserve_usdt" in payload.get("profit_protection", {}),
        "size_scaling_rules_present": isinstance(payload.get("size_scaling_rules"), dict) and "scale_up_step_pct" in payload.get("size_scaling_rules", {}),
        "anti_overtrade_rules_present": isinstance(payload.get("anti_overtrade_rules"), dict) and "max_daily_trade_cap" in payload.get("anti_overtrade_rules", {}),
        "monthly_score_present": isinstance(payload.get("monthly_performance_score"), (int, float)),
        "service_does_not_place_order": command.get("places_order") is False,
        "service_does_not_execute_network_call": command.get("sends_exchange_request") is False,
        "service_does_not_write_runtime": command.get("writes_runtime_state") is False,
        "direct_submit_off": command.get("direct_submit_enabled") is False,
        "real_submit_off": command.get("real_submit_enabled") is False,
        "secret_safe": payload.get("safety_contract", {}).get("contains_secret") is False,
        "summary_revision_is_98": _summary_from_payload(payload).get("revision") == 98,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 98,
        "engine": "autonomous_profit_protection_scaling_rules_quality",
        "generated_at": now_iso(),
        "quality_status": "PROFIT_PROTECTION_SCALING_RULES_OK" if passed else "PROFIT_PROTECTION_SCALING_RULES_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_decision": payload.get("decision"),
        "sample_action": command.get("scaling_action"),
    }
