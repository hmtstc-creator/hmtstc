from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_execution_approval_gate_service import build_autonomous_execution_approval_gate


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
    raw = settings.get("autonomous_paper_execution_runner") if isinstance(settings.get("autonomous_paper_execution_runner"), dict) else {}
    allowed_lanes = raw.get("allowed_lanes") if isinstance(raw.get("allowed_lanes"), list) else ["PAPER"]
    allowed_lanes = [str(item).upper() for item in allowed_lanes if str(item).strip()]
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "allowed_lanes": allowed_lanes or ["PAPER"],
        "min_approval_score": _clamp(_safe_float(raw.get("min_approval_score"), 78.0), 1.0, 100.0),
        "max_fee_pct": max(0.0, _safe_float(raw.get("max_fee_pct"), 0.12)),
        "max_slippage_pct": max(0.0, _safe_float(raw.get("max_slippage_pct"), 0.18)),
        "default_reference_price": max(0.00000001, _safe_float(raw.get("default_reference_price"), 100.0)),
        "paper_only": True,
        "read_only": True,
        "auto_apply": False,
    }


def _approval(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_execution_approval_gate") if isinstance(data.get("autonomous_execution_approval_gate"), dict) else None
    return raw or build_autonomous_execution_approval_gate(data, settings, auth_store, username)


def _score(approval: dict, policy: dict, blockers: list[str], warnings: list[str]) -> float:
    score = _safe_float(approval.get("approval_score"), 0.0) * 0.76
    packet = approval.get("approval_packet") if isinstance(approval.get("approval_packet"), dict) else {}
    lane = str(packet.get("lane") or "WATCH").upper()
    estimated_cost_pct = _safe_float(packet.get("estimated_cost_pct"), 99.0)

    if approval.get("approval_state") == "APPROVED":
        score += 12.0
    else:
        blockers.append("approval_gate_not_approved")

    if lane in policy["allowed_lanes"]:
        score += 8.0
    else:
        blockers.append("paper_runner_lane_not_allowed")

    if _safe_float(approval.get("approval_score"), 0.0) >= policy["min_approval_score"]:
        score += 4.0
    else:
        blockers.append("approval_score_below_paper_runner_floor")

    if estimated_cost_pct <= policy["max_fee_pct"] + policy["max_slippage_pct"] + 0.08:
        score += 3.0
    else:
        warnings.append("estimated_cost_near_or_above_paper_runner_cost_guard")
        score -= 5.0

    inherited_blockers = approval.get("blockers") if isinstance(approval.get("blockers"), list) else []
    inherited_warnings = approval.get("warnings") if isinstance(approval.get("warnings"), list) else []
    blockers.extend(str(item) for item in inherited_blockers if item)
    warnings.extend(str(item) for item in inherited_warnings if item)

    if blockers:
        score -= min(42.0, len(set(blockers)) * 9.0)
    if warnings:
        score -= min(12.0, len(set(warnings)) * 2.0)
    return round(_clamp(score), 2)


def _paper_fill(packet: dict, policy: dict, runner_score: float, generated_at: str) -> dict:
    notional = max(0.0, _safe_float(packet.get("notional_usdt"), 0.0))
    reference_price = policy["default_reference_price"]
    side = str(packet.get("side") or "BUY").upper()
    estimated_cost_pct = max(0.0, _safe_float(packet.get("estimated_cost_pct"), 0.0))
    fee_pct = min(policy["max_fee_pct"], max(0.0, estimated_cost_pct * 0.45))
    slippage_pct = min(policy["max_slippage_pct"], max(0.0, estimated_cost_pct * 0.55))
    fill_multiplier = 1 + (slippage_pct / 100.0 if side == "BUY" else -slippage_pct / 100.0)
    fill_price = round(reference_price * fill_multiplier, 8)
    qty = round(notional / fill_price, 8) if fill_price > 0 else 0.0
    fee_usdt = round(notional * fee_pct / 100.0, 6)
    slippage_usdt = round(notional * slippage_pct / 100.0, 6)
    return {
        "paper_execution_id": f"PAPER-{generated_at}-{packet.get('symbol') or 'NONE'}-{packet.get('lane') or 'WATCH'}",
        "source_approval_id": packet.get("approval_id"),
        "source_plan_id": packet.get("source_plan_id"),
        "source_simulation_id": packet.get("source_simulation_id"),
        "lane": packet.get("lane"),
        "symbol": packet.get("symbol"),
        "side": side,
        "notional_usdt": round(notional, 4),
        "reference_price": reference_price,
        "paper_fill_price": fill_price,
        "paper_quantity": qty,
        "fee_pct": round(fee_pct, 4),
        "fee_usdt": fee_usdt,
        "slippage_pct": round(slippage_pct, 4),
        "slippage_usdt": slippage_usdt,
        "net_open_cost_usdt": round(fee_usdt + slippage_usdt, 6),
        "paper_execution_score": runner_score,
        "paper_filled": runner_score >= 72.0,
    }


def build_autonomous_paper_execution_runner(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev82 read-only paper execution runner.

    Converts an approved Rev81 execution packet into a deterministic paper fill.
    It is intentionally paper-only: no exchange request, no direct order placement
    and no runtime persistence/write side effect.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    approval = _approval(data, settings, auth_store, username)
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("paper_execution_runner_disabled")

    packet = approval.get("approval_packet") if isinstance(approval.get("approval_packet"), dict) else {}
    runner_score = _score(approval, policy, blockers, warnings)
    generated_at = now_iso()

    if blockers:
        execution_state = "BLOCKED"
        execution_action = "DO_NOT_RUN_PAPER_EXECUTION"
    elif runner_score >= 78.0:
        execution_state = "PAPER_EXECUTED"
        execution_action = "RECORD_PAPER_FILL_PREVIEW"
    else:
        execution_state = "REVIEW"
        execution_action = "HOLD_PAPER_EXECUTION_REVIEW"

    paper_fill = _paper_fill(packet, policy, runner_score, generated_at) if execution_state == "PAPER_EXECUTED" else {}

    return {
        "status": "ok" if execution_state == "PAPER_EXECUTED" else ("blocked" if execution_state == "BLOCKED" else "review"),
        "revision": 82,
        "engine": "autonomous_paper_execution_runner",
        "generated_at": generated_at,
        "read_only": True,
        "auto_apply": False,
        "execution_state": execution_state,
        "execution_action": execution_action,
        "paper_execution_score": runner_score,
        "paper_fill": paper_fill,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "inputs": {
            "approval_revision": approval.get("revision"),
            "approval_state": approval.get("approval_state"),
            "approval_score": approval.get("approval_score"),
            "source_approval_id": packet.get("approval_id"),
            "source_plan_id": packet.get("source_plan_id"),
            "source_simulation_id": packet.get("source_simulation_id"),
            "lane": packet.get("lane"),
            "symbol": packet.get("symbol"),
        },
        "policy": policy,
        "command_preview": {
            "type": "paper_execution_runner_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "paper_only": True,
            "source_revision": 82,
            "execution_state": execution_state,
            "execution_action": execution_action,
            "symbol": packet.get("symbol"),
            "lane": packet.get("lane"),
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    fill = payload.get("paper_fill") if isinstance(payload.get("paper_fill"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 82,
        "engine": "autonomous_paper_execution_runner_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "execution_state": payload.get("execution_state"),
        "execution_action": payload.get("execution_action"),
        "paper_execution_score": payload.get("paper_execution_score"),
        "paper_filled": fill.get("paper_filled") is True,
        "symbol": fill.get("symbol") or (payload.get("inputs") or {}).get("symbol"),
        "lane": fill.get("lane") or (payload.get("inputs") or {}).get("lane"),
        "notional_usdt": fill.get("notional_usdt"),
        "net_open_cost_usdt": fill.get("net_open_cost_usdt"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_paper_execution_runner(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_paper_execution_runner(data, settings, auth_store, username))


def build_autonomous_paper_execution_runner_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_paper_execution_runner(data, settings, auth_store, username)
    summary = _summary_from_payload(payload)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_is_82": payload.get("revision") == 82,
        "approval_chain_present": (payload.get("inputs") or {}).get("approval_revision") == 81,
        "paper_only": command.get("paper_only") is True,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": command.get("places_order") is False,
        "no_exchange_request": command.get("sends_exchange_request") is False,
        "no_runtime_write": command.get("writes_runtime_state") is False,
        "summary_revision_is_82": summary.get("revision") == 82,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 82,
        "engine": "autonomous_paper_execution_runner_quality",
        "generated_at": now_iso(),
        "quality_status": "PAPER_EXECUTION_RUNNER_OK" if passed else "PAPER_EXECUTION_RUNNER_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("execution_state"),
        "sample_action": payload.get("execution_action"),
    }
