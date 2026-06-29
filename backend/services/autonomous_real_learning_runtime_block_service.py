from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

from services.autonomous_micro_real_live_ops_block_service import build_rev113_realized_pnl_trade_journal


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


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == '':
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_text(value: Any, fallback: str = '') -> str:
    text = str(value or '').strip()
    return text or fallback


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    return settings.get(key) if isinstance(settings.get(key), dict) else {}


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
    if any(c.get('status') == 'blocked' and c.get('required') for c in checks):
        return 'blocked'
    if any(c.get('status') == 'review' for c in checks):
        return 'review'
    return 'ok'


def _hash(prefix: str, *parts: Any) -> str:
    return prefix + sha256(':'.join(_safe_text(p) for p in parts).encode('utf-8')).hexdigest()[:24]


def _auth_user(auth_store: dict | None, username: str) -> dict:
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    users = auth_store.get('users') if isinstance(auth_store.get('users'), dict) else {}
    return users.get(username) if isinstance(users.get(username), dict) else {}


def _rev113(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get('autonomous_realized_pnl_trade_journal') if isinstance(data.get('autonomous_realized_pnl_trade_journal'), dict) else None
    if raw and raw.get('revision') == 113:
        return raw
    return build_rev113_realized_pnl_trade_journal(data, settings, auth_store, username)


def _journal_record(rev113: dict) -> dict:
    return rev113.get('journal_record_preview') if isinstance(rev113.get('journal_record_preview'), dict) else {}


def _safe_runtime_records(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    candidates = []
    for key in ('safe_trade_journal_records', 'trade_journal_preview_records', 'real_learning_memory_seed'):
        raw = data.get(key)
        if isinstance(raw, list):
            candidates.extend([r for r in raw if isinstance(r, dict)])
    return candidates[:250]


def _pnl_from_record(record: dict) -> float:
    for key in ('net_pnl_usdt', 'realized_pnl_usdt', 'pnl_usdt'):
        if key in record:
            return _safe_float(record.get(key), 0.0)
    return 0.0


def _summary_from_records(records: list[dict]) -> dict:
    sample = len(records)
    wins = len([r for r in records if _pnl_from_record(r) > 0])
    losses = len([r for r in records if _pnl_from_record(r) < 0])
    pnl = sum(_pnl_from_record(r) for r in records)
    gross_win = sum(max(_pnl_from_record(r), 0.0) for r in records)
    gross_loss = abs(sum(min(_pnl_from_record(r), 0.0) for r in records))
    return {
        'sample_size': sample,
        'wins': wins,
        'losses': losses,
        'win_rate_pct': round((wins / sample * 100.0), 2) if sample else 0.0,
        'net_pnl_usdt': round(pnl, 8),
        'profit_factor': round(gross_win / gross_loss, 4) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        'avg_pnl_usdt': round(pnl / sample, 8) if sample else 0.0,
    }


def build_rev114_real_learning_memory(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    src = _rev113(data, settings, auth_store, username)
    record = _journal_record(src)
    records = _safe_runtime_records(data)
    if record:
        records.append(record)
    summary = _summary_from_records(records)
    policy = _settings(settings, 'autonomous_real_learning_memory')
    min_samples = _safe_int(policy.get('min_learning_samples'), 3)
    strategy = _safe_text(record.get('strategy') or record.get('strategy_name') or data.get('strategy'), 'unknown')
    symbol = _safe_text(record.get('symbol') or data.get('symbol'), 'UNKNOWN').upper()
    risk_impact = 'positive' if summary['net_pnl_usdt'] > 0 else ('negative' if summary['net_pnl_usdt'] < 0 else 'neutral')
    checks = [
        _check('rev113_journal_available', 'ok' if record else 'review', 'Rev114 learns from Rev113 realized PnL/trade journal preview.', False),
        _check('secret_free_learning_source', 'ok' if not src.get('contains_secret') and not record.get('contains_secret') else 'blocked', 'Learning memory may not contain API secrets.'),
        _check('sample_size_gate', 'ok' if summary['sample_size'] >= min_samples else 'review', 'More real samples improve confidence.', False),
        _check('runtime_write_disabled_by_default', 'ok' if not _safe_bool(policy.get('allow_runtime_write'), False) else 'review', 'Learning memory runtime write remains explicit and secret-free.', False),
    ]
    confidence = 'high' if summary['sample_size'] >= max(min_samples, 10) else ('medium' if summary['sample_size'] >= min_samples else 'low')
    return {
        'engine': 'autonomous_real_learning_memory', 'revision': 114, 'status': _final_status(checks),
        'readiness': 'REAL_LEARNING_MEMORY_READY' if summary['sample_size'] >= min_samples else 'REAL_LEARNING_MEMORY_COLLECTING_SAMPLES',
        'memory_id_preview': _hash('rlm114_', username, symbol, strategy, summary['sample_size'], summary['net_pnl_usdt']),
        'learning_scope': {'symbol': symbol, 'strategy': strategy, 'lane': 'micro_real_or_real_lane'},
        'learning_summary': summary,
        'confidence': confidence,
        'risk_impact': risk_impact,
        'recommendation': 'use_for_runtime_controller' if summary['sample_size'] >= min_samples else 'collect_more_secret_free_results',
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False},
        'next_allowed_step': 'promotion_demotion_runtime_controller', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev115_promotion_demotion_runtime_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    memory = data.get('autonomous_real_learning_memory') if isinstance(data.get('autonomous_real_learning_memory'), dict) else build_rev114_real_learning_memory(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_promotion_demotion_runtime_controller')
    s = memory.get('learning_summary') if isinstance(memory.get('learning_summary'), dict) else {}
    win_rate = _safe_float(s.get('win_rate_pct'), 0.0)
    pf = _safe_float(s.get('profit_factor'), 0.0)
    pnl = _safe_float(s.get('net_pnl_usdt'), 0.0)
    samples = _safe_int(s.get('sample_size'), 0)
    min_samples = _safe_int(policy.get('min_runtime_samples'), 5)
    stop_loss_floor = _safe_float(policy.get('stop_loss_floor_usdt'), -10.0)
    if pnl <= stop_loss_floor or (samples >= min_samples and win_rate < 35):
        decision = 'stop'
        reason = 'drawdown_or_low_win_rate'
    elif samples < min_samples:
        decision = 'hold'
        reason = 'insufficient_real_samples'
    elif pnl < 0 or pf < 1.0:
        decision = 'reduce'
        reason = 'negative_or_unprofitable_real_results'
    elif win_rate >= 60 and pf >= 1.25 and pnl > 0:
        decision = 'increase'
        reason = 'positive_real_results_with_guarded_confidence'
    else:
        decision = 'hold'
        reason = 'mixed_real_results'
    checks = [
        _check('learning_memory_available', 'ok' if memory.get('revision') == 114 else 'blocked', 'Rev115 consumes Rev114 learning memory.'),
        _check('decision_enum_valid', 'ok' if decision in {'increase','hold','reduce','stop'} else 'blocked', 'Runtime decision must be bounded.'),
        _check('no_auto_apply', 'ok' if not _safe_bool(policy.get('auto_apply'), False) else 'review', 'Controller does not auto-apply by default.', False),
        _check('secret_free_controller', 'ok' if not memory.get('contains_secret') else 'blocked', 'Controller input is secret-free.'),
    ]
    return {
        'engine': 'autonomous_promotion_demotion_runtime_controller', 'revision': 115, 'status': _final_status(checks),
        'readiness': 'RUNTIME_DECISION_READY_PREVIEW' if samples >= min_samples else 'RUNTIME_DECISION_SAMPLE_LIMITED',
        'decision': decision, 'decision_reason': reason,
        'decision_inputs': {'sample_size': samples, 'win_rate_pct': win_rate, 'profit_factor': pf, 'net_pnl_usdt': pnl},
        'runtime_policy': {'auto_apply': False, 'allowed_outputs': ['increase','hold','reduce','stop']},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'auto_applies': False},
        'next_allowed_step': 'size_scaling_cooldown_controller', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev116_size_scaling_cooldown_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    controller = data.get('autonomous_promotion_demotion_runtime_controller') if isinstance(data.get('autonomous_promotion_demotion_runtime_controller'), dict) else build_rev115_promotion_demotion_runtime_controller(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_size_scaling_cooldown_controller')
    base_notional = _safe_float(policy.get('base_notional_usdt'), _safe_float(data.get('current_micro_notional_usdt'), 6.0))
    max_notional = _safe_float(policy.get('max_notional_usdt'), 15.0)
    min_notional = _safe_float(policy.get('min_notional_usdt'), 5.0)
    loss_streak = _safe_int(data.get('loss_streak') or policy.get('loss_streak'), 0)
    emergency = _safe_bool(data.get('emergency_state') or policy.get('emergency_state'), False)
    daily_loss_hit = _safe_bool(data.get('daily_loss_hard_stop_hit') or policy.get('daily_loss_hard_stop_hit'), False)
    decision = _safe_text(controller.get('decision'), 'hold')
    factor = {'increase': 1.10, 'hold': 1.0, 'reduce': 0.50, 'stop': 0.0}.get(decision, 1.0)
    if loss_streak >= 2:
        factor = min(factor, 0.50)
    if emergency or daily_loss_hit:
        factor = 0.0
    target = round(min(max(base_notional * factor, 0.0 if factor == 0.0 else min_notional), max_notional), 8) if factor else 0.0
    cooldown = 0
    if decision == 'reduce' or loss_streak >= 2:
        cooldown = _safe_int(policy.get('reduce_cooldown_minutes'), 60)
    if decision == 'stop' or emergency or daily_loss_hit:
        cooldown = _safe_int(policy.get('stop_cooldown_minutes'), 240)
    checks = [
        _check('runtime_controller_available', 'ok' if controller.get('revision') == 115 else 'blocked', 'Rev116 consumes Rev115 controller.'),
        _check('max_notional_guard', 'ok' if target <= max_notional else 'blocked', 'Target notional must stay within max notional.'),
        _check('emergency_guard', 'blocked' if emergency else 'ok', 'Emergency state blocks size scaling.'),
        _check('daily_loss_guard', 'blocked' if daily_loss_hit else 'ok', 'Daily hard stop blocks size scaling.'),
        _check('no_aggressive_growth', 'ok' if factor <= 1.10 else 'blocked', 'Increase is capped to conservative growth.'),
    ]
    return {
        'engine': 'autonomous_size_scaling_cooldown_controller', 'revision': 116, 'status': _final_status(checks),
        'readiness': 'SIZE_SCALING_READY_PREVIEW' if _final_status(checks) != 'blocked' else 'SIZE_SCALING_BLOCKED',
        'source_decision': decision,
        'target_notional_usdt': target,
        'previous_notional_usdt': round(base_notional, 8),
        'max_notional_usdt': max_notional,
        'cooldown_minutes': cooldown,
        'scaling_action': 'stop' if target == 0 else ('increase' if target > base_notional else ('reduce' if target < base_notional else 'hold')),
        'guards': {'loss_streak': loss_streak, 'emergency_state': emergency, 'daily_loss_hard_stop_hit': daily_loss_hit},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'auto_applies': False},
        'next_allowed_step': 'semi_auto_real_session_runner', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev117_semi_auto_real_session_runner(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    size = data.get('autonomous_size_scaling_cooldown_controller') if isinstance(data.get('autonomous_size_scaling_cooldown_controller'), dict) else build_rev116_size_scaling_cooldown_controller(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_semi_auto_real_session_runner')
    user = _auth_user(auth_store, username)
    explicit_enable = _safe_bool(policy.get('real_session_enable'), False)
    owner_confirmed = _safe_bool(policy.get('owner_confirmed'), False)
    trade_permission = _safe_bool(user.get('trade_permission') or policy.get('trade_permission'), False)
    idempotency_ready = _safe_bool(data.get('idempotency_lock_ready') or policy.get('idempotency_lock_ready'), True)
    emergency_clear = not _safe_bool(data.get('emergency_state') or policy.get('emergency_state'), False)
    daily_hard_stop_clear = not _safe_bool(data.get('daily_loss_hard_stop_hit') or policy.get('daily_loss_hard_stop_hit'), False)
    session_ready = all([explicit_enable, owner_confirmed, trade_permission, idempotency_ready, emergency_clear, daily_hard_stop_clear, size.get('status') != 'blocked', _safe_float(size.get('target_notional_usdt'), 0.0) > 0])
    checks = [
        _check('size_controller_not_blocked', 'ok' if size.get('status') != 'blocked' else 'blocked', 'Size controller must not be blocked.'),
        _check('explicit_enable_flag', 'ok' if explicit_enable else 'blocked', 'Semi-auto real session requires explicit enable flag.'),
        _check('owner_confirmation', 'ok' if owner_confirmed else 'blocked', 'Owner confirmation is mandatory.'),
        _check('api_trade_permission', 'ok' if trade_permission else 'blocked', 'Trade permission is mandatory.'),
        _check('idempotency_guard', 'ok' if idempotency_ready else 'blocked', 'Idempotency lock must be ready.'),
        _check('emergency_guard_clear', 'ok' if emergency_clear else 'blocked', 'Emergency state blocks session.'),
        _check('daily_hard_stop_clear', 'ok' if daily_hard_stop_clear else 'blocked', 'Daily hard stop blocks session.'),
    ]
    return {
        'engine': 'autonomous_semi_auto_real_session_runner_v2', 'revision': 117, 'status': _final_status(checks),
        'readiness': 'SEMI_AUTO_REAL_SESSION_READY_GATED' if session_ready else 'SEMI_AUTO_REAL_SESSION_BLOCKED',
        'session_id_preview': _hash('sess117_', username, now_iso(), size.get('target_notional_usdt')),
        'session_ready': session_ready,
        'session_plan_preview': {'mode': 'semi_auto_real', 'target_notional_usdt': size.get('target_notional_usdt'), 'requires_final_approval': True},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'requires_submitter': True},
        'next_allowed_step': 'real_approval_policy_capital_allocator', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev118_real_approval_policy_capital_allocator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    session = data.get('autonomous_semi_auto_real_session_runner_v2') if isinstance(data.get('autonomous_semi_auto_real_session_runner_v2'), dict) else build_rev117_semi_auto_real_session_runner(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_real_approval_policy_capital_allocator')
    free_usdt = _safe_float(data.get('free_usdt') or data.get('usdt_balance') or policy.get('free_usdt'), 100.0)
    reserve_pct = _safe_float(policy.get('usdt_reserve_pct'), 80.0)
    max_capital_pct = _safe_float(policy.get('max_capital_use_pct'), 5.0)
    requested = _safe_float((session.get('session_plan_preview') or {}).get('target_notional_usdt'), 0.0)
    reserve_usdt = round(free_usdt * reserve_pct / 100.0, 8)
    max_allowed = round(min(free_usdt * max_capital_pct / 100.0, max(0.0, free_usdt - reserve_usdt)), 8)
    approved_notional = round(min(requested, max_allowed), 8) if session.get('session_ready') else 0.0
    approval = session.get('session_ready') and approved_notional > 0 and requested <= max_allowed
    checks = [
        _check('semi_auto_session_ready', 'ok' if session.get('session_ready') else 'blocked', 'Rev118 consumes ready Rev117 session.'),
        _check('usdt_reserve_protected', 'ok' if free_usdt - approved_notional >= reserve_usdt else 'blocked', 'USDT reserve must be protected.'),
        _check('capital_cap_guard', 'ok' if approved_notional <= max_allowed else 'blocked', 'Approved notional must stay within capital cap.'),
        _check('small_capital_bias', 'ok' if max_capital_pct <= 10 else 'review', 'Small-capital mode should avoid aggressive allocation.', False),
    ]
    return {
        'engine': 'autonomous_real_approval_policy_capital_allocator', 'revision': 118, 'status': _final_status(checks),
        'readiness': 'REAL_APPROVAL_CAPITAL_READY_PREVIEW' if approval else 'REAL_APPROVAL_CAPITAL_BLOCKED',
        'approval_decision': 'approve_preview' if approval else 'block',
        'capital_plan': {'free_usdt': free_usdt, 'reserve_usdt': reserve_usdt, 'requested_notional_usdt': requested, 'approved_notional_usdt': approved_notional, 'max_allowed_notional_usdt': max_allowed},
        'approval_policy': {'requires_owner_confirmation': True, 'requires_idempotency': True, 'requires_emergency_clear': True, 'requires_daily_hard_stop_clear': True},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'approval_only': True},
        'next_allowed_step': 'whitelist_daily_hard_stop', 'contains_secret': False, 'secret_values_returned': False,
    }


def build_rev119_whitelist_daily_hard_stop(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    approval = data.get('autonomous_real_approval_policy_capital_allocator') if isinstance(data.get('autonomous_real_approval_policy_capital_allocator'), dict) else build_rev118_real_approval_policy_capital_allocator(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_whitelist_daily_hard_stop')
    symbol = _safe_text(data.get('symbol') or (data.get('autonomous_real_learning_memory') or {}).get('learning_scope', {}).get('symbol'), 'BTCUSDT').upper()
    strategy = _safe_text(data.get('strategy') or (data.get('autonomous_real_learning_memory') or {}).get('learning_scope', {}).get('strategy'), 'unknown')
    symbol_whitelist = [str(x).upper() for x in policy.get('symbol_whitelist', ['BTCUSDT','ETHUSDT']) if str(x).strip()]
    strategy_whitelist = [str(x) for x in policy.get('strategy_whitelist', ['unknown','choch_imbalance','micro_scalp']) if str(x).strip()]
    daily_realized_pnl = _safe_float(data.get('daily_realized_pnl_usdt') or policy.get('daily_realized_pnl_usdt'), 0.0)
    daily_loss_limit = abs(_safe_float(policy.get('daily_loss_limit_usdt'), 10.0))
    hard_stop_hit = daily_realized_pnl <= -daily_loss_limit
    symbol_allowed = symbol in symbol_whitelist
    strategy_allowed = strategy in strategy_whitelist
    final_allowed = approval.get('approval_decision') == 'approve_preview' and symbol_allowed and strategy_allowed and not hard_stop_hit
    checks = [
        _check('capital_approval_ready', 'ok' if approval.get('approval_decision') == 'approve_preview' else 'blocked', 'Capital approval must be ready.'),
        _check('symbol_whitelisted', 'ok' if symbol_allowed else 'blocked', 'Symbol must be whitelisted.'),
        _check('strategy_whitelisted', 'ok' if strategy_allowed else 'blocked', 'Strategy must be whitelisted.'),
        _check('daily_hard_stop_clear', 'ok' if not hard_stop_hit else 'blocked', 'Daily hard stop blocks real-lane actions.'),
        _check('network_default_off', 'ok', 'This layer never sends network requests.'),
    ]
    return {
        'engine': 'autonomous_whitelist_daily_hard_stop', 'revision': 119, 'status': _final_status(checks),
        'readiness': 'REAL_LANE_GUARDED_ACTION_ALLOWED_PREVIEW' if final_allowed else 'REAL_LANE_ACTION_BLOCKED',
        'final_real_lane_action': 'allow_preview' if final_allowed else 'block',
        'whitelist': {'symbol': symbol, 'symbol_allowed': symbol_allowed, 'strategy': strategy, 'strategy_allowed': strategy_allowed},
        'daily_hard_stop': {'daily_realized_pnl_usdt': daily_realized_pnl, 'daily_loss_limit_usdt': daily_loss_limit, 'hard_stop_hit': hard_stop_hit},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False, 'central_guard': True},
        'next_allowed_step': 'autonomous_scheduler_runtime', 'contains_secret': False, 'secret_values_returned': False,
    }

_BUILDERS: dict[int, Callable[[dict | None, dict | None, dict | None, str], dict]] = {
    114: build_rev114_real_learning_memory,
    115: build_rev115_promotion_demotion_runtime_controller,
    116: build_rev116_size_scaling_cooldown_controller,
    117: build_rev117_semi_auto_real_session_runner,
    118: build_rev118_real_approval_policy_capital_allocator,
    119: build_rev119_whitelist_daily_hard_stop,
}

_KEYS = {
    114: 'autonomous_real_learning_memory',
    115: 'autonomous_promotion_demotion_runtime_controller',
    116: 'autonomous_size_scaling_cooldown_controller',
    117: 'autonomous_semi_auto_real_session_runner_v2',
    118: 'autonomous_real_approval_policy_capital_allocator',
    119: 'autonomous_whitelist_daily_hard_stop',
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builder = _BUILDERS.get(int(revision))
    if not builder:
        return {'engine': 'autonomous_real_learning_runtime_block', 'revision': revision, 'status': 'blocked', 'message': 'Unsupported Rev114-119 revision.', 'contains_secret': False}
    return builder(data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data_work, settings_work, auth_work = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs: dict[str, dict] = {}
    for rev in range(114, 120):
        payload = build_for_revision(rev, data_work, settings_work, auth_work, username)
        key = _KEYS[rev]
        outputs[key] = payload
        data_work[key] = payload
    blockers = [key for key, payload in outputs.items() if payload.get('status') == 'blocked']
    return {
        'engine': 'autonomous_real_learning_runtime_block', 'revision': 119,
        'status': 'blocked' if blockers else ('review' if any(p.get('status') == 'review' for p in outputs.values()) else 'ok'),
        'readiness': 'REV114_119_REAL_RUNTIME_BLOCK_READY' if not blockers else 'REV114_119_REAL_RUNTIME_BLOCK_BLOCKED',
        'outputs': outputs, 'blockers': blockers,
        'command_preview': {'places_order': False, 'sends_exchange_request': False, 'writes_runtime_state': False},
        'contains_secret': False, 'secret_values_returned': False,
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    return {
        'revision': payload.get('revision'), 'engine': payload.get('engine'), 'status': payload.get('status'),
        'readiness': payload.get('readiness'), 'decision': payload.get('decision') or payload.get('final_real_lane_action') or payload.get('approval_decision') or payload.get('scaling_action'),
        'check_totals': payload.get('check_totals'), 'command_preview': payload.get('command_preview'),
        'contains_secret': False, 'secret_values_returned': False,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    totals = payload.get('check_totals') if isinstance(payload.get('check_totals'), dict) else _totals(payload.get('checks') or [])
    return {
        'quality_gate': 'PASS' if payload.get('status') != 'blocked' else 'FAIL',
        'engine': payload.get('engine'), 'revision': payload.get('revision'), 'status': payload.get('status'),
        'readiness': payload.get('readiness'), 'check_totals': totals,
        'network_default_off': not payload.get('command_preview', {}).get('sends_exchange_request', False),
        'direct_order_default_off': not payload.get('command_preview', {}).get('places_order', False),
        'runtime_write_default_off': not payload.get('command_preview', {}).get('writes_runtime_state', False),
        'contains_secret': False, 'secret_values_returned': False,
    }
