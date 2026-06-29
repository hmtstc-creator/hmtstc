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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == '':
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'approved', 'ready', 'present', 'valid', 'ok'}


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason('none', 'No first limited-live session blocker.', 'no_action', 'ok', 999)
    weights = {'critical': 0, 'major': 1, 'review': 2, 'minor': 3, 'ok': 4}
    return sorted(reasons, key=lambda r: (weights.get(str(r.get('severity')), 3), int(r.get('priority', 50))))[0]


def _check(name: str, status: str, message: str, detail: dict | None = None) -> dict:
    return {'name': name, 'status': status, 'message': message, 'detail': detail or {}}


def _status_from_checks(checks: list[dict]) -> str:
    statuses = {str(c.get('status', '')).lower() for c in checks}
    if 'blocked' in statuses or 'fail' in statuses:
        return 'blocked'
    if 'review' in statuses or 'attention' in statuses:
        return 'review'
    return 'ok'


def _totals(checks: list[dict]) -> dict:
    return {
        'ok': sum(1 for c in checks if c.get('status') == 'ok'),
        'review': sum(1 for c in checks if c.get('status') == 'review'),
        'blocked': sum(1 for c in checks if c.get('status') == 'blocked'),
        'total': len(checks),
    }


def _command_preview() -> dict:
    return {
        'places_order': False,
        'sends_exchange_request': False,
        'submits_close_order': False,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'emergency_close_default_off': True,
        'auto_scale': False,
        'auto_apply': False,
        'network_default_off': True,
        'approval_gated_only': True,
        'session_control_only': True,
    }


def _settings(settings: dict | None) -> dict:
    root = _as_dict(settings)
    limited = _as_dict(root.get('limited_live'))
    session = _as_dict(root.get('session'))
    risk = _as_dict(root.get('risk'))
    execution = _as_dict(root.get('execution'))
    exchange = _as_dict(root.get('exchange'))
    runtime = _as_dict(root.get('runtime'))

    allowed_symbols = _as_list(limited.get('allowed_symbols') or root.get('allowed_symbols')) or ['BTCUSDT']
    session_id = str(limited.get('session_id') or session.get('session_id') or root.get('session_id') or '').strip()
    session_status = str(session.get('status') or limited.get('session_status') or root.get('session_status') or 'planned').lower()
    return {
        'real_submit_enable': _truthy(limited.get('real_submit_enable') or execution.get('real_submit_enable') or root.get('real_submit_enable')),
        'real_close_enable': _truthy(limited.get('real_close_enable') or execution.get('real_close_enable') or root.get('real_close_enable')),
        'emergency_close_enable': _truthy(limited.get('emergency_close_enable') or execution.get('emergency_close_enable') or root.get('emergency_close_enable')),
        'network_enable': _truthy(exchange.get('network_enable') or execution.get('network_enable') or root.get('network_enable')),
        'owner_approved': _truthy(limited.get('owner_approval') or root.get('owner_approval')),
        'token_preview_present': _truthy(limited.get('activation_token_preview') or root.get('activation_token_preview')),
        'session_id': session_id,
        'session_status': session_status,
        'session_duration_minutes': _safe_int(session.get('duration_minutes', limited.get('session_duration_minutes', root.get('session_duration_minutes', 0))), 0),
        'elapsed_minutes': _safe_int(runtime.get('elapsed_minutes', session.get('elapsed_minutes', root.get('elapsed_minutes', 0))), 0),
        'cooldown_minutes': _safe_int(session.get('cooldown_minutes', limited.get('cooldown_minutes', root.get('cooldown_minutes', 15))), 15),
        'cooldown_active': _truthy(runtime.get('cooldown_active') or session.get('cooldown_active') or root.get('cooldown_active')),
        'session_timed_out': _truthy(runtime.get('session_timed_out') or session.get('session_timed_out') or root.get('session_timed_out')),
        'max_notional': _safe_float(limited.get('max_notional', root.get('max_notional', 0)), 0),
        'max_daily_loss': _safe_float(limited.get('max_daily_loss', root.get('max_daily_loss', 0)), 0),
        'session_max_loss': _safe_float(session.get('max_loss', limited.get('session_max_loss', root.get('session_max_loss', 0))), 0),
        'current_session_loss': _safe_float(runtime.get('current_session_loss', session.get('current_loss', root.get('current_session_loss', 0))), 0),
        'current_notional': _safe_float(runtime.get('current_notional', session.get('current_notional', root.get('current_notional', 0))), 0),
        'open_positions': _safe_int(runtime.get('open_positions', session.get('open_positions', root.get('open_positions', 0))), 0),
        'pending_orders': _safe_int(runtime.get('pending_orders', session.get('pending_orders', root.get('pending_orders', 0))), 0),
        'allowed_symbols': [str(s).upper().strip() for s in allowed_symbols if str(s).strip()],
        'selected_symbol': str(session.get('symbol') or limited.get('symbol') or root.get('symbol') or 'BTCUSDT').upper().strip(),
        'risk_firewall_status': str(risk.get('firewall_status') or root.get('risk_firewall_status') or 'review').lower(),
        'capital_status': str(risk.get('capital_status') or root.get('capital_status') or 'review').lower(),
        'halt_requested': _truthy(runtime.get('halt_requested') or session.get('halt_requested') or root.get('halt_requested')),
        'emergency_triggered': _truthy(runtime.get('emergency_triggered') or session.get('emergency_triggered') or root.get('emergency_triggered')),
        'manual_attention': _truthy(runtime.get('manual_attention') or session.get('manual_attention') or root.get('manual_attention')),
        'daily_hard_stop_enabled': _truthy(limited.get('daily_hard_stop_enabled', root.get('daily_hard_stop_enabled', True))) or True,
        'emergency_guard_enabled': _truthy(limited.get('emergency_guard_enabled', root.get('emergency_guard_enabled', True))) or True,
    }


def _base_reasons(settings: dict | None) -> list[dict]:
    p = _settings(settings)
    reasons: list[dict] = []
    if p['real_submit_enable'] or p['real_close_enable'] or p['emergency_close_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Real submit/close flags must remain default OFF during first-session control.', 'disable_real_execution_flags', 'critical', 1))
    if p['network_enable']:
        reasons.append(_reason('network_flag_enabled', 'Network execution must stay OFF until approval-gated live activation.', 'disable_network_execution', 'critical', 2))
    if not p['owner_approved']:
        reasons.append(_reason('owner_approval_missing', 'Owner approval is required for first limited-live session readiness.', 'request_owner_approval', 'major', 8))
    if not p['token_preview_present']:
        reasons.append(_reason('activation_token_preview_missing', 'Activation token preview presence is required; token value must never be returned.', 'generate_token_preview', 'major', 10))
    if not p['session_id']:
        reasons.append(_reason('session_boundary_missing', 'First limited-live session requires a session ID.', 'create_session_boundary', 'major', 12))
    if p['max_notional'] <= 0:
        reasons.append(_reason('max_notional_missing', 'Max notional must be explicit for first session.', 'set_max_notional', 'major', 14))
    if p['max_daily_loss'] <= 0 and p['session_max_loss'] <= 0:
        reasons.append(_reason('max_loss_missing', 'Daily/session max loss must be explicit.', 'set_session_max_loss', 'major', 15))
    if p['selected_symbol'] not in p['allowed_symbols']:
        reasons.append(_reason('symbol_not_whitelisted', 'Selected first-session symbol is not in whitelist.', 'select_whitelisted_symbol', 'critical', 6))
    return reasons


def build_rev281_first_session_boundary_contract(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    reasons = _base_reasons(settings)
    checks = [
        _check('session_id_present', 'ok' if p['session_id'] else 'blocked', 'Session ID must exist.'),
        _check('owner_approval_present', 'ok' if p['owner_approved'] else 'blocked', 'Owner approval must bind the session.'),
        _check('token_preview_present', 'ok' if p['token_preview_present'] else 'blocked', 'Token preview presence must exist without returning token value.'),
        _check('duration_explicit', 'ok' if p['session_duration_minutes'] > 0 else 'blocked', 'Session duration must be explicit.'),
        _check('symbol_whitelisted', 'ok' if p['selected_symbol'] in p['allowed_symbols'] else 'blocked', 'Session symbol must be whitelisted.'),
    ]
    body = {
        'session_boundary': 'BOUND' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'session_id': p['session_id'] or None,
        'selected_symbol': p['selected_symbol'],
        'allowed_symbols': p['allowed_symbols'],
        'duration_minutes': p['session_duration_minutes'],
        'token_value_returned': False,
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'first_session_boundary_contract', 'revision': 281, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'first_session_boundary_contract': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev282_session_max_loss_max_notional_enforcement'}


def build_rev282_session_max_loss_max_notional_enforcement(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    reasons = _base_reasons(settings)
    loss_limit = p['session_max_loss'] if p['session_max_loss'] > 0 else p['max_daily_loss']
    if loss_limit > 0 and abs(p['current_session_loss']) >= loss_limit:
        reasons.append(_reason('session_loss_limit_reached', 'Session loss reached or exceeded the configured max loss.', 'halt_session', 'critical', 3))
    if p['max_notional'] > 0 and p['current_notional'] > p['max_notional']:
        reasons.append(_reason('session_notional_exceeded', 'Current session notional exceeds max notional.', 'halt_and_reduce_exposure', 'critical', 4))
    checks = [
        _check('max_notional_explicit', 'ok' if p['max_notional'] > 0 else 'blocked', 'Max notional must be explicit.'),
        _check('max_loss_explicit', 'ok' if loss_limit > 0 else 'blocked', 'Max session/daily loss must be explicit.'),
        _check('notional_within_limit', 'ok' if p['max_notional'] > 0 and p['current_notional'] <= p['max_notional'] else 'blocked', 'Session notional must stay within limit.'),
        _check('loss_within_limit', 'ok' if loss_limit > 0 and abs(p['current_session_loss']) < loss_limit else 'blocked', 'Session loss must stay below limit.'),
        _check('daily_hard_stop_enabled', 'ok' if p['daily_hard_stop_enabled'] else 'blocked', 'Daily hard stop must be enabled.'),
    ]
    body = {
        'session_limits': 'ENFORCED' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'max_notional': p['max_notional'],
        'max_session_loss': loss_limit,
        'current_notional': p['current_notional'],
        'current_session_loss': p['current_session_loss'],
        'trade_allowed': _status_from_checks(checks) == 'ok',
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'session_max_loss_max_notional_enforcement', 'revision': 282, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'session_max_loss_max_notional_enforcement': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev283_session_timeout_cooldown_controller'}


def build_rev283_session_timeout_cooldown_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    reasons = _base_reasons(settings)
    timed_out_by_elapsed = p['session_duration_minutes'] > 0 and p['elapsed_minutes'] >= p['session_duration_minutes']
    if timed_out_by_elapsed or p['session_timed_out']:
        reasons.append(_reason('session_timeout_reached', 'Session timeout reached; new trades must stop.', 'cooldown_session', 'major', 20))
    if p['cooldown_active']:
        reasons.append(_reason('cooldown_active', 'Cooldown is active; hold new entries.', 'wait_for_cooldown', 'major', 22))
    checks = [
        _check('duration_configured', 'ok' if p['session_duration_minutes'] > 0 else 'blocked', 'Session duration must be configured.'),
        _check('session_not_timed_out', 'ok' if not (timed_out_by_elapsed or p['session_timed_out']) else 'review', 'Timed-out sessions should not accept new trades.'),
        _check('cooldown_not_active', 'ok' if not p['cooldown_active'] else 'review', 'Cooldown suppresses new opportunities.'),
        _check('cooldown_minutes_configured', 'ok' if p['cooldown_minutes'] > 0 else 'blocked', 'Cooldown minutes must be configured.'),
    ]
    body = {
        'timeout_cooldown': 'ACTIVE_HOLD' if (timed_out_by_elapsed or p['session_timed_out'] or p['cooldown_active']) else ('READY' if _status_from_checks(checks) == 'ok' else 'BLOCKED'),
        'duration_minutes': p['session_duration_minutes'],
        'elapsed_minutes': p['elapsed_minutes'],
        'cooldown_minutes': p['cooldown_minutes'],
        'cooldown_active': p['cooldown_active'],
        'new_trade_allowed': _status_from_checks(checks) == 'ok',
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'session_timeout_cooldown_controller', 'revision': 283, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'session_timeout_cooldown_controller': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev284_session_halt_emergency_state_router'}


def build_rev284_session_halt_emergency_state_router(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    reasons = _base_reasons(settings)
    if p['emergency_triggered']:
        reasons.append(_reason('emergency_triggered', 'Emergency state is active; session must stop.', 'emergency_stop_session', 'critical', 1))
    if p['halt_requested']:
        reasons.append(_reason('halt_requested', 'Halt state is active; no new live action allowed.', 'halt_session', 'critical', 2))
    if p['manual_attention']:
        reasons.append(_reason('manual_attention_required', 'Manual attention is required before continuing.', 'review_session_attention', 'major', 11))
    checks = [
        _check('emergency_guard_enabled', 'ok' if p['emergency_guard_enabled'] else 'blocked', 'Emergency guard must be enabled.'),
        _check('no_emergency_trigger', 'ok' if not p['emergency_triggered'] else 'blocked', 'Emergency state blocks the session.'),
        _check('no_halt_requested', 'ok' if not p['halt_requested'] else 'blocked', 'Halt state blocks the session.'),
        _check('manual_attention_clear', 'ok' if not p['manual_attention'] else 'review', 'Manual attention requires review.'),
        _check('real_emergency_close_default_off', 'ok' if not p['emergency_close_enable'] else 'blocked', 'Emergency close submitter remains default OFF.'),
    ]
    body = {
        'session_state_router': 'EMERGENCY' if p['emergency_triggered'] else ('HALT' if p['halt_requested'] else ('ATTENTION' if p['manual_attention'] else 'CLEAR')),
        'emergency_guard_enabled': p['emergency_guard_enabled'],
        'real_emergency_close': 'OFF',
        'auto_close': 'OFF',
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'session_halt_emergency_state_router', 'revision': 284, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'session_halt_emergency_state_router': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev285_first_limited_live_session_decision_packet'}


def build_rev285_first_limited_live_session_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev281 = build_rev281_first_session_boundary_contract(data, settings, auth_store, username)
    rev282 = build_rev282_session_max_loss_max_notional_enforcement(data, settings, auth_store, username)
    rev283 = build_rev283_session_timeout_cooldown_controller(data, settings, auth_store, username)
    rev284 = build_rev284_session_halt_emergency_state_router(data, settings, auth_store, username)
    checks: list[dict] = []
    reasons: list[dict] = []
    for payload, key in ((rev281, 'first_session_boundary_contract'), (rev282, 'session_max_loss_max_notional_enforcement'), (rev283, 'session_timeout_cooldown_controller'), (rev284, 'session_halt_emergency_state_router')):
        checks.extend(_as_list(payload.get('checks')))
        body = _as_dict(payload.get(key))
        blocker = _as_dict(body.get('critical_blocker'))
        if blocker.get('code') and blocker.get('code') != 'none':
            reasons.append(blocker)
    status = _status_from_checks(checks)
    blocker = _critical(reasons)
    p = _settings(settings)
    if status == 'ok':
        decision = 'LIMITED_SESSION_READY'
    elif blocker.get('severity') == 'critical' or status == 'blocked':
        decision = 'NO_GO'
    else:
        decision = 'REVIEW'
    packet = {
        'first_limited_live_session': decision,
        'session_id': p['session_id'] or None,
        'selected_symbol': p['selected_symbol'],
        'allowed_symbols': p['allowed_symbols'],
        'max_notional': p['max_notional'],
        'max_session_loss': p['session_max_loss'] if p['session_max_loss'] > 0 else p['max_daily_loss'],
        'duration_minutes': p['session_duration_minutes'],
        'cooldown_minutes': p['cooldown_minutes'],
        'stop_conditions': ['max_loss', 'max_notional', 'timeout', 'cooldown', 'manual_attention', 'halt', 'emergency'],
        'owner_action': blocker.get('action') if blocker.get('code') != 'none' else 'owner_may_start_approval_gated_session_preview',
        'critical_blocker': blocker,
        'real_submit_close': 'OFF',
        'emergency_close': 'OFF',
        'network': 'OFF',
        'auto_scale': 'OFF',
        'auto_apply': 'OFF',
    }
    return {'engine': 'first_limited_live_session_decision_packet', 'revision': 285, 'status': status, 'generated_at': now_iso(), 'first_limited_live_session_decision_packet': packet, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev286_live_result_reconciliation_freeze_block'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {
        281: build_rev281_first_session_boundary_contract,
        282: build_rev282_session_max_loss_max_notional_enforcement,
        283: build_rev283_session_timeout_cooldown_controller,
        284: build_rev284_session_halt_emergency_state_router,
        285: build_rev285_first_limited_live_session_decision_packet,
    }
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev281-285 first limited-live session control revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev281 = build_rev281_first_session_boundary_contract(data, settings, auth_store, username)
    rev282 = build_rev282_session_max_loss_max_notional_enforcement(data, settings, auth_store, username)
    rev283 = build_rev283_session_timeout_cooldown_controller(data, settings, auth_store, username)
    rev284 = build_rev284_session_halt_emergency_state_router(data, settings, auth_store, username)
    rev285 = build_rev285_first_limited_live_session_decision_packet(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev281, rev282, rev283, rev284, rev285):
        checks.extend(_as_list(payload.get('checks')))
    return {
        'engine': 'first_limited_live_session_control_block',
        'revision': 285,
        'status': rev285.get('status', 'review'),
        'generated_at': now_iso(),
        'rev281_first_session_boundary_contract': rev281,
        'rev282_session_max_loss_max_notional_enforcement': rev282,
        'rev283_session_timeout_cooldown_controller': rev283,
        'rev284_session_halt_emergency_state_router': rev284,
        'rev285_first_limited_live_session_decision_packet': rev285,
        'first_limited_live_session_decision_packet': rev285.get('first_limited_live_session_decision_packet', {}),
        'summary_result': build_summary_for_revision(285, data, settings, auth_store, username),
        'checks': checks,
        'check_totals': _totals(checks),
        'command_preview': _command_preview(),
        'contains_secret': False,
        'secret_values_returned': False,
        'next_allowed_step': 'live_result_reconciliation_freeze_block',
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key_map = {
        281: 'first_session_boundary_contract',
        282: 'session_max_loss_max_notional_enforcement',
        283: 'session_timeout_cooldown_controller',
        284: 'session_halt_emergency_state_router',
        285: 'first_limited_live_session_decision_packet',
    }
    body = _as_dict(payload.get(key_map[int(revision)]))
    blocker = _as_dict(body.get('critical_blocker'))
    decision = body.get('first_limited_live_session') or body.get('session_boundary') or body.get('session_limits') or body.get('timeout_cooldown') or body.get('session_state_router') or ('READY' if payload.get('status') == 'ok' else 'REVIEW')
    return {
        'revision': int(revision),
        'first_limited_live_session': decision,
        'critical_issue': blocker.get('code', 'none'),
        'owner_action': body.get('owner_action') or body.get('operator_action') or blocker.get('action') or 'review',
        'session_id': body.get('session_id'),
        'selected_symbol': body.get('selected_symbol'),
        'max_notional': body.get('max_notional'),
        'max_session_loss': body.get('max_session_loss'),
        'duration_minutes': body.get('duration_minutes'),
        'cooldown_minutes': body.get('cooldown_minutes'),
        'stop_conditions': body.get('stop_conditions'),
        'trade_allowed': decision == 'LIMITED_SESSION_READY',
        'real_submit_close': 'OFF',
        'emergency_close': 'OFF',
        'network': 'OFF',
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    command = _as_dict(payload.get('command_preview'))
    failures = []
    if command.get('places_order') or command.get('sends_exchange_request') or command.get('submits_close_order'):
        failures.append('unexpected_execution_side_effect')
    if command.get('real_submit_default_off') is not True or command.get('real_close_default_off') is not True or command.get('emergency_close_default_off') is not True:
        failures.append('real_execution_not_default_off')
    if command.get('auto_scale') or command.get('auto_apply'):
        failures.append('auto_scale_or_apply_enabled')
    if payload.get('contains_secret') or payload.get('secret_values_returned'):
        failures.append('secret_leak')
    return {'quality_gate': 'FAIL' if failures else 'PASS', 'revision': int(revision), 'engine': payload.get('engine'), 'status': payload.get('status'), 'failures': failures, 'command_preview': command, 'checked_at': now_iso()}
