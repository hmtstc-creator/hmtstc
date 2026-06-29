from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_runtime_audit_idempotency_lock_service import build_autonomous_runtime_audit_idempotency_lock


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {'1', 'true', 'yes', 'on', 'enabled', 'allow', 'allowed', 'ready', 'ok', 'armed'}:
            return True
        if text in {'0', 'false', 'no', 'off', 'disabled', 'deny', 'blocked', 'none'}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_text(value: Any, fallback: str = '') -> str:
    text = str(value or '').strip()
    return text or fallback


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get('autonomous_first_micro_real_submit_enable_flag') if isinstance(settings.get('autonomous_first_micro_real_submit_enable_flag'), dict) else {}
    return {
        'enabled': _safe_bool(raw.get('enabled'), True),
        'required_source_revision': 104,
        'submit_enable_flag_configured': _safe_bool(raw.get('submit_enable_flag_configured'), True),
        'submit_enable_flag_requested': _safe_bool(raw.get('submit_enable_flag_requested'), False),
        'owner_confirmation_token_present': _safe_bool(raw.get('owner_confirmation_token_present'), False),
        'owner_confirmation_token_hash': _safe_text(raw.get('owner_confirmation_token_hash'))[:32],
        'manual_one_shot_ack': _safe_bool(raw.get('manual_one_shot_ack'), False),
        'max_first_submit_notional_usdt': max(1.0, min(_safe_float(raw.get('max_first_submit_notional_usdt'), 10.0), 25.0)),
        'single_symbol_only': _safe_bool(raw.get('single_symbol_only'), True),
        'allow_runtime_write': _safe_bool(raw.get('allow_runtime_write'), False),
        'allow_network_calls': _safe_bool(raw.get('allow_network_calls'), False),
        'allow_direct_orders': _safe_bool(raw.get('allow_direct_orders'), False),
        'allow_real_submit': _safe_bool(raw.get('allow_real_submit'), False),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get('autonomous_runtime_audit_idempotency_lock') if isinstance(data.get('autonomous_runtime_audit_idempotency_lock'), dict) else None
    if raw and raw.get('revision') == 104 and raw.get('engine') == 'autonomous_runtime_audit_idempotency_lock':
        return raw
    return build_autonomous_runtime_audit_idempotency_lock(data, settings, auth_store, username)


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {'name': name, 'status': status, 'required': required, 'detail': detail}


def _extract_user(auth_store: dict, username: str) -> dict:
    users = auth_store.get('users') if isinstance(auth_store.get('users'), dict) else {}
    user = users.get(username) if isinstance(users.get(username), dict) else {}
    return user


def _audit_id(username: str, source: dict, policy: dict) -> str:
    lock = source.get('idempotency_lock') if isinstance(source.get('idempotency_lock'), dict) else {}
    event = source.get('audit_event_preview') if isinstance(source.get('audit_event_preview'), dict) else {}
    seed = ':'.join([
        'rev105-submit-enable-flag',
        username,
        _safe_text(lock.get('lock_key_preview')),
        _safe_text(event.get('audit_event_id')),
        str(policy['submit_enable_flag_requested']),
        str(policy['owner_confirmation_token_hash']),
    ])
    return sha256(seed.encode('utf-8')).hexdigest()[:24]


def build_autonomous_first_micro_real_submit_enable_flag(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data = data if isinstance(data, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get('command_preview') if isinstance(source.get('command_preview'), dict) else {}
    safety = source.get('safety_contract') if isinstance(source.get('safety_contract'), dict) else {}
    lock = source.get('idempotency_lock') if isinstance(source.get('idempotency_lock'), dict) else {}
    audit_store = source.get('runtime_audit_store') if isinstance(source.get('runtime_audit_store'), dict) else {}
    audit_event = source.get('audit_event_preview') if isinstance(source.get('audit_event_preview'), dict) else {}
    source_submit_event = audit_event.get('submit_idempotency_key_preview')
    user = _extract_user(auth_store, username)
    trade_permission = _safe_bool(user.get('trade_permission'), False)
    api_ready = _safe_bool(user.get('api_key_present'), False) and _safe_bool(user.get('secret_present'), False)
    requested = policy['submit_enable_flag_requested']
    owner_confirmed = policy['owner_confirmation_token_present'] and bool(policy['owner_confirmation_token_hash']) and policy['manual_one_shot_ack']
    first_submit_notional = _safe_float(audit_event.get('notional_preview_usdt'), 0.0)

    checks = [
        _check('rev105_policy_enabled', 'ok' if policy['enabled'] else 'blocked', 'Rev105 submit enable flag policy must be enabled.'),
        _check('source_revision_104', 'ok' if source.get('revision') == 104 else 'blocked', 'Rev105 must be fed by Rev104 runtime audit/idempotency lock.'),
        _check('source_not_blocked', 'ok' if source.get('status') != 'blocked' else 'blocked', f"Rev104 source status: {source.get('status', 'unknown')}"),
        _check('source_does_not_place_order', 'ok' if command.get('places_order') is False else 'blocked', 'Upstream must not place order.'),
        _check('source_does_not_call_exchange', 'ok' if command.get('sends_exchange_request') is False else 'blocked', 'Upstream must not call exchange.'),
        _check('source_does_not_write_runtime', 'ok' if command.get('writes_runtime_state') is False else 'blocked', 'Upstream must not write runtime.'),
        _check('source_secret_free', 'ok' if safety.get('contains_secret') is False and safety.get('secret_values_returned') is False else 'blocked', 'No secret may be returned in Rev105.'),
        _check('audit_store_configured', 'ok' if audit_store.get('configured') is True else 'blocked', 'Runtime audit store must be configured before enable flag.'),
        _check('idempotency_lock_configured', 'ok' if lock.get('configured') is True and lock.get('duplicate_detected') is False else 'blocked', 'Idempotency lock must be configured and duplicate-free.'),
        _check('submit_enable_flag_configured', 'ok' if policy['submit_enable_flag_configured'] else 'blocked', 'Submit enable flag configuration must exist.'),
        _check('submit_enable_flag_requested', 'ok' if requested else 'review', 'Owner has not requested one-shot submit enable yet.', required=False),
        _check('owner_confirmation_token_present', 'ok' if owner_confirmed else 'review', 'Owner confirmation token + one-shot acknowledgement are required before first real submit.', required=False),
        _check('api_keys_present', 'ok' if api_ready else 'blocked', 'API key and secret metadata must be present; plaintext secret is never returned.'),
        _check('api_trade_permission_present', 'ok' if trade_permission else 'review', 'Trade permission is required before real submit; Rev105 does not submit.', required=False),
        _check('first_submit_notional_within_cap', 'ok' if 0 < first_submit_notional <= policy['max_first_submit_notional_usdt'] else 'blocked', 'First submit notional must stay under configured cap.'),
        _check('single_symbol_only', 'ok' if policy['single_symbol_only'] else 'blocked', 'First micro-real submit must remain one-symbol-only.'),
        _check('network_calls_disabled', 'ok' if not policy['allow_network_calls'] else 'blocked', 'Rev105 still does not call exchange.'),
        _check('direct_orders_disabled', 'ok' if not policy['allow_direct_orders'] else 'blocked', 'Direct order placement remains disabled in Rev105.'),
        _check('runtime_write_disabled', 'ok' if not policy['allow_runtime_write'] else 'blocked', 'Rev105 is preview-only and must not write runtime state.'),
        _check('real_submit_still_disabled', 'ok' if not policy['allow_real_submit'] else 'blocked', 'Rev105 arms the flag contract only; real submit remains disabled until submitter revision.'),
    ]
    blockers = [c for c in checks if c['status'] == 'blocked' and c.get('required')]
    reviews = [c for c in checks if c['status'] == 'review']
    status = 'blocked' if blockers else ('review' if reviews or source.get('status') == 'review' else 'ok')
    readiness = {
        'ok': 'FIRST_MICRO_REAL_SUBMIT_FLAG_ARMED_PREVIEW',
        'review': 'FIRST_MICRO_REAL_SUBMIT_FLAG_REVIEW',
        'blocked': 'FIRST_MICRO_REAL_SUBMIT_FLAG_BLOCKED',
    }[status]
    flag_id = _audit_id(username, source, policy)
    armed_preview = status != 'blocked' and requested and owner_confirmed and trade_permission
    return {
        'status': status,
        'revision': 105,
        'engine': 'autonomous_first_micro_real_submit_enable_flag',
        'generated_at': now_iso(),
        'source_revision': source.get('revision'),
        'source_status': source.get('status'),
        'readiness': readiness,
        'mode': 'first_micro_real_submit_enable_flag_preview_only',
        'submit_enable_flag': {
            'flag_id_preview': flag_id,
            'configured': policy['submit_enable_flag_configured'],
            'requested': requested,
            'owner_confirmed': owner_confirmed,
            'armed_preview': armed_preview,
            'one_shot': True,
            'single_symbol_only': policy['single_symbol_only'],
            'max_first_submit_notional_usdt': policy['max_first_submit_notional_usdt'],
            'source_submit_idempotency_key_preview': source_submit_event,
            'runtime_lock_key_preview': lock.get('lock_key_preview'),
            'audit_event_id': audit_event.get('audit_event_id'),
            'writes_runtime_state': False,
        },
        'api_permission_context': {
            'api_key_present': _safe_bool(user.get('api_key_present'), False),
            'secret_present': _safe_bool(user.get('secret_present'), False),
            'read_permission': _safe_bool(user.get('read_permission'), False),
            'trade_permission': trade_permission,
            'secret_values_returned': False,
        },
        'first_submit_candidate': {
            'symbol': audit_event.get('symbol'),
            'notional_preview_usdt': first_submit_notional,
            'cap_usdt': policy['max_first_submit_notional_usdt'],
            'within_cap': 0 < first_submit_notional <= policy['max_first_submit_notional_usdt'],
            'submit_enabled_preview': armed_preview,
        },
        'checks': checks,
        'check_totals': {'total': len(checks), 'ok': len([c for c in checks if c['status'] == 'ok']), 'review': len(reviews), 'blocked': len(blockers)},
        'blockers': [c['name'] for c in blockers],
        'warnings': [c['name'] for c in reviews],
        'command_preview': {
            'type': 'first_micro_real_submit_enable_flag_preview',
            'read_only': True,
            'dry_run': True,
            'places_order': False,
            'closes_position': False,
            'sends_exchange_request': False,
            'writes_runtime_state': False,
            'direct_order_enabled': False,
            'real_submit_enabled': False,
            'real_submit_flag_armed_preview': armed_preview,
            'requires_manual_owner_approval': True,
            'next_allowed_step': 'real_binance_micro_order_submitter' if status != 'blocked' else 'resolve_first_submit_enable_flag_blockers',
        },
        'safety_contract': {
            'contains_secret': False,
            'secret_values_returned': False,
            'direct_order_placement': False,
            'exchange_request': False,
            'runtime_write': False,
            'real_submit': False,
            'approval_gated': True,
            'auto_apply': False,
            'manual_go_live_required': True,
            'owner_confirmation_required': True,
            'idempotency_required_before_live_submit': True,
            'audit_store_required_before_live_submit': True,
        },
        'audit_evidence': {
            'evidence_id': sha256(f"rev105:{username}:{flag_id}:{status}".encode('utf-8')).hexdigest()[:24],
            'source_engine': source.get('engine'),
            'source_status': source.get('status'),
            'readiness': readiness,
            'blocked_count': len(blockers),
            'review_count': len(reviews),
        },
        'read_only': True,
        'dry_run': True,
        'places_order': False,
        'closes_position': False,
        'sends_exchange_request': False,
        'writes_runtime_state': False,
    }


def _summary_from_payload(payload: dict) -> dict:
    flag = payload.get('submit_enable_flag') if isinstance(payload.get('submit_enable_flag'), dict) else {}
    candidate = payload.get('first_submit_candidate') if isinstance(payload.get('first_submit_candidate'), dict) else {}
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    return {
        'status': payload.get('status', 'review'),
        'revision': 105,
        'engine': 'autonomous_first_micro_real_submit_enable_flag_summary',
        'generated_at': payload.get('generated_at'),
        'readiness': payload.get('readiness'),
        'source_revision': payload.get('source_revision'),
        'source_status': payload.get('source_status'),
        'flag_id_preview': flag.get('flag_id_preview'),
        'flag_configured': flag.get('configured'),
        'flag_requested': flag.get('requested'),
        'owner_confirmed': flag.get('owner_confirmed'),
        'armed_preview': flag.get('armed_preview'),
        'symbol': candidate.get('symbol'),
        'notional_preview_usdt': candidate.get('notional_preview_usdt'),
        'cap_usdt': candidate.get('cap_usdt'),
        'check_totals': payload.get('check_totals') or {},
        'blockers': payload.get('blockers') or [],
        'warnings': payload.get('warnings') or [],
        'next_allowed_step': command.get('next_allowed_step'),
        'read_only': True,
        'dry_run': True,
        'direct_order_placement': False,
        'exchange_request': False,
        'runtime_write': False,
        'real_submit_enabled': False,
    }


def build_summary_autonomous_first_micro_real_submit_enable_flag(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _summary_from_payload(build_autonomous_first_micro_real_submit_enable_flag(data, settings, auth_store, username))


def _sample_source() -> dict:
    source = {
        'status': 'ok',
        'revision': 104,
        'engine': 'autonomous_runtime_audit_idempotency_lock',
        'readiness': 'RUNTIME_AUDIT_IDEMPOTENCY_READY_PREVIEW',
        'runtime_audit_store': {'configured': True, 'writes_runtime_state': False},
        'idempotency_lock': {'configured': True, 'lock_key_preview': 'sample_lock', 'duplicate_detected': False, 'writes_runtime_state': False},
        'audit_event_preview': {'audit_event_id': 'sample_event', 'symbol': 'BTCUSDT', 'notional_preview_usdt': 6.0, 'submit_idempotency_key_preview': 'sample_submit_key', 'contains_secret': False, 'secret_values_returned': False},
        'command_preview': {'read_only': True, 'places_order': False, 'closes_position': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'real_submit_enabled': False},
        'safety_contract': {'contains_secret': False, 'secret_values_returned': False, 'direct_order_placement': False, 'exchange_request': False, 'runtime_write': False},
    }
    return {'autonomous_runtime_audit_idempotency_lock': source}


def build_autonomous_first_micro_real_submit_enable_flag_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_autonomous_first_micro_real_submit_enable_flag(
        data or _sample_source(),
        settings or {'autonomous_first_micro_real_submit_enable_flag': {'enabled': True, 'submit_enable_flag_configured': True, 'submit_enable_flag_requested': True, 'owner_confirmation_token_present': True, 'owner_confirmation_token_hash': 'sample_hash', 'manual_one_shot_ack': True, 'max_first_submit_notional_usdt': 10}},
        auth_store or {'users': {username: {'role': 'owner', 'api_key_present': True, 'secret_present': True, 'read_permission': True, 'trade_permission': True}}},
        username,
    )
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    safety = payload.get('safety_contract') if isinstance(payload.get('safety_contract'), dict) else {}
    flag = payload.get('submit_enable_flag') if isinstance(payload.get('submit_enable_flag'), dict) else {}
    candidate = payload.get('first_submit_candidate') if isinstance(payload.get('first_submit_candidate'), dict) else {}
    checks = {
        'revision_is_105': payload.get('revision') == 105,
        'source_revision_is_104': payload.get('source_revision') == 104,
        'readiness_present': payload.get('readiness') in {'FIRST_MICRO_REAL_SUBMIT_FLAG_ARMED_PREVIEW', 'FIRST_MICRO_REAL_SUBMIT_FLAG_REVIEW', 'FIRST_MICRO_REAL_SUBMIT_FLAG_BLOCKED'},
        'flag_preview_present': bool(flag.get('flag_id_preview')) and flag.get('one_shot') is True,
        'armed_preview_possible': flag.get('armed_preview') is True,
        'notional_within_cap': candidate.get('within_cap') is True,
        'does_not_place_order': command.get('places_order') is False,
        'does_not_close_position': command.get('closes_position') is False,
        'does_not_call_exchange': command.get('sends_exchange_request') is False,
        'does_not_write_runtime': command.get('writes_runtime_state') is False,
        'real_submit_still_off': command.get('real_submit_enabled') is False,
        'contract_secret_free': safety.get('contains_secret') is False and safety.get('secret_values_returned') is False,
        'summary_revision_is_105': _summary_from_payload(payload).get('revision') == 105,
    }
    passed = all(checks.values())
    return {
        'status': 'ok' if passed else 'review',
        'revision': 105,
        'engine': 'autonomous_first_micro_real_submit_enable_flag_quality',
        'generated_at': now_iso(),
        'quality_status': 'FIRST_MICRO_REAL_SUBMIT_ENABLE_FLAG_OK' if passed else 'FIRST_MICRO_REAL_SUBMIT_ENABLE_FLAG_REVIEW',
        'checks': checks,
        'summary': _summary_from_payload(payload),
        'sample_readiness': payload.get('readiness'),
        'sample_totals': payload.get('check_totals') or {},
    }
