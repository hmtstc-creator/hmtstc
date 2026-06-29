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
        return _reason('none', 'No repeat/stop/reduce blocker.', 'no_action', 'ok', 999)
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
        'repeat_decision_only': True,
        'owner_approval_required_for_repeat': True,
    }


def _settings(settings: dict | None) -> dict:
    root = _as_dict(settings)
    risk = _as_dict(root.get('risk'))
    limited = _as_dict(root.get('limited_live'))
    execution = _as_dict(root.get('execution'))
    exchange = _as_dict(root.get('exchange'))
    strategy = _as_dict(root.get('strategy'))
    return {
        'minimum_sample_count': _safe_int(risk.get('minimum_live_sample_count') or limited.get('minimum_live_sample_count') or 3, 3),
        'min_expectancy': _safe_float(risk.get('min_live_expectancy') or strategy.get('min_expectancy') or 0.05, 0.05),
        'max_drawdown': _safe_float(risk.get('max_live_drawdown') or limited.get('max_drawdown') or 2.0, 2.0),
        'max_slippage_bps': _safe_float(risk.get('max_slippage_bps') or limited.get('max_slippage_bps') or 12.0, 12.0),
        'max_latency_ms': _safe_float(risk.get('max_latency_ms') or limited.get('max_latency_ms') or 1500.0, 1500.0),
        'max_consecutive_losses': _safe_int(risk.get('max_consecutive_losses') or limited.get('max_consecutive_losses') or 2, 2),
        'real_submit_enable': _truthy(limited.get('real_submit_enable') or execution.get('real_submit_enable') or root.get('real_submit_enable')),
        'real_close_enable': _truthy(limited.get('real_close_enable') or execution.get('real_close_enable') or root.get('real_close_enable')),
        'network_enable': _truthy(exchange.get('network_enable') or execution.get('network_enable') or root.get('network_enable')),
    }


def _live_metrics(data: dict | None, settings: dict | None) -> dict:
    root = _as_dict(data)
    live = _as_dict(root.get('live_result') or root.get('micro_live_result') or root.get('last_live_result'))
    perf = _as_dict(root.get('live_performance') or root.get('performance'))
    reality = _as_dict(root.get('strategy_reality') or root.get('strategy_symbol_reality'))
    candidate = _as_dict(root.get('repeat_candidate') or root.get('candidate'))
    sample_count = _safe_int(root.get('live_sample_count') or live.get('sample_count') or perf.get('sample_count'), 0)
    wins = _safe_int(perf.get('wins') or root.get('wins'), 0)
    losses = _safe_int(perf.get('losses') or root.get('losses'), 0)
    pnl = _safe_float(live.get('pnl') or live.get('realized_pnl') or root.get('realized_pnl') or perf.get('last_pnl'), 0.0)
    expectancy = _safe_float(perf.get('expectancy') or reality.get('expectancy') or root.get('expectancy'), pnl if sample_count <= 1 else 0.0)
    profit_factor = _safe_float(perf.get('profit_factor') or reality.get('profit_factor'), 0.0)
    drawdown = abs(_safe_float(perf.get('drawdown') or root.get('drawdown'), 0.0))
    slippage = _safe_float(live.get('slippage_bps') or root.get('slippage_bps') or perf.get('avg_slippage_bps'), 0.0)
    latency = _safe_float(live.get('latency_ms') or root.get('latency_ms') or perf.get('avg_latency_ms'), 0.0)
    consecutive_losses = _safe_int(perf.get('consecutive_losses') or root.get('consecutive_losses'), 1 if pnl < 0 else 0)
    strategy_name = str(candidate.get('strategy') or live.get('strategy') or root.get('strategy') or 'micro_probe').strip()
    symbol = str(candidate.get('symbol') or live.get('symbol') or root.get('symbol') or _as_dict(_as_dict(settings).get('limited_live')).get('symbol') or 'BTCUSDT').upper()
    confidence = _safe_float(reality.get('confidence') or candidate.get('confidence') or root.get('evidence_confidence'), 0.0)
    reconciliation = str(root.get('reconciliation') or live.get('reconciliation') or 'unknown').upper()
    return {
        'sample_count': sample_count,
        'wins': wins,
        'losses': losses,
        'pnl': pnl,
        'expectancy': expectancy,
        'profit_factor': profit_factor,
        'drawdown': drawdown,
        'slippage_bps': slippage,
        'latency_ms': latency,
        'consecutive_losses': consecutive_losses,
        'strategy': strategy_name,
        'symbol': symbol,
        'confidence': confidence,
        'reconciliation': reconciliation,
        'result_present': bool(live or perf or sample_count),
    }


def _base_reasons(settings: dict | None) -> list[dict]:
    cfg = _settings(settings)
    reasons: list[dict] = []
    if cfg['real_submit_enable'] or cfg['real_close_enable'] or cfg['network_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Repeat/stop/reduce decision layer is read-only and expects network/submit/close OFF.', 'disable_real_execution_flags', 'critical', 1))
    return reasons


def build_rev291_repeat_eligibility_after_live_result(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    metrics = _live_metrics(data, settings)
    cfg = _settings(settings)
    reasons = _base_reasons(settings)
    if not metrics['result_present']:
        reasons.append(_reason('live_result_missing', 'Repeat eligibility requires live result evidence.', 'attach_live_result_before_repeat', 'major', 10))
    if metrics['sample_count'] < cfg['minimum_sample_count']:
        reasons.append(_reason('sample_size_too_low', 'Live sample size is too low to allow repeat without owner review.', 'freeze_repeat_until_more_evidence', 'major', 14))
    if metrics['reconciliation'] not in {'OK', 'CONSISTENT'}:
        reasons.append(_reason('reconciliation_not_ok', 'Repeat requires consistent position/order/journal reconciliation.', 'review_reconciliation_before_repeat', 'major', 12))
    eligible = not reasons or all(r.get('severity') in {'minor', 'ok'} for r in reasons)
    checks = [
        _check('live_result_present', 'ok' if metrics['result_present'] else 'blocked', 'Live result evidence must exist.'),
        _check('sample_count_ready', 'ok' if metrics['sample_count'] >= cfg['minimum_sample_count'] else 'review', 'Repeat needs minimum live sample count.'),
        _check('reconciliation_ok', 'ok' if metrics['reconciliation'] in {'OK', 'CONSISTENT'} else 'review', 'Reconciliation must be OK.'),
        _check('owner_approval_required', 'ok', 'Repeat remains approval-gated.'),
    ]
    body = {'repeat_eligible': bool(eligible), 'sample_count': metrics['sample_count'], 'minimum_sample_count': cfg['minimum_sample_count'], 'reconciliation': metrics['reconciliation'], 'symbol': metrics['symbol'], 'strategy': metrics['strategy'], 'owner_approval_required': True, 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'repeat_eligibility_after_live_result', 'revision': 291, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'repeat_eligibility_after_live_result': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev292_loss_based_stop_reduce_decision'}


def build_rev292_loss_based_stop_reduce_decision(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    metrics = _live_metrics(data, settings)
    cfg = _settings(settings)
    reasons = _base_reasons(settings)
    decision = 'hold'
    if metrics['consecutive_losses'] >= cfg['max_consecutive_losses'] or metrics['drawdown'] >= cfg['max_drawdown']:
        reasons.append(_reason('loss_escalation_limit_hit', 'Consecutive losses or drawdown reached the reduction/stop threshold.', 'stop_or_reduce_before_any_repeat', 'critical', 6))
        decision = 'stop'
    elif metrics['pnl'] < 0:
        reasons.append(_reason('negative_live_result', 'Last live result is negative; repeat should be reduced or cooled down.', 'reduce_and_cooldown', 'major', 18))
        decision = 'reduce'
    checks = [
        _check('drawdown_within_limit', 'ok' if metrics['drawdown'] < cfg['max_drawdown'] else 'blocked', 'Drawdown must remain below live threshold.'),
        _check('consecutive_losses_safe', 'ok' if metrics['consecutive_losses'] < cfg['max_consecutive_losses'] else 'blocked', 'Consecutive losses must stay below threshold.'),
        _check('revenge_trade_blocked', 'ok', 'Martingale/revenge repeat remains blocked.'),
    ]
    body = {'loss_decision': decision, 'pnl': metrics['pnl'], 'drawdown': metrics['drawdown'], 'max_drawdown': cfg['max_drawdown'], 'consecutive_losses': metrics['consecutive_losses'], 'max_consecutive_losses': cfg['max_consecutive_losses'], 'martingale_allowed': False, 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'loss_based_stop_reduce_decision', 'revision': 292, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'loss_based_stop_reduce_decision': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev293_profit_but_low_sample_freeze_rule'}


def build_rev293_profit_but_low_sample_freeze_rule(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    metrics = _live_metrics(data, settings)
    cfg = _settings(settings)
    reasons = _base_reasons(settings)
    freeze_required = metrics['sample_count'] < cfg['minimum_sample_count']
    if freeze_required and metrics['pnl'] >= 0:
        reasons.append(_reason('profit_low_sample_freeze', 'Profit exists but sample size is too low for scale or auto-repeat.', 'freeze_scale_collect_more_samples', 'major', 20))
    elif freeze_required:
        reasons.append(_reason('low_sample_freeze', 'Sample size is too low after live result.', 'freeze_repeat_until_more_evidence', 'major', 21))
    checks = [
        _check('scale_blocked_on_low_sample', 'ok' if freeze_required else 'ok', 'Scale remains blocked regardless of first profitable result.'),
        _check('sample_count_sufficient', 'ok' if not freeze_required else 'review', 'Minimum live sample count is required before repeat expansion.'),
        _check('auto_scale_off', 'ok', 'Auto-scale is OFF.'),
    ]
    body = {'freeze_required': bool(freeze_required), 'pnl': metrics['pnl'], 'sample_count': metrics['sample_count'], 'minimum_sample_count': cfg['minimum_sample_count'], 'scale_allowed': False, 'auto_repeat_allowed': False, 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'profit_but_low_sample_freeze_rule', 'revision': 293, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'profit_but_low_sample_freeze_rule': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev294_strategy_symbol_continuation_decision'}


def build_rev294_strategy_symbol_continuation_decision(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    metrics = _live_metrics(data, settings)
    cfg = _settings(settings)
    reasons = _base_reasons(settings)
    if metrics['expectancy'] < cfg['min_expectancy']:
        reasons.append(_reason('expectancy_below_threshold', 'Strategy-symbol live expectancy is below continuation threshold.', 'quarantine_or_review_strategy_symbol', 'major', 15))
    if metrics['slippage_bps'] > cfg['max_slippage_bps']:
        reasons.append(_reason('slippage_too_high', 'Observed slippage is too high for continuation.', 'review_symbol_liquidity_before_repeat', 'major', 17))
    if metrics['latency_ms'] > cfg['max_latency_ms']:
        reasons.append(_reason('latency_too_high', 'Observed latency is too high for continuation.', 'review_execution_latency_before_repeat', 'review', 25))
    if metrics['confidence'] and metrics['confidence'] < 0.55:
        reasons.append(_reason('confidence_low', 'Strategy-symbol confidence is low after live result.', 'hold_strategy_symbol_for_review', 'review', 30))
    continuation = 'continue_review'
    critical = _critical(reasons)
    if critical.get('severity') == 'critical':
        continuation = 'stop'
    elif critical.get('severity') == 'major':
        continuation = 'reduce_or_quarantine'
    elif critical.get('code') == 'none':
        continuation = 'eligible_for_owner_review_repeat'
    checks = [
        _check('expectancy_above_threshold', 'ok' if metrics['expectancy'] >= cfg['min_expectancy'] else 'review', 'Expectancy should support continuation.'),
        _check('slippage_within_limit', 'ok' if metrics['slippage_bps'] <= cfg['max_slippage_bps'] else 'review', 'Slippage should be within tolerance.'),
        _check('latency_within_limit', 'ok' if metrics['latency_ms'] <= cfg['max_latency_ms'] else 'review', 'Latency should be within tolerance.'),
    ]
    body = {'continuation_decision': continuation, 'symbol': metrics['symbol'], 'strategy': metrics['strategy'], 'expectancy': metrics['expectancy'], 'min_expectancy': cfg['min_expectancy'], 'profit_factor': metrics['profit_factor'], 'confidence': metrics['confidence'], 'slippage_bps': metrics['slippage_bps'], 'latency_ms': metrics['latency_ms'], 'critical_blocker': critical, 'operator_action': critical.get('action')}
    return {'engine': 'strategy_symbol_continuation_decision', 'revision': 294, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'strategy_symbol_continuation_decision': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev295_repeat_stop_reduce_decision_packet'}


def build_rev295_repeat_stop_reduce_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    r291 = build_rev291_repeat_eligibility_after_live_result(data, settings, auth_store, username)
    r292 = build_rev292_loss_based_stop_reduce_decision(data, settings, auth_store, username)
    r293 = build_rev293_profit_but_low_sample_freeze_rule(data, settings, auth_store, username)
    r294 = build_rev294_strategy_symbol_continuation_decision(data, settings, auth_store, username)
    checks: list[dict] = []
    reasons: list[dict] = []
    for payload, key in ((r291, 'repeat_eligibility_after_live_result'), (r292, 'loss_based_stop_reduce_decision'), (r293, 'profit_but_low_sample_freeze_rule'), (r294, 'strategy_symbol_continuation_decision')):
        checks.extend(_as_list(payload.get('checks')))
        blocker = _as_dict(_as_dict(payload.get(key)).get('critical_blocker'))
        if blocker.get('code') and blocker.get('code') != 'none':
            reasons.append(blocker)
    metrics = _live_metrics(data, settings)
    status = _status_from_checks(checks)
    critical = _critical(reasons)
    loss_decision = _as_dict(r292.get('loss_based_stop_reduce_decision')).get('loss_decision')
    freeze_required = bool(_as_dict(r293.get('profit_but_low_sample_freeze_rule')).get('freeze_required'))
    continuation = _as_dict(r294.get('strategy_symbol_continuation_decision')).get('continuation_decision')
    if critical.get('severity') == 'critical' or status == 'blocked' or loss_decision == 'stop':
        decision = 'STOP'
    elif loss_decision == 'reduce':
        decision = 'REDUCE'
    elif freeze_required:
        decision = 'FREEZE'
    elif continuation in {'reduce_or_quarantine', 'stop'}:
        decision = 'REVIEW'
    elif _as_dict(r291.get('repeat_eligibility_after_live_result')).get('repeat_eligible'):
        decision = 'REPEAT_REVIEW'
    else:
        decision = 'HOLD'
    packet = {'repeat_stop_reduce': decision, 'reason': critical, 'symbol': metrics['symbol'], 'strategy': metrics['strategy'], 'pnl': metrics['pnl'], 'sample_count': metrics['sample_count'], 'expectancy': metrics['expectancy'], 'next_allowed_action': 'owner_review_required' if decision in {'REPEAT_REVIEW', 'HOLD'} else critical.get('action'), 'repeat_allowed': decision == 'REPEAT_REVIEW', 'scale_allowed': False, 'auto_repeat_allowed': False, 'owner_approval_required': True, 'real_submit_close': 'OFF', 'network': 'OFF', 'auto_scale': 'OFF', 'auto_apply': 'OFF'}
    return {'engine': 'repeat_stop_reduce_decision_packet', 'revision': 295, 'status': status, 'generated_at': now_iso(), 'repeat_stop_reduce_decision_packet': packet, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'small_capital_controlled_autonomy_candidate_block'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {291: build_rev291_repeat_eligibility_after_live_result, 292: build_rev292_loss_based_stop_reduce_decision, 293: build_rev293_profit_but_low_sample_freeze_rule, 294: build_rev294_strategy_symbol_continuation_decision, 295: build_rev295_repeat_stop_reduce_decision_packet}
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev291-295 repeat/stop/reduce revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key_map = {291: 'repeat_eligibility_after_live_result', 292: 'loss_based_stop_reduce_decision', 293: 'profit_but_low_sample_freeze_rule', 294: 'strategy_symbol_continuation_decision', 295: 'repeat_stop_reduce_decision_packet'}
    body = _as_dict(payload.get(key_map[int(revision)]))
    reason = _as_dict(body.get('reason') or body.get('critical_blocker'))
    decision = body.get('repeat_stop_reduce') or body.get('continuation_decision') or body.get('loss_decision') or ('REVIEW' if payload.get('status') != 'ok' else 'OK')
    return {'revision': int(revision), 'repeat_stop_reduce': decision, 'critical_issue': reason.get('code', 'none'), 'operator_action': body.get('next_allowed_action') or body.get('operator_action') or reason.get('action') or 'review', 'symbol': body.get('symbol'), 'strategy': body.get('strategy'), 'pnl': body.get('pnl'), 'sample_count': body.get('sample_count'), 'expectancy': body.get('expectancy'), 'repeat_allowed': bool(body.get('repeat_allowed')), 'scale_allowed': False, 'auto_repeat_allowed': False, 'real_submit_close': 'OFF', 'network': 'OFF'}


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    r291 = build_rev291_repeat_eligibility_after_live_result(data, settings, auth_store, username)
    r292 = build_rev292_loss_based_stop_reduce_decision(data, settings, auth_store, username)
    r293 = build_rev293_profit_but_low_sample_freeze_rule(data, settings, auth_store, username)
    r294 = build_rev294_strategy_symbol_continuation_decision(data, settings, auth_store, username)
    r295 = build_rev295_repeat_stop_reduce_decision_packet(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (r291, r292, r293, r294, r295):
        checks.extend(_as_list(payload.get('checks')))
    return {'engine': 'repeat_stop_reduce_decision_block', 'revision': 295, 'status': r295.get('status', 'review'), 'generated_at': now_iso(), 'rev291_repeat_eligibility_after_live_result': r291, 'rev292_loss_based_stop_reduce_decision': r292, 'rev293_profit_but_low_sample_freeze_rule': r293, 'rev294_strategy_symbol_continuation_decision': r294, 'rev295_repeat_stop_reduce_decision_packet': r295, 'repeat_stop_reduce_decision_packet': r295.get('repeat_stop_reduce_decision_packet', {}), 'summary_result': build_summary_for_revision(295, data, settings, auth_store, username), 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'small_capital_controlled_autonomy_candidate_block'}


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
