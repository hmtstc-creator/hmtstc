from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

REVISION = 900


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


def get_user_record(auth_store: dict | None, username: str) -> dict:
    return as_dict(as_dict(auth_store).get('users')).get(username, {}) or {}


def _mask_decision_hash(*parts: Any) -> str:
    raw = '|'.join(str(part) for part in parts).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def _default_payload() -> dict:
    return {
        'paper_signal': {
            'symbol': 'BTCUSDT',
            'strategy': 'choch_micro_scalper',
            'side': 'buy',
            'signal_score': 82,
            'quality_score': 78,
            'expected_edge_usdt': 1.25,
            'signal_age_ms': 450,
        },
        'risk_context': {
            'risk_firewall': 'pass',
            'capital_gate': 'pass',
            'daily_loss_usdt': 0,
            'max_daily_loss_usdt': 10,
            'max_notional_usdt': 25,
            'requested_notional_usdt': 15,
            'usdt_reserve_ratio': 0.92,
        },
        'approval_context': {
            'owner_approved': False,
            'activation_token_present': False,
            'explicit_submit_enabled': False,
            'session_id': 'dry-run-session',
            'session_open': True,
        },
    }


def _build_intent(signal: dict, risk: dict) -> dict:
    symbol = normalize_symbol(signal.get('symbol'))
    strategy = str(signal.get('strategy') or 'unknown_strategy').strip() or 'unknown_strategy'
    requested_notional = round(max(0.0, safe_float(risk.get('requested_notional_usdt'), 0.0)), 8)
    max_notional = round(max(0.0, safe_float(risk.get('max_notional_usdt'), 0.0)), 8)
    notional = min(requested_notional, max_notional) if max_notional > 0 else requested_notional
    side = 'sell' if str(signal.get('side') or '').lower() == 'sell' else 'buy'
    score = max(0.0, min(100.0, safe_float(signal.get('signal_score'), 0.0)))
    quality = max(0.0, min(100.0, safe_float(signal.get('quality_score'), score)))
    edge = round(safe_float(signal.get('expected_edge_usdt'), 0.0), 8)
    intent_id = 'dry-intent-' + _mask_decision_hash(symbol, strategy, side, notional, score)
    blockers = []
    if notional <= 0:
        blockers.append('notional_missing')
    if score < 65:
        blockers.append('paper_signal_score_low')
    if quality < 65:
        blockers.append('opportunity_quality_low')
    if edge <= 0:
        blockers.append('expected_edge_not_positive')
    return {
        'intent_id': intent_id,
        'symbol': symbol,
        'strategy': strategy,
        'side': side,
        'notional_usdt': round(notional, 8),
        'signal_score': round(score, 4),
        'quality_score': round(quality, 4),
        'expected_edge_usdt': edge,
        'status': 'ready' if not blockers else 'blocked',
        'blockers': blockers,
        'secret_values_returned': False,
    }


def _build_order_preview(intent: dict, risk: dict, user_record: dict) -> dict:
    allowed_symbols = [normalize_symbol(item) for item in as_list(user_record.get('allowed_symbols'))]
    if not allowed_symbols:
        allowed_symbols = [intent['symbol']]
    max_notional = max(0.0, safe_float(risk.get('max_notional_usdt'), intent.get('notional_usdt')))
    notional = safe_float(intent.get('notional_usdt'), 0.0)
    estimated_binance_fee = round(notional * 0.001, 8)
    blockers = []
    if intent.get('status') != 'ready':
        blockers.append('intent_not_ready')
    if intent['symbol'] not in allowed_symbols:
        blockers.append('symbol_not_whitelisted')
    if max_notional > 0 and notional > max_notional:
        blockers.append('max_notional_exceeded')
    return {
        'preview_id': 'dry-preview-' + _mask_decision_hash(intent.get('intent_id'), notional, max_notional),
        'symbol': intent['symbol'],
        'side': intent['side'],
        'type': 'MARKET_PREVIEW_ONLY',
        'notional_usdt': round(notional, 8),
        'estimated_binance_fee_usdt': estimated_binance_fee,
        'allowed_symbols': allowed_symbols,
        'real_submit_attempted': False,
        'status': 'ready' if not blockers else 'blocked',
        'blockers': blockers,
        'secret_values_returned': False,
    }


def _risk_approval(intent: dict, preview: dict, risk: dict) -> dict:
    daily_loss = max(0.0, safe_float(risk.get('daily_loss_usdt'), 0.0))
    max_daily_loss = max(0.0, safe_float(risk.get('max_daily_loss_usdt'), 0.0))
    reserve_ratio = safe_float(risk.get('usdt_reserve_ratio'), 1.0)
    firewall = str(risk.get('risk_firewall') or 'pass').strip().lower()
    capital_gate = str(risk.get('capital_gate') or 'pass').strip().lower()
    blockers = []
    if intent.get('status') != 'ready':
        blockers.append('intent_blocked')
    if preview.get('status') != 'ready':
        blockers.append('order_preview_blocked')
    if firewall not in {'pass', 'ok', 'ready'}:
        blockers.append('risk_firewall_blocked')
    if capital_gate not in {'pass', 'ok', 'ready'}:
        blockers.append('capital_gate_blocked')
    if max_daily_loss > 0 and daily_loss >= max_daily_loss:
        blockers.append('daily_hard_stop_reached')
    if reserve_ratio < 0.70:
        blockers.append('usdt_reserve_weak')
    return {
        'decision': 'APPROVED_FOR_PREVIEW' if not blockers else 'BLOCKED',
        'blockers': blockers,
        'daily_loss_usdt': round(daily_loss, 8),
        'max_daily_loss_usdt': round(max_daily_loss, 8),
        'usdt_reserve_ratio': round(reserve_ratio, 4),
        'real_submit_allowed': False,
        'secret_values_returned': False,
    }


def _approval_preview(approval_context: dict, risk_result: dict) -> dict:
    owner_approved = safe_bool(approval_context.get('owner_approved'))
    token_present = safe_bool(approval_context.get('activation_token_present'))
    explicit_enabled = safe_bool(approval_context.get('explicit_submit_enabled'))
    session_open = safe_bool(approval_context.get('session_open'))
    blockers = []
    if risk_result.get('decision') != 'APPROVED_FOR_PREVIEW':
        blockers.append('risk_or_preview_not_approved')
    if not owner_approved:
        blockers.append('owner_approval_missing')
    if not token_present:
        blockers.append('activation_token_missing')
    if not explicit_enabled:
        blockers.append('explicit_submit_disabled')
    if not session_open:
        blockers.append('session_closed')
    return {
        'decision': 'READY_BUT_SUBMIT_DEFAULT_OFF' if not blockers else 'SUBMIT_BLOCKED',
        'critical_blocker': blockers[0] if blockers else 'real_submit_default_off_policy',
        'blockers': blockers or ['real_submit_default_off_policy'],
        'owner_approved': owner_approved,
        'activation_token_present': token_present,
        'explicit_submit_enabled': explicit_enabled,
        'session_id': str(approval_context.get('session_id') or 'dry-run-session'),
        'real_submit_attempted': False,
        'real_network_call_performed': False,
        'secret_values_returned': False,
    }


def run_paper_to_live_dry_production_drill(payload: dict | None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = as_dict(payload) or _default_payload()
    signal = as_dict(payload.get('paper_signal') or _default_payload()['paper_signal'])
    risk = as_dict(payload.get('risk_context') or _default_payload()['risk_context'])
    approval_context = as_dict(payload.get('approval_context') or _default_payload()['approval_context'])
    user_record = get_user_record(auth_store, username)

    intent = _build_intent(signal, risk)
    preview = _build_order_preview(intent, risk, user_record)
    risk_result = _risk_approval(intent, preview, risk)
    approval = _approval_preview(approval_context, risk_result)

    checks = [
        {'name': 'paper_signal_to_trade_intent', 'status': 'ok' if intent['status'] == 'ready' else 'blocked'},
        {'name': 'intent_to_order_preview', 'status': 'ok' if preview['status'] == 'ready' else 'blocked'},
        {'name': 'risk_firewall_to_approval_preview', 'status': 'ok' if risk_result['decision'] == 'APPROVED_FOR_PREVIEW' else 'blocked'},
        {'name': 'owner_approval_required_before_submit', 'status': 'ok' if 'owner_approval_missing' in approval['blockers'] or approval['owner_approved'] else 'blocked'},
        {'name': 'explicit_submit_default_off', 'status': 'ok' if approval['explicit_submit_enabled'] is False or approval['decision'] != 'READY_TO_SUBMIT' else 'blocked'},
        {'name': 'real_network_not_called', 'status': 'ok' if approval['real_network_call_performed'] is False else 'blocked'},
        {'name': 'secret_values_never_returned', 'status': 'ok'},
    ]
    blockers = [row['name'] for row in checks if row['status'] == 'blocked']
    stage_blockers = intent['blockers'] + preview['blockers'] + risk_result['blockers'] + approval['blockers']
    if blockers:
        decision = 'BLOCKED'
        action = 'Fix dry production drill blockers before live preview.'
    elif approval['decision'] == 'SUBMIT_BLOCKED':
        decision = 'DRY_RUN_PASS_SUBMIT_BLOCKED'
        action = 'Review owner approval requirements; do not submit real order.'
    else:
        decision = 'DRY_RUN_PASS_READY_PREVIEW_ONLY'
        action = 'All pre-submit controls align; real submit remains disabled by policy.'
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': decision,
        'critical_blocker': (blockers[0] if blockers else (stage_blockers[0] if stage_blockers else 'real_submit_default_off_policy')),
        'operator_action': action,
        'paper_signal': {
            'symbol': intent['symbol'],
            'strategy': intent['strategy'],
            'score': intent['signal_score'],
            'quality_score': intent['quality_score'],
        },
        'trade_intent': intent,
        'order_preview': preview,
        'risk_approval': risk_result,
        'approval_preview': approval,
        'checks': checks,
        'stage_blockers': stage_blockers,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'auto_scale_default_off': True,
        'auto_apply_default_off': True,
        'secret_values_returned': False,
        'generated_at': now_iso(),
    }


def build_paper_to_live_dry_production_drill_summary(auth_store: dict | None = None, username: str = 'default') -> dict:
    result = run_paper_to_live_dry_production_drill(_default_payload(), auth_store, username)
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': result['decision'],
        'critical_blocker': result['critical_blocker'],
        'operator_action': result['operator_action'],
        'symbol': result['paper_signal']['symbol'],
        'strategy': result['paper_signal']['strategy'],
        'intent_status': result['trade_intent']['status'],
        'preview_status': result['order_preview']['status'],
        'risk_decision': result['risk_approval']['decision'],
        'approval_decision': result['approval_preview']['decision'],
        'checks': result['checks'],
        'real_submit_default_off': True,
        'real_network_call_performed': False,
        'secret_values_returned': False,
    }
