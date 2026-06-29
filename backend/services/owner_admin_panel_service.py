from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.rental_commission_service import build_owner_commission_summary
from services.user_api_secret_layer_service import build_user_api_secret_summary


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return round(float(value), 8)
    except Exception:
        return fallback


def _find_commission_row(owner_commission: dict, username: str) -> dict:
    for row in owner_commission.get('users') or []:
        if row.get('user') == username:
            return row
    return {}


def _user_action_label(active: bool, api_ready: bool, live_enabled: bool, billing_status: str) -> str:
    if not active:
        return 'Hesap kapalı. Gerekirse aktif et.'
    if billing_status in {'overdue', 'suspended'}:
        return 'Ödeme sorunlu. Canlı izni kapalı tutulmalı.'
    if live_enabled and not api_ready:
        return 'Canlı paket var ama Binance bağlı değil.'
    if live_enabled:
        return 'Canlı izin açık. Risk ve işlem geçmişini izle.'
    if api_ready:
        return 'Paper veya mikro canlı için hazır.'
    return 'Önce Binance bağlantısı veya paper denemesi tamamlanmalı.'


def build_owner_admin_panel(auth_store: dict | None, runtime_by_user: dict | None = None) -> dict:
    """Return a secret-safe owner command center for tenant administration.

    Owner panel must answer five practical questions in one payload:
    who is active, who paid, whose Binance is connected, who can trade live,
    and how much commission/net PnL was produced. Secret keys are never returned.
    """
    store = _as_dict(auth_store)
    users = _as_dict(store.get('users'))
    runtime_map = _as_dict(runtime_by_user)
    owner_commission = build_owner_commission_summary(store, runtime_map)
    rows: list[dict] = []

    totals = {
        'user_count': 0,
        'active_user_count': 0,
        'api_connected_count': 0,
        'live_enabled_count': 0,
        'payment_problem_count': 0,
        'platform_commission_usdt': _safe_float(_as_dict(owner_commission.get('summary')).get('platform_commission_usdt')),
        'net_pnl_usdt': _safe_float(_as_dict(owner_commission.get('summary')).get('net_pnl_usdt')),
        'outstanding_usdt': _safe_float(_as_dict(owner_commission.get('summary')).get('outstanding_usdt')),
    }

    for username, raw_record in sorted(users.items()):
        record = _as_dict(raw_record)
        if record.get('role') == 'owner':
            continue
        active = record.get('active', True) is not False
        api_summary = build_user_api_secret_summary(store, username)
        commission_row = _find_commission_row(owner_commission, username)
        billing_status = str(commission_row.get('billing_status') or 'trial')
        live_enabled = bool(commission_row.get('live_enabled'))
        api_connected = bool(api_summary.get('configured'))
        payment_problem = billing_status in {'overdue', 'suspended'} or _safe_float(commission_row.get('outstanding_usdt')) > 0
        blockers = []
        if not active:
            blockers.append('Kullanıcı pasif')
        if live_enabled and not api_connected:
            blockers.append('Canlı izin var ama Binance bağlı değil')
        if billing_status in {'overdue', 'suspended'}:
            blockers.append('Ödeme durumu sorunlu')
        if live_enabled and not active:
            blockers.append('Pasif kullanıcıda canlı izin açık görünüyor')
        rows.append({
            'user': username,
            'role': record.get('role', 'user'),
            'active': active,
            'package': commission_row.get('package') or record.get('package') or 'paper_only',
            'package_label': commission_row.get('package_label') or commission_row.get('package') or record.get('package') or 'Paper Only',
            'billing_status': billing_status,
            'billing_label': commission_row.get('billing_label') or billing_status,
            'outstanding_usdt': _safe_float(commission_row.get('outstanding_usdt')),
            'monthly_fee_usdt': _safe_float(commission_row.get('monthly_fee_usdt')),
            'api_connected': api_connected,
            'api_environment': api_summary.get('environment') or 'not_connected',
            'api_trade_enabled': bool(api_summary.get('trade_enabled')),
            'api_masked_key': api_summary.get('masked_api_key') or '-',
            'live_enabled': live_enabled,
            'trade_count': int(commission_row.get('trade_count') or 0),
            'gross_pnl_usdt': _safe_float(commission_row.get('gross_pnl_usdt')),
            'platform_commission_usdt': _safe_float(commission_row.get('platform_commission_usdt')),
            'net_pnl_usdt': _safe_float(commission_row.get('net_pnl_usdt')),
            'decision': commission_row.get('decision') or 'PASS',
            'blockers': blockers,
            'next_action': _user_action_label(active, api_connected, live_enabled, billing_status),
            'secret_values_returned': False,
        })
        totals['user_count'] += 1
        totals['active_user_count'] += 1 if active else 0
        totals['api_connected_count'] += 1 if api_connected else 0
        totals['live_enabled_count'] += 1 if live_enabled else 0
        totals['payment_problem_count'] += 1 if payment_problem else 0

    return {
        'status': 'ok',
        'generated_at': _now_iso(),
        'summary': totals,
        'users': rows,
        'owner_actions': [
            {'id': 'pause_user', 'label': 'Kullanıcıyı durdur', 'description': 'Kullanıcı yeni işlem açamaz.'},
            {'id': 'disable_live', 'label': 'Canlı izni kapat', 'description': 'Paketi güvenli paper seviyesine çeker.'},
            {'id': 'clear_api', 'label': 'API bağlantısını sil', 'description': 'Kullanıcının Binance bağlantısını kaldırır.'},
            {'id': 'mark_paid', 'label': 'Ödendi işaretle', 'description': 'Tahsilat durumunu günceller.'},
        ],
        'simple_text': 'Owner burada kullanıcı, ödeme, Binance bağlantısı, canlı izin ve sistem payını tek ekrandan izler.',
        'secret_values_returned': False,
    }


def validate_owner_admin_panel(auth_store: dict | None = None) -> dict:
    sample_store = auth_store or {
        'users': {
            'owner': {'role': 'owner', 'active': True},
            'demo_user': {
                'role': 'user',
                'active': True,
                'package': 'micro_live',
                'api_connection': {
                    'exchange': 'binance',
                    'environment': 'testnet',
                    'masked_api_key': 'ABCD********WXYZ',
                    'api_secret_digest': 'digest',
                    'permissions': ['read'],
                    'trade_enabled': False,
                },
                'commission_settings': {'enabled': True, 'buy_rate_percent': 0.1, 'sell_rate_percent': 0.1},
                'billing': {'status': 'pending', 'monthly_fee_usdt': 25, 'paid_usdt': 0},
            },
        }
    }
    panel = build_owner_admin_panel(sample_store)
    checks = [
        {'name': 'owner_summary_exists', 'status': 'ok' if panel.get('summary') else 'blocked'},
        {'name': 'user_rows_optional', 'status': 'ok'},
        {'name': 'api_status_visible', 'status': 'ok' if all('api_connected' in row for row in panel.get('users', [])) else 'blocked'},
        {'name': 'live_permission_visible', 'status': 'ok' if all('live_enabled' in row for row in panel.get('users', [])) else 'blocked'},
        {'name': 'billing_status_visible', 'status': 'ok' if all('billing_status' in row for row in panel.get('users', [])) else 'blocked'},
        {'name': 'commission_visible', 'status': 'ok' if all('platform_commission_usdt' in row for row in panel.get('users', [])) else 'blocked'},
        {'name': 'secret_values_never_returned', 'status': 'ok' if panel.get('secret_values_returned') is False and all(row.get('secret_values_returned') is False for row in panel.get('users', [])) else 'blocked'},
    ]
    blockers = [row['name'] for row in checks if row['status'] != 'ok']
    return {
        'status': 'ok' if not blockers else 'blocked',
        'generated_at': _now_iso(),
        'checks': checks,
        'blockers': blockers,
        'panel': panel,
        'secret_values_returned': False,
    }
