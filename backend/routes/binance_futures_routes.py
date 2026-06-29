from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_owner, require_user
from core.config import DEFAULT_USER
from core.storage import load_shadow, load_settings
from services.binance_futures_connection_service import (
    clear_futures_credentials,
    get_futures_connection_summary,
    set_futures_credentials,
)
from services.binance_futures_permission_service import (
    get_user_futures_permission,
    list_futures_permissions,
    set_user_futures_permission,
)
from services.binance_futures_readiness_service import build_futures_readiness
from services.binance_futures_risk_service import build_futures_risk_settings
from services.binance_futures_karabasan_service import build_karabasan_futures_score
from services.binance_futures_order_service import build_futures_order_preview
from services.binance_futures_position_service import build_futures_position_snapshot
from services.binance_futures_lifecycle_service import build_futures_lifecycle
from services.binance_futures_ledger_service import build_futures_ledger
from services.binance_futures_commission_service import build_futures_commission_income
from services.binance_futures_models import public_permission

router = APIRouter(prefix="/api/futures", tags=["binance-futures"])


def current_username(current_user: dict) -> str:
    return str(current_user.get("username") or DEFAULT_USER).strip() or DEFAULT_USER


def is_owner(current_user: dict) -> bool:
    return str(current_user.get("role") or "user").lower() == "owner"


@router.get("/dashboard")
def futures_dashboard(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    owner = is_owner(current_user)
    permission = get_user_futures_permission(user)
    connection = get_futures_connection_summary(user)
    runtime = load_shadow(user)
    settings = load_settings(user)
    visible = bool(permission.get("futures_enabled")) or owner
    if not visible:
        return {"service": "binance_futures_dashboard", "visible": False, "vip_area": True, "status": "hidden_until_owner_enables"}
    return {
        "service": "binance_futures_dashboard",
        "visible": True,
        "vip_area": True,
        "spot_separated": True,
        "permission": public_permission(permission, is_owner=owner),
        "connection": connection,
        "readiness": build_futures_readiness(user, permission, connection),
        "karabasan_futures": build_karabasan_futures_score(runtime, settings, permission, connection),
        "positions": build_futures_position_snapshot(runtime),
        "lifecycle": build_futures_lifecycle(runtime),
        "ledger": build_futures_ledger(runtime, permission, owner_view=owner),
        "commission": build_futures_commission_income(runtime, permission) if owner else {"owner_only": True, "hidden_for_user": True},
    }


@router.get("/connection")
def futures_connection(current_user: dict = Depends(require_user)):
    return get_futures_connection_summary(current_username(current_user))


@router.post("/connection")
def futures_connection_update(payload: dict, current_user: dict = Depends(require_user)):
    return set_futures_credentials(current_username(current_user), payload or {})


@router.delete("/connection")
def futures_connection_clear(current_user: dict = Depends(require_user)):
    return clear_futures_credentials(current_username(current_user))


@router.get("/readiness")
def futures_readiness(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_futures_readiness(user, get_user_futures_permission(user), get_futures_connection_summary(user))


@router.get("/risk-settings")
def futures_risk_settings(current_user: dict = Depends(require_user)):
    return build_futures_risk_settings(get_user_futures_permission(current_username(current_user)))


@router.post("/karabasan-score")
def futures_karabasan_score(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_futures_score(load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or None)


@router.post("/dry-run-order")
def futures_dry_run_order(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_futures_order_preview(load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


@router.get("/positions")
def futures_positions(current_user: dict = Depends(require_user)):
    return build_futures_position_snapshot(load_shadow(current_username(current_user)))


@router.get("/lifecycle")
def futures_lifecycle(current_user: dict = Depends(require_user)):
    return build_futures_lifecycle(load_shadow(current_username(current_user)))


@router.get("/ledger")
def futures_ledger(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_futures_ledger(load_shadow(user), get_user_futures_permission(user), owner_view=is_owner(current_user))


@router.get("/admin/users")
def futures_admin_users(current_user: dict = Depends(require_owner)):
    return list_futures_permissions()


@router.post("/admin/users/{username}/permission")
def futures_admin_update_user(username: str, payload: dict, current_user: dict = Depends(require_owner)):
    try:
        return {"status": "ok", "user": set_user_futures_permission(username, payload or {})}
    except KeyError:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

# G1_PRODUCTION_LIVE_GATE
from services.binance_futures_production_gate_service import build_production_live_gate

@router.post("/production-live-gate")
def futures_production_live_gate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_production_live_gate(load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

# G2_POSITION_MODE_POLICY
from services.binance_futures_position_mode_service import build_position_mode_policy

@router.post("/position-mode-policy")
def futures_position_mode_policy(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_position_mode_policy(get_user_futures_permission(user), (payload or {}).get("requested_mode"))

# G3_SHORT_SCORE
from services.karabasan_futures_short_score_service import build_karabasan_futures_short_score

@router.post("/short-score")
def futures_short_score(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_futures_short_score(get_user_futures_permission(user), payload or {})

# G4_AUTO_ADVISOR
from services.futures_auto_mode_advisor_service import build_futures_auto_mode_advice

@router.post("/auto-mode-advice")
def futures_auto_mode_advice(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_futures_auto_mode_advice(load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

# G5_LIVE_POSITION_MONITOR
from services.binance_futures_live_position_monitor_service import build_live_position_monitor

@router.get("/live-position-monitor")
def futures_live_position_monitor(current_user: dict = Depends(require_user)):
    return build_live_position_monitor(load_shadow(current_username(current_user)))

# G6_AUTO_CLOSE
from services.binance_futures_auto_close_service import build_auto_close_decision

@router.post("/auto-close-decision")
def futures_auto_close_decision(payload: dict | None = None, current_user: dict = Depends(require_user)):
    payload = payload or {}
    return build_auto_close_decision(payload.get("position") or {}, payload.get("context") or {})

# G7_REPORTING
from services.futures_reporting_service import build_futures_performance_report

@router.get("/reporting")
def futures_reporting(current_user: dict = Depends(require_user)):
    return build_futures_performance_report(load_shadow(current_username(current_user)), owner_view=is_owner(current_user))

# G8_OWNER_FINANCE
from services.owner_finance_service import build_owner_finance_panel

@router.get("/admin/owner-finance")
def futures_owner_finance(current_user: dict = Depends(require_owner)):
    return build_owner_finance_panel(load_shadow(DEFAULT_USER))

# G9_ACCESS_CONTROL
from services.futures_access_control_service import build_futures_access_control

@router.get("/access-control")
def futures_access_control(current_user: dict = Depends(require_user)):
    return build_futures_access_control(get_user_futures_permission(current_username(current_user)))

# G10_ALARMS
from services.futures_alarm_service import build_futures_alarms

@router.post("/alarms")
def futures_alarms(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_futures_alarms(load_shadow(current_username(current_user)), payload or {})

# G11_EVIDENCE
from services.futures_evidence_service import build_futures_evidence

@router.post("/evidence")
def futures_evidence(payload: dict, current_user: dict = Depends(require_user)):
    return build_futures_evidence(payload or {})

# G12_UI_DESCRIPTOR
from services.futures_ui_descriptor_service import build_futures_ui_descriptor

@router.get("/ui-descriptor")
def futures_ui_descriptor(current_user: dict = Depends(require_user)):
    return build_futures_ui_descriptor(is_owner=is_owner(current_user))

# G13_MOBILE_SAFETY
from services.futures_mobile_safety_service import build_mobile_safety_contract

@router.post("/mobile-safety")
def futures_mobile_safety(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_mobile_safety_contract((payload or {}).get("action"))

# G14_PRODUCTION_HARDENING
from services.production_health_service import build_production_health
from services.binance_rate_limit_service import build_rate_limit_policy
from services.bot_state_recovery_service import build_bot_state_recovery_plan
from services.secret_safety_audit_service import build_secret_safety_audit

@router.get("/production-hardening")
def futures_production_hardening(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    runtime = load_shadow(user)
    connection = get_futures_connection_summary(user)
    return {
        "service": "futures_production_hardening",
        "production_health": build_production_health(runtime, connection),
        "rate_limit_policy": build_rate_limit_policy(),
        "bot_state_recovery": build_bot_state_recovery_plan(runtime),
        "secret_safety_audit": build_secret_safety_audit({}),
        "real_mainnet_requires_hardening_ok": True,
    }


# PHASE1_REAL_FUTURES_PRE_RENTAL_GATE
from services.futures_phase1_live_gate_service import build_phase1_real_futures_live_gate
from services.futures_phase1_owner_permission_service import build_owner_permission_plan
from services.futures_phase1_user_control_service import build_user_futures_control_contract
from services.futures_phase1_karabasan_bridge_service import build_futures_karabasan_execution_bridge
from services.futures_phase1_order_preview_service import build_phase1_order_preview
from services.futures_phase1_tpsl_guard_service import build_tpsl_guard
from services.futures_phase1_liquidation_engine_service import build_liquidation_risk_engine
from services.futures_phase1_final_gate_service import build_phase1_real_futures_final_gate

@router.post("/phase1/live-gate")
def futures_phase1_live_gate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase1_real_futures_live_gate(load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

@router.get("/admin/phase1/users/{username}/permission-plan")
def futures_phase1_owner_permission_plan(username: str, current_user: dict = Depends(require_owner)):
    return build_owner_permission_plan(username, get_user_futures_permission(username))

@router.post("/phase1/user-control")
def futures_phase1_user_control(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = payload or {}
    return build_user_futures_control_contract(get_user_futures_permission(user), payload.get("mode"))

@router.post("/phase1/karabasan-bridge")
def futures_phase1_karabasan_bridge(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_futures_karabasan_execution_bridge(load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

@router.post("/phase1/order-preview")
def futures_phase1_order_preview(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase1_order_preview(load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

@router.post("/phase1/tpsl-guard")
def futures_phase1_tpsl_guard(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_tpsl_guard(get_user_futures_permission(user), payload or {})

@router.post("/phase1/liquidation-risk")
def futures_phase1_liquidation_risk(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_liquidation_risk_engine(get_user_futures_permission(user), payload or {})

@router.post("/phase1/final-gate")
def futures_phase1_final_gate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase1_real_futures_final_gate(user, load_shadow(user), load_settings(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

# PHASE2_LIVE_USE_PREPARATION
from services.futures_phase2_funding_control_service import build_phase2_funding_control

@router.post("/phase2/funding-control")
def futures_phase2_funding_control(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = payload or {}
    return build_phase2_funding_control(get_user_futures_permission(user), payload.get("market") or payload)

from services.futures_phase2_live_position_service import build_phase2_live_position_monitor

@router.post("/phase2/live-position-monitor")
def futures_phase2_live_position_monitor(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase2_live_position_monitor(load_shadow(user), get_user_futures_permission(user), payload or {})

from services.futures_phase2_auto_close_gate_service import build_phase2_auto_close_gate

@router.post("/phase2/auto-close-gate")
def futures_phase2_auto_close_gate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase2_auto_close_gate(load_shadow(user), get_user_futures_permission(user), payload or {})

from services.futures_phase2_alarm_service import build_phase2_alarm_center

@router.post("/phase2/alarm-center")
def futures_phase2_alarm_center(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase2_alarm_center(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

from services.futures_phase2_evidence_gate_service import build_phase2_evidence_record, build_phase2_final_gate

@router.post("/phase2/evidence")
def futures_phase2_evidence(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase2_evidence_record(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

@router.post("/phase2/final-gate")
def futures_phase2_final_gate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase2_final_gate(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# PHASE3_1_USER_FUTURES_EXPERIENCE
from services.futures_phase3_user_experience_service import build_phase3_user_futures_experience

@router.post("/phase3/user-experience")
def futures_phase3_user_experience(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase3_user_futures_experience(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})

# PHASE3_2_ADMIN_OPERATIONS
from services.futures_phase3_admin_ops_service import build_phase3_admin_operations_panel

@router.post("/phase3/admin-operations")
def futures_phase3_admin_operations(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    payload = payload or {}
    username = str(payload.get("username") or DEFAULT_USER)
    return build_phase3_admin_operations_panel(username, load_shadow(username), get_user_futures_permission(username), get_futures_connection_summary(username), payload)

# PHASE3_3_RENTAL_FINANCE
from services.futures_phase3_rental_finance_service import build_phase3_rental_finance_link

@router.post("/phase3/rental-finance")
def futures_phase3_rental_finance(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase3_rental_finance_link(load_shadow(user), get_user_futures_permission(user), payload or {}, owner_view=is_owner(current_user))

# PHASE3_4_MOBILE_EXPERIENCE
from services.futures_phase3_mobile_experience_service import build_phase3_mobile_futures_experience

@router.post("/phase3/mobile-experience")
def futures_phase3_mobile_experience(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase3_mobile_futures_experience(get_user_futures_permission(user), payload or {})

# PHASE3_5_PRODUCTION_SAFETY_FINAL
from services.futures_phase3_production_safety_service import build_phase3_production_safety_final

@router.post("/phase3/final-gate")
def futures_phase3_final_gate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_phase3_production_safety_final(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H1_RENTAL_READY_PACKAGE
from services.futures_h1_deploy_environment_service import build_h1_deploy_environment_readiness

@router.post("/phaseH/deploy-environment")
def futures_phaseH_deploy_environment(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h1_deploy_environment_readiness(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H2_RENTAL_READY_PACKAGE
from services.futures_h2_mainnet_readonly_pilot_service import build_h2_mainnet_readonly_pilot

@router.post("/phaseH/mainnet-readonly-pilot")
def futures_phaseH_mainnet_readonly_pilot(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h2_mainnet_readonly_pilot(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H3_RENTAL_READY_PACKAGE
from services.futures_h3_testnet_e2e_service import build_h3_testnet_e2e_scenario

@router.post("/phaseH/testnet-e2e")
def futures_phaseH_testnet_e2e(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h3_testnet_e2e_scenario(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H4_RENTAL_READY_PACKAGE
from services.futures_h4_owner_mainnet_mini_pilot_service import build_h4_owner_mainnet_mini_pilot_plan

@router.post("/phaseH/owner-mini-pilot")
def futures_phaseH_owner_mini_pilot(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h4_owner_mainnet_mini_pilot_plan(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H5_RENTAL_READY_PACKAGE
from services.futures_h5_user_rental_ui_final_service import build_h5_user_rental_ui_final

@router.post("/phaseH/user-rental-ui")
def futures_phaseH_user_rental_ui(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h5_user_rental_ui_final(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H6_RENTAL_READY_PACKAGE
from services.futures_h6_admin_ops_center_service import build_h6_admin_ops_center

@router.post("/phaseH/admin-ops-center")
def futures_phaseH_admin_ops_center(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h6_admin_ops_center(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H7_RENTAL_READY_PACKAGE
from services.futures_h7_finance_collection_final_service import build_h7_finance_collection_final

@router.post("/phaseH/finance-collection-final")
def futures_phaseH_finance_collection_final(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h7_finance_collection_final(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H8_RENTAL_READY_PACKAGE
from services.futures_h8_onboarding_guide_service import build_h8_onboarding_guide

@router.post("/phaseH/onboarding-guide")
def futures_phaseH_onboarding_guide(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h8_onboarding_guide(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H9_RENTAL_READY_PACKAGE
from services.futures_h9_evidence_audit_final_service import build_h9_evidence_audit_final

@router.post("/phaseH/evidence-audit-final")
def futures_phaseH_evidence_audit_final(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h9_evidence_audit_final(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})


# H10_RENTAL_READY_PACKAGE
from services.futures_h10_rental_ready_final_service import build_h10_rental_ready_final_checklist

@router.post("/phaseH/rental-ready-final")
def futures_phaseH_rental_ready_final(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_h10_rental_ready_final_checklist(load_shadow(user), get_user_futures_permission(user), get_futures_connection_summary(user), payload or {})
