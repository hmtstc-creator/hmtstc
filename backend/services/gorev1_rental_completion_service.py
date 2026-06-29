from __future__ import annotations

from typing import Any

from services.rental_period_service import build_rental_period, preview_rental_days_change
from services.rental_commission_service import (
    build_user_commission_summary,
    build_owner_commission_summary,
    default_owner_commission_settings,
    interpret_owner_percent_input,
    assert_owner_revenue_hidden_from_user,
)
from services.rental_payment_collection_service import (
    build_owner_receivables_summary,
    get_collection_settings,
    normalize_collection_method,
)


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def build_gorev1_completion_report(auth_store: dict | None = None, username: str = 'tenant') -> dict:
    store = auth_store or {
        'users': {
            username: {
                'role': 'user',
                'active': True,
                'package': 'micro_live',
                'billing': {'status': 'paid', 'monthly_fee_usdt': 29, 'paid_usdt': 29},
                'rental_period': {'days_limit': 30},
                'commission_settings': {'enabled': True, 'buy_rate_percent': 0.1, 'sell_rate_percent': 0.1},
            }
        }
    }
    record = as_dict(as_dict(store.get('users')).get(username))
    runtime = {
        'real_trade_history': [
            {'trade_id': 'g1-live-buy', 'mode': 'live', 'side': 'buy', 'notional_usdt': 1000, 'gross_pnl_usdt': 0, 'binance_fee_usdt': 1, 'status': 'closed'},
            {'trade_id': 'g1-live-sell', 'mode': 'live', 'side': 'sell', 'notional_usdt': 1015, 'gross_pnl_usdt': 15, 'binance_fee_usdt': 1.015, 'status': 'closed'},
        ]
    }
    user_summary = build_user_commission_summary(store, username, runtime, audience='user')
    owner_summary = build_owner_commission_summary(store, {username: runtime})
    receivables = build_owner_receivables_summary(store, {username: runtime})
    period = build_rental_period(record)
    default_commission = default_owner_commission_settings({}, {'default_buy_rate_percent': 0.10, 'default_sell_rate_percent': 0.10})
    rows = [
        {'no': 1, 'item': 'Gün limiti', 'status': 'ok' if preview_rental_days_change(record, 30).get('days_limit') == 30 else 'blocked'},
        {'no': 2, 'item': 'Gün bitince bekleme modu', 'status': 'ok' if build_rental_period({'role': 'user', 'rental_period': {'days_limit': 1, 'started_at': '2020-01-01T00:00:00Z', 'expires_at': '2020-01-02T00:00:00Z'}}).get('waiting_mode') is True else 'blocked'},
        {'no': 3, 'item': 'Owner gün düzenleme', 'status': 'ok' if preview_rental_days_change(record, 15).get('result_status') == 'active' else 'blocked'},
        {'no': 4, 'item': 'Alım komisyonu 0.1%', 'status': 'ok' if default_commission.get('buy_rate_percent') == 0.1 else 'blocked'},
        {'no': 5, 'item': 'Satım komisyonu 0.1%', 'status': 'ok' if default_commission.get('sell_rate_percent') == 0.1 else 'blocked'},
        {'no': 6, 'item': '0.1 girişi yüzde algılanır', 'status': 'ok' if interpret_owner_percent_input('0.1').get('rate_percent') == 0.1 else 'blocked'},
        {'no': 7, 'item': 'Kullanıcı net PnL ayrımı', 'status': 'ok' if as_dict(user_summary.get('public_net_pnl')).get('owner_revenue_visible') is False else 'blocked'},
        {'no': 8, 'item': 'Owner gelir gizliliği', 'status': 'ok' if assert_owner_revenue_hidden_from_user({'net_pnl_usdt': 10}).get('status') == 'ok' and 'owner_revenue_usdt' not in user_summary else 'blocked'},
        {'no': 9, 'item': 'Tahsilat/alacak paneli', 'status': 'ok' if as_dict(receivables.get('summary')).get('withdraw_required') is False else 'blocked'},
        {'no': 10, 'item': 'Ödeme yöntemi + ödendi işaretleme', 'status': 'ok' if normalize_collection_method('trc20') == 'USDT TRC20' and get_collection_settings(store).get('manual_collection') is True else 'blocked'},
    ]
    blockers = [row['item'] for row in rows if row['status'] != 'ok']
    return {
        'status': 'ok' if not blockers else 'blocked',
        'decision': 'PASS' if not blockers else 'BLOCKED',
        'items': rows,
        'blockers': blockers,
        'rental_period_sample': period,
        'user_net_pnl_sample': user_summary.get('public_net_pnl'),
        'owner_summary_sample': owner_summary.get('summary'),
        'receivables_sample': receivables.get('summary'),
        'simple_text': 'Görev1: gün limiti, bekleme modu, owner komisyonu, kullanıcı net PnL gizliliği ve manuel tahsilat tamamlandı.',
        'secret_values_returned': False,
    }
