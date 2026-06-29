from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

REVISION_RANGE = "1001-1005"
PACKAGE_NAME = "Micro-Live Permission Final Gate Block"
FINAL_DECISION_READY = "MICRO_LIVE_PERMISSION_GATE_READY"
DRILL_USERNAME = "rev1001_micro_live_permission_gate"

MAX_MICRO_LIVE_NOTIONAL_USDT = 10.0
MAX_MICRO_LIVE_LOSS_USDT = 1.0
MAX_MICRO_LIVE_LOSS_PCT = 0.35
ALLOWED_SYMBOLS = ("BTCUSDT", "ETHUSDT")
ALLOWED_STRATEGIES = ("choch_micro_scalper", "imbalance_fill_hunter")
FORBIDDEN_TOKENS = ("api_secret", "secret_key", "binance_secret", "private_key", "raw_activation_token")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_micro_live_policy(username: str = DRILL_USERNAME) -> dict[str, Any]:
    return {
        "username": username,
        "lane": "MICRO_LIVE_LOCKED",
        "real_submit_default": False,
        "real_close_default": False,
        "emergency_close_default": False,
        "auto_scale": False,
        "auto_apply": False,
        "auto_close": False,
        "max_notional_usdt": MAX_MICRO_LIVE_NOTIONAL_USDT,
        "max_total_open_notional_usdt": MAX_MICRO_LIVE_NOTIONAL_USDT,
        "max_loss_usdt": MAX_MICRO_LIVE_LOSS_USDT,
        "max_loss_pct": MAX_MICRO_LIVE_LOSS_PCT,
        "allowed_symbols": list(ALLOWED_SYMBOLS),
        "allowed_strategies": list(ALLOWED_STRATEGIES),
        "owner_approval_required": True,
        "activation_token_required": True,
        "activation_token_returned": False,
        "paper_evidence_required": True,
        "read_only_preflight_required": True,
    }


def _activation_gate_preview(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_id": "REV1004-MICRO-LIVE-OWNER-ACTIVATION-GATE",
        "approval_actor": "owner",
        "approval_required": policy["owner_approval_required"],
        "activation_token_required": policy["activation_token_required"],
        "activation_token_value_returned": False,
        "real_submit_enabled": False,
        "real_close_enabled": False,
        "auto_apply_enabled": False,
        "ready_to_submit_real_order": False,
        "allowed_action_before_owner_approval": "ORDER_PREVIEW_ONLY",
    }


def _leak_scan(payload: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    leaks = [token for token in FORBIDDEN_TOKENS if token in serialized]
    return {"status": "PASS" if not leaks else "FAIL", "forbidden_tokens_found": leaks}


def build_rev1001_first_micro_live_max_notional_final_limit(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_micro_live_policy(username)
    blockers: list[str] = []
    if policy["max_notional_usdt"] <= 0:
        blockers.append("micro_live_max_notional_missing")
    if policy["max_notional_usdt"] > 10:
        blockers.append("micro_live_max_notional_above_safe_cap")
    if policy["max_total_open_notional_usdt"] > policy["max_notional_usdt"]:
        blockers.append("total_open_notional_exceeds_single_micro_cap")
    return {
        "revision": 1001,
        "name": "first_micro_live_max_notional_final_limit",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "max_notional_usdt": policy["max_notional_usdt"],
        "max_total_open_notional_usdt": policy["max_total_open_notional_usdt"],
        "policy_state": "LOCKED" if not blockers else "REVIEW",
        "real_order_submit_triggered": False,
        "real_order_close_triggered": False,
        "binance_network_call_triggered": False,
    }


def build_rev1002_first_micro_live_max_loss_final_limit(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_micro_live_policy(username)
    blockers: list[str] = []
    if policy["max_loss_usdt"] <= 0:
        blockers.append("micro_live_max_loss_missing")
    if policy["max_loss_usdt"] > 1:
        blockers.append("micro_live_max_loss_above_safe_cap")
    if policy["max_loss_pct"] > 0.5:
        blockers.append("micro_live_max_loss_pct_above_safe_cap")
    return {
        "revision": 1002,
        "name": "first_micro_live_max_loss_final_limit",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "max_loss_usdt": policy["max_loss_usdt"],
        "max_loss_pct": policy["max_loss_pct"],
        "loss_guard_state": "LOCKED" if not blockers else "REVIEW",
        "emergency_close_triggered": False,
        "real_order_submit_triggered": False,
        "binance_network_call_triggered": False,
    }


def build_rev1003_allowed_symbol_whitelist_final_lock(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_micro_live_policy(username)
    symbols = policy["allowed_symbols"]
    strategies = policy["allowed_strategies"]
    blockers: list[str] = []
    if not symbols:
        blockers.append("micro_live_symbol_whitelist_missing")
    if any(symbol in {"*", "ALL", "ANY"} for symbol in symbols):
        blockers.append("wildcard_symbol_not_allowed")
    if any(not str(symbol).endswith("USDT") for symbol in symbols):
        blockers.append("non_usdt_symbol_not_allowed_for_first_micro_live")
    if not strategies:
        blockers.append("micro_live_strategy_whitelist_missing")
    return {
        "revision": 1003,
        "name": "allowed_symbol_whitelist_final_lock",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "allowed_symbols": symbols,
        "allowed_strategies": strategies,
        "whitelist_state": "LOCKED" if not blockers else "REVIEW",
        "wildcard_allowed": False,
        "auto_scale": policy["auto_scale"],
        "auto_apply": policy["auto_apply"],
        "real_order_submit_triggered": False,
    }


def build_rev1004_owner_approval_activation_token_final_gate(username: str = DRILL_USERNAME) -> dict[str, Any]:
    policy = _safe_micro_live_policy(username)
    gate = _activation_gate_preview(policy)
    blockers: list[str] = []
    if gate["approval_required"] is not True:
        blockers.append("owner_approval_not_required")
    if gate["activation_token_required"] is not True:
        blockers.append("activation_token_not_required")
    if gate["activation_token_value_returned"] is not False:
        blockers.append("activation_token_value_leak")
    if gate["ready_to_submit_real_order"] is not False:
        blockers.append("real_submit_ready_without_owner_activation")
    return {
        "revision": 1004,
        "name": "owner_approval_activation_token_final_gate",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "activation_gate": gate,
        "owner_approval_required": True,
        "activation_token_required": True,
        "activation_token_returned": False,
        "real_submit_enabled": False,
        "real_close_enabled": False,
        "auto_close": policy["auto_close"],
    }


def build_micro_live_permission_final_gate_report(username: str = DRILL_USERNAME) -> dict[str, Any]:
    generated_at = now_iso()
    checks = {
        "rev1001_max_notional_final_limit": build_rev1001_first_micro_live_max_notional_final_limit(username),
        "rev1002_max_loss_final_limit": build_rev1002_first_micro_live_max_loss_final_limit(username),
        "rev1003_whitelist_final_lock": build_rev1003_allowed_symbol_whitelist_final_lock(username),
        "rev1004_owner_approval_activation_token_gate": build_rev1004_owner_approval_activation_token_final_gate(username),
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
        "auto_apply": False,
        "auto_close": False,
        "owner_approval_required": True,
        "activation_token_required": True,
        "activation_token_returned": False,
    }
    report = {
        "status": "ok" if not blockers else "blocked",
        "revision": 1005,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "generated_at": generated_at,
        "final_decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "safety_scope": safety_scope,
        "micro_live_policy": _safe_micro_live_policy(username),
        "secret_values_returned": False,
        "operator_next_steps": [
            "Run Rev1005 gate on VPS before enabling any real micro-live preview.",
            "Keep real submit/close defaults OFF until explicit owner approval and activation token are supplied.",
            "Use only locked symbols, locked notional and locked max-loss caps for first supervised micro-live trial.",
        ],
    }
    report["leak_scan"] = _leak_scan(report)
    if report["leak_scan"]["status"] != "PASS":
        report["status"] = "blocked"
        report["final_decision"] = "BLOCKED"
        report["blockers"].append("forbidden_secret_token_leak_detected")
    return report


def build_micro_live_permission_final_gate_summary(username: str = DRILL_USERNAME) -> dict[str, Any]:
    report = build_micro_live_permission_final_gate_report(username)
    policy = report["micro_live_policy"]
    return {
        "status": report["status"],
        "revision": report["revision"],
        "final_decision": report["final_decision"],
        "blocker_count": len(report["blockers"]),
        "max_notional_usdt": policy["max_notional_usdt"],
        "max_loss_usdt": policy["max_loss_usdt"],
        "allowed_symbols": policy["allowed_symbols"],
        "owner_approval_required": True,
        "activation_token_required": True,
        "real_order_submit_triggered": False,
        "secret_values_returned": False,
    }
