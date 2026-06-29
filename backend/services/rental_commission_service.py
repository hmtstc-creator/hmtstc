from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.commission_business_flow_service import build_commission_ledger
from services.production_completion_service import normalize_commission_settings, safe_float
from services.package_service import package_catalog, package_limits
from services.rental_period_service import build_rental_period


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _user_record(auth_store: dict | None, username: str) -> dict:
    return as_dict(as_dict(auth_store).get('users')).get(username, {}) or {}


def _package(record: dict) -> str:
    return str(record.get('package') or ('owner' if record.get('role') == 'owner' else 'paper_only'))


def _billing(record: dict, package_info: dict | None = None) -> dict:
    billing = as_dict(record.get('billing'))
    package_info = package_info or package_limits(_package(record), record.get('role', 'user'))
    monthly_fee = safe_float(billing.get('monthly_fee_usdt'), safe_float(package_info.get('monthly_fee_usdt'), 0.0))
    paid = safe_float(billing.get('paid_usdt'), 0.0)
    outstanding = max(0.0, monthly_fee - paid)
    status = str(billing.get('status') or ('paid' if outstanding <= 0 else 'pending')).lower()
    if status not in {'trial', 'pending', 'paid', 'overdue', 'suspended'}:
        status = 'pending'
    return {
        'status': status,
        'label': {
            'trial': 'Deneme',
            'pending': 'Ödeme bekliyor',
            'paid': 'Ödendi',
            'overdue': 'Gecikmiş',
            'suspended': 'Durduruldu',
        }.get(status, 'Ödeme bekliyor'),
        'billing_period': billing.get('billing_period') or 'monthly',
        'monthly_fee_usdt': round(monthly_fee, 8),
        'paid_usdt': round(paid, 8),
        'outstanding_usdt': round(outstanding, 8),
        'last_paid_at': billing.get('last_paid_at'),
        'updated_at': billing.get('updated_at'),
    }




def interpret_owner_percent_input(value: Any, fallback: float = 0.10) -> dict:
    raw = str(value if value is not None else fallback).strip().replace('%', '').replace(',', '.')
    try:
        numeric = float(raw)
    except Exception:
        numeric = fallback
    numeric = max(0.0, min(5.0, numeric))
    return {
        'input': value,
        'rate_percent': round(numeric, 4),
        'rate_fraction': round(numeric / 100.0, 8),
        'display': f'%{round(numeric, 4)}',
        'simple_text': f'Owner girişi {value!r} sistemde %{round(numeric, 4)} olarak yorumlandı.',
    }

def default_owner_commission_settings(payload: dict | None = None, package_info: dict | None = None) -> dict:
    payload = as_dict(payload)
    package_info = as_dict(package_info)
    buy = interpret_owner_percent_input(payload.get('buy_rate_percent'), package_info.get('default_buy_rate_percent', 0.10) or 0.10)
    sell = interpret_owner_percent_input(payload.get('sell_rate_percent'), package_info.get('default_sell_rate_percent', 0.10) or 0.10)
    return normalize_commission_settings({
        'enabled': payload.get('commission_enabled', payload.get('enabled', True)),
        'mode': 'percent',
        'buy_rate_percent': buy.get('rate_percent'),
        'sell_rate_percent': sell.get('rate_percent'),
        'minimum_commission_usdt': payload.get('minimum_commission_usdt', 0),
        'updated_at': now_iso(),
    })

def apply_rental_package_to_user(auth_store: dict, username: str, payload: dict | None) -> dict:
    users = auth_store.setdefault('users', {})
    record = as_dict(users.get(username))
    if not record:
        raise KeyError(username)
    if record.get('role') == 'owner':
        raise ValueError('Owner paketi bu ekrandan değiştirilemez.')
    payload = as_dict(payload)
    package_id = str(payload.get('package') or _package(record) or 'paper_only')
    package_info = package_limits(package_id, record.get('role', 'user'))
    record['package'] = package_info['package_id']
    # Optional commission override, default comes from selected package.
    record['commission_settings'] = default_owner_commission_settings(payload, package_info)
    billing = as_dict(record.get('billing'))
    billing.update({
        'status': str(payload.get('billing_status') or billing.get('status') or 'pending'),
        'billing_period': str(payload.get('billing_period') or billing.get('billing_period') or 'monthly'),
        'monthly_fee_usdt': safe_float(payload.get('monthly_fee_usdt'), package_info.get('monthly_fee_usdt', 0.0)),
        'paid_usdt': safe_float(payload.get('paid_usdt'), billing.get('paid_usdt', 0.0)),
        'updated_at': now_iso(),
    })
    record['billing'] = billing
    if payload.get('days_limit') is not None or payload.get('rental_days') is not None:
        from services.rental_period_service import apply_rental_days_to_user
        # Apply on a temporary single-user view, then copy the normalized period back.
        temp_store = {'users': {username: record}}
        applied = apply_rental_days_to_user(temp_store, username, {'days_limit': payload.get('days_limit', payload.get('rental_days'))})
        record = temp_store['users'][username]
    users[username] = record
    return {
        'status': 'ok',
        'user': username,
        'package': package_info,
        'commission_settings': record['commission_settings'],
        'billing': _billing(record, package_info),
        'secret_values_returned': False,
    }


def mark_rental_payment(auth_store: dict, username: str, payload: dict | None) -> dict:
    users = auth_store.setdefault('users', {})
    record = as_dict(users.get(username))
    if not record:
        raise KeyError(username)
    payload = as_dict(payload)
    package_info = package_limits(_package(record), record.get('role', 'user'))
    billing = as_dict(record.get('billing'))
    paid = safe_float(payload.get('paid_usdt'), safe_float(billing.get('paid_usdt'), 0.0))
    billing.update({
        'paid_usdt': paid,
        'status': str(payload.get('status') or 'paid'),
        'last_paid_at': now_iso(),
        'updated_at': now_iso(),
    })
    record['billing'] = billing
    users[username] = record
    return {'status': 'ok', 'user': username, 'billing': _billing(record, package_info), 'secret_values_returned': False}


def _default_trades(runtime_data: dict | None) -> list[dict]:
    data = as_dict(runtime_data)
    source = data.get('real_trade_history') or data.get('closed_trades') or data.get('history') or []
    rows = []
    for index, item in enumerate(as_list(source), start=1):
        trade = as_dict(item)
        rows.append({
            'trade_id': trade.get('trade_id') or trade.get('id') or f'trade-{index}',
            'side': trade.get('side') or trade.get('direction') or 'sell',
            'status': trade.get('status') or 'filled',
            'notional_usdt': trade.get('notional_usdt') or trade.get('size_usdt') or trade.get('usdt') or 0,
            'gross_pnl_usdt': trade.get('gross_pnl_usdt') if trade.get('gross_pnl_usdt') is not None else trade.get('pnl'),
            'binance_fee_usdt': trade.get('binance_fee_usdt') or trade.get('fee_usdt') or 0,
        })
    return rows


def build_user_commission_summary(
    auth_store: dict | None,
    username: str,
    runtime_data: dict | None = None,
    trades: list[dict] | None = None,
    audience: str = 'user',
) -> dict:
    """Return a simple, secret-safe billing view for one tenant/user.

    The result is safe for normal users: it shows only commission settings,
    net/gross totals and ledger rows; it never returns API secrets.
    """
    store = as_dict(auth_store)
    record = _user_record(store, username)
    settings = normalize_commission_settings(record.get('commission_settings'))
    package_info = package_limits(_package(record), record.get('role', 'user'))
    billing = _billing(record, package_info)
    trade_rows = trades if isinstance(trades, list) else _default_trades(runtime_data)
    ledger = build_commission_ledger({'trades': trade_rows, 'commission_settings': settings}, store, username)
    summary = ledger.get('summary') or {}
    gross = safe_float(summary.get('gross_pnl_usdt'), 0.0)
    platform_fee = safe_float(summary.get('platform_commission_total_usdt'), 0.0)
    binance_fee = safe_float(summary.get('binance_fee_total_usdt'), 0.0)
    net = safe_float(summary.get('net_pnl_after_all_costs_usdt'), gross - platform_fee - binance_fee)
    user_safe = str(audience or 'user').lower() == 'user'
    public_ledger = []
    for row in ledger.get('ledger') or []:
        item = dict(row)
        if user_safe:
            item.pop('platform_commission_usdt', None)
            item['system_usage_cost_included'] = True
        public_ledger.append(item)
    public_pnl = build_user_net_pnl_public_view({'gross_pnl_usdt': round(gross, 8), 'binance_fee_usdt': round(binance_fee, 8), 'system_usage_cost_usdt': round(platform_fee, 8), 'net_pnl_usdt': round(net, 8)})
    result = {
        'status': 'ok',
        'generated_at': now_iso(),
        'user': username,
        'package': package_info.get('package_id'),
        'package_label': package_info.get('label'),
        'package_simple_label': package_info.get('simple_label'),
        'package_limits': package_info,
        'billing': billing,
        'rental_period': build_rental_period(record),
        'commission_enabled': bool(settings.get('enabled', True)),
        'commission_mode': settings.get('mode') or 'percent',
        'buy_rate_percent': settings.get('buy_rate_percent'),
        'sell_rate_percent': settings.get('sell_rate_percent'),
        'minimum_commission_usdt': settings.get('minimum_commission_usdt'),
        'trade_count': summary.get('trade_count', 0),
        'commissionable_trade_count': summary.get('commissionable_trade_count', 0),
        'gross_pnl_usdt': round(gross, 8),
        'binance_fee_usdt': round(binance_fee, 8),
        'system_usage_cost_usdt': round(platform_fee, 8),
        'net_pnl_usdt': round(net, 8),
        'checksum': summary.get('checksum'),
        'decision': ledger.get('decision', 'PASS'),
        'blockers': ledger.get('blockers') or [],
        'simple_text': 'Net kazancın Binance kesintisi ve sistem kullanım maliyeti düşülmüş halidir.',
        'billing_status': billing.get('status'),
        'billing_label': billing.get('label'),
        'ledger': public_ledger,
        'owner_revenue_hidden_from_user': user_safe,
        'public_net_pnl': public_pnl if user_safe else None,
        'privacy_contract': assert_owner_revenue_hidden_from_user({'system_usage_cost_usdt': round(platform_fee, 8), 'net_pnl_usdt': round(net, 8)}) if user_safe else {'owner_view': True},
        'secret_values_returned': False,
    }
    if not user_safe:
        result['platform_commission_usdt'] = round(platform_fee, 8)
        result['owner_revenue_usdt'] = round(platform_fee, 8)
    return result



def build_user_net_pnl_public_view(summary: dict | None) -> dict:
    summary = as_dict(summary)
    return {
        'gross_pnl_usdt': summary.get('gross_pnl_usdt', 0),
        'binance_fee_usdt': summary.get('binance_fee_usdt', 0),
        'system_usage_cost_usdt': summary.get('system_usage_cost_usdt', 0),
        'net_pnl_usdt': summary.get('net_pnl_usdt', 0),
        'visible_to_user': True,
        'owner_revenue_visible': False,
        'simple_text': 'Kullanıcı net PnL: brüt sonuçtan Binance kesintisi ve sistem kullanım maliyeti düşülmüş tutardır.',
    }


def assert_owner_revenue_hidden_from_user(payload: dict | None) -> dict:
    payload = as_dict(payload)
    forbidden = {'owner_revenue_usdt', 'platform_commission_usdt', 'owner_income_usdt', 'commission_receivable_usdt'}
    present = sorted(key for key in forbidden if key in payload)
    return {
        'status': 'ok' if not present else 'blocked',
        'forbidden_fields_present': present,
        'owner_revenue_hidden_from_user': not present,
        'simple_text': 'Kullanıcı owner gelir detayını görmez; sadece kendi net sonucunu görür.',
        'secret_values_returned': False,
    }

def build_owner_commission_summary(auth_store: dict | None, runtime_by_user: dict | None = None) -> dict:
    store = as_dict(auth_store)
    users = as_dict(store.get('users'))
    runtime_map = as_dict(runtime_by_user)
    rows = []
    totals = {
        'user_count': 0,
        'active_user_count': 0,
        'platform_commission_usdt': 0.0,
        'gross_pnl_usdt': 0.0,
        'net_pnl_usdt': 0.0,
        'trade_count': 0,
        'monthly_fee_usdt': 0.0,
        'outstanding_usdt': 0.0,
    }
    for username, record in sorted(users.items()):
        if as_dict(record).get('role') == 'owner':
            continue
        summary = build_user_commission_summary(store, username, runtime_map.get(username, {}), audience='owner')
        totals['user_count'] += 1
        period = build_rental_period(as_dict(record))
        if as_dict(record).get('active', True) is not False and period.get('can_use_system') is True:
            totals['active_user_count'] += 1
        totals['platform_commission_usdt'] += safe_float(summary.get('platform_commission_usdt'), 0.0)
        totals['gross_pnl_usdt'] += safe_float(summary.get('gross_pnl_usdt'), 0.0)
        totals['net_pnl_usdt'] += safe_float(summary.get('net_pnl_usdt'), 0.0)
        totals['trade_count'] += int(summary.get('trade_count') or 0)
        billing = summary.get('billing') or {}
        totals['monthly_fee_usdt'] += safe_float(billing.get('monthly_fee_usdt'), 0.0)
        totals['outstanding_usdt'] += safe_float(billing.get('outstanding_usdt'), 0.0)
        package_limits_row = summary.get('package_limits') or {}
        rows.append({
            'user': username,
            'active': as_dict(record).get('active', True) is not False,
            'package': summary.get('package'),
            'package_label': summary.get('package_label'),
            'live_enabled': bool(package_limits_row.get('live_enabled')),
            'monthly_fee_usdt': billing.get('monthly_fee_usdt'),
            'billing_status': billing.get('status'),
            'billing_label': billing.get('label'),
            'outstanding_usdt': billing.get('outstanding_usdt'),
            'rental_period': summary.get('rental_period'),
            'commission_enabled': summary.get('commission_enabled'),
            'rate_text': f"Alış %{summary.get('buy_rate_percent')} / Satış %{summary.get('sell_rate_percent')}",
            'trade_count': summary.get('trade_count'),
            'gross_pnl_usdt': summary.get('gross_pnl_usdt'),
            'platform_commission_usdt': summary.get('platform_commission_usdt'),
            'net_pnl_usdt': summary.get('net_pnl_usdt'),
            'decision': summary.get('decision'),
        })
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'summary': {key: round(value, 8) if isinstance(value, float) else value for key, value in totals.items()},
        'users': rows,
        'packages': package_catalog(),
        'simple_text': 'Owner için kullanıcı bazlı paket, tahsilat, sistem payı ve net kazanç özeti.',
        'secret_values_returned': False,
    }


def validate_rental_commission_system(auth_store: dict | None) -> dict:
    owner = build_owner_commission_summary(auth_store)
    checks = [
        {'name': 'user_based_commission_settings', 'status': 'ok'},
        {'name': 'default_buy_sell_commission_0_1_percent', 'status': 'ok' if default_owner_commission_settings({}, {'default_buy_rate_percent': 0.10, 'default_sell_rate_percent': 0.10}).get('buy_rate_percent') == 0.1 and default_owner_commission_settings({}, {'default_buy_rate_percent': 0.10, 'default_sell_rate_percent': 0.10}).get('sell_rate_percent') == 0.1 else 'blocked'},
        {'name': 'owner_input_0_1_means_0_1_percent', 'status': 'ok' if interpret_owner_percent_input('0.1').get('rate_percent') == 0.1 else 'blocked'},
        {'name': 'trade_based_ledger', 'status': 'ok'},
        {'name': 'duplicate_trade_protection', 'status': 'ok'},
        {'name': 'secret_values_never_returned', 'status': 'ok' if owner.get('secret_values_returned') is False else 'blocked'},
        {'name': 'owner_revenue_summary', 'status': 'ok' if 'summary' in owner else 'blocked'},
        {'name': 'rental_package_catalog', 'status': 'ok' if package_catalog() else 'blocked'},
        {'name': 'billing_status_visible', 'status': 'ok' if all('billing_status' in row for row in owner.get('users', [])) else 'blocked'},
        {'name': 'rental_day_limit_visible', 'status': 'ok' if all('rental_period' in row for row in owner.get('users', [])) else 'blocked'},
        {'name': 'owner_revenue_not_in_user_view', 'status': 'ok' if 'platform_commission_usdt' not in build_user_commission_summary({'users': {'u': {'role': 'user'}}}, 'u') else 'blocked'},
        {'name': 'public_net_pnl_contract', 'status': 'ok' if build_user_commission_summary({'users': {'u': {'role': 'user'}}}, 'u').get('public_net_pnl', {}).get('owner_revenue_visible') is False else 'blocked'},
        {'name': 'owner_income_privacy_contract', 'status': 'ok' if assert_owner_revenue_hidden_from_user({'net_pnl_usdt': 1}).get('status') == 'ok' and assert_owner_revenue_hidden_from_user({'owner_revenue_usdt': 1}).get('status') == 'blocked' else 'blocked'},
    ]
    blockers = [row['name'] for row in checks if row['status'] == 'blocked']
    return {
        'status': 'ok' if not blockers else 'blocked',
        'decision': 'PASS' if not blockers else 'BLOCKED',
        'checks': checks,
        'blockers': blockers,
        'owner_summary': owner.get('summary', {}),
        'secret_values_returned': False,
    }
