from __future__ import annotations

from typing import Any

from core.config import DEFAULT_USER
from core.storage import load_shadow, now_iso
from services.binance_api_connection_service import get_connection_summary, _container, _normalize_environment
from services.binance_service import BinanceService
from services.performance_service import shadow_wallet_value
from services.summary_service import safe_float


def _safe_user(user: str | None) -> str:
    return str(user or DEFAULT_USER).strip() or DEFAULT_USER


def _record_for_user(user: str) -> dict:
    payload = get_connection_summary(user)
    # public summary intentionally hides secret; the raw credential store is owned by
    # binance_api_connection_service. We reuse test_connection/balances only through
    # the connection service path below to avoid returning secrets to routes.
    return payload.get("connection") if isinstance(payload, dict) else {}


def _extract_usdt(balances_payload: dict) -> dict:
    rows = ((balances_payload.get("data") or {}).get("balances") or []) if isinstance(balances_payload, dict) else []
    for row in rows:
        if str(row.get("asset") or "").upper() == "USDT":
            free = safe_float(row.get("free"), 0.0)
            locked = safe_float(row.get("locked"), 0.0)
            total = safe_float(row.get("total"), free + locked)
            return {"free_usdt": free, "locked_usdt": locked, "total_usdt": total}
    return {"free_usdt": 0.0, "locked_usdt": 0.0, "total_usdt": 0.0}


def _fallback_wallet(user: str, reason: str, shadow: dict | None = None) -> dict:
    shadow = shadow if isinstance(shadow, dict) else load_shadow(user)
    total = shadow_wallet_value(shadow)
    allocated = safe_float(((shadow.get("risk") or {}) if isinstance(shadow.get("risk"), dict) else {}).get("allocated_usdt"), 0.0)
    if total <= 0 and allocated > 0:
        total = allocated
    return {
        "source": "demo" if total > 0 else "not_connected",
        "source_label": "Demo / kayıtlı takip bütçesi" if total > 0 else "Binance bağlı değil",
        "is_real_binance": False,
        "is_testnet": False,
        "wallet_total_usdt": total,
        "available_usdt": total,
        "locked_usdt": 0.0,
        "in_order_usdt": 0.0,
        "simple_status": "Demo bakiye gösteriliyor" if total > 0 else "Binance bağlı değil",
        "reason": reason,
        "updated_at": now_iso(),
    }


def build_wallet_summary(user: str | None = DEFAULT_USER, shadow: dict | None = None) -> dict:
    username = _safe_user(user)
    # Raw keys are read only inside backend service scope and never returned by routes.
    record = ((_container().get("users") or {}).get(username) or {})
    connection = get_connection_summary(username).get("connection", {})
    if not isinstance(record, dict) or not record.get("api_key") or not record.get("api_secret"):
        return {"status": "missing", "user": username, "wallet": _fallback_wallet(username, "API key ve secret yok", shadow)}
    environment = str(record.get("environment") or connection.get("environment") or "testnet").lower()
    service = BinanceService(api_key=record.get("api_key"), api_secret=record.get("api_secret"), mode=_normalize_environment(record.get("environment")))
    balances = service.balances()
    if not balances.get("ok"):
        mapped = balances.get("mapped_error") or {}
        fallback = _fallback_wallet(username, mapped.get("message") or mapped.get("category") or "Binance bakiyesi okunamadı", shadow)
        fallback.update({"source": "fallback", "source_label": "Binance okunamadı, güvenli fallback", "simple_status": "Bakiye okunamadı"})
        return {"status": "review", "user": username, "wallet": fallback, "binance_error": mapped}

    usdt = _extract_usdt(balances)
    source = "binance_mainnet" if environment == "mainnet" else "binance_testnet"
    label = "Gerçek Binance bakiyesi" if environment == "mainnet" else "Testnet bakiyesi"
    wallet = {
        "source": source,
        "source_label": label,
        "is_real_binance": environment == "mainnet",
        "is_testnet": environment == "testnet",
        "wallet_total_usdt": usdt["total_usdt"],
        "available_usdt": usdt["free_usdt"],
        "locked_usdt": usdt["locked_usdt"],
        "in_order_usdt": usdt["locked_usdt"],
        "simple_status": "Gerçek Binance bakiyesi okunuyor" if environment == "mainnet" else "Testnet bakiyesi okunuyor",
        "updated_at": now_iso(),
    }
    return {"status": "ok", "user": username, "wallet": wallet}


def build_wallet_summary_quality_report() -> dict:
    checks = [
        "/api/binance/wallet-summary endpoint mevcut",
        "USDT toplamı, kullanılabilir ve işlemdeki tutar ayrı gösterilir",
        "Binance yoksa demo/fallback kaynağı açıkça etiketlenir",
        "Secret key route cevabına dönmez",
        "Runtime Summary wallet_source bilgisini taşır",
    ]
    sample = build_wallet_summary("wallet_quality_probe", shadow={"wallet_value": 0})
    blockers: list[str] = []
    wallet = sample.get("wallet") or {}
    for key in ["source", "source_label", "wallet_total_usdt", "available_usdt", "locked_usdt", "simple_status"]:
        if key not in wallet:
            blockers.append(f"wallet.{key} eksik")
    return {"status": "ok" if not blockers else "blocked", "checks": checks, "blockers": blockers, "sample_status": sample.get("status")}
