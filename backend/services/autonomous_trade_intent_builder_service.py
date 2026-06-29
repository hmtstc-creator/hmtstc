from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_signal_validator_service import build_autonomous_signal_validator


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
    raw = settings.get("autonomous_trade_intent_builder") if isinstance(settings.get("autonomous_trade_intent_builder"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_intent_score": _clamp(_safe_float(raw.get("min_intent_score"), 70.0), 1.0, 100.0),
        "min_validation_score": _clamp(_safe_float(raw.get("min_validation_score"), 64.0), 1.0, 100.0),
        "max_notional_usdt": max(1.0, _safe_float(raw.get("max_notional_usdt"), 25.0)),
        "min_notional_usdt": max(1.0, _safe_float(raw.get("min_notional_usdt"), 5.0)),
        "default_stop_loss_pct": max(0.05, min(8.0, _safe_float(raw.get("default_stop_loss_pct"), 0.65))),
        "default_take_profit_pct": max(0.05, min(12.0, _safe_float(raw.get("default_take_profit_pct"), 0.95))),
        "default_trailing_pct": max(0.0, min(8.0, _safe_float(raw.get("default_trailing_pct"), 0.35))),
        "paper_first": _safe_bool(raw.get("paper_first"), True),
        "read_only": True,
        "auto_apply": False,
    }


def _wallet(data: dict) -> dict:
    wallet = data.get("wallet") if isinstance(data.get("wallet"), dict) else {}
    total = _safe_float(wallet.get("total_usdt") or data.get("total_usdt"), 0.0)
    free = _safe_float(wallet.get("free_usdt") or data.get("free_usdt"), total)
    return {"total_usdt": max(0.0, total), "free_usdt": max(0.0, free)}


def _risk_budget(data: dict, policy: dict) -> dict:
    risk = data.get("risk_brain") if isinstance(data.get("risk_brain"), dict) else {}
    allocator = data.get("autonomous_capital_allocator") if isinstance(data.get("autonomous_capital_allocator"), dict) else {}
    suggested = _safe_float(risk.get("suggested_order_usdt") or allocator.get("suggested_order_usdt"), 0.0)
    max_symbol = _safe_float(allocator.get("max_symbol_notional_usdt"), 0.0)
    wallet = _wallet(data)
    fallback = min(policy["max_notional_usdt"], max(policy["min_notional_usdt"], wallet["free_usdt"] * 0.02 if wallet["free_usdt"] else policy["min_notional_usdt"]))
    notional = suggested if suggested > 0 else fallback
    if max_symbol > 0:
        notional = min(notional, max_symbol)
    notional = min(notional, policy["max_notional_usdt"], wallet["free_usdt"])
    return {
        "suggested_notional_usdt": round(max(0.0, notional), 2),
        "min_notional_usdt": policy["min_notional_usdt"],
        "max_notional_usdt": policy["max_notional_usdt"],
        "free_usdt": wallet["free_usdt"],
    }


def _lane_from_signal(signal: dict, policy: dict) -> str:
    decision = str(signal.get("validation_decision") or "WAIT").upper()
    route_action = str(signal.get("route_action") or "WAIT").upper()
    if policy["paper_first"]:
        return "PAPER"
    if decision == "APPROVE_EXECUTION_PREVIEW" and route_action == "REAL_ROUTE":
        return "REAL_PREVIEW"
    if decision == "APPROVE_EXECUTION_PREVIEW":
        return "MICRO_REAL_PREVIEW"
    if decision in {"APPROVE_PAPER_PREVIEW", "PAPER_ONLY_REVIEW"}:
        return "PAPER"
    return "WATCH"


def _intent_score(signal: dict, budget: dict, policy: dict, blockers: list[str], warnings: list[str]) -> float:
    validation_score = _safe_float(signal.get("validation_score"), 0.0)
    score = validation_score * 0.74
    if budget["suggested_notional_usdt"] >= policy["min_notional_usdt"]:
        score += 12.0
    else:
        blockers.append("notional_below_minimum")
    if budget["free_usdt"] >= policy["min_notional_usdt"]:
        score += 8.0
    else:
        blockers.append("insufficient_free_usdt")
    if str(signal.get("validation_state") or "").upper() == "VALIDATED":
        score += 6.0
    if warnings:
        score -= min(14.0, len(warnings) * 3.5)
    if blockers:
        score -= min(50.0, len(blockers) * 18.0)
    return round(_clamp(score), 2)


def build_autonomous_trade_intent_builder(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev78 read-only trade intent builder.

    Converts a validated signal into a normalized, non-executing trade intent.
    This is the last preview layer before a future order executor. It never
    places orders, never writes runtime state and never returns secrets.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    signal = data.get("autonomous_signal_validator") if isinstance(data.get("autonomous_signal_validator"), dict) else None
    if not signal:
        signal = build_autonomous_signal_validator(data, settings, auth_store, username)

    blockers = list(signal.get("blockers") or [])
    warnings = list(signal.get("warnings") or [])
    if not policy["enabled"]:
        blockers.append("trade_intent_builder_disabled")
    if _safe_float(signal.get("validation_score"), 0.0) < policy["min_validation_score"]:
        warnings.append("validation_score_below_intent_policy")
    if str(signal.get("validation_decision") or "").upper() in {"REJECT_SIGNAL", "WAIT"}:
        blockers.append("signal_not_approved_for_intent")

    budget = _risk_budget(data, policy)
    lane = _lane_from_signal(signal, policy)
    score = _intent_score(signal, budget, policy, blockers, warnings)
    symbol = str(signal.get("symbol") or "").upper()
    strategy = str(signal.get("strategy") or "micro_scalp_watch")

    if blockers:
        intent_state = "BLOCKED"
        intent_action = "NO_INTENT"
    elif score >= policy["min_intent_score"] and lane in {"PAPER", "MICRO_REAL_PREVIEW", "REAL_PREVIEW"}:
        intent_state = "READY"
        intent_action = f"BUILD_{lane}_INTENT"
    else:
        intent_state = "REVIEW"
        intent_action = "REVIEW_INTENT"

    trade_intent = {
        "intent_id": f"INTENT-{now_iso()}-{symbol or 'NONE'}",
        "symbol": symbol or None,
        "strategy": strategy,
        "lane": lane,
        "side": "LONG",  # Direction is intentionally conservative until strategy engine supplies signed bias.
        "order_type": "MARKET_PREVIEW",
        "notional_usdt": budget["suggested_notional_usdt"],
        "stop_loss_pct": policy["default_stop_loss_pct"],
        "take_profit_pct": policy["default_take_profit_pct"],
        "trailing_pct": policy["default_trailing_pct"],
        "time_in_force": "IOC_PREVIEW",
        "reduce_only": False,
        "paper_first": policy["paper_first"],
    }

    return {
        "status": "ok" if intent_state == "READY" else ("blocked" if intent_state == "BLOCKED" else "review"),
        "revision": 78,
        "engine": "autonomous_trade_intent_builder",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "intent_state": intent_state,
        "intent_action": intent_action,
        "intent_score": score,
        "trade_intent": trade_intent,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "inputs": {
            "signal_validator_revision": signal.get("revision"),
            "signal_validation_state": signal.get("validation_state"),
            "signal_validation_decision": signal.get("validation_decision"),
            "signal_validation_score": signal.get("validation_score"),
            "risk_budget": budget,
        },
        "policy": policy,
        "command_preview": {
            "type": "trade_intent_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "writes_runtime_state": False,
            "requires_signal_validator": True,
            "requires_risk_budget": True,
            "source_revision": 78,
            "intent_state": intent_state,
            "intent_action": intent_action,
            "symbol": symbol or None,
            "lane": lane,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    intent = payload.get("trade_intent") if isinstance(payload.get("trade_intent"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 78,
        "engine": "autonomous_trade_intent_builder_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "intent_state": payload.get("intent_state"),
        "intent_action": payload.get("intent_action"),
        "intent_score": payload.get("intent_score"),
        "symbol": intent.get("symbol"),
        "lane": intent.get("lane"),
        "notional_usdt": intent.get("notional_usdt"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_trade_intent_builder(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_trade_intent_builder(data, settings, auth_store, username))


def build_autonomous_trade_intent_builder_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_trade_intent_builder(data, settings, auth_store, username)
    summary = _summary_from_payload(payload)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    intent = payload.get("trade_intent") if isinstance(payload.get("trade_intent"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    checks = {
        "revision_78": payload.get("revision") == 78 and summary.get("revision") == 78,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "source_chain_visible": {"signal_validator_revision", "signal_validation_state", "signal_validation_decision", "risk_budget"}.issubset(inputs.keys()),
        "intent_contract": {"symbol", "strategy", "lane", "notional_usdt", "stop_loss_pct", "take_profit_pct"}.issubset(intent.keys()),
        "summary_minimal": {"intent_state", "intent_action", "attention_required"}.issubset(summary.keys()),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "secret_key" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 78,
        "engine": "autonomous_trade_intent_builder_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "intent_state": payload.get("intent_state"),
        "intent_action": payload.get("intent_action"),
        "intent_score": payload.get("intent_score"),
    }
