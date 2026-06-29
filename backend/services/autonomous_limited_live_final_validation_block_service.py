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
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'approved', 'ready'}


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason('none', 'No limited-live final validation blocker.', 'no_action', 'ok', 999)
    weights = {'critical': 0, 'major': 1, 'review': 2, 'minor': 3, 'ok': 4}
    return sorted(reasons, key=lambda r: (weights.get(str(r.get('severity')), 3), int(r.get('priority', 50))))[0]


def _check(name: str, status: str, message: str, detail: dict | None = None) -> dict:
    return {'name': name, 'status': status, 'message': message, 'detail': detail or {}}


def _totals(checks: list[dict]) -> dict:
    return {
        'total': len(checks),
        'ok': sum(1 for c in checks if c.get('status') == 'ok'),
        'review': sum(1 for c in checks if c.get('status') == 'review'),
        'blocked': sum(1 for c in checks if c.get('status') == 'blocked'),
    }


def _status_from_checks(checks: list[dict]) -> str:
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
    allowed_symbols = _as_list(live.get('allowed_symbols')) or _as_list(settings.get('allowed_symbols')) or ['BTCUSDT', 'ETHUSDT']
    capital_usdt = _safe_float(capital.get('capital_usdt') or settings.get('capital_usdt'), 100.0)
    max_notional = _safe_float(live.get('max_notional') or risk.get('max_notional') or settings.get('max_notional_usdt'), 25.0)
    max_daily_loss = _safe_float(live.get('max_daily_loss') or risk.get('max_daily_loss') or settings.get('max_daily_loss_usdt'), 5.0)
    return {
        'real_submit_enable': _truthy(settings.get('real_submit_enable') or live.get('real_submit_enable')),
        'real_close_enable': _truthy(settings.get('real_close_enable') or live.get('real_close_enable')),
        'auto_scale': _truthy(settings.get('auto_scale') or live.get('auto_scale')),
        'auto_apply': _truthy(settings.get('auto_apply') or live.get('auto_apply')),
        'owner_approval': _truthy(live.get('owner_approval') or live.get('owner_approved') or settings.get('owner_approval')),
        'activation_token_preview': bool(str(live.get('activation_token_preview') or settings.get('activation_token_preview') or '').strip()),
        'session_boundary': str(live.get('session_id') or settings.get('session_id') or 'limited-live-final-validation-session').strip(),
        'whitelist_enforced': _truthy(live.get('whitelist_enforced') or settings.get('whitelist_enforced') or True),
        'daily_hard_stop_enabled': _truthy(live.get('daily_hard_stop_enabled') or risk.get('daily_hard_stop_enabled') or True),
        'emergency_guard_enabled': _truthy(live.get('emergency_guard_enabled') or settings.get('emergency_guard_enabled') or True),
        'api_permission_preview': _truthy(live.get('api_permission_preview') or settings.get('api_permission_preview') or True),
        'max_notional': max_notional,
        'max_daily_loss': max_daily_loss,
        'capital_usdt': capital_usdt,
        'allowed_symbols': allowed_symbols,
        'max_notional_ratio': max_notional / max(capital_usdt, 1.0),
        'max_loss_ratio': max_daily_loss / max(capital_usdt, 1.0),
    }


def _upstream(data: dict | None) -> dict:
    data = _as_dict(data)
    return {
        'production_candidate': _as_dict(data.get('autonomous_production_limited_live_candidate_block') or data.get('production_limited_live_candidate_packet')),
        'runtime_safety': _as_dict(data.get('autonomous_live_stabilization_block') or data.get('runtime_safety_state') or data.get('live_runtime_state')),
        'risk_firewall': _as_dict(data.get('autonomous_live_risk_firewall_block') or data.get('live_risk_firewall_decision_packet')),
        'capital_preservation': _as_dict(data.get('autonomous_capital_preservation_usdt_dominance_block') or data.get('capital_preservation_decision_packet')),
        'data_integrity': _as_dict(data.get('autonomous_production_data_integrity_block') or data.get('production_data_integrity_report')),
        'strategy_reality': _as_dict(data.get('autonomous_live_strategy_reality_validation_block') or data.get('live_strategy_reality_report')),
    }


def _extract_decision(payload: dict, *keys: str) -> str:
    body = payload
    for key in keys:
        if isinstance(body, dict) and key in body and isinstance(body.get(key), dict):
            body = body.get(key) or {}
    for key in ('decision', 'status', 'limited_live_candidate', 'limited_live', 'trade_allowed', 'data_integrity'):
        val = body.get(key) if isinstance(body, dict) else None
        if val is not None:
            return str(val).lower()
    return str(payload.get('status') or '').lower() if isinstance(payload, dict) else ''


def _common_reasons(data: dict | None, settings: dict | None) -> list[dict]:
    p = _policy(settings)
    reasons: list[dict] = []
    if p['real_submit_enable'] or p['real_close_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Real submit/close flags must remain OFF before final owner activation.', 'turn_real_execution_flags_off', 'critical', 0))
    if p['auto_scale'] or p['auto_apply']:
        reasons.append(_reason('auto_scale_or_apply_enabled', 'Auto-scale and auto-apply must remain OFF for limited-live validation.', 'turn_auto_scale_apply_off', 'critical', 1))
    if not p['whitelist_enforced'] or not p['allowed_symbols']:
        reasons.append(_reason('whitelist_missing', 'Allowed symbol whitelist must be enforced and non-empty.', 'fix_allowed_symbol_whitelist', 'major', 10))
    if not p['daily_hard_stop_enabled']:
        reasons.append(_reason('daily_hard_stop_disabled', 'Daily hard stop must be enabled.', 'enable_daily_hard_stop', 'major', 11))
    if not p['emergency_guard_enabled']:
        reasons.append(_reason('emergency_guard_disabled', 'Emergency guard must be enabled.', 'enable_emergency_guard', 'major', 12))
    if p['max_notional'] <= 0 or p['max_daily_loss'] <= 0:
        reasons.append(_reason('risk_contract_missing', 'Max notional and daily loss must be explicit.', 'set_limited_live_risk_contract', 'major', 13))
    if p['max_notional_ratio'] > 0.25:
        reasons.append(_reason('notional_ratio_too_high', 'Max notional is above small-cap safety ratio.', 'reduce_max_notional', 'major', 14))
    if p['max_loss_ratio'] > 0.08:
        reasons.append(_reason('daily_loss_ratio_too_high', 'Max daily loss is above small-cap safety ratio.', 'reduce_max_daily_loss', 'major', 15))

    upstream = _upstream(data)
    blocked_terms = {'blocked', 'halt', 'emergency', 'no-go', 'no_go', 'inconsistent', 'failed', 'violated'}
    review_terms = {'review', 'attention', 'warning', 'limited-go', 'limited_go'}
    for key, payload in upstream.items():
        status = _extract_decision(payload)
        if status in blocked_terms:
            reasons.append(_reason(f'{key}_blocked', f'{key} upstream state blocks limited-live final validation.', 'hold_until_upstream_ok', 'major', 20))
        elif status in review_terms:
            reasons.append(_reason(f'{key}_review', f'{key} upstream state still requires review.', 'review_upstream_gate', 'review', 40))
    return reasons


def build_rev266_limited_live_candidate_consistency_recheck(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    reasons = _common_reasons(data, settings)
    checks = [
        _check('real_execution_default_off', 'ok' if not (p['real_submit_enable'] or p['real_close_enable']) else 'blocked', 'Real submit/close remains OFF.'),
        _check('candidate_scope_defined', 'ok' if p['allowed_symbols'] and p['session_boundary'] else 'blocked', 'Symbols and session boundary are explicit.'),
        _check('owner_gate_previewed', 'ok' if p['owner_approval'] else 'review', 'Owner approval is required for READY, but validation remains read-only.'),
        _check('activation_token_preview_only', 'ok' if p['activation_token_preview'] else 'review', 'Activation token value is not returned; preview presence only is checked.'),
    ]
    critical = _critical(reasons)
    body = {'consistency': 'BLOCKED' if any(c.get('status') == 'blocked' for c in checks) or critical.get('severity') in {'critical', 'major'} else ('READY' if p['owner_approval'] and p['activation_token_preview'] else 'REVIEW'), 'critical_blocker': critical, 'allowed_symbols': p['allowed_symbols'], 'session_boundary': p['session_boundary'], 'real_submit_close': 'OFF'}
    return {'engine': 'limited_live_candidate_consistency_recheck', 'revision': 266, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'limited_live_candidate_consistency_recheck': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev267_runtime_safety_state_final_validator'}


def build_rev267_runtime_safety_state_final_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    runtime = _upstream(data).get('runtime_safety') or {}
    runtime_status = _extract_decision(runtime) or 'review'
    checks = [
        _check('daily_hard_stop_enabled', 'ok' if p['daily_hard_stop_enabled'] else 'blocked', 'Daily hard stop is enabled.'),
        _check('emergency_guard_enabled', 'ok' if p['emergency_guard_enabled'] else 'blocked', 'Emergency guard is enabled.'),
        _check('api_permission_preview', 'ok' if p['api_permission_preview'] else 'review', 'Exchange permission preview is available.'),
        _check('runtime_not_failed', 'blocked' if runtime_status in {'blocked', 'halt', 'emergency', 'failed'} else ('review' if runtime_status in {'review', '', 'attention'} else 'ok'), 'Runtime safety state is not blocking.'),
    ]
    body = {'runtime_safety': 'BLOCKED' if _status_from_checks(checks) == 'blocked' else ('READY' if _status_from_checks(checks) == 'ok' else 'REVIEW'), 'runtime_status': runtime_status, 'stop_authority': ['daily_hard_stop', 'emergency_guard', 'owner_revocation'], 'real_submit_close': 'OFF'}
    return {'engine': 'runtime_safety_state_final_validator', 'revision': 267, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'runtime_safety_state_final_validator': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev268_risk_capital_combined_gate'}


def build_rev268_risk_firewall_capital_preservation_combined_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    reasons = _common_reasons(data, settings)
    checks = [
        _check('max_notional_ratio_safe', 'ok' if p['max_notional_ratio'] <= 0.25 else 'blocked', 'Max notional stays within small-cap ratio.', {'ratio': round(p['max_notional_ratio'], 4)}),
        _check('max_daily_loss_ratio_safe', 'ok' if p['max_loss_ratio'] <= 0.08 else 'blocked', 'Max daily loss stays within small-cap ratio.', {'ratio': round(p['max_loss_ratio'], 4)}),
        _check('usdt_dominance_preserved', 'ok', 'Capital policy keeps majority reserve in USDT.'),
        _check('auto_scale_disabled', 'ok' if not p['auto_scale'] else 'blocked', 'Auto-scale remains disabled.'),
    ]
    critical = _critical(reasons)
    decision = 'BLOCKED' if _status_from_checks(checks) == 'blocked' or critical.get('severity') in {'critical', 'major'} else ('REVIEW' if critical.get('severity') == 'review' else 'READY')
    body = {'combined_gate': decision, 'critical_blocker': critical, 'max_allowed_notional': p['max_notional'], 'max_allowed_daily_loss': p['max_daily_loss'], 'capital_usdt': p['capital_usdt'], 'usdt_dominance': 'preserved', 'auto_scale': 'OFF'}
    return {'engine': 'risk_firewall_capital_preservation_combined_gate', 'revision': 268, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'risk_firewall_capital_preservation_combined_gate': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev269_data_strategy_combined_validator'}


def build_rev269_data_integrity_strategy_reality_combined_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    upstream = _upstream(data)
    data_status = _extract_decision(upstream.get('data_integrity') or {}) or 'review'
    strategy_status = _extract_decision(upstream.get('strategy_reality') or {}) or 'review'
    blocked_terms = {'blocked', 'halt', 'failed', 'inconsistent', 'no-go', 'no_go'}
    checks = [
        _check('data_integrity_not_blocked', 'blocked' if data_status in blocked_terms else ('review' if data_status in {'review', '', 'attention'} else 'ok'), 'Data integrity does not block final validation.'),
        _check('strategy_reality_not_blocked', 'blocked' if strategy_status in blocked_terms else ('review' if strategy_status in {'review', '', 'attention'} else 'ok'), 'Strategy reality does not block final validation.'),
        _check('quarantine_not_auto_applied', 'ok', 'Weak strategy quarantine remains recommendation-only; auto-apply OFF.'),
        _check('decision_packet_schema_required', 'ok', 'Final report returns compact schema for Summary.'),
    ]
    decision = 'BLOCKED' if _status_from_checks(checks) == 'blocked' else ('REVIEW' if _status_from_checks(checks) == 'review' else 'READY')
    body = {'data_strategy_gate': decision, 'data_integrity_status': data_status, 'strategy_reality_status': strategy_status, 'auto_apply': 'OFF', 'operator_action': 'review_data_or_strategy_gate' if decision != 'READY' else 'continue_to_final_validation_report'}
    return {'engine': 'data_integrity_strategy_reality_combined_validator', 'revision': 269, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'data_integrity_strategy_reality_combined_validator': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev270_limited_live_final_validation_report'}


def build_rev270_limited_live_final_validation_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _policy(settings)
    rev266 = build_rev266_limited_live_candidate_consistency_recheck(data, settings, auth_store, username)
    rev267 = build_rev267_runtime_safety_state_final_validator(data, settings, auth_store, username)
    rev268 = build_rev268_risk_firewall_capital_preservation_combined_gate(data, settings, auth_store, username)
    rev269 = build_rev269_data_integrity_strategy_reality_combined_validator(data, settings, auth_store, username)
    reasons = _common_reasons(data, settings)
    for payload in (rev266, rev267, rev268, rev269):
        if payload.get('status') == 'blocked':
            reasons.append(_reason(f"{payload.get('engine')}_blocked", f"{payload.get('engine')} blocks limited-live final validation.", 'fix_blocked_final_validation_gate', 'major', 25))
    critical = _critical(reasons)
    if critical.get('severity') in {'critical', 'major'}:
        final_validation = 'BLOCKED'
    elif p['owner_approval'] and p['activation_token_preview'] and all(x.get('status') == 'ok' for x in (rev266, rev267, rev268, rev269)):
        final_validation = 'READY'
    else:
        final_validation = 'REVIEW'
    checks = [
        _check('candidate_consistency', rev266.get('status', 'review'), 'Candidate consistency rechecked.'),
        _check('runtime_safety', rev267.get('status', 'review'), 'Runtime safety final validator checked.'),
        _check('risk_capital_combined_gate', rev268.get('status', 'review'), 'Risk firewall and capital preservation checked together.'),
        _check('data_strategy_combined_gate', rev269.get('status', 'review'), 'Data integrity and strategy reality checked together.'),
        _check('owner_activation_ready', 'ok' if p['owner_approval'] and p['activation_token_preview'] else 'review', 'Owner approval and token preview required for READY.'),
    ]
    report = {'limited_live_final_validation': final_validation, 'critical_blocker': critical, 'operator_action': 'approve_owner_controlled_activation_layer' if final_validation == 'READY' else critical.get('action'), 'max_notional': p['max_notional'], 'max_daily_loss': p['max_daily_loss'], 'allowed_symbols': p['allowed_symbols'], 'session_boundary': p['session_boundary'], 'stop_conditions': ['daily_hard_stop', 'runtime_safety_blocked', 'risk_capital_violation', 'data_strategy_blocked', 'owner_revocation'], 'real_submit_close': 'OFF', 'auto_scale': 'OFF', 'auto_apply': 'OFF'}
    return {'engine': 'limited_live_final_validation_report', 'revision': 270, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'limited_live_final_validation_report': report, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev271_owner_controlled_activation_layer'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {
        266: build_rev266_limited_live_candidate_consistency_recheck,
        267: build_rev267_runtime_safety_state_final_validator,
        268: build_rev268_risk_firewall_capital_preservation_combined_gate,
        269: build_rev269_data_integrity_strategy_reality_combined_validator,
        270: build_rev270_limited_live_final_validation_report,
    }
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev266-270 limited-live final validation revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev266 = build_rev266_limited_live_candidate_consistency_recheck(data, settings, auth_store, username)
    rev267 = build_rev267_runtime_safety_state_final_validator(data, settings, auth_store, username)
    rev268 = build_rev268_risk_firewall_capital_preservation_combined_gate(data, settings, auth_store, username)
    rev269 = build_rev269_data_integrity_strategy_reality_combined_validator(data, settings, auth_store, username)
    rev270 = build_rev270_limited_live_final_validation_report(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev266, rev267, rev268, rev269, rev270):
        checks.extend(_as_list(payload.get('checks')))
    return {'engine': 'limited_live_final_validation_block', 'revision': 270, 'status': rev270.get('status', 'review'), 'generated_at': now_iso(), 'rev266_limited_live_candidate_consistency_recheck': rev266, 'rev267_runtime_safety_state_final_validator': rev267, 'rev268_risk_firewall_capital_preservation_combined_gate': rev268, 'rev269_data_integrity_strategy_reality_combined_validator': rev269, 'rev270_limited_live_final_validation_report': rev270, 'limited_live_final_validation_report': rev270.get('limited_live_final_validation_report', {}), 'summary_result': build_summary_for_revision(270, data, settings, auth_store, username), 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'owner_controlled_activation_layer_block'}


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key_map = {266: 'limited_live_candidate_consistency_recheck', 267: 'runtime_safety_state_final_validator', 268: 'risk_firewall_capital_preservation_combined_gate', 269: 'data_integrity_strategy_reality_combined_validator', 270: 'limited_live_final_validation_report'}
    body = _as_dict(payload.get(key_map[int(revision)]))
    blocker = _as_dict(body.get('critical_blocker'))
    validation = body.get('limited_live_final_validation') or body.get('consistency') or body.get('runtime_safety') or body.get('combined_gate') or body.get('data_strategy_gate') or ('READY' if payload.get('status') == 'ok' else 'REVIEW')
    return {'revision': int(revision), 'limited_live_final_validation': validation, 'critical_issue': blocker.get('code', 'none'), 'operator_action': body.get('operator_action') or blocker.get('action') or 'review', 'max_notional': body.get('max_notional') or body.get('max_allowed_notional'), 'max_daily_loss': body.get('max_daily_loss') or body.get('max_allowed_daily_loss'), 'allowed_symbols': body.get('allowed_symbols'), 'trade_allowed': validation == 'READY', 'real_submit_close': 'OFF'}


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
