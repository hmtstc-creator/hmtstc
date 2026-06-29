from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.rental_commission_service import build_owner_commission_summary
from services.production_completion_service import safe_float


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def default_collection_settings() -> dict:
    return {
        'manual_collection': True,
        'withdraw_permission_required': False,
        'supported_methods': ['USDT TRC20', 'USDT BEP20', 'Banka/IBAN', 'Manuel ödeme'],
        'usdt_trc20_address': '',
        'usdt_bep20_address': '',
        'iban': '',
        'note': 'Komisyon sistemde alacak olarak birikir; kullanıcıdan withdraw izni istenmez.',
    }


def get_collection_settings(auth_store: dict | None) -> dict:
    settings = default_collection_settings()
    settings.update(as_dict(as_dict(auth_store).get('owner_collection_settings')))
    settings['withdraw_permission_required'] = False
    settings['manual_collection'] = True
    return settings


def update_collection_settings(auth_store: dict, payload: dict | None) -> dict:
    payload = as_dict(payload)
    current = get_collection_settings(auth_store)
    for key in ('usdt_trc20_address', 'usdt_bep20_address', 'iban', 'note'):
        if key in payload:
            current[key] = str(payload.get(key) or '').strip()
    auth_store['owner_collection_settings'] = current
    return {'status': 'ok', 'collection_settings': current, 'secret_values_returned': False}




def normalize_collection_method(value: Any) -> str:
    raw = str(value or 'manual').strip().lower()
    aliases = {
        'trc20': 'USDT TRC20',
        'usdt trc20': 'USDT TRC20',
        'bep20': 'USDT BEP20',
        'usdt bep20': 'USDT BEP20',
        'iban': 'Banka/IBAN',
        'bank': 'Banka/IBAN',
        'banka': 'Banka/IBAN',
        'manual': 'Manuel ödeme',
        'manuel': 'Manuel ödeme',
    }
    return aliases.get(raw, str(value or 'Manuel ödeme'))

def receivable_status(balance: float) -> str:
    return 'paid' if balance <= 0 else 'pending_collection'

def receivable_action_text(balance: float) -> str:
    return 'Tahsil edildi' if balance <= 0 else 'Owner manuel tahsilat almalı ve ödendi işaretlemeli.'

def mark_commission_receivable_payment(auth_store: dict, username: str, payload: dict | None) -> dict:
    users = auth_store.setdefault('users', {})
    record = as_dict(users.get(username))
    if not record:
        raise KeyError(username)
    payload = as_dict(payload)
    payments = record.setdefault('commission_payments', [])
    amount = safe_float(payload.get('amount_usdt'), 0.0)
    payments.append({
        'amount_usdt': round(max(0.0, amount), 8),
        'method': normalize_collection_method(payload.get('method')),
        'note': str(payload.get('note') or ''),
        'paid_at': now_iso(),
        'marked_by_owner': True,
    })
    record['commission_payments'] = payments
    users[username] = record
    return {'status': 'ok', 'user': username, 'paid_total_usdt': round(sum(safe_float(x.get('amount_usdt'), 0.0) for x in payments), 8), 'secret_values_returned': False}


def build_owner_receivables_summary(auth_store: dict | None, runtime_by_user: dict | None = None) -> dict:
    owner = build_owner_commission_summary(auth_store, runtime_by_user)
    users = as_dict(as_dict(auth_store).get('users'))
    rows = []
    total_due = 0.0
    total_paid = 0.0
    for row in owner.get('users', []):
        username = row.get('user')
        record = as_dict(users.get(username))
        paid = sum(safe_float(x.get('amount_usdt'), 0.0) for x in record.get('commission_payments', []) if isinstance(x, dict))
        due = safe_float(row.get('platform_commission_usdt'), 0.0) + safe_float(row.get('outstanding_usdt'), 0.0)
        balance = max(0.0, due - paid)
        total_due += due
        total_paid += paid
        rows.append({
            'user': username,
            'package': row.get('package_label'),
            'commission_receivable_usdt': row.get('platform_commission_usdt'),
            'package_outstanding_usdt': row.get('outstanding_usdt'),
            'paid_usdt': round(paid, 8),
            'balance_usdt': round(balance, 8),
            'status': receivable_status(balance),
            'action': receivable_action_text(balance),
            'collection_model': 'manual_usdt_iban',
        })
    return {
        'status': 'ok',
        'generated_at': now_iso(),
        'collection_settings': get_collection_settings(auth_store),
        'summary': {'receivable_usdt': round(total_due, 8), 'paid_usdt': round(total_paid, 8), 'balance_usdt': round(max(0.0, total_due - total_paid), 8), 'collection_model': 'manual_usdt_iban', 'withdraw_required': False},
        'users': rows,
        'secret_values_returned': False,
    }


def validate_collection_flow() -> dict:
    settings = get_collection_settings({})
    blockers = []
    if settings.get('withdraw_permission_required') is not False:
        blockers.append('withdraw_must_not_be_required')
    if settings.get('manual_collection') is not True:
        blockers.append('manual_collection_must_be_default')
    sample_status = receivable_status(10)
    if sample_status != 'pending_collection':
        blockers.append('receivable_pending_status_missing')
    if normalize_collection_method('trc20') != 'USDT TRC20' or normalize_collection_method('iban') != 'Banka/IBAN':
        blockers.append('collection_method_normalization_failed')
    return {'status': 'ok' if not blockers else 'blocked', 'decision': 'PASS' if not blockers else 'BLOCKED', 'blockers': blockers, 'secret_values_returned': False}
