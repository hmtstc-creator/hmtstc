from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.package_service import package_limits
from services.rental_commission_service import build_user_commission_summary
from services.rental_period_service import build_rental_period
from services.trade_ledger_net_pnl_service import build_trade_ledger


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def money(value: Any, fallback: float = 0.0) -> float:
    try:
        return round(float(value), 8)
    except Exception:
        return fallback


def _user_record(auth_store: dict | None, username: str) -> dict:
    return as_dict(as_dict(auth_store).get('users')).get(username, {}) or {}


def _billing_ok(billing: dict, role: str) -> bool:
    if role == 'owner':
        return True
    status = str(billing.get('status') or '').lower()
    outstanding = money(billing.get('outstanding_usdt'), 0.0)
    return status in {'paid', 'trial'} and status not in {'overdue', 'suspended'} and outstanding <= 0


def _api_connected(api_summary: dict | None) -> bool:
    conn = as_dict(as_dict(api_summary).get('connection'))
    return bool(conn.get('has_api_key') and conn.get('has_api_secret'))


def _open_live_trades(runtime_data: dict) -> int:
    count = 0
    for source_name in ('open_positions', 'real_trade_history', 'live_trade_history', 'closed_trades'):
        for row in as_list(runtime_data.get(source_name)):
            item = as_dict(row)
            status = str(item.get('status') or item.get('state') or '').lower()
            mode = str(item.get('mode') or item.get('trade_mode') or 'live').lower()
            if mode != 'paper' and status in {'open', 'active', 'running', 'new', 'partially_filled'}:
                count += 1
    return count


def build_rental_live_ops_guard(
    runtime_data: dict | None,
    settings: dict | None,
    auth_store: dict | None,
    username: str,
    api_summary: dict | None = None,
) -> dict:
    """Single decision layer for rentable live-bot operation.

    This is intentionally simple for the UI: users see whether live use is allowed,
    why it is blocked, and which action fixes it. Paper Lab stays admin-only and is
    not part of the user mode decision.
    """
    runtime = as_dict(runtime_data)
    setting_map = as_dict(settings)
    store = as_dict(auth_store)
    record = _user_record(store, username)
    role = str(record.get('role') or 'user')
    package_id = str(record.get('package') or ('owner' if role == 'owner' else 'paper_only'))
    limits = package_limits(package_id, role)
    commission = build_user_commission_summary(store, username, runtime, audience='owner')
    billing = as_dict(commission.get('billing'))
    ledger = build_trade_ledger(runtime, setting_map, store, username)
    ledger_summary = as_dict(ledger.get('summary'))

    bot_running = bool(runtime.get('bot_running'))
    control_mode = str(runtime.get('bot_control_mode') or as_dict(setting_map.get('bot')).get('control_mode') or ('open' if bot_running else 'closed')).lower()
    if control_mode not in {'closed', 'open', 'automatic'}:
        control_mode = 'closed'
    emergency_lock = bool(runtime.get('emergency_lock'))
    rental_period = build_rental_period(record)
    waiting_mode = bool(rental_period.get('waiting_mode'))
    active = as_dict(record).get('active', True) is not False and rental_period.get('can_use_system') is True and waiting_mode is False
    live_enabled = bool(limits.get('live_enabled')) or role == 'owner'
    billing_pass = _billing_ok(billing, role)
    api_pass = _api_connected(api_summary) or role == 'owner'
    open_count = _open_live_trades(runtime)
    max_open = int(limits.get('max_open_trades') or 0)
    max_open_pass = role == 'owner' or max_open == 0 or open_count < max_open

    blockers: list[str] = []
    actions: list[str] = []
    if not active:
        blockers.append('user_inactive_or_rental_expired')
        actions.append('Owner kullanıcıyı aktif etmeli veya kiralama gününü yenilemeli.')
    if waiting_mode:
        blockers.append('rental_waiting_mode')
        actions.append('Kiralama süresi yenilenmeden bot canlı işlem açamaz.')
    if not billing_pass:
        blockers.append('billing_not_clear')
        actions.append('Ödeme durumu owner tarafından ödendi/trial yapılmalı.')
    if not live_enabled:
        blockers.append('package_live_disabled')
        actions.append('Canlı kullanım için Micro Live, Full Live veya Custom paket seçilmeli.')
    if not api_pass:
        blockers.append('binance_api_missing')
        actions.append('Kullanıcı Summary üzerinden Binance API bağlamalı ve test etmeli.')
    if emergency_lock:
        blockers.append('emergency_lock')
        actions.append('Owner acil durdurma kilidini kontrol etmeli.')
    if not max_open_pass:
        blockers.append('open_trade_limit_reached')
        actions.append('Açık işlem sayısı paket limitinin altına inmeli.')

    allowed = not blockers
    checklist = [
        {'area': 'Kullanıcı', 'current': 'Aktif' if active else 'Pasif / süre bitmiş', 'expected': 'Aktif ve kiralama süresi dolmamış olmalı', 'ok': active, 'action': 'Owner gün/aktiflik kontrolü'},
        {'area': 'Kiralama süresi', 'current': rental_period.get('label'), 'expected': 'Kalan gün olmalı', 'ok': rental_period.get('can_use_system') is True, 'action': rental_period.get('action')},
        {'area': 'Bekleme modu', 'current': 'Aktif' if waiting_mode else 'Kapalı', 'expected': 'Süre varsa kapalı olmalı; süre bitince kullanıcı beklemeye alınır', 'ok': not waiting_mode, 'action': 'Owner gün yeniler veya kullanıcı pasif kalır'},
        {'area': 'Paket', 'current': limits.get('label'), 'expected': 'Canlı kullanım izni olan paket', 'ok': live_enabled, 'action': 'Paket yönetimi'},
        {'area': 'Ödeme', 'current': billing.get('label') or billing.get('status'), 'expected': 'Ödenmiş veya trial', 'ok': billing_pass, 'action': 'Tahsilat / ödeme işaretleme'},
        {'area': 'Binance API', 'current': 'Bağlı' if api_pass else 'Eksik', 'expected': 'API bağlı ve secret güvenli', 'ok': api_pass, 'action': 'Summary API kutusu'},
        {'area': 'Bot', 'current': 'Çalışıyor' if bot_running else 'Kapalı', 'expected': 'Kullanıcı başlatabilir', 'ok': True, 'action': 'Summary bot kontrolü'},
        {'area': 'Bot modu', 'current': {'closed': 'Kapalı', 'open': 'Açık', 'automatic': 'Otomatik'}.get(control_mode, 'Kapalı'), 'expected': 'Kapalı / Açık / Otomatik seçimi Summary’de olmalı', 'ok': True, 'action': 'Kullanıcı seçer'},
        {'area': 'Acil kilit', 'current': 'Aktif' if emergency_lock else 'Kapalı', 'expected': 'Kapalı olmalı', 'ok': not emergency_lock, 'action': 'Risk kontrol'},
        {'area': 'Açık işlem limiti', 'current': f'{open_count}/{max_open or "sınırsız"}', 'expected': 'Paket limitini aşmamalı', 'ok': max_open_pass, 'action': 'Pozisyon azalt / paket yükselt'},
        {'area': 'Paper Lab', 'current': 'Admin laboratuvarı', 'expected': 'Son kullanıcı mod seçimi yok', 'ok': True, 'action': 'Admin izler, kullanıcı Summary kullanır'},
    ]
    return {
        'status': 'ok' if allowed else 'blocked',
        'decision': 'ALLOW_LIVE_SUMMARY' if allowed else 'BLOCK_LIVE_SUMMARY',
        'generated_at': now_iso(),
        'user': username,
        'live_mode_only': True,
        'shadow_removed_from_user_flow': True,
        'paper_lab_admin_only': True,
        'can_start_bot': allowed,
        'waiting_mode': waiting_mode,
        'bot_start_blocked_by_rental_period': waiting_mode or rental_period.get('can_use_system') is not True,
        'bot_running': bot_running,
        'bot_control_mode': control_mode,
        'automatic_mode_available': True,
        'blockers': blockers,
        'next_actions': actions,
        'package': limits,
        'billing': billing,
        'rental_period': rental_period,
        'commission': {
            'enabled': commission.get('commission_enabled'),
            'buy_rate_percent': commission.get('buy_rate_percent'),
            'sell_rate_percent': commission.get('sell_rate_percent'),
            'system_usage_cost_usdt': commission.get('system_usage_cost_usdt'),
            'owner_revenue_usdt': commission.get('platform_commission_usdt'),
            'net_pnl_usdt': commission.get('net_pnl_usdt'),
        },
        'ledger_summary': ledger_summary,
        'checklist': checklist,
        'simple_text': 'Canlı kullanım için paket, ödeme, API, acil kilit ve açık işlem limitleri geçmelidir.',
        'secret_values_returned': False,
    }


def build_rental_live_ops_guard_quality_report() -> dict:
    runtime = {'bot_running': False, 'open_positions': []}
    paid_store = {'users': {'tenant': {'role': 'user', 'active': True, 'package': 'micro_live', 'billing': {'status': 'paid', 'monthly_fee_usdt': 29, 'paid_usdt': 29}}}}
    blocked_store = {'users': {'tenant': {'role': 'user', 'active': True, 'package': 'paper_only', 'billing': {'status': 'pending', 'monthly_fee_usdt': 29, 'paid_usdt': 0}}}}
    api = {'connection': {'has_api_key': True, 'has_api_secret': True}}
    allowed = build_rental_live_ops_guard(runtime, {}, paid_store, 'tenant', api)
    blocked = build_rental_live_ops_guard(runtime, {}, blocked_store, 'tenant', {'connection': {}})
    expired_store = {'users': {'tenant': {'role': 'user', 'active': True, 'package': 'micro_live', 'billing': {'status': 'paid', 'monthly_fee_usdt': 29, 'paid_usdt': 29}, 'rental_period': {'days_limit': 1, 'started_at': '2020-01-01T00:00:00Z', 'expires_at': '2020-01-02T00:00:00Z'}}}}
    expired = build_rental_live_ops_guard(runtime, {}, expired_store, 'tenant', api)
    blockers = []
    if allowed.get('decision') != 'ALLOW_LIVE_SUMMARY':
        blockers.append('paid_micro_live_should_allow')
    if blocked.get('decision') != 'BLOCK_LIVE_SUMMARY':
        blockers.append('pending_paper_only_should_block')
    if expired.get('can_start_bot') is not False or 'rental_waiting_mode' not in expired.get('blockers', []):
        blockers.append('expired_rental_should_block_bot_start')
    if allowed.get('shadow_removed_from_user_flow') is not True or allowed.get('paper_lab_admin_only') is not True:
        blockers.append('mode_simplification_flags_missing')
    if allowed.get('automatic_mode_available') is not True:
        blockers.append('automatic_mode_missing')
    if allowed.get('secret_values_returned') is not False:
        blockers.append('secret_values_returned')
    return {
        'status': 'ok' if not blockers else 'blocked',
        'decision': 'PASS' if not blockers else 'BLOCKED',
        'blockers': blockers,
        'allowed_sample': allowed,
        'blocked_sample': blocked,
        'expired_sample': expired,
        'secret_values_returned': False,
    }
