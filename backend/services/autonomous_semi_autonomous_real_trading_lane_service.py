from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_promotion_demotion_controller_service import (
    build_autonomous_micro_real_promotion_demotion_controller,
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
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled", "allow"}
    if value is None:
        return fallback
    return bool(value)


def _safe_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        rows = [str(item).strip().upper() for item in value if str(item).strip()]
        return rows or fallback
    if isinstance(value, str) and value.strip():
        return [item.strip().upper() for item in value.split(",") if item.strip()] or fallback
    return fallback


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_semi_autonomous_real_trading_lane") if isinstance(settings.get("autonomous_semi_autonomous_real_trading_lane"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 95,
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "direct_order_enabled": _safe_bool(raw.get("direct_order_enabled"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "real_submit_enabled": _safe_bool(raw.get("real_submit_enabled"), False),
        "manual_override_required": _safe_bool(raw.get("manual_override_required"), True),
        "session_lock_required": _safe_bool(raw.get("session_lock_required"), True),
        "audit_evidence_required": _safe_bool(raw.get("audit_evidence_required"), True),
        "min_controller_score": max(1.0, min(100.0, _safe_float(raw.get("min_controller_score"), 72.0))),
        "max_real_notional_usdt": max(1.0, _safe_float(raw.get("max_real_notional_usdt"), 15.0)),
        "daily_trade_cap": max(1, _safe_int(raw.get("daily_trade_cap"), 3)),
        "max_daily_loss_usdt": max(0.1, _safe_float(raw.get("max_daily_loss_usdt"), 3.0)),
        "max_daily_loss_pct": max(0.1, _safe_float(raw.get("max_daily_loss_pct"), 1.0)),
        "symbol_whitelist": _safe_list(raw.get("symbol_whitelist"), ["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
        "strategy_whitelist": _safe_list(raw.get("strategy_whitelist"), ["CHOCH_IMBALANCE", "MICRO_PULLBACK", "TREND_CONTINUATION"]),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_promotion_demotion_controller") if isinstance(data.get("autonomous_micro_real_promotion_demotion_controller"), dict) else None
    if raw and raw.get("revision") == 95 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_promotion_demotion_controller(data, settings, auth_store, username)


def _operator_override(data: dict) -> dict:
    for key in ("semi_autonomous_real_lane_override", "real_lane_manual_override", "manual_override"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _session_lock(data: dict) -> dict:
    for key in ("real_lane_session_lock", "session_lock", "trading_session"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _symbol_strategy(data: dict, source: dict) -> tuple[str, str]:
    for symbol_key in ("primary_symbol", "selected_symbol", "symbol"):
        if data.get(symbol_key):
            symbol = str(data.get(symbol_key)).upper()
            break
    else:
        symbol = str(source.get("primary_symbol") or source.get("symbol") or "BTCUSDT").upper()
    for strategy_key in ("primary_strategy", "selected_strategy", "strategy"):
        if data.get(strategy_key):
            strategy = str(data.get(strategy_key)).upper()
            break
    else:
        strategy = str(source.get("primary_strategy") or source.get("strategy") or "CHOCH_IMBALANCE").upper()
    return symbol, strategy


def build_autonomous_semi_autonomous_real_trading_lane(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev96 semi-autonomous real trading lane readiness layer.

    This layer prepares a real-trading lane contract after successful micro-real
    promotion signals. It is preview-only: it never places orders, never calls an
    exchange and never writes runtime state by default.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    scale = source.get("micro_real_scale_decision") if isinstance(source.get("micro_real_scale_decision"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("semi_autonomous_real_lane_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_promotion_demotion_revision_mismatch")
    if source.get("status") != "ok":
        blockers.append("source_controller_not_ok")
    if source.get("decision") != "increase":
        blockers.append("source_decision_not_increase")
    if command.get("approved_for_semi_autonomous_real_lane_review") is not True:
        blockers.append("source_not_approved_for_real_lane_review")
    if _safe_float(source.get("controller_score"), 0.0) < policy["min_controller_score"]:
        blockers.append("controller_score_below_real_lane_minimum")

    if policy["network_calls_allowed"]:
        blockers.append("network_calls_must_remain_disabled_for_rev96")
    if policy["direct_order_enabled"]:
        blockers.append("direct_order_must_remain_disabled_for_rev96")
    if policy["runtime_write_enabled"]:
        blockers.append("runtime_write_must_remain_disabled_for_rev96")
    if policy["real_submit_enabled"]:
        blockers.append("real_submit_must_remain_disabled_for_rev96")

    symbol, strategy = _symbol_strategy(data, source)
    if symbol not in policy["symbol_whitelist"]:
        blockers.append("symbol_not_in_real_lane_whitelist")
    if strategy not in policy["strategy_whitelist"]:
        blockers.append("strategy_not_in_real_lane_whitelist")

    target_notional = _safe_float(scale.get("target_notional_usdt"), 0.0)
    real_preview_notional = min(policy["max_real_notional_usdt"], max(0.0, target_notional))
    if target_notional <= 0:
        blockers.append("target_notional_missing")
    if target_notional > policy["max_real_notional_usdt"]:
        warnings.append("target_notional_capped_for_real_lane_preview")

    daily_trade_count = _safe_int(data.get("today_real_trade_count", data.get("daily_real_trade_count")), 0)
    daily_loss_usdt = abs(min(0.0, _safe_float(data.get("today_real_pnl_usdt", data.get("today_pnl_usdt")), 0.0)))
    daily_loss_pct = abs(min(0.0, _safe_float(data.get("today_real_pnl_pct", data.get("today_pnl_pct")), 0.0)))
    if daily_trade_count >= policy["daily_trade_cap"]:
        blockers.append("daily_real_trade_cap_reached")
    if daily_loss_usdt >= policy["max_daily_loss_usdt"]:
        blockers.append("daily_loss_usdt_hard_stop")
    if daily_loss_pct >= policy["max_daily_loss_pct"]:
        blockers.append("daily_loss_pct_hard_stop")

    session = _session_lock(data)
    session_locked = _safe_bool(session.get("locked"), False) or str(session.get("state", "")).upper() in {"LOCKED", "ACTIVE_LOCK"}
    if policy["session_lock_required"] and not session_locked:
        blockers.append("session_lock_required_for_real_lane")

    override = _operator_override(data)
    manual_override = _safe_bool(override.get("approved"), False) and str(override.get("scope", "")).lower() in {"real_lane", "semi_autonomous_real_lane", "rev96"}
    if policy["manual_override_required"] and not manual_override:
        blockers.append("manual_override_required_for_real_lane")

    audit_seed = f"rev96:{username}:{source.get('controller_id')}:{symbol}:{strategy}:{real_preview_notional}"
    audit_id = "sarlt_" + sha256(audit_seed.encode("utf-8")).hexdigest()[:24]
    audit_evidence = {
        "audit_id": audit_id,
        "source_revision": source.get("revision"),
        "source_controller_id": source.get("controller_id"),
        "source_decision": source.get("decision"),
        "source_controller_score": source.get("controller_score"),
        "symbol": symbol,
        "strategy": strategy,
        "session_locked": session_locked,
        "manual_override_present": manual_override,
        "daily_trade_count": daily_trade_count,
        "daily_loss_usdt": round(daily_loss_usdt, 6),
        "daily_loss_pct": round(daily_loss_pct, 4),
        "no_network_call": True,
        "no_order_placement": True,
        "no_runtime_write": True,
    }
    if policy["audit_evidence_required"] and not audit_evidence.get("audit_id"):
        blockers.append("audit_evidence_missing")

    if blockers:
        status = "blocked"
        readiness_decision = "blocked"
        lane_state = "SEMI_AUTONOMOUS_REAL_LANE_BLOCKED"
        next_action = "KEEP_MICRO_REAL_OR_REVIEW_BLOCKERS"
    elif warnings:
        status = "review"
        readiness_decision = "review"
        lane_state = "SEMI_AUTONOMOUS_REAL_LANE_REVIEW"
        next_action = "REVIEW_REAL_LANE_CONSTRAINTS"
    else:
        status = "ok"
        readiness_decision = "ready_preview"
        lane_state = "SEMI_AUTONOMOUS_REAL_LANE_READY_PREVIEW"
        next_action = "ALLOW_SEMI_AUTONOMOUS_REAL_LANE_PREVIEW"

    score = 55.0
    score += min(20.0, max(0.0, _safe_float(source.get("controller_score"), 0.0) - 70.0) * 0.8)
    score += 7.0 if session_locked else -12.0
    score += 7.0 if manual_override else -12.0
    score += 5.0 if symbol in policy["symbol_whitelist"] else -10.0
    score += 5.0 if strategy in policy["strategy_whitelist"] else -10.0
    score -= len(set(blockers)) * 8.0 + len(set(warnings)) * 3.0
    readiness_score = max(0.0, min(100.0, score))

    return {
        "status": status,
        "revision": 96,
        "engine": "autonomous_semi_autonomous_real_trading_lane",
        "generated_at": now_iso(),
        "read_only": True,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "direct_submit_enabled": False,
        "real_submit_enabled": False,
        "lane_state": lane_state,
        "readiness_decision": readiness_decision,
        "readiness_score": round(readiness_score, 2),
        "next_action": next_action,
        "source_revision": source.get("revision"),
        "source_controller_id": source.get("controller_id"),
        "source_decision": source.get("decision"),
        "symbol": symbol,
        "strategy": strategy,
        "real_lane_constraints": {
            "preview_notional_usdt": round(real_preview_notional, 6),
            "requested_notional_usdt": round(target_notional, 6),
            "max_real_notional_usdt": policy["max_real_notional_usdt"],
            "daily_trade_cap": policy["daily_trade_cap"],
            "daily_trade_count": daily_trade_count,
            "max_daily_loss_usdt": policy["max_daily_loss_usdt"],
            "max_daily_loss_pct": policy["max_daily_loss_pct"],
            "symbol_whitelist": policy["symbol_whitelist"],
            "strategy_whitelist": policy["strategy_whitelist"],
            "session_lock_required": policy["session_lock_required"],
            "session_locked": session_locked,
            "manual_override_required": policy["manual_override_required"],
            "manual_override_present": manual_override,
            "audit_evidence_required": policy["audit_evidence_required"],
        },
        "safety_contract": {
            "network_calls_allowed": policy["network_calls_allowed"],
            "direct_order_enabled": policy["direct_order_enabled"],
            "runtime_write_enabled": policy["runtime_write_enabled"],
            "real_submit_enabled": policy["real_submit_enabled"],
            "contains_secret": False,
        },
        "audit_evidence": audit_evidence,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": policy,
        "command_preview": {
            "type": "semi_autonomous_real_trading_lane_preview",
            "source_revision": 96,
            "lane": "SEMI_AUTONOMOUS_REAL_TRADING_LANE",
            "lane_state": lane_state,
            "readiness_decision": readiness_decision,
            "next_action": next_action,
            "symbol": symbol,
            "strategy": strategy,
            "preview_notional_usdt": round(real_preview_notional, 6),
            "read_only": True,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "direct_submit_enabled": False,
            "real_submit_enabled": False,
            "approved_for_fully_autonomous_small_capital_mode_review": readiness_decision == "ready_preview" and status == "ok" and not blockers,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    constraints = payload.get("real_lane_constraints") if isinstance(payload.get("real_lane_constraints"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 96,
        "engine": "autonomous_semi_autonomous_real_trading_lane_summary",
        "generated_at": payload.get("generated_at"),
        "lane_state": payload.get("lane_state"),
        "readiness_decision": payload.get("readiness_decision"),
        "readiness_score": payload.get("readiness_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "strategy": payload.get("strategy"),
        "preview_notional_usdt": constraints.get("preview_notional_usdt"),
        "daily_trade_cap": constraints.get("daily_trade_cap"),
        "daily_trade_count": constraints.get("daily_trade_count"),
        "session_locked": constraints.get("session_locked"),
        "manual_override_present": constraints.get("manual_override_present"),
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "read_only": True,
        "dry_run": True,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_semi_autonomous_real_trading_lane(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_semi_autonomous_real_trading_lane(data, settings, auth_store, username))


def build_autonomous_semi_autonomous_real_trading_lane_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_semi_autonomous_real_trading_lane(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_is_96": payload.get("revision") == 96,
        "source_promotion_demotion_chain_present": payload.get("source_revision") == 95,
        "readiness_decision_is_controlled": payload.get("readiness_decision") in {"ready_preview", "review", "blocked"},
        "real_lane_constraints_present": isinstance(payload.get("real_lane_constraints"), dict) and "daily_trade_cap" in payload.get("real_lane_constraints", {}),
        "audit_evidence_present": isinstance(payload.get("audit_evidence"), dict) and bool(payload.get("audit_evidence", {}).get("audit_id")),
        "service_does_not_place_order": payload.get("places_order") is False and command.get("places_order") is False,
        "service_does_not_execute_network_call": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False,
        "service_does_not_write_runtime": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "direct_submit_off": payload.get("direct_submit_enabled") is False and command.get("direct_submit_enabled") is False,
        "real_submit_off": payload.get("real_submit_enabled") is False and command.get("real_submit_enabled") is False,
        "secret_safe": payload.get("safety_contract", {}).get("contains_secret") is False,
        "summary_revision_is_96": _summary_from_payload(payload).get("revision") == 96,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 96,
        "engine": "autonomous_semi_autonomous_real_trading_lane_quality",
        "generated_at": now_iso(),
        "quality_status": "SEMI_AUTONOMOUS_REAL_TRADING_LANE_OK" if passed else "SEMI_AUTONOMOUS_REAL_TRADING_LANE_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_state": payload.get("lane_state"),
        "sample_action": command.get("next_action"),
    }
