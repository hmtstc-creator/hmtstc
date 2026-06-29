from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_execution_simulator_service import build_autonomous_execution_simulator


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
    raw = settings.get("autonomous_execution_approval_gate") if isinstance(settings.get("autonomous_execution_approval_gate"), dict) else {}
    allowed_lanes = raw.get("allowed_lanes") if isinstance(raw.get("allowed_lanes"), list) else ["PAPER", "MICRO_REAL", "REAL_PREVIEW"]
    allowed_lanes = [str(item).upper() for item in allowed_lanes if str(item).strip()]
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_approval_score": _clamp(_safe_float(raw.get("min_approval_score"), 78.0), 1.0, 100.0),
        "min_simulation_score": _clamp(_safe_float(raw.get("min_simulation_score"), 72.0), 1.0, 100.0),
        "max_estimated_cost_pct": max(0.01, _safe_float(raw.get("max_estimated_cost_pct"), 0.32)),
        "block_partial_fill_risk": _safe_bool(raw.get("block_partial_fill_risk"), True),
        "allowed_lanes": allowed_lanes or ["PAPER", "MICRO_REAL", "REAL_PREVIEW"],
        "read_only": True,
        "auto_apply": False,
    }


def _simulator(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_execution_simulator") if isinstance(data.get("autonomous_execution_simulator"), dict) else None
    return raw or build_autonomous_execution_simulator(data, settings, auth_store, username)


def _score(simulator: dict, policy: dict, blockers: list[str], warnings: list[str]) -> float:
    score = _safe_float(simulator.get("simulation_score"), 0.0) * 0.82
    if simulator.get("simulation_state") == "READY":
        score += 10.0
    else:
        blockers.append("simulation_not_ready")

    fill = simulator.get("simulated_fill") if isinstance(simulator.get("simulated_fill"), dict) else {}
    cost = fill.get("cost_model") if isinstance(fill.get("cost_model"), dict) else {}
    lane = str(fill.get("lane") or "WATCH").upper()
    cost_pct = _safe_float(cost.get("estimated_cost_pct"), 99.0)

    if lane in policy["allowed_lanes"]:
        score += 4.0
    else:
        blockers.append("lane_not_allowed_for_approval")

    if cost_pct <= policy["max_estimated_cost_pct"]:
        score += 4.0
    else:
        blockers.append("estimated_cost_above_approval_gate")

    if policy["block_partial_fill_risk"] and cost.get("partial_fill_risk") is True:
        blockers.append("partial_fill_risk_blocked")
    elif cost.get("partial_fill_risk") is True:
        warnings.append("partial_fill_risk_allowed_by_policy")
        score -= 4.0

    if simulator.get("status") == "review":
        warnings.append("simulator_status_review")
    if simulator.get("status") == "blocked":
        blockers.append("simulator_status_blocked")

    inherited_blockers = simulator.get("blockers") if isinstance(simulator.get("blockers"), list) else []
    inherited_warnings = simulator.get("warnings") if isinstance(simulator.get("warnings"), list) else []
    blockers.extend(str(item) for item in inherited_blockers if item)
    warnings.extend(str(item) for item in inherited_warnings if item)

    if blockers:
        score -= min(48.0, len(set(blockers)) * 10.0)
    if warnings:
        score -= min(14.0, len(set(warnings)) * 2.0)
    return round(_clamp(score), 2)


def build_autonomous_execution_approval_gate(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev81 read-only final approval gate before execution.

    This gate consumes Rev80 simulation output and decides whether the planned
    execution may move forward as a command preview. It still places no order,
    sends no exchange request and writes no runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    simulator = _simulator(data, settings, auth_store, username)
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("execution_approval_gate_disabled")

    fill = simulator.get("simulated_fill") if isinstance(simulator.get("simulated_fill"), dict) else {}
    cost = fill.get("cost_model") if isinstance(fill.get("cost_model"), dict) else {}
    lane = str(fill.get("lane") or "WATCH").upper()
    symbol = fill.get("symbol")
    approval_score = _score(simulator, policy, blockers, warnings)

    if _safe_float(simulator.get("simulation_score"), 0.0) < policy["min_simulation_score"]:
        blockers.append("simulation_score_below_approval_floor")

    if blockers:
        approval_state = "BLOCKED"
        approval_action = "DO_NOT_RELEASE_EXECUTION"
    elif approval_score >= policy["min_approval_score"]:
        approval_state = "APPROVED"
        approval_action = f"RELEASE_{lane}_COMMAND_PREVIEW"
    else:
        approval_state = "REVIEW"
        approval_action = "HOLD_FOR_EXECUTION_REVIEW"

    generated_at = now_iso()
    approval_id = f"APPROVAL-{generated_at}-{symbol or 'NONE'}-{lane}"
    approval_packet = {
        "approval_id": approval_id,
        "source_simulation_id": fill.get("simulation_id"),
        "source_plan_id": fill.get("source_plan_id"),
        "lane": lane,
        "symbol": symbol,
        "side": fill.get("side"),
        "notional_usdt": fill.get("notional_usdt"),
        "estimated_cost_pct": cost.get("estimated_cost_pct"),
        "estimated_cost_usdt": cost.get("estimated_cost_usdt"),
        "partial_fill_risk": cost.get("partial_fill_risk"),
        "approved": approval_state == "APPROVED",
        "approval_state": approval_state,
        "approval_score": approval_score,
    }

    return {
        "status": "ok" if approval_state == "APPROVED" else ("blocked" if approval_state == "BLOCKED" else "review"),
        "revision": 81,
        "engine": "autonomous_execution_approval_gate",
        "generated_at": generated_at,
        "read_only": True,
        "auto_apply": False,
        "approval_state": approval_state,
        "approval_action": approval_action,
        "approval_score": approval_score,
        "approval_packet": approval_packet,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "inputs": {
            "simulator_revision": simulator.get("revision"),
            "simulation_state": simulator.get("simulation_state"),
            "simulation_action": simulator.get("simulation_action"),
            "simulation_score": simulator.get("simulation_score"),
            "source_simulation_id": fill.get("simulation_id"),
            "source_plan_id": fill.get("source_plan_id"),
        },
        "policy": policy,
        "command_preview": {
            "type": "execution_approval_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "requires_simulation_ready": True,
            "source_revision": 81,
            "approval_state": approval_state,
            "approval_action": approval_action,
            "lane": lane,
            "symbol": symbol,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    packet = payload.get("approval_packet") if isinstance(payload.get("approval_packet"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 81,
        "engine": "autonomous_execution_approval_gate_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "approval_state": payload.get("approval_state"),
        "approval_action": payload.get("approval_action"),
        "approval_score": payload.get("approval_score"),
        "lane": packet.get("lane"),
        "symbol": packet.get("symbol"),
        "notional_usdt": packet.get("notional_usdt"),
        "estimated_cost_pct": packet.get("estimated_cost_pct"),
        "approved": packet.get("approved") is True,
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_execution_approval_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_execution_approval_gate(data, settings, auth_store, username))


def build_autonomous_execution_approval_gate_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_execution_approval_gate(data, settings, auth_store, username)
    summary = _summary_from_payload(payload)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    packet = payload.get("approval_packet") if isinstance(payload.get("approval_packet"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    checks = {
        "revision_81": payload.get("revision") == 81 and summary.get("revision") == 81,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False and command.get("sends_exchange_request") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "approval_contract": {"approval_id", "source_simulation_id", "source_plan_id", "lane", "approval_state", "approval_score"}.issubset(packet.keys()),
        "source_chain_visible": {"simulator_revision", "simulation_state", "simulation_action", "source_simulation_id"}.issubset(inputs.keys()),
        "requires_simulation": command.get("requires_simulation_ready") is True,
        "summary_minimal": {"approval_state", "approval_action", "approved", "attention_required"}.issubset(summary.keys()),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "secret_key" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 81,
        "engine": "autonomous_execution_approval_gate_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "approval_state": payload.get("approval_state"),
        "approval_action": payload.get("approval_action"),
        "approval_score": payload.get("approval_score"),
    }
