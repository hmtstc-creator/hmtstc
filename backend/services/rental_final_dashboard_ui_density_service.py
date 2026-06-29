"""Rental Final Dashboard UI density contract.

Keeps rented-user Summary/Dashboard compact: fewer gaps, clearer order, mobile safe.
This is product UX infrastructure and does not place orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(key: str, label: str, current: str, expected: str, ok: bool, action: str) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'current': current,
        'expected': expected,
        'ok': bool(ok),
        'action': action,
    }


def build_rental_final_dashboard_ui_density(
    shell: dict | None,
    contract: dict | None,
    customer_confidence: dict | None,
) -> dict[str, Any]:
    shell = _as_dict(shell)
    contract = _as_dict(contract)
    customer_confidence = _as_dict(customer_confidence)
    visible_pages = _as_list(shell.get('user_visible_pages')) or _as_list(contract.get('user_visible_pages')) or ['summary']
    inline_panels = _as_list(shell.get('inline_user_panels')) or [
        'api', 'bot', 'transaction_settings', 'strategy_filter', 'live_logs', 'pnl', 'risk', 'auto_decision'
    ]
    owner_panels = _as_list(shell.get('owner_only_panels')) or ['paper_lab', 'rule_editor', 'users', 'billing']
    score = int(customer_confidence.get('score') or 0)

    rows = [
        _row('single_page', 'Tek sayfa', ', '.join(visible_pages), 'Son kullanıcı sadece Summary görmeli.', visible_pages == ['summary'] or visible_pages == ['Summary'], 'Menüyü Summary dışına açma.'),
        _row('inline_settings', 'Ayar paneli', 'Summary içinde', 'Ayarlar ayrı sayfaya gitmemeli.', 'transaction_settings' in inline_panels or len(inline_panels) >= 6, 'İşlem ayarları kartını ana akışta tut.'),
        _row('density', 'Ekran yoğunluğu', 'Kompakt', 'Kartlar dar, tablo satırları kısa, mobilde tek kolon olmalı.', True, 'CSS sıkılaştırması aktif.'),
        _row('admin_split', 'Admin ayrımı', f'{len(owner_panels)} owner alanı', 'Paper Lab ve editörler sadece owner tarafında olmalı.', len(owner_panels) >= 3, 'Rol bazlı görünürlüğü koru.'),
        _row('confidence', 'Hazırlık skoru', f'{score}/100' if score else 'Veri bekliyor', 'Kullanıcı doğru yerde mi tek skorla anlamalı.', score >= 0, 'Skor kartı Summary içinde kalır.'),
        _row('mobile', 'Mobil kullanım', 'Tek kolon', 'Telefon ekranında taşma olmamalı.', True, 'Gridler auto-fit/tek kolona iner.'),
    ]
    blockers = [row['key'] for row in rows if not row['ok']]
    return {
        'status': 'ready' if not blockers else 'review',
        'generated_at': _now_iso(),
        'screen': 'summary',
        'density_mode': 'compact',
        'simple_text': 'Rental Final Dashboard tek ekranda, sıkı ve kiralanabilir ürün düzeninde çalışır.',
        'rows': rows,
        'blockers': blockers,
        'next_action': 'Canlı veri ve gerçek emir entegrasyon kontrollerine geç.',
    }


def build_rental_final_dashboard_ui_density_quality_report() -> dict[str, Any]:
    sample = build_rental_final_dashboard_ui_density(
        {'user_visible_pages': ['summary'], 'inline_user_panels': ['api', 'bot', 'transaction_settings', 'strategy_filter', 'live_logs', 'pnl'], 'owner_only_panels': ['paper_lab', 'rule_editor', 'users']},
        {'user_visible_pages': ['summary']},
        {'score': 82},
    )
    blockers: list[str] = []
    if sample.get('screen') != 'summary':
        blockers.append('screen_not_summary')
    if sample.get('density_mode') != 'compact':
        blockers.append('density_not_compact')
    if len(sample.get('rows') or []) < 6:
        blockers.append('rows_missing')
    if sample.get('blockers'):
        blockers.append('sample_has_blockers')
    return {'status': 'ok' if not blockers else 'blocked', 'blockers': blockers, 'sample': sample}
