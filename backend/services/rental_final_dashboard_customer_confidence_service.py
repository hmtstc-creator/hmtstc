"""Rental Final Dashboard customer confidence score.

One compact product score for rented users: am I ready, safe and correctly configured?
This is UX/readiness infrastructure; it does not send orders.
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
    return datetime.now(timezone.utc).isoformat()


def _score_item(key: str, label: str, ok: bool, current: str, expected: str, action: str, weight: int) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'ok': bool(ok),
        'current': current,
        'expected': expected,
        'action': action,
        'weight': int(weight),
        'score': int(weight) if ok else 0,
    }


def build_rental_final_dashboard_customer_confidence(
    runtime: dict | None,
    settings: dict | None,
    api_summary: dict | None,
    wallet_summary: dict | None,
    automatic_decision: dict | None,
    live_ops_guard: dict | None,
    live_feed: dict | None,
    action_center: dict | None,
    decision_timeline: dict | None,
) -> dict[str, Any]:
    runtime = _as_dict(runtime)
    settings = _as_dict(settings)
    api_summary = _as_dict(api_summary)
    wallet_summary = _as_dict(wallet_summary)
    automatic_decision = _as_dict(automatic_decision)
    live_ops_guard = _as_dict(live_ops_guard)
    live_feed = _as_dict(live_feed)
    action_center = _as_dict(action_center)
    decision_timeline = _as_dict(decision_timeline)

    bot_settings = _as_dict(settings.get('bot'))
    risk_settings = _as_dict(settings.get('risk'))
    wallet = _as_dict(wallet_summary.get('wallet'))
    connected = bool(api_summary.get('connected') or api_summary.get('status') == 'connected')
    usdt = _num(wallet.get('total_usdt') or wallet.get('total') or wallet.get('balance'), 0)
    control_mode = str(runtime.get('bot_control_mode') or bot_settings.get('control_mode') or 'closed').lower()
    if control_mode not in {'closed', 'open', 'automatic'}:
        control_mode = 'closed'
    auto_score = _num(automatic_decision.get('overall_score'), 0)
    auto_threshold = _num(automatic_decision.get('threshold'), 65)
    feed_status = str(live_feed.get('status') or 'review')
    guard_ok = live_ops_guard.get('can_start_bot') is True or live_ops_guard.get('status') == 'ok'
    timeline_events = _as_list(decision_timeline.get('events'))

    items = [
        _score_item('api', 'API', connected, 'Bağlı' if connected else 'Eksik', 'Binance API bağlı olmalı.', 'API bağla ve test et.', 18),
        _score_item('wallet', 'Bakiye', usdt > 0, f'{usdt:.2f} USDT', 'USDT bakiye okunmalı.', 'Bakiye/API bağlantısını kontrol et.', 12),
        _score_item('settings', 'İşlem ayarı', _num(bot_settings.get('usdt_per_position'), 0) > 0 and _num(bot_settings.get('max_open_positions'), 0) > 0, f"{_num(bot_settings.get('usdt_per_position'), 0):.2f} USDT / {_num(bot_settings.get('max_open_positions'), 0):.0f} lot", 'İşlem tutarı ve lot dolu olmalı.', 'Summary içindeki işlem ayarlarını doldur.', 14),
        _score_item('risk', 'Risk', _num(risk_settings.get('take_profit'), 0) > 0 and _num(risk_settings.get('stop_loss'), 0) > 0, f"TP {_num(risk_settings.get('take_profit'), 0):.2f} / SL {_num(risk_settings.get('stop_loss'), 0):.2f}", 'Kar alma ve stop loss tanımlı olmalı.', 'Risk ayarlarını doldur.', 12),
        _score_item('rental_gate', 'Kiralama kapısı', guard_ok, 'Uygun' if guard_ok else 'Engelli', 'Paket, ödeme, API ve risk kapısı geçmeli.', 'Sarı uyarıları çöz.', 18),
        _score_item('bot_mode', 'Bot modu', control_mode in {'open', 'automatic'}, {'closed':'Kapalı','open':'Açık','automatic':'Otomatik'}.get(control_mode, control_mode), 'Açık veya Otomatik seçilmeli.', 'Bot kontrolünden seçim yap.', 10),
        _score_item('auto', 'Otomatik panel', control_mode != 'automatic' or auto_score >= auto_threshold, f'{auto_score:.0f}/100', 'Otomatikte piyasa güveni eşik üstünde olmalı.', 'Skor düşükse bekle veya manuel Açık seç.', 8),
        _score_item('feed', 'Canlı kayıt', feed_status in {'ready', 'ok'}, live_feed.get('status_label') or feed_status, 'Canlı log/karar/PNL akışı hazır olmalı.', 'İlk canlı hareketi bekle veya veri kalitesini kontrol et.', 8),
    ]
    max_score = sum(item['weight'] for item in items) or 100
    score = round(sum(item['score'] for item in items) / max_score * 100)
    blockers = [item for item in items if not item['ok']]
    first_action = str(action_center.get('primary_action') or '').strip() or (blockers[0]['action'] if blockers else 'Dashboard hazır; canlı logları ve net karı izle.')
    if score >= 85:
        label = 'Hazır'
        tone = 'ok'
    elif score >= 65:
        label = 'İzle'
        tone = 'warn'
    else:
        label = 'Eksik var'
        tone = 'warn'
    return {
        'status': 'ready' if score >= 85 else 'review',
        'generated_at': _now_iso(),
        'screen': 'summary',
        'score': score,
        'label': label,
        'tone': tone,
        'items': items,
        'blockers': [item['key'] for item in blockers],
        'primary_action': first_action,
        'short_text': 'Kiralayan kullanıcı için tek sayfa hazırlık skoru.',
        'summary': f'{score}/100 - {label}',
        'timeline_event_count': len(timeline_events),
    }


def build_rental_final_dashboard_customer_confidence_quality_report() -> dict[str, Any]:
    sample = build_rental_final_dashboard_customer_confidence(
        {'bot_control_mode': 'automatic'},
        {'bot': {'usdt_per_position': 100, 'max_open_positions': 3, 'control_mode': 'automatic'}, 'risk': {'take_profit': 1.5, 'stop_loss': 0.8}},
        {'connected': True},
        {'wallet': {'total_usdt': 1000}},
        {'overall_score': 78, 'threshold': 65},
        {'status': 'ok', 'can_start_bot': True},
        {'status': 'ready', 'status_label': 'Hazır'},
        {'primary_action': 'Canlı logları izle.'},
        {'events': [{'title': 'Otomatik karar aktif'}]},
    )
    blockers: list[str] = []
    if sample.get('screen') != 'summary':
        blockers.append('screen_not_summary')
    if sample.get('score', 0) < 80:
        blockers.append('score_contract_weak')
    if len(sample.get('items') or []) < 8:
        blockers.append('items_missing')
    if not sample.get('primary_action'):
        blockers.append('primary_action_missing')
    return {'status': 'ok' if not blockers else 'blocked', 'blockers': blockers, 'sample': sample}
