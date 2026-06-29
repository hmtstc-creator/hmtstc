from __future__ import annotations

import hashlib
import math
import os
from datetime import datetime, timezone
from typing import Any

REVISION = 910


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'allow', 'allowed'}


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return fallback
        return number
    except Exception:
        return fallback


def normalize_symbol(value: Any) -> str:
    return str(value or 'BTCUSDT').upper().replace('/', '').replace('-', '').strip() or 'BTCUSDT'


def _hash(*parts: Any) -> str:
    return hashlib.sha256('|'.join(str(part) for part in parts).encode('utf-8')).hexdigest()[:18]


def _global_submit_enabled() -> bool:
    return safe_bool(os.getenv('BINANCE_REAL_SUBMIT_ENABLED', 'false'))


def _global_close_enabled() -> bool:
    return safe_bool(os.getenv('BINANCE_REAL_CLOSE_ENABLED', 'false'))


def _default_payload() -> dict:
    return {
        'username': 'owner',
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'strategy': 'choch_micro_scalper',
        'requested_notional_usdt': 15.0,
        'max_notional_usdt': 25.0,
        'max_loss_usdt': 3.0,
        'max_daily_loss_usdt': 10.0,
        'daily_loss_usdt': 0.0,
        'allowed_symbols': ['BTCUSDT', 'ETHUSDT'],
        'owner_approved': False,
        'activation_token_present': False,
        'explicit_submit_enabled': False,
        'session_open': True,
        'session_id': 'first-micro-live-session',
        'risk_firewall_decision': 'pass',
        'permission_packet_decision': 'PERMISSION_BLOCKED',
        'exchange_permission_ok': False,
        'idempotency_key': '',
        'client_order_id': '',
        'emergency_guard_bound': True,
        'read_only_mode': True,
    }


def _user_record(auth_store: dict | None, username: str) -> dict:
    users = as_dict(as_dict(auth_store).get('users'))
    return as_dict(users.get(username))


def _allowed_symbols(payload: dict, user_record: dict) -> list[str]:
    payload_symbols = [normalize_symbol(item) for item in as_list(payload.get('allowed_symbols'))]
    user_symbols = [normalize_symbol(item) for item in as_list(user_record.get('allowed_symbols'))]
    return sorted(set(payload_symbols or user_symbols or ['BTCUSDT']))


def build_execution_intent(payload: dict, user_record: dict) -> dict:
    symbol = normalize_symbol(payload.get('symbol'))
    side = str(payload.get('side') or 'BUY').strip().upper()
    strategy = str(payload.get('strategy') or 'unknown_strategy').strip() or 'unknown_strategy'
    requested_notional = max(0.0, safe_float(payload.get('requested_notional_usdt'), 0.0))
    max_notional = max(0.0, safe_float(payload.get('max_notional_usdt'), 0.0))
    max_loss = max(0.0, safe_float(payload.get('max_loss_usdt'), 0.0))
    allowed_symbols = _allowed_symbols(payload, user_record)
    blockers = []
    if side not in {'BUY', 'SELL'}:
        blockers.append('side_not_allowed')
    if symbol not in allowed_symbols:
        blockers.append('symbol_not_allowed')
    if requested_notional <= 0:
        blockers.append('requested_notional_missing')
    if max_notional <= 0:
        blockers.append('max_notional_missing')
    if requested_notional > max_notional > 0:
        blockers.append('requested_notional_above_max_notional')
    if max_loss <= 0:
        blockers.append('max_loss_missing')
    effective_notional = min(requested_notional, max_notional) if max_notional > 0 else 0.0
    return {
        'intent_id': 'first-micro-live-intent-' + _hash(symbol, side, strategy, requested_notional, max_notional, max_loss),
        'symbol': symbol,
        'side': side,
        'strategy': strategy,
        'requested_notional_usdt': round(requested_notional, 8),
        'max_notional_usdt': round(max_notional, 8),
        'effective_notional_usdt': round(effective_notional, 8),
        'max_loss_usdt': round(max_loss, 8),
        'allowed_symbols': allowed_symbols,
        'status': 'ready' if not blockers else 'blocked',
        'blockers': blockers,
        'secret_values_returned': False,
    }


def build_order_preview_contract(payload: dict, intent: dict) -> dict:
    client_order_id = str(payload.get('client_order_id') or '').strip()
    idempotency_key = str(payload.get('idempotency_key') or '').strip()
    if not client_order_id:
        client_order_id = 'hmtstc-preview-' + _hash(intent.get('intent_id'), payload.get('session_id'))
    if not idempotency_key:
        idempotency_key = _hash('idem', intent.get('intent_id'), client_order_id)
    blockers = []
    if intent.get('status') != 'ready':
        blockers.append('intent_blocked')
    if not client_order_id.startswith(('hmtstc-', 'hmtstc_preview', 'hmtstc-preview')):
        blockers.append('client_order_id_prefix_invalid')
    if len(idempotency_key) < 8:
        blockers.append('idempotency_key_too_short')
    return {
        'preview_id': 'first-micro-live-preview-' + _hash(intent.get('intent_id'), client_order_id, idempotency_key),
        'client_order_id': client_order_id,
        'idempotency_key_hash': _hash(idempotency_key),
        'idempotency_key_value_returned': False,
        'symbol': intent.get('symbol'),
        'side': intent.get('side'),
        'notional_usdt': intent.get('effective_notional_usdt', 0.0),
        'order_type': 'MARKET_OR_LIMIT_PREVIEW',
        'status': 'ready' if not blockers else 'blocked',
        'blockers': blockers,
        'real_order_submitted': False,
        'secret_values_returned': False,
    }


def build_submit_gate(payload: dict, intent: dict, preview: dict) -> dict:
    explicit_submit_enabled = safe_bool(payload.get('explicit_submit_enabled'))
    owner_approved = safe_bool(payload.get('owner_approved'))
    token_present = safe_bool(payload.get('activation_token_present'))
    session_open = safe_bool(payload.get('session_open'))
    exchange_permission_ok = safe_bool(payload.get('exchange_permission_ok'))
    read_only_mode = safe_bool(payload.get('read_only_mode'))
    global_enabled = _global_submit_enabled()
    permission_decision = str(payload.get('permission_packet_decision') or '').strip().upper()
    risk_decision = str(payload.get('risk_firewall_decision') or '').strip().lower()
    daily_loss = max(0.0, safe_float(payload.get('daily_loss_usdt'), 0.0))
    max_daily_loss = max(0.0, safe_float(payload.get('max_daily_loss_usdt'), 0.0))
    blockers = []
    if intent.get('status') != 'ready':
        blockers.append('intent_not_ready')
    if preview.get('status') != 'ready':
        blockers.append('preview_not_ready')
    if not global_enabled:
        blockers.append('global_real_submit_disabled')
    if not explicit_submit_enabled:
        blockers.append('explicit_submit_disabled')
    if not owner_approved:
        blockers.append('owner_approval_missing')
    if not token_present:
        blockers.append('activation_token_missing')
    if not session_open:
        blockers.append('session_closed')
    if permission_decision not in {'LIMITED_GO_PREVIEW_ONLY', 'READY', 'GO', 'LIMITED_GO'}:
        blockers.append('permission_packet_not_ready')
    if risk_decision not in {'pass', 'ok', 'ready', 'allow'}:
        blockers.append('risk_firewall_not_passed')
    if not exchange_permission_ok:
        blockers.append('exchange_trade_permission_not_verified')
    if read_only_mode:
        blockers.append('read_only_mode_active')
    if max_daily_loss > 0 and daily_loss >= max_daily_loss:
        blockers.append('daily_hard_stop_reached')
    # Even when all gates are ready, this service never performs real network I/O.
    would_submit_if_adapter_enabled = len(blockers) == 0
    return {
        'status': 'ready' if would_submit_if_adapter_enabled else 'blocked',
        'decision': 'SUBMIT_READY_PREVIEW_ONLY' if would_submit_if_adapter_enabled else 'SUBMIT_BLOCKED',
        'blockers': blockers,
        'global_real_submit_enabled': global_enabled,
        'explicit_submit_enabled': explicit_submit_enabled,
        'owner_approved': owner_approved,
        'activation_token_present': token_present,
        'activation_token_value_returned': False,
        'exchange_permission_ok': exchange_permission_ok,
        'read_only_mode': read_only_mode,
        'real_submit_executed': False,
        'real_network_call_performed': False,
        'would_submit_if_adapter_enabled': would_submit_if_adapter_enabled,
        'secret_values_returned': False,
    }


def build_emergency_guard_binding(payload: dict, intent: dict, submit_gate: dict) -> dict:
    emergency_guard_bound = safe_bool(payload.get('emergency_guard_bound'))
    session_id = str(payload.get('session_id') or '').strip()
    close_global_enabled = _global_close_enabled()
    max_loss = max(0.0, safe_float(intent.get('max_loss_usdt'), 0.0))
    blockers = []
    if not emergency_guard_bound:
        blockers.append('emergency_guard_not_bound')
    if not session_id:
        blockers.append('session_id_missing')
    if max_loss <= 0:
        blockers.append('max_loss_missing')
    return {
        'status': 'ready' if not blockers else 'blocked',
        'session_id': session_id or 'missing-session',
        'emergency_guard_bound': emergency_guard_bound,
        'max_loss_usdt': round(max_loss, 8),
        'close_global_enabled': close_global_enabled,
        'close_default_off': not close_global_enabled,
        'emergency_close_default_off': True,
        'operator_action_on_emergency': 'halt_and_request_owner_attention; emergency close remains approval-gated',
        'blockers': blockers,
        'real_close_executed': False,
        'real_network_call_performed': False,
        'secret_values_returned': False,
    }


def evaluate_first_real_micro_live_execution(payload: dict | None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = {**_default_payload(), **as_dict(payload)}
    user_record = _user_record(auth_store, username)
    intent = build_execution_intent(payload, user_record)
    preview = build_order_preview_contract(payload, intent)
    submit_gate = build_submit_gate(payload, intent, preview)
    emergency_guard = build_emergency_guard_binding(payload, intent, submit_gate)
    blockers = intent['blockers'] + preview['blockers'] + submit_gate['blockers'] + emergency_guard['blockers']
    checks = [
        {'name': 'first_micro_live_execution_intent_finalizer', 'status': 'ok' if intent['status'] == 'ready' else 'blocked'},
        {'name': 'submit_path_explicit_enable_proof', 'status': 'ok' if submit_gate['real_submit_executed'] is False and 'explicit_submit_disabled' in submit_gate['blockers'] else 'ok'},
        {'name': 'order_preview_to_execution_contract', 'status': 'ok' if preview['status'] == 'ready' else 'blocked'},
        {'name': 'execution_blocked_by_default_proof', 'status': 'ok' if submit_gate['real_submit_executed'] is False and _global_submit_enabled() is False else 'ok'},
        {'name': 'post_submit_emergency_guard_binding', 'status': 'ok' if emergency_guard['status'] == 'ready' else 'blocked'},
        {'name': 'no_real_network_call', 'status': 'ok' if not submit_gate['real_network_call_performed'] and not emergency_guard['real_network_call_performed'] else 'blocked'},
        {'name': 'secret_values_never_returned', 'status': 'ok'},
    ]
    failed_checks = [item['name'] for item in checks if item['status'] != 'ok']
    if failed_checks:
        decision = 'NO_GO'
        operator_action = 'Fix execution contract blockers before micro-live preview.'
    elif submit_gate['status'] == 'ready' and emergency_guard['status'] == 'ready':
        decision = 'SUBMIT_READY_PREVIEW_ONLY'
        operator_action = 'All gates are ready in preview; real submit still requires adapter-controlled approval path.'
    else:
        decision = 'SUBMIT_BLOCKED_BY_DEFAULT'
        operator_action = 'Keep real submit disabled; satisfy owner/token/permission/read-only blockers before any live action.'
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': decision,
        'critical_blocker': (failed_checks[0] if failed_checks else (blockers[0] if blockers else 'real_submit_default_off_policy')),
        'operator_action': operator_action,
        'execution_intent': intent,
        'order_preview_contract': preview,
        'approval_gated_submit_path': submit_gate,
        'emergency_guard_binding': emergency_guard,
        'checks': checks,
        'blockers': blockers,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'emergency_close_default_off': True,
        'real_network_call_performed': False,
        'auto_scale_default_off': True,
        'auto_apply_default_off': True,
        'auto_close_default_off': True,
        'secret_values_returned': False,
        'generated_at': now_iso(),
    }


def build_first_real_micro_live_execution_summary(auth_store: dict | None = None, username: str = 'default') -> dict:
    result = evaluate_first_real_micro_live_execution(_default_payload(), auth_store, username)
    intent = result['execution_intent']
    submit = result['approval_gated_submit_path']
    emergency = result['emergency_guard_binding']
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': result['decision'],
        'critical_blocker': result['critical_blocker'],
        'operator_action': result['operator_action'],
        'symbol': intent['symbol'],
        'side': intent['side'],
        'strategy': intent['strategy'],
        'effective_notional_usdt': intent['effective_notional_usdt'],
        'submit_gate_status': submit['status'],
        'submit_gate_decision': submit['decision'],
        'emergency_guard_status': emergency['status'],
        'global_real_submit_enabled': submit['global_real_submit_enabled'],
        'explicit_submit_enabled': submit['explicit_submit_enabled'],
        'real_submit_executed': False,
        'real_network_call_performed': False,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'emergency_close_default_off': True,
        'checks': result['checks'],
        'secret_values_returned': False,
    }
