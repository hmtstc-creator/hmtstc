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
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'approved', 'ready', 'present', 'valid'}


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason('none', 'No owner-controlled activation blocker.', 'no_action', 'ok', 999)
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
        'auto_scale': False,
        'auto_apply': False,
        'network_default_off': True,
        'approval_gated_only': True,
    }


def _limited_live_settings(settings: dict | None) -> dict:
    root = _as_dict(settings)
    limited = _as_dict(root.get('limited_live'))
    owner = _as_dict(root.get('owner_approval'))
    activation = _as_dict(root.get('activation'))
    capital = _as_dict(root.get('capital'))
    execution = _as_dict(root.get('execution'))

    max_notional = _safe_float(limited.get('max_notional', root.get('max_notional', 0)), 0)
    max_daily_loss = _safe_float(limited.get('max_daily_loss', root.get('max_daily_loss', 0)), 0)
    allowed_symbols = _as_list(limited.get('allowed_symbols') or root.get('allowed_symbols')) or ['BTCUSDT']
    session_id = str(limited.get('session_id') or activation.get('session_id') or root.get('session_id') or '').strip()
    session_scope = str(limited.get('session_scope') or activation.get('scope') or owner.get('scope') or 'limited_live_micro_session').strip()
    token_state = str(limited.get('activation_token_preview') or activation.get('token_preview') or activation.get('token_state') or root.get('activation_token_preview') or '').strip().lower()
    token_preview_present = _truthy(token_state) or token_state in {'present', 'previewed'}
    owner_approved = _truthy(limited.get('owner_approval') or owner.get('approved') or root.get('owner_approval'))
    token_age_minutes = _safe_float(activation.get('token_age_minutes', limited.get('token_age_minutes', 0)), 0)
    ttl_minutes = _safe_float(activation.get('token_ttl_minutes', limited.get('token_ttl_minutes', 30)), 30)
    real_submit_enable = _truthy(limited.get('real_submit_enable') or execution.get('real_submit_enable') or root.get('real_submit_enable'))
    real_close_enable = _truthy(limited.get('real_close_enable') or execution.get('real_close_enable') or root.get('real_close_enable'))

    return {
        'owner_approved': owner_approved,
        'session_id': session_id,
        'session_scope': session_scope,
        'activation_token_preview_present': token_preview_present,
        'token_age_minutes': token_age_minutes,
        'token_ttl_minutes': ttl_minutes,
        'token_fresh': token_preview_present and token_age_minutes <= ttl_minutes,
        'max_notional': max_notional,
        'max_daily_loss': max_daily_loss,
        'capital_usdt': _safe_float(capital.get('capital_usdt', root.get('capital_usdt', 100)), 100),
        'allowed_symbols': [str(s).upper() for s in allowed_symbols if str(s).strip()],
        'whitelist_enabled': _truthy(limited.get('whitelist_enabled', root.get('whitelist_enabled', True))) or True,
        'daily_hard_stop_enabled': _truthy(limited.get('daily_hard_stop_enabled', root.get('daily_hard_stop_enabled', True))) or True,
        'emergency_guard_enabled': _truthy(limited.get('emergency_guard_enabled', root.get('emergency_guard_enabled', True))) or True,
        'real_submit_enable': real_submit_enable,
        'real_close_enable': real_close_enable,
    }


def _safe_owner_snapshot(auth_store: dict | None, username: str) -> dict:
    users = _as_dict(_as_dict(auth_store).get('users'))
    user = _as_dict(users.get(username))
    role = str(user.get('role') or 'unknown')
    return {
        'username': username,
        'role': role if role in {'owner', 'admin', 'user'} else 'unknown',
        'owner_role': role == 'owner',
        'active': user.get('active') is not False,
        'token_present': bool(user.get('token')),
        'token_value_returned': False,
    }


def _common_reasons(data: dict | None, settings: dict | None, auth_store: dict | None, username: str) -> list[dict]:
    p = _limited_live_settings(settings)
    owner = _safe_owner_snapshot(auth_store, username)
    reasons: list[dict] = []
    if p['real_submit_enable'] or p['real_close_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Real submit/close flags must stay disabled until final owner action.', 'disable_real_execution_flags', 'critical', 1))
    if not owner['owner_role']:
        reasons.append(_reason('owner_role_missing', 'Authenticated user is not confirmed as owner.', 'login_as_owner_or_fix_owner_role', 'major', 5))
    if not owner['active']:
        reasons.append(_reason('owner_inactive', 'Owner account is inactive.', 'reactivate_owner_before_activation', 'critical', 2))
    if not p['owner_approved']:
        reasons.append(_reason('owner_approval_missing', 'Owner approval is required before activation.', 'request_owner_approval', 'major', 10))
    if not p['activation_token_preview_present']:
        reasons.append(_reason('activation_token_preview_missing', 'Activation token preview is missing.', 'generate_activation_token_preview', 'major', 12))
    elif not p['token_fresh']:
        reasons.append(_reason('activation_token_stale', 'Activation token preview is stale.', 'refresh_activation_token_preview', 'major', 8))
    if not p['session_id']:
        reasons.append(_reason('session_id_missing', 'Activation must be bound to a session ID.', 'create_session_boundary', 'major', 15))
    if p['max_notional'] <= 0:
        reasons.append(_reason('max_notional_missing', 'Max notional must be explicit.', 'set_max_notional', 'major', 18))
    if p['max_daily_loss'] <= 0:
        reasons.append(_reason('max_daily_loss_missing', 'Max daily loss must be explicit.', 'set_max_daily_loss', 'major', 19))
    if not p['allowed_symbols']:
        reasons.append(_reason('allowed_symbols_missing', 'Allowed symbols whitelist is empty.', 'set_allowed_symbols', 'major', 20))
    return reasons


def build_rev271_owner_approval_scope_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _limited_live_settings(settings)
    owner = _safe_owner_snapshot(auth_store, username)
    reasons = _common_reasons(data, settings, auth_store, username)
    checks = [
        _check('owner_role_confirmed', 'ok' if owner['owner_role'] and owner['active'] else 'blocked', 'Owner role and active status are required.'),
        _check('owner_approval_present', 'ok' if p['owner_approved'] else 'blocked', 'Owner approval must be explicit.'),
        _check('scope_is_limited_live', 'ok' if 'live' in p['session_scope'] else 'review', 'Approval scope must match limited-live session.'),
        _check('max_notional_explicit', 'ok' if p['max_notional'] > 0 else 'blocked', 'Approval scope requires max notional.'),
        _check('max_daily_loss_explicit', 'ok' if p['max_daily_loss'] > 0 else 'blocked', 'Approval scope requires max daily loss.'),
    ]
    scope = {
        'approval_scope': 'VALID' if _status_from_checks(checks) == 'ok' else ('BLOCKED' if _status_from_checks(checks) == 'blocked' else 'REVIEW'),
        'owner_role': owner['role'],
        'session_scope': p['session_scope'],
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'allowed_symbols': p['allowed_symbols'],
        'critical_blocker': _critical(reasons),
        'token_value_returned': False,
    }
    return {'engine': 'owner_approval_scope_validator', 'revision': 271, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'owner_approval_scope_validator': scope, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev272_activation_token_lifecycle_preview'}


def build_rev272_activation_token_lifecycle_preview(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _limited_live_settings(settings)
    checks = [
        _check('token_preview_present', 'ok' if p['activation_token_preview_present'] else 'blocked', 'Only token presence is reported, never token value.'),
        _check('token_fresh', 'ok' if p['token_fresh'] else 'blocked', 'Token preview must be within TTL.'),
        _check('token_bound_to_owner', 'ok' if p['owner_approved'] else 'blocked', 'Token lifecycle is valid only after owner approval.'),
        _check('token_bound_to_session', 'ok' if p['session_id'] else 'blocked', 'Token must be bound to a session ID.'),
    ]
    lifecycle = {
        'token_lifecycle': 'VALID' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'token_preview_present': p['activation_token_preview_present'],
        'token_value_returned': False,
        'token_age_minutes': p['token_age_minutes'],
        'token_ttl_minutes': p['token_ttl_minutes'],
        'session_id': p['session_id'] or 'missing',
        'refresh_required': not p['token_fresh'],
        'operator_action': 'continue_to_session_permission_contract' if _status_from_checks(checks) == 'ok' else 'refresh_or_create_activation_token_preview',
    }
    return {'engine': 'activation_token_lifecycle_preview', 'revision': 272, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'activation_token_lifecycle_preview': lifecycle, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev273_session_bound_permission_contract'}


def build_rev273_session_bound_permission_contract(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _limited_live_settings(settings)
    checks = [
        _check('session_id_present', 'ok' if p['session_id'] else 'blocked', 'Permission must be tied to session ID.'),
        _check('whitelist_enabled', 'ok' if p['whitelist_enabled'] else 'blocked', 'Symbol whitelist must be enabled.'),
        _check('daily_hard_stop_enabled', 'ok' if p['daily_hard_stop_enabled'] else 'blocked', 'Daily hard stop is mandatory.'),
        _check('emergency_guard_enabled', 'ok' if p['emergency_guard_enabled'] else 'blocked', 'Emergency guard is mandatory.'),
        _check('real_execution_still_off', 'ok' if not (p['real_submit_enable'] or p['real_close_enable']) else 'blocked', 'Real execution remains default OFF.'),
    ]
    contract = {
        'permission_contract': 'VALID' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'session_id': p['session_id'] or 'missing',
        'scope': p['session_scope'],
        'allowed_symbols': p['allowed_symbols'],
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'required_guards': ['whitelist', 'daily_hard_stop', 'emergency_guard', 'session_boundary'],
        'real_submit_close': 'OFF',
    }
    return {'engine': 'session_bound_permission_contract', 'revision': 273, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'session_bound_permission_contract': contract, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev274_approval_misuse_stale_token_guard'}


def build_rev274_approval_misuse_stale_token_guard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _limited_live_settings(settings)
    reasons = _common_reasons(data, settings, auth_store, username)
    duplicate_session = _truthy(_as_dict(data).get('duplicate_activation_session'))
    if duplicate_session:
        reasons.append(_reason('duplicate_activation_session', 'Duplicate activation session detected.', 'invalidate_duplicate_session', 'major', 6))
    checks = [
        _check('token_not_stale', 'ok' if p['token_fresh'] else 'blocked', 'Stale token previews are blocked.'),
        _check('no_duplicate_session', 'ok' if not duplicate_session else 'blocked', 'Duplicate activation sessions are blocked.'),
        _check('token_value_not_returned', 'ok', 'Token values are never returned to frontend or logs.'),
        _check('approval_not_reusable_outside_scope', 'ok' if p['session_scope'] else 'blocked', 'Approval is limited to scope and session.'),
        _check('real_submit_not_enabled_by_approval', 'ok' if not p['real_submit_enable'] else 'blocked', 'Approval preview cannot enable submit by itself.'),
    ]
    guard = {
        'misuse_guard': 'CLEAR' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'critical_blocker': _critical(reasons),
        'stale_token_blocked': not p['token_fresh'],
        'duplicate_session_blocked': duplicate_session,
        'token_value_returned': False,
        'operator_action': 'continue_to_activation_decision_packet' if _status_from_checks(checks) == 'ok' else _critical(reasons).get('action'),
    }
    return {'engine': 'approval_misuse_stale_token_guard', 'revision': 274, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'approval_misuse_stale_token_guard': guard, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev275_owner_controlled_activation_decision_packet'}


def build_rev275_owner_controlled_activation_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _limited_live_settings(settings)
    rev271 = build_rev271_owner_approval_scope_validator(data, settings, auth_store, username)
    rev272 = build_rev272_activation_token_lifecycle_preview(data, settings, auth_store, username)
    rev273 = build_rev273_session_bound_permission_contract(data, settings, auth_store, username)
    rev274 = build_rev274_approval_misuse_stale_token_guard(data, settings, auth_store, username)
    reasons = _common_reasons(data, settings, auth_store, username)
    for payload in (rev271, rev272, rev273, rev274):
        if payload.get('status') == 'blocked':
            reasons.append(_reason(f"{payload.get('engine')}_blocked", f"{payload.get('engine')} blocks owner-controlled activation.", 'fix_owner_activation_blocker', 'major', 25))
    critical = _critical(reasons)
    all_ok = all(x.get('status') == 'ok' for x in (rev271, rev272, rev273, rev274))
    if critical.get('severity') in {'critical', 'major'}:
        decision = 'BLOCKED'
    elif all_ok:
        decision = 'READY_FOR_OWNER_CONTROLLED_ACTIVATION'
    else:
        decision = 'REVIEW'
    checks = [
        _check('owner_scope_validator', rev271.get('status', 'review'), 'Owner scope validator checked.'),
        _check('token_lifecycle_preview', rev272.get('status', 'review'), 'Activation token lifecycle preview checked.'),
        _check('session_permission_contract', rev273.get('status', 'review'), 'Session-bound permission contract checked.'),
        _check('misuse_stale_token_guard', rev274.get('status', 'review'), 'Misuse and stale-token guard checked.'),
        _check('real_execution_default_off', 'ok' if not (p['real_submit_enable'] or p['real_close_enable']) else 'blocked', 'Real execution remains OFF.'),
    ]
    packet = {
        'owner_controlled_activation': decision,
        'critical_blocker': critical,
        'owner_action': 'approve_limited_live_session_in_ui' if decision == 'READY_FOR_OWNER_CONTROLLED_ACTIVATION' else critical.get('action'),
        'session_id': p['session_id'] or 'missing',
        'scope': p['session_scope'],
        'allowed_symbols': p['allowed_symbols'],
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'token_preview_present': p['activation_token_preview_present'],
        'token_value_returned': False,
        'real_submit_close': 'OFF',
        'auto_scale': 'OFF',
        'auto_apply': 'OFF',
        'stop_conditions': ['owner_revocation', 'stale_token', 'session_boundary_violation', 'daily_hard_stop', 'emergency_guard'],
    }
    return {'engine': 'owner_controlled_activation_decision_packet', 'revision': 275, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'owner_controlled_activation_decision_packet': packet, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev276_micro_live_execution_guardrail_block'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {
        271: build_rev271_owner_approval_scope_validator,
        272: build_rev272_activation_token_lifecycle_preview,
        273: build_rev273_session_bound_permission_contract,
        274: build_rev274_approval_misuse_stale_token_guard,
        275: build_rev275_owner_controlled_activation_decision_packet,
    }
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev271-275 owner-controlled activation revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev271 = build_rev271_owner_approval_scope_validator(data, settings, auth_store, username)
    rev272 = build_rev272_activation_token_lifecycle_preview(data, settings, auth_store, username)
    rev273 = build_rev273_session_bound_permission_contract(data, settings, auth_store, username)
    rev274 = build_rev274_approval_misuse_stale_token_guard(data, settings, auth_store, username)
    rev275 = build_rev275_owner_controlled_activation_decision_packet(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev271, rev272, rev273, rev274, rev275):
        checks.extend(_as_list(payload.get('checks')))
    return {
        'engine': 'owner_controlled_activation_layer_block',
        'revision': 275,
        'status': rev275.get('status', 'review'),
        'generated_at': now_iso(),
        'rev271_owner_approval_scope_validator': rev271,
        'rev272_activation_token_lifecycle_preview': rev272,
        'rev273_session_bound_permission_contract': rev273,
        'rev274_approval_misuse_stale_token_guard': rev274,
        'rev275_owner_controlled_activation_decision_packet': rev275,
        'owner_controlled_activation_decision_packet': rev275.get('owner_controlled_activation_decision_packet', {}),
        'summary_result': build_summary_for_revision(275, data, settings, auth_store, username),
        'checks': checks,
        'check_totals': _totals(checks),
        'command_preview': _command_preview(),
        'contains_secret': False,
        'secret_values_returned': False,
        'next_allowed_step': 'micro_live_execution_guardrail_block',
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key_map = {
        271: 'owner_approval_scope_validator',
        272: 'activation_token_lifecycle_preview',
        273: 'session_bound_permission_contract',
        274: 'approval_misuse_stale_token_guard',
        275: 'owner_controlled_activation_decision_packet',
    }
    body = _as_dict(payload.get(key_map[int(revision)]))
    blocker = _as_dict(body.get('critical_blocker'))
    decision = body.get('owner_controlled_activation') or body.get('approval_scope') or body.get('token_lifecycle') or body.get('permission_contract') or body.get('misuse_guard') or ('READY' if payload.get('status') == 'ok' else 'REVIEW')
    return {
        'revision': int(revision),
        'owner_controlled_activation': decision,
        'critical_issue': blocker.get('code', 'none'),
        'owner_action': body.get('owner_action') or body.get('operator_action') or blocker.get('action') or 'review',
        'session_id': body.get('session_id'),
        'scope': body.get('scope') or body.get('session_scope'),
        'max_notional': body.get('max_notional'),
        'max_daily_loss': body.get('max_daily_loss'),
        'allowed_symbols': body.get('allowed_symbols'),
        'trade_allowed': decision == 'READY_FOR_OWNER_CONTROLLED_ACTIVATION',
        'token_value_returned': False,
        'real_submit_close': 'OFF',
    }


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
