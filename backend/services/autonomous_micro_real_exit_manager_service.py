from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_position_tracker_service import build_autonomous_micro_real_position_tracker


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


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_exit_manager") if isinstance(settings.get("autonomous_micro_real_exit_manager"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 92,
        "required_position_status": "OPEN",
        "exit_direct_close_enabled": _safe_bool(raw.get("exit_direct_close_enabled"), False),
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "owner_exit_confirmation_required": _safe_bool(raw.get("owner_exit_confirmation_required"), True),
        "owner_exit_confirmed": _safe_bool(raw.get("owner_exit_confirmed"), False),
        "emergency_close_compatible": _safe_bool(raw.get("emergency_close_compatible"), False),
        "kill_switch_active": _safe_bool(raw.get("kill_switch_active"), False),
        "safe_mode_active": _safe_bool(raw.get("safe_mode_active"), False),
        "max_exit_notional_usdt": max(1.0, _safe_float(raw.get("max_exit_notional_usdt"), 15.0)),
        "max_exit_loss_usdt": max(0.05, _safe_float(raw.get("max_exit_loss_usdt"), 0.75)),
        "take_profit_trigger_pct": max(0.05, _safe_float(raw.get("take_profit_trigger_pct"), 1.20)),
        "stop_loss_trigger_pct": max(0.05, _safe_float(raw.get("stop_loss_trigger_pct"), 0.75)),
        "trailing_trigger_pct": max(0.05, _safe_float(raw.get("trailing_trigger_pct"), 0.45)),
        "post_exit_evaluator_required": _safe_bool(raw.get("post_exit_evaluator_required"), True),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_position_tracker") if isinstance(data.get("autonomous_micro_real_position_tracker"), dict) else None
    if raw and raw.get("revision") == 92 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_position_tracker(data, settings, auth_store, username)


def _decide_exit_reason(pnl: dict, policy: dict) -> tuple[str, str]:
    roi = _safe_float(pnl.get("roi_pct"), 0.0)
    pnl_usdt = _safe_float(pnl.get("unrealized_pnl_usdt"), 0.0)
    if pnl_usdt <= -policy["max_exit_loss_usdt"] or roi <= -policy["stop_loss_trigger_pct"]:
        return "STOP_LOSS", "protect_capital"
    if roi >= policy["take_profit_trigger_pct"]:
        return "TAKE_PROFIT", "lock_profit"
    if roi > 0 and roi >= policy["trailing_trigger_pct"]:
        return "TRAILING_STOP_PREVIEW", "protect_open_profit"
    return "HOLD_PREVIEW", "no_exit_trigger_yet"


def _build_exit_payload(source: dict, reason: str) -> dict:
    pos = source.get("position_snapshot") if isinstance(source.get("position_snapshot"), dict) else {}
    symbol = str(source.get("symbol") or pos.get("symbol") or "UNKNOWN").upper()
    side = str(pos.get("side") or "BUY").upper()
    exit_side = "SELL" if side == "BUY" else "BUY"
    qty = _safe_float(pos.get("quantity"), 0.0)
    return {
        "symbol": symbol,
        "side": exit_side,
        "type": "MARKET",
        "quantity": qty,
        "reduce_only_semantics": True,
        "reason": reason,
        "client_exit_id_preview": "mrex_" + sha256(f"rev93:{symbol}:{qty}:{reason}".encode("utf-8")).hexdigest()[:24],
        "contains_secret": False,
    }


def build_autonomous_micro_real_exit_manager(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev93 micro-real exit manager.

    Builds exit intent/plan and a final approval gate for a tracked micro-real
    position. It never sends close orders, never performs exchange calls and
    never writes runtime state by default.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("micro_real_exit_manager_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_position_tracker_revision_mismatch")
    if command.get("approved_for_micro_real_exit_manager") is not True:
        blockers.append("source_not_approved_for_micro_real_exit_manager")
    if source.get("position_status") != policy["required_position_status"]:
        blockers.append("position_not_open")
    if source.get("manual_attention_required") is True:
        blockers.append("position_tracker_manual_attention_required")
    if policy["kill_switch_active"]:
        blockers.append("kill_switch_active")
    if policy["safe_mode_active"]:
        blockers.append("safe_mode_active")
    if not policy["emergency_close_compatible"]:
        warnings.append("emergency_close_compatibility_not_confirmed")
    if policy["owner_exit_confirmation_required"] and not policy["owner_exit_confirmed"]:
        warnings.append("owner_exit_confirmation_required")

    position = source.get("position_snapshot") if isinstance(source.get("position_snapshot"), dict) else {}
    pnl = source.get("pnl_estimate") if isinstance(source.get("pnl_estimate"), dict) else {}
    notional = _safe_float(position.get("notional_usdt") or pnl.get("notional_usdt"), 0.0)
    if notional > policy["max_exit_notional_usdt"]:
        blockers.append("exit_notional_above_micro_policy")

    exit_reason, exit_rationale = _decide_exit_reason(pnl, policy)
    payload_preview = _build_exit_payload(source, exit_reason)
    if _safe_float(payload_preview.get("quantity"), 0.0) <= 0:
        blockers.append("position_quantity_missing")

    final_gate_ready = (
        not blockers
        and policy["owner_exit_confirmed"]
        and policy["emergency_close_compatible"]
        and policy["exit_direct_close_enabled"]
        and policy["network_calls_allowed"]
        and policy["runtime_write_enabled"]
    )
    approval_gate_status = "EXIT_APPROVED_FOR_EXPLICIT_CLOSE" if final_gate_ready else ("EXIT_BLOCKED" if blockers else "EXIT_REVIEW_REQUIRED")
    manager_state = "MICRO_REAL_EXIT_READY" if final_gate_ready else ("MICRO_REAL_EXIT_BLOCKED" if blockers else "MICRO_REAL_EXIT_REVIEW")
    status = "ok" if final_gate_ready else ("blocked" if blockers else "review")
    score = max(0.0, min(100.0, _safe_float(source.get("tracker_score"), 75.0) - len(set(blockers)) * 15.0 - len(set(warnings)) * 3.0))
    exit_plan_id = "mrem_" + sha256(f"rev93:{username}:{source.get('tracker_id')}:{payload_preview.get('client_exit_id_preview')}".encode("utf-8")).hexdigest()[:24]

    return {
        "status": status,
        "revision": 93,
        "engine": "autonomous_micro_real_exit_manager",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "manager_state": manager_state,
        "manager_score": round(score, 2),
        "exit_plan_id": exit_plan_id,
        "source_revision": source.get("revision"),
        "source_tracker_id": source.get("tracker_id"),
        "source_tracker_state": source.get("tracker_state"),
        "symbol": source.get("symbol") or position.get("symbol"),
        "position_status": source.get("position_status"),
        "exit_intent": {
            "reason": exit_reason,
            "rationale": exit_rationale,
            "position_notional_usdt": notional,
            "unrealized_pnl_usdt": _safe_float(pnl.get("unrealized_pnl_usdt"), 0.0),
            "roi_pct": _safe_float(pnl.get("roi_pct"), 0.0),
            "post_exit_evaluator_required": policy["post_exit_evaluator_required"],
        },
        "exit_order_plan_preview": payload_preview,
        "final_exit_approval_gate": {
            "status": approval_gate_status,
            "ready_for_explicit_close": final_gate_ready,
            "owner_exit_confirmation_required": policy["owner_exit_confirmation_required"],
            "owner_exit_confirmed": policy["owner_exit_confirmed"],
            "emergency_close_compatible": policy["emergency_close_compatible"],
            "direct_close_enabled": policy["exit_direct_close_enabled"],
            "network_calls_allowed": policy["network_calls_allowed"],
            "runtime_write_enabled": policy["runtime_write_enabled"],
            "direct_close_default_off": True,
        },
        "safety_contract": {
            "max_exit_notional_usdt": policy["max_exit_notional_usdt"],
            "max_exit_loss_usdt": policy["max_exit_loss_usdt"],
            "kill_switch_active": policy["kill_switch_active"],
            "safe_mode_active": policy["safe_mode_active"],
            "contains_secret": False,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": policy,
        "command_preview": {
            "type": "micro_real_exit_manager_preview",
            "source_revision": 93,
            "manager_state": manager_state,
            "next_action": "EXPLICIT_MICRO_REAL_CLOSE_CAN_BE_SUBMITTED" if final_gate_ready else ("MANUAL_ATTENTION_REQUIRED" if blockers else "WAIT_FOR_OWNER_CONFIRMATION_AND_EMERGENCY_COMPATIBILITY"),
            "symbol": source.get("symbol") or position.get("symbol"),
            "lane": "MICRO_REAL_EXIT_MANAGER",
            "read_only": True,
            "auto_apply": False,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "approved_for_micro_real_result_evaluator": final_gate_ready,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    gate = payload.get("final_exit_approval_gate") if isinstance(payload.get("final_exit_approval_gate"), dict) else {}
    intent = payload.get("exit_intent") if isinstance(payload.get("exit_intent"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 93,
        "engine": "autonomous_micro_real_exit_manager_summary",
        "generated_at": payload.get("generated_at"),
        "manager_state": payload.get("manager_state"),
        "manager_score": payload.get("manager_score"),
        "next_action": command.get("next_action"),
        "symbol": payload.get("symbol"),
        "position_status": payload.get("position_status"),
        "exit_reason": intent.get("reason"),
        "unrealized_pnl_usdt": intent.get("unrealized_pnl_usdt"),
        "roi_pct": intent.get("roi_pct"),
        "ready_for_explicit_close": gate.get("ready_for_explicit_close") is True,
        "direct_close_default_off": gate.get("direct_close_default_off") is True,
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
    }


def build_summary_autonomous_micro_real_exit_manager(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_exit_manager(data, settings, auth_store, username))


def build_autonomous_micro_real_exit_manager_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_exit_manager(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    gate = payload.get("final_exit_approval_gate") if isinstance(payload.get("final_exit_approval_gate"), dict) else {}
    checks = {
        "revision_is_93": payload.get("revision") == 93,
        "source_tracker_chain_present": payload.get("source_revision") == 92,
        "exit_intent_present": isinstance(payload.get("exit_intent"), dict) and "reason" in payload.get("exit_intent", {}),
        "exit_order_plan_preview_present": isinstance(payload.get("exit_order_plan_preview"), dict) and payload.get("exit_order_plan_preview", {}).get("contains_secret") is False,
        "final_exit_approval_gate_present": isinstance(gate, dict) and gate.get("direct_close_default_off") is True,
        "service_does_not_place_order": payload.get("places_order") is False and command.get("places_order") is False,
        "service_does_not_execute_network_call": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False,
        "service_does_not_write_runtime": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "secret_safe": payload.get("safety_contract", {}).get("contains_secret") is False,
        "summary_revision_is_93": _summary_from_payload(payload).get("revision") == 93,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 93,
        "engine": "autonomous_micro_real_exit_manager_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_EXIT_MANAGER_OK" if passed else "MICRO_REAL_EXIT_MANAGER_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_state": payload.get("manager_state"),
        "sample_action": command.get("next_action"),
    }
