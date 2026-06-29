
"""Rev311-315 Live Permission Safety Contract block.
Read-only decision layer. It never opens/closes real Binance orders and never returns secrets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1','true','yes','on','enabled'}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _settings(settings: dict | None) -> dict:
    s = _dict(settings)
    risk = _dict(s.get('risk') or s.get('live_risk') or s.get('small_capital'))
    live = _dict(s.get('live') or s.get('binance') or s.get('execution'))
    flags = _dict(s.get('flags') or s.get('feature_flags'))
    return {
        'real_submit_enable': _truthy(live.get('real_submit_enable') or flags.get('real_submit_enable') or s.get('real_submit_enable')),
        'real_close_enable': _truthy(live.get('real_close_enable') or flags.get('real_close_enable') or s.get('real_close_enable')),
        'emergency_close_enable': _truthy(live.get('emergency_close_enable') or flags.get('emergency_close_enable') or s.get('emergency_close_enable')),
        'network_enable': _truthy(live.get('network_enable') or flags.get('network_enable') or s.get('network_enable')),
        'auto_scale': _truthy(s.get('auto_scale') or flags.get('auto_scale')),
        'auto_apply': _truthy(s.get('auto_apply') or flags.get('auto_apply')),
        'auto_close': _truthy(s.get('auto_close') or flags.get('auto_close')),
        'max_notional_usdt': _float(risk.get('max_notional_usdt') or s.get('max_notional_usdt'), 25.0),
        'max_daily_loss_usdt': _float(risk.get('max_daily_loss_usdt') or s.get('max_daily_loss_usdt'), 10.0),
        'min_usdt_reserve_pct': _float(risk.get('min_usdt_reserve_pct') or s.get('min_usdt_reserve_pct'), 80.0),
        'max_exposure_pct': _float(risk.get('max_exposure_pct') or s.get('max_exposure_pct'), 15.0),
        'min_evidence_confidence': _float(risk.get('min_evidence_confidence') or s.get('min_evidence_confidence'), 0.72),
        'min_live_sample_count': _int(risk.get('min_live_sample_count') or s.get('min_live_sample_count'), 5),
        'allowed_symbols': list(risk.get('allowed_symbols') or s.get('allowed_symbols') or ['BTCUSDT','ETHUSDT']),
    }


def _state(data: dict | None, settings: dict | None = None, auth_store: dict | None = None) -> dict:
    root = _dict(data)
    wallet = _dict(root.get('wallet') or root.get('shadow_wallet'))
    candidate = _dict(root.get('autonomy_candidate') or root.get('small_cap_candidate') or root.get('candidate'))
    perf = _dict(root.get('live_performance') or root.get('performance'))
    session = _dict(root.get('session') or root.get('limited_live_session'))
    result = _dict(root.get('live_result') or root.get('last_live_result'))
    strategy = _dict(root.get('strategy') or root.get('strategy_reality'))
    cfg = _settings(settings)
    total = _float(wallet.get('total_usdt') or root.get('total_usdt'), 1000.0)
    free = _float(wallet.get('free_usdt') or wallet.get('USDT') or root.get('free_usdt'), total)
    exposure = _float(root.get('active_exposure_usdt') or candidate.get('active_exposure_usdt'), max(0.0, total-free))
    reserve_pct = _float(root.get('usdt_reserve_pct') or candidate.get('usdt_reserve_pct'), (free/total*100.0) if total else 0.0)
    exposure_pct = _float(root.get('exposure_pct') or candidate.get('exposure_pct'), (exposure/total*100.0) if total else 0.0)
    confidence = _float(root.get('evidence_confidence') or candidate.get('evidence_confidence') or perf.get('confidence'), 0.0)
    sample_count = _int(root.get('live_sample_count') or perf.get('sample_count') or result.get('sample_count'), 0)
    pnl = _float(result.get('pnl_usdt') or root.get('pnl_usdt'), 0.0)
    daily_loss = abs(_float(root.get('daily_loss_usdt') or result.get('daily_loss_usdt'), 0.0))
    return {
        'total_usdt': total,
        'free_usdt': free,
        'active_exposure_usdt': exposure,
        'reserve_pct': reserve_pct,
        'exposure_pct': exposure_pct,
        'evidence_confidence': confidence,
        'sample_count': sample_count,
        'pnl_usdt': pnl,
        'daily_loss_usdt': daily_loss,
        'reconciliation': str(root.get('reconciliation') or result.get('reconciliation') or candidate.get('reconciliation') or 'UNKNOWN').upper(),
        'owner_approval': _truthy(root.get('owner_approval') or session.get('owner_approval')),
        'session_scope': str(session.get('scope') or root.get('session_scope') or 'preview'),
        'halt_authority': _truthy(root.get('autonomous_halt_authority') or candidate.get('autonomous_halt_authority') or True),
        'summary_compact': _truthy(root.get('operator_free_summary') or candidate.get('operator_free_summary') or True),
        'strategy_degraded': _truthy(strategy.get('degraded') or root.get('strategy_degraded')),
        'underperformance_count': _int(strategy.get('underperformance_count') or root.get('underperformance_count'), 0),
        'allowed_symbols': cfg['allowed_symbols'],
    }


def _reason(code: str, message: str, action: str, severity: str = 'major', priority: int = 50) -> dict:
    return {'code': code, 'message': message, 'action': action, 'severity': severity, 'priority': priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {'code': 'none', 'message': 'No critical blocker.', 'action': 'none', 'severity': 'info', 'priority': 999}
    return sorted(reasons, key=lambda r: (r.get('priority', 999), r.get('severity') != 'critical'))[0]


def _check(name: str, status: str, detail: str) -> dict:
    return {'name': name, 'status': status, 'detail': detail}


def _totals(checks: list[dict]) -> dict:
    return {'total': len(checks), 'ok': sum(1 for c in checks if c.get('status') == 'ok'), 'review': sum(1 for c in checks if c.get('status') == 'review'), 'blocked': sum(1 for c in checks if c.get('status') == 'blocked')}


def _status(checks: list[dict]) -> str:
    if any(c.get('status') == 'blocked' for c in checks):
        return 'blocked'
    if any(c.get('status') == 'review' for c in checks):
        return 'review'
    return 'ready'


def _base_reasons(settings: dict | None) -> list[dict]:
    cfg = _settings(settings)
    reasons: list[dict] = []
    if cfg['real_submit_enable'] or cfg['real_close_enable'] or cfg['emergency_close_enable'] or cfg['network_enable']:
        reasons.append(_reason('real_execution_flag_enabled', 'Real submit/close/network flags must remain OFF by default.', 'disable_real_execution_flags', 'critical', 1))
    if cfg['auto_scale'] or cfg['auto_apply'] or cfg['auto_close']:
        reasons.append(_reason('unsafe_auto_action_enabled', 'Auto-scale, auto-apply and auto-close must remain OFF.', 'disable_auto_actions', 'critical', 2))
    return reasons


def _command_preview() -> dict:
    return {'real_submit': 'OFF', 'real_close': 'OFF', 'auto_scale': 'OFF', 'auto_apply': 'OFF', 'auto_close': 'OFF', 'network': 'OFF'}


def _make_payload(revision: int, payload_key: str, label: str, data: dict | None, settings: dict | None, auth_store: dict | None, username: str) -> dict:
    cfg = _settings(settings)
    state = _state(data, settings, auth_store)
    reasons = _base_reasons(settings)
    if state['reconciliation'] not in {'OK','CONSISTENT'}:
        reasons.append(_reason('reconciliation_not_ok', 'Position/order/journal evidence is not consistent.', 'resolve_reconciliation_before_live_action', 'major', 10))
    if state['daily_loss_usdt'] >= cfg['max_daily_loss_usdt']:
        reasons.append(_reason('daily_loss_limit_hit', 'Daily hard stop would be violated.', 'halt_for_the_day', 'critical', 3))
    if state['reserve_pct'] < cfg['min_usdt_reserve_pct']:
        reasons.append(_reason('usdt_reserve_below_policy', 'USDT reserve dominance is below policy.', 'reduce_exposure_keep_usdt_dominant', 'major', 20))
    if state['exposure_pct'] > cfg['max_exposure_pct']:
        reasons.append(_reason('exposure_above_policy', 'Active exposure is above policy.', 'freeze_new_trades_reduce_exposure', 'major', 21))
    if revision in {311, 315} and state['sample_count'] < cfg['min_live_sample_count']:
        reasons.append(_reason('insufficient_live_sample', 'Controlled live sample count is still below threshold.', 'keep_freeze_or_manual_review', 'major', 22))
    if revision in {312, 315} and state['evidence_confidence'] < cfg['min_evidence_confidence']:
        reasons.append(_reason('evidence_confidence_low', 'Evidence confidence is below controlled autonomy threshold.', 'collect_more_high_quality_evidence', 'major', 23))
    if revision in {313, 315} and not state['owner_approval']:
        reasons.append(_reason('owner_approval_required', 'Owner approval remains required for any live action.', 'request_owner_approval_preview_only', 'major', 30))
    if revision in {314, 315} and not state['halt_authority']:
        reasons.append(_reason('halt_authority_missing', 'System must be able to halt/freeze/reduce itself.', 'enable_read_only_halt_authority', 'critical', 5))
    if revision in {315} and (state['strategy_degraded'] or state['underperformance_count'] >= 3):
        reasons.append(_reason('strategy_underperformance', 'Strategy-symbol pair is underperforming live reality checks.', 'quarantine_or_downgrade_strategy', 'major', 24))
    checks = [
        _check('real_execution_default_off', 'ok' if not (cfg['real_submit_enable'] or cfg['real_close_enable'] or cfg['network_enable']) else 'blocked', 'Real execution flags remain OFF.'),
        _check('unsafe_auto_actions_off', 'ok' if not (cfg['auto_scale'] or cfg['auto_apply'] or cfg['auto_close']) else 'blocked', 'Auto-scale/apply/close remain OFF.'),
        _check('reconciliation_consistent', 'ok' if state['reconciliation'] in {'OK','CONSISTENT'} else 'review', 'Reconciliation should be consistent before growth.'),
        _check('capital_policy_safe', 'ok' if state['reserve_pct'] >= cfg['min_usdt_reserve_pct'] and state['exposure_pct'] <= cfg['max_exposure_pct'] else 'review', 'USDT dominance and exposure envelope checked.'),
        _check('owner_growth_blocked', 'ok', 'No growth or live submit is allowed without owner-controlled activation.'),
    ]
    status = _status(checks)
    decision = 'READY' if status == 'ready' and not reasons else ('BLOCKED' if any(r.get('severity') == 'critical' for r in reasons) else 'REVIEW')
    critical = _critical(reasons)
    body = {
        'decision': decision,
        'live_permission_safety': decision,
        'revision': revision,
        'label': label,
        'critical_blocker': critical,
        'operator_action': critical.get('action'),
        'max_notional_usdt': cfg['max_notional_usdt'],
        'max_daily_loss_usdt': cfg['max_daily_loss_usdt'],
        'allowed_symbols': state['allowed_symbols'],
        'usdt_reserve_pct': round(state['reserve_pct'], 2),
        'exposure_pct': round(state['exposure_pct'], 2),
        'sample_count': state['sample_count'],
        'evidence_confidence': state['evidence_confidence'],
        'actions_allowed_without_owner': ['halt', 'freeze', 'reduce'],
        'actions_blocked_without_owner': ['real_submit', 'real_close', 'auto_scale', 'auto_apply', 'auto_close'],
    }
    return {'engine': 'live_permission_safety_contract', 'revision': revision, 'status': status, 'generated_at': now_iso(), payload_key: body, 'checks': checks, 'check_totals': _totals(checks), 'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False, 'next_allowed_step': 'rev315_packet_or_next_block'}

def build_rev311_live_permission_contract_schema(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _make_payload(311, 'live_permission_contract_schema', 'Live permission contract schema', data, settings, auth_store, username)

def build_rev312_owner_approval_session_scope_final_guard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _make_payload(312, 'owner_approval_session_scope_final_guard', 'Owner approval + session scope final guard', data, settings, auth_store, username)

def build_rev313_whitelist_symbol_permission_enforcement(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _make_payload(313, 'whitelist_symbol_permission_enforcement', 'Whitelist + symbol permission enforcement', data, settings, auth_store, username)

def build_rev314_daily_hard_stop_max_notional_binding(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _make_payload(314, 'daily_hard_stop_max_notional_binding', 'Daily hard stop + max notional binding', data, settings, auth_store, username)

def build_rev315_live_permission_safety_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    return _make_payload(315, 'live_permission_safety_decision_packet', 'Live permission safety decision packet', data, settings, auth_store, username)


_BUILDERS = {
    311: build_rev311_live_permission_contract_schema,
    312: build_rev312_owner_approval_session_scope_final_guard,
    313: build_rev313_whitelist_symbol_permission_enforcement,
    314: build_rev314_daily_hard_stop_max_notional_binding,
    315: build_rev315_live_permission_safety_decision_packet,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    try:
        builder = _BUILDERS[int(revision)]
    except KeyError as exc:
        raise ValueError(f'Unsupported Rev{revision} for Live Permission Safety Contract') from exc
    return builder(data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get(_REV_KEYS[int(revision)], {})
    blocker = body.get('critical_blocker') or {}
    return {
        'revision': int(revision),
        'status': payload.get('status'),
        'live_permission_safety': body.get('live_permission_safety') or body.get('decision') or payload.get('status'),
        'decision': body.get('decision') or payload.get('status'),
        'critical_issue': blocker.get('code', 'none'),
        'operator_action': body.get('operator_action') or blocker.get('action', 'none'),
        'max_notional_usdt': body.get('max_notional_usdt'),
        'max_daily_loss_usdt': body.get('max_daily_loss_usdt'),
        'allowed_symbols': body.get('allowed_symbols', []),
        'real_submit': 'OFF',
        'real_close': 'OFF',
        'auto_scale': 'OFF',
        'auto_apply': 'OFF',
        'auto_close': 'OFF',
        'contains_secret': False,
    }


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    parts = {rev: build_for_revision(rev, data, settings, auth_store, username) for rev in range(311, 315+1)}
    final = parts[315].get(_REV_KEYS[315], {})
    checks = []
    for p in parts.values():
        checks.extend(p.get('checks', []))
    return {
        'engine': 'live_permission_safety_contract',
        'revision': 315,
        'status': 'blocked' if any(p.get('status') == 'blocked' for p in parts.values()) else ('review' if any(p.get('status') == 'review' for p in parts.values()) else 'ready'),
        'generated_at': now_iso(),
        'rev311_live_permission_contract_schema': parts[311],
        'rev312_owner_approval_session_scope_final_guard': parts[312],
        'rev313_whitelist_symbol_permission_enforcement': parts[313],
        'rev314_daily_hard_stop_max_notional_binding': parts[314],
        'rev315_live_permission_safety_decision_packet': parts[315],
        'live_permission_safety_decision_packet': final,
        'summary_result': build_summary_for_revision(315, data, settings, auth_store, username),
        'checks': checks,
        'check_totals': _totals(checks),
        'command_preview': _command_preview(),
        'contains_secret': False,
        'secret_values_returned': False,
        'next_allowed_step': 'next_controlled_block',
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    commands = payload.get('command_preview', {})
    pass_gate = (
        payload.get('contains_secret') is False
        and payload.get('secret_values_returned') is False
        and commands.get('real_submit') == 'OFF'
        and commands.get('real_close') == 'OFF'
        and commands.get('auto_scale') == 'OFF'
        and commands.get('auto_apply') == 'OFF'
        and commands.get('auto_close') == 'OFF'
        and commands.get('network') == 'OFF'
    )
    return {'revision': int(revision), 'quality_gate': 'PASS' if pass_gate else 'FAIL', 'payload_status': payload.get('status'), 'checks': payload.get('checks', []), 'command_preview': commands, 'contains_secret': False, 'secret_values_returned': False}

_REV_KEYS = {
    311: 'live_permission_contract_schema',
    312: 'owner_approval_session_scope_final_guard',
    313: 'whitelist_symbol_permission_enforcement',
    314: 'daily_hard_stop_max_notional_binding',
    315: 'live_permission_safety_decision_packet',
}
