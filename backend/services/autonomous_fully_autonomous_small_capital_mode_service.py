from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_semi_autonomous_real_trading_lane_service import (
    build_autonomous_semi_autonomous_real_trading_lane,
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


def _safe_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        rows = [str(item).strip().upper() for item in value if str(item).strip()]
        return rows or fallback
    if isinstance(value, str) and value.strip():
        rows = [item.strip().upper() for item in value.split(",") if item.strip()]
        return rows or fallback
    return fallback


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_fully_autonomous_small_capital_mode") if isinstance(settings.get("autonomous_fully_autonomous_small_capital_mode"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 96,
        "auto_scheduler_enabled": _safe_bool(raw.get("auto_scheduler_enabled"), True),
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "direct_order_enabled": _safe_bool(raw.get("direct_order_enabled"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "real_submit_enabled": _safe_bool(raw.get("real_submit_enabled"), False),
        "position_management_preview_enabled": _safe_bool(raw.get("position_management_preview_enabled"), True),
        "exit_management_preview_enabled": _safe_bool(raw.get("exit_management_preview_enabled"), True),
        "daily_halt_enabled": _safe_bool(raw.get("daily_halt_enabled"), True),
        "profit_lock_enabled": _safe_bool(raw.get("profit_lock_enabled"), True),
        "min_real_lane_score": max(1.0, min(100.0, _safe_float(raw.get("min_real_lane_score"), 76.0))),
        "small_capital_usdt": max(10.0, _safe_float(raw.get("small_capital_usdt"), 100.0)),
        "max_active_positions": max(1, _safe_int(raw.get("max_active_positions"), 1)),
        "max_daily_trades": max(1, _safe_int(raw.get("max_daily_trades"), 3)),
        "max_daily_loss_usdt": max(0.1, _safe_float(raw.get("max_daily_loss_usdt"), 2.5)),
        "max_daily_loss_pct": max(0.1, _safe_float(raw.get("max_daily_loss_pct"), 1.0)),
        "profit_lock_trigger_usdt": max(0.1, _safe_float(raw.get("profit_lock_trigger_usdt"), 3.0)),
        "profit_lock_reserve_pct": max(0.0, min(95.0, _safe_float(raw.get("profit_lock_reserve_pct"), 50.0))),
        "symbol_whitelist": _safe_list(raw.get("symbol_whitelist"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
        "strategy_whitelist": _safe_list(raw.get("strategy_whitelist"), ["CHOCH_IMBALANCE", "MICRO_PULLBACK", "TREND_CONTINUATION"]),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_semi_autonomous_real_trading_lane") if isinstance(data.get("autonomous_semi_autonomous_real_trading_lane"), dict) else None
    if raw and raw.get("revision") == 96 and "command_preview" in raw:
        return raw
    return build_autonomous_semi_autonomous_real_trading_lane(data, settings, auth_store, username)


def _market_open(data: dict) -> tuple[bool, str]:
    market_state = str(data.get("market_state") or data.get("market_condition") or data.get("tradeability") or "TRADE").upper()
    if market_state in {"BLOCKED", "DANGER", "CLOSED", "HALT", "NO_TRADE"}:
        return False, market_state
    return True, market_state


def _active_positions(data: dict) -> int:
    positions = data.get("positions") or data.get("real_positions") or []
    if isinstance(positions, list):
        return len([p for p in positions if isinstance(p, dict) and str(p.get("status") or "OPEN").upper() in {"OPEN", "FILLED", "PARTIAL", "ACTIVE"}])
    return _safe_int(data.get("active_position_count"), 0)


def build_autonomous_fully_autonomous_small_capital_mode(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev97 fully autonomous small-capital mode controller.

    The service converts the Rev96 real-lane preview into an operator-light small
    capital control loop. It remains preview-only in this revision: no exchange
    request, no order placement and no runtime write are performed.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    constraints = source.get("real_lane_constraints") if isinstance(source.get("real_lane_constraints"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("fully_autonomous_small_capital_mode_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_real_lane_revision_mismatch")
    if source.get("status") != "ok" or source.get("readiness_decision") != "ready_preview":
        blockers.append("source_real_lane_not_ready")
    if command.get("approved_for_fully_autonomous_small_capital_mode_review") is not True:
        blockers.append("source_not_approved_for_small_capital_review")
    if _safe_float(source.get("readiness_score"), 0.0) < policy["min_real_lane_score"]:
        blockers.append("real_lane_score_below_small_capital_minimum")

    if policy["network_calls_allowed"]:
        blockers.append("network_calls_must_remain_disabled_for_rev97")
    if policy["direct_order_enabled"]:
        blockers.append("direct_order_must_remain_disabled_for_rev97")
    if policy["runtime_write_enabled"]:
        blockers.append("runtime_write_must_remain_disabled_for_rev97")
    if policy["real_submit_enabled"]:
        blockers.append("real_submit_must_remain_disabled_for_rev97")

    symbol = str(source.get("symbol") or data.get("primary_symbol") or "BTCUSDT").upper()
    strategy = str(source.get("strategy") or data.get("primary_strategy") or "CHOCH_IMBALANCE").upper()
    if symbol not in policy["symbol_whitelist"]:
        blockers.append("symbol_not_in_small_capital_whitelist")
    if strategy not in policy["strategy_whitelist"]:
        blockers.append("strategy_not_in_small_capital_whitelist")

    market_ok, market_state = _market_open(data)
    if not market_ok:
        blockers.append("market_not_tradeable_for_small_capital_mode")

    active_positions = _active_positions(data)
    daily_trades = _safe_int(data.get("today_real_trade_count", data.get("daily_real_trade_count")), 0)
    daily_pnl_usdt = _safe_float(data.get("today_real_pnl_usdt", data.get("today_pnl_usdt")), 0.0)
    daily_pnl_pct = _safe_float(data.get("today_real_pnl_pct", data.get("today_pnl_pct")), 0.0)
    daily_loss_usdt = abs(min(0.0, daily_pnl_usdt))
    daily_loss_pct = abs(min(0.0, daily_pnl_pct))
    if active_positions >= policy["max_active_positions"]:
        warnings.append("max_active_positions_reached_manage_existing_first")
    if daily_trades >= policy["max_daily_trades"]:
        blockers.append("daily_small_capital_trade_cap_reached")
    if policy["daily_halt_enabled"] and daily_loss_usdt >= policy["max_daily_loss_usdt"]:
        blockers.append("daily_loss_usdt_halt")
    if policy["daily_halt_enabled"] and daily_loss_pct >= policy["max_daily_loss_pct"]:
        blockers.append("daily_loss_pct_halt")

    preview_notional = min(
        policy["small_capital_usdt"],
        max(0.0, _safe_float(constraints.get("preview_notional_usdt"), _safe_float(source.get("preview_notional_usdt"), 0.0))),
    )
    if preview_notional <= 0:
        blockers.append("preview_notional_missing")

    if policy["profit_lock_enabled"] and daily_pnl_usdt >= policy["profit_lock_trigger_usdt"]:
        profit_lock_action = "LOCK_PROFIT_AND_REDUCE_NEW_ENTRIES"
        warnings.append("profit_lock_triggered")
    else:
        profit_lock_action = "NO_PROFIT_LOCK"

    if blockers:
        mode_state = "FULLY_AUTONOMOUS_SMALL_CAPITAL_BLOCKED"
        decision = "stop"
        next_action = "HALT_AUTONOMOUS_ENTRIES_REVIEW_BLOCKERS"
        status = "blocked"
    elif warnings:
        mode_state = "FULLY_AUTONOMOUS_SMALL_CAPITAL_REVIEW"
        decision = "hold"
        next_action = "MANAGE_EXISTING_OR_REVIEW_LIMITS"
        status = "review"
    else:
        mode_state = "FULLY_AUTONOMOUS_SMALL_CAPITAL_READY_PREVIEW"
        decision = "start_preview"
        next_action = "ALLOW_OPERATOR_FREE_PREVIEW_LOOP"
        status = "ok"

    score = 52.0
    score += min(22.0, max(0.0, _safe_float(source.get("readiness_score"), 0.0) - 70.0) * 0.75)
    score += 7.0 if market_ok else -12.0
    score += 6.0 if active_positions < policy["max_active_positions"] else -4.0
    score += 6.0 if daily_trades < policy["max_daily_trades"] else -10.0
    score += 5.0 if daily_pnl_usdt >= 0 else -5.0
    score -= len(set(blockers)) * 8.0 + len(set(warnings)) * 3.0
    autonomy_score = max(0.0, min(100.0, score))

    loop_id = "fascm_" + sha256(f"rev97:{username}:{source.get('audit_evidence', {}).get('audit_id')}:{symbol}:{strategy}:{preview_notional}".encode("utf-8")).hexdigest()[:24]

    loop_plan = {
        "loop_id": loop_id,
        "scheduler_action": "START_LOOP_PREVIEW" if decision == "start_preview" else ("HOLD_LOOP_PREVIEW" if decision == "hold" else "STOP_LOOP_PREVIEW"),
        "auto_start_allowed": decision == "start_preview" and policy["auto_scheduler_enabled"],
        "auto_stop_allowed": True,
        "opportunity_routing": "ROUTE_BEST_VALIDATED_SIGNAL" if decision == "start_preview" else "NO_NEW_ROUTE",
        "execution_submit": "PREVIEW_ONLY_NO_SUBMIT",
        "position_management": "PREVIEW_EXISTING_POSITIONS" if policy["position_management_preview_enabled"] else "DISABLED",
        "exit_management": "PREVIEW_EXIT_PLANS" if policy["exit_management_preview_enabled"] else "DISABLED",
        "daily_halt": "ARMED" if policy["daily_halt_enabled"] else "DISABLED",
        "profit_lock": profit_lock_action,
    }

    return {
        "status": status,
        "revision": 97,
        "engine": "autonomous_fully_autonomous_small_capital_mode",
        "generated_at": now_iso(),
        "read_only": True,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "direct_submit_enabled": False,
        "real_submit_enabled": False,
        "mode_state": mode_state,
        "decision": decision,
        "autonomy_score": round(autonomy_score, 2),
        "next_action": next_action,
        "source_revision": source.get("revision"),
        "source_readiness_decision": source.get("readiness_decision"),
        "source_readiness_score": source.get("readiness_score"),
        "symbol": symbol,
        "strategy": strategy,
        "market_state": market_state,
        "small_capital_constraints": {
            "small_capital_usdt": policy["small_capital_usdt"],
            "preview_notional_usdt": round(preview_notional, 6),
            "max_active_positions": policy["max_active_positions"],
            "active_positions": active_positions,
            "max_daily_trades": policy["max_daily_trades"],
            "daily_trades": daily_trades,
            "daily_pnl_usdt": round(daily_pnl_usdt, 6),
            "daily_pnl_pct": round(daily_pnl_pct, 4),
            "max_daily_loss_usdt": policy["max_daily_loss_usdt"],
            "max_daily_loss_pct": policy["max_daily_loss_pct"],
            "profit_lock_trigger_usdt": policy["profit_lock_trigger_usdt"],
            "profit_lock_reserve_pct": policy["profit_lock_reserve_pct"],
            "symbol_whitelist": policy["symbol_whitelist"],
            "strategy_whitelist": policy["strategy_whitelist"],
        },
        "autonomous_loop_plan": loop_plan,
        "safety_contract": {
            "network_calls_allowed": policy["network_calls_allowed"],
            "direct_order_enabled": policy["direct_order_enabled"],
            "runtime_write_enabled": policy["runtime_write_enabled"],
            "real_submit_enabled": policy["real_submit_enabled"],
            "contains_secret": False,
        },
        "audit_evidence": {
            "loop_id": loop_id,
            "source_audit_id": (source.get("audit_evidence") or {}).get("audit_id") if isinstance(source.get("audit_evidence"), dict) else None,
            "source_revision": source.get("revision"),
            "source_state": source.get("lane_state"),
            "decision": decision,
            "no_network_call": True,
            "no_order_placement": True,
            "no_runtime_write": True,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": policy,
        "command_preview": {
            "type": "fully_autonomous_small_capital_mode_preview",
            "source_revision": 97,
            "decision": decision,
            "mode_state": mode_state,
            "next_action": next_action,
            "loop_id": loop_id,
            "symbol": symbol,
            "strategy": strategy,
            "preview_notional_usdt": round(preview_notional, 6),
            "read_only": True,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "direct_submit_enabled": False,
            "real_submit_enabled": False,
            "auto_apply_enabled": False,
            "operator_free_preview": decision == "start_preview" and status == "ok",
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    constraints = payload.get("small_capital_constraints") if isinstance(payload.get("small_capital_constraints"), dict) else {}
    loop = payload.get("autonomous_loop_plan") if isinstance(payload.get("autonomous_loop_plan"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 97,
        "engine": "autonomous_fully_autonomous_small_capital_mode_summary",
        "generated_at": payload.get("generated_at"),
        "mode_state": payload.get("mode_state"),
        "decision": payload.get("decision"),
        "autonomy_score": payload.get("autonomy_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "strategy": payload.get("strategy"),
        "market_state": payload.get("market_state"),
        "preview_notional_usdt": constraints.get("preview_notional_usdt"),
        "daily_trades": constraints.get("daily_trades"),
        "max_daily_trades": constraints.get("max_daily_trades"),
        "daily_pnl_usdt": constraints.get("daily_pnl_usdt"),
        "active_positions": constraints.get("active_positions"),
        "profit_lock": loop.get("profit_lock"),
        "loop_scheduler_action": loop.get("scheduler_action"),
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "read_only": True,
        "dry_run": True,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_fully_autonomous_small_capital_mode(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_fully_autonomous_small_capital_mode(data, settings, auth_store, username))


def build_autonomous_fully_autonomous_small_capital_mode_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_fully_autonomous_small_capital_mode(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_is_97": payload.get("revision") == 97,
        "source_real_lane_chain_present": payload.get("source_revision") == 96,
        "decision_is_controlled": payload.get("decision") in {"start_preview", "hold", "stop"},
        "small_capital_constraints_present": isinstance(payload.get("small_capital_constraints"), dict) and "max_daily_trades" in payload.get("small_capital_constraints", {}),
        "autonomous_loop_plan_present": isinstance(payload.get("autonomous_loop_plan"), dict) and "scheduler_action" in payload.get("autonomous_loop_plan", {}),
        "service_does_not_place_order": payload.get("places_order") is False and command.get("places_order") is False,
        "service_does_not_execute_network_call": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False,
        "service_does_not_write_runtime": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "direct_submit_off": payload.get("direct_submit_enabled") is False and command.get("direct_submit_enabled") is False,
        "real_submit_off": payload.get("real_submit_enabled") is False and command.get("real_submit_enabled") is False,
        "secret_safe": payload.get("safety_contract", {}).get("contains_secret") is False,
        "summary_revision_is_97": _summary_from_payload(payload).get("revision") == 97,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 97,
        "engine": "autonomous_fully_autonomous_small_capital_mode_quality",
        "generated_at": now_iso(),
        "quality_status": "FULLY_AUTONOMOUS_SMALL_CAPITAL_MODE_OK" if passed else "FULLY_AUTONOMOUS_SMALL_CAPITAL_MODE_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_state": payload.get("mode_state"),
        "sample_action": command.get("next_action"),
    }
