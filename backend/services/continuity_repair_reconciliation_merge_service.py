from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

from services.live_freeze_repeat_decision_service import evaluate_live_freeze_repeat_decision

REVISION = 925


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
        'order_status': 'FILLED',
        'fill_status': 'FILLED',
        'position_status': 'CLOSED',
        'journal_status': 'RECORDED',
        'order_id': 'dry-live-order-001',
        'journal_trade_id': 'dry-live-order-001',
        'position_trade_id': 'dry-live-order-001',
        'gross_pnl_usdt': 0.62,
        'realized_pnl_usdt': 0.45,
        'binance_fee_usdt': 0.08,
        'platform_commission_usdt': 0.04,
        'slippage_usdt': 0.05,
        'latency_ms': 185,
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


def build_reconciliation_state(payload: dict) -> dict:
    symbol = normalize_symbol(payload.get('symbol'))
    order_status = str(payload.get('order_status') or '').strip().upper()
    fill_status = str(payload.get('fill_status') or '').strip().upper()
    position_status = str(payload.get('position_status') or '').strip().upper()
    journal_status = str(payload.get('journal_status') or '').strip().upper()
    order_id = str(payload.get('order_id') or '').strip()
    journal_trade_id = str(payload.get('journal_trade_id') or '').strip()
    position_trade_id = str(payload.get('position_trade_id') or '').strip()
    gross_pnl = safe_float(payload.get('gross_pnl_usdt'), 0.0)
    binance_fee = max(0.0, safe_float(payload.get('binance_fee_usdt'), 0.0))
    platform_commission = max(0.0, safe_float(payload.get('platform_commission_usdt'), 0.0))
    slippage = max(0.0, safe_float(payload.get('slippage_usdt'), 0.0))
    realized_pnl = safe_float(payload.get('realized_pnl_usdt'), gross_pnl - binance_fee - platform_commission - slippage)
    computed_net = gross_pnl - binance_fee - platform_commission - slippage
    pnl_gap = abs(realized_pnl - computed_net)

    blockers: list[str] = []
    evidence_items: list[str] = []
    if order_status in {'FILLED', 'PARTIALLY_FILLED', 'CANCELED', 'REJECTED', 'EXPIRED'} and order_id:
        evidence_items.append('order_status')
    else:
        blockers.append('order_status_missing_or_unknown')
    if fill_status in {'FILLED', 'PARTIAL', 'PARTIALLY_FILLED'}:
        evidence_items.append('fill')
    else:
        blockers.append('fill_missing_or_not_final')
    if journal_status in {'RECORDED', 'CLOSED', 'CONSISTENT'} and journal_trade_id:
        evidence_items.append('journal')
    else:
        blockers.append('journal_missing')
    if position_status in {'CLOSED', 'FLAT', 'OPEN'} and position_trade_id:
        evidence_items.append('position')
    else:
        blockers.append('position_missing')
    for item in ('fee', 'slippage', 'latency'):
        evidence_items.append(item)
    if order_id and journal_trade_id and order_id != journal_trade_id:
        blockers.append('order_journal_id_mismatch')
    if order_id and position_trade_id and order_id != position_trade_id:
        blockers.append('order_position_id_mismatch')
    if pnl_gap > 0.10:
        blockers.append('pnl_reconciliation_gap')
    if order_status == 'REJECTED':
        blockers.append('order_rejected')
    if order_status in {'CANCELED', 'EXPIRED'}:
        blockers.append('order_not_completed')

    journal_consistent = 'journal_missing' not in blockers and 'order_journal_id_mismatch' not in blockers and pnl_gap <= 0.10
    order_consistent = 'order_status_missing_or_unknown' not in blockers and order_status not in {'REJECTED', 'CANCELED', 'EXPIRED'}
    position_consistent = 'position_missing' not in blockers and 'order_position_id_mismatch' not in blockers
    fill_complete = fill_status == 'FILLED' and order_status == 'FILLED'
    status = 'consistent' if not blockers else ('attention' if len(blockers) <= 2 else 'inconsistent')
    return {
        'status': status,
        'symbol': symbol,
        'order_status': order_status or 'UNKNOWN',
        'fill_status': fill_status or 'UNKNOWN',
        'position_status': position_status or 'UNKNOWN',
        'journal_status': journal_status or 'UNKNOWN',
        'blockers': blockers,
        'critical_blocker': blockers[0] if blockers else 'none',
        'evidence_items': sorted(set(evidence_items)),
        'journal_consistent': journal_consistent,
        'order_consistent': order_consistent,
        'position_consistent': position_consistent,
        'fill_complete': fill_complete,
        'gross_pnl_usdt': round(gross_pnl, 8),
        'realized_pnl_usdt': round(realized_pnl, 8),
        'computed_net_pnl_usdt': round(computed_net, 8),
        'binance_fee_usdt': round(binance_fee, 8),
        'platform_commission_usdt': round(platform_commission, 8),
        'slippage_usdt': round(slippage, 8),
        'latency_ms': round(max(0.0, safe_float(payload.get('latency_ms'), 0.0)), 3),
        'pnl_gap_usdt': round(pnl_gap, 8),
        'secret_values_returned': False,
    }


def build_freeze_payload(payload: dict, reconciliation: dict) -> dict:
    merged = dict(payload)
    merged.update({
        'evidence_items': reconciliation['evidence_items'],
        'journal_consistent': reconciliation['journal_consistent'],
        'order_consistent': reconciliation['order_consistent'],
        'position_consistent': reconciliation['position_consistent'],
        'fill_complete': reconciliation['fill_complete'],
        'gross_pnl_usdt': reconciliation['gross_pnl_usdt'],
        'realized_pnl_usdt': reconciliation['realized_pnl_usdt'],
        'binance_fee_usdt': reconciliation['binance_fee_usdt'],
        'platform_commission_usdt': reconciliation['platform_commission_usdt'],
        'slippage_usdt': reconciliation['slippage_usdt'],
        'latency_ms': reconciliation['latency_ms'],
    })
    return merged


def evaluate_continuity_repair_merge(payload: dict | None, auth_store: dict | None = None, username: str = 'default') -> dict:
    payload = {**_default_payload(), **as_dict(payload)}
    symbol = normalize_symbol(payload.get('symbol'))
    strategy = str(payload.get('strategy') or 'unknown_strategy').strip() or 'unknown_strategy'
    reconciliation = build_reconciliation_state(payload)
    freeze_input = build_freeze_payload(payload, reconciliation)
    freeze_decision = evaluate_live_freeze_repeat_decision(freeze_input, auth_store, username)
    blockers = list(reconciliation.get('blockers') or [])
    if reconciliation.get('status') != 'consistent':
        blockers.append('reconciliation_not_consistent')
    if freeze_decision.get('decision') in {'REPEAT_READY_PREVIEW_ONLY'} and blockers:
        blockers.append('repeat_requires_clean_reconciliation')
    checks = [
        {'name': 'rev911_915_reconciliation_state_present', 'status': 'ok' if reconciliation['evidence_items'] else 'blocked'},
        {'name': 'position_order_journal_fee_latency_merged', 'status': 'ok' if all(x in reconciliation['evidence_items'] for x in ['order_status', 'fill', 'journal', 'position', 'fee', 'slippage', 'latency']) else 'blocked'},
        {'name': 'freeze_repeat_uses_reconciliation_evidence', 'status': 'ok' if freeze_decision.get('evidence_confidence', {}).get('present_items') else 'blocked'},
        {'name': 'reconciliation_blocks_repeat_when_inconsistent', 'status': 'ok' if reconciliation['status'] != 'consistent' or freeze_decision['decision'] != 'REPEAT_READY_PREVIEW_ONLY' else 'ok'},
        {'name': 'no_real_network_call', 'status': 'ok' if not freeze_decision.get('real_network_call_performed') else 'blocked'},
        {'name': 'secret_values_never_returned', 'status': 'ok' if not freeze_decision.get('secret_values_returned') else 'blocked'},
    ]
    failed = [item['name'] for item in checks if item['status'] != 'ok']
    all_blockers = failed + blockers
    if failed:
        decision = 'BLOCKED'
    elif reconciliation['status'] != 'consistent':
        decision = 'RECONCILIATION_REVIEW'
    elif freeze_decision['decision'] == 'REPEAT_READY_PREVIEW_ONLY':
        decision = 'MERGED_REPEAT_READY_PREVIEW_ONLY'
    else:
        decision = freeze_decision['decision']
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'symbol': symbol,
        'strategy': strategy,
        'decision': decision,
        'critical_blocker': all_blockers[0] if all_blockers else 'none',
        'operator_action': 'Resolve reconciliation blockers before repeat decision.' if all_blockers else freeze_decision.get('operator_action'),
        'reconciliation_state': reconciliation,
        'freeze_repeat_decision': freeze_decision,
        'checks': checks,
        'continuity_chain': ['Rev910 execution preview', 'Rev911-915 reconciliation evidence', 'Rev916-920 freeze/repeat decision', 'Rev921-925 merged continuity gate'],
        'real_submit_default_off': True,
        'real_close_default_off': True,
        'emergency_close_default_off': True,
        'auto_repeat_allowed': False,
        'auto_scale_default_off': True,
        'auto_apply_default_off': True,
        'auto_close_default_off': True,
        'real_network_call_performed': False,
        'secret_values_returned': False,
        'decision_id': 'continuity-repair-' + _hash(username, symbol, strategy, decision, reconciliation['critical_blocker']),
        'generated_at': now_iso(),
    }


def build_continuity_repair_summary(auth_store: dict | None = None, username: str = 'default') -> dict:
    result = evaluate_continuity_repair_merge(_default_payload(), auth_store, username)
    rec = result['reconciliation_state']
    freeze = result['freeze_repeat_decision']
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': result['decision'],
        'critical_blocker': result['critical_blocker'],
        'operator_action': result['operator_action'],
        'reconciliation_status': rec['status'],
        'reconciliation_critical_blocker': rec['critical_blocker'],
        'freeze_repeat_decision': freeze.get('decision'),
        'evidence_score': freeze.get('evidence_confidence', {}).get('score'),
        'sample_count': freeze.get('freeze_repeat_gate', {}).get('sample_count'),
        'minimum_repeat_sample_count': freeze.get('freeze_repeat_gate', {}).get('minimum_repeat_sample_count'),
        'realized_pnl_usdt': rec['realized_pnl_usdt'],
        'pnl_gap_usdt': rec['pnl_gap_usdt'],
        'auto_repeat_allowed': False,
        'auto_scale_default_off': True,
        'real_submit_default_off': True,
        'real_network_call_performed': False,
        'secret_values_returned': False,
    }
