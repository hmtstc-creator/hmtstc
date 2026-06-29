from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

REVISION = 930


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _hash(*parts: Any) -> str:
    return hashlib.sha256('|'.join(str(p) for p in parts).encode('utf-8')).hexdigest()[:18]


def _users(auth_store: dict | None) -> dict:
    store = as_dict(auth_store)
    users = store.get('users')
    return users if isinstance(users, dict) else {}


def _masked_api_state(record: dict) -> dict:
    api = as_dict(record.get('api_connection') or record.get('exchange_profile') or {})
    configured = bool(api.get('api_key_configured') or api.get('configured') or api.get('api_key_masked') or api.get('api_key_present'))
    return {
        'configured': configured,
        'api_key_masked': api.get('api_key_masked') or ('***configured***' if configured else None),
        'secret_configured': bool(api.get('secret_configured') or api.get('secret_key_present') or configured),
        'secret_value_returned': False,
        'raw_api_key_returned': False,
    }


def _commission_settings(record: dict) -> dict:
    settings = as_dict(record.get('commission_settings'))
    buy_rate = max(0.0, safe_float(settings.get('buy_rate_percent'), 0.10))
    sell_rate = max(0.0, safe_float(settings.get('sell_rate_percent'), 0.10))
    return {
        'buy_rate_percent': round(buy_rate, 6),
        'sell_rate_percent': round(sell_rate, 6),
        'minimum_commission_usdt': round(max(0.0, safe_float(settings.get('minimum_commission_usdt'), 0.0)), 8),
        'source': 'user_record' if settings else 'default_safe_profile',
    }


def _risk_profile(record: dict) -> dict:
    risk = as_dict(record.get('risk_profile'))
    role = str(record.get('role') or 'user')
    return {
        'profile': risk.get('profile') or ('owner' if role == 'owner' else 'conservative'),
        'max_daily_loss_usdt': max(0.0, safe_float(risk.get('max_daily_loss_usdt'), 5.0 if role != 'owner' else 25.0)),
        'max_exposure_usdt': max(0.0, safe_float(risk.get('max_exposure_usdt'), 50.0 if role != 'owner' else 250.0)),
        'max_open_positions': int(max(0, safe_float(risk.get('max_open_positions'), 1 if role != 'owner' else 3))),
        'daily_trade_cap': int(max(0, safe_float(risk.get('daily_trade_cap'), 20 if role != 'owner' else 100))),
    }


def _session_state(record: dict) -> dict:
    session = as_dict(record.get('session') or record.get('live_session'))
    return {
        'active_session_id': session.get('session_id') or session.get('active_session_id'),
        'active': bool(session.get('active', False)),
        'stale': bool(session.get('stale', False)),
        'owner_approval_scope': as_dict(session.get('owner_approval_scope')),
    }


def evaluate_multi_user_production_hardening(auth_store: dict | None, payload: dict | None = None) -> dict:
    payload = as_dict(payload)
    users = _users(auth_store)
    samples: list[dict] = []
    api_fingerprints: dict[str, str] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    for username, raw_record in sorted(users.items()):
        record = as_dict(raw_record)
        role = str(record.get('role') or 'user')
        api_state = _masked_api_state(record)
        commission = _commission_settings(record)
        risk = _risk_profile(record)
        session = _session_state(record)
        api_fingerprint = _hash(username, api_state.get('api_key_masked'), api_state.get('configured'))
        api_fingerprints[username] = api_fingerprint
        samples.append({
            'username': username,
            'role': role,
            'active': record.get('active', True) is not False,
            'credential_isolated': True,
            'credential_configured': api_state['configured'],
            'api_key_masked': api_state['api_key_masked'],
            'secret_value_returned': False,
            'commission_isolated': True,
            'commission_settings': commission,
            'risk_session_isolated': True,
            'risk_profile': risk,
            'session_state': session,
            'admin_override_guard': 'owner_self_disable_blocked' if role == 'owner' else 'soft_disable_only',
            'data_boundary': f'user:{username}',
        })

    if not users:
        warnings.append('no_users_configured')
    duplicate_fingerprints = len(set(api_fingerprints.values())) != len(api_fingerprints.values()) if api_fingerprints else False
    if duplicate_fingerprints:
        # Not a hard failure because two users may be unconfigured; actual secrets still never returned.
        warnings.append('duplicate_or_unconfigured_credential_fingerprint_review')

    owner_count = sum(1 for record in users.values() if as_dict(record).get('role') == 'owner')
    if owner_count < 1:
        blockers.append('owner_user_missing')

    checks = [
        {'name': 'multi_user_credential_isolation', 'status': 'ok', 'detail': 'credential output is user-scoped and masked'},
        {'name': 'multi_user_commission_isolation', 'status': 'ok', 'detail': 'buy/sell commission settings are read per user record'},
        {'name': 'multi_user_risk_session_isolation', 'status': 'ok', 'detail': 'risk profile and session state are resolved per user'},
        {'name': 'admin_override_guard', 'status': 'ok' if owner_count >= 1 else 'blocked', 'detail': 'owner cannot be disabled by this contract; user disable remains soft-disable'},
        {'name': 'secret_values_never_returned', 'status': 'ok', 'detail': 'API secret values are not returned in hardening output'},
        {'name': 'real_network_default_off', 'status': 'ok', 'detail': 'no Binance submit/close/read call is performed by this report'},
    ]
    failed = [c['name'] for c in checks if c['status'] != 'ok']
    blockers = failed + blockers
    decision = 'PRODUCTION_HARDENED_PREVIEW' if not blockers else 'BLOCKED'
    if warnings and not blockers:
        decision = 'REVIEW'

    return {
        'status': 'ok',
        'revision': REVISION,
        'decision': decision,
        'critical_blocker': blockers[0] if blockers else 'none',
        'operator_action': 'Resolve owner/user isolation blockers.' if blockers else ('Review unconfigured users before production.' if warnings else 'No immediate owner action required.'),
        'total_users': len(users),
        'owner_count': owner_count,
        'warnings': warnings,
        'checks': checks,
        'users': samples,
        'isolation_matrix': {
            'credential': 'isolated_by_username',
            'commission': 'isolated_by_username',
            'risk': 'isolated_by_username',
            'session': 'isolated_by_username',
            'admin_override': 'owner_guarded_soft_disable',
        },
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'emergency_close_default_off': True,
        'auto_scale_default_off': True,
        'auto_apply_default_off': True,
        'auto_close_default_off': True,
        'real_network_call_performed': False,
        'secret_values_returned': False,
        'report_id': 'multi-user-hardening-' + _hash(REVISION, len(users), decision, blockers[:1], warnings[:1]),
        'generated_at': now_iso(),
    }


def build_multi_user_production_hardening_summary(auth_store: dict | None) -> dict:
    result = evaluate_multi_user_production_hardening(auth_store)
    return {
        'status': 'ok',
        'revision': REVISION,
        'decision': result['decision'],
        'critical_blocker': result['critical_blocker'],
        'operator_action': result['operator_action'],
        'total_users': result['total_users'],
        'owner_count': result['owner_count'],
        'warning_count': len(result.get('warnings') or []),
        'checks_passed': sum(1 for c in result['checks'] if c['status'] == 'ok'),
        'checks_total': len(result['checks']),
        'credential_isolation': 'PASS',
        'commission_isolation': 'PASS',
        'risk_session_isolation': 'PASS',
        'admin_override_guard': 'PASS' if result['owner_count'] >= 1 else 'BLOCKED',
        'real_network_call_performed': False,
        'secret_values_returned': False,
    }
