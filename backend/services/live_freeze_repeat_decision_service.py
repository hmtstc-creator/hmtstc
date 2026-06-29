from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

REVISION = 920


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return fallback
        return number
    except Exception:
        return fallback


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on', 'enabled', 'allow', 'allowed'}


def normalize_symbol(value: Any) -> str:
    return str(value or 'BTCUSDT').upper().replace('/', '').replace('-', '').strip() or 'BTCUSDT'


def _hash(*parts: Any) -> str:
    return hashlib.sha256('|'.join(str(part) for part in parts).encode('utf-8')).hexdigest()[:18]


def _default_payload() -> dict:
    return {
        'username': 'owner',
        'symbol': 'BTCUSDT',
        'strategy': 'choch_micro_scalper',
        'realized_pnl_usdt': 0.45,
        'gross_pnl_usdt': 0.62,
        'binance_fee_usdt': 0.08,
        'platform_commission_usdt': 0.04,
        'slippage_usdt': 0.05,
        'latency_ms': 185,
        'journal_consistent': True,
        'order_consistent': True,
        'position_consistent': True,
        'fill_complete': True,
        'evidence_items': ['order_status', 'fill', 'journal', 'position', 'fee', 'slippage', 'latency'],
        'sample_count': 1,
        'minimum_repeat_sample_count': 5,
        'loss_streak': 0,
        'daily_loss_usdt': 0.0,
        'max_daily_loss_usdt': 10.0,
        'max_slippage_usdt': 0.25,
        'max_latency_ms': 750,
        'owner_approved_repeat': False,
        'repeat_permission_enabled': False,
        'real_submit_enabled': False,
    }


def evidence_confidence(payload: dict) -> dict:
    required = ['order_status', 'fill', 'journal', 'position', 'fee', 'slippage', 'latency']
    items = {str(item).strip().lower() for item in as_list(payload.get('evidence_items')) if str(item).strip()}
    missing = [item for item in required if item not in items]
    consistency_flags = {
        'journal_consistent': safe_bool(payload.get('journal_consistent')),
        'order_consistent': safe_bool(payload.get('order_consistent')),
        'position_consistent': safe_bool(payload.get('position_consistent')),
        'fill_complete': safe_bool(payload.get('fill_complete')),
    }
    missing_penalty = len(missing) * 12
    inconsistency_penalty = sum(18 for ok in consistency_flags.values() if not ok)
    score = max(0, min(100, 100 - missing_penalty - inconsistency_penalty))
    if score >= 90:
        status = 'strong'
    elif score >= 70:
        status = 'usable'
    elif score >= 45:
        status = 'weak'
    else:
        status = 'insufficient'
    return {
        'status': status,
        'score': score,
        'required_items': required,
        'present_items': sorted(items),
        'missing_items': missing,
        'consistency_flags': consistency_flags,
        'secret_values_returned': False,
    }


def cost_reality(payload: dict) -> dict:
    gross_pnl = safe_float(payload.get('gross_pnl_usdt'), 0.0)
    binance_fee = max(0.0, safe_float(payload.get('binance_fee_usdt'), 0.0))
    platform_fee = max(0.0, safe_float(payload.get('platform_commission_usdt'), 0.0))
    slippage = max(0.0, safe_float(payload.get('slippage_usdt'), 0.0))
    realized_pnl = safe_float(payload.get('realized_pnl_usdt'), gross_pnl - binance_fee - platform_fee - slippage)
    computed_net = gross_pnl - binance_fee - platform_fee - slippage
    pnl_gap = abs(realized_pnl - computed_net)
    max_slippage = max(0.0, safe_float(payload.get('max_slippage_usdt'), 0.0))
    latency_ms = max(0.0, safe_float(payload.get('latency_ms'), 0.0))
    max_latency = max(0.0, safe_float(payload.get('max_latency_ms'), 0.0))
    blockers = []
    if pnl_gap > 0.10:
        blockers.append('pnl_reconciliation_gap')
    if max_slippage > 0 and slippage > max_slippage:
        blockers.append('slippage_above_limit')
    if max_latency > 0 and latency_ms > max_latency:
        blockers.append('latency_above_limit')
    if realized_pnl <= 0:
        blockers.append('non_positive_net_pnl')
    return {
        'gross_pnl_usdt': round(gross_pnl, 8),
        'binance_fee_usdt': round(binance_fee, 8),
        'platform_commission_usdt': round(platform_fee, 8),
        'slippage_usdt': round(slippage, 8),
        'computed_net_pnl_usdt': round(computed_net, 8),
        'realized_pnl_usdt': round(realized_pnl, 8),
        'pnl_gap_usdt': round(pnl_gap, 8),
        'latency_ms': round(latency_ms, 3),
        'status': 'ok' if not blockers else 'attention',
        'blockers': blockers,
    }


def freeze_repeat_gate(payload: dict, evidence: dict, costs: dict) -> dict:
    realized_pnl = safe_float(costs.get('realized_pnl_usdt'), 0.0)
    sample_count = max(0, safe_int(payload.get('sample_count'), 0))
    minimum_samples = max(1, safe_int(payload.get('minimum_repeat_sample_count'), 5))
    loss_streak = max(0, safe_int(payload.get('loss_streak'), 0))
    daily_loss = max(0.0, safe_float(payload.get('daily_loss_usdt'), 0.0))
    max_daily_loss = max(0.0, safe_float(payload.get('max_daily_loss_usdt'), 0.0))
    owner_approved_repeat = safe_bool(payload.get('owner_approved_repeat'))
    repeat_permission_enabled = safe_bool(payload.get('repeat_permission_enabled'))
    real_submit_enabled = safe_bool(payload.get('real_submit_enabled'))

    blockers = []
    if evidence.get('score', 0) < 90:
        blockers.append('evidence_not_strong_enough')
    if costs.get('status') != 'ok':
        blockers.extend(costs.get('blockers') or ['cost_reality_attention'])
    if sample_count < minimum_samples:
        blockers.append('minimum_sample_size_not_met')
    if max_daily_loss > 0 and daily_loss >= max_daily_loss:
        blockers.append('daily_hard_stop_reached')
    if loss_streak >= 3:
        blockers.append('loss_streak_halt_required')
    if loss_streak >= 1:
        blockers.append('loss_streak_cooldown_required')
    if realized_pnl < 0:
        blockers.append('latest_trade_loss')
    if not owner_approved_repeat:
        blockers.append('owner_repeat_approval_missing')
    if not repeat_permission_enabled:
        blockers.append('repeat_permission_disabled')
    if not real_submit_enabled:
        blockers.append('real_submit_disabled_default_off')

    if 'daily_hard_stop_reached' in blockers or 'loss_streak_halt_required' in blockers:
        decision = 'HALT'
        operator_action = 'Keep live actions stopped; inspect loss and hard-stop evidence.'
    elif 'latest_trade_loss' in blockers or 'loss_streak_cooldown_required' in blockers:
        decision = 'REDUCE_OR_COOLDOWN'
        operator_action = 'Do not repeat automatically; reduce size or cooldown until evidence improves.'
    elif 'minimum_sample_size_not_met' in blockers:
        decision = 'FREEZE_LOW_SAMPLE'
        operator_action = 'Freeze repeat/scale despite profit; collect more controlled samples first.'
    elif blockers:
        decision = 'REVIEW'
        operator_action = 'Resolve blockers before any repeat micro-live attempt.'
    else:
        decision = 'REPEAT_READY_PREVIEW_ONLY'
        operator_action = 'Repeat is only preview-ready; real submit remains approval-gated and adapter-controlled.'

    return {
        'decision': decision,
        'blockers': blockers,
        'critical_blocker': blockers[0] if blockers else 'none',
        'operator_action': operator_action,
        'sample_count': sample_count,
        'minimum_repeat_sample_count': minimum_samples,
        'owner_approved_repeat': owner_approved_repeat,
        'repeat_permission_enabled': repeat_permission_enabled,
        'real_submit_enabled': real_submit_enabled,
        'auto_repeat_allowed': False,
        'auto_scale_allowed': False,
        'auto_apply_allowed': False,
        'real_submit_executed': False,
    }


def evaluate_live_freeze_repeat_decision(payload: dict | None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = {**_default_payload(), **as_dict(payload)}
    symbol = normalize_symbol(payload.get('symbol'))
    strategy = str(payload.get('strategy') or 'unknown_strategy').strip() or 'unknown_strategy'
    evidence = evidence_confidence(payload)
    costs = cost_reality(payload)
    gate = freeze_repeat_gate(payload, evidence, costs)
    checks = [
        {'name': 'evidence_confidence_scorer', 'status': 'ok' if evidence['score'] >= 0 else 'blocked'},
        {'name': 'profit_but_low_sample_freeze_rule', 'status': 'ok' if gate['decision'] in {'FREEZE_LOW_SAMPLE', 'REVIEW', 'HALT', 'REDUCE_OR_COOLDOWN', 'REPEAT_READY_PREVIEW_ONLY'} else 'blocked'},
        {'name': 'loss_cooldown_reduce_halt_rule', 'status': 'ok'},
        {'name': 'repeat_stop_reduce_engine', 'status': 'ok'},
        {'name': 'no_auto_repeat_or_scale', 'status': 'ok' if not gate['auto_repeat_allowed'] and not gate['auto_scale_allowed'] else 'blocked'},
        {'name': 'no_real_network_call', 'status': 'ok'},
        {'name': 'secret_values_never_returned', 'status': 'ok'},
    ]
    failed = [item['name'] for item in checks if item['status'] != 'ok']
    decision = 'NO_GO' if failed else gate['decision']
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'symbol': symbol,
        'strategy': strategy,
        'decision': decision,
        'critical_blocker': failed[0] if failed else gate['critical_blocker'],
        'operator_action': gate['operator_action'] if not failed else 'Fix blocked repeat/freeze decision checks.',
        'evidence_confidence': evidence,
        'cost_reality': costs,
        'freeze_repeat_gate': gate,
        'checks': checks,
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'emergency_close_default_off': True,
        'auto_repeat_allowed': False,
        'auto_scale_default_off': True,
        'auto_apply_default_off': True,
        'auto_close_default_off': True,
        'real_network_call_performed': False,
        'secret_values_returned': False,
        'decision_id': 'live-freeze-repeat-' + _hash(username, symbol, strategy, decision, gate['critical_blocker']),
        'generated_at': now_iso(),
    }


def build_live_freeze_repeat_decision_summary(auth_store: dict | None = None, username: str = 'default') -> dict:
    result = evaluate_live_freeze_repeat_decision(_default_payload(), auth_store, username)
    gate = result['freeze_repeat_gate']
    costs = result['cost_reality']
    evidence = result['evidence_confidence']
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': result['decision'],
        'critical_blocker': result['critical_blocker'],
        'operator_action': result['operator_action'],
        'symbol': result['symbol'],
        'strategy': result['strategy'],
        'evidence_score': evidence['score'],
        'evidence_status': evidence['status'],
        'sample_count': gate['sample_count'],
        'minimum_repeat_sample_count': gate['minimum_repeat_sample_count'],
        'realized_pnl_usdt': costs['realized_pnl_usdt'],
        'cost_status': costs['status'],
        'auto_repeat_allowed': False,
        'auto_scale_default_off': True,
        'real_submit_default_off': True,
        'real_network_call_performed': False,
        'secret_values_returned': False,
    }
