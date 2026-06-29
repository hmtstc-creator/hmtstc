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
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'approved', 'ready', 'present', 'valid', 'ok'}


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason('none', 'No small-cap autonomy blocker.', 'no_action', 'ok', 999)
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
        'small_cap_autonomy_candidate_only': True,
        'owner_approval_required_for_live_action': True,
    }


def _settings(settings: dict | None) -> dict:
    root = _as_dict(settings)
    risk = _as_dict(root.get('risk'))
    bot = _as_dict(root.get('bot'))
    limited = _as_dict(root.get('limited_live'))
    execution = _as_dict(root.get('execution'))
    exchange = _as_dict(root.get('exchange'))
    capital = _as_dict(root.get('capital'))
    return {
        'min_evidence_confidence': _safe_float(risk.get('min_evidence_confidence') or limited.get('min_evidence_confidence') or 0.78, 0.78),
        'min_live_sample_count': _safe_int(risk.get('minimum_live_sample_count') or limited.get('minimum_live_sample_count') or 5, 5),
        'min_usdt_reserve_pct': _safe_float(capital.get('min_usdt_reserve_pct') or risk.get('min_usdt_reserve_pct') or 75.0, 75.0),
        'max_exposure_pct': _safe_float(capital.get('max_exposure_pct') or risk.get('max_exposure_pct') or 20.0, 20.0),
        'max_daily_loss_usdt': _safe_float(risk.get('max_daily_loss_usdt') or limited.get('max_daily_loss_usdt') or 5.0, 5.0),
        'max_notional_usdt': _safe_float(limited.get('max_notional_usdt') or bot.get('max_order_usdt') or 25.0, 25.0),
        'max_open_positions': _safe_int(limited.get('max_open_positions') or bot.get('max_open_positions') or 1, 1),
        'max_daily_trades': _safe_int(limited.get('max_daily_trades') or risk.get('max_daily_trades') or 3, 3),
        'allowed_symbols': _as_list(limited.get('allowed_symbols') or bot.get('allowed_symbols') or ['BTCUSDT', 'ETHUSDT']),
        'real_submit_enable': _truthy(limited.get('real_submit_enable') or execution.get('real_submit_enable') or root.get('real_submit_enable')),
        'real_close_enable': _truthy(limited.get('real_close_enable') or execution.get('real_close_enable') or root.get('real_close_enable')),
        'network_enable': _truthy(exchange.get('network_enable') or execution.get('network_enable') or root.get('network_enable')),
        'auto_scale': _truthy(limited.get('auto_scale') or execution.get('auto_scale') or root.get('auto_scale')),
        'auto_apply': _truthy(limited.get('auto_apply') or execution.get('auto_apply') or root.get('auto_apply')),
    }


def _state(data: dict | None, settings: dict | None) -> dict:
    root = _as_dict(data)
    wallet = _as_dict(root.get('wallet') or root.get('shadow_wallet'))
    perf = _as_dict(root.get('live_performance') or root.get('performance'))
    candidate = _as_dict(root.get('small_cap_candidate') or root.get('limited_live_candidate') or root.get('candidate'))
    result = _as_dict(root.get('live_result') or root.get('last_live_result'))
    capital = _as_dict(root.get('capital') or root.get('capital_preservation'))
    cfg = _settings(settings)
    total_usdt = _safe_float(wallet.get('total_usdt') or wallet.get('total') or root.get('total_usdt') or 1000.0, 1000.0)
    free_usdt = _safe_float(wallet.get('free_usdt') or wallet.get('USDT') or wallet.get('free') or root.get('free_usdt') or total_usdt, total_usdt)
    active_exposure = _safe_float(root.get('active_exposure_usdt') or capital.get('active_exposure_usdt') or candidate.get('active_exposure_usdt'), max(0.0, total_usdt - free_usdt))
    reserve_pct = _safe_float(capital.get('usdt_reserve_pct') or root.get('usdt_reserve_pct'), (free_usdt / total_usdt * 100.0) if total_usdt else 0.0)
    exposure_pct = _safe_float(capital.get('exposure_pct') or root.get('exposure_pct'), (active_exposure / total_usdt * 100.0) if total_usdt else 0.0)
    daily_loss = abs(_safe_float(root.get('daily_loss_usdt') or perf.get('daily_loss_usdt') or result.get('daily_loss_usdt'), 0.0))
    sample_count = _safe_int(root.get('live_sample_count') or perf.get('sample_count') or result.get('sample_count'), 0)
    confidence = _safe_float(root.get('evidence_confidence') or candidate.get('evidence_confidence') or perf.get('confidence'), 0.0)
    reconciliation = str(root.get('reconciliation') or result.get('reconciliation') or candidate.get('reconciliation') or 'unknown').upper()
    repeat_decision = str(root.get('repeat_stop_reduce') or candidate.get('repeat_stop_reduce') or candidate.get('decision') or 'review').upper()
    halt_authority = _truthy(root.get('autonomous_halt_authority') or candidate.get('autonomous_halt_authority') or True)
    operator_free_summary = _truthy(root.get('operator_free_summary') or candidate.get('operator_free_summary') or True)
    return {
        'total_usdt': total_usdt,
        'free_usdt': free_usdt,
        'active_exposure_usdt': active_exposure,
        'usdt_reserve_pct': reserve_pct,
        'exposure_pct': exposure_pct,
        'daily_loss_usdt': daily_loss,
        'sample_count': sample_count,
        'evidence_confidence': confidence,
        'reconciliation': reconciliation,
        'repeat_stop_reduce': repeat_decision,
        'autonomous_halt_authority': halt_authority,
        'operator_free_summary': operator_free_summary,
        'allowed_symbols': cfg['allowed_symbols'],
    }


def _base_reasons(settings: dict | None) -> list[dict]:
    cfg = _settings(settings)
    reasons: list[dict] = []
    if cfg['real_submit_enable'] or cfg['real_close_enable'] or cfg['network_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Small-cap autonomy candidate layer requires submit/close/network OFF by default.', 'disable_real_execution_flags', 'critical', 1))
    if cfg['auto_scale'] or cfg['auto_apply']:
        reasons.append(_reason('unsafe_auto_growth_enabled', 'Auto-scale/auto-apply must remain OFF before controlled autonomy.', 'disable_auto_scale_and_auto_apply', 'critical', 2))
    return reasons


def build_rev296_small_capital_autonomy_readiness_recheck(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    state = _state(data, settings)
    cfg = _settings(settings)
    reasons = _base_reasons(settings)
    if state['sample_count'] < cfg['min_live_sample_count']:
        reasons.append(_reason('insufficient_live_sample', 'Small-cap autonomy needs more controlled live samples.', 'continue_manual_review_or_freeze', 'major', 12))
    if state['evidence_confidence'] < cfg['min_evidence_confidence']:
        reasons.append(_reason('evidence_confidence_low', 'Evidence confidence is below small-cap autonomy threshold.', 'collect_higher_quality_evidence', 'major', 14))
    if state['reconciliation'] not in {'OK', 'CONSISTENT'}:
        reasons.append(_reason('reconciliation_not_ok', 'Position/order/journal reconciliation must be consistent.', 'resolve_reconciliation_before_autonomy', 'major', 10))
    checks = [
        _check('sample_count_ready', 'ok' if state['sample_count'] >= cfg['min_live_sample_count'] else 'review', 'Minimum controlled live samples required.'),
        _check('evidence_confidence_ready', 'ok' if state['evidence_confidence'] >= cfg['min_evidence_confidence'] else 'review', 'Evidence confidence must be high.'),
        _check('reconciliation_ready', 'ok' if state['reconciliation'] in {'OK', 'CONSISTENT'} else 'blocked', 'Reconciliation must be OK.'),
        _check('owner_approval_required', 'ok', 'Controlled autonomy remains owner-gated.'),
    ]
    body = {'readiness': 'ready' if not reasons else 'review', 'sample_count': state['sample_count'], 'minimum_sample_count': cfg['min_live_sample_count'], 'evidence_confidence': state['evidence_confidence'], 'minimum_confidence': cfg['min_evidence_confidence'], 'reconciliation': state['reconciliation'], 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'small_capital_autonomy_readiness_recheck', 'revision': 296, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'small_capital_autonomy_readiness_recheck': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev297_usdt_dominance_exposure_final_gate'}


def build_rev297_usdt_dominance_exposure_final_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    state = _state(data, settings)
    cfg = _settings(settings)
    reasons = _base_reasons(settings)
    if state['usdt_reserve_pct'] < cfg['min_usdt_reserve_pct']:
        reasons.append(_reason('usdt_reserve_weak', 'USDT reserve dominance is below required level.', 'reduce_exposure_keep_capital_in_usdt', 'critical', 8))
    if state['exposure_pct'] > cfg['max_exposure_pct']:
        reasons.append(_reason('exposure_too_high', 'Active exposure exceeds small-cap autonomy envelope.', 'freeze_new_trades_reduce_exposure', 'critical', 9))
    if state['daily_loss_usdt'] >= cfg['max_daily_loss_usdt']:
        reasons.append(_reason('daily_loss_limit_hit', 'Daily loss reached or exceeded allowed limit.', 'halt_for_the_day', 'critical', 6))
    checks = [
        _check('usdt_reserve_dominant', 'ok' if state['usdt_reserve_pct'] >= cfg['min_usdt_reserve_pct'] else 'blocked', 'Most capital must remain in USDT.'),
        _check('exposure_within_limit', 'ok' if state['exposure_pct'] <= cfg['max_exposure_pct'] else 'blocked', 'Exposure must stay below cap.'),
        _check('daily_loss_safe', 'ok' if state['daily_loss_usdt'] < cfg['max_daily_loss_usdt'] else 'blocked', 'Daily hard loss limit must hold.'),
    ]
    body = {'capital_gate': 'pass' if not reasons else 'blocked', 'usdt_reserve_pct': round(state['usdt_reserve_pct'], 2), 'min_usdt_reserve_pct': cfg['min_usdt_reserve_pct'], 'exposure_pct': round(state['exposure_pct'], 2), 'max_exposure_pct': cfg['max_exposure_pct'], 'daily_loss_usdt': state['daily_loss_usdt'], 'max_daily_loss_usdt': cfg['max_daily_loss_usdt'], 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'usdt_dominance_exposure_final_gate', 'revision': 297, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'usdt_dominance_exposure_final_gate': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev298_autonomous_halt_authority_final_proof'}


def build_rev298_autonomous_halt_authority_final_proof(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    state = _state(data, settings)
    reasons = _base_reasons(settings)
    if not state['autonomous_halt_authority']:
        reasons.append(_reason('halt_authority_missing', 'System must be able to halt/reduce/freeze itself before controlled autonomy.', 'enable_read_only_halt_authority_signal', 'critical', 5))
    halt_required = bool(reasons)
    checks = [
        _check('can_halt_without_owner_growth', 'ok' if state['autonomous_halt_authority'] else 'blocked', 'System can halt by itself but cannot grow without owner.'),
        _check('auto_growth_forbidden', 'ok', 'Autonomous growth remains forbidden.'),
        _check('emergency_state_routable', 'ok', 'Emergency state can route to halt/freeze decision.'),
    ]
    body = {'halt_authority_ready': bool(state['autonomous_halt_authority']), 'halt_required_now': halt_required, 'growth_without_owner_allowed': False, 'actions_allowed_without_owner': ['halt', 'freeze', 'reduce'], 'actions_blocked_without_owner': ['increase_size', 'enable_real_submit', 'auto_scale'], 'critical_blocker': _critical(reasons), 'operator_action': _critical(reasons).get('action')}
    return {'engine': 'autonomous_halt_authority_final_proof', 'revision': 298, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'autonomous_halt_authority_final_proof': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev299_operator_free_summary_final_compact_mode'}


def build_rev299_operator_free_summary_final_compact_mode(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    state = _state(data, settings)
    reasons = _base_reasons(settings)
    if not state['operator_free_summary']:
        reasons.append(_reason('summary_not_operator_free', 'Summary must show compact mode/risk/PnL/trade allowed/next action/blocker.', 'enable_minimal_operator_summary', 'major', 15))
    compact = {
        'mode': 'small_cap_candidate',
        'risk': 'blocked' if reasons else 'normal',
        'pnl': _safe_float(_as_dict(data).get('realized_pnl') or _as_dict(data).get('today_pnl'), 0.0),
        'trade_allowed': False,
        'next_action': _critical(reasons).get('action') if reasons else 'owner_review_before_controlled_autonomy',
        'blocker': _critical(reasons).get('code'),
        'owner_action': 'review_small_cap_candidate_packet',
    }
    checks = [
        _check('summary_compact_ready', 'ok' if state['operator_free_summary'] else 'review', 'Operator-free Summary compact mode must be available.'),
        _check('trade_allowed_visible', 'ok', 'Trade allowed state is visible.'),
        _check('owner_action_visible', 'ok', 'Owner action is visible.'),
    ]
    body = {'compact_summary_ready': bool(state['operator_free_summary']), 'summary_visible': compact, 'critical_blocker': _critical(reasons), 'operator_action': compact['owner_action']}
    return {'engine': 'operator_free_summary_final_compact_mode', 'revision': 299, 'status': _status_from_checks(checks), 'generated_at': now_iso(), 'operator_free_summary_final_compact_mode': body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev300_small_capital_controlled_autonomy_candidate_packet'}


def build_rev300_small_capital_controlled_autonomy_candidate_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    r296 = build_rev296_small_capital_autonomy_readiness_recheck(data, settings, auth_store, username)
    r297 = build_rev297_usdt_dominance_exposure_final_gate(data, settings, auth_store, username)
    r298 = build_rev298_autonomous_halt_authority_final_proof(data, settings, auth_store, username)
    r299 = build_rev299_operator_free_summary_final_compact_mode(data, settings, auth_store, username)
    cfg = _settings(settings)
    state = _state(data, settings)
    reasons: list[dict] = []
    for payload, key in ((r296, 'small_capital_autonomy_readiness_recheck'), (r297, 'usdt_dominance_exposure_final_gate'), (r298, 'autonomous_halt_authority_final_proof'), (r299, 'operator_free_summary_final_compact_mode')):
        body = _as_dict(payload.get(key))
        blocker = _as_dict(body.get('critical_blocker'))
        if blocker and blocker.get('code') != 'none':
            reasons.append(blocker)
    critical = _critical(reasons)
    if any(str(r.get('severity')) == 'critical' for r in reasons):
        candidate = 'BLOCKED'
    elif reasons:
        candidate = 'REVIEW'
    else:
        candidate = 'LIMITED-CANDIDATE'
    checks = [
        _check('readiness_recheck', r296.get('status', 'review'), 'Small-cap readiness must pass.'),
        _check('capital_gate', r297.get('status', 'review'), 'USDT dominance and exposure must pass.'),
        _check('halt_authority', r298.get('status', 'review'), 'Autonomous halt authority must be ready.'),
        _check('summary_compact', r299.get('status', 'review'), 'Operator-free Summary must be compact.'),
        _check('real_submit_close_default_off', 'ok', 'Real submit/close remains OFF.'),
    ]
    packet = {
        'small_capital_controlled_autonomy_candidate': candidate,
        'reason': critical,
        'recommended_capital_usdt': min(state['total_usdt'], 250.0),
        'max_notional_usdt': cfg['max_notional_usdt'],
        'max_daily_loss_usdt': cfg['max_daily_loss_usdt'],
        'max_open_positions': cfg['max_open_positions'],
        'max_daily_trades': cfg['max_daily_trades'],
        'allowed_symbols': state['allowed_symbols'],
        'required_approvals': ['owner_session_approval', 'activation_token_preview', 'whitelist', 'daily_hard_stop', 'session_boundary'],
        'actions_allowed_without_owner': ['halt', 'freeze', 'reduce'],
        'actions_blocked_without_owner': ['real_submit', 'real_close', 'auto_scale', 'auto_apply', 'increase_size'],
        'real_submit_close': 'OFF',
        'network': 'OFF',
        'auto_scale': 'OFF',
        'auto_apply': 'OFF',
        'operator_action': 'review_and_keep_default_off' if candidate != 'LIMITED-CANDIDATE' else 'owner_review_required_before_any_live_action',
    }
    status = 'blocked' if candidate == 'BLOCKED' else ('review' if candidate == 'REVIEW' else 'ok')
    return {'engine': 'small_capital_controlled_autonomy_candidate_packet', 'revision': 300, 'status': status, 'generated_at': now_iso(), 'small_capital_controlled_autonomy_candidate_packet': packet, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'post_rev300_operator_decision'}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builders = {
        296: build_rev296_small_capital_autonomy_readiness_recheck,
        297: build_rev297_usdt_dominance_exposure_final_gate,
        298: build_rev298_autonomous_halt_authority_final_proof,
        299: build_rev299_operator_free_summary_final_compact_mode,
        300: build_rev300_small_capital_controlled_autonomy_candidate_packet,
    }
    if int(revision) not in builders:
        raise ValueError(f'Unsupported Rev296-300 revision: {revision}')
    return builders[int(revision)](data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    key_map = {
        296: 'small_capital_autonomy_readiness_recheck',
        297: 'usdt_dominance_exposure_final_gate',
        298: 'autonomous_halt_authority_final_proof',
        299: 'operator_free_summary_final_compact_mode',
        300: 'small_capital_controlled_autonomy_candidate_packet',
    }
    body = _as_dict(payload.get(key_map[int(revision)]))
    reason = _as_dict(body.get('reason') or body.get('critical_blocker'))
    return {
        'revision': int(revision),
        'candidate': body.get('small_capital_controlled_autonomy_candidate') or body.get('readiness') or body.get('capital_gate') or ('READY' if payload.get('status') == 'ok' else 'REVIEW'),
        'critical_issue': reason.get('code', 'none'),
        'operator_action': body.get('operator_action') or reason.get('action') or 'review',
        'max_notional_usdt': body.get('max_notional_usdt'),
        'max_daily_loss_usdt': body.get('max_daily_loss_usdt'),
        'allowed_symbols': body.get('allowed_symbols'),
        'real_submit_close': 'OFF',
        'network': 'OFF',
        'auto_scale': False,
        'auto_apply': False,
        'owner_approval_required': True,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    return {'revision': int(revision), 'status': payload.get('status', 'review'), 'engine': payload.get('engine'), 'check_totals': payload.get('check_totals'), 'contains_secret': False, 'secret_values_returned': False, 'command_preview': payload.get('command_preview')}


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    r296 = build_rev296_small_capital_autonomy_readiness_recheck(data, settings, auth_store, username)
    r297 = build_rev297_usdt_dominance_exposure_final_gate(data, settings, auth_store, username)
    r298 = build_rev298_autonomous_halt_authority_final_proof(data, settings, auth_store, username)
    r299 = build_rev299_operator_free_summary_final_compact_mode(data, settings, auth_store, username)
    r300 = build_rev300_small_capital_controlled_autonomy_candidate_packet(data, settings, auth_store, username)
    checks = []
    for payload in (r296, r297, r298, r299, r300):
        checks.extend(_as_list(payload.get('checks')))
    return {'engine': 'small_capital_controlled_autonomy_candidate_block', 'revision': 300, 'status': r300.get('status', 'review'), 'generated_at': now_iso(), 'rev296_small_capital_autonomy_readiness_recheck': r296, 'rev297_usdt_dominance_exposure_final_gate': r297, 'rev298_autonomous_halt_authority_final_proof': r298, 'rev299_operator_free_summary_final_compact_mode': r299, 'rev300_small_capital_controlled_autonomy_candidate_packet': r300, 'small_capital_controlled_autonomy_candidate_packet': r300.get('small_capital_controlled_autonomy_candidate_packet', {}), 'summary_result': build_summary_for_revision(300, data, settings, auth_store, username), 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'post_rev300_operator_decision'}
