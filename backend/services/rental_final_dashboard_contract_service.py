from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _ok_row(area: str, current: str, expected: str, ok: bool, action: str) -> dict:
    return {
        'area': area,
        'current': current,
        'expected': expected,
        'ok': bool(ok),
        'action': action,
    }


def _api_connected(api_summary: dict | None) -> bool:
    connection = _as_dict(_as_dict(api_summary).get('connection'))
    return bool(connection.get('has_api_key') and connection.get('has_api_secret'))


def _trade_rows(runtime_data: dict) -> list:
    rows: list = []
    for key in ('real_trade_history', 'live_trade_history', 'closed_trades', 'history'):
        rows.extend(_as_list(runtime_data.get(key)))
    return rows


def build_rental_final_dashboard_contract(
    runtime_data: dict | None,
    settings: dict | None,
    username: str,
    api_summary: dict | None = None,
    live_ops_guard: dict | None = None,
    automatic_decision: dict | None = None,
) -> dict:
    """Single-page commercial dashboard contract.

    The rented user should not navigate product pages. This contract keeps the UI
    focused on one Summary/Dashboard screen and gives the frontend one compact
    truth table: what is visible, what must be true, and the next action.
    """
    runtime = _as_dict(runtime_data)
    setting_map = _as_dict(settings)
    bot_settings = _as_dict(setting_map.get('bot'))
    risk_settings = _as_dict(setting_map.get('risk'))
    coin_filter = _as_dict(setting_map.get('coin_filter'))
    guard = _as_dict(live_ops_guard)
    automatic = _as_dict(automatic_decision)

    bot_running = bool(runtime.get('bot_running'))
    control_mode = str(runtime.get('bot_control_mode') or bot_settings.get('control_mode') or ('open' if bot_running else 'closed')).lower()
    if control_mode not in {'closed', 'open', 'automatic'}:
        control_mode = 'closed'
    control_label = {'closed': 'Kapalı', 'open': 'Açık', 'automatic': 'Otomatik'}[control_mode]

    usdt_per_position = _num(bot_settings.get('usdt_per_position'), 0)
    max_open_positions = int(_num(bot_settings.get('max_open_positions'), 0))
    take_profit = _num(risk_settings.get('take_profit'), 0)
    stop_loss = _num(risk_settings.get('stop_loss'), 0)
    symbols = coin_filter.get('included_symbols') or bot_settings.get('symbols') or bot_settings.get('allowed_symbols') or ''
    symbols_ok = bool(str(symbols).strip())
    transaction_settings_ok = usdt_per_position > 0 and max_open_positions > 0 and take_profit > 0 and stop_loss > 0 and symbols_ok

    strategy_source = _as_list(setting_map.get('strategies')) or _as_list(_as_dict(runtime.get('rules')).get('strategies'))
    filter_source = _as_list(setting_map.get('filters')) or _as_list(_as_dict(runtime.get('rules')).get('filters'))
    selected_strategy_ids = _as_list(setting_map.get('selected_strategy_ids'))
    selected_filter_ids = _as_list(setting_map.get('selected_filter_ids'))
    active_strategy_count = len(selected_strategy_ids) if selected_strategy_ids else len([s for s in strategy_source if _as_dict(s).get('enabled', True) is not False])
    active_filter_count = len(selected_filter_ids) if selected_filter_ids else len([f for f in filter_source if _as_dict(f).get('enabled', True) is not False])

    api_ok = _api_connected(api_summary)
    guard_ok = guard.get('can_start_bot') is True or guard.get('status') == 'ok'
    trade_count = len(_trade_rows(runtime))
    auto_score = _num(automatic.get('overall_score'), 0)
    auto_ok = control_mode != 'automatic' or automatic.get('allow_trade') is True

    readiness_rows = [
        _ok_row('Ekran yapısı', 'Tek Summary/Dashboard', 'Son kullanıcı ayrı sayfa açmadan tüm işini görmeli.', True, 'Menü sade tutulur.'),
        _ok_row('Bot modu', control_label, 'Kapalı / Açık / Otomatik seçenekleri Summary’de olmalı.', True, 'Kullanıcı tek yerden seçer.'),
        _ok_row('API bağlantısı', 'Bağlı' if api_ok else 'Eksik', 'Binance API bağlı ve test edilmiş olmalı.', api_ok, 'Summary içindeki API kutusundan bağla/test et.'),
        _ok_row('İşlem ayarları', f'{usdt_per_position:g} USDT / {max_open_positions} işlem', 'Tutar, lot, kar/stop ve coin listesi dolu olmalı.', transaction_settings_ok, 'Summary içi işlem ayarları panelini doldur.'),
        _ok_row('Strateji seçimi', f'{active_strategy_count} açık', 'En az 1 strateji açık olmalı.', active_strategy_count > 0, 'Kullanıcı sadece aç/kapat yapar.'),
        _ok_row('Filtre seçimi', f'{active_filter_count} açık', 'En az 1 filtre açık olmalı.', active_filter_count > 0, 'Kullanıcı sadece aç/kapat yapar.'),
        _ok_row('Canlı log', f'{trade_count} kayıt', 'Alım-satım kayıtları Summary’de görünmeli.', trade_count > 0, 'İlk canlı işlem sonrası otomatik dolar.'),
        _ok_row('Otomatik karar', f'{auto_score:.0f}/100' if auto_score else 'Veri bekliyor', 'Otomatikte piyasa güveni eşik üstünde olmalı.', auto_ok, automatic.get('headline') or 'Derin AI sonraki pakette geliştirilecek.'),
        _ok_row('Canlı kullanım kapısı', 'Uygun' if guard_ok else 'Engelli', 'Paket, ödeme, API, acil kilit ve limitler geçmeli.', guard_ok, 'Eksik varsa owner veya kullanıcı aksiyonu gerekir.'),
        _ok_row('Paper Lab', 'Admin laboratuvarı', 'Son kullanıcı paper/mod seçimi görmemeli.', True, 'Paper testleri admin karar alanında kalır.'),
    ]
    failed = [row for row in readiness_rows if not row['ok']]
    first_failed = failed[0] if failed else None
    return {
        'status': 'ready' if not failed else 'review',
        'generated_at': _now_iso(),
        'user': username,
        'screen_model': 'single_summary_dashboard',
        'user_visible_pages': ['summary'],
        'user_hidden_pages': ['settings', 'paperLabModels', 'ruleEditor', 'users', 'reports', 'logs', 'dashboard', 'systemStatus'],
        'admin_only_pages': ['paperLabModels', 'ruleEditor', 'users', 'reports', 'logs'],
        'summary_is_live_dashboard': True,
        'settings_are_inline': True,
        'paper_lab_admin_only': True,
        'shadow_removed': True,
        'mode_selection_removed': True,
        'bot_control_modes': ['closed', 'open', 'automatic'],
        'current_bot_control_mode': control_mode,
        'current_bot_control_label': control_label,
        'ready_for_rental_use': not failed,
        'readiness_rows': readiness_rows,
        'blockers': [row['area'] for row in failed],
        'next_action': first_failed['action'] if first_failed else 'Kiralayan kullanıcı tek Summary ekranından kullanıma hazır.',
        'simple_text': 'Kiralayan kullanıcı için ürün tek Summary ekranıdır; ayarlar inline panelde, Paper Lab sadece admindedir.',
        'secret_values_returned': False,
    }


def build_rental_final_dashboard_contract_quality_report() -> dict:
    runtime = {'bot_running': True, 'bot_control_mode': 'automatic', 'real_trade_history': [{'status': 'filled'}]}
    settings = {
        'bot': {'usdt_per_position': 100, 'max_open_positions': 3, 'control_mode': 'automatic'},
        'risk': {'take_profit': 2, 'stop_loss': 1},
        'coin_filter': {'included_symbols': 'BTCUSDT,ETHUSDT'},
        'selected_strategy_ids': ['s1'],
        'selected_filter_ids': ['f1'],
    }
    contract = build_rental_final_dashboard_contract(
        runtime,
        settings,
        'tenant',
        {'connection': {'has_api_key': True, 'has_api_secret': True}},
        {'status': 'ok', 'can_start_bot': True},
        {'overall_score': 72, 'allow_trade': True, 'headline': 'Piyasa uygun.'},
    )
    blockers: list[str] = []
    if contract.get('screen_model') != 'single_summary_dashboard':
        blockers.append('screen_model_not_single_summary')
    if contract.get('user_visible_pages') != ['summary']:
        blockers.append('user_visible_pages_not_summary_only')
    if contract.get('settings_are_inline') is not True:
        blockers.append('settings_not_inline')
    if contract.get('paper_lab_admin_only') is not True:
        blockers.append('paper_lab_not_admin_only')
    if contract.get('shadow_removed') is not True or contract.get('mode_selection_removed') is not True:
        blockers.append('mode_simplification_missing')
    if contract.get('bot_control_modes') != ['closed', 'open', 'automatic']:
        blockers.append('bot_control_modes_wrong')
    if contract.get('secret_values_returned') is not False:
        blockers.append('secret_values_returned')
    return {'status': 'ok' if not blockers else 'blocked', 'blockers': blockers, 'sample': contract}
