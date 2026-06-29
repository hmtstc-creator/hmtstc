from __future__ import annotations

from typing import Any

from core.storage import now_iso
from services.binance_wallet_summary_service import build_wallet_summary
from services.live_trade_readiness_check_service import build_live_trade_readiness_check
from services.real_trade_service import dry_run_order
from services.strategy_filter_toggle_service import get_strategy_filter_toggles


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("USDT", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return fallback


def _plain_blocker(code: str) -> str:
    mapping = {
        "symbol_missing": "Coin seçilmedi.",
        "amount_missing": "İşlem tutarı girilmedi.",
        "strategy_missing": "En az bir strateji açık olmalı.",
        "filter_missing": "En az bir filtre açık olmalı.",
        "wallet_not_ready": "Bakiye okunamadı veya Binance bağlı değil.",
        "live_readiness_blocked": "Canlı işlem hazırlığında eksik var.",
        "quote_amount_over_limit": "İşlem tutarı izin verilen sınırı aşıyor.",
        "insufficient_usdt_balance": "Kullanılabilir USDT yetersiz.",
        "real_trading_not_enabled": "Gerçek para modu kapalı.",
        "owner_unlock_missing_or_expired": "Son onay açık değil veya süresi doldu.",
        "emergency_lock_active": "Acil durdurma açık.",
        "dry_run_active_real_place_blocked": "Sistem güvenli deneme modunda.",
        "env_real_trading_disabled": "Canlı emir ortam kilidi kapalı.",
    }
    return mapping.get(str(code), str(code).replace("_", " "))


def _normalize_order(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    quote_amount = _safe_float(
        payload.get("quote_order_qty", payload.get("quote_amount", payload.get("amount", payload.get("usdt", 0)))),
        0.0,
    )
    return {
        "symbol": str(payload.get("symbol") or "BTCUSDT").upper().strip(),
        "side": str(payload.get("side") or "BUY").upper().strip(),
        "quote_order_qty": quote_amount,
        "order_type": str(payload.get("order_type") or "MARKET").upper().strip(),
        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
    }


def build_real_order_dry_run_simulation(data: dict, settings: dict, payload: dict | None, user: str = "default", role: str = "owner") -> dict:
    """Run a plain-language real-order dry-run without sending any exchange order.

    This wrapper intentionally keeps Binance money-moving disabled. It combines the
    existing safety report, live readiness, wallet summary and strategy/filter
    toggles so the UI can answer: "Bu emir gönderilebilir mi?".
    """
    order = _normalize_order(payload)
    toggles = get_strategy_filter_toggles(user)
    readiness = build_live_trade_readiness_check(data, settings, user=user)
    wallet_payload = build_wallet_summary(user, shadow=data)
    wallet = wallet_payload.get("wallet") or {}

    pre_blockers: list[str] = []
    if not order["symbol"]:
        pre_blockers.append("symbol_missing")
    if order["quote_order_qty"] <= 0:
        pre_blockers.append("amount_missing")
    if not toggles.get("active_strategies"):
        pre_blockers.append("strategy_missing")
    if not toggles.get("active_filters"):
        pre_blockers.append("filter_missing")
    if wallet_payload.get("status") not in {"ok", "review"} or wallet.get("source") in {"not_connected"}:
        pre_blockers.append("wallet_not_ready")
    if not readiness.get("ready_for_dry_run", False):
        pre_blockers.append("live_readiness_blocked")

    dry_record = dry_run_order(data, settings, order, user=user, role=role)
    safety = dry_record.get("safety") or {}
    safety_blockers = list(safety.get("blockers") or [])
    all_blockers = []
    for blocker in pre_blockers + safety_blockers:
        if blocker not in all_blockers:
            all_blockers.append(blocker)

    status = "ready" if not all_blockers else "blocked"
    simple_status = "Emir gönderilebilir" if status == "ready" else "Emir gönderilemez"
    decision = "Bu sadece denemedir; Binance’e gerçek emir gönderilmedi." if status == "ready" else "Eksikler çözülmeden gerçek emir gönderilmez."

    result = {
        "status": status,
        "simple_status": simple_status,
        "decision": decision,
        "user": user,
        "real_order_created": False,
        "dry_run_only": True,
        "order": order,
        "symbol": order["symbol"],
        "side": order["side"],
        "quote_order_qty": order["quote_order_qty"],
        "dry_run_order_id": dry_record.get("order_id"),
        "blockers": all_blockers,
        "blocker_texts": [_plain_blocker(item) for item in all_blockers],
        "warnings": readiness.get("warnings") or [],
        "wallet": {
            "source": wallet.get("source"),
            "source_label": wallet.get("source_label"),
            "available_usdt": wallet.get("available_usdt", 0),
            "wallet_total_usdt": wallet.get("wallet_total_usdt", 0),
        },
        "strategy_filter": {
            "active_strategy_count": len(toggles.get("active_strategies") or []),
            "active_filter_count": len(toggles.get("active_filters") or []),
            "active_strategies": toggles.get("active_strategies") or [],
            "active_filters": toggles.get("active_filters") or [],
        },
        "readiness": {
            "simple_status": readiness.get("simple_status"),
            "ready_for_dry_run": readiness.get("ready_for_dry_run"),
            "ready_for_real_order": readiness.get("ready_for_real_order"),
            "blockers": readiness.get("blockers") or [],
        },
        "safety": safety,
        "checked_at": now_iso(),
    }
    data.setdefault("real_trade", {}).setdefault("last_dry_run_simulation", result)
    return result


def build_real_order_dry_run_quality_report() -> dict:
    sample_data = {"wallet_value": 1000}
    sample_settings = {
        "bot": {"usdt_per_position": 10, "max_open_positions": 1, "allocated_usdt": 1000},
        "risk": {"daily_loss_limit": "30 USDT"},
    }
    sample = build_real_order_dry_run_simulation(
        sample_data,
        sample_settings,
        {"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 5},
        user="dry_run_quality_probe",
    )
    checks = [
        "/api/real/order/dry-run endpoint gerçek emir göndermeden çalışır",
        "Dry-run sonucu real_order_created=false döndürür",
        "Strateji, filtre, wallet ve canlı hazırlık kontrolleri aynı raporda toplanır",
        "Kullanıcıya sade blocker_texts listesi döner",
        "Son dry-run sonucu shadow state içine kayıt edilir",
    ]
    blockers = []
    if sample.get("real_order_created") is not False:
        blockers.append("dry-run gerçek emir oluşturuyor gibi işaretlenmiş")
    for key in ["status", "simple_status", "order", "blockers", "blocker_texts", "wallet", "strategy_filter", "readiness"]:
        if key not in sample:
            blockers.append(f"{key} eksik")
    return {"status": "ok" if not blockers else "blocked", "checks": checks, "blockers": blockers, "sample_status": sample.get("status")}
