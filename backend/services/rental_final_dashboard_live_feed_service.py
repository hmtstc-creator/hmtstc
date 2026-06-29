"""Rental Final Dashboard live feed quality contract.

Keeps the rented user screen focused on the only commercial question:
Is the live dashboard showing enough real operational evidence right now?
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


def _row(area: str, current: str, expected: str, ok: bool, action: str) -> dict[str, Any]:
    return {"area": area, "current": current, "expected": expected, "ok": bool(ok), "action": action}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _trade_count(runtime: dict) -> int:
    total = 0
    for key in ("real_trade_history", "live_trade_history", "closed_trades", "history", "trade_ledger"):
        value = runtime.get(key)
        if isinstance(value, list):
            total += len(value)
        elif isinstance(value, dict):
            total += len(_as_list(value.get("recent"))) + len(_as_list(value.get("trades")))
    return total


def build_rental_final_dashboard_live_feed(
    runtime_data: dict | None,
    settings: dict | None,
    api_summary: dict | None = None,
    wallet_summary: dict | None = None,
    automatic_decision: dict | None = None,
    live_ops_guard: dict | None = None,
) -> dict[str, Any]:
    runtime = _as_dict(runtime_data)
    setting_map = _as_dict(settings)
    api = _as_dict(api_summary)
    wallet_payload = _as_dict(wallet_summary)
    wallet = _as_dict(wallet_payload.get("wallet"))
    automatic = _as_dict(automatic_decision)
    guard = _as_dict(live_ops_guard)
    bot_settings = _as_dict(setting_map.get("bot"))
    risk_settings = _as_dict(setting_map.get("risk"))

    api_connection = _as_dict(api.get("connection"))
    api_connected = bool(api_connection.get("has_api_key") and api_connection.get("has_api_secret"))
    wallet_total = _num(wallet.get("wallet_total_usdt") or wallet.get("total_usdt"), 0)
    available = _num(wallet.get("available_usdt"), 0)
    last_tick = runtime.get("last_tick") or _as_dict(runtime.get("bot")).get("last_tick") or runtime.get("updated_at")
    control_mode = str(runtime.get("bot_control_mode") or bot_settings.get("control_mode") or "closed").lower()
    if control_mode not in {"closed", "open", "automatic"}:
        control_mode = "closed"
    trade_count = _trade_count(runtime)
    auto_score = _num(automatic.get("overall_score"), 0)
    decision_reason = automatic.get("headline") or automatic.get("decision_reason") or automatic.get("simple_rule") or "Otomatik karar verisi bekleniyor."
    guard_ok = guard.get("can_start_bot") is True or guard.get("status") == "ok"
    fee_ready = bool(runtime.get("commission") or runtime.get("trade_ledger") or runtime.get("ledger"))
    amount = _num(bot_settings.get("usdt_per_position"), 0)
    max_open = int(_num(bot_settings.get("max_open_positions"), 0))
    take_profit = _num(risk_settings.get("take_profit"), 0)
    stop_loss = _num(risk_settings.get("stop_loss"), 0)

    rows = [
        _row("API canlı veri", "Bağlı" if api_connected else "Eksik", "Kullanıcı API durumunu Summary üzerinde net görmeli.", api_connected, "API kutusundan kaydet/test et."),
        _row("Bakiye beslemesi", f"{wallet_total:.2f} USDT", "Toplam ve kullanılabilir bakiye dolu olmalı.", wallet_total > 0 or available > 0, "Binance wallet okumasını doğrula."),
        _row("Bot hareketi", str(last_tick or "Tick yok"), "Bot son hareketi veya bekleme nedeni görünmeli.", bool(last_tick) or control_mode == "closed", "Bot Açık/Otomatik seçilince tick beklenir."),
        _row("Canlı al-sat logu", f"{trade_count} kayıt", "Kullanıcı alım/satım, fee ve net sonucu görmeli.", trade_count > 0, "İlk canlı işlem sonrası otomatik dolar."),
        _row("Otomatik gerekçe", f"{auto_score:.0f}/100", "Otomatik modda neden girdi/girmedi açıklanmalı.", control_mode != "automatic" or auto_score > 0, str(decision_reason)),
        _row("İşlem parametresi", f"{amount:g} USDT / {max_open} işlem", "Tutar, lot, TP ve SL dolu olmalı.", amount > 0 and max_open > 0 and take_profit > 0 and stop_loss > 0, "Summary içi işlem ayarlarını doldur."),
        _row("Risk/kiralama kapısı", "Uygun" if guard_ok else "Engelli", "Paket, ödeme, API, risk ve acil kilit geçmeli.", guard_ok, "Eksikleri kontrol özeti gösterir."),
        _row("Net PnL hesabı", "Bağlı" if fee_ready else "Veri bekliyor", "Brüt kar, Binance fee, sistem payı ve net sonuç birlikte hesaplanmalı.", fee_ready, "Ledger/komisyon akışı ilk işlemden sonra dolar."),
    ]
    blockers = [row["area"] for row in rows if not row["ok"]]
    return {
        "status": "ready" if not blockers else "review",
        "generated_at": _now_iso(),
        "screen": "summary",
        "rows": rows,
        "blockers": blockers,
        "live_log_required": True,
        "automatic_reason_required": True,
        "settings_inline_required": True,
        "paper_visible_to_user": False,
        "shadow_visible_to_user": False,
        "simple_text": "Kiralayan kullanıcı tek ekranda canlı veri, işlem ayarı, bot kararı, log ve net sonucu görmelidir.",
        "next_action": rows[[i for i, r in enumerate(rows) if not r["ok"]][0]]["action"] if blockers else "Canlı dashboard veri akışı kiralık kullanım için hazır.",
    }


def build_rental_final_dashboard_live_feed_quality_report() -> dict[str, Any]:
    sample = build_rental_final_dashboard_live_feed(
        {"bot_control_mode": "automatic", "last_tick": "2026-05-29T19:00:00Z", "real_trade_history": [{"symbol": "BTCUSDT"}], "commission": {"platform_commission_usdt": 0.1}},
        {"bot": {"usdt_per_position": 100, "max_open_positions": 3, "control_mode": "automatic"}, "risk": {"take_profit": 2, "stop_loss": 1}},
        {"connection": {"has_api_key": True, "has_api_secret": True}},
        {"wallet": {"wallet_total_usdt": 1000, "available_usdt": 900}},
        {"overall_score": 74, "headline": "Piyasa uygun."},
        {"status": "ok", "can_start_bot": True},
    )
    blockers: list[str] = []
    if sample.get("screen") != "summary":
        blockers.append("screen_not_summary")
    if sample.get("paper_visible_to_user") is not False:
        blockers.append("paper_visible_to_user")
    if sample.get("shadow_visible_to_user") is not False:
        blockers.append("shadow_visible_to_user")
    if sample.get("live_log_required") is not True:
        blockers.append("live_log_not_required")
    if sample.get("automatic_reason_required") is not True:
        blockers.append("automatic_reason_not_required")
    if sample.get("settings_inline_required") is not True:
        blockers.append("settings_not_inline")
    if sample.get("status") != "ready":
        blockers.append("sample_not_ready")
    return {"status": "ok" if not blockers else "blocked", "blockers": blockers, "sample": sample}
