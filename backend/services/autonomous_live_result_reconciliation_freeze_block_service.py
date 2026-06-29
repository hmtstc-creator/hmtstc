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
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'approved', 'ready', 'present', 'valid', 'ok', 'filled'}


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason('none', 'No live result reconciliation blocker.', 'no_action', 'ok', 999)
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
    return {'ok': sum(1 for c in checks if c.get('status') == 'ok'), 'review': sum(1 for c in checks if c.get('status') == 'review'), 'blocked': sum(1 for c in checks if c.get('status') == 'blocked'), 'total': len(checks)}


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
        'reconciliation_read_only': True,
        'freeze_decision_only': True,
    }


def _live_result(data: dict | None, settings: dict | None) -> dict:
    root = _as_dict(data)
    settings_root = _as_dict(settings)
    result = _as_dict(root.get('live_result') or root.get('micro_live_result') or root.get('last_live_result') or settings_root.get('live_result'))
    fills = _as_list(result.get('fills') or root.get('live_fills') or root.get('fills'))
    orders = _as_list(result.get('orders') or root.get('exchange_orders') or root.get('orders'))
    positions = _as_list(result.get('positions') or root.get('live_positions') or root.get('positions'))
    journal = _as_list(result.get('journal') or root.get('trade_journal') or root.get('journal'))
    fees = _safe_float(result.get('fee') or result.get('fees') or root.get('fee'), 0.0)
    slippage_bps = _safe_float(result.get('slippage_bps') or root.get('slippage_bps'), 0.0)
    latency_ms = _safe_float(result.get('latency_ms') or root.get('latency_ms'), 0.0)
    pnl = _safe_float(result.get('pnl') or result.get('realized_pnl') or root.get('realized_pnl'), 0.0)
    session_id = str(result.get('session_id') or root.get('session_id') or _as_dict(settings_root.get('session')).get('session_id') or '').strip()
    order_id = str(result.get('order_id') or root.get('order_id') or '').strip()
    position_id = str(result.get('position_id') or root.get('position_id') or '').strip()
    exit_reason = str(result.get('exit_reason') or root.get('exit_reason') or '').strip()
    return {
        'session_id': session_id,
        'order_id': order_id,
        'position_id': position_id,
        'symbol': str(result.get('symbol') or root.get('symbol') or _as_dict(settings_root.get('limited_live')).get('symbol') or 'BTCUSDT').upper(),
        'pnl': pnl,
        'fee': fees,
        'slippage_bps': slippage_bps,
        'latency_ms': latency_ms,
        'fill_count': len(fills),
        'order_count': len(orders),
        'position_count': len(positions),
        'journal_count': len(journal),
        'fills': fills,
        'orders': orders,
        'positions': positions,
        'journal': journal,
        'exit_reason': exit_reason,
        'result_present': bool(result or fills or orders or positions or journal),
        'result_status': str(result.get('status') or result.get('order_status') or root.get('result_status') or 'missing').lower(),
    }


def _limits(settings: dict | None) -> dict:
    root = _as_dict(settings)
    risk = _as_dict(root.get('risk'))
    session = _as_dict(root.get('session'))
    limited = _as_dict(root.get('limited_live'))
    execution = _as_dict(root.get('execution'))
    exchange = _as_dict(root.get('exchange'))
    return {
        'max_slippage_bps': _safe_float(risk.get('max_slippage_bps') or limited.get('max_slippage_bps') or 12, 12),
        'max_latency_ms': _safe_float(risk.get('max_latency_ms') or limited.get('max_latency_ms') or 1500, 1500),
        'max_fee_bps': _safe_float(risk.get('max_fee_bps') or limited.get('max_fee_bps') or 20, 20),
        'max_session_loss': _safe_float(session.get('max_loss') or limited.get('session_max_loss') or limited.get('max_daily_loss') or root.get('max_daily_loss') or 0, 0),
        'real_submit_enable': _truthy(limited.get('real_submit_enable') or execution.get('real_submit_enable') or root.get('real_submit_enable')),
        'real_close_enable': _truthy(limited.get('real_close_enable') or execution.get('real_close_enable') or root.get('real_close_enable')),
        'network_enable': _truthy(exchange.get('network_enable') or execution.get('network_enable') or root.get('network_enable')),
        'minimum_sample_count': _safe_int(risk.get('minimum_live_sample_count') or limited.get('minimum_live_sample_count') or 3, 3),
        'live_sample_count': _safe_int(root.get('live_sample_count') or limited.get('live_sample_count') or 0, 0),
    }


def _base_safety_reasons(settings: dict | None) -> list[dict]:
    limits = _limits(settings)
    reasons: list[dict] = []
    if limits['real_submit_enable'] or limits['real_close_enable'] or limits['network_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Live result reconciliation must remain read-only; real network/submit/close flags are expected OFF.', 'disable_real_execution_flags', 'critical', 1))
    return reasons


def build_rev286_live_fill_result_collector(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    live = _live_result(data, settings)
    reasons = _base_safety_reasons(settings)
    if not live['result_present']:
        reasons.append(_reason('live_result_missing', 'No live fill/result evidence is available for reconciliation.', 'wait_for_or_attach_live_result_evidence', 'major', 10))
    if not live['session_id']:
        reasons.append(_reason('session_id_missing', 'Live result evidence must be linked to a session ID.', 'attach_session_id_to_result', 'major', 12))
    checks = [
        _check('result_present', 'ok' if live['result_present'] else 'blocked', 'Live result evidence must exist.'),
        _check('session_id_present', 'ok' if live['session_id'] else 'blocked', 'Result must reference the approved session.'),
        _check('fill_or_order_present', 'ok' if live['fill_count'] or live['order_count'] else 'review', 'At least fill or order evidence should be available.'),
    ]
    body = {k: live[k] for k in ('session_id', 'order_id', 'position_id', 'symbol', 'pnl', 'fill_count', 'order_count', 'position_count', 'journal_count', 'result_status')}
    body.update({'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action'), 'secret_free': True})
    return {'engine': 'live_fill_result_collector', 'revision': 286, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'live_fill_result_collector': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev287_fee_slippage_latency_reality_recorder'}


def build_rev287_fee_slippage_latency_reality_recorder(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    live = _live_result(data, settings)
    limits = _limits(settings)
    reasons = _base_safety_reasons(settings)
    if live['slippage_bps'] > limits['max_slippage_bps']:
        reasons.append(_reason('slippage_above_limit', 'Observed slippage is above configured live tolerance.', 'freeze_and_review_cost_model', 'major', 15))
    if live['latency_ms'] > limits['max_latency_ms']:
        reasons.append(_reason('latency_above_limit', 'Observed latency is above configured live tolerance.', 'freeze_and_review_execution_path', 'review', 20))
    fee_bps_estimate = abs(live['fee']) * 10000 if 0 < abs(live['fee']) < 1 else abs(live['fee'])
    if fee_bps_estimate > limits['max_fee_bps']:
        reasons.append(_reason('fee_above_limit', 'Observed fee/cost is above configured live tolerance.', 'freeze_and_review_fee_model', 'major', 18))
    checks = [
        _check('fee_recorded', 'ok' if live['fee'] >= 0 else 'review', 'Fee must be recorded as non-negative cost.'),
        _check('slippage_within_limit', 'ok' if live['slippage_bps'] <= limits['max_slippage_bps'] else 'blocked', 'Slippage must stay within tolerance.'),
        _check('latency_within_limit', 'ok' if live['latency_ms'] <= limits['max_latency_ms'] else 'review', 'Latency should stay within tolerance.'),
    ]
    body = {'fee': live['fee'], 'slippage_bps': live['slippage_bps'], 'latency_ms': live['latency_ms'], 'max_slippage_bps': limits['max_slippage_bps'], 'max_latency_ms': limits['max_latency_ms'], 'max_fee_bps': limits['max_fee_bps'], 'cost_reality': 'ATTENTION' if reasons else 'OK', 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'fee_slippage_latency_reality_recorder', 'revision': 287, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'fee_slippage_latency_reality_recorder': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev288_position_order_journal_final_reconciler'}


def build_rev288_position_order_journal_final_reconciler(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    live = _live_result(data, settings)
    reasons = _base_safety_reasons(settings)
    if live['order_count'] and not live['journal_count']:
        reasons.append(_reason('order_without_journal', 'Exchange order evidence exists but trade journal entry is missing.', 'freeze_and_rebuild_journal_evidence', 'critical', 5))
    if live['position_count'] and not live['order_count']:
        reasons.append(_reason('position_without_order', 'Position evidence exists but order evidence is missing.', 'manual_reconciliation_required', 'critical', 6))
    if live['result_status'] in {'unknown', 'rejected', 'expired', 'canceled'} and live['position_count']:
        reasons.append(_reason('inconsistent_terminal_state', 'Terminal order status conflicts with position evidence.', 'halt_and_reconcile_position_order_journal', 'critical', 7))
    consistent = not reasons and live['result_present']
    checks = [
        _check('order_journal_consistency', 'ok' if not (live['order_count'] and not live['journal_count']) else 'blocked', 'Orders must have journal evidence.'),
        _check('position_order_consistency', 'ok' if not (live['position_count'] and not live['order_count']) else 'blocked', 'Positions must have order evidence.'),
        _check('terminal_state_consistency', 'ok' if not (live['result_status'] in {'unknown', 'rejected', 'expired', 'canceled'} and live['position_count']) else 'blocked', 'Terminal status must not conflict with position.'),
    ]
    body = {'reconciliation': 'CONSISTENT' if consistent else ('INCONSISTENT' if reasons else 'ATTENTION'), 'order_count': live['order_count'], 'position_count': live['position_count'], 'journal_count': live['journal_count'], 'result_status': live['result_status'], 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'position_order_journal_final_reconciler', 'revision': 288, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'position_order_journal_final_reconciler': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev289_post_session_freeze_cooldown_gate'}


def build_rev289_post_session_freeze_cooldown_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    live = _live_result(data, settings)
    limits = _limits(settings)
    reasons = _base_safety_reasons(settings)
    if limits['max_session_loss'] > 0 and live['pnl'] <= -abs(limits['max_session_loss']):
        reasons.append(_reason('session_loss_limit_hit', 'Session loss limit is hit or exceeded.', 'freeze_and_cooldown_before_repeat', 'critical', 4))
    if live['pnl'] < 0:
        reasons.append(_reason('negative_live_result', 'First live result is negative; repeat must cool down.', 'cooldown_and_reduce_before_repeat', 'major', 16))
    if limits['live_sample_count'] < limits['minimum_sample_count']:
        reasons.append(_reason('sample_size_too_low', 'Live sample size is too low for any scale decision.', 'freeze_scale_and_collect_more_evidence', 'major', 25))
    decision = 'freeze'
    if any(r.get('severity') == 'critical' for r in reasons):
        decision = 'halt_freeze'
    elif live['pnl'] < 0:
        decision = 'cooldown_reduce'
    elif live['result_present'] and limits['live_sample_count'] >= limits['minimum_sample_count'] and not reasons:
        decision = 'review_repeat'
    checks = [
        _check('session_loss_safe', 'ok' if not (limits['max_session_loss'] > 0 and live['pnl'] <= -abs(limits['max_session_loss'])) else 'blocked', 'Session loss must remain below limit.'),
        _check('sample_size_sufficient_for_scale', 'ok' if limits['live_sample_count'] >= limits['minimum_sample_count'] else 'review', 'Scaling requires enough live samples.'),
        _check('auto_scale_blocked', 'ok', 'Auto-scale remains OFF after session.'),
    ]
    body = {'post_session_decision': decision, 'pnl': live['pnl'], 'live_sample_count': limits['live_sample_count'], 'minimum_sample_count': limits['minimum_sample_count'], 'scale_allowed': False, 'repeat_requires_review': True, 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'post_session_freeze_cooldown_gate', 'revision': 289, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'post_session_freeze_cooldown_gate': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev290_live_result_reconciliation_report'}


def build_rev290_live_result_reconciliation_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev286 = build_rev286_live_fill_result_collector(data, settings, auth_store, username)
    rev287 = build_rev287_fee_slippage_latency_reality_recorder(data, settings, auth_store, username)
    rev288 = build_rev288_position_order_journal_final_reconciler(data, settings, auth_store, username)
    rev289 = build_rev289_post_session_freeze_cooldown_gate(data, settings, auth_store, username)
    checks: list[dict] = []
    reasons: list[dict] = []
    for payload, key in ((rev286, 'live_fill_result_collector'), (rev287, 'fee_slippage_latency_reality_recorder'), (rev288, 'position_order_journal_final_reconciler'), (rev289, 'post_session_freeze_cooldown_gate')):
        checks.extend(_as_list(payload.get('checks')))
        blocker = _as_dict(_as_dict(payload.get(key)).get('critical_blocker'))
        if blocker.get('code') and blocker.get('code') != 'none':
            reasons.append(blocker)
    status = _status_from_checks(checks)
    critical = _critical(reasons)
    live = _live_result(data, settings)
    reconciler = _as_dict(rev288.get('position_order_journal_final_reconciler'))
    freeze_gate = _as_dict(rev289.get('post_session_freeze_cooldown_gate'))
    if status == 'ok':
        decision = 'REVIEW_REPEAT'
    elif critical.get('severity') == 'critical' or status == 'blocked':
        decision = 'FREEZE'
    else:
        decision = 'COOLDOWN_REVIEW'
    report = {
        'live_result_reconciliation': decision,
        'reconciliation': reconciler.get('reconciliation', 'ATTENTION'),
        'post_session_decision': freeze_gate.get('post_session_decision', 'freeze'),
        'pnl': live['pnl'],
        'fee': live['fee'],
        'slippage_bps': live['slippage_bps'],
        'latency_ms': live['latency_ms'],
        'session_id': live['session_id'] or None,
        'symbol': live['symbol'],
        'scale_allowed': False,
        'auto_repeat_allowed': False,
        'operator_action': critical.get('action') if critical.get('code') != 'none' else 'review_before_any_repeat',
        'critical_blocker': critical,
        'real_submit_close': 'OFF',
        'network': 'OFF',
        'auto_scale': 'OFF',
        'auto_apply': 'OFF',
    }
    return {'engine': 'live_result_reconciliation_report', 'revision': 290, 'status': status, 'generated_at': now_iso(), 'live_result_reconciliation_report': report, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev291_repeat_stop_reduce_decision_block'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {286: build_rev286_live_fill_result_collector, 287: build_rev287_fee_slippage_latency_reality_recorder, 288: build_rev288_position_order_journal_final_reconciler, 289: build_rev289_post_session_freeze_cooldown_gate, 290: build_rev290_live_result_reconciliation_report}
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev286-290 live result reconciliation freeze revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key_map = {286: 'live_fill_result_collector', 287: 'fee_slippage_latency_reality_recorder', 288: 'position_order_journal_final_reconciler', 289: 'post_session_freeze_cooldown_gate', 290: 'live_result_reconciliation_report'}
    body = _as_dict(payload.get(key_map[int(revision)]))
    blocker = _as_dict(body.get('critical_blocker'))
    decision = body.get('live_result_reconciliation') or body.get('post_session_decision') or body.get('reconciliation') or body.get('cost_reality') or ('REVIEW' if payload.get('status') != 'ok' else 'OK')
    return {'revision': int(revision), 'live_result_reconciliation': decision, 'reconciliation': body.get('reconciliation'), 'post_session_decision': body.get('post_session_decision'), 'critical_issue': blocker.get('code', 'none'), 'operator_action': body.get('operator_action') or blocker.get('action') or 'review', 'pnl': body.get('pnl'), 'fee': body.get('fee'), 'slippage_bps': body.get('slippage_bps'), 'latency_ms': body.get('latency_ms'), 'scale_allowed': False, 'auto_repeat_allowed': False, 'real_submit_close': 'OFF', 'network': 'OFF'}


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    rev286 = build_rev286_live_fill_result_collector(data, settings, auth_store, username)
    rev287 = build_rev287_fee_slippage_latency_reality_recorder(data, settings, auth_store, username)
    rev288 = build_rev288_position_order_journal_final_reconciler(data, settings, auth_store, username)
    rev289 = build_rev289_post_session_freeze_cooldown_gate(data, settings, auth_store, username)
    rev290 = build_rev290_live_result_reconciliation_report(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev286, rev287, rev288, rev289, rev290):
        checks.extend(_as_list(payload.get('checks')))
    return {'engine': 'live_result_reconciliation_freeze_block', 'revision': 290, 'status': rev290.get('status', 'review'), 'generated_at': now_iso(), 'rev286_live_fill_result_collector': rev286, 'rev287_fee_slippage_latency_reality_recorder': rev287, 'rev288_position_order_journal_final_reconciler': rev288, 'rev289_post_session_freeze_cooldown_gate': rev289, 'rev290_live_result_reconciliation_report': rev290, 'live_result_reconciliation_report': rev290.get('live_result_reconciliation_report', {}), 'summary_result': build_summary_for_revision(290, data, settings, auth_store, username), 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'repeat_stop_reduce_decision_block'}


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
