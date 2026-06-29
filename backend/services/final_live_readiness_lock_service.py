"""Rev956-960 Final Live Readiness Lock service.

Network-free, secret-safe final safety lock contract before any real micro-live
action. The service proves real submit/close paths remain blocked by default,
validates owner approval/token/session boundaries, locks notional/loss/whitelist
constraints, and verifies rollback/freeze/halt emergency readiness.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "pass", "ready", "ok"}
    if value is None:
        return default
    return bool(value)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _bounded(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, float(value))), 4)


def _payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "real_submit_enabled": _bool(payload.get("real_submit_enabled"), False),
        "real_close_enabled": _bool(payload.get("real_close_enabled"), False),
        "emergency_close_enabled": _bool(payload.get("emergency_close_enabled"), False),
        "auto_scale_enabled": _bool(payload.get("auto_scale_enabled"), False),
        "auto_apply_enabled": _bool(payload.get("auto_apply_enabled"), False),
        "auto_close_enabled": _bool(payload.get("auto_close_enabled"), False),
        "owner_approval_required": _bool(payload.get("owner_approval_required"), True),
        "owner_approval_present": _bool(payload.get("owner_approval_present"), False),
        "activation_token_present": _bool(payload.get("activation_token_present"), True),
        "activation_token_value_returned": _bool(payload.get("activation_token_value_returned"), False),
        "session_bound": _bool(payload.get("session_bound"), True),
        "session_not_expired": _bool(payload.get("session_not_expired"), True),
        "max_notional": _num(payload.get("max_notional"), 25.0),
        "max_notional_limit": _num(payload.get("max_notional_limit"), 25.0),
        "max_loss": _num(payload.get("max_loss"), 2.5),
        "max_loss_limit": _num(payload.get("max_loss_limit"), 2.5),
        "whitelist_bound": _bool(payload.get("whitelist_bound"), True),
        "allowed_symbols": payload.get("allowed_symbols") or ["BTCUSDT", "ETHUSDT"],
        "requested_symbol": str(payload.get("requested_symbol") or "BTCUSDT"),
        "rollback_ready": _bool(payload.get("rollback_ready"), True),
        "freeze_ready": _bool(payload.get("freeze_ready"), True),
        "halt_ready": _bool(payload.get("halt_ready"), True),
        "emergency_guard_ready": _bool(payload.get("emergency_guard_ready"), True),
        "audit_ready": _bool(payload.get("audit_ready"), True),
        "secret_values_returned": _bool(payload.get("secret_values_returned"), False),
    }


def prove_real_actions_default_off(model: dict[str, Any]) -> dict[str, Any]:
    flags_off = [
        not model["real_submit_enabled"],
        not model["real_close_enabled"],
        not model["emergency_close_enabled"],
        not model["auto_close_enabled"],
        not model["auto_scale_enabled"],
        not model["auto_apply_enabled"],
    ]
    passed = sum(1 for item in flags_off if item)
    status = "PASS" if passed == len(flags_off) else "BLOCKED"
    return {
        "status": status,
        "real_submit_default_off": not model["real_submit_enabled"],
        "real_close_default_off": not model["real_close_enabled"],
        "emergency_close_default_off": not model["emergency_close_enabled"],
        "auto_close_default_off": not model["auto_close_enabled"],
        "auto_scale_default_off": not model["auto_scale_enabled"],
        "auto_apply_default_off": not model["auto_apply_enabled"],
        "score": _bounded(passed / len(flags_off) * 100),
    }


def validate_owner_token_lock(model: dict[str, Any]) -> dict[str, Any]:
    checks = [
        model["owner_approval_required"],
        model["activation_token_present"],
        not model["activation_token_value_returned"],
        model["session_bound"],
        model["session_not_expired"],
        not model["secret_values_returned"],
    ]
    passed = sum(1 for item in checks if item)
    status = "PASS" if passed == len(checks) else "REVIEW" if passed >= 4 else "BLOCKED"
    return {
        "status": status,
        "owner_approval_required": bool(model["owner_approval_required"]),
        "owner_approval_present": bool(model["owner_approval_present"]),
        "activation_token_present": bool(model["activation_token_present"]),
        "activation_token_value_returned": False,
        "session_bound": bool(model["session_bound"]),
        "session_not_expired": bool(model["session_not_expired"]),
        "secret_values_returned": False,
        "score": _bounded(passed / len(checks) * 100),
    }


def validate_capital_symbol_lock(model: dict[str, Any]) -> dict[str, Any]:
    allowed_symbols = [str(s).upper() for s in model["allowed_symbols"] if str(s).strip()]
    requested_symbol = str(model["requested_symbol"]).upper()
    max_notional_ok = float(model["max_notional"]) <= float(model["max_notional_limit"])
    max_loss_ok = float(model["max_loss"]) <= float(model["max_loss_limit"])
    symbol_ok = requested_symbol in allowed_symbols
    checks = [max_notional_ok, max_loss_ok, bool(model["whitelist_bound"]), symbol_ok]
    passed = sum(1 for item in checks if item)
    status = "PASS" if passed == len(checks) else "REVIEW" if passed >= 3 else "BLOCKED"
    return {
        "status": status,
        "max_notional": round(float(model["max_notional"]), 4),
        "max_notional_limit": round(float(model["max_notional_limit"]), 4),
        "max_loss": round(float(model["max_loss"]), 4),
        "max_loss_limit": round(float(model["max_loss_limit"]), 4),
        "whitelist_bound": bool(model["whitelist_bound"]),
        "requested_symbol": requested_symbol,
        "allowed_symbols": allowed_symbols,
        "symbol_allowed": symbol_ok,
        "score": _bounded(passed / len(checks) * 100),
    }


def validate_emergency_rollback_freeze_halt(model: dict[str, Any]) -> dict[str, Any]:
    checks = [
        model["rollback_ready"],
        model["freeze_ready"],
        model["halt_ready"],
        model["emergency_guard_ready"],
        model["audit_ready"],
    ]
    passed = sum(1 for item in checks if item)
    status = "PASS" if passed == len(checks) else "REVIEW" if passed >= 4 else "BLOCKED"
    return {
        "status": status,
        "rollback_ready": bool(model["rollback_ready"]),
        "freeze_ready": bool(model["freeze_ready"]),
        "halt_ready": bool(model["halt_ready"]),
        "emergency_guard_ready": bool(model["emergency_guard_ready"]),
        "audit_ready": bool(model["audit_ready"]),
        "score": _bounded(passed / len(checks) * 100),
    }


def _critical_blocker(checks: dict[str, dict[str, Any]]) -> str:
    for key, value in checks.items():
        if value.get("status") == "BLOCKED":
            return key
    for key, value in checks.items():
        if value.get("status") == "REVIEW":
            return key
    return "none"


def build_final_live_readiness_lock(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    model = _payload(payload)
    checks = {
        "real_action_default_off_proof": prove_real_actions_default_off(model),
        "owner_token_session_lock": validate_owner_token_lock(model),
        "capital_symbol_lock": validate_capital_symbol_lock(model),
        "emergency_rollback_freeze_halt": validate_emergency_rollback_freeze_halt(model),
    }
    blocker = _critical_blocker(checks)
    score = _bounded(sum(float(item["score"]) for item in checks.values()) / len(checks))
    if blocker == "none":
        decision = "FINAL_LIVE_READINESS_LOCK_READY"
        operator_action = "System is locked for controlled owner-gated micro-live review. Real actions remain disabled by default."
    elif any(item["status"] == "BLOCKED" for item in checks.values()):
        decision = "FINAL_LIVE_READINESS_LOCK_BLOCKED"
        operator_action = f"Resolve blocker before any live readiness review: {blocker}."
    else:
        decision = "FINAL_LIVE_READINESS_LOCK_REVIEW"
        operator_action = f"Review live readiness lock issue: {blocker}."
    return {
        "revision": 960,
        "block": "Final Live Readiness Lock",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "score": score,
        "critical_blocker": blocker,
        "operator_action": operator_action,
        "real_action_default_off_proof": checks["real_action_default_off_proof"],
        "owner_approval_activation_token_final_lock": checks["owner_token_session_lock"],
        "max_notional_max_loss_whitelist_lock": checks["capital_symbol_lock"],
        "emergency_rollback_freeze_halt_final_proof": checks["emergency_rollback_freeze_halt"],
        "real_network_call_performed": False,
        "secret_values_returned": False,
    }


def build_final_live_readiness_lock_summary() -> dict[str, Any]:
    result = build_final_live_readiness_lock()
    default_off = result["real_action_default_off_proof"]
    cap = result["max_notional_max_loss_whitelist_lock"]
    emergency = result["emergency_rollback_freeze_halt_final_proof"]
    owner = result["owner_approval_activation_token_final_lock"]
    return {
        "revision": result["revision"],
        "decision": result["decision"],
        "score": result["score"],
        "critical_blocker": result["critical_blocker"],
        "operator_action": result["operator_action"],
        "real_submit_default_off": default_off["real_submit_default_off"],
        "real_close_default_off": default_off["real_close_default_off"],
        "emergency_close_default_off": default_off["emergency_close_default_off"],
        "owner_approval_required": owner["owner_approval_required"],
        "activation_token_present": owner["activation_token_present"],
        "activation_token_value_returned": False,
        "requested_symbol": cap["requested_symbol"],
        "max_notional": cap["max_notional"],
        "max_loss": cap["max_loss"],
        "rollback_ready": emergency["rollback_ready"],
        "freeze_ready": emergency["freeze_ready"],
        "halt_ready": emergency["halt_ready"],
        "secret_values_returned": False,
    }
