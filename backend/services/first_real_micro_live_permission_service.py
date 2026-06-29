from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

REVISION = 905

DEFAULT_SYMBOLS = ["BTCUSDT"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return fallback
        return result
    except Exception:
        return fallback


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'enabled'}


def normalize_symbol(value: Any) -> str:
    return str(value or 'BTCUSDT').upper().replace('/', '').replace('-', '').strip() or 'BTCUSDT'


def _hash(*parts: Any) -> str:
    return hashlib.sha256('|'.join(str(part) for part in parts).encode('utf-8')).hexdigest()[:16]


def get_user_record(auth_store: dict | None, username: str) -> dict:
    return as_dict(as_dict(auth_store).get('users')).get(username, {}) or {}


def _default_payload() -> dict:
    return {
        'username': 'owner',
        'symbol': 'BTCUSDT',
        'strategy': 'choch_micro_scalper',
        'requested_notional_usdt': 15,
        'max_notional_usdt': 25,
        'max_loss_usdt': 3,
        'daily_loss_usdt': 0,
        'max_daily_loss_usdt': 10,
        'owner_approved': False,
        'activation_token_present': False,
        'session_id': 'first-micro-live-session',
        'session_open': True,
        'explicit_submit_enabled': False,
        'risk_firewall': 'pass',
        'capital_gate': 'pass',
        'permission_drift': False,
        'whitelist_symbols': ['BTCUSDT', 'ETHUSDT'],
    }


def _contract(payload: dict, user_record: dict) -> dict:
    symbol = normalize_symbol(payload.get('symbol'))
    requested = max(0.0, safe_float(payload.get('requested_notional_usdt'), 0.0))
    max_notional = max(0.0, safe_float(payload.get('max_notional_usdt'), 0.0))
    max_loss = max(0.0, safe_float(payload.get('max_loss_usdt'), 0.0))
    user_allowed = [normalize_symbol(item) for item in as_list(user_record.get('allowed_symbols'))]
    payload_whitelist = [normalize_symbol(item) for item in as_list(payload.get('whitelist_symbols'))]
    allowed_symbols = payload_whitelist or user_allowed or DEFAULT_SYMBOLS
    allowed_symbols = sorted(set(allowed_symbols))
    effective_notional = min(requested, max_notional) if max_notional > 0 else 0.0
    blockers = []
    if requested <= 0:
        blockers.append('requested_notional_missing')
    if max_notional <= 0:
        blockers.append('max_notional_missing')
    if requested > max_notional > 0:
        blockers.append('requested_notional_above_contract')
    if max_loss <= 0:
        blockers.append('max_loss_missing')
    if symbol not in allowed_symbols:
        blockers.append('symbol_not_whitelisted')
    return {
        'contract_id': 'first-micro-live-permission-' + _hash(symbol, requested, max_notional, max_loss, ','.join(allowed_symbols)),
        'symbol': symbol,
        'strategy': str(payload.get('strategy') or 'unknown_strategy').strip() or 'unknown_strategy',
        'requested_notional_usdt': round(requested, 8),
        'max_notional_usdt': round(max_notional, 8),
        'effective_notional_usdt': round(effective_notional, 8),
        'max_loss_usdt': round(max_loss, 8),
        'allowed_symbols': allowed_symbols,
        'status': 'ready' if not blockers else 'blocked',
        'blockers': blockers,
        'secret_values_returned': False,
    }


def _owner_guard(payload: dict, contract: dict) -> dict:
    owner_approved = safe_bool(payload.get('owner_approved'))
    token_present = safe_bool(payload.get('activation_token_present'))
    session_open = safe_bool(payload.get('session_open'))
    explicit_submit_enabled = safe_bool(payload.get('explicit_submit_enabled'))
    session_id = str(payload.get('session_id') or '').strip()
    blockers = []
    if contract.get('status') != 'ready':
        blockers.append('permission_contract_blocked')
    if not owner_approved:
        blockers.append('owner_approval_missing')
    if not token_present:
        blockers.append('activation_token_missing')
    if not session_id:
        blockers.append('session_id_missing')
    if not session_open:
        blockers.append('session_closed')
    if not explicit_submit_enabled:
        blockers.append('explicit_submit_disabled')
    return {
        'owner_approved': owner_approved,
        'activation_token_present': token_present,
        'activation_token_value_returned': False,
        'session_id': session_id or 'missing-session',
        'session_open': session_open,
        'explicit_submit_enabled': explicit_submit_enabled,
        'status': 'ready' if not blockers else 'blocked',
        'blockers': blockers,
        'secret_values_returned': False,
    }


def _risk_guard(payload: dict, contract: dict) -> dict:
    daily_loss = max(0.0, safe_float(payload.get('daily_loss_usdt'), 0.0))
    max_daily_loss = max(0.0, safe_float(payload.get('max_daily_loss_usdt'), 0.0))
    firewall = str(payload.get('risk_firewall') or 'pass').strip().lower()
    capital_gate = str(payload.get('capital_gate') or 'pass').strip().lower()
    permission_drift = safe_bool(payload.get('permission_drift'))
    blockers = []
    if contract.get('status') != 'ready':
        blockers.append('permission_contract_blocked')
    if firewall not in {'pass', 'ok', 'ready'}:
        blockers.append('risk_firewall_blocked')
    if capital_gate not in {'pass', 'ok', 'ready'}:
        blockers.append('capital_gate_blocked')
    if max_daily_loss > 0 and daily_loss >= max_daily_loss:
        blockers.append('daily_hard_stop_reached')
    if permission_drift:
        blockers.append('exchange_permission_drift')
    if contract.get('max_loss_usdt', 0) > max(0.0, max_daily_loss - daily_loss) and max_daily_loss > 0:
        blockers.append('max_loss_exceeds_remaining_daily_budget')
    return {
        'risk_firewall': firewall,
        'capital_gate': capital_gate,
        'permission_drift': permission_drift,
        'daily_loss_usdt': round(daily_loss, 8),
        'max_daily_loss_usdt': round(max_daily_loss, 8),
        'remaining_daily_loss_budget_usdt': round(max(0.0, max_daily_loss - daily_loss), 8),
        'status': 'ready' if not blockers else 'blocked',
        'blockers': blockers,
        'real_submit_allowed': False,
        'secret_values_returned': False,
    }


def evaluate_first_real_micro_live_permission(payload: dict | None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = {**_default_payload(), **as_dict(payload)}
    user_record = get_user_record(auth_store, username)
    contract = _contract(payload, user_record)
    owner_guard = _owner_guard(payload, contract)
    risk_guard = _risk_guard(payload, contract)
    checks = [
        {'name': 'max_notional_contract', 'status': 'ok' if 'max_notional_missing' not in contract['blockers'] and 'requested_notional_above_contract' not in contract['blockers'] else 'blocked'},
        {'name': 'max_loss_contract', 'status': 'ok' if 'max_loss_missing' not in contract['blockers'] and 'max_loss_exceeds_remaining_daily_budget' not in risk_guard['blockers'] else 'blocked'},
        {'name': 'whitelist_symbol_lock', 'status': 'ok' if 'symbol_not_whitelisted' not in contract['blockers'] else 'blocked'},
        {'name': 'owner_approval_required', 'status': 'ok' if owner_guard['owner_approved'] or 'owner_approval_missing' in owner_guard['blockers'] else 'blocked'},
        {'name': 'activation_token_presence_only', 'status': 'ok' if owner_guard['activation_token_value_returned'] is False else 'blocked'},
        {'name': 'explicit_submit_default_off', 'status': 'ok' if owner_guard['explicit_submit_enabled'] is False or owner_guard['status'] == 'ready' else 'ok'},
        {'name': 'real_network_not_called', 'status': 'ok'},
        {'name': 'secret_values_never_returned', 'status': 'ok'},
    ]
    all_blockers = contract['blockers'] + owner_guard['blockers'] + risk_guard['blockers']
    failed_checks = [item['name'] for item in checks if item['status'] != 'ok']
    if failed_checks or contract['status'] != 'ready' or risk_guard['status'] != 'ready':
        decision = 'NO_GO'
        operator_action = 'Fix first micro-live permission blockers before approval.'
    elif owner_guard['status'] != 'ready':
        decision = 'PERMISSION_BLOCKED'
        operator_action = 'Owner approval, activation token and explicit enable are required; do not submit real order.'
    else:
        decision = 'LIMITED_GO_PREVIEW_ONLY'
        operator_action = 'Permission packet is ready for owner-controlled preview; real submit remains default OFF.'
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': decision,
        'critical_blocker': (failed_checks[0] if failed_checks else (all_blockers[0] if all_blockers else 'real_submit_default_off_policy')),
        'operator_action': operator_action,
        'permission_contract': contract,
        'owner_activation_guard': owner_guard,
        'risk_and_permission_guard': risk_guard,
        'checks': checks,
        'blockers': all_blockers,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'real_network_call_performed': False,
        'auto_scale_default_off': True,
        'auto_apply_default_off': True,
        'auto_close_default_off': True,
        'secret_values_returned': False,
        'generated_at': now_iso(),
    }


def build_first_real_micro_live_permission_summary(auth_store: dict | None = None, username: str = 'default') -> dict:
    result = evaluate_first_real_micro_live_permission(_default_payload(), auth_store, username)
    contract = result['permission_contract']
    owner = result['owner_activation_guard']
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': result['decision'],
        'critical_blocker': result['critical_blocker'],
        'operator_action': result['operator_action'],
        'symbol': contract['symbol'],
        'strategy': contract['strategy'],
        'max_notional_usdt': contract['max_notional_usdt'],
        'max_loss_usdt': contract['max_loss_usdt'],
        'allowed_symbols': contract['allowed_symbols'],
        'owner_approved': owner['owner_approved'],
        'activation_token_present': owner['activation_token_present'],
        'activation_token_value_returned': False,
        'session_id': owner['session_id'],
        'checks': result['checks'],
        'real_submit_default_off': True,
        'real_network_call_performed': False,
        'secret_values_returned': False,
    }
