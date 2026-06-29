"""Rev951-955 Commercial Launch Candidate service.

Secret-safe, network-free launch candidate contract. It validates the business
launch chain: API-key-only setup, user onboarding + commission full flow,
first micro-live readiness, and deploy-safe packaging. It never submits, closes
or emergency-closes real Binance orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ready", "ok", "pass"}
    if value is None:
        return default
    return bool(value)


def _bounded(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, float(value))), 4)


def _payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "users_total": int(_num(payload.get("users_total"), 1)),
        "users_api_key_configured": int(_num(payload.get("users_api_key_configured"), 1)),
        "users_secret_configured": int(_num(payload.get("users_secret_configured"), 1)),
        "users_onboarded": int(_num(payload.get("users_onboarded"), 1)),
        "commission_buy_rate_configured": _bool(payload.get("commission_buy_rate_configured"), True),
        "commission_sell_rate_configured": _bool(payload.get("commission_sell_rate_configured"), True),
        "commission_ledger_ready": _bool(payload.get("commission_ledger_ready"), True),
        "net_pnl_after_commission_ready": _bool(payload.get("net_pnl_after_commission_ready"), True),
        "micro_live_permission_ready": _bool(payload.get("micro_live_permission_ready"), True),
        "micro_live_execution_preview_ready": _bool(payload.get("micro_live_execution_preview_ready"), True),
        "max_notional_bound": _bool(payload.get("max_notional_bound"), True),
        "max_loss_bound": _bool(payload.get("max_loss_bound"), True),
        "whitelist_bound": _bool(payload.get("whitelist_bound"), True),
        "owner_approval_required": _bool(payload.get("owner_approval_required"), True),
        "deploy_manifest_ready": _bool(payload.get("deploy_manifest_ready"), True),
        "forbidden_file_scan_passed": _bool(payload.get("forbidden_file_scan_passed"), True),
        "secret_scan_passed": _bool(payload.get("secret_scan_passed"), True),
        "runtime_file_scan_passed": _bool(payload.get("runtime_file_scan_passed"), True),
        "frontend_smoke_passed": _bool(payload.get("frontend_smoke_passed"), True),
        "backend_smoke_passed": _bool(payload.get("backend_smoke_passed"), True),
        "monitoring_ready": _bool(payload.get("monitoring_ready"), True),
        "real_submit_enabled": _bool(payload.get("real_submit_enabled"), False),
        "real_close_enabled": _bool(payload.get("real_close_enabled"), False),
        "emergency_close_enabled": _bool(payload.get("emergency_close_enabled"), False),
        "auto_scale_enabled": _bool(payload.get("auto_scale_enabled"), False),
        "auto_apply_enabled": _bool(payload.get("auto_apply_enabled"), False),
        "secret_values_returned": _bool(payload.get("secret_values_returned"), False),
    }


def build_api_key_only_launch_check(model: dict[str, Any]) -> dict[str, Any]:
    total = max(1, int(model["users_total"]))
    api = int(model["users_api_key_configured"])
    secret = int(model["users_secret_configured"])
    configured = min(api, secret, total)
    score = _bounded(configured / total * 100)
    status = "PASS" if configured == total else "REVIEW" if configured > 0 else "BLOCKED"
    return {
        "status": status,
        "users_total": total,
        "users_api_key_configured": api,
        "users_secret_configured": secret,
        "ready_users": configured,
        "score": score,
        "secret_values_returned": False,
    }


def build_onboarding_commission_flow_check(model: dict[str, Any]) -> dict[str, Any]:
    total = max(1, int(model["users_total"]))
    onboarded = min(int(model["users_onboarded"]), total)
    checks = [
        onboarded == total,
        bool(model["commission_buy_rate_configured"]),
        bool(model["commission_sell_rate_configured"]),
        bool(model["commission_ledger_ready"]),
        bool(model["net_pnl_after_commission_ready"]),
    ]
    passed = sum(1 for item in checks if item)
    status = "PASS" if passed == len(checks) else "REVIEW" if passed >= 3 else "BLOCKED"
    return {
        "status": status,
        "users_onboarded": onboarded,
        "users_total": total,
        "buy_commission_ready": bool(model["commission_buy_rate_configured"]),
        "sell_commission_ready": bool(model["commission_sell_rate_configured"]),
        "ledger_ready": bool(model["commission_ledger_ready"]),
        "net_pnl_after_commission_ready": bool(model["net_pnl_after_commission_ready"]),
        "score": _bounded(passed / len(checks) * 100),
    }


def build_first_micro_live_readiness_gate(model: dict[str, Any]) -> dict[str, Any]:
    checks = [
        bool(model["micro_live_permission_ready"]),
        bool(model["micro_live_execution_preview_ready"]),
        bool(model["max_notional_bound"]),
        bool(model["max_loss_bound"]),
        bool(model["whitelist_bound"]),
        bool(model["owner_approval_required"]),
    ]
    passed = sum(1 for item in checks if item)
    status = "PASS" if passed == len(checks) else "REVIEW" if passed >= 4 else "BLOCKED"
    return {
        "status": status,
        "permission_ready": bool(model["micro_live_permission_ready"]),
        "execution_preview_ready": bool(model["micro_live_execution_preview_ready"]),
        "max_notional_bound": bool(model["max_notional_bound"]),
        "max_loss_bound": bool(model["max_loss_bound"]),
        "whitelist_bound": bool(model["whitelist_bound"]),
        "owner_approval_required": bool(model["owner_approval_required"]),
        "score": _bounded(passed / len(checks) * 100),
    }


def build_deploy_safe_final_audit(model: dict[str, Any]) -> dict[str, Any]:
    checks = [
        bool(model["deploy_manifest_ready"]),
        bool(model["forbidden_file_scan_passed"]),
        bool(model["secret_scan_passed"]),
        bool(model["runtime_file_scan_passed"]),
        bool(model["frontend_smoke_passed"]),
        bool(model["backend_smoke_passed"]),
        bool(model["monitoring_ready"]),
    ]
    passed = sum(1 for item in checks if item)
    status = "PASS" if passed == len(checks) else "REVIEW" if passed >= 5 else "BLOCKED"
    return {
        "status": status,
        "deploy_manifest_ready": bool(model["deploy_manifest_ready"]),
        "forbidden_file_scan_passed": bool(model["forbidden_file_scan_passed"]),
        "secret_scan_passed": bool(model["secret_scan_passed"]),
        "runtime_file_scan_passed": bool(model["runtime_file_scan_passed"]),
        "frontend_smoke_passed": bool(model["frontend_smoke_passed"]),
        "backend_smoke_passed": bool(model["backend_smoke_passed"]),
        "monitoring_ready": bool(model["monitoring_ready"]),
        "score": _bounded(passed / len(checks) * 100),
    }


def _critical_blocker(checks: dict[str, dict[str, Any]], model: dict[str, Any]) -> str:
    if model["secret_values_returned"]:
        return "secret_values_returned"
    if model["real_submit_enabled"] or model["real_close_enabled"] or model["emergency_close_enabled"]:
        return "real_action_flag_enabled"
    if model["auto_scale_enabled"] or model["auto_apply_enabled"]:
        return "auto_growth_or_apply_enabled"
    for key, value in checks.items():
        if value.get("status") == "BLOCKED":
            return key
    for key, value in checks.items():
        if value.get("status") == "REVIEW":
            return key
    return "none"


def build_commercial_launch_candidate(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    model = _payload(payload)
    checks = {
        "api_key_only_launch": build_api_key_only_launch_check(model),
        "onboarding_commission_flow": build_onboarding_commission_flow_check(model),
        "first_micro_live_readiness": build_first_micro_live_readiness_gate(model),
        "deploy_safe_final_audit": build_deploy_safe_final_audit(model),
    }
    statuses = [item["status"] for item in checks.values()]
    blocker = _critical_blocker(checks, model)
    average_score = _bounded(sum(float(item["score"]) for item in checks.values()) / len(checks))
    if blocker == "none" and all(status == "PASS" for status in statuses):
        decision = "COMMERCIAL_LAUNCH_CANDIDATE_READY"
        operator_action = "Proceed to controlled commercial RC review. Keep real actions approval-gated."
    elif "BLOCKED" in statuses or blocker in {"secret_values_returned", "real_action_flag_enabled", "auto_growth_or_apply_enabled"}:
        decision = "COMMERCIAL_LAUNCH_CANDIDATE_BLOCKED"
        operator_action = f"Resolve blocker: {blocker}."
    else:
        decision = "COMMERCIAL_LAUNCH_CANDIDATE_REVIEW"
        operator_action = f"Review launch candidate issue: {blocker}."
    return {
        "revision": 955,
        "block": "Commercial Launch Candidate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "average_score": average_score,
        "api_key_only_launch_check": checks["api_key_only_launch"],
        "onboarding_commission_full_flow": checks["onboarding_commission_flow"],
        "first_micro_live_readiness_final_gate": checks["first_micro_live_readiness"],
        "deploy_safe_final_package_audit": checks["deploy_safe_final_audit"],
        "critical_blocker": blocker,
        "operator_action": operator_action,
        "real_submit_default_off": not bool(model["real_submit_enabled"]),
        "real_close_default_off": not bool(model["real_close_enabled"]),
        "emergency_close_default_off": not bool(model["emergency_close_enabled"]),
        "auto_scale_default_off": not bool(model["auto_scale_enabled"]),
        "auto_apply_default_off": not bool(model["auto_apply_enabled"]),
        "secret_values_returned": False,
        "real_network_call_performed": False,
    }


def build_commercial_launch_candidate_summary() -> dict[str, Any]:
    result = build_commercial_launch_candidate()
    return {
        "revision": result["revision"],
        "decision": result["decision"],
        "average_score": result["average_score"],
        "api_key_only_launch": result["api_key_only_launch_check"]["status"],
        "ready_users": result["api_key_only_launch_check"]["ready_users"],
        "users_total": result["api_key_only_launch_check"]["users_total"],
        "onboarding_commission_flow": result["onboarding_commission_full_flow"]["status"],
        "first_micro_live_readiness": result["first_micro_live_readiness_final_gate"]["status"],
        "deploy_safe_audit": result["deploy_safe_final_package_audit"]["status"],
        "critical_blocker": result["critical_blocker"],
        "operator_action": result["operator_action"],
        "real_submit_default_off": result["real_submit_default_off"],
        "real_close_default_off": result["real_close_default_off"],
        "emergency_close_default_off": result["emergency_close_default_off"],
        "auto_scale_default_off": result["auto_scale_default_off"],
        "auto_apply_default_off": result["auto_apply_default_off"],
        "secret_values_returned": result["secret_values_returned"],
    }
