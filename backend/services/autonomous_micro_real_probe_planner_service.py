from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_readiness_gate_service import build_autonomous_micro_real_readiness_gate


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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_probe_planner") if isinstance(settings.get("autonomous_micro_real_probe_planner"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_readiness_score": _clamp(_safe_float(raw.get("min_readiness_score"), 78.0), 1.0, 100.0),
        "max_probe_notional_usdt": max(5.0, _safe_float(raw.get("max_probe_notional_usdt"), 25.0)),
        "max_probe_loss_usdt": max(0.25, _safe_float(raw.get("max_probe_loss_usdt"), 1.0)),
        "max_probe_loss_pct": max(0.05, _safe_float(raw.get("max_probe_loss_pct"), 0.45)),
        "max_probe_count_per_day": max(1, _safe_int(raw.get("max_probe_count_per_day"), 3)),
        "require_readiness_state": str(raw.get("require_readiness_state") or "READY_FOR_MICRO_REAL_PROBATION"),
        "allowed_lane": "MICRO_REAL_PREVIEW",
        "read_only": True,
        "auto_apply": False,
    }


def _readiness(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_readiness_gate") if isinstance(data.get("autonomous_micro_real_readiness_gate"), dict) else None
    return raw or build_autonomous_micro_real_readiness_gate(data, settings, auth_store, username)


def _probe_count(data: dict) -> int:
    history = data.get("micro_real_probe_history")
    if isinstance(history, list):
        today_prefix = now_iso()[:10]
        return sum(1 for item in history if isinstance(item, dict) and str(item.get("created_at") or "").startswith(today_prefix))
    return _safe_int(data.get("micro_real_probe_count_today"), 0)


def _idempotency_key(symbol: str, lane: str, notional: float, readiness_score: float, username: str) -> str:
    seed = f"rev86:{username}:{symbol}:{lane}:{round(notional, 4)}:{round(readiness_score, 2)}"
    return "mrp_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


def _next_action(state: str) -> str:
    if state == "MICRO_REAL_PROBE_PLAN_READY":
        return "SEND_TO_FINAL_APPROVAL_BEFORE_ANY_EXCHANGE_REQUEST"
    if state == "MICRO_REAL_PROBE_REVIEW_REQUIRED":
        return "REVIEW_PROBE_LIMITS_OR_READINESS_INPUTS"
    return "KEEP_MICRO_REAL_PROBE_BLOCKED"


def build_autonomous_micro_real_probe_planner(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev86 read-only planner for a tiny micro-real probation probe.

    The planner converts Rev85 readiness into a final micro-real probe preview.
    It deliberately never places an order, never calls the exchange and never
    writes runtime state. Its output is a bounded command preview that can be
    reviewed by a later approval/execution bridge.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    readiness = _readiness(data, settings, auth_store, username)
    blockers: list[str] = []
    warnings: list[str] = []

    readiness_state = str(readiness.get("readiness_state") or "unknown")
    readiness_score = _safe_float(readiness.get("readiness_score"), 0.0)
    target_lane = str(readiness.get("target_lane") or "")
    symbol = str(readiness.get("symbol") or "UNKNOWN")
    probe_count_today = _probe_count(data)

    if not policy["enabled"]:
        blockers.append("micro_real_probe_planner_disabled")
    if readiness.get("revision") != 85:
        blockers.append("micro_real_readiness_revision_mismatch")
    if readiness_state != policy["require_readiness_state"]:
        blockers.append("micro_real_readiness_state_not_probation_ready")
    if readiness_score < policy["min_readiness_score"]:
        blockers.append("readiness_score_below_probe_floor")
    if target_lane != policy["allowed_lane"]:
        blockers.append("target_lane_not_micro_real_preview")
    if readiness.get("status") == "blocked":
        blockers.append("readiness_gate_blocked")
    if probe_count_today >= policy["max_probe_count_per_day"]:
        blockers.append("daily_micro_real_probe_limit_reached")
    if symbol == "UNKNOWN":
        warnings.append("missing_symbol_for_probe_plan")

    source_notional = _safe_float(readiness.get("probe_notional_usdt"), policy["max_probe_notional_usdt"])
    probe_notional = min(policy["max_probe_notional_usdt"], source_notional)
    max_loss_by_pct = probe_notional * policy["max_probe_loss_pct"] / 100.0
    max_probe_loss = min(policy["max_probe_loss_usdt"], max_loss_by_pct if max_loss_by_pct > 0 else policy["max_probe_loss_usdt"])
    idempotency_key = _idempotency_key(symbol, policy["allowed_lane"], probe_notional, readiness_score, username)

    plan_score = readiness_score
    if blockers:
        plan_score -= min(50.0, len(set(blockers)) * 12.5)
    if warnings:
        plan_score -= min(8.0, len(set(warnings)) * 2.0)
    plan_score = round(_clamp(plan_score), 2)

    if blockers:
        plan_state = "BLOCKED"
    elif plan_score >= policy["min_readiness_score"]:
        plan_state = "MICRO_REAL_PROBE_PLAN_READY"
    else:
        plan_state = "MICRO_REAL_PROBE_REVIEW_REQUIRED"
    status = "ok" if plan_state == "MICRO_REAL_PROBE_PLAN_READY" else ("blocked" if plan_state == "BLOCKED" else "review")
    next_action = _next_action(plan_state)

    return {
        "status": status,
        "revision": 86,
        "engine": "autonomous_micro_real_probe_planner",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "plan_state": plan_state,
        "plan_score": plan_score,
        "next_action": next_action,
        "source_revision": readiness.get("revision"),
        "source_readiness_state": readiness_state,
        "source_readiness_score": readiness_score,
        "symbol": symbol,
        "source_lane": "PAPER",
        "target_lane": "MICRO_REAL_PREVIEW" if plan_state != "BLOCKED" else "PAPER",
        "probe_notional_usdt": round(probe_notional, 4),
        "max_probe_loss_usdt": round(max_probe_loss, 4),
        "max_probe_loss_pct": policy["max_probe_loss_pct"],
        "probe_count_today": probe_count_today,
        "remaining_probe_slots_today": max(0, policy["max_probe_count_per_day"] - probe_count_today),
        "idempotency_key": idempotency_key,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy": policy,
        "inputs": {
            "micro_real_readiness_revision": readiness.get("revision"),
            "micro_real_readiness_state": readiness_state,
            "micro_real_readiness_score": readiness_score,
            "api_readiness": readiness.get("api_readiness"),
            "api_trade_enabled": readiness.get("api_trade_enabled"),
        },
        "command_preview": {
            "type": "micro_real_probe_plan_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "source_revision": 86,
            "plan_state": plan_state,
            "next_action": next_action,
            "symbol": symbol,
            "lane": "MICRO_REAL_PREVIEW" if plan_state != "BLOCKED" else "PAPER",
            "notional_usdt": round(probe_notional, 4),
            "max_loss_usdt": round(max_probe_loss, 4),
            "idempotency_key": idempotency_key,
            "requires_final_execution_approval": True,
            "requires_manual_confirmation": False,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 86,
        "engine": "autonomous_micro_real_probe_planner_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "plan_state": payload.get("plan_state"),
        "plan_score": payload.get("plan_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "target_lane": payload.get("target_lane"),
        "probe_notional_usdt": payload.get("probe_notional_usdt"),
        "max_probe_loss_usdt": payload.get("max_probe_loss_usdt"),
        "remaining_probe_slots_today": payload.get("remaining_probe_slots_today"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_micro_real_probe_planner(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_probe_planner(data, settings, auth_store, username))


def build_autonomous_micro_real_probe_planner_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_probe_planner(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_86": payload.get("revision") == 86,
        "micro_real_readiness_chain_present": (payload.get("inputs") or {}).get("micro_real_readiness_revision") == 85,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": command.get("places_order") is False,
        "no_exchange_request": command.get("sends_exchange_request") is False,
        "no_runtime_write": command.get("writes_runtime_state") is False,
        "bounded_probe_notional": _safe_float(payload.get("probe_notional_usdt"), 0.0) <= _safe_float((payload.get("policy") or {}).get("max_probe_notional_usdt"), 0.0),
        "bounded_probe_loss": _safe_float(payload.get("max_probe_loss_usdt"), 0.0) <= _safe_float((payload.get("policy") or {}).get("max_probe_loss_usdt"), 0.0),
        "idempotency_key_present": isinstance(payload.get("idempotency_key"), str) and payload.get("idempotency_key", "").startswith("mrp_"),
        "summary_revision_is_86": summary.get("revision") == 86,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 86,
        "engine": "autonomous_micro_real_probe_planner_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_PROBE_PLANNER_OK" if passed else "MICRO_REAL_PROBE_PLANNER_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("plan_state"),
        "sample_action": payload.get("next_action"),
    }
