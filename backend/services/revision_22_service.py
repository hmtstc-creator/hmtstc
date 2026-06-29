from __future__ import annotations

from services.real_pilot_service import build_pilot_report, pilot_config, pilot_readiness
from services.real_trade_state_service import ensure_real_trade_state, open_real_positions
from services.real_trade_service import build_real_readiness


def _status_from_issues(issues: list[str], warnings: list[str] | None = None) -> str:
    if issues:
        return "blocked"
    if warnings:
        return "review"
    return "ok"


def build_micro_pilot_config_quality(data: dict, settings: dict) -> dict:
    cfg = pilot_config()
    issues = []
    warnings = []
    if cfg.get("max_order_usdt", 0) > 10:
        warnings.append("pilot_max_order_above_micro_recommendation")
    if cfg.get("max_open_positions", 0) > 1:
        warnings.append("pilot_open_position_limit_above_micro_recommendation")
    if cfg.get("max_daily_trades", 0) > 3:
        warnings.append("pilot_daily_trade_limit_above_micro_recommendation")
    if cfg.get("daily_loss_limit_usdt", 0) > 2:
        warnings.append("pilot_daily_loss_limit_above_micro_recommendation")
    if not cfg.get("allowed_symbols"):
        issues.append("pilot_allowed_symbols_missing")
    return {"status": _status_from_issues(issues, warnings), "config": cfg, "issues": issues, "warnings": warnings}


def build_micro_pilot_lifecycle_quality(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    pilot = state.get("pilot") or {}
    issues = []
    warnings = []
    if pilot.get("active") and not pilot.get("expires_at"):
        issues.append("active_pilot_missing_expiry")
    if pilot.get("active") and not state.get("owner_unlocked"):
        issues.append("active_pilot_without_owner_unlock")
    if not pilot.get("locked_after_finish", True):
        issues.append("pilot_not_configured_to_lock_after_finish")
    if pilot.get("active") and state.get("emergency_lock"):
        issues.append("pilot_active_during_emergency_lock")
    if not pilot.get("status"):
        warnings.append("pilot_status_not_initialized")
    return {"status": _status_from_issues(issues, warnings), "pilot": pilot, "open_real_positions": len(open_real_positions(state)), "issues": issues, "warnings": warnings}


def build_micro_pilot_safety_quality(data: dict, settings: dict) -> dict:
    readiness = pilot_readiness(data, settings)
    real_readiness = build_real_readiness(data, settings)
    blockers = list(readiness.get("blockers") or [])
    warnings = list(readiness.get("warnings") or [])
    # Safety is OK when it is either ready or safely blocked for explicit reasons.
    safety_ok = bool(blockers) or readiness.get("status") == "ready"
    status = "ok" if safety_ok else "blocked"
    return {"status": status, "pilot_readiness": readiness, "real_readiness_status": real_readiness.get("status"), "blockers": blockers, "warnings": warnings}


def build_micro_pilot_report_quality(data: dict, settings: dict) -> dict:
    report = build_pilot_report(data, settings)
    issues = []
    warnings = []
    if not isinstance(report.get("last_orders"), list):
        issues.append("pilot_report_missing_order_list")
    if "readiness" not in report:
        issues.append("pilot_report_missing_readiness")
    if report.get("status") == "active" and not (report.get("pilot") or {}).get("expires_at"):
        issues.append("active_pilot_report_missing_expiry")
    return {"status": _status_from_issues(issues, warnings), "report": report, "issues": issues, "warnings": warnings}


def build_pilot_ui_contract(data: dict, settings: dict) -> dict:
    required = [
        "pilot_status", "pilot_readiness", "pilot_config", "pilot_start", "pilot_stop", "pilot_report",
        "max_order_usdt", "max_open_positions", "daily_loss_limit_usdt", "allowed_symbols", "expires_at",
    ]
    # This is a contract report; frontend quality script checks concrete JS strings.
    return {"status": "ok", "required_ui_concepts": required, "message": "Dashboard/Positions real trade panels must show micro pilot state, limits, readiness and report."}


def build_revision_22_quality_report(data: dict, settings: dict) -> dict:
    sections = {
        "pilot_config": build_micro_pilot_config_quality(data, settings),
        "pilot_lifecycle": build_micro_pilot_lifecycle_quality(data, settings),
        "pilot_safety": build_micro_pilot_safety_quality(data, settings),
        "pilot_report": build_micro_pilot_report_quality(data, settings),
        "pilot_ui": build_pilot_ui_contract(data, settings),
    }
    blockers = []
    reviews = []
    for name, section in sections.items():
        if section.get("status") == "blocked":
            blockers.append(name)
        elif section.get("status") == "review":
            reviews.append(name)
    return {
        "revision": 22,
        "status": "blocked" if blockers else ("review" if reviews else "ok"),
        "title": "Rev22 Micro Pilot Control Quality Gate",
        "sections": sections,
        "blockers": blockers,
        "reviews": reviews,
    }
