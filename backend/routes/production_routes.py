from fastapi import APIRouter, Depends, HTTPException

from core.auth import read_auth_store, require_owner, require_user, write_auth_store
from core.config import DEFAULT_USER
from core.storage import load_settings, load_shadow
from services.final_code_reality_audit_service import (
    build_final_code_reality_audit,
    build_final_code_reality_audit_summary,
)

from services.binance_read_only_verification_service import (
    build_binance_read_only_verification,
    build_binance_read_only_verification_summary,
    build_binance_read_only_verification_quality,
)

from services.production_deploy_readiness_service import (
    build_production_deploy_readiness,
    build_production_deploy_readiness_summary,
)


from services.commission_business_flow_service import (
    build_commission_business_flow_summary,
    build_commission_ledger,
    validate_commission_business_flow,
)

from services.paper_to_live_dry_production_drill_service import (
    build_paper_to_live_dry_production_drill_summary,
    run_paper_to_live_dry_production_drill,
)

from services.first_real_micro_live_permission_service import (
    build_first_real_micro_live_permission_summary,
    evaluate_first_real_micro_live_permission,
)

from services.first_real_micro_live_execution_service import (
    build_first_real_micro_live_execution_summary,
    evaluate_first_real_micro_live_execution,
)

from services.live_freeze_repeat_decision_service import (
    build_live_freeze_repeat_decision_summary,
    evaluate_live_freeze_repeat_decision,
)

from services.continuity_repair_reconciliation_merge_service import (
    build_continuity_repair_summary,
    evaluate_continuity_repair_merge,
)

from services.production_onboarding_service import (
    apply_onboarding_to_existing_user,
    build_onboarding_quality,
    build_onboarding_summary,
    validate_onboarding_payload,
)

from services.multi_user_production_hardening_service import (
    build_multi_user_production_hardening_summary,
    evaluate_multi_user_production_hardening,
)

from services.premium_ui_final_polish_service import (
    build_premium_ui_final_polish_report,
    build_premium_ui_final_polish_summary,
)

from services.strategy_filter_live_calibration_service import (
    build_strategy_filter_live_calibration,
    build_strategy_filter_live_calibration_summary,
)

from services.high_frequency_safety_capacity_service import (
    build_high_frequency_safety_capacity,
    build_high_frequency_safety_capacity_summary,
)

from services.production_monitoring_alert_service import (
    build_production_monitoring_alert,
    build_production_monitoring_alert_summary,
)

from services.commercial_launch_candidate_service import (
    build_commercial_launch_candidate,
    build_commercial_launch_candidate_summary,
)

from services.final_live_readiness_lock_service import (
    build_final_live_readiness_lock,
    build_final_live_readiness_lock_summary,
)

from services.final_regression_clean_package_service import (
    build_final_regression_clean_package,
    build_final_regression_clean_package_summary,
)

from services.production_completion_service import (
    commission_preview,
    completion_claim,
    evaluate_filters,
    evaluate_strategy_candidates,
    high_frequency_capacity,
    launch_readiness,
    normalize_commission_settings,
    update_commission_settings,
)


from services.hmtstc_final_commercial_rc_service import (
    build_hmtstc_final_commercial_rc,
    build_hmtstc_final_commercial_rc_summary,
)

from services.final_reality_reaudit_service import (
    build_final_reality_reaudit,
    build_final_reality_reaudit_summary,
)

from services.local_github_vps_sync_service import (
    build_local_github_vps_sync_report,
    build_rev976_local_structure_check,
    build_rev977_gitignore_secret_runtime_check,
    build_rev978_github_commit_push_safe_list,
    build_rev979_vps_pull_deploy_match_check,
)

from services.production_environment_activation_service import (
    build_production_environment_activation_report,
    build_production_environment_activation_summary,
    build_rev981_backend_env_check,
    build_rev982_frontend_build_config_check,
    build_rev983_service_nginx_check,
    build_rev984_vps_dependency_permission_check,
)

from services.binance_read_only_live_check_service import (
    build_binance_read_only_live_check_report,
    build_binance_read_only_live_check_summary,
    build_rev986_api_secret_masking_check,
    build_rev987_binance_account_read_only_check,
    build_rev988_balance_read_only_check,
    build_rev989_permission_drift_trade_permission_check,
)
from services.single_user_onboarding_drill_service import (
    build_rev991_new_user_creation_drill,
    build_rev992_api_secret_storage_drill,
    build_rev993_commission_fee_settings_drill,
    build_rev994_risk_whitelist_strategy_permission_drill,
    build_single_user_onboarding_drill_report,
    build_single_user_onboarding_drill_summary,
)

from services.paper_trading_production_drill_service import (
    build_paper_trading_production_drill_report,
    build_paper_trading_production_drill_summary,
    build_rev996_market_scanner_signal_flow_production_test,
    build_rev997_filter_strategy_selection_production_test,
    build_rev998_trade_intent_risk_approval_production_test,
    build_rev999_paper_execution_journal_pnl_production_test,
)

from services.micro_live_permission_final_gate_service import (
    build_micro_live_permission_final_gate_report,
    build_micro_live_permission_final_gate_summary,
    build_rev1001_first_micro_live_max_notional_final_limit,
    build_rev1002_first_micro_live_max_loss_final_limit,
    build_rev1003_allowed_symbol_whitelist_final_lock,
    build_rev1004_owner_approval_activation_token_final_gate,
)

from services.first_real_micro_live_supervised_trial_service import (
    build_first_real_micro_live_supervised_trial_packet,
    build_first_real_micro_live_supervised_trial_summary,
    build_rev1006_explicit_real_submit_enable_check,
    build_rev1007_order_preview_submit_final_contract,
    build_rev1008_position_tracker_emergency_guard_binding,
    build_rev1009_exit_plan_timeout_sl_tp_binding,
)

from services.post_trade_evidence_freeze_service import (
    build_post_trade_evidence_freeze_report,
    build_post_trade_evidence_freeze_summary,
    build_rev1011_exchange_order_status_collector,
    build_rev1012_fill_partial_rejected_analysis,
    build_rev1013_position_journal_pnl_reconciliation,
    build_rev1014_fee_slippage_latency_reality_check,
)


router = APIRouter(prefix="/api/production", tags=["production"])


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/completion-claim")
def get_completion_claim(current_user: dict = Depends(require_user)):
    return completion_claim(read_auth_store(), current_username(current_user))


@router.get("/launch-readiness")
def get_launch_readiness(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return launch_readiness(read_auth_store(), user, load_shadow(user), load_settings(user))


@router.get("/commission/settings")
def get_my_commission_settings(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    record = (read_auth_store().get("users") or {}).get(user, {})
    return {"status": "ok", "user": user, "commission_settings": normalize_commission_settings(record.get("commission_settings")), "secret_values_returned": False}


@router.post("/commission/settings")
def set_my_commission_settings(payload: dict, current_user: dict = Depends(require_owner)):
    user = str((payload or {}).get("username") or current_username(current_user)).strip()
    store = read_auth_store()
    try:
        result = update_commission_settings(store, user, payload or {})
    except KeyError:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    write_auth_store(store)
    return result


@router.post("/commission/preview")
def get_commission_preview(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return commission_preview(payload, read_auth_store(), current_username(current_user))




@router.post("/commission/business-flow")
def post_commission_business_flow(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return validate_commission_business_flow(payload or {}, read_auth_store(), current_username(current_user))


@router.post("/commission/ledger/preview")
def post_commission_ledger_preview(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_commission_ledger(payload or {}, read_auth_store(), current_username(current_user))


@router.get("/commission/business-flow/summary")
def get_commission_business_flow_summary(current_user: dict = Depends(require_owner)):
    return build_commission_business_flow_summary(read_auth_store(), current_username(current_user))


@router.post("/filters/evaluate")
def post_filter_evaluation(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return evaluate_filters(payload, read_auth_store(), current_username(current_user))


@router.post("/strategies/evaluate")
def post_strategy_evaluation(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return evaluate_strategy_candidates(payload, read_auth_store(), current_username(current_user))


@router.post("/high-frequency/capacity")
def post_high_frequency_capacity(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return high_frequency_capacity(payload, read_auth_store(), current_username(current_user))


@router.get("/final-code-reality-audit")
def get_final_code_reality_audit(current_user: dict = Depends(require_owner)):
    return build_final_code_reality_audit()


@router.get("/final-code-reality-audit/summary")
def get_final_code_reality_audit_summary(current_user: dict = Depends(require_owner)):
    return build_final_code_reality_audit_summary()


@router.get("/deploy-readiness")
def get_production_deploy_readiness(current_user: dict = Depends(require_owner)):
    return build_production_deploy_readiness()


@router.get("/deploy-readiness/summary")
def get_production_deploy_readiness_summary(current_user: dict = Depends(require_owner)):
    return build_production_deploy_readiness_summary()


@router.get("/binance/read-only-verification")
def get_binance_read_only_verification(current_user: dict = Depends(require_owner)):
    return build_binance_read_only_verification(current_username(current_user))


@router.get("/binance/read-only-verification/summary")
def get_binance_read_only_verification_summary(current_user: dict = Depends(require_owner)):
    return build_binance_read_only_verification_summary(current_username(current_user))


@router.get("/binance/read-only-verification/quality")
def get_binance_read_only_verification_quality(current_user: dict = Depends(require_owner)):
    return build_binance_read_only_verification_quality(current_username(current_user))


@router.get("/onboarding/summary")
def get_production_onboarding_summary(current_user: dict = Depends(require_owner)):
    return build_onboarding_summary(read_auth_store())


@router.post("/onboarding/validate")
def post_production_onboarding_validate(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    return validate_onboarding_payload(payload or {})


@router.post("/onboarding/apply")
def post_production_onboarding_apply(payload: dict, current_user: dict = Depends(require_owner)):
    username = str((payload or {}).get("username") or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Kullanıcı adı gerekli.")
    store = read_auth_store()
    try:
        result = apply_onboarding_to_existing_user(store, username, payload or {})
    except KeyError:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if result.get("status") != "ok":
        return result
    write_auth_store(store)
    return result


@router.get("/onboarding/quality")
def get_production_onboarding_quality(current_user: dict = Depends(require_owner)):
    return build_onboarding_quality(read_auth_store())

@router.post("/dry-run/paper-to-live")
def post_paper_to_live_dry_production_drill(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return run_paper_to_live_dry_production_drill(payload or {}, read_auth_store(), current_username(current_user))


@router.get("/dry-run/paper-to-live/summary")
def get_paper_to_live_dry_production_drill_summary(current_user: dict = Depends(require_owner)):
    return build_paper_to_live_dry_production_drill_summary(read_auth_store(), current_username(current_user))



@router.post("/micro-live/permission/first")
def post_first_real_micro_live_permission(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return evaluate_first_real_micro_live_permission(payload or {}, read_auth_store(), current_username(current_user))


@router.get("/micro-live/permission/first/summary")
def get_first_real_micro_live_permission_summary(current_user: dict = Depends(require_owner)):
    return build_first_real_micro_live_permission_summary(read_auth_store(), current_username(current_user))

@router.post("/micro-live/execution/first")
def post_first_real_micro_live_execution(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return evaluate_first_real_micro_live_execution(payload or {}, read_auth_store(), current_username(current_user))


@router.get("/micro-live/execution/first/summary")
def get_first_real_micro_live_execution_summary(current_user: dict = Depends(require_owner)):
    return build_first_real_micro_live_execution_summary(read_auth_store(), current_username(current_user))

@router.post("/micro-live/freeze-repeat-decision")
def post_live_freeze_repeat_decision(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return evaluate_live_freeze_repeat_decision(payload or {}, read_auth_store(), current_username(current_user))


@router.get("/micro-live/freeze-repeat-decision/summary")
def get_live_freeze_repeat_decision_summary(current_user: dict = Depends(require_owner)):
    return build_live_freeze_repeat_decision_summary(read_auth_store(), current_username(current_user))



@router.post("/micro-live/continuity-repair")
def post_continuity_repair_reconciliation_merge(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return evaluate_continuity_repair_merge(payload or {}, read_auth_store(), current_username(current_user))


@router.get("/micro-live/continuity-repair/summary")
def get_continuity_repair_reconciliation_merge_summary(current_user: dict = Depends(require_owner)):
    return build_continuity_repair_summary(read_auth_store(), current_username(current_user))


@router.get("/multi-user/hardening")
def get_multi_user_production_hardening(current_user: dict = Depends(require_owner)):
    return evaluate_multi_user_production_hardening(read_auth_store())


@router.get("/multi-user/hardening/summary")
def get_multi_user_production_hardening_summary(current_user: dict = Depends(require_owner)):
    return build_multi_user_production_hardening_summary(read_auth_store())

@router.get("/ui/premium-polish")
def get_premium_ui_final_polish(current_user: dict = Depends(require_owner)):
    return build_premium_ui_final_polish_report()


@router.get("/ui/premium-polish/summary")
def get_premium_ui_final_polish_summary(current_user: dict = Depends(require_owner)):
    return build_premium_ui_final_polish_summary()



@router.post("/strategy-filter/live-calibration")
def post_strategy_filter_live_calibration(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_strategy_filter_live_calibration(payload or {})


@router.get("/strategy-filter/live-calibration/summary")
def get_strategy_filter_live_calibration_summary(current_user: dict = Depends(require_owner)):
    return build_strategy_filter_live_calibration_summary()


@router.post("/high-frequency/safety-capacity")
def post_high_frequency_safety_capacity(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_high_frequency_safety_capacity(payload or {})


@router.get("/high-frequency/safety-capacity/summary")
def get_high_frequency_safety_capacity_summary(current_user: dict = Depends(require_owner)):
    return build_high_frequency_safety_capacity_summary()


@router.post("/monitoring/alert")
def post_production_monitoring_alert(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_production_monitoring_alert(payload or {})


@router.get("/monitoring/alert/summary")
def get_production_monitoring_alert_summary(current_user: dict = Depends(require_owner)):
    return build_production_monitoring_alert_summary()


@router.post("/commercial-launch/candidate")
def post_commercial_launch_candidate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_commercial_launch_candidate(payload or {})


@router.get("/commercial-launch/candidate/summary")
def get_commercial_launch_candidate_summary(current_user: dict = Depends(require_owner)):
    return build_commercial_launch_candidate_summary()


@router.post("/live-readiness/final-lock")
def post_final_live_readiness_lock(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_final_live_readiness_lock(payload or {})


@router.get("/live-readiness/final-lock/summary")
def get_final_live_readiness_lock_summary(current_user: dict = Depends(require_owner)):
    return build_final_live_readiness_lock_summary()


@router.post("/regression/clean-package")
def post_final_regression_clean_package(payload: dict | None = None, current_user: dict = Depends(require_user)):
    return build_final_regression_clean_package(payload or {})


@router.get("/regression/clean-package/summary")
def get_final_regression_clean_package_summary(current_user: dict = Depends(require_owner)):
    return build_final_regression_clean_package_summary()


@router.post("/final-commercial-rc")
def post_hmtstc_final_commercial_rc(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    return build_hmtstc_final_commercial_rc(payload or {})


@router.get("/final-commercial-rc/summary")
def get_hmtstc_final_commercial_rc_summary(current_user: dict = Depends(require_owner)):
    return build_hmtstc_final_commercial_rc_summary()


@router.post("/final-reality-reaudit")
def post_final_reality_reaudit(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    return build_final_reality_reaudit(payload or {})


@router.get("/final-reality-reaudit/summary")
def get_final_reality_reaudit_summary(current_user: dict = Depends(require_owner)):
    return build_final_reality_reaudit_summary()


@router.get("/sync/local-github-vps")
def get_local_github_vps_sync_report(current_user: dict = Depends(require_owner)):
    return build_local_github_vps_sync_report()


@router.get("/sync/local-github-vps/local-structure")
def get_rev976_local_structure_check(current_user: dict = Depends(require_owner)):
    return build_rev976_local_structure_check()


@router.get("/sync/local-github-vps/gitignore-secret-runtime")
def get_rev977_gitignore_secret_runtime_check(current_user: dict = Depends(require_owner)):
    return build_rev977_gitignore_secret_runtime_check()


@router.get("/sync/local-github-vps/github-safe-list")
def get_rev978_github_commit_push_safe_list(current_user: dict = Depends(require_owner)):
    return build_rev978_github_commit_push_safe_list()


@router.get("/sync/local-github-vps/vps-match")
def get_rev979_vps_pull_deploy_match_check(current_user: dict = Depends(require_owner)):
    return build_rev979_vps_pull_deploy_match_check()


@router.get("/environment-activation")
def get_production_environment_activation_report(current_user: dict = Depends(require_owner)):
    return build_production_environment_activation_report()


@router.get("/environment-activation/summary")
def get_production_environment_activation_summary(current_user: dict = Depends(require_owner)):
    return build_production_environment_activation_summary()


@router.get("/environment-activation/backend-env")
def get_rev981_backend_env_check(current_user: dict = Depends(require_owner)):
    return build_rev981_backend_env_check()


@router.get("/environment-activation/frontend-config")
def get_rev982_frontend_build_config_check(current_user: dict = Depends(require_owner)):
    return build_rev982_frontend_build_config_check()


@router.get("/environment-activation/service-nginx")
def get_rev983_service_nginx_check(current_user: dict = Depends(require_owner)):
    return build_rev983_service_nginx_check()


@router.get("/environment-activation/dependency-permission")
def get_rev984_vps_dependency_permission_check(current_user: dict = Depends(require_owner)):
    return build_rev984_vps_dependency_permission_check()


@router.get("/binance/read-only-live-check")
def get_binance_read_only_live_check_report(current_user: dict = Depends(require_owner)):
    return build_binance_read_only_live_check_report(current_username(current_user))


@router.get("/binance/read-only-live-check/summary")
def get_binance_read_only_live_check_summary(current_user: dict = Depends(require_owner)):
    return build_binance_read_only_live_check_summary(current_username(current_user))


@router.get("/binance/read-only-live-check/api-secret-masking")
def get_rev986_api_secret_masking_check(current_user: dict = Depends(require_owner)):
    return build_rev986_api_secret_masking_check(current_username(current_user))


@router.get("/binance/read-only-live-check/account")
def get_rev987_binance_account_read_only_check(current_user: dict = Depends(require_owner)):
    return build_rev987_binance_account_read_only_check()


@router.get("/binance/read-only-live-check/balances")
def get_rev988_balance_read_only_check(current_user: dict = Depends(require_owner)):
    return build_rev988_balance_read_only_check()


@router.get("/binance/read-only-live-check/permission-drift")
def get_rev989_permission_drift_trade_permission_check(current_user: dict = Depends(require_owner)):
    return build_rev989_permission_drift_trade_permission_check(current_username(current_user))

@router.get("/onboarding/drill/full")
def get_single_user_onboarding_drill_report(current_user: dict = Depends(require_owner)):
    return build_single_user_onboarding_drill_report(current_username(current_user))


@router.get("/onboarding/drill/summary")
def get_single_user_onboarding_drill_summary(current_user: dict = Depends(require_owner)):
    return build_single_user_onboarding_drill_summary(current_username(current_user))


@router.get("/onboarding/drill/new-user")
def get_rev991_new_user_creation_drill(current_user: dict = Depends(require_owner)):
    return build_rev991_new_user_creation_drill(current_username(current_user))


@router.get("/onboarding/drill/api-secret-storage")
def get_rev992_api_secret_storage_drill(current_user: dict = Depends(require_owner)):
    return build_rev992_api_secret_storage_drill(current_username(current_user))


@router.get("/onboarding/drill/commission-fee")
def get_rev993_commission_fee_settings_drill(current_user: dict = Depends(require_owner)):
    return build_rev993_commission_fee_settings_drill(current_username(current_user))


@router.get("/onboarding/drill/risk-permissions")
def get_rev994_risk_whitelist_strategy_permission_drill(current_user: dict = Depends(require_owner)):
    return build_rev994_risk_whitelist_strategy_permission_drill(current_username(current_user))


@router.get("/paper-trading/production-drill/full")
def get_paper_trading_production_drill_report(current_user: dict = Depends(require_owner)):
    return build_paper_trading_production_drill_report(current_username(current_user))


@router.get("/paper-trading/production-drill/summary")
def get_paper_trading_production_drill_summary(current_user: dict = Depends(require_owner)):
    return build_paper_trading_production_drill_summary(current_username(current_user))


@router.get("/paper-trading/production-drill/market-signal")
def get_rev996_market_scanner_signal_flow_production_test(current_user: dict = Depends(require_owner)):
    return build_rev996_market_scanner_signal_flow_production_test(current_username(current_user))


@router.get("/paper-trading/production-drill/filter-strategy")
def get_rev997_filter_strategy_selection_production_test(current_user: dict = Depends(require_owner)):
    return build_rev997_filter_strategy_selection_production_test(current_username(current_user))


@router.get("/paper-trading/production-drill/intent-risk-approval")
def get_rev998_trade_intent_risk_approval_production_test(current_user: dict = Depends(require_owner)):
    return build_rev998_trade_intent_risk_approval_production_test(current_username(current_user))


@router.get("/paper-trading/production-drill/execution-journal-pnl")
def get_rev999_paper_execution_journal_pnl_production_test(current_user: dict = Depends(require_owner)):
    return build_rev999_paper_execution_journal_pnl_production_test(current_username(current_user))

@router.get("/micro-live/permission-final-gate/full")
def get_micro_live_permission_final_gate_report(current_user: dict = Depends(require_owner)):
    return build_micro_live_permission_final_gate_report(current_username(current_user))


@router.get("/micro-live/permission-final-gate/summary")
def get_micro_live_permission_final_gate_summary(current_user: dict = Depends(require_owner)):
    return build_micro_live_permission_final_gate_summary(current_username(current_user))


@router.get("/micro-live/permission-final-gate/max-notional")
def get_rev1001_first_micro_live_max_notional_final_limit(current_user: dict = Depends(require_owner)):
    return build_rev1001_first_micro_live_max_notional_final_limit(current_username(current_user))


@router.get("/micro-live/permission-final-gate/max-loss")
def get_rev1002_first_micro_live_max_loss_final_limit(current_user: dict = Depends(require_owner)):
    return build_rev1002_first_micro_live_max_loss_final_limit(current_username(current_user))


@router.get("/micro-live/permission-final-gate/whitelist")
def get_rev1003_allowed_symbol_whitelist_final_lock(current_user: dict = Depends(require_owner)):
    return build_rev1003_allowed_symbol_whitelist_final_lock(current_username(current_user))


@router.get("/micro-live/permission-final-gate/owner-activation")
def get_rev1004_owner_approval_activation_token_final_gate(current_user: dict = Depends(require_owner)):
    return build_rev1004_owner_approval_activation_token_final_gate(current_username(current_user))

@router.get("/micro-live/supervised-trial/packet")
def get_first_real_micro_live_supervised_trial_packet(current_user: dict = Depends(require_owner)):
    return build_first_real_micro_live_supervised_trial_packet(current_username(current_user))


@router.get("/micro-live/supervised-trial/summary")
def get_first_real_micro_live_supervised_trial_summary(current_user: dict = Depends(require_owner)):
    return build_first_real_micro_live_supervised_trial_summary(current_username(current_user))


@router.get("/micro-live/supervised-trial/explicit-submit-enable")
def get_rev1006_explicit_real_submit_enable_check(current_user: dict = Depends(require_owner)):
    return build_rev1006_explicit_real_submit_enable_check(current_username(current_user))


@router.get("/micro-live/supervised-trial/order-preview-contract")
def get_rev1007_order_preview_submit_final_contract(current_user: dict = Depends(require_owner)):
    return build_rev1007_order_preview_submit_final_contract(current_username(current_user))


@router.get("/micro-live/supervised-trial/position-emergency-guard")
def get_rev1008_position_tracker_emergency_guard_binding(current_user: dict = Depends(require_owner)):
    return build_rev1008_position_tracker_emergency_guard_binding(current_username(current_user))


@router.get("/micro-live/supervised-trial/exit-plan")
def get_rev1009_exit_plan_timeout_sl_tp_binding(current_user: dict = Depends(require_owner)):
    return build_rev1009_exit_plan_timeout_sl_tp_binding(current_username(current_user))


@router.get("/micro-live/post-trade-evidence-freeze/report")
@router.get("/post-trade/evidence-freeze/full")
def get_post_trade_evidence_freeze_report(current_user: dict = Depends(require_owner)):
    return build_post_trade_evidence_freeze_report(username=current_username(current_user))


@router.post("/micro-live/post-trade-evidence-freeze/report")
@router.post("/post-trade/evidence-freeze/full")
def post_post_trade_evidence_freeze_report(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    return build_post_trade_evidence_freeze_report(payload or {}, current_username(current_user))


@router.get("/micro-live/post-trade-evidence-freeze/summary")
@router.get("/post-trade/evidence-freeze/summary")
def get_post_trade_evidence_freeze_summary(current_user: dict = Depends(require_owner)):
    return build_post_trade_evidence_freeze_summary(username=current_username(current_user))


@router.get("/micro-live/post-trade-evidence-freeze/order-status")
@router.get("/post-trade/evidence-freeze/order-status")
def get_rev1011_exchange_order_status_collector(current_user: dict = Depends(require_owner)):
    return build_rev1011_exchange_order_status_collector(username=current_username(current_user))


@router.get("/micro-live/post-trade-evidence-freeze/fill-analysis")
@router.get("/post-trade/evidence-freeze/fill-analysis")
def get_rev1012_fill_partial_rejected_analysis(current_user: dict = Depends(require_owner)):
    return build_rev1012_fill_partial_rejected_analysis(username=current_username(current_user))


@router.get("/micro-live/post-trade-evidence-freeze/reconciliation")
@router.get("/post-trade/evidence-freeze/reconciliation")
def get_rev1013_position_journal_pnl_reconciliation(current_user: dict = Depends(require_owner)):
    return build_rev1013_position_journal_pnl_reconciliation(username=current_username(current_user))


@router.get("/micro-live/post-trade-evidence-freeze/reality-check")
@router.get("/post-trade/evidence-freeze/reality-check")
def get_rev1014_fee_slippage_latency_reality_check(current_user: dict = Depends(require_owner)):
    return build_rev1014_fee_slippage_latency_reality_check(username=current_username(current_user))

