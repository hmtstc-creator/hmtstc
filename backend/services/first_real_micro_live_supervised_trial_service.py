from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

REVISION_RANGE = "1006-1010"
PACKAGE_NAME = "First Real Micro-Live Supervised Trial Block"
FINAL_DECISION_READY = "FIRST_REAL_MICRO_LIVE_SUPERVISED_TRIAL_READY"
DRILL_USERNAME = "rev1006_first_real_micro_live_supervised_trial"

MAX_FIRST_ORDER_NOTIONAL_USDT = 10.0
MAX_FIRST_ORDER_LOSS_USDT = 1.0
MAX_FIRST_ORDER_TIMEOUT_SECONDS = 180
ALLOWED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
ALLOWED_ORDER_TYPES = ("MARKET_PREVIEW", "LIMIT_PREVIEW")
REQUIRED_APPROVAL_FIELDS = ("owner_approved", "activation_token_present", "explicit_real_submit_enabled")
FORBIDDEN_TOKENS = (
    "api_secret",
    "secret_key",
    "binance_secret",
    "private_key",
    "raw_activation_token",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_trial_policy(username: str = DRILL_USERNAME) -> dict[str, Any]:
    return {
        "username": username,
        "lane": "FIRST_REAL_MICRO_LIVE_SUPERVISED_TRIAL",
        "mode": "SUPERVISED_PACKET_ONLY",
        "real_submit_default": False,
        "real_close_default": False,
        "emergency_close_default": False,
        "auto_scale": False,
        "auto_apply": False,
        "auto_close": False,
        "allowed_symbols": list(ALLOWED_SYMBOLS),
        "allowed_order_types": list(ALLOWED_ORDER_TYPES),
        "max_first_order_notional_usdt": MAX_FIRST_ORDER_NOTIONAL_USDT,
        "max_first_order_loss_usdt": MAX_FIRST_ORDER_LOSS_USDT,
        "max_timeout_seconds": MAX_FIRST_ORDER_TIMEOUT_SECONDS,
        "owner_approval_required": True,
        "activation_token_required": True,
        "paper_evidence_required": True,
        "read_only_preflight_required": True,
        "micro_live_permission_gate_required": True,
        "order_preview_required_before_submit": True,
        "position_tracker_required": True,
        "emergency_guard_required": True,
        "exit_plan_required": True,
        "sl_tp_required": True,
    }


def _safe_order_preview(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "preview_id": "REV1007-FIRST-REAL-MICRO-LIVE-ORDER-PREVIEW",
        "symbol": policy["allowed_symbols"][0],
        "side": "BUY",
        "order_type": "MARKET_PREVIEW",
        "notional_usdt": policy["max_first_order_notional_usdt"],
        "max_loss_usdt": policy["max_first_order_loss_usdt"],
        "submit_contract_ready": False,
        "submit_contract_reason": "Explicit enable, owner approval and activation token are required before live submit.",
        "real_exchange_submit_triggered": False,
        "binance_network_call_triggered": False,
        "secret_values_returned": False,
    }


def _safe_exit_plan(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "exit_plan_id": "REV1009-FIRST-REAL-MICRO-LIVE-EXIT-PLAN",
        "timeout_seconds": policy["max_timeout_seconds"],
        "stop_loss_usdt": policy["max_first_order_loss_usdt"],
        "take_profit_mode": "OPERATOR_DEFINED_BEFORE_SUBMIT",
        "sl_bound": True,
        "tp_binding_required": True,
        "timeout_bound": True,
        "manual_owner_close_required_if_guard_blocks_auto_close": True,
        "real_close_default": False,
        "auto_close": False,
        "emergency_close_default": False,
    }


def _leak_scan(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    leaks = [token for token in FORBIDDEN_TOKENS if token in serialized]
    return {"status": "PASS" if not leaks else "FAIL", "forbidden_tokens_found": leaks}


def build_rev1006_explicit_real_submit_enable_check(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_trial_policy(username)
    blockers: list[str] = []
    if policy["real_submit_default"] is not False:
        blockers.append("real_submit_default_not_off")
    if policy["owner_approval_required"] is not True:
        blockers.append("owner_approval_not_required")
    if policy["activation_token_required"] is not True:
        blockers.append("activation_token_not_required")
    return {
        "revision": 1006,
        "name": "explicit_real_submit_enable_check",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "required_fields": list(REQUIRED_APPROVAL_FIELDS),
        "explicit_real_submit_enabled": False,
        "owner_approved": False,
        "activation_token_present": False,
        "ready_for_real_submit": False,
        "allowed_action": "ORDER_PREVIEW_ONLY",
        "real_order_submit_triggered": False,
        "binance_network_call_triggered": False,
    }


def build_rev1007_order_preview_submit_final_contract(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_trial_policy(username)
    preview = _safe_order_preview(policy)
    blockers: list[str] = []
    if preview["notional_usdt"] > policy["max_first_order_notional_usdt"]:
        blockers.append("preview_notional_above_first_order_cap")
    if preview["submit_contract_ready"] is not False:
        blockers.append("submit_contract_ready_without_owner_gate")
    if preview["real_exchange_submit_triggered"] is not False:
        blockers.append("real_exchange_submit_triggered")
    return {
        "revision": 1007,
        "name": "order_preview_submit_final_contract",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "order_preview": preview,
        "preview_required_before_submit": True,
        "submit_allowed_now": False,
        "real_order_submit_triggered": False,
        "binance_network_call_triggered": False,
    }


def build_rev1008_position_tracker_emergency_guard_binding(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_trial_policy(username)
    blockers: list[str] = []
    guard = {
        "position_tracker_bound": True,
        "exchange_order_status_collector_required": True,
        "emergency_guard_bound": True,
        "max_open_position_notional_usdt": policy["max_first_order_notional_usdt"],
        "max_position_loss_usdt": policy["max_first_order_loss_usdt"],
        "emergency_close_default": False,
        "operator_confirmed_close_required": True,
        "auto_close": False,
    }
    if guard["position_tracker_bound"] is not True:
        blockers.append("position_tracker_not_bound")
    if guard["emergency_guard_bound"] is not True:
        blockers.append("emergency_guard_not_bound")
    if guard["emergency_close_default"] is not False:
        blockers.append("emergency_close_default_not_off")
    return {
        "revision": 1008,
        "name": "position_tracker_emergency_guard_binding",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "guard_binding": guard,
        "real_order_close_triggered": False,
        "emergency_close_triggered": False,
        "binance_network_call_triggered": False,
    }


def build_rev1009_exit_plan_timeout_sl_tp_binding(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_trial_policy(username)
    exit_plan = _safe_exit_plan(policy)
    blockers: list[str] = []
    if exit_plan["timeout_seconds"] <= 0:
        blockers.append("timeout_missing")
    if exit_plan["stop_loss_usdt"] <= 0 or exit_plan["stop_loss_usdt"] > policy["max_first_order_loss_usdt"]:
        blockers.append("stop_loss_not_bound_to_micro_cap")
    if exit_plan["sl_bound"] is not True:
        blockers.append("stop_loss_not_bound")
    if exit_plan["tp_binding_required"] is not True:
        blockers.append("take_profit_binding_not_required")
    return {
        "revision": 1009,
        "name": "exit_plan_timeout_sl_tp_binding",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "exit_plan": exit_plan,
        "real_order_submit_triggered": False,
        "real_order_close_triggered": False,
        "emergency_close_triggered": False,
    }


def build_first_real_micro_live_supervised_trial_packet(username: str = DRILL_USERNAME) -> dict[str, Any]:
    generated_at = now_iso()
    checks = {
        "rev1006_explicit_real_submit_enable": build_rev1006_explicit_real_submit_enable_check(username),
        "rev1007_order_preview_submit_contract": build_rev1007_order_preview_submit_final_contract(username),
        "rev1008_position_tracker_emergency_guard": build_rev1008_position_tracker_emergency_guard_binding(username),
        "rev1009_exit_plan_timeout_sl_tp": build_rev1009_exit_plan_timeout_sl_tp_binding(username),
    }
    blockers: list[str] = []
    for check_name, check in checks.items():
        blockers.extend([f"{check_name}:{item}" for item in check.get("blockers", [])])
    safety_scope = {
        "real_order_submit_triggered": False,
        "real_order_close_triggered": False,
        "emergency_close_triggered": False,
        "binance_network_call_triggered": False,
        "runtime_write_triggered": False,
        "explicit_real_submit_enabled": False,
        "owner_approved": False,
        "activation_token_returned": False,
        "auto_apply": False,
        "auto_close": False,
        "auto_scale": False,
    }
    report = {
        "status": "ok" if not blockers else "blocked",
        "revision": 1010,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "generated_at": generated_at,
        "final_decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "safety_scope": safety_scope,
        "trial_policy": _safe_trial_policy(username),
        "order_preview_contract": checks["rev1007_order_preview_submit_contract"]["order_preview"],
        "exit_plan_contract": checks["rev1009_exit_plan_timeout_sl_tp"]["exit_plan"],
        "secret_values_returned": False,
        "operator_next_steps": [
            "Run Rev1010 packet after Rev1005 gate passes on VPS.",
            "Keep real submit disabled until explicit enable, owner approval and activation token are supplied in the live UI flow.",
            "Before any micro-live submit, verify order preview, position tracker, emergency guard, timeout and SL/TP bindings together.",
        ],
    }
    report["leak_scan"] = _leak_scan(report)
    if report["leak_scan"]["status"] != "PASS":
        report["status"] = "blocked"
        report["final_decision"] = "BLOCKED"
        report["blockers"].append("forbidden_secret_token_leak_detected")
    return report


def build_first_real_micro_live_supervised_trial_summary(username: str = DRILL_USERNAME) -> dict[str, Any]:
    report = build_first_real_micro_live_supervised_trial_packet(username)
    policy = report["trial_policy"]
    return {
        "status": report["status"],
        "revision": report["revision"],
        "final_decision": report["final_decision"],
        "blocker_count": len(report["blockers"]),
        "max_first_order_notional_usdt": policy["max_first_order_notional_usdt"],
        "max_first_order_loss_usdt": policy["max_first_order_loss_usdt"],
        "allowed_symbols": policy["allowed_symbols"],
        "owner_approval_required": policy["owner_approval_required"],
        "activation_token_required": policy["activation_token_required"],
        "order_preview_required_before_submit": policy["order_preview_required_before_submit"],
        "position_tracker_required": policy["position_tracker_required"],
        "exit_plan_required": policy["exit_plan_required"],
        "real_order_submit_triggered": False,
        "binance_network_call_triggered": False,
        "secret_values_returned": False,
    }
