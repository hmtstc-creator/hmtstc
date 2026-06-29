from __future__ import annotations

from typing import Any

from core.storage import now_iso
from services.binance_service import load_binance_runtime_config
from services.real_trade_service import build_binance_health, build_real_readiness
from services.strategy_filter_toggle_service import get_strategy_filter_toggles


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("USDT", "").replace("%", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return fallback


def _status_from_blockers(blockers: list[str]) -> str:
    return "ready" if not blockers else "blocked"


def _simple_item(key: str, title: str, ok: bool, good: str, bad: str, detail: str | None = None) -> dict:
    return {
        "key": key,
        "title": title,
        "status": "ok" if ok else "blocked",
        "ok": bool(ok),
        "simple_text": good if ok else bad,
        "detail": detail or "",
    }


def build_live_trade_readiness_check(data: dict, settings: dict, user: str = "default") -> dict:
    """Build a user-facing pre-live checklist without placing real orders.

    This service intentionally performs no order submission. It summarizes the
    existing Binance/runtime/readiness safeguards in plain language so the live
    trading page can show one clear answer: ready, test-only, or blocked.
    """
    runtime = load_binance_runtime_config()
    readiness = build_real_readiness(data, settings)
    binance = readiness.get("binance") or build_binance_health()
    toggles = get_strategy_filter_toggles(user)

    bot = settings.get("bot") or {}
    risk = settings.get("risk") or {}
    selected_strategies = toggles.get("selected_strategy_ids") or []
    selected_filters = toggles.get("selected_filter_ids") or []

    max_order = _safe_float(runtime.max_order_usdt, _safe_float(bot.get("usdt_per_position"), 0.0))
    daily_loss = _safe_float(runtime.daily_loss_limit_usdt, _safe_float(risk.get("daily_loss_limit"), 0.0))
    max_open = int(runtime.max_open_positions or bot.get("max_open_positions") or 0)

    account_access = bool((binance.get("permission") or {}).get("account_access") or (binance.get("summary") or {}).get("account_access"))
    public_ok = binance.get("status") == "ok" or bool((binance.get("summary") or {}).get("public_connection"))
    has_credentials = bool(runtime.has_api_key and runtime.has_api_secret)
    testnet_or_dry = bool(runtime.testnet or runtime.real_trading_dry_run or runtime.mode == "testnet")
    real_enabled = bool(runtime.real_trading_enabled and not runtime.real_trading_dry_run)
    live_unlocked = bool((readiness.get("real_state") or {}).get("unlock_valid"))
    blockers = list(readiness.get("blockers") or [])

    items = [
        _simple_item(
            "api_key",
            "Binance anahtarı",
            has_credentials,
            "Anahtar var.",
            "Binance anahtarı eksik.",
            "API key ve secret backend ortamında olmalı; secret frontend'e dönmez.",
        ),
        _simple_item(
            "public_connection",
            "Binance bağlantısı",
            public_ok,
            "Binance ile konuşabiliyoruz.",
            "Binance bağlantısı hazır değil.",
            "Önce public bağlantı ve server time kontrol edilir.",
        ),
        _simple_item(
            "account_access",
            "Bakiye okuma",
            account_access,
            "Bakiye okunabiliyor.",
            "Bakiye okunamıyor.",
            "Canlı işlem öncesi hesap okuma izni gerekir.",
        ),
        _simple_item(
            "withdraw_disabled_design",
            "Para çekme güvenliği",
            True,
            "Bu sistem para çekme işlemi yapmaz.",
            "Para çekme riski var.",
            "Kodda withdraw, futures ve margin emir uçları yoktur.",
        ),
        _simple_item(
            "mode_guard",
            "Gerçek para modu",
            real_enabled,
            "Gerçek para modu açılabilir.",
            "Şu an test/güvenli modda.",
            "Testnet veya dry-run aktifse gerçek emir gönderilmez.",
        ),
        _simple_item(
            "owner_unlock",
            "Son onay",
            live_unlocked,
            "Son onay verilmiş.",
            "Son onay yok veya süresi dolmuş.",
            "Gerçek emir için kısa süreli owner onayı gerekir.",
        ),
        _simple_item(
            "risk_limits",
            "Para sınırları",
            max_order > 0 and daily_loss > 0 and max_open > 0,
            "Para sınırları dolu.",
            "Para sınırları eksik.",
            f"İşlem sınırı: {max_order:.2f} USDT, günlük zarar sınırı: {daily_loss:.2f} USDT, açık işlem sınırı: {max_open}.",
        ),
        _simple_item(
            "strategy_filter_selection",
            "Açık fikirler",
            bool(selected_strategies) and bool(selected_filters),
            "Strateji ve filtre seçili.",
            "Strateji veya filtre seçimi eksik.",
            "Botun hangi fikir ve hangi kontrolle çalışacağı net olmalı.",
        ),
        _simple_item(
            "emergency_lock",
            "Acil durdurma",
            "emergency_lock_active" not in blockers,
            "Acil durdurma kapalı.",
            "Acil durdurma aktif.",
            "Acil durdurma aktifken canlı emir gönderilmez.",
        ),
    ]

    item_blockers = [item["key"] for item in items if not item.get("ok")]
    all_blockers = sorted(set(blockers + item_blockers))
    ready_for_real = bool(readiness.get("ready_for_real_order") and not item_blockers)
    ready_for_dry_run = bool(readiness.get("ready_for_dry_run") or (has_credentials and public_ok))

    if ready_for_real:
        simple_status = "Canlıya hazır"
        decision = "Gerçek para açılabilir. Yine de küçük tutarla başla."
    elif ready_for_dry_run:
        simple_status = "Teste hazır"
        decision = "Gerçek para yerine prova modunda test et."
    else:
        simple_status = "Hazır değil"
        decision = "Eksik maddeleri tamamlamadan canlıya geçme."

    return {
        "status": _status_from_blockers([] if ready_for_real else all_blockers),
        "user": user,
        "simple_status": simple_status,
        "decision": decision,
        "ready_for_real_order": ready_for_real,
        "ready_for_dry_run": ready_for_dry_run,
        "mode": {
            "binance_mode": runtime.mode,
            "testnet": bool(runtime.testnet),
            "dry_run": bool(runtime.real_trading_dry_run),
            "real_trading_enabled": bool(runtime.real_trading_enabled),
        },
        "limits": {
            "max_order_usdt": max_order,
            "daily_loss_limit_usdt": daily_loss,
            "weekly_loss_limit_usdt": _safe_float(runtime.weekly_loss_limit_usdt, 0.0),
            "max_open_positions": max_open,
        },
        "permissions": {
            "has_api_key": bool(runtime.has_api_key),
            "has_api_secret": bool(runtime.has_api_secret),
            "account_access": account_access,
            "spot_only_design": True,
            "withdraw_endpoint_present": False,
            "futures_margin_endpoints_present": False,
        },
        "selected_strategy_ids": selected_strategies,
        "selected_filter_ids": selected_filters,
        "checklist": items,
        "blockers": all_blockers,
        "raw_readiness_status": readiness.get("status"),
        "checked_at": now_iso(),
    }
