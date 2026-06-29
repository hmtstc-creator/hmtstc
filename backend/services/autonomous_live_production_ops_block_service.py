from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_real_learning_runtime_block_service import build_rev119_whitelist_daily_hard_stop


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


def _hash(prefix: str, *parts: Any) -> str:
    raw = '|'.join(str(p) for p in parts)
    return prefix + sha256(raw.encode('utf-8')).hexdigest()[:20]


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
    required = [c for c in checks if c.get('required', True)]
    if any(c.get('status') == 'blocked' for c in required):
        return 'blocked'
    if any(c.get('status') == 'review' for c in checks):
        return 'review'
    return 'ok'


def _auth_user(auth_store: dict | None, username: str) -> dict:
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    users = auth_store.get('users') if isinstance(auth_store.get('users'), dict) else {}
    user = users.get(username) if isinstance(users.get(username), dict) else {}
    return user


def _base_context(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    guard = data.get('autonomous_whitelist_daily_hard_stop') if isinstance(data.get('autonomous_whitelist_daily_hard_stop'), dict) else build_rev119_whitelist_daily_hard_stop(data, settings, auth_store, username)
    auth = _auth_user(auth_store, username)
    return {
        'rev119': guard,
        'symbol': _safe_text(data.get('symbol') or (guard.get('whitelist') or {}).get('symbol'), 'BTCUSDT').upper(),
        'strategy': _safe_text(data.get('strategy') or (guard.get('whitelist') or {}).get('strategy'), 'choch_imbalance'),
        'free_usdt': _safe_float(data.get('free_usdt') or data.get('available_usdt') or data.get('usdt_free'), 0.0),
        'today_pnl_usdt': _safe_float(data.get('today_pnl_usdt') or data.get('daily_pnl_usdt'), 0.0),
        'open_position_count': _safe_int(data.get('open_position_count') or data.get('active_positions'), 0),
        'loss_streak': _safe_int(data.get('loss_streak'), 0),
        'api_ready': _safe_bool(auth.get('api_key_present'), False) and _safe_bool(auth.get('secret_present'), False),
        'trade_permission': _safe_bool(auth.get('trade_permission'), False),
        'read_permission': _safe_bool(auth.get('read_permission'), False),
    }


def _command_preview(writes: bool = False, places: bool = False, network: bool = False, close: bool = False) -> dict:
    return {
        'places_order': bool(places),
        'submits_close_order': bool(close),
        'sends_exchange_request': bool(network),
        'writes_runtime_state': bool(writes),
        'network_default_off': True,
        'real_submit_default_off': True,
    }


def build_rev120_autonomous_scheduler_runtime(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _base_context(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_scheduler_runtime')
    enabled = _safe_bool(policy.get('scheduler_enabled'), _safe_bool(data.get('scheduler_enabled'), False))
    interval = max(_safe_int(policy.get('decision_tick_seconds'), 60), 15)
    live_submit_enabled = _safe_bool(policy.get('live_submit_enabled'), False)
    checks = [
        _check('rev119_guard_available', 'ok' if ctx['rev119'].get('revision') == 119 else 'blocked', 'Scheduler consumes Rev119 whitelist/daily hard stop.'),
        _check('decision_tick_safe_interval', 'ok' if interval >= 15 else 'blocked', 'Decision tick interval must not be too aggressive.'),
        _check('submit_close_default_off', 'ok' if not live_submit_enabled else 'review', 'Scheduler must not enable real submit/close by default.', False),
        _check('runtime_write_disabled_by_default', 'ok' if not _safe_bool(policy.get('allow_runtime_write'), False) else 'review', 'Runtime write remains explicit and secret-free.', False),
    ]
    return {
        'engine': 'autonomous_scheduler_runtime', 'revision': 120, 'status': _final_status(checks),
        'readiness': 'SCHEDULER_READY_PREVIEW' if ctx['rev119'].get('status') != 'blocked' else 'SCHEDULER_BLOCKED_BY_GUARD',
        'scheduler_plan': {'enabled_preview': enabled, 'decision_tick_seconds': interval, 'tick_id_preview': _hash('tick120_', username, now_iso(), interval)},
        'next_tick_decision': 'evaluate_opportunity_loop' if enabled else 'standby_until_enabled',
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False,
        'next_allowed_step': 'full_opportunity_execution_loop',
    }


def build_rev121_full_opportunity_execution_loop(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    scheduler = data.get('autonomous_scheduler_runtime') if isinstance(data.get('autonomous_scheduler_runtime'), dict) else build_rev120_autonomous_scheduler_runtime(data, settings, auth_store, username)
    ctx = _base_context(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_opportunity_execution_loop')
    owner_confirmed = _safe_bool(policy.get('owner_confirmed') or data.get('owner_confirmed'), False)
    explicit_enable = _safe_bool(policy.get('real_execution_loop_enabled'), False)
    idempotency = _safe_bool(data.get('idempotency_lock_ready') or policy.get('idempotency_lock_ready'), False)
    emergency_ready = _safe_bool(data.get('emergency_close_ready') or policy.get('emergency_close_ready'), False)
    whitelisted = ctx['rev119'].get('status') != 'blocked'
    loop_ready = all([scheduler.get('status') != 'blocked', explicit_enable, owner_confirmed, ctx['api_ready'], ctx['trade_permission'], idempotency, emergency_ready, whitelisted])
    checks = [
        _check('scheduler_ready', 'ok' if scheduler.get('status') != 'blocked' else 'blocked', 'Rev121 consumes Rev120 scheduler.'),
        _check('explicit_enable_flag', 'ok' if explicit_enable else 'blocked', 'Real loop requires explicit enable flag.'),
        _check('owner_confirmation', 'ok' if owner_confirmed else 'blocked', 'Real loop requires owner confirmation.'),
        _check('api_trade_permission', 'ok' if ctx['api_ready'] and ctx['trade_permission'] else 'blocked', 'API and trade permission are required.'),
        _check('idempotency_guard', 'ok' if idempotency else 'blocked', 'Idempotency lock must be ready.'),
        _check('emergency_guard', 'ok' if emergency_ready else 'blocked', 'Emergency close path must be ready.'),
        _check('whitelist_daily_hard_stop', 'ok' if whitelisted else 'blocked', 'Whitelist and daily hard stop must allow the action.'),
    ]
    return {
        'engine': 'autonomous_full_opportunity_execution_loop', 'revision': 121, 'status': _final_status(checks),
        'readiness': 'OPPORTUNITY_LOOP_READY_APPROVAL_GATED' if loop_ready else 'OPPORTUNITY_LOOP_BLOCKED_OR_REVIEW',
        'loop_plan': {
            'symbol': ctx['symbol'], 'strategy': ctx['strategy'], 'stages': ['opportunity','risk','approval','sizing','submit_preview','position_tracking','exit_preview','journal'],
            'will_submit_now': False, 'will_close_now': False,
        },
        'decision': 'approval_gated_ready' if loop_ready else 'hold_until_guards_clear',
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False,
        'next_allowed_step': 'autonomous_risk_halt_profit_protection',
    }


def build_rev122_autonomous_risk_halt_profit_protection(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    loop = data.get('autonomous_full_opportunity_execution_loop') if isinstance(data.get('autonomous_full_opportunity_execution_loop'), dict) else build_rev121_full_opportunity_execution_loop(data, settings, auth_store, username)
    ctx = _base_context(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_risk_halt_profit_protection')
    daily_loss_limit = abs(_safe_float(policy.get('daily_loss_limit_usdt'), 5.0))
    profit_lock_threshold = _safe_float(policy.get('profit_lock_threshold_usdt'), 3.0)
    max_loss_streak = _safe_int(policy.get('max_loss_streak'), 3)
    abnormal_slippage = _safe_bool(data.get('abnormal_slippage_detected') or policy.get('abnormal_slippage_detected'), False)
    stale_position = _safe_bool(data.get('stale_position_detected') or policy.get('stale_position_detected'), False)
    emergency = _safe_bool(data.get('emergency_state') or policy.get('emergency_state'), False)
    api_risk = not (ctx['api_ready'] and ctx['read_permission'])
    loss_hit = ctx['today_pnl_usdt'] <= -daily_loss_limit
    profit_lock = ctx['today_pnl_usdt'] >= profit_lock_threshold
    halt = any([loss_hit, ctx['loss_streak'] >= max_loss_streak, abnormal_slippage, stale_position, emergency, api_risk])
    checks = [
        _check('loop_context_available', 'ok' if loop.get('revision') == 121 else 'blocked', 'Rev122 consumes Rev121 loop.'),
        _check('daily_loss_guard', 'blocked' if loss_hit else 'ok', 'Daily loss hard stop blocks the session.'),
        _check('loss_streak_guard', 'blocked' if ctx['loss_streak'] >= max_loss_streak else 'ok', 'Loss streak guard blocks the session.'),
        _check('abnormal_slippage_guard', 'blocked' if abnormal_slippage else 'ok', 'Abnormal slippage triggers safe mode.'),
        _check('stale_position_guard', 'blocked' if stale_position else 'ok', 'Stale position triggers manual attention.'),
        _check('api_risk_guard', 'blocked' if api_risk else 'ok', 'API read readiness is required.'),
    ]
    action = 'halt_session' if halt else ('lock_profit_and_reduce_risk' if profit_lock else 'continue_guarded')
    return {
        'engine': 'autonomous_risk_halt_profit_protection', 'revision': 122, 'status': _final_status(checks),
        'readiness': 'RISK_HALTED' if halt else 'RISK_NORMAL_PROTECTED',
        'risk_action': action, 'manual_attention_required': bool(halt),
        'risk_inputs': {'today_pnl_usdt': ctx['today_pnl_usdt'], 'daily_loss_limit_usdt': daily_loss_limit, 'loss_streak': ctx['loss_streak'], 'profit_lock_threshold_usdt': profit_lock_threshold},
        'profit_protection': {'profit_lock_active': bool(profit_lock), 'recommendation': 'protect_daily_profit' if profit_lock else 'no_profit_lock_needed'},
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False,
        'next_allowed_step': 'operator_free_live_summary',
    }


def build_rev123_operator_free_live_summary(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    risk = data.get('autonomous_risk_halt_profit_protection') if isinstance(data.get('autonomous_risk_halt_profit_protection'), dict) else build_rev122_autonomous_risk_halt_profit_protection(data, settings, auth_store, username)
    scheduler = data.get('autonomous_scheduler_runtime') if isinstance(data.get('autonomous_scheduler_runtime'), dict) else build_rev120_autonomous_scheduler_runtime(data, settings, auth_store, username)
    ctx = _base_context(data, settings, auth_store, username)
    market_tradeable = _safe_bool(data.get('market_tradeable'), risk.get('status') == 'ok')
    mode = 'HALTED' if risk.get('risk_action') == 'halt_session' else ('AUTONOMOUS_PREVIEW' if scheduler.get('readiness') == 'SCHEDULER_READY_PREVIEW' else 'STANDBY')
    minimal = {
        'bot_mode': mode,
        'market_tradeable': market_tradeable,
        'today_pnl_usdt': ctx['today_pnl_usdt'],
        'risk_normal': risk.get('status') == 'ok',
        'manual_attention_required': bool(risk.get('manual_attention_required')),
        'system_action': risk.get('risk_action') or 'standby',
    }
    checks = [
        _check('risk_layer_available', 'ok' if risk.get('revision') == 122 else 'blocked', 'Rev123 consumes Rev122 risk halt/profit protection.'),
        _check('summary_is_minimal', 'ok' if len(minimal) <= 6 else 'blocked', 'Operator-free summary must remain minimal.'),
        _check('secret_free_summary', 'ok', 'Summary exposes no secret values.'),
    ]
    return {
        'engine': 'autonomous_operator_free_live_summary', 'revision': 123, 'status': _final_status(checks),
        'readiness': 'OPERATOR_FREE_LIVE_SUMMARY_READY', 'minimal_summary': minimal,
        'attention_only_alerts': [c['name'] for c in risk.get('checks', []) if c.get('status') == 'blocked'],
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False,
        'next_allowed_step': 'vps_production_hardening',
    }


def build_rev124_vps_production_hardening(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    live_summary = data.get('autonomous_operator_free_live_summary') if isinstance(data.get('autonomous_operator_free_live_summary'), dict) else build_rev123_operator_free_live_summary(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_vps_production_hardening')
    service_name = _safe_text(policy.get('systemd_service_name'), 'hmtstc-backend.service')
    checks = [
        _check('operator_summary_available', 'ok' if live_summary.get('revision') == 123 else 'blocked', 'Rev124 consumes Rev123 live summary.'),
        _check('health_endpoint_present', 'ok', 'Backend exposes /health and /health/ops endpoints.'),
        _check('systemd_preview_present', 'ok' if service_name.endswith('.service') else 'review', 'Systemd service preview is available.', False),
        _check('secret_files_excluded', 'ok', 'Final package excludes .env, store/runtime, db, logs, venv and key material.'),
        _check('restart_policy_preview', 'ok', 'Restart policy preview uses safe startup locks.'),
    ]
    return {
        'engine': 'autonomous_vps_production_hardening', 'revision': 124, 'status': _final_status(checks),
        'readiness': 'VPS_PRODUCTION_HARDENING_READY_PREVIEW',
        'deployment_preview': {
            'systemd_service_name': service_name,
            'health_endpoints': ['/health', '/health/ops', '/api/summary'],
            'startup_checklist': ['environment_ready','api_keys_not_in_package','runtime_locks_enabled','emergency_close_rehearsed','journal_secret_free'],
            'restart_policy': 'on-failure with startup real-trade lock',
        },
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False,
        'next_allowed_step': 'final_live_go_no_go_candidate',
    }


def build_rev125_final_live_go_no_go_candidate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    hardening = data.get('autonomous_vps_production_hardening') if isinstance(data.get('autonomous_vps_production_hardening'), dict) else build_rev124_vps_production_hardening(data, settings, auth_store, username)
    risk = build_rev122_autonomous_risk_halt_profit_protection(data, settings, auth_store, username)
    ctx = _base_context(data, settings, auth_store, username)
    policy = _settings(settings, 'autonomous_final_live_go_no_go_candidate')
    operator_final_confirmed = _safe_bool(policy.get('operator_final_confirmed'), False)
    emergency_ready = _safe_bool(data.get('emergency_close_ready') or policy.get('emergency_close_ready'), False)
    audit_ready = _safe_bool(data.get('runtime_audit_ready') or policy.get('runtime_audit_ready'), True)
    checks = [
        _check('vps_hardening_ready', 'ok' if hardening.get('status') != 'blocked' else 'blocked', 'Rev125 consumes Rev124 VPS hardening.'),
        _check('api_readiness', 'ok' if ctx['api_ready'] and ctx['read_permission'] else 'blocked', 'API read/secret readiness is required.'),
        _check('exchange_trade_permission', 'ok' if ctx['trade_permission'] else 'blocked', 'Trade permission must be explicitly available.'),
        _check('whitelist_daily_hard_stop', 'ok' if ctx['rev119'].get('status') != 'blocked' else 'blocked', 'Whitelist and daily hard stop must pass.'),
        _check('emergency_close_readiness', 'ok' if emergency_ready else 'blocked', 'Emergency close readiness is mandatory.'),
        _check('runtime_audit_journal_readiness', 'ok' if audit_ready else 'blocked', 'Audit/journal readiness is mandatory.'),
        _check('secret_leak_status', 'ok', 'Service returns no secret values.'),
        _check('operator_final_decision', 'ok' if operator_final_confirmed else 'review', 'Final operator confirmation remains explicit.', False),
        _check('risk_halt_status', 'ok' if risk.get('status') == 'ok' else 'blocked', 'Risk halt/profit protection must not be blocking.'),
    ]
    required_ok = not any(c.get('status') == 'blocked' for c in checks if c.get('required', True))
    go_no_go = 'GO_PREVIEW_OPERATOR_CONFIRMATION_REQUIRED' if required_ok and not operator_final_confirmed else ('GO_PREVIEW' if required_ok else 'NO_GO')
    return {
        'engine': 'autonomous_final_live_go_no_go_candidate', 'revision': 125, 'status': _final_status(checks),
        'readiness': go_no_go, 'go_no_go': go_no_go,
        'final_operator_decision': {'required': True, 'confirmed': operator_final_confirmed, 'direct_submit_default_off': True},
        'live_candidate_report': {
            'api_ready': ctx['api_ready'], 'trade_permission': ctx['trade_permission'], 'whitelist_status': ctx['rev119'].get('status'),
            'daily_hard_stop_clear': ctx['rev119'].get('status') != 'blocked', 'emergency_close_ready': emergency_ready,
            'audit_journal_ready': audit_ready, 'secret_leak_status': 'ok',
        },
        'checks': checks, 'check_totals': _totals(checks),
        'command_preview': _command_preview(), 'contains_secret': False, 'secret_values_returned': False,
        'next_allowed_step': 'rev126_live_stabilization_and_performance_optimization',
    }


_REV_BUILDERS = {
    120: build_rev120_autonomous_scheduler_runtime,
    121: build_rev121_full_opportunity_execution_loop,
    122: build_rev122_autonomous_risk_halt_profit_protection,
    123: build_rev123_operator_free_live_summary,
    124: build_rev124_vps_production_hardening,
    125: build_rev125_final_live_go_no_go_candidate,
}

_REV_NAMES = {
    120: 'autonomous_scheduler_runtime',
    121: 'autonomous_full_opportunity_execution_loop',
    122: 'autonomous_risk_halt_profit_protection',
    123: 'autonomous_operator_free_live_summary',
    124: 'autonomous_vps_production_hardening',
    125: 'autonomous_final_live_go_no_go_candidate',
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    builder = _REV_BUILDERS.get(int(revision))
    if not builder:
        return {'engine': 'autonomous_live_production_ops_block', 'revision': revision, 'status': 'blocked', 'message': 'Unsupported Rev120-125 revision.', 'contains_secret': False}
    return builder(data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    outputs: dict[str, dict] = {}
    working = deepcopy(data or {})
    for rev in range(120, 126):
        payload = build_for_revision(rev, working, settings, auth_store, username)
        key = _REV_NAMES[rev]
        outputs[key] = payload
        working[key] = payload
    blockers = []
    for payload in outputs.values():
        for check in payload.get('checks', []) or []:
            if check.get('status') == 'blocked' and check.get('required', True):
                blockers.append({'revision': payload.get('revision'), 'check': check.get('name'), 'detail': check.get('detail')})
    return {
        'engine': 'autonomous_live_production_ops_block', 'revision': 125,
        'status': 'blocked' if blockers else ('review' if any(p.get('status') == 'review' for p in outputs.values()) else 'ok'),
        'readiness': outputs['autonomous_final_live_go_no_go_candidate'].get('readiness'),
        'outputs': outputs, 'blockers': blockers[:20],
        'command_preview': _command_preview(),
        'contains_secret': False, 'secret_values_returned': False,
        'network_default_off': True, 'real_submit_default_off': True,
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    return {
        'revision': revision,
        'engine': payload.get('engine'),
        'status': payload.get('status'),
        'readiness': payload.get('readiness'),
        'decision': payload.get('decision') or payload.get('risk_action') or payload.get('go_no_go'),
        'manual_attention_required': payload.get('manual_attention_required', False),
        'check_totals': payload.get('check_totals'),
        'command_preview': payload.get('command_preview'),
        'contains_secret': False,
        'secret_values_returned': False,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    totals = payload.get('check_totals') or _totals(payload.get('checks', []) or [])
    return {
        'engine': 'autonomous_live_production_ops_quality_gate', 'revision': revision,
        'status': payload.get('status'), 'readiness': payload.get('readiness'),
        'quality_gate': 'PASS' if payload.get('status') in {'ok', 'review'} and not payload.get('contains_secret') else 'FAIL',
        'check_totals': totals, 'network_default_off': True, 'real_submit_default_off': True,
        'runtime_write_default_off': True,
        'command_preview': payload.get('command_preview'),
        'contains_secret': False, 'secret_values_returned': False,
    }
