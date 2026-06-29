from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def now_iso() -> str:
    return now_utc().isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return fallback


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    clean = str(value).strip().replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _user_record(auth_store: dict | None, username: str) -> dict:
    return as_dict(as_dict(auth_store).get('users')).get(username, {}) or {}



def rental_waiting_mode_label(period: dict | None) -> str:
    period = as_dict(period)
    if period.get('can_use_system') is True:
        return 'Aktif'
    if period.get('is_expired') is True or str(period.get('status') or '').lower() == 'waiting':
        return 'Bekleme modu'
    return 'Pasif'


def rental_period_user_can_trade(record: dict | None) -> bool:
    return build_rental_period(record).get('can_use_system') is True

def build_rental_period(record: dict | None) -> dict:
    record = as_dict(record)
    rental = as_dict(record.get('rental_period'))
    role = str(record.get('role') or 'user')
    if role == 'owner':
        return {
            'status': 'active',
            'label': 'Owner sınırsız',
            'days_limit': 0,
            'started_at': None,
            'expires_at': None,
            'remaining_days': None,
            'is_expired': False,
            'can_use_system': True,
            'waiting_mode': False,
            'bot_start_allowed': True,
            'owner_editable_days': False,
            'action': 'Owner için gün limiti uygulanmaz.',
        }
    days_limit = safe_int(rental.get('days_limit'), 0)
    started_at = parse_iso(rental.get('started_at'))
    expires_at = parse_iso(rental.get('expires_at'))
    if days_limit > 0 and not expires_at:
        if not started_at:
            started_at = now_utc()
        expires_at = started_at + timedelta(days=days_limit)
    current = now_utc()
    if days_limit <= 0:
        status = str(rental.get('status') or 'waiting').lower()
        can_use = status in {'active', 'trial'}
        return {
            'status': status,
            'label': 'Gün tanımı yok' if not can_use else 'Aktif',
            'days_limit': days_limit,
            'started_at': started_at.isoformat().replace('+00:00', 'Z') if started_at else None,
            'expires_at': None,
            'remaining_days': 0,
            'is_expired': not can_use,
            'can_use_system': can_use,
            'waiting_mode': not can_use,
            'bot_start_allowed': can_use,
            'owner_editable_days': True,
            'action': 'Owner kullanıcı için kiralama günü tanımlamalı.',
        }
    expired = bool(expires_at and current >= expires_at)
    remaining_seconds = max(0, int(((expires_at or current) - current).total_seconds()))
    remaining_days = 0 if expired else max(1, (remaining_seconds + 86399) // 86400)
    status = 'waiting' if expired else 'active'
    return {
        'status': status,
        'label': 'Süre bitti - beklemede' if expired else 'Aktif',
        'days_limit': days_limit,
        'started_at': started_at.isoformat().replace('+00:00', 'Z') if started_at else None,
        'expires_at': expires_at.isoformat().replace('+00:00', 'Z') if expires_at else None,
        'remaining_days': remaining_days,
        'is_expired': expired,
        'can_use_system': not expired,
        'waiting_mode': expired,
        'bot_start_allowed': not expired,
        'owner_editable_days': True,
        'action': 'Süre yenilenmeli.' if expired else 'Kullanıcı aktif süre içinde.',
    }


def apply_rental_days_to_user(auth_store: dict, username: str, payload: dict | None) -> dict:
    users = auth_store.setdefault('users', {})
    record = as_dict(users.get(username))
    if not record:
        raise KeyError(username)
    if record.get('role') == 'owner':
        raise ValueError('Owner için gün limiti uygulanmaz.')
    payload = as_dict(payload)
    days = max(0, safe_int(payload.get('days_limit') if payload.get('days_limit') is not None else payload.get('days'), 0))
    start = parse_iso(payload.get('started_at')) or now_utc()
    expires = start + timedelta(days=days) if days > 0 else None
    previous_period = as_dict(record.get('rental_period'))
    record['rental_period'] = {
        'days_limit': days,
        'started_at': start.isoformat().replace('+00:00', 'Z'),
        'expires_at': expires.isoformat().replace('+00:00', 'Z') if expires else None,
        'status': 'active' if days > 0 else 'waiting',
        'updated_at': now_iso(),
        'configured_by_owner': True,
    }
    history = record.setdefault('rental_period_history', [])
    if isinstance(history, list):
        history.append({
            'changed_at': now_iso(),
            'previous_days_limit': previous_period.get('days_limit'),
            'new_days_limit': days,
            'previous_expires_at': previous_period.get('expires_at'),
            'new_expires_at': record['rental_period'].get('expires_at'),
            'reason': str(payload.get('reason') or 'owner_update'),
        })
        record['rental_period_history'] = history[-50:]
    record['active'] = days > 0
    users[username] = record
    period = build_rental_period(record)
    return {'status': 'ok', 'user': username, 'rental_period': period, 'secret_values_returned': False}


def build_user_rental_period_summary(auth_store: dict | None, username: str) -> dict:
    record = _user_record(auth_store, username)
    return {'status': 'ok', 'user': username, 'rental_period': build_rental_period(record), 'secret_values_returned': False}



def preview_rental_days_change(record: dict | None, days_limit: Any) -> dict:
    record = as_dict(record)
    days = max(0, safe_int(days_limit, 0))
    start = now_utc()
    expires = start + timedelta(days=days) if days > 0 else None
    return {
        'status': 'ok',
        'days_limit': days,
        'started_at': start.isoformat().replace('+00:00', 'Z'),
        'expires_at': expires.isoformat().replace('+00:00', 'Z') if expires else None,
        'result_status': 'active' if days > 0 else 'waiting',
        'will_enter_waiting_mode': days <= 0,
        'simple_text': 'Gün sayısı owner tarafından belirlenir; süre bitince kullanıcı bekleme moduna alınır.',
        'secret_values_returned': False,
    }

def validate_rental_period_system() -> dict:
    active_store = {'users': {'u': {'role': 'user', 'active': True, 'rental_period': {'days_limit': 10, 'started_at': now_iso()}}}}
    expired_store = {'users': {'u': {'role': 'user', 'active': True, 'rental_period': {'days_limit': 1, 'started_at': '2020-01-01T00:00:00Z', 'expires_at': '2020-01-02T00:00:00Z'}}}}
    active = build_user_rental_period_summary(active_store, 'u')['rental_period']
    expired = build_user_rental_period_summary(expired_store, 'u')['rental_period']
    blockers = []
    if active.get('can_use_system') is not True:
        blockers.append('active_period_should_allow')
    if expired.get('can_use_system') is not False or expired.get('status') != 'waiting':
        blockers.append('expired_period_should_wait')
    if expired.get('waiting_mode') is not True or expired.get('bot_start_allowed') is not False:
        blockers.append('expired_waiting_mode_should_block_bot')
    preview = preview_rental_days_change({}, 15)
    if preview.get('days_limit') != 15 or preview.get('result_status') != 'active':
        blockers.append('owner_day_preview_failed')
    return {'status': 'ok' if not blockers else 'blocked', 'decision': 'PASS' if not blockers else 'BLOCKED', 'blockers': blockers, 'secret_values_returned': False}
