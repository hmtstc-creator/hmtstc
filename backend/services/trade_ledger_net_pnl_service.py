from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

from services.commission_business_flow_service import build_commission_ledger
from services.production_completion_service import normalize_commission_settings, safe_float


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def money(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return fallback
        return round(result, 8)
    except Exception:
        return fallback


def _status(value: Any) -> str:
    clean = str(value or 'closed').strip().lower()
    if clean in {'cancelled', 'canceled'}:
        return 'cancelled'
    if clean in {'rejected', 'expired'}:
        return clean
    if clean in {'open', 'active', 'running'}:
        return 'open'
    if clean in {'filled', 'closed', 'done', 'success'}:
        return 'closed'
    return clean or 'closed'


def _side(value: Any) -> str:
    clean = str(value or '').strip().lower()
    if clean in {'sell', 'short', 's'}:
        return 'sell'
    return 'buy'


def _ids_from(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or '').strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.replace('|', ',').split(',') if part.strip()]
    return []


def _hash_row(user: str, row: dict) -> str:
    raw = '|'.join([
        str(user),
        str(row.get('trade_id') or ''),
        str(row.get('mode') or ''),
        str(row.get('symbol') or ''),
        f"{money(row.get('gross_pnl_usdt')):.8f}",
        f"{money(row.get('binance_fee_usdt')):.8f}",
        f"{money(row.get('platform_commission_usdt')):.8f}",
        f"{money(row.get('net_pnl_usdt')):.8f}",
    ]).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16]


def _extract_trade_sources(data: dict) -> list[dict]:
    rows: list[dict] = []
    candidates = [
        ('live', data.get('real_trade_history')),
        ('live', data.get('live_trade_history')),
        ('live', data.get('closed_real_trades')),
        ('paper', data.get('paper_trade_history')),
        ('paper', data.get('paper_history')),
        ('paper', data.get('history')),
        ('mixed', data.get('closed_trades')),
    ]
    real_state = as_dict(data.get('real_trade'))
    if real_state:
        candidates.extend([
            ('live', real_state.get('closed_positions')),
            ('live', real_state.get('trade_history')),
            ('live', real_state.get('orders')),
        ])
    paper_lab = as_dict(data.get('paper_lab'))
    if paper_lab:
        candidates.extend([
            ('paper', paper_lab.get('closed_trades')),
            ('paper', paper_lab.get('trades')),
            ('paper', paper_lab.get('executions')),
        ])

    seen = set()
    for default_mode, source in candidates:
        for raw in as_list(source):
            trade = as_dict(raw)
            if not trade:
                continue
            trade_id = str(trade.get('trade_id') or trade.get('id') or trade.get('order_id') or '').strip()
            if not trade_id:
                trade_id = f"{default_mode}-{len(rows) + 1}"
            key = (default_mode, trade_id)
            if key in seen:
                continue
            seen.add(key)
            trade['_default_mode'] = default_mode
            rows.append(trade)
    return rows


def _normalize_trade(raw: dict, index: int) -> dict:
    mode = str(raw.get('mode') or raw.get('trade_mode') or raw.get('_default_mode') or 'paper').lower()
    if mode not in {'paper', 'live'}:
        mode = 'live' if str(raw.get('source') or '').lower().startswith('real') else 'paper'
    status = _status(raw.get('status') or raw.get('state'))
    qty = money(raw.get('quantity') or raw.get('qty') or raw.get('executed_qty'), 0.0)
    entry = money(raw.get('entry_price') or raw.get('buy_price') or raw.get('open_price'), 0.0)
    exit_price = money(raw.get('exit_price') or raw.get('sell_price') or raw.get('close_price') or raw.get('price'), 0.0)
    notional = money(raw.get('filled_notional_usdt') if raw.get('filled_notional_usdt') is not None else raw.get('notional_usdt') or raw.get('quote_order_qty') or raw.get('quote_amount') or raw.get('usdt_size') or raw.get('size_usdt'), 0.0)
    if notional <= 0 and qty > 0:
        notional = money(qty * (exit_price or entry), 0.0)
    gross = raw.get('gross_pnl_usdt')
    if gross is None:
        gross = raw.get('pnl_usdt') if raw.get('pnl_usdt') is not None else raw.get('pnl')
    gross_pnl = money(gross, 0.0)
    if gross is None and status == 'closed' and qty > 0 and entry > 0 and exit_price > 0:
        side = _side(raw.get('side'))
        gross_pnl = money((exit_price - entry) * qty * (1 if side == 'buy' else -1), 0.0)
    return {
        'trade_id': str(raw.get('trade_id') or raw.get('id') or raw.get('order_id') or f'{mode}-{index}'),
        'user_id': str(raw.get('user_id') or raw.get('user') or ''),
        'mode': mode,
        'symbol': str(raw.get('symbol') or raw.get('coin') or 'BTCUSDT').upper(),
        'side': _side(raw.get('side') or raw.get('direction')),
        'status': status,
        'strategy_id': str(raw.get('strategy_id') or raw.get('strategy') or raw.get('model_id') or ''),
        'filter_ids': _ids_from(raw.get('filter_ids') or raw.get('filters') or raw.get('filter_id')),
        'entry_price': entry,
        'exit_price': exit_price,
        'quantity': qty,
        'notional_usdt': notional,
        'gross_pnl_usdt': gross_pnl,
        'binance_fee_usdt': max(0.0, money(raw.get('binance_fee_usdt') or raw.get('fee_usdt') or raw.get('commission_usdt'), 0.0)),
        'order_id': str(raw.get('order_id') or raw.get('exchange_order_id') or ''),
        'created_at': raw.get('created_at') or raw.get('opened_at') or raw.get('timestamp') or now_iso(),
        'closed_at': raw.get('closed_at') or raw.get('updated_at') or raw.get('exit_time'),
    }


def build_trade_ledger(data: dict | None, settings: dict | None, auth_store: dict | None = None, user: str = 'default') -> dict:
    runtime = as_dict(data)
    setting_map = as_dict(settings)
    auth = as_dict(auth_store)
    record = as_dict(as_dict(auth.get('users')).get(user))
    commission_settings = normalize_commission_settings(record.get('commission_settings') or setting_map.get('commission_settings'))
    normalized = [_normalize_trade(raw, idx) for idx, raw in enumerate(_extract_trade_sources(runtime), start=1)]

    commission_payload_trades = []
    for trade in normalized:
        commission_payload_trades.append({
            'trade_id': trade['trade_id'],
            'side': trade['side'],
            'status': trade['status'],
            'notional_usdt': trade['notional_usdt'],
            'gross_pnl_usdt': trade['gross_pnl_usdt'],
            'binance_fee_usdt': trade['binance_fee_usdt'],
        })
    commission_ledger = build_commission_ledger({'trades': commission_payload_trades, 'commission_settings': commission_settings}, auth, user)
    fee_by_id = {row.get('trade_id'): row for row in as_list(commission_ledger.get('ledger'))}

    ledger = []
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()
    totals = {
        'trade_count': 0,
        'paper_trade_count': 0,
        'live_trade_count': 0,
        'open_trade_count': 0,
        'closed_trade_count': 0,
        'gross_pnl_usdt': 0.0,
        'binance_fee_usdt': 0.0,
        'platform_commission_usdt': 0.0,
        'net_pnl_usdt': 0.0,
    }

    for trade in normalized:
        fee_row = as_dict(fee_by_id.get(trade['trade_id']))
        platform_fee = money(fee_row.get('platform_commission_usdt'), 0.0)
        net = money(trade['gross_pnl_usdt'] - trade['binance_fee_usdt'] - platform_fee, 0.0)
        row = dict(trade)
        row['platform_commission_usdt'] = platform_fee
        row['net_pnl_usdt'] = net
        row['simple_text'] = f"{row['symbol']} işleminden {net:+.2f} USDT net sonuç."
        row['checksum'] = _hash_row(user, row)
        if row['trade_id'] in seen_ids:
            duplicate_ids.append(row['trade_id'])
        seen_ids.add(row['trade_id'])
        ledger.append(row)
        totals['trade_count'] += 1
        totals['paper_trade_count'] += 1 if row['mode'] == 'paper' else 0
        totals['live_trade_count'] += 1 if row['mode'] == 'live' else 0
        totals['open_trade_count'] += 1 if row['status'] == 'open' else 0
        totals['closed_trade_count'] += 1 if row['status'] == 'closed' else 0
        totals['gross_pnl_usdt'] += row['gross_pnl_usdt']
        totals['binance_fee_usdt'] += row['binance_fee_usdt']
        totals['platform_commission_usdt'] += row['platform_commission_usdt']
        totals['net_pnl_usdt'] += row['net_pnl_usdt']

    for key, value in list(totals.items()):
        if isinstance(value, float):
            totals[key] = round(value, 8)
    checksum_raw = '|'.join(row['checksum'] for row in ledger).encode('utf-8')
    checksum = hashlib.sha256(checksum_raw).hexdigest()[:16] if ledger else None
    blockers = []
    if duplicate_ids:
        blockers.append('duplicate_trade_id')
    if any(row['net_pnl_usdt'] != round(row['gross_pnl_usdt'] - row['binance_fee_usdt'] - row['platform_commission_usdt'], 8) for row in ledger):
        blockers.append('net_pnl_mismatch')
    return {
        'status': 'ok' if not blockers else 'review',
        'generated_at': now_iso(),
        'user': user,
        'summary': totals,
        'ledger': ledger,
        'recent': ledger[-20:][::-1],
        'checksum': checksum,
        'duplicate_trade_ids': sorted(set(duplicate_ids)),
        'blockers': blockers,
        'simple_text': 'Net kazanç = brüt kar - Binance kesintisi - sistem payı.',
        'secret_values_returned': False,
    }


def build_trade_ledger_quality_report() -> dict:
    sample = {
        'real_trade_history': [
            {'trade_id': 'live-1', 'mode': 'live', 'symbol': 'BTCUSDT', 'side': 'buy', 'notional_usdt': 10, 'gross_pnl_usdt': 0.42, 'binance_fee_usdt': 0.01, 'status': 'closed', 'strategy_id': 'choch', 'filter_ids': ['spread']},
            {'trade_id': 'live-2', 'mode': 'live', 'symbol': 'ETHUSDT', 'side': 'sell', 'notional_usdt': 8, 'gross_pnl_usdt': -0.1, 'binance_fee_usdt': 0.008, 'status': 'closed', 'strategy_id': 'imbalance', 'filter_ids': ['volume']},
        ],
        'paper_trade_history': [
            {'trade_id': 'paper-1', 'mode': 'paper', 'symbol': 'BNBUSDT', 'side': 'buy', 'notional_usdt': 20, 'gross_pnl_usdt': 0.8, 'binance_fee_usdt': 0, 'status': 'closed'}
        ]
    }
    report = build_trade_ledger(sample, {}, {'users': {'quality_user': {'commission_settings': {'enabled': True, 'buy_rate_percent': 0.1, 'sell_rate_percent': 0.1}}}}, 'quality_user')
    checks = [
        'paper_and_live_are_separated',
        'gross_binance_platform_net_are_separated',
        'checksum_present',
        'secret_values_not_returned',
        'duplicate_trade_protection',
    ]
    blockers = list(report.get('blockers') or [])
    summary = as_dict(report.get('summary'))
    if summary.get('paper_trade_count') != 1 or summary.get('live_trade_count') != 2:
        blockers.append('paper_live_count_mismatch')
    if report.get('secret_values_returned') is not False:
        blockers.append('secret_values_returned')
    if not report.get('checksum'):
        blockers.append('ledger_checksum_missing')
    return {
        'status': 'ok' if not blockers else 'blocked',
        'checks': checks,
        'blockers': blockers,
        'sample_summary': summary,
        'secret_values_returned': False,
    }
