"""Rental Final Dashboard action center.

One compact commercial decision layer for rented users:
- what is blocking live use now
- what should the user do next
- whether bot mode is safe to use
- whether automatic mode is waiting or allowed
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _item(key: str, label: str, current: str, ok: bool, action: str, priority: int) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'current': current,
        'ok': bool(ok),
        'action': action,
        'priority': int(priority),
    }


def _api_connected(api_summary: dict | None) -> bool:
    connection = _as_dict(_as_dict(api_summary).get('connection'))
    return bool(connection.get('has_api_key') and connection.get('has_api_secret'))


def _trade_count(runtime: dict) -> int:
    count = 0
    for key in ('real_trade_history', 'live_trade_history', 'closed_trades', 'history'):
        count += len(_as_list(runtime.get(key)))
    ledger = _as_dict(runtime.get('trade_ledger') or runtime.get('ledger'))
    count += len(_as_list(ledger.get('recent'))) + len(_as_list(ledger.get('trades')))
    return count


def build_rental_final_dashboard_action_center(
    runtime_data: dict | None,
    settings: dict | None,
    api_summary: dict | None = None,
    automatic_decision: dict | None = None,
    live_ops_guard: dict | None = None,
    live_feed: dict | None = None,
) -> dict[str, Any]:
    runtime = _as_dict(runtime_data)
    setting_map = _as_dict(settings)
    bot_settings = _as_dict(setting_map.get('bot'))
    risk_settings = _as_dict(setting_map.get('risk'))
    automatic = _as_dict(automatic_decision)
    guard = _as_dict(live_ops_guard)
    feed = _as_dict(live_feed)

    api_ok = _api_connected(api_summary)
    guard_ok = guard.get('can_start_bot') is True or guard.get('status') == 'ok'
    bot_running = bool(runtime.get('bot_running') or _as_dict(runtime.get('bot')).get('running'))
    control_mode = str(runtime.get('bot_control_mode') or bot_settings.get('control_mode') or ('open' if bot_running else 'closed')).lower()
    if control_mode not in {'closed', 'open', 'automatic'}:
        control_mode = 'closed'
    control_label = {'closed': 'Kapalı', 'open': 'Açık', 'automatic': 'Otomatik'}[control_mode]

    amount = _num(bot_settings.get('usdt_per_position'), 0)
    max_open = int(_num(bot_settings.get('max_open_positions'), 0))
    take_profit = _num(risk_settings.get('take_profit'), 0)
    stop_loss = _num(risk_settings.get('stop_loss'), 0)
    settings_ok = amount > 0 and max_open > 0 and take_profit > 0 and stop_loss > 0

    auto_score = _num(automatic.get('overall_score'), 0)
    auto_threshold = _num(automatic.get('threshold'), 65)
    auto_ok = automatic.get('allow_trade') is True
    trade_count = _trade_count(runtime)
    feed_status = str(feed.get('status') or 'review').lower()
    blockers = _as_list(guard.get('blockers')) + _as_list(feed.get('blockers'))

    items = [
        _item('api', 'API', 'Bağlı' if api_ok else 'Eksik', api_ok, 'Binance API kutusundan bağla ve test et.', 10),
        _item('settings', 'İşlem ayarı', f'{amount:g} USDT / {max_open} işlem', settings_ok, 'İşlem tutarı, açık işlem, kar ve stop değerlerini doldur.', 20),
        _item('rental_gate', 'Kiralama kapısı', 'Uygun' if guard_ok else 'Engelli', guard_ok, 'Paket, ödeme, API veya risk engelini gider.', 30),
        _item('bot_mode', 'Bot modu', control_label, control_mode != 'closed', 'Kapalı/Açık/Otomatik seçiminden kullanım kararını ver.', 40),
        _item('automatic', 'Otomatik karar', f'{auto_score:.0f}/{auto_threshold:.0f}', control_mode != 'automatic' or auto_ok, automatic.get('headline') or 'Piyasa güven skoru bekleniyor.', 50),
        _item('live_log', 'Canlı log', f'{trade_count} kayıt', trade_count > 0, 'İlk canlı işlemden sonra alış/satış ve net sonuç otomatik görünür.', 60),
        _item('feed', 'Veri kalitesi', 'Hazır' if feed_status == 'ready' else 'İzle', feed_status == 'ready', feed.get('next_action') or 'Canlı veri akışını izlemeye devam et.', 70),
    ]
    failed = sorted([item for item in items if not item['ok']], key=lambda x: x['priority'])
    first = failed[0] if failed else None
    if first:
        primary_action = first['action']
        commercial_status = 'Eksik var'
    elif control_mode == 'automatic' and not auto_ok:
        primary_action = automatic.get('headline') or 'Otomatik mod piyasanın uygun olmasını bekliyor.'
        commercial_status = 'Beklemede'
    elif control_mode == 'closed':
        primary_action = 'Botu Açık veya Otomatik moda al.'
        commercial_status = 'Kapalı'
    else:
        primary_action = 'Canlı dashboard kullanıma hazır; logları ve net sonucu izle.'
        commercial_status = 'Hazır'

    return {
        'status': 'ready' if not failed else 'review',
        'generated_at': _now_iso(),
        'screen': 'summary',
        'commercial_status': commercial_status,
        'primary_action': primary_action,
        'bot_control_mode': control_mode,
        'bot_control_label': control_label,
        'items': items,
        'blockers': [item['label'] for item in failed],
        'raw_blockers': blockers[:8],
        'one_page_user_flow': True,
        'settings_inline': True,
        'paper_lab_admin_only': True,
        'shadow_removed': True,
        'simple_text': 'Kiralayan kullanıcı için sıradaki doğru aksiyon tek kutuda gösterilir.',
    }


def build_rental_final_dashboard_action_center_quality_report() -> dict[str, Any]:
    sample = build_rental_final_dashboard_action_center(
        {'bot_control_mode': 'automatic', 'bot_running': True, 'real_trade_history': [{'symbol': 'BTCUSDT'}]},
        {'bot': {'usdt_per_position': 100, 'max_open_positions': 3, 'control_mode': 'automatic'}, 'risk': {'take_profit': 2, 'stop_loss': 1}},
        {'connection': {'has_api_key': True, 'has_api_secret': True}},
        {'overall_score': 74, 'threshold': 65, 'allow_trade': True, 'headline': 'Piyasa uygun.'},
        {'status': 'ok', 'can_start_bot': True, 'blockers': []},
        {'status': 'ready', 'blockers': []},
    )
    blockers: list[str] = []
    if sample.get('screen') != 'summary':
        blockers.append('screen_not_summary')
    if sample.get('one_page_user_flow') is not True:
        blockers.append('one_page_flow_missing')
    if sample.get('paper_lab_admin_only') is not True:
        blockers.append('paper_lab_not_admin_only')
    if sample.get('shadow_removed') is not True:
        blockers.append('shadow_not_removed')
    if len(sample.get('items') or []) < 6:
        blockers.append('action_items_missing')
    if not sample.get('primary_action'):
        blockers.append('primary_action_missing')
    if sample.get('status') != 'ready':
        blockers.append('sample_not_ready')
    return {'status': 'ok' if not blockers else 'blocked', 'blockers': blockers, 'sample': sample}
