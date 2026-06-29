from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_submit_emergency_rehearsal_service import build_autonomous_micro_real_submit_emergency_rehearsal


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {'1', 'true', 'yes', 'on', 'enabled', 'allow', 'allowed', 'ready', 'ok'}:
            return True
        if text in {'0', 'false', 'no', 'off', 'disabled', 'deny', 'blocked', 'none'}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get('autonomous_runtime_audit_idempotency_lock') if isinstance(settings.get('autonomous_runtime_audit_idempotency_lock'), dict) else {}
    return {
        'enabled': _safe_bool(raw.get('enabled'), True),
        'required_source_revision': 103,
        'allow_runtime_write': _safe_bool(raw.get('allow_runtime_write'), False),
        'allow_network_calls': _safe_bool(raw.get('allow_network_calls'), False),
        'allow_direct_orders': _safe_bool(raw.get('allow_direct_orders'), False),
        'allow_real_submit': _safe_bool(raw.get('allow_real_submit'), False),
        'runtime_audit_store_configured': _safe_bool(raw.get('runtime_audit_store_configured'), True),
        'idempotency_lock_configured': _safe_bool(raw.get('idempotency_lock_configured'), True),
        'lock_ttl_seconds': max(60, min(_safe_int(raw.get('lock_ttl_seconds'), 86400), 604800)),
        'duplicate_probe_detected': _safe_bool(raw.get('duplicate_probe_detected'), False),
        'audit_retention_days': max(1, min(_safe_int(raw.get('audit_retention_days'), 90), 365)),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get('autonomous_micro_real_submit_emergency_rehearsal') if isinstance(data.get('autonomous_micro_real_submit_emergency_rehearsal'), dict) else None
    if raw and raw.get('revision') == 103 and raw.get('engine') == 'autonomous_micro_real_submit_emergency_rehearsal':
        return raw
    return build_autonomous_micro_real_submit_emergency_rehearsal(data, settings, auth_store, username)


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {'name': name, 'status': status, 'required': required, 'detail': detail}


def _safe_text(value: Any, fallback: str = 'unknown') -> str:
    text = str(value or '').strip()
    return text or fallback


def _fingerprint(source: dict, username: str) -> str:
    submit = source.get('submit_rehearsal') if isinstance(source.get('submit_rehearsal'), dict) else {}
    emergency = source.get('emergency_close_rehearsal') if isinstance(source.get('emergency_close_rehearsal'), dict) else {}
    parts = [
        'rev104-runtime-lock',
        username,
        _safe_text(submit.get('idempotency_key_preview')),
        _safe_text(emergency.get('emergency_rehearsal_id')),
        _safe_text(submit.get('symbol')),
        _safe_text(submit.get('side')),
        _safe_text(submit.get('order_type')),
        _safe_text(submit.get('quantity_preview')),
    ]
    return sha256(':'.join(parts).encode('utf-8')).hexdigest()[:32]


def _audit_event(source: dict, lock_key: str, policy: dict) -> dict:
    submit = source.get('submit_rehearsal') if isinstance(source.get('submit_rehearsal'), dict) else {}
    emergency = source.get('emergency_close_rehearsal') if isinstance(source.get('emergency_close_rehearsal'), dict) else {}
    seed = f"rev104-audit:{lock_key}:{source.get('status')}:{submit.get('notional_preview_usdt')}"
    return {
        'audit_event_id': sha256(seed.encode('utf-8')).hexdigest()[:24],
        'event_type': 'micro_real_pre_submit_runtime_audit_preview',
        'source_revision': source.get('revision'),
        'source_status': source.get('status'),
        'symbol': submit.get('symbol') or (source.get('policy') or {}).get('symbol'),
        'notional_preview_usdt': submit.get('notional_preview_usdt'),
        'submit_idempotency_key_preview': submit.get('idempotency_key_preview'),
        'emergency_rehearsal_id': emergency.get('emergency_rehearsal_id'),
        'runtime_lock_key_preview': lock_key,
        'audit_retention_days': policy['audit_retention_days'],
        'secret_values_returned': False,
        'contains_secret': False,
        'writes_runtime_state': False,
    }


def build_autonomous_runtime_audit_idempotency_lock(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data = data if isinstance(data, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    source_command = source.get('command_preview') if isinstance(source.get('command_preview'), dict) else {}
    source_safety = source.get('safety_contract') if isinstance(source.get('safety_contract'), dict) else {}
    lock_key = _fingerprint(source, username)
    audit_event = _audit_event(source, lock_key, policy)

    checks = [
        _check('runtime_lock_enabled', 'ok' if policy['enabled'] else 'blocked', 'Rev104 runtime audit/idempotency policy must be enabled.'),
        _check('source_revision_103', 'ok' if source.get('revision') == 103 else 'blocked', 'Rev104 must be fed by Rev103 submit/emergency rehearsal.'),
        _check('source_not_blocked', 'ok' if source.get('status') != 'blocked' else 'blocked', f"Rev103 source status: {source.get('status', 'unknown')}"),
        _check('source_does_not_place_order', 'ok' if source_command.get('places_order') is False else 'blocked', 'Upstream rehearsal must not place orders.'),
        _check('source_does_not_call_exchange', 'ok' if source_command.get('sends_exchange_request') is False else 'blocked', 'Upstream rehearsal must not call exchange.'),
        _check('source_does_not_write_runtime', 'ok' if source_command.get('writes_runtime_state') is False else 'blocked', 'Upstream rehearsal must not write runtime state.'),
        _check('source_secret_free', 'ok' if source_safety.get('contains_secret') is False else 'blocked', 'No secret may be present in upstream evidence.'),
        _check('runtime_audit_store_configured', 'ok' if policy['runtime_audit_store_configured'] else 'blocked', 'Audit store target must be configured before live submit.'),
        _check('idempotency_lock_configured', 'ok' if policy['idempotency_lock_configured'] else 'blocked', 'Runtime idempotency lock must be configured before live submit.'),
        _check('duplicate_probe_not_detected', 'ok' if not policy['duplicate_probe_detected'] else 'blocked', 'Duplicate probe lock collision blocks submit.'),
        _check('network_calls_disabled', 'ok' if not policy['allow_network_calls'] else 'blocked', 'Rev104 stays offline/read-only.'),
        _check('direct_orders_disabled', 'ok' if not policy['allow_direct_orders'] else 'blocked', 'Direct order placement remains disabled.'),
        _check('real_submit_disabled', 'ok' if not policy['allow_real_submit'] else 'blocked', 'Real submit remains disabled in Rev104.'),
        _check('runtime_write_disabled', 'ok' if not policy['allow_runtime_write'] else 'blocked', 'Rev104 previews runtime write contract but does not write.'),
    ]
    blockers = [c for c in checks if c['status'] == 'blocked' and c.get('required')]
    reviews = [c for c in checks if c['status'] == 'review']
    status = 'blocked' if blockers else ('review' if reviews or source.get('status') == 'review' else 'ok')
    readiness = {
        'ok': 'RUNTIME_AUDIT_IDEMPOTENCY_READY_PREVIEW',
        'review': 'RUNTIME_AUDIT_IDEMPOTENCY_REVIEW',
        'blocked': 'RUNTIME_AUDIT_IDEMPOTENCY_BLOCKED',
    }[status]
    seed = f"rev104:{username}:{status}:{lock_key}:{audit_event.get('audit_event_id')}"
    return {
        'status': status,
        'revision': 104,
        'engine': 'autonomous_runtime_audit_idempotency_lock',
        'generated_at': now_iso(),
        'source_revision': source.get('revision'),
        'source_status': source.get('status'),
        'readiness': readiness,
        'mode': 'runtime_audit_and_idempotency_preview_only',
        'runtime_audit_store': {
            'configured': policy['runtime_audit_store_configured'],
            'target': 'runtime/audit/micro_real_events.jsonl',
            'event_schema_version': 'rev104.v1',
            'retention_days': policy['audit_retention_days'],
            'secret_values_returned': False,
            'writes_runtime_state': False,
        },
        'idempotency_lock': {
            'configured': policy['idempotency_lock_configured'],
            'lock_key_preview': lock_key,
            'ttl_seconds': policy['lock_ttl_seconds'],
            'duplicate_detected': policy['duplicate_probe_detected'],
            'collision_policy': 'block_duplicate_submit',
            'writes_runtime_state': False,
        },
        'audit_event_preview': audit_event,
        'checks': checks,
        'check_totals': {'total': len(checks), 'ok': len([c for c in checks if c['status'] == 'ok']), 'review': len(reviews), 'blocked': len(blockers)},
        'blockers': [c['name'] for c in blockers],
        'warnings': [c['name'] for c in reviews],
        'command_preview': {
            'type': 'runtime_audit_store_and_idempotency_lock_preview',
            'read_only': True,
            'dry_run': True,
            'places_order': False,
            'closes_position': False,
            'sends_exchange_request': False,
            'writes_runtime_state': False,
            'direct_order_enabled': False,
            'real_submit_enabled': False,
            'requires_manual_owner_approval': True,
            'next_allowed_step': 'first_micro_real_submit_enable_flag' if status != 'blocked' else 'resolve_runtime_audit_idempotency_blockers',
        },
        'safety_contract': {
            'contains_secret': False,
            'secret_values_returned': False,
            'direct_order_placement': False,
            'exchange_request': False,
            'runtime_write': False,
            'approval_gated': True,
            'auto_apply': False,
            'manual_go_live_required': True,
            'idempotency_required_before_live_submit': True,
            'audit_store_required_before_live_submit': True,
        },
        'audit_evidence': {
            'evidence_id': sha256(seed.encode('utf-8')).hexdigest()[:24],
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
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    lock = payload.get('idempotency_lock') if isinstance(payload.get('idempotency_lock'), dict) else {}
    audit_store = payload.get('runtime_audit_store') if isinstance(payload.get('runtime_audit_store'), dict) else {}
    event = payload.get('audit_event_preview') if isinstance(payload.get('audit_event_preview'), dict) else {}
    return {
        'status': payload.get('status', 'review'),
        'revision': 104,
        'engine': 'autonomous_runtime_audit_idempotency_lock_summary',
        'generated_at': payload.get('generated_at'),
        'readiness': payload.get('readiness'),
        'source_revision': payload.get('source_revision'),
        'source_status': payload.get('source_status'),
        'audit_store_configured': audit_store.get('configured'),
        'idempotency_lock_configured': lock.get('configured'),
        'duplicate_detected': lock.get('duplicate_detected'),
        'lock_key_preview': lock.get('lock_key_preview'),
        'audit_event_id': event.get('audit_event_id'),
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


def build_summary_autonomous_runtime_audit_idempotency_lock(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _summary_from_payload(build_autonomous_runtime_audit_idempotency_lock(data, settings, auth_store, username))


def _sample_data() -> dict:
    source = {
        'status': 'review',
        'revision': 103,
        'engine': 'autonomous_micro_real_submit_emergency_rehearsal',
        'readiness': 'MICRO_REAL_REHEARSAL_REVIEW',
        'policy': {'symbol': 'BTCUSDT', 'probe_notional_usdt': 6, 'max_probe_notional_usdt': 10, 'secret_values_returned': False},
        'submit_rehearsal': {
            'status': 'ok', 'type': 'micro_real_submit_dry_run_rehearsal', 'symbol': 'BTCUSDT', 'side': 'BUY', 'order_type': 'MARKET',
            'quantity_preview': '0.00012', 'notional_preview_usdt': 6.0, 'idempotency_key_preview': 'sample_submit_lock_key',
            'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False,
        },
        'emergency_close_rehearsal': {'status': 'ok', 'type': 'emergency_close_rehearsal', 'emergency_rehearsal_id': 'sample_emergency_rehearsal', 'closes_position': False, 'sends_exchange_request': False},
        'command_preview': {'read_only': True, 'places_order': False, 'closes_position': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'real_submit_enabled': False},
        'safety_contract': {'contains_secret': False, 'secret_values_returned': False, 'direct_order_placement': False, 'exchange_request': False, 'runtime_write': False},
    }
    return {'autonomous_micro_real_submit_emergency_rehearsal': source}


def build_autonomous_runtime_audit_idempotency_lock_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_autonomous_runtime_audit_idempotency_lock(
        data or _sample_data(),
        settings or {'autonomous_runtime_audit_idempotency_lock': {'enabled': True, 'runtime_audit_store_configured': True, 'idempotency_lock_configured': True}},
        auth_store or {'users': {username: {'role': 'owner', 'api_key_present': True, 'secret_present': True, 'read_permission': True, 'trade_permission': False}}},
        username,
    )
    command = payload.get('command_preview') if isinstance(payload.get('command_preview'), dict) else {}
    safety = payload.get('safety_contract') if isinstance(payload.get('safety_contract'), dict) else {}
    lock = payload.get('idempotency_lock') if isinstance(payload.get('idempotency_lock'), dict) else {}
    audit_store = payload.get('runtime_audit_store') if isinstance(payload.get('runtime_audit_store'), dict) else {}
    audit_event = payload.get('audit_event_preview') if isinstance(payload.get('audit_event_preview'), dict) else {}
    checks = {
        'revision_is_104': payload.get('revision') == 104,
        'source_revision_is_103': payload.get('source_revision') == 103,
        'readiness_present': payload.get('readiness') in {'RUNTIME_AUDIT_IDEMPOTENCY_READY_PREVIEW', 'RUNTIME_AUDIT_IDEMPOTENCY_REVIEW', 'RUNTIME_AUDIT_IDEMPOTENCY_BLOCKED'},
        'audit_store_preview_present': audit_store.get('configured') is True and audit_store.get('writes_runtime_state') is False,
        'idempotency_lock_preview_present': bool(lock.get('lock_key_preview')) and lock.get('writes_runtime_state') is False,
        'audit_event_secret_free': audit_event.get('contains_secret') is False and audit_event.get('secret_values_returned') is False,
        'does_not_place_order': command.get('places_order') is False,
        'does_not_close_position': command.get('closes_position') is False,
        'does_not_call_exchange': command.get('sends_exchange_request') is False,
        'does_not_write_runtime': command.get('writes_runtime_state') is False,
        'real_submit_off': command.get('real_submit_enabled') is False,
        'contract_secret_free': safety.get('contains_secret') is False and safety.get('secret_values_returned') is False,
        'summary_revision_is_104': _summary_from_payload(payload).get('revision') == 104,
    }
    passed = all(checks.values())
    return {
        'status': 'ok' if passed else 'review',
        'revision': 104,
        'engine': 'autonomous_runtime_audit_idempotency_lock_quality',
        'generated_at': now_iso(),
        'quality_status': 'RUNTIME_AUDIT_IDEMPOTENCY_LOCK_OK' if passed else 'RUNTIME_AUDIT_IDEMPOTENCY_LOCK_REVIEW',
        'checks': checks,
        'summary': _summary_from_payload(payload),
        'sample_readiness': payload.get('readiness'),
        'sample_totals': payload.get('check_totals') or {},
    }
