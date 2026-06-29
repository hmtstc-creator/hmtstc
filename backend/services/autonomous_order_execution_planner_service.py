from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_trade_intent_builder_service import build_autonomous_trade_intent_builder


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_order_execution_planner") if isinstance(settings.get("autonomous_order_execution_planner"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_planner_score": _clamp(_safe_float(raw.get("min_planner_score"), 72.0), 1.0, 100.0),
        "max_market_order_usdt": max(1.0, _safe_float(raw.get("max_market_order_usdt"), 25.0)),
        "min_order_usdt": max(1.0, _safe_float(raw.get("min_order_usdt"), 5.0)),
        "allow_real_preview": _safe_bool(raw.get("allow_real_preview"), False),
        "require_idempotency_key": True,
        "read_only": True,
        "auto_apply": False,
    }


def _api_connection(auth_store: dict, username: str) -> dict:
    users = auth_store.get("users") if isinstance(auth_store.get("users"), dict) else {}
    user = users.get(username) if isinstance(users.get(username), dict) else {}
    api = user.get("api_connection") if isinstance(user.get("api_connection"), dict) else {}
    return {
        "can_read": _safe_bool(api.get("can_read"), False),
        "can_trade": _safe_bool(api.get("can_trade"), False),
        "has_api_key": bool(api.get("api_key")),
        "has_secret_ref": bool(api.get("secret_ref")),
    }


def _intent(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_trade_intent_builder") if isinstance(data.get("autonomous_trade_intent_builder"), dict) else None
    return raw or build_autonomous_trade_intent_builder(data, settings, auth_store, username)


def _exchange_payload(intent: dict) -> dict:
    trade = intent.get("trade_intent") if isinstance(intent.get("trade_intent"), dict) else {}
    return {
        "symbol": trade.get("symbol"),
        "side": trade.get("side") or "LONG",
        "order_type": trade.get("order_type") or "MARKET_PREVIEW",
        "time_in_force": trade.get("time_in_force") or "IOC_PREVIEW",
        "notional_usdt": _safe_float(trade.get("notional_usdt"), 0.0),
        "reduce_only": bool(trade.get("reduce_only", False)),
        "stop_loss_pct": _safe_float(trade.get("stop_loss_pct"), 0.0),
        "take_profit_pct": _safe_float(trade.get("take_profit_pct"), 0.0),
        "trailing_pct": _safe_float(trade.get("trailing_pct"), 0.0),
    }


def _score(intent: dict, exchange_payload: dict, api: dict, policy: dict, blockers: list[str], warnings: list[str]) -> float:
    score = _safe_float(intent.get("intent_score"), 0.0) * 0.78
    notional = _safe_float(exchange_payload.get("notional_usdt"), 0.0)
    if notional >= policy["min_order_usdt"]:
        score += 8.0
    else:
        blockers.append("order_notional_below_minimum")
    if notional <= policy["max_market_order_usdt"]:
        score += 6.0
    else:
        blockers.append("order_notional_above_market_limit")
    if exchange_payload.get("symbol"):
        score += 4.0
    else:
        blockers.append("missing_symbol")
    if api["has_api_key"] and api["has_secret_ref"]:
        score += 4.0
    else:
        warnings.append("api_connection_incomplete_for_real_lane")
    if api["can_trade"]:
        score += 4.0
    else:
        warnings.append("trade_permission_not_enabled")
    if blockers:
        score -= min(50.0, len(blockers) * 18.0)
    if warnings:
        score -= min(12.0, len(warnings) * 3.0)
    return round(_clamp(score), 2)


def build_autonomous_order_execution_planner(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev79 read-only order execution planner.

    Converts a Rev78 trade intent into an exchange-safe execution plan preview.
    It prepares an idempotent command envelope and lane-specific preflight checks,
    but it never sends an order, never writes runtime state and never returns secrets.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    intent = _intent(data, settings, auth_store, username)
    trade = intent.get("trade_intent") if isinstance(intent.get("trade_intent"), dict) else {}
    api = _api_connection(auth_store, username)
    blockers = list(intent.get("blockers") or [])
    warnings = list(intent.get("warnings") or [])

    if not policy["enabled"]:
        blockers.append("order_execution_planner_disabled")
    if intent.get("intent_state") != "READY":
        blockers.append("trade_intent_not_ready")

    lane = str(trade.get("lane") or "WATCH").upper()
    if lane == "REAL_PREVIEW" and not policy["allow_real_preview"]:
        blockers.append("real_preview_disabled_by_policy")
    if lane in {"REAL_PREVIEW", "MICRO_REAL_PREVIEW"} and not api["can_trade"]:
        blockers.append("trade_permission_required_for_real_lane")
    if lane == "WATCH":
        blockers.append("watch_lane_has_no_executable_plan")

    exchange_payload = _exchange_payload(intent)
    planner_score = _score(intent, exchange_payload, api, policy, blockers, warnings)
    symbol = exchange_payload.get("symbol") or "NONE"
    generated_at = now_iso()
    idempotency_key = f"PLAN-{generated_at}-{symbol}-{lane}"

    if blockers:
        planner_state = "BLOCKED"
        planner_action = "NO_ORDER_PLAN"
    elif planner_score >= policy["min_planner_score"]:
        planner_state = "READY"
        planner_action = f"PREPARE_{lane}_ORDER_PREVIEW"
    else:
        planner_state = "REVIEW"
        planner_action = "REVIEW_ORDER_PLAN"

    order_plan = {
        "plan_id": idempotency_key,
        "source_intent_id": trade.get("intent_id"),
        "lane": lane,
        "symbol": exchange_payload.get("symbol"),
        "strategy": trade.get("strategy"),
        "exchange_payload_preview": exchange_payload,
        "preflight": {
            "idempotency_key": idempotency_key,
            "requires_api_readiness": lane in {"REAL_PREVIEW", "MICRO_REAL_PREVIEW"},
            "api_connection_ready": api["has_api_key"] and api["has_secret_ref"],
            "trade_permission_ready": api["can_trade"],
            "min_order_usdt": policy["min_order_usdt"],
            "max_market_order_usdt": policy["max_market_order_usdt"],
        },
    }

    return {
        "status": "ok" if planner_state == "READY" else ("blocked" if planner_state == "BLOCKED" else "review"),
        "revision": 79,
        "engine": "autonomous_order_execution_planner",
        "generated_at": generated_at,
        "read_only": True,
        "auto_apply": False,
        "planner_state": planner_state,
        "planner_action": planner_action,
        "planner_score": planner_score,
        "order_plan": order_plan,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "inputs": {
            "trade_intent_revision": intent.get("revision"),
            "intent_state": intent.get("intent_state"),
            "intent_action": intent.get("intent_action"),
            "intent_score": intent.get("intent_score"),
            "api_connection": api,
        },
        "policy": policy,
        "command_preview": {
            "type": "order_execution_plan_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "writes_runtime_state": False,
            "sends_exchange_request": False,
            "requires_trade_intent": True,
            "requires_idempotency_key": True,
            "source_revision": 79,
            "planner_state": planner_state,
            "planner_action": planner_action,
            "lane": lane,
            "symbol": exchange_payload.get("symbol"),
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    plan = payload.get("order_plan") if isinstance(payload.get("order_plan"), dict) else {}
    preflight = plan.get("preflight") if isinstance(plan.get("preflight"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 79,
        "engine": "autonomous_order_execution_planner_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "planner_state": payload.get("planner_state"),
        "planner_action": payload.get("planner_action"),
        "planner_score": payload.get("planner_score"),
        "lane": plan.get("lane"),
        "symbol": plan.get("symbol"),
        "api_connection_ready": preflight.get("api_connection_ready"),
        "trade_permission_ready": preflight.get("trade_permission_ready"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_order_execution_planner(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_order_execution_planner(data, settings, auth_store, username))


def build_autonomous_order_execution_planner_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_order_execution_planner(data, settings, auth_store, username)
    summary = _summary_from_payload(payload)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    plan = payload.get("order_plan") if isinstance(payload.get("order_plan"), dict) else {}
    preflight = plan.get("preflight") if isinstance(plan.get("preflight"), dict) else {}
    exchange_payload = plan.get("exchange_payload_preview") if isinstance(plan.get("exchange_payload_preview"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    checks = {
        "revision_79": payload.get("revision") == 79 and summary.get("revision") == 79,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False and command.get("sends_exchange_request") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "idempotency_key_visible": bool(preflight.get("idempotency_key")),
        "exchange_payload_contract": {"symbol", "side", "order_type", "notional_usdt", "stop_loss_pct", "take_profit_pct"}.issubset(exchange_payload.keys()),
        "source_chain_visible": {"trade_intent_revision", "intent_state", "intent_action", "api_connection"}.issubset(inputs.keys()),
        "summary_minimal": {"planner_state", "planner_action", "attention_required"}.issubset(summary.keys()),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "secret_key" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 79,
        "engine": "autonomous_order_execution_planner_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "planner_state": payload.get("planner_state"),
        "planner_action": payload.get("planner_action"),
        "planner_score": payload.get("planner_score"),
    }
