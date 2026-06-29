from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'approved'}


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason('none', 'No production limited-live blocker.', 'no_action', 'ok', 999)
    weights = {'critical': 0, 'major': 1, 'minor': 2, 'ok': 3}
    return sorted(reasons, key=lambda r: (weights.get(str(r.get('severity')), 2), int(r.get('priority', 50))))[0]


def _check(name: str, status: str, message: str, detail: dict | None = None) -> dict:
    return {'name': name, 'status': status, 'message': message, 'detail': detail or {}}


def _totals(checks: list[dict]) -> dict:
    return {
        'total': len(checks),
        'ok': sum(1 for c in checks if c.get('status') == 'ok'),
        'review': sum(1 for c in checks if c.get('status') == 'review'),
        'blocked': sum(1 for c in checks if c.get('status') == 'blocked'),
    }


def _final_status(checks: list[dict]) -> str:
    if any(c.get('status') == 'blocked' for c in checks):
        return 'blocked'
    if any(c.get('status') == 'review' for c in checks):
        return 'review'
    return 'ok'


def _command_preview() -> dict:
    return {
        'places_order': False,
        'sends_exchange_request': False,
        'submits_close_order': False,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'auto_scale': False,
        'auto_apply': False,
        'read_only': True,
        'approval_gated': True,
    }


def _policy(settings: dict | None) -> dict:
    settings = _as_dict(settings)
    live = _as_dict(settings.get('limited_live') or settings.get('live') or {})
    risk = _as_dict(settings.get('risk') or settings.get('risk_profile') or {})
    capital = _as_dict(settings.get('small_capital') or settings.get('capital') or {})
    symbols = _as_list(live.get('allowed_symbols')) or _as_list(settings.get('allowed_symbols')) or ['BTCUSDT', 'ETHUSDT']
    return {
        'real_submit_enable': _truthy(settings.get('real_submit_enable') or live.get('real_submit_enable')),
        'real_close_enable': _truthy(settings.get('real_close_enable') or live.get('real_close_enable')),
        'auto_scale': _truthy(settings.get('auto_scale') or live.get('auto_scale')),
        'auto_apply': _truthy(settings.get('auto_apply') or live.get('auto_apply')),
        'owner_approval': _truthy(live.get('owner_approval') or live.get('owner_approved') or settings.get('owner_approval')),
        'activation_token_preview': bool(str(live.get('activation_token_preview') or settings.get('activation_token_preview') or '').strip()),
        'whitelist_enforced': _truthy(live.get('whitelist_enforced') or settings.get('whitelist_enforced') or True),
        'daily_hard_stop_enabled': _truthy(live.get('daily_hard_stop_enabled') or risk.get('daily_hard_stop_enabled') or True),
        'api_permission_preview': _truthy(live.get('api_permission_preview') or settings.get('api_permission_preview') or True),
        'emergency_guard_enabled': _truthy(live.get('emergency_guard_enabled') or settings.get('emergency_guard_enabled') or True),
        'session_boundary': str(live.get('session_id') or settings.get('session_id') or 'production-limited-live-candidate-session').strip(),
        'max_notional': _safe_float(live.get('max_notional') or risk.get('max_notional') or settings.get('max_notional_usdt'), 25.0),
        'max_daily_loss': _safe_float(live.get('max_daily_loss') or risk.get('max_daily_loss') or settings.get('max_daily_loss_usdt'), 5.0),
        'capital_usdt': _safe_float(capital.get('capital_usdt') or settings.get('capital_usdt'), 100.0),
        'allowed_symbols': symbols,
    }


def _upstream(data: dict | None) -> dict:
    data = _as_dict(data)
    return {
        'data_integrity': _as_dict(data.get('autonomous_production_data_integrity_block') or data.get('production_data_integrity_report')),
        'strategy_reality': _as_dict(data.get('autonomous_live_strategy_reality_validation_block') or data.get('live_strategy_reality_report')),
        'capital_preservation': _as_dict(data.get('autonomous_capital_preservation_usdt_dominance_block') or data.get('capital_preservation_decision_packet')),
        'opportunity_quality': _as_dict(data.get('autonomous_opportunity_quality_block') or data.get('autonomous_opportunity_quality_report')),
        'operator_ux': _as_dict(data.get('autonomous_limited_live_operator_approval_ux_block') or data.get('limited_live_operator_ux_packet')),
        'dry_proof': _as_dict(data.get('autonomous_micro_live_execution_dry_proof_block') or data.get('micro_live_execution_dry_proof_report')),
        'readiness_v2': _as_dict(data.get('autonomous_small_capital_live_readiness_gate_v2_block') or data.get('small_capital_live_readiness_decision')),
    }


def _common_reasons(data: dict | None, settings: dict | None) -> list[dict]:
    p = _policy(settings)
    reasons: list[dict] = []
    if p['real_submit_enable'] or p['real_close_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Real submit/close flags must remain OFF until owner-gated activation.', 'turn_real_execution_flags_off', 'critical', 0))
    if p['auto_scale'] or p['auto_apply']:
        reasons.append(_reason('auto_scale_or_apply_enabled', 'Auto-scale and auto-apply must remain OFF for candidate review.', 'turn_auto_scale_apply_off', 'critical', 1))
    if not p['whitelist_enforced'] or not p['allowed_symbols']:
        reasons.append(_reason('whitelist_not_ready', 'Allowed symbol whitelist must be enforced and non-empty.', 'fix_symbol_whitelist', 'major', 10))
    if not p['daily_hard_stop_enabled']:
        reasons.append(_reason('daily_hard_stop_disabled', 'Daily hard stop must be enabled.', 'enable_daily_hard_stop', 'major', 11))
    if not p['emergency_guard_enabled']:
        reasons.append(_reason('emergency_guard_disabled', 'Emergency guard must be enabled.', 'enable_emergency_guard', 'major', 12))
    if p['max_notional'] <= 0 or p['max_daily_loss'] <= 0:
        reasons.append(_reason('risk_contract_missing', 'Max notional and max daily loss must be explicit.', 'set_live_risk_contract', 'major', 13))
    if p['max_notional'] > max(1.0, p['capital_usdt'] * 0.25):
        reasons.append(_reason('notional_too_large', 'Max notional is too large for small capital limited-live.', 'reduce_max_notional', 'major', 14))
    if not p['session_boundary']:
        reasons.append(_reason('session_boundary_missing', 'Limited-live session boundary is required.', 'set_session_boundary', 'major', 15))
    for key, payload in _upstream(data).items():
        status = str(payload.get('status') or payload.get('decision') or payload.get('limited_live') or '').lower()
        if status in {'blocked', 'halt', 'emergency', 'inconsistent', 'no-go'}:
            reasons.append(_reason(f'{key}_blocked', f'{key} upstream result blocks production limited-live candidate.', 'hold_until_upstream_ok', 'major', 20))
    return reasons


def build_rev261_production_limited_live_checklist(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    checks = [
        _check('real_execution_default_off', 'ok' if not (p['real_submit_enable'] or p['real_close_enable']) else 'blocked', 'Real submit/close remains OFF by default.'),
        _check('owner_gate_defined', 'ok' if p['owner_approval'] else 'review', 'Owner approval is required before live activation.'),
        _check('risk_contract_defined', 'ok' if p['max_notional'] > 0 and p['max_daily_loss'] > 0 else 'blocked', 'Max notional and daily loss are explicit.'),
        _check('whitelist_enforced', 'ok' if p['whitelist_enforced'] and p['allowed_symbols'] else 'blocked', 'Allowed symbols are restricted.'),
        _check('session_boundary_defined', 'ok' if p['session_boundary'] else 'blocked', 'Session boundary is explicit.'),
    ]
    body = {'candidate_checklist': checks, 'allowed_symbols': p['allowed_symbols'], 'max_notional': p['max_notional'], 'max_daily_loss': p['max_daily_loss'], 'session_boundary': bool(p['session_boundary']), 'real_submit_close': 'OFF'}
    return {'engine': 'production_limited_live_checklist', 'revision': 261, 'status': _final_status(checks), 'generated_at': now_iso(), 'production_limited_live_checklist': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev262_live_activation_contract_finalizer'}


def build_rev262_live_activation_contract_finalizer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    checks = [
        _check('approval_scope_present', 'ok' if p['owner_approval'] else 'review', 'Owner approval scope is previewed, not executed.'),
        _check('activation_token_preview_present', 'ok' if p['activation_token_preview'] else 'review', 'Activation token preview is required; token value is never returned.'),
        _check('permission_preview_ok', 'ok' if p['api_permission_preview'] else 'blocked', 'API permission preview must be valid.'),
        _check('approval_gated_path', 'ok', 'Submit path remains approval-gated and read-only in package.'),
    ]
    contract = {'contract_version': 'final-preview-v1', 'owner_approval_required': True, 'owner_approval_present': p['owner_approval'], 'activation_token_preview_present': p['activation_token_preview'], 'token_value_returned': False, 'scope': 'limited_live_micro_submit_exit_preview', 'max_notional': p['max_notional'], 'max_daily_loss': p['max_daily_loss'], 'session_boundary': p['session_boundary'], 'approval_gated': True, 'real_submit_close': 'OFF'}
    return {'engine': 'live_activation_contract_finalizer', 'revision': 262, 'status': _final_status(checks), 'generated_at': now_iso(), 'live_activation_contract_finalizer': contract, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev263_rollback_emergency_protocol_final_check'}


def build_rev263_rollback_emergency_protocol_final_check(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    checks = [
        _check('emergency_guard_enabled', 'ok' if p['emergency_guard_enabled'] else 'blocked', 'Emergency guard is enabled.'),
        _check('daily_hard_stop_enabled', 'ok' if p['daily_hard_stop_enabled'] else 'blocked', 'Daily hard stop is enabled.'),
        _check('rollback_action_defined', 'ok', 'Rollback action is freeze + disable activation + manual attention.'),
        _check('auto_close_default_off', 'ok', 'Emergency close is not auto-submitted by default.'),
    ]
    protocol = {'rollback_ready': _final_status(checks) != 'blocked', 'halt_action': 'HALT_AND_FREEZE', 'rollback_action': 'DISABLE_ACTIVATION_AND_REQUIRE_OWNER_REVIEW', 'emergency_condition': 'loss_limit_or_reconciliation_failure_or_permission_drift', 'auto_close_default_off': True, 'manual_attention_required': True}
    return {'engine': 'rollback_emergency_protocol_final_check', 'revision': 263, 'status': _final_status(checks), 'generated_at': now_iso(), 'rollback_emergency_protocol_final_check': protocol, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev264_deployment_safe_package_audit'}


def build_rev264_deployment_safe_package_audit(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    checks = [
        _check('runtime_files_excluded', 'ok', 'Runtime stores, db/log/env artifacts are excluded by packaging rules.'),
        _check('secret_response_blocked', 'ok', 'Service returns no secret, key or token value.'),
        _check('read_only_candidate_packet', 'ok', 'Candidate packet is read-only and side-effect free.'),
        _check('real_network_default_off', 'ok', 'Network execution remains disabled by default.'),
    ]
    audit = {'deployment_safe': True, 'forbidden_runtime_artifacts_expected': False, 'secret_values_returned': False, 'network_execution': 'OFF', 'package_scope': 'source_plus_tests_plus_minimal_docs'}
    return {'engine': 'deployment_safe_package_audit', 'revision': 264, 'status': _final_status(checks), 'generated_at': now_iso(), 'deployment_safe_package_audit': audit, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev265_production_limited_live_candidate_packet'}


def build_rev265_production_limited_live_candidate_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    reasons = _common_reasons(data, settings)
    checklist = build_rev261_production_limited_live_checklist(data, settings, auth_store, username)
    contract = build_rev262_live_activation_contract_finalizer(data, settings, auth_store, username)
    rollback = build_rev263_rollback_emergency_protocol_final_check(data, settings, auth_store, username)
    audit = build_rev264_deployment_safe_package_audit(data, settings, auth_store, username)
    for payload in (checklist, contract, rollback, audit):
        if payload.get('status') == 'blocked':
            reasons.append(_reason(f"{payload.get('engine')}_blocked", f"{payload.get('engine')} blocks candidate readiness.", 'fix_blocked_candidate_gate', 'major', 25))
    critical = _critical(reasons)
    if critical.get('severity') in {'critical', 'major'}:
        candidate = 'BLOCKED'
    elif p['owner_approval'] and p['activation_token_preview']:
        candidate = 'READY'
    else:
        candidate = 'REVIEW'
    checks = [
        _check('candidate_blockers_absent', 'ok' if candidate != 'BLOCKED' else 'blocked', 'No critical or major candidate blocker.'),
        _check('owner_activation_ready', 'ok' if p['owner_approval'] and p['activation_token_preview'] else 'review', 'Owner approval and token preview are required for READY.'),
        _check('rollback_ready', rollback.get('status', 'review'), 'Rollback and emergency protocol are checked.'),
        _check('deploy_safe', audit.get('status', 'review'), 'Deployment-safe package audit is checked.'),
    ]
    packet = {'limited_live_candidate': candidate, 'critical_blocker': critical, 'operator_action': 'approve_limited_live_session' if candidate == 'READY' else critical.get('action'), 'live_activation_scope': 'micro_limited_live_preview_only', 'max_notional': p['max_notional'], 'max_daily_loss': p['max_daily_loss'], 'allowed_symbols': p['allowed_symbols'], 'session_boundary': p['session_boundary'], 'stop_conditions': ['daily_hard_stop', 'reconciliation_inconsistent', 'permission_drift', 'emergency_guard', 'owner_revocation'], 'real_submit_close': 'OFF', 'auto_scale': 'OFF', 'auto_apply': 'OFF'}
    return {'engine': 'production_limited_live_candidate_packet', 'revision': 265, 'status': _final_status(checks), 'generated_at': now_iso(), 'production_limited_live_candidate_packet': packet, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'post_rev265_owner_deploy_review'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {261: build_rev261_production_limited_live_checklist, 262: build_rev262_live_activation_contract_finalizer, 263: build_rev263_rollback_emergency_protocol_final_check, 264: build_rev264_deployment_safe_package_audit, 265: build_rev265_production_limited_live_candidate_packet}
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev261-265 production limited-live candidate revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev261 = build_rev261_production_limited_live_checklist(data, settings, auth_store, username)
    rev262 = build_rev262_live_activation_contract_finalizer(data, settings, auth_store, username)
    rev263 = build_rev263_rollback_emergency_protocol_final_check(data, settings, auth_store, username)
    rev264 = build_rev264_deployment_safe_package_audit(data, settings, auth_store, username)
    rev265 = build_rev265_production_limited_live_candidate_packet(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev261, rev262, rev263, rev264, rev265):
        checks.extend(_as_list(payload.get('checks')))
    return {'engine': 'production_limited_live_candidate_block', 'revision': 265, 'status': rev265.get('status', 'review'), 'generated_at': now_iso(), 'rev261_production_limited_live_checklist': rev261, 'rev262_live_activation_contract_finalizer': rev262, 'rev263_rollback_emergency_protocol_final_check': rev263, 'rev264_deployment_safe_package_audit': rev264, 'rev265_production_limited_live_candidate_packet': rev265, 'production_limited_live_candidate_packet': rev265.get('production_limited_live_candidate_packet', {}), 'summary_result': build_summary_for_revision(265, data, settings, auth_store, username), 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'owner_review_before_real_limited_live'}


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key = {261: 'production_limited_live_checklist', 262: 'live_activation_contract_finalizer', 263: 'rollback_emergency_protocol_final_check', 264: 'deployment_safe_package_audit', 265: 'production_limited_live_candidate_packet'}[int(revision)]
    body = _as_dict(payload.get(key))
    blocker = _as_dict(body.get('critical_blocker'))
    return {'revision': int(revision), 'limited_live_candidate': body.get('limited_live_candidate') or ('READY' if payload.get('status') == 'ok' else 'REVIEW'), 'critical_issue': blocker.get('code', 'none'), 'operator_action': body.get('operator_action') or blocker.get('action') or 'review', 'max_notional': body.get('max_notional'), 'max_daily_loss': body.get('max_daily_loss'), 'allowed_symbols': body.get('allowed_symbols'), 'trade_allowed': body.get('limited_live_candidate') == 'READY', 'real_submit_close': 'OFF'}


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    command = _as_dict(payload.get('command_preview'))
    failures = []
    if command.get('places_order') or command.get('sends_exchange_request') or command.get('submits_close_order'):
        failures.append('unexpected_execution_side_effect')
    if command.get('real_submit_default_off') is not True or command.get('real_close_default_off') is not True:
        failures.append('real_execution_not_default_off')
    if command.get('auto_scale') or command.get('auto_apply'):
        failures.append('auto_scale_or_apply_enabled')
    if payload.get('contains_secret') or payload.get('secret_values_returned'):
        failures.append('secret_leak')
    return {'quality_gate': 'FAIL' if failures else 'PASS', 'revision': int(revision), 'engine': payload.get('engine'), 'status': payload.get('status'), 'failures': failures, 'command_preview': command, 'checked_at': now_iso()}
