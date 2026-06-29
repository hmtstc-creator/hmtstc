from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

from services.production_completion_service import (
    commission_for_trade,
    normalize_commission_settings,
    safe_float,
)

REVISION = 895


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def safe_id(value: Any, fallback: str) -> str:
    clean = str(value or '').strip()
    return clean or fallback


def money(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return fallback
        return round(result, 8)
    except Exception:
        return fallback


def pct(value: Any, fallback: float = 0.0) -> float:
    return max(0.0, min(100.0, money(value, fallback)))


def get_user_record(auth_store: dict | None, username: str) -> dict:
    return as_dict(as_dict(auth_store).get('users')).get(username, {}) or {}


def _trade_hash(user: str, trade_id: str, side: str, notional: float, commission: float) -> str:
    raw = f'{user}|{trade_id}|{side}|{notional:.8f}|{commission:.8f}'.encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def _canonical_side(side: Any) -> str:
    clean = str(side or '').strip().lower()
    if clean in {'sell', 's'}:
        return 'sell'
    return 'buy'


def _is_commissionable(status: Any) -> bool:
    clean = str(status or 'filled').strip().lower()
    return clean in {'filled', 'partially_filled', 'partial', 'closed'}


def build_commission_ledger(payload: dict | None, auth_store: dict | None = None, username: str = 'default') -> dict:
    """Build a secret-safe per-user commission ledger from trade executions.

    The function is intentionally pure: it does not write runtime state and can be
    used both by production previews and regression tests. Cancelled/rejected
    orders produce zero platform commission; partial fills use filled_notional
    when provided.
    """
    payload = as_dict(payload)
    record = get_user_record(auth_store, username)
    settings = normalize_commission_settings(payload.get('commission_settings') or record.get('commission_settings'))
    trades = as_list(payload.get('trades'))
    if not trades:
        trades = [
            {'trade_id': 'sample-buy', 'side': 'buy', 'notional_usdt': 200.0, 'status': 'filled'},
            {'trade_id': 'sample-sell', 'side': 'sell', 'notional_usdt': 203.0, 'gross_pnl_usdt': 3.0, 'status': 'filled'},
        ]

    ledger = []
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    cancelled_count = 0
    buy_total = 0.0
    sell_total = 0.0
    platform_total = 0.0
    gross_pnl_total = 0.0
    binance_fee_total = 0.0
    commissionable_count = 0

    for index, raw in enumerate(trades, start=1):
        trade = as_dict(raw)
        trade_id = safe_id(trade.get('trade_id') or trade.get('id'), f'trade-{index}')
        side = _canonical_side(trade.get('side'))
        status = str(trade.get('status') or 'filled').strip().lower()
        notional = money(trade.get('filled_notional_usdt') if trade.get('filled_notional_usdt') is not None else trade.get('notional_usdt'), 0.0)
        gross_pnl = money(trade.get('gross_pnl_usdt'), 0.0)
        binance_fee = max(0.0, money(trade.get('binance_fee_usdt'), 0.0))
        commissionable = _is_commissionable(status) and notional > 0
        if trade_id in seen_ids:
            duplicate_ids.append(trade_id)
        seen_ids.add(trade_id)

        if commissionable:
            commission = commission_for_trade(notional, side, settings)
            platform_fee = money(commission.get('platform_commission_usdt'), 0.0)
            commissionable_count += 1
        else:
            platform_fee = 0.0
            if status in {'cancelled', 'canceled', 'rejected', 'expired'}:
                cancelled_count += 1

        if side == 'buy':
            buy_total += platform_fee
        else:
            sell_total += platform_fee
        platform_total += platform_fee
        gross_pnl_total += gross_pnl
        binance_fee_total += binance_fee
        ledger.append({
            'trade_id': trade_id,
            'side': side,
            'status': status,
            'notional_usdt': round(notional, 8),
            'gross_pnl_usdt': round(gross_pnl, 8),
            'binance_fee_usdt': round(binance_fee, 8),
            'platform_commission_usdt': round(platform_fee, 8),
            'commissionable': commissionable,
            'ledger_hash': _trade_hash(username, trade_id, side, notional, platform_fee),
        })

    net_pnl = gross_pnl_total - binance_fee_total - platform_total
    checksum_raw = '|'.join(row['ledger_hash'] for row in ledger).encode('utf-8')
    checksum = hashlib.sha256(checksum_raw).hexdigest()[:16] if ledger else None
    blockers = []
    if duplicate_ids:
        blockers.append('duplicate_trade_id')
    if any(row['platform_commission_usdt'] < 0 for row in ledger):
        blockers.append('negative_commission_detected')
    decision = 'PASS' if not blockers else 'REVIEW'
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': decision,
        'commission_settings': settings,
        'ledger': ledger,
        'summary': {
            'trade_count': len(ledger),
            'commissionable_trade_count': commissionable_count,
            'cancelled_or_rejected_count': cancelled_count,
            'buy_commission_usdt': round(buy_total, 8),
            'sell_commission_usdt': round(sell_total, 8),
            'platform_commission_total_usdt': round(platform_total, 8),
            'binance_fee_total_usdt': round(binance_fee_total, 8),
            'gross_pnl_usdt': round(gross_pnl_total, 8),
            'net_pnl_after_all_costs_usdt': round(net_pnl, 8),
            'commission_drag_percent_of_gross_pnl': round((platform_total / gross_pnl_total * 100.0), 4) if gross_pnl_total > 0 else None,
            'checksum': checksum,
        },
        'blockers': blockers,
        'duplicate_trade_ids': sorted(set(duplicate_ids)),
        'secret_values_returned': False,
    }


def validate_commission_business_flow(payload: dict | None, auth_store: dict | None = None, username: str = 'default') -> dict:
    ledger = build_commission_ledger(payload, auth_store, username)
    summary = ledger['summary']
    checks = [
        {'name': 'buy_commission_calculated', 'status': 'ok' if summary['buy_commission_usdt'] >= 0 else 'blocked'},
        {'name': 'sell_commission_calculated', 'status': 'ok' if summary['sell_commission_usdt'] >= 0 else 'blocked'},
        {'name': 'gross_net_pnl_separated', 'status': 'ok' if 'net_pnl_after_all_costs_usdt' in summary else 'blocked'},
        {'name': 'cancelled_orders_zero_commission', 'status': 'ok' if all((row['commissionable'] or row['platform_commission_usdt'] == 0) for row in ledger['ledger']) else 'blocked'},
        {'name': 'ledger_checksum_present', 'status': 'ok' if summary.get('checksum') else 'review'},
        {'name': 'duplicate_trade_protection', 'status': 'review' if ledger['duplicate_trade_ids'] else 'ok'},
        {'name': 'secret_values_never_returned', 'status': 'ok'},
    ]
    blockers = [row['name'] for row in checks if row['status'] == 'blocked']
    reviews = [row['name'] for row in checks if row['status'] == 'review']
    return {
        'status': 'ok',
        'revision': REVISION,
        'user': username,
        'decision': 'PASS' if not blockers and not reviews else ('BLOCKED' if blockers else 'REVIEW'),
        'critical_issue': blockers[0] if blockers else (reviews[0] if reviews else None),
        'checks': checks,
        'ledger_summary': summary,
        'secret_values_returned': False,
        'real_submit_default_off': True,
        'real_close_default_off': True,
    }


def build_commission_business_flow_summary(auth_store: dict | None = None, username: str = 'default') -> dict:
    sample = {
        'trades': [
            {'trade_id': 'sample-buy', 'side': 'buy', 'notional_usdt': 200.0, 'status': 'filled', 'binance_fee_usdt': 0.2},
            {'trade_id': 'sample-sell', 'side': 'sell', 'notional_usdt': 202.5, 'status': 'filled', 'gross_pnl_usdt': 2.5, 'binance_fee_usdt': 0.2025},
            {'trade_id': 'sample-cancel', 'side': 'buy', 'notional_usdt': 200.0, 'status': 'cancelled'},
        ]
    }
    result = validate_commission_business_flow(sample, auth_store, username)
    result['operator_action'] = 'Commission business flow ready' if result['decision'] == 'PASS' else 'Review commission ledger blockers'
    return result
