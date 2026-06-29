"""Rental Final Dashboard decision timeline.

Compact one-page explanation feed for rented users:
- why bot entered / did not enter
- what automatic mode is waiting for
- what the next visible state means
This is product UX infrastructure, not the deep AI engine.
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


def _event(kind: str, title: str, detail: str, tone: str = 'info', score: float | None = None, source: str = 'Sistem') -> dict[str, Any]:
    return {
        'kind': kind,
        'title': title,
        'detail': detail,
        'tone': tone,
        'score': score,
        'source': source,
    }


def _recent_trade_events(runtime: dict) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    sources = []
    for key in ('real_trade_history', 'live_trade_history', 'closed_trades', 'history'):
        sources.extend(_as_list(runtime.get(key)))
    ledger = _as_dict(runtime.get('trade_ledger') or runtime.get('ledger'))
    sources.extend(_as_list(ledger.get('recent')))
    sources.extend(_as_list(ledger.get('trades')))
    for item in sources[-6:]:
        row = _as_dict(item)
        symbol = str(row.get('symbol') or row.get('coin') or '-').upper()
        status = str(row.get('status') or row.get('side') or row.get('action') or 'İşlem').strip()
        pnl = _num(row.get('net_pnl') or row.get('pnl') or row.get('realized_pnl'), 0)
        reason = str(row.get('decision_reason') or row.get('reason') or row.get('note') or '').strip()
        title = f'{symbol} · {status}'
        detail = reason or ('Net sonuç pozitif.' if pnl > 0 else 'İşlem sonucu kayda alındı.')
        tone = 'ok' if pnl >= 0 else 'warn'
        events.append(_event('trade', title, detail, tone, None, 'Canlı log'))
    return events


def _recent_log_events(runtime: dict) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    logs = _as_list(runtime.get('logs')) + _as_list(runtime.get('audit_logs'))
    for item in logs[-6:]:
        row = _as_dict(item)
        message = str(row.get('message') or row.get('text') or row.get('event') or '').strip()
        if not message:
            continue
        lower = message.lower()
        if any(token in lower for token in ('market', 'skor', 'risk', 'engel', 'bekle', 'işlem', 'order')):
            tone = 'warn' if any(token in lower for token in ('engel', 'risk', 'bekle', 'redd')) else 'info'
            events.append(_event('log', row.get('event') or 'Bot kaydı', message, tone, None, 'Runtime'))
    return events


def build_rental_final_dashboard_decision_timeline(
    runtime_data: dict | None,
    settings: dict | None,
    automatic_decision: dict | None = None,
    live_ops_guard: dict | None = None,
    live_feed: dict | None = None,
    action_center: dict | None = None,
) -> dict[str, Any]:
    runtime = _as_dict(runtime_data)
    automatic = _as_dict(automatic_decision)
    guard = _as_dict(live_ops_guard)
    feed = _as_dict(live_feed)
    action = _as_dict(action_center)
    setting_map = _as_dict(settings)
    bot_settings = _as_dict(setting_map.get('bot'))

    control_mode = str(runtime.get('bot_control_mode') or bot_settings.get('control_mode') or automatic.get('control_mode') or 'closed').lower()
    if control_mode not in {'closed', 'open', 'automatic'}:
        control_mode = 'closed'
    score = _num(automatic.get('overall_score'), 0)
    threshold = _num(automatic.get('threshold'), 65)
    allow_trade = automatic.get('allow_trade') is True

    events: list[dict[str, Any]] = []
    if control_mode == 'automatic':
        events.append(_event(
            'automatic',
            'Otomatik karar aktif',
            automatic.get('headline') or ('Piyasa uygun, bot işlem arayabilir.' if allow_trade else 'Piyasa güveni düşük, bot yeni işlem bekletir.'),
            'ok' if allow_trade else 'warn',
            score,
            'Otomatik panel',
        ))
    elif control_mode == 'open':
        events.append(_event('manual_open', 'Bot manuel açık', 'Bot strateji, filtre ve risk kapısından geçen fırsatları arar.', 'ok', None, 'Bot kontrolü'))
    else:
        events.append(_event('closed', 'Bot kapalı', 'Yeni işlem açılmaz. Kullanıcı Açık veya Otomatik seçebilir.', 'off', None, 'Bot kontrolü'))

    if guard.get('can_start_bot') is False or guard.get('status') not in (None, 'ok'):
        blockers = _as_list(guard.get('blockers'))
        events.append(_event('guard', 'Canlı kullanım engeli', ' · '.join(map(str, blockers[:3])) or 'Paket, ödeme, API veya risk kapısı kontrol edilmeli.', 'warn', None, 'Kiralama kapısı'))
    else:
        events.append(_event('guard', 'Canlı kullanım kapısı uygun', 'Paket, ödeme, API ve risk kontrolü bot başlatma için uygundur.', 'ok', None, 'Kiralama kapısı'))

    primary_action = str(action.get('primary_action') or '').strip()
    if primary_action:
        events.append(_event('next_action', 'Sıradaki aksiyon', primary_action, 'info', None, 'Aksiyon merkezi'))

    events.extend(_recent_trade_events(runtime))
    events.extend(_recent_log_events(runtime))

    if len(events) < 5:
        feed_status = str(feed.get('status') or 'review')
        events.append(_event('feed', 'Canlı veri bekleniyor', feed.get('next_action') or 'İlk canlı veri geldikçe karar, log ve PnL geçmişi burada görünür.', 'info' if feed_status == 'ready' else 'warn', None, 'Canlı veri'))

    visible = events[:8]
    blocked = any(e.get('tone') == 'warn' for e in visible)
    return {
        'status': 'review' if blocked else 'ready',
        'generated_at': _now_iso(),
        'screen': 'summary',
        'control_mode': control_mode,
        'overall_score': score,
        'threshold': threshold,
        'events': visible,
        'simple_text': 'Botun neden işlem açtığı, beklediği veya engellendiği tek mini akışta gösterilir.',
        'next_action': 'Uyarı varsa ilk sarı satırı çöz; yoksa canlı log ve net karı izle.',
        'ai_engine_status': 'visual_contract_ready',
    }


def build_rental_final_dashboard_decision_timeline_quality_report() -> dict[str, Any]:
    sample = build_rental_final_dashboard_decision_timeline(
        {'bot_control_mode': 'automatic', 'real_trade_history': [{'symbol': 'BTCUSDT', 'status': 'Alım yapıldı', 'pnl': 1.2, 'decision_reason': 'Piyasa skoru uygun.'}]},
        {'bot': {'control_mode': 'automatic'}},
        {'overall_score': 76, 'threshold': 65, 'allow_trade': True, 'headline': 'Piyasa uygun.'},
        {'status': 'ok', 'can_start_bot': True, 'blockers': []},
        {'status': 'ready', 'next_action': 'Canlı veri akıyor.'},
        {'primary_action': 'Logları izle.'},
    )
    blockers: list[str] = []
    if sample.get('screen') != 'summary':
        blockers.append('screen_not_summary')
    if len(sample.get('events') or []) < 4:
        blockers.append('timeline_events_missing')
    if sample.get('ai_engine_status') != 'visual_contract_ready':
        blockers.append('visual_contract_missing')
    if not sample.get('simple_text'):
        blockers.append('simple_text_missing')
    return {'status': 'ok' if not blockers else 'blocked', 'blockers': blockers, 'sample': sample}
