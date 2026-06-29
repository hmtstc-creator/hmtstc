from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from services.autonomous_order_status_poller_exchange_response_recorder_service import build_autonomous_order_status_poller_exchange_response_recorder


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {'1','true','yes','on','enabled','allow','allowed','ready','armed','confirmed'}:
            return True
        if text in {'0','false','no','off','disabled','deny','blocked','none'}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == '':
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_text(value: Any, fallback: str = '') -> str:
    text = str(value or '').strip()
    return text or fallback


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get(key) if isinstance(settings.get(key), dict) else {}
    return raw


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {'name': name, 'status': status, 'required': required, 'detail': detail}


def _totals(checks: list[dict]) -> dict:
    return {
        'total': len(checks),
        'ok': len([c for c in checks if c.get('status') == 'ok']),
        'review': len([c for c in checks if c.get('status') == 'review']),
        'blocked': len([c for c in checks if c.get('status') == 'blocked']),
    }


def _final_status(checks: list[dict]) -> str:
    return 'blocked' if any(c.get('status') == 'blocked' and c.get('required') for c in checks) else ('ok' if not any(c.get('status') == 'review' for c in checks) else 'review')


def _source107(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get('autonomous_order_status_poller_exchange_response_recorder') if isinstance(data.get('autonomous_order_status_poller_exchange_response_recorder'), dict) else None
    if raw and raw.get('revision') == 107:
        return raw
    return build_autonomous_order_status_poller_exchange_response_recorder(data, settings, auth_store, username)


def _order_public(source: dict) -> dict:
    return source.get('poll_request_public') if isinstance(source.get('poll_request_public'), dict) else {}


def _normalized_status(source: dict) -> dict:
    return source.get('normalized_order_status') if isinstance(source.get('normalized_order_status'), dict) else {}


def _hash(prefix: str, *parts: Any) -> str:
    return prefix + sha256(':'.join(_safe_text(p) for p in parts).encode('utf-8')).hexdigest()[:24]


def _auth_user(auth_store: dict | None, username: str) -> dict:
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    users = auth_store.get('users') if isinstance(auth_store.get('users'), dict) else {}
    return users.get(username) if isinstance(users.get(username), dict) else {}


def build_rev108_balance_reconciliation_manual_attention(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    src = _source107(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_balance_reconciliation_manual_attention')
    status = _normalized_status(src)
    order = _order_public(src)
    executed_quote = _safe_float(status.get('cumulative_quote_qty'), _safe_float(order.get('quoteOrderQty'), 0.0))
    expected_delta = executed_quote if str(status.get('side') or 'BUY').upper() == 'BUY' else -executed_quote
    tolerance = _safe_float(policy.get('reconciliation_tolerance_usdt'), 0.25)
    balance = data.get('balance_reconciliation_snapshot') if isinstance(data.get('balance_reconciliation_snapshot'), dict) else {}
    observed_delta = _safe_float(balance.get('observed_usdt_delta'), expected_delta)
    mismatch = abs(observed_delta - expected_delta)
    manual_attention = mismatch > tolerance or status.get('status') in {'REJECTED','EXPIRED'}
    checks = [
        _check('rev107_source_present', 'ok' if src.get('revision') == 107 else 'blocked', 'Rev108 consumes Rev107 order status recorder.'),
        _check('secret_free_source', 'ok' if not src.get('contains_secret') else 'blocked', 'Source must be secret-free.'),
        _check('status_terminal_or_trackable', 'ok' if status.get('status') in {'FILLED','PARTIALLY_FILLED','NEW','CANCELED','DRY_RUN_NOT_SUBMITTED'} else 'review', 'Order status is normalized and trackable.', False),
        _check('reconciliation_tolerance', 'ok' if mismatch <= tolerance else 'review', 'Balance delta mismatch requires manual attention.', False),
        _check('runtime_write_disabled', 'ok' if not _safe_bool(policy.get('allow_runtime_write'), False) else 'review', 'Runtime write is disabled by default.', False),
    ]
    result = {
        'engine': 'autonomous_balance_reconciliation_manual_attention', 'revision': 108,
        'status': _final_status(checks), 'readiness': 'BALANCE_RECONCILIATION_ATTENTION' if manual_attention else 'BALANCE_RECONCILIATION_OK_PREVIEW',
        'expected_usdt_delta': round(expected_delta, 8), 'observed_usdt_delta': round(observed_delta, 8), 'mismatch_usdt': round(mismatch, 8),
        'manual_attention_required': manual_attention, 'attention_reason': 'balance_delta_mismatch_or_rejected_order' if manual_attention else 'none',
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False},
        'next_allowed_step': 'live_position_tracker' if not manual_attention else 'manual_attention_before_live_tracking',
        'contains_secret': False, 'secret_values_returned': False,
    }
    return result


def build_rev109_live_position_tracker(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    rev108 = data.get('autonomous_balance_reconciliation_manual_attention') if isinstance(data.get('autonomous_balance_reconciliation_manual_attention'), dict) else build_rev108_balance_reconciliation_manual_attention(data, settings, auth_store, username)
    src = _source107(data, settings, auth_store, username)
    status = _normalized_status(src)
    symbol = _safe_text(status.get('symbol') or _order_public(src).get('symbol'), 'UNKNOWN').upper()
    qty = _safe_float(status.get('executed_qty'), 0.0)
    quote = _safe_float(status.get('cumulative_quote_qty'), rev108.get('expected_usdt_delta', 0.0))
    avg = _safe_float(status.get('avg_price'), 0.0) or (quote / qty if qty > 0 and quote > 0 else 0.0)
    open_position = qty > 0 and str(status.get('status')).upper() in {'FILLED','PARTIALLY_FILLED','NEW'}
    position = {
        'position_id': _hash('pos109_', username, symbol, status.get('client_order_id'), qty),
        'symbol': symbol, 'status': 'open_preview' if open_position else 'no_open_position',
        'quantity': round(qty, 10), 'entry_price': round(avg, 10), 'notional_usdt': round(quote, 8),
        'source_order_status': status.get('status'), 'stale_position': False, 'contains_secret': False,
    }
    checks = [
        _check('rev108_not_blocked', 'ok' if rev108.get('status') != 'blocked' else 'blocked', 'Reconciliation must not be blocked.'),
        _check('manual_attention_clear', 'ok' if not rev108.get('manual_attention_required') else 'review', 'Manual attention should be clear before live tracking.', False),
        _check('position_source_secret_free', 'ok' if not src.get('contains_secret') else 'blocked', 'Position source must be secret-free.'),
        _check('no_exchange_request', 'ok', 'Tracker is state preview; no exchange request.'),
    ]
    return {
        'engine': 'autonomous_live_position_tracker', 'revision': 109, 'status': _final_status(checks),
        'readiness': 'LIVE_POSITION_TRACKING_PREVIEW' if open_position else 'NO_LIVE_POSITION_TO_TRACK',
        'position': position, 'open_position_detected': open_position,
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False},
        'next_allowed_step': 'live_stop_tp_trailing_guard', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev110_live_stop_tp_trailing_guard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    tracker = data.get('autonomous_live_position_tracker') if isinstance(data.get('autonomous_live_position_tracker'), dict) else build_rev109_live_position_tracker(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_live_stop_tp_trailing_guard')
    pos = tracker.get('position') if isinstance(tracker.get('position'), dict) else {}
    entry = _safe_float(pos.get('entry_price'), 0.0)
    current = _safe_float(data.get('current_price') or policy.get('current_price'), entry)
    sl_pct = _safe_float(policy.get('stop_loss_pct'), 2.0)
    tp_pct = _safe_float(policy.get('take_profit_pct'), 1.5)
    trail_pct = _safe_float(policy.get('trailing_stop_pct'), 0.8)
    sl = entry * (1 - sl_pct / 100) if entry else 0.0
    tp = entry * (1 + tp_pct / 100) if entry else 0.0
    trail = max(sl, current * (1 - trail_pct / 100)) if current else sl
    action = 'hold'
    if current and sl and current <= sl: action = 'exit_stop_loss_review'
    elif current and tp and current >= tp: action = 'exit_take_profit_review'
    elif current and trail and current <= trail and current > entry: action = 'exit_trailing_review'
    checks = [
        _check('tracker_not_blocked', 'ok' if tracker.get('status') != 'blocked' else 'blocked', 'Position tracker must not be blocked.'),
        _check('open_position_detected', 'ok' if tracker.get('open_position_detected') else 'review', 'No open live position detected.', False),
        _check('guard_prices_valid', 'ok' if entry > 0 else 'review', 'Entry price is needed for guard math.', False),
        _check('no_direct_exit', 'ok', 'Rev110 only builds exit guard preview.'),
    ]
    return {
        'engine': 'autonomous_live_stop_tp_trailing_guard', 'revision': 110, 'status': _final_status(checks),
        'readiness': 'LIVE_EXIT_GUARD_ACTIVE_PREVIEW', 'position_id': pos.get('position_id'), 'symbol': pos.get('symbol'),
        'guard_levels': {'entry_price': round(entry,10), 'current_price': round(current,10), 'stop_loss': round(sl,10), 'take_profit': round(tp,10), 'trailing_stop': round(trail,10)},
        'recommended_action': action,
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False},
        'next_allowed_step': 'live_exit_submitter', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev111_live_exit_submitter(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default', exit_adapter: Callable[[dict], dict] | None = None) -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    guard = data.get('autonomous_live_stop_tp_trailing_guard') if isinstance(data.get('autonomous_live_stop_tp_trailing_guard'), dict) else build_rev110_live_stop_tp_trailing_guard(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_live_exit_submitter')
    user = _auth_user(auth_store, username)
    allow_network = _safe_bool(policy.get('allow_network_calls'), False)
    enable_live_close = _safe_bool(policy.get('enable_live_close'), False)
    owner_confirmed = _safe_bool(policy.get('owner_confirmed'), False)
    explicit_token = _safe_text(policy.get('owner_confirmation_token')) == _safe_text(policy.get('expected_owner_confirmation_token'), 'CONFIRM_EXIT')
    emergency_ready = _safe_bool(policy.get('emergency_close_ready'), True)
    exit_intent = {
        'intent_id': _hash('exit111_', username, guard.get('position_id'), guard.get('recommended_action')),
        'exchange': 'binance', 'symbol': guard.get('symbol'), 'side': 'SELL', 'type': 'MARKET',
        'reason': guard.get('recommended_action'), 'reduce_only_semantics': True, 'contains_secret': False,
    }
    permitted = allow_network and enable_live_close and owner_confirmed and explicit_token and emergency_ready and _safe_bool(user.get('trade_permission'), False)
    adapter_response = None
    if permitted and exit_adapter is not None:
        adapter_response = exit_adapter(exit_intent)
    checks = [
        _check('guard_not_blocked', 'ok' if guard.get('status') != 'blocked' else 'blocked', 'Exit guard must not be blocked.'),
        _check('trade_permission', 'ok' if _safe_bool(user.get('trade_permission'), False) else 'blocked', 'Trade permission is required.'),
        _check('owner_confirmation', 'ok' if owner_confirmed and explicit_token else 'blocked', 'Owner confirmation token required.'),
        _check('emergency_close_ready', 'ok' if emergency_ready else 'blocked', 'Emergency close readiness is required.'),
        _check('live_close_flag', 'ok' if enable_live_close else 'blocked', 'Explicit live close flag is required.'),
        _check('network_flag', 'ok' if allow_network else 'blocked', 'Network flag must be explicitly enabled.'),
    ]
    return {
        'engine': 'autonomous_live_exit_submitter', 'revision': 111, 'status': _final_status(checks),
        'readiness': 'LIVE_EXIT_SUBMIT_ALLOWED' if permitted else 'LIVE_EXIT_SUBMIT_BLOCKED',
        'exit_intent_public': exit_intent, 'adapter_response_public': adapter_response if adapter_response else {'ok': False, 'adapter_state': 'NOT_CALLED_DEFAULT_GUARD'},
        'live_path': {'network_call_attempted': bool(permitted and exit_adapter), 'real_close_attempted': bool(permitted and exit_adapter), 'runtime_write_attempted': False},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': permitted, 'sends_exchange_request': bool(permitted and exit_adapter), 'writes_runtime_state': False},
        'next_allowed_step': 'emergency_close_submitter', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev112_emergency_close_submitter(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default', close_adapter: Callable[[dict], dict] | None = None) -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    exit_submitter = data.get('autonomous_live_exit_submitter') if isinstance(data.get('autonomous_live_exit_submitter'), dict) else build_rev111_live_exit_submitter(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_emergency_close_submitter')
    user = _auth_user(auth_store, username)
    emergency_triggered = _safe_bool(policy.get('emergency_triggered'), False)
    allow_network = _safe_bool(policy.get('allow_network_calls'), False)
    enable = _safe_bool(policy.get('enable_emergency_close'), False)
    owner_confirmed = _safe_bool(policy.get('owner_confirmed'), False)
    kill_switch_clear = not _safe_bool(policy.get('kill_switch_active'), False)
    emergency_intent = {**(exit_submitter.get('exit_intent_public') or {}), 'intent_id': _hash('emg112_', username, now_iso()), 'reason': 'emergency_close', 'contains_secret': False}
    permitted = emergency_triggered and allow_network and enable and owner_confirmed and kill_switch_clear and _safe_bool(user.get('trade_permission'), False)
    adapter_response = close_adapter(emergency_intent) if permitted and close_adapter is not None else None
    checks = [
        _check('trade_permission', 'ok' if _safe_bool(user.get('trade_permission'), False) else 'blocked', 'Trade permission required.'),
        _check('emergency_triggered', 'ok' if emergency_triggered else 'review', 'Emergency close is not triggered by default.', False),
        _check('owner_confirmed', 'ok' if owner_confirmed else 'blocked', 'Owner confirmation required.'),
        _check('enable_emergency_close', 'ok' if enable else 'blocked', 'Explicit emergency close enable flag required.'),
        _check('network_flag', 'ok' if allow_network else 'blocked', 'Network flag must be explicitly enabled.'),
        _check('kill_switch_clear', 'ok' if kill_switch_clear else 'blocked', 'Kill switch blocks emergency close submit path.'),
    ]
    return {
        'engine': 'autonomous_emergency_close_submitter', 'revision': 112, 'status': _final_status(checks),
        'readiness': 'EMERGENCY_CLOSE_ALLOWED' if permitted else 'EMERGENCY_CLOSE_BLOCKED',
        'emergency_intent_public': emergency_intent, 'adapter_response_public': adapter_response if adapter_response else {'ok': False, 'adapter_state': 'NOT_CALLED_DEFAULT_GUARD'},
        'live_path': {'network_call_attempted': bool(permitted and close_adapter), 'real_close_attempted': bool(permitted and close_adapter), 'runtime_write_attempted': False},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': permitted, 'sends_exchange_request': bool(permitted and close_adapter), 'writes_runtime_state': False},
        'next_allowed_step': 'realized_pnl_trade_journal', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev113_realized_pnl_trade_journal(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    tracker = data.get('autonomous_live_position_tracker') if isinstance(data.get('autonomous_live_position_tracker'), dict) else build_rev109_live_position_tracker(data, settings, auth_store, username)
    guard = data.get('autonomous_live_stop_tp_trailing_guard') if isinstance(data.get('autonomous_live_stop_tp_trailing_guard'), dict) else build_rev110_live_stop_tp_trailing_guard(data, settings, auth_store, username)
    pos = tracker.get('position') if isinstance(tracker.get('position'), dict) else {}
    qty = _safe_float(pos.get('quantity'), 0.0)
    entry = _safe_float(pos.get('entry_price'), 0.0)
    exit_price = _safe_float(data.get('exit_price') or (guard.get('guard_levels') or {}).get('current_price'), entry)
    gross = (exit_price - entry) * qty
    fees = _safe_float(data.get('realized_fee_usdt'), abs(entry * qty) * 0.001 + abs(exit_price * qty) * 0.001)
    net = gross - fees
    notional = max(abs(entry * qty), 1e-9)
    roi = (net / notional) * 100
    journal = {
        'journal_id': _hash('j113_', username, pos.get('position_id'), entry, exit_price),
        'record_type': 'realized_micro_trade_result_preview', 'symbol': pos.get('symbol'),
        'entry_price': round(entry, 10), 'exit_price': round(exit_price, 10), 'quantity': round(qty, 10),
        'gross_pnl_usdt': round(gross, 8), 'fees_usdt': round(fees, 8), 'net_pnl_usdt': round(net, 8), 'roi_pct': round(roi, 6),
        'contains_secret': False, 'secret_values_returned': False, 'writes_runtime_state': False,
    }
    checks = [
        _check('position_tracker_available', 'ok' if tracker.get('revision') == 109 else 'blocked', 'Rev109 tracker is required.'),
        _check('pnl_inputs_valid', 'ok' if qty > 0 and entry > 0 else 'review', 'PnL inputs are preview-only until live fill exists.', False),
        _check('journal_secret_free', 'ok' if not journal.get('contains_secret') else 'blocked', 'Journal must be secret-free.'),
        _check('runtime_write_disabled', 'ok', 'Runtime write disabled in final package; journal schema only.'),
    ]
    decision = 'repeat_small_probe' if net > 0 else ('tighten_or_cooldown' if qty > 0 else 'await_live_fill')
    return {
        'engine': 'autonomous_realized_pnl_trade_journal', 'revision': 113, 'status': _final_status(checks),
        'readiness': 'REALIZED_PNL_JOURNAL_PREVIEW', 'journal_record_preview': journal,
        'learning_feedback': {'decision': decision, 'net_pnl_usdt': round(net, 8), 'roi_pct': round(roi, 6)},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False},
        'next_allowed_step': 'real_learning_memory', 'contains_secret': False, 'secret_values_returned': False,
    }

_BUILDERS = {
    108: build_rev108_balance_reconciliation_manual_attention,
    109: build_rev109_live_position_tracker,
    110: build_rev110_live_stop_tp_trailing_guard,
    111: build_rev111_live_exit_submitter,
    112: build_rev112_emergency_close_submitter,
    113: build_rev113_realized_pnl_trade_journal,
}

_NAMES = {
    108: 'autonomous_balance_reconciliation_manual_attention',
    109: 'autonomous_live_position_tracker',
    110: 'autonomous_live_stop_tp_trailing_guard',
    111: 'autonomous_live_exit_submitter',
    112: 'autonomous_emergency_close_submitter',
    113: 'autonomous_realized_pnl_trade_journal',
}


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    working = deepcopy(data or {})
    outputs = {}
    for rev in range(108, 114):
        payload = _BUILDERS[rev](working, settings, auth_store, username)
        outputs[_NAMES[rev]] = payload
        working[_NAMES[rev]] = payload
    blockers = [name for name, payload in outputs.items() if payload.get('status') == 'blocked']
    return {
        'engine': 'autonomous_micro_real_live_ops_block', 'revision': 113, 'status': 'blocked' if blockers else 'review',
        'readiness': 'REV108_113_BLOCK_READY_PREVIEW' if not blockers else 'REV108_113_BLOCK_BLOCKED',
        'outputs': outputs, 'blockers': blockers, 'contains_secret': False, 'secret_values_returned': False,
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False},
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = _BUILDERS[revision](data, settings, auth_store, username)
    return {
        'revision': revision, 'status': payload.get('status'), 'readiness': payload.get('readiness'),
        'check_totals': payload.get('check_totals'), 'next_allowed_step': payload.get('next_allowed_step'),
        'command_preview': payload.get('command_preview'), 'contains_secret': False, 'secret_values_returned': False,
    }


def build_quality_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    sample = data or _sample_source()
    payload = _BUILDERS[revision](sample, settings or {}, auth_store or _sample_auth(username), username)
    checks = payload.get('checks') or []
    blockers = [c for c in checks if c.get('status') == 'blocked' and c.get('required')]
    return {
        'engine': f'{_NAMES[revision]}_quality', 'revision': revision, 'status': 'blocked' if blockers else 'ok',
        'checks': checks, 'check_totals': _totals(checks), 'blockers': blockers,
        'quality_gate': 'PASS' if not blockers and payload.get('contains_secret') is False else 'FAIL',
    }


def _sample_auth(username='ahmet') -> dict:
    return {'users': {username: {'role': 'owner', 'api_key_present': True, 'secret_present': True, 'read_permission': True, 'trade_permission': True}}}


def _sample_source() -> dict:
    return {
        'autonomous_order_status_poller_exchange_response_recorder': {
            'engine': 'autonomous_order_status_poller_exchange_response_recorder', 'revision': 107,
            'status': 'review', 'contains_secret': False,
            'poll_request_public': {'symbol': 'BTCUSDT', 'origClientOrderId': 'client107', 'contains_secret': False},
            'normalized_order_status': {'symbol': 'BTCUSDT', 'client_order_id': 'client107', 'status': 'FILLED', 'side': 'BUY', 'executed_qty': 0.0001, 'cumulative_quote_qty': 6.0, 'avg_price': 60000.0},
        }
    }
