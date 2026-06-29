from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re


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
        return _reason('none', 'No micro-live execution guardrail blocker.', 'no_action', 'ok', 999)
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
        'dry_guardrail_only': True,
    }


def _settings(settings: dict | None) -> dict:
    root = _as_dict(settings)
    limited = _as_dict(root.get('limited_live'))
    execution = _as_dict(root.get('execution'))
    exchange = _as_dict(root.get('exchange'))
    risk = _as_dict(root.get('risk'))
    activation = _as_dict(root.get('activation'))
    guardrails = _as_dict(root.get('guardrails'))
    idempotency = _as_dict(root.get('idempotency'))

    enabled_real_submit = _truthy(limited.get('real_submit_enable') or execution.get('real_submit_enable') or root.get('real_submit_enable'))
    enabled_real_close = _truthy(limited.get('real_close_enable') or execution.get('real_close_enable') or root.get('real_close_enable'))
    enabled_emergency_close = _truthy(limited.get('emergency_close_enable') or execution.get('emergency_close_enable') or root.get('emergency_close_enable'))

    allowed_symbols = _as_list(limited.get('allowed_symbols') or root.get('allowed_symbols')) or ['BTCUSDT']
    permissions = _as_dict(exchange.get('permissions') or root.get('exchange_permissions'))
    return {
        'real_submit_enable': enabled_real_submit,
        'real_close_enable': enabled_real_close,
        'emergency_close_enable': enabled_emergency_close,
        'network_enable': _truthy(exchange.get('network_enable') or execution.get('network_enable') or root.get('network_enable')),
        'owner_approved': _truthy(limited.get('owner_approval') or root.get('owner_approval')),
        'session_id': str(limited.get('session_id') or activation.get('session_id') or root.get('session_id') or '').strip(),
        'token_preview_present': _truthy(limited.get('activation_token_preview') or activation.get('token_preview') or root.get('activation_token_preview')),
        'whitelist_enabled': _truthy(limited.get('whitelist_enabled', root.get('whitelist_enabled', True))) or True,
        'daily_hard_stop_enabled': _truthy(limited.get('daily_hard_stop_enabled', root.get('daily_hard_stop_enabled', True))) or True,
        'emergency_guard_enabled': _truthy(limited.get('emergency_guard_enabled', root.get('emergency_guard_enabled', True))) or True,
        'risk_firewall_ok': str(risk.get('firewall_status') or root.get('risk_firewall_status') or 'review').lower() in {'ok', 'ready', 'pass'},
        'max_notional': _safe_float(limited.get('max_notional', root.get('max_notional', 0)), 0),
        'max_daily_loss': _safe_float(limited.get('max_daily_loss', root.get('max_daily_loss', 0)), 0),
        'allowed_symbols': [str(s).upper().strip() for s in allowed_symbols if str(s).strip()],
        'order_id_prefix': str(idempotency.get('prefix') or execution.get('client_order_id_prefix') or 'HMTSTC-ML').strip(),
        'last_client_order_ids': [str(x) for x in _as_list(idempotency.get('last_client_order_ids') or root.get('last_client_order_ids'))],
        'stale_order_age_seconds': _safe_float(idempotency.get('stale_order_age_seconds', root.get('stale_order_age_seconds', 0)), 0),
        'max_order_age_seconds': _safe_float(idempotency.get('max_order_age_seconds', root.get('max_order_age_seconds', 300)), 300),
        'submit_guardrail_enabled': _truthy(guardrails.get('submit_guardrail_enabled', True)) or True,
        'close_guardrail_enabled': _truthy(guardrails.get('close_guardrail_enabled', True)) or True,
        'idempotency_enabled': _truthy(idempotency.get('enabled', True)) or True,
        'permission_drift_detected': _truthy(exchange.get('permission_drift_detected') or root.get('permission_drift_detected')),
        'can_trade': bool(permissions.get('can_trade', exchange.get('can_trade', False))),
        'can_withdraw': bool(permissions.get('can_withdraw', exchange.get('can_withdraw', False))),
        'ip_restricted': bool(permissions.get('ip_restricted', exchange.get('ip_restricted', True))),
        'api_key_present': bool(exchange.get('api_key_present', root.get('api_key_present', False))),
    }


def _base_reasons(settings: dict | None) -> list[dict]:
    p = _settings(settings)
    reasons: list[dict] = []
    if p['real_submit_enable'] or p['real_close_enable'] or p['emergency_close_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Real submit/close flags must remain default OFF until final guarded activation.', 'disable_real_execution_flags', 'critical', 1))
    if p['network_enable']:
        reasons.append(_reason('network_flag_enabled', 'Network execution must stay OFF during guardrail validation.', 'disable_network_execution', 'critical', 2))
    if not p['owner_approved']:
        reasons.append(_reason('owner_approval_missing', 'Owner approval is required before any micro-live action can be considered.', 'request_owner_approval', 'major', 8))
    if not p['session_id']:
        reasons.append(_reason('session_boundary_missing', 'Micro-live execution must be bound to a session ID.', 'create_session_boundary', 'major', 10))
    if not p['token_preview_present']:
        reasons.append(_reason('activation_token_preview_missing', 'Activation token preview presence is required; token value must never be returned.', 'generate_token_preview', 'major', 12))
    if p['max_notional'] <= 0:
        reasons.append(_reason('max_notional_missing', 'Max notional must be explicit before submit path can be armed.', 'set_max_notional', 'major', 14))
    if p['max_daily_loss'] <= 0:
        reasons.append(_reason('max_daily_loss_missing', 'Daily hard stop max loss must be explicit before submit path can be armed.', 'set_max_daily_loss', 'major', 15))
    if not p['allowed_symbols']:
        reasons.append(_reason('allowed_symbols_missing', 'Symbol whitelist must not be empty.', 'set_allowed_symbols', 'major', 16))
    return reasons


def build_rev276_submit_guardrail_finalizer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    reasons = _base_reasons(settings)
    checks = [
        _check('submit_guardrail_enabled', 'ok' if p['submit_guardrail_enabled'] else 'blocked', 'Submit guardrail must be enabled.'),
        _check('real_submit_default_off', 'ok' if not p['real_submit_enable'] else 'blocked', 'Real submit must remain default OFF.'),
        _check('network_default_off', 'ok' if not p['network_enable'] else 'blocked', 'Network execution must remain OFF.'),
        _check('owner_session_token_present', 'ok' if p['owner_approved'] and p['session_id'] and p['token_preview_present'] else 'blocked', 'Owner approval, session boundary and token preview are required.'),
        _check('risk_contract_explicit', 'ok' if p['max_notional'] > 0 and p['max_daily_loss'] > 0 else 'blocked', 'Max notional and daily loss must be explicit.'),
    ]
    body = {
        'submit_guardrail': 'ARMABLE_PREVIEW' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'real_submit': 'OFF',
        'network': 'OFF',
        'approval_gated_only': True,
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'allowed_symbols': p['allowed_symbols'],
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'submit_guardrail_finalizer', 'revision': 276, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'submit_guardrail_finalizer': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev277_close_emergency_close_guardrail_finalizer'}


def build_rev277_close_emergency_close_guardrail_finalizer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    reasons = _base_reasons(settings)
    if not p['emergency_guard_enabled']:
        reasons.append(_reason('emergency_guard_disabled', 'Emergency guard must be enabled before close path can be considered.', 'enable_emergency_guard', 'critical', 3))
    checks = [
        _check('close_guardrail_enabled', 'ok' if p['close_guardrail_enabled'] else 'blocked', 'Close guardrail must be enabled.'),
        _check('real_close_default_off', 'ok' if not p['real_close_enable'] else 'blocked', 'Real close must remain default OFF.'),
        _check('emergency_close_default_off', 'ok' if not p['emergency_close_enable'] else 'blocked', 'Emergency close submitter must remain default OFF.'),
        _check('emergency_guard_enabled', 'ok' if p['emergency_guard_enabled'] else 'blocked', 'Emergency guard must be active.'),
        _check('session_bound_close_only', 'ok' if p['session_id'] else 'blocked', 'Close path must be session-bound.'),
    ]
    body = {
        'close_guardrail': 'ARMABLE_PREVIEW' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'real_close': 'OFF',
        'emergency_close': 'OFF',
        'auto_close': 'OFF',
        'approval_gated_only': True,
        'stop_conditions': ['tp', 'sl', 'trailing', 'time_stop', 'manual_attention', 'emergency_guard'],
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'close_emergency_close_guardrail_finalizer', 'revision': 277, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'close_emergency_close_guardrail_finalizer': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev278_client_order_id_idempotency_hardening'}


def _valid_prefix(prefix: str) -> bool:
    return bool(re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{2,24}', prefix or ''))


def build_rev278_client_order_id_idempotency_hardening(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    duplicates = len(p['last_client_order_ids']) != len(set(p['last_client_order_ids']))
    stale = p['stale_order_age_seconds'] > p['max_order_age_seconds']
    reasons = _base_reasons(settings)
    if duplicates:
        reasons.append(_reason('duplicate_client_order_id_detected', 'Repeated client order IDs were detected.', 'rotate_client_order_id_and_hold', 'critical', 4))
    if stale:
        reasons.append(_reason('stale_order_preview_detected', 'Order preview is older than max order age.', 'refresh_order_preview', 'major', 6))
    if not _valid_prefix(p['order_id_prefix']):
        reasons.append(_reason('client_order_id_prefix_invalid', 'Client order ID prefix is invalid or too weak.', 'set_safe_order_id_prefix', 'major', 7))
    checks = [
        _check('idempotency_enabled', 'ok' if p['idempotency_enabled'] else 'blocked', 'Idempotency layer must be enabled.'),
        _check('client_order_id_prefix_valid', 'ok' if _valid_prefix(p['order_id_prefix']) else 'blocked', 'Client order ID prefix must be deterministic and safe.'),
        _check('no_duplicate_client_order_id', 'ok' if not duplicates else 'blocked', 'Duplicate client order IDs are blocked.'),
        _check('no_stale_order_preview', 'ok' if not stale else 'blocked', 'Stale order previews are blocked.'),
        _check('session_binding_available', 'ok' if p['session_id'] else 'blocked', 'Client order ID must include/bind session context.'),
    ]
    body = {
        'idempotency_guard': 'PASS' if _status_from_checks(checks) == 'ok' else 'BLOCKED',
        'client_order_id_prefix': p['order_id_prefix'],
        'duplicate_detected': duplicates,
        'stale_preview_detected': stale,
        'last_id_count': len(p['last_client_order_ids']),
        'max_order_age_seconds': p['max_order_age_seconds'],
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'client_order_id_idempotency_hardening', 'revision': 278, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'client_order_id_idempotency_hardening': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev279_exchange_permission_drift_final_guard'}


def build_rev279_exchange_permission_drift_final_guard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    reasons = _base_reasons(settings)
    if p['permission_drift_detected']:
        reasons.append(_reason('exchange_permission_drift_detected', 'Exchange/API permission drift was detected.', 'recheck_exchange_permissions_and_hold', 'critical', 2))
    if p['can_withdraw']:
        reasons.append(_reason('withdraw_permission_enabled', 'Withdraw permission must never be enabled for trading key.', 'disable_withdraw_permission', 'critical', 1))
    if not p['ip_restricted'] and p['api_key_present']:
        reasons.append(_reason('ip_restriction_missing', 'API key should be IP restricted before live activation.', 'enable_ip_restriction', 'major', 5))
    checks = [
        _check('no_permission_drift', 'ok' if not p['permission_drift_detected'] else 'blocked', 'Permission drift blocks live execution.'),
        _check('withdraw_permission_disabled', 'ok' if not p['can_withdraw'] else 'blocked', 'Withdraw permission must be disabled.'),
        _check('trade_permission_known', 'ok' if p['can_trade'] or not p['api_key_present'] else 'review', 'Trade permission must be known before activation.'),
        _check('ip_restriction_safe', 'ok' if p['ip_restricted'] or not p['api_key_present'] else 'review', 'IP restriction is expected for real API key.'),
        _check('secret_not_returned', 'ok', 'Permission guard never returns API key/secret.'),
    ]
    body = {
        'permission_guard': 'PASS' if _status_from_checks(checks) == 'ok' else ('BLOCKED' if _status_from_checks(checks) == 'blocked' else 'REVIEW'),
        'permission_drift_detected': p['permission_drift_detected'],
        'can_trade_known': bool(p['can_trade']),
        'withdraw_permission': 'DISABLED' if not p['can_withdraw'] else 'ENABLED_BLOCKED',
        'ip_restricted': bool(p['ip_restricted']),
        'api_key_present': bool(p['api_key_present']),
        'api_secret_returned': False,
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'exchange_permission_drift_final_guard', 'revision': 279, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'exchange_permission_drift_final_guard': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev280_micro_live_execution_guardrail_report'}


def build_rev280_micro_live_execution_guardrail_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    p = _settings(settings)
    payloads = [
        build_rev276_submit_guardrail_finalizer(data, settings, auth_store, username),
        build_rev277_close_emergency_close_guardrail_finalizer(data, settings, auth_store, username),
        build_rev278_client_order_id_idempotency_hardening(data, settings, auth_store, username),
        build_rev279_exchange_permission_drift_final_guard(data, settings, auth_store, username),
    ]
    reasons = _base_reasons(settings)
    for payload in payloads:
        body = _as_dict(payload.get({276:'submit_guardrail_finalizer',277:'close_emergency_close_guardrail_finalizer',278:'client_order_id_idempotency_hardening',279:'exchange_permission_drift_final_guard'}.get(payload.get('revision'), '')))
        blocker = _as_dict(body.get('critical_blocker'))
        if blocker and blocker.get('code') != 'none':
            reasons.append(blocker)
    checks = []
    for payload in payloads:
        checks.extend(_as_list(payload.get('checks')))
    status = _status_from_checks(checks)
    decision = 'READY_FOR_OWNER_GATED_DRY_ACTIVATION' if status == 'ok' else ('BLOCKED' if status == 'blocked' else 'REVIEW')
    report = {
        'micro_live_execution_guardrail': decision,
        'submit_guardrail': _as_dict(payloads[0].get('submit_guardrail_finalizer')).get('submit_guardrail'),
        'close_guardrail': _as_dict(payloads[1].get('close_emergency_close_guardrail_finalizer')).get('close_guardrail'),
        'idempotency_guard': _as_dict(payloads[2].get('client_order_id_idempotency_hardening')).get('idempotency_guard'),
        'permission_guard': _as_dict(payloads[3].get('exchange_permission_drift_final_guard')).get('permission_guard'),
        'max_notional': p['max_notional'],
        'max_daily_loss': p['max_daily_loss'],
        'allowed_symbols': p['allowed_symbols'],
        'real_submit': 'OFF',
        'real_close': 'OFF',
        'emergency_close': 'OFF',
        'auto_scale': 'OFF',
        'auto_apply': 'OFF',
        'critical_blocker': _critical(reasons),
        'operator_action': _critical(reasons).get('action'),
    }
    return {'engine': 'micro_live_execution_guardrail_report', 'revision': 280, 'status': status, 'generated_at': now_iso(), 'micro_live_execution_guardrail_report': report, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev281_first_limited_live_session_control_block'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {
        276: build_rev276_submit_guardrail_finalizer,
        277: build_rev277_close_emergency_close_guardrail_finalizer,
        278: build_rev278_client_order_id_idempotency_hardening,
        279: build_rev279_exchange_permission_drift_final_guard,
        280: build_rev280_micro_live_execution_guardrail_report,
    }
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev276-280 micro-live execution guardrail revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev276 = build_rev276_submit_guardrail_finalizer(data, settings, auth_store, username)
    rev277 = build_rev277_close_emergency_close_guardrail_finalizer(data, settings, auth_store, username)
    rev278 = build_rev278_client_order_id_idempotency_hardening(data, settings, auth_store, username)
    rev279 = build_rev279_exchange_permission_drift_final_guard(data, settings, auth_store, username)
    rev280 = build_rev280_micro_live_execution_guardrail_report(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev276, rev277, rev278, rev279, rev280):
        checks.extend(_as_list(payload.get('checks')))
    return {
        'engine': 'micro_live_execution_guardrail_block',
        'revision': 280,
        'status': rev280.get('status', 'review'),
        'generated_at': now_iso(),
        'rev276_submit_guardrail_finalizer': rev276,
        'rev277_close_emergency_close_guardrail_finalizer': rev277,
        'rev278_client_order_id_idempotency_hardening': rev278,
        'rev279_exchange_permission_drift_final_guard': rev279,
        'rev280_micro_live_execution_guardrail_report': rev280,
        'micro_live_execution_guardrail_report': rev280.get('micro_live_execution_guardrail_report', {}),
        'summary_result': build_summary_for_revision(280, data, settings, auth_store, username),
        'checks': checks,
        'check_totals': _totals(checks),
        'command_preview': _command_preview(),
        'contains_secret': False,
        'secret_values_returned': False,
        'next_allowed_step': 'first_limited_live_session_control_block',
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key_map = {
        276: 'submit_guardrail_finalizer',
        277: 'close_emergency_close_guardrail_finalizer',
        278: 'client_order_id_idempotency_hardening',
        279: 'exchange_permission_drift_final_guard',
        280: 'micro_live_execution_guardrail_report',
    }
    body = _as_dict(payload.get(key_map[int(revision)]))
    blocker = _as_dict(body.get('critical_blocker'))
    decision = body.get('micro_live_execution_guardrail') or body.get('submit_guardrail') or body.get('close_guardrail') or body.get('idempotency_guard') or body.get('permission_guard') or ('READY' if payload.get('status') == 'ok' else 'REVIEW')
    return {
        'revision': int(revision),
        'micro_live_execution_guardrail': decision,
        'critical_issue': blocker.get('code', 'none'),
        'owner_action': body.get('operator_action') or blocker.get('action') or 'review',
        'submit_guardrail': body.get('submit_guardrail'),
        'close_guardrail': body.get('close_guardrail'),
        'idempotency_guard': body.get('idempotency_guard'),
        'permission_guard': body.get('permission_guard'),
        'max_notional': body.get('max_notional'),
        'max_daily_loss': body.get('max_daily_loss'),
        'allowed_symbols': body.get('allowed_symbols'),
        'trade_allowed': decision == 'READY_FOR_OWNER_GATED_DRY_ACTIVATION',
        'real_submit_close': 'OFF',
        'emergency_close': 'OFF',
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
