from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_probe_planner_service import build_autonomous_micro_real_probe_planner


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
    raw = settings.get("autonomous_micro_real_approval_gate") if isinstance(settings.get("autonomous_micro_real_approval_gate"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_plan_score": _clamp(_safe_float(raw.get("min_plan_score"), 82.0), 1.0, 100.0),
        "max_approved_notional_usdt": max(5.0, _safe_float(raw.get("max_approved_notional_usdt"), 25.0)),
        "max_approved_loss_usdt": max(0.25, _safe_float(raw.get("max_approved_loss_usdt"), 1.0)),
        "require_plan_state": str(raw.get("require_plan_state") or "MICRO_REAL_PROBE_PLAN_READY"),
        "require_idempotency_key_prefix": "mrp_",
        "target_lane": "MICRO_REAL_APPROVAL_PREVIEW",
        "read_only": True,
        "auto_apply": False,
        "requires_owner_confirmation": True,
    }


def _planner(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_probe_planner") if isinstance(data.get("autonomous_micro_real_probe_planner"), dict) else None
    return raw or build_autonomous_micro_real_probe_planner(data, settings, auth_store, username)


def _approval_id(symbol: str, idempotency_key: str, plan_score: float, username: str) -> str:
    seed = f"rev87:{username}:{symbol}:{idempotency_key}:{round(plan_score, 2)}"
    return "mra_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


def _next_action(state: str) -> str:
    if state == "MICRO_REAL_APPROVAL_READY":
        return "ALLOW_OWNER_CONFIRMED_MICRO_REAL_EXECUTION_BRIDGE_PREVIEW"
    if state == "MICRO_REAL_APPROVAL_REVIEW_REQUIRED":
        return "REVIEW_PROBE_APPROVAL_INPUTS_BEFORE_EXECUTION"
    return "KEEP_MICRO_REAL_EXECUTION_BLOCKED"


def build_autonomous_micro_real_approval_gate(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev87 read-only approval gate for micro-real probe execution.

    This gate is intentionally not an execution engine. It validates the Rev86
    probe plan, bounds notional/loss once more, creates an approval ticket and
    produces a command preview for the later execution bridge. It never calls an
    exchange, never places an order and never writes runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    plan = _planner(data, settings, auth_store, username)
    command = plan.get("command_preview") if isinstance(plan.get("command_preview"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []

    plan_state = str(plan.get("plan_state") or "unknown")
    plan_score = _safe_float(plan.get("plan_score"), 0.0)
    symbol = str(plan.get("symbol") or "UNKNOWN")
    idempotency_key = str(plan.get("idempotency_key") or command.get("idempotency_key") or "")
    notional = _safe_float(plan.get("probe_notional_usdt"), 0.0)
    max_loss = _safe_float(plan.get("max_probe_loss_usdt"), 0.0)

    if not policy["enabled"]:
        blockers.append("micro_real_approval_gate_disabled")
    if plan.get("revision") != 86:
        blockers.append("micro_real_probe_plan_revision_mismatch")
    if plan.get("status") != "ok":
        blockers.append("micro_real_probe_plan_not_ok")
    if plan_state != policy["require_plan_state"]:
        blockers.append("micro_real_probe_plan_state_not_ready")
    if plan_score < policy["min_plan_score"]:
        blockers.append("micro_real_probe_plan_score_below_approval_floor")
    if not idempotency_key.startswith(policy["require_idempotency_key_prefix"]):
        blockers.append("missing_or_invalid_probe_idempotency_key")
    if notional <= 0 or notional > policy["max_approved_notional_usdt"]:
        blockers.append("probe_notional_outside_approval_bounds")
    if max_loss <= 0 or max_loss > policy["max_approved_loss_usdt"]:
        blockers.append("probe_loss_outside_approval_bounds")
    if command.get("places_order") is not False:
        blockers.append("source_command_not_read_only")
    if command.get("sends_exchange_request") is not False:
        blockers.append("source_command_exchange_request_not_blocked")
    if command.get("writes_runtime_state") is not False:
        blockers.append("source_command_runtime_write_not_blocked")
    if symbol == "UNKNOWN":
        warnings.append("missing_symbol_for_micro_real_approval")

    approval_score = plan_score
    if blockers:
        approval_score -= min(60.0, len(set(blockers)) * 14.0)
    if warnings:
        approval_score -= min(8.0, len(set(warnings)) * 2.0)
    approval_score = round(_clamp(approval_score), 2)

    if blockers:
        approval_state = "BLOCKED"
    elif approval_score >= policy["min_plan_score"]:
        approval_state = "MICRO_REAL_APPROVAL_READY"
    else:
        approval_state = "MICRO_REAL_APPROVAL_REVIEW_REQUIRED"
    status = "ok" if approval_state == "MICRO_REAL_APPROVAL_READY" else ("blocked" if approval_state == "BLOCKED" else "review")
    next_action = _next_action(approval_state)
    approval_id = _approval_id(symbol, idempotency_key, plan_score, username)

    return {
        "status": status,
        "revision": 87,
        "engine": "autonomous_micro_real_approval_gate",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "approval_state": approval_state,
        "approval_score": approval_score,
        "next_action": next_action,
        "source_revision": plan.get("revision"),
        "source_plan_state": plan_state,
        "source_plan_score": plan_score,
        "symbol": symbol,
        "source_lane": plan.get("target_lane"),
        "target_lane": policy["target_lane"] if status == "ok" else "MICRO_REAL_BLOCKED",
        "approved_notional_usdt": round(min(notional, policy["max_approved_notional_usdt"]), 4),
        "approved_max_loss_usdt": round(min(max_loss, policy["max_approved_loss_usdt"]), 4),
        "source_idempotency_key": idempotency_key,
        "approval_id": approval_id,
        "requires_owner_confirmation": True,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy": policy,
        "inputs": {
            "micro_real_probe_planner_revision": plan.get("revision"),
            "micro_real_probe_plan_state": plan_state,
            "micro_real_probe_plan_score": plan_score,
            "probe_notional_usdt": notional,
            "max_probe_loss_usdt": max_loss,
            "idempotency_key": idempotency_key,
        },
        "command_preview": {
            "type": "micro_real_approval_gate_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "source_revision": 87,
            "approval_state": approval_state,
            "next_action": next_action,
            "symbol": symbol,
            "lane": policy["target_lane"] if status == "ok" else "MICRO_REAL_BLOCKED",
            "notional_usdt": round(min(notional, policy["max_approved_notional_usdt"]), 4),
            "max_loss_usdt": round(min(max_loss, policy["max_approved_loss_usdt"]), 4),
            "source_idempotency_key": idempotency_key,
            "approval_id": approval_id,
            "requires_owner_confirmation": True,
            "approved_for_later_execution_bridge": status == "ok",
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 87,
        "engine": "autonomous_micro_real_approval_gate_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "approval_state": payload.get("approval_state"),
        "approval_score": payload.get("approval_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "target_lane": payload.get("target_lane"),
        "approved_notional_usdt": payload.get("approved_notional_usdt"),
        "approved_max_loss_usdt": payload.get("approved_max_loss_usdt"),
        "requires_owner_confirmation": payload.get("requires_owner_confirmation"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_micro_real_approval_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_approval_gate(data, settings, auth_store, username))


def build_autonomous_micro_real_approval_gate_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_approval_gate(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_87": payload.get("revision") == 87,
        "micro_real_probe_planner_chain_present": (payload.get("inputs") or {}).get("micro_real_probe_planner_revision") == 86,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": command.get("places_order") is False,
        "no_exchange_request": command.get("sends_exchange_request") is False,
        "no_runtime_write": command.get("writes_runtime_state") is False,
        "bounded_approval_notional": _safe_float(payload.get("approved_notional_usdt"), 0.0) <= _safe_float((payload.get("policy") or {}).get("max_approved_notional_usdt"), 0.0),
        "bounded_approval_loss": _safe_float(payload.get("approved_max_loss_usdt"), 0.0) <= _safe_float((payload.get("policy") or {}).get("max_approved_loss_usdt"), 0.0),
        "approval_id_present": isinstance(payload.get("approval_id"), str) and payload.get("approval_id", "").startswith("mra_"),
        "owner_confirmation_required": payload.get("requires_owner_confirmation") is True and command.get("requires_owner_confirmation") is True,
        "summary_revision_is_87": summary.get("revision") == 87,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 87,
        "engine": "autonomous_micro_real_approval_gate_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_APPROVAL_GATE_OK" if passed else "MICRO_REAL_APPROVAL_GATE_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("approval_state"),
        "sample_action": payload.get("next_action"),
    }
