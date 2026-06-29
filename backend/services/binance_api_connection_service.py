from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.config import BASE_DIR, DEFAULT_USER
from core.storage import append_audit, load_shadow, now_iso, read_json_file, save_shadow, write_json_file
from services.binance_service import BinanceService

CREDENTIALS_FILE = BASE_DIR / "binance_credentials_store.json"


def _safe_user(user: str | None) -> str:
    return str(user or DEFAULT_USER).strip() or DEFAULT_USER


def _container() -> dict:
    raw = read_json_file(CREDENTIALS_FILE, {})
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("users", {})
    if not isinstance(raw.get("users"), dict):
        raw["users"] = {}
    return raw


def _mask(value: str | None, visible: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    tail = text[-visible:] if len(text) > visible else text
    return f"**** **** **** {tail}"


def _fingerprint(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _normalize_environment(value: Any) -> str:
    env = str(value or "testnet").strip().lower()
    return env if env in {"testnet", "mainnet"} else "testnet"



def _mainnet_confirmed(payload: dict | None) -> bool:
    payload = payload if isinstance(payload, dict) else {}
    ack = bool(payload.get("mainnet_ack") or payload.get("mainnet_confirmed"))
    text = str(payload.get("mainnet_confirm_text") or payload.get("mainnet_confirmation") or "").strip().upper()
    normalized = text.replace("İ", "I").replace("Ç", "C").replace("Ğ", "G").replace("Ş", "S").replace("Ü", "U").replace("Ö", "O")
    return bool(ack and ("GERCEK PARA" in normalized or "MAINNET" in normalized))

def _environment_safety(record: dict | None) -> dict:
    record = record if isinstance(record, dict) else {}
    environment = _normalize_environment(record.get("environment"))
    mainnet_confirmed = bool(record.get("mainnet_confirmed_at"))
    is_mainnet = environment == "mainnet"
    return {
        "environment": environment,
        "mode_label": "Gerçek Binance" if is_mainnet else "Testnet",
        "uses_real_money": bool(is_mainnet),
        "requires_extra_confirmation": bool(is_mainnet and not mainnet_confirmed),
        "mainnet_confirmed": bool(mainnet_confirmed),
        "mainnet_confirmed_at": record.get("mainnet_confirmed_at"),
        "simple_status": "Dikkat: Gerçek para kullanılabilir" if is_mainnet else "Şu an gerçek para kullanılmıyor",
        "warning": "Gerçek Binance seçiliyse emir yetkisi ayrıca canlı işlem kilitlerinden geçer." if is_mainnet else "Testnet seçili. Bu ortam gerçek para kullanmaz.",
        "badge": "real-money" if is_mainnet else "test-money",
    }

def _public_summary(record: dict | None, last_test: dict | None = None) -> dict:
    record = record if isinstance(record, dict) else {}
    api_key = str(record.get("api_key") or "").strip()
    api_secret = str(record.get("api_secret") or "").strip()
    environment = _normalize_environment(record.get("environment"))
    has_key = bool(api_key)
    has_secret = bool(api_secret)
    return {
        "status": "configured" if has_key and has_secret else "missing",
        "has_api_key": has_key,
        "has_api_secret": has_secret,
        "api_key_masked": _mask(api_key),
        "api_key_fingerprint": _fingerprint(api_key),
        "secret_saved": has_secret,
        "secret_masked": _mask(api_secret),
        "environment": environment,
        "mode_label": "Gerçek Binance" if environment == "mainnet" else "Testnet",
        "environment_safety": _environment_safety(record),
        "saved_at": record.get("saved_at"),
        "updated_at": record.get("updated_at"),
        "last_test": last_test or record.get("last_test") or {},
        "safety": {
            "withdrawal_permission_supported": False,
            "withdrawal_permission_label": "Para çekme izni kullanılmaz",
            "futures_margin_supported": False,
            "futures_margin_label": "Futures ve margin kullanılmaz",
            "secret_returned_to_frontend": False,
        },
        "simple_status": "Binance bağlantısı kayıtlı" if has_key and has_secret else "Binance bağlı değil",
    }


def get_connection_summary(user: str | None = DEFAULT_USER) -> dict:
    username = _safe_user(user)
    record = (_container().get("users") or {}).get(username, {})
    return {"status": "ok", "user": username, "connection": _public_summary(record)}


def get_environment_safety(user: str | None = DEFAULT_USER) -> dict:
    username = _safe_user(user)
    record = (_container().get("users") or {}).get(username, {})
    safety = _environment_safety(record)
    return {"status": "ok", "user": username, "environment_safety": safety}


def save_connection(payload: dict, user: str | None = DEFAULT_USER) -> dict:
    username = _safe_user(user)
    payload = payload if isinstance(payload, dict) else {}
    api_key = str(payload.get("api_key") or "").strip()
    api_secret = str(payload.get("api_secret") or "").strip()
    environment = _normalize_environment(payload.get("environment"))

    blockers: list[str] = []
    if len(api_key) < 8:
        blockers.append("API key çok kısa")
    if len(api_secret) < 8:
        blockers.append("Secret key çok kısa")
    if environment == "mainnet" and not _mainnet_confirmed(payload):
        blockers.append("Gerçek Binance için ekstra onay gerekli")
    if blockers:
        return {"status": "blocked", "user": username, "blockers": blockers, "connection": _public_summary({"environment": environment})}

    data = _container()
    users = data.setdefault("users", {})
    before = deepcopy(users.get(username, {})) if isinstance(users.get(username), dict) else {}
    now = now_iso()
    users[username] = {
        "api_key": api_key,
        "api_secret": api_secret,
        "environment": environment,
        "mainnet_confirmed_at": now if environment == "mainnet" else None,
        "mainnet_ack_text": "GERCEK PARA" if environment == "mainnet" else "",
        "saved_at": before.get("saved_at") or now,
        "updated_at": now,
        "last_test": before.get("last_test") or {},
    }
    write_json_file(CREDENTIALS_FILE, data)

    shadow = load_shadow(username)
    append_audit(
        shadow,
        "binance.connection.save",
        "ok",
        "Binance API bağlantısı kaydedildi.",
        meta={"page": "settings", "environment": environment, "uses_real_money": environment == "mainnet", "api_key_fingerprint": _fingerprint(api_key)},
        user=username,
    )
    save_shadow(shadow, username)
    return {"status": "saved", "ok": True, "user": username, "connection": _public_summary(users[username])}


def delete_connection(user: str | None = DEFAULT_USER) -> dict:
    username = _safe_user(user)
    data = _container()
    users = data.setdefault("users", {})
    existed = username in users
    users.pop(username, None)
    write_json_file(CREDENTIALS_FILE, data)
    return {"status": "deleted", "ok": True, "user": username, "existed": existed, "connection": _public_summary({})}


def _permission_summary(record: dict) -> dict:
    return {
        "balance_read": bool(record.get("api_key") and record.get("api_secret")),
        "spot_trade_possible": bool(record.get("api_key") and record.get("api_secret")),
        "withdrawal_used_by_system": False,
        "futures_margin_used_by_system": False,
        "simple_lines": [
            "Bakiye okumak için anahtar hazır" if record.get("api_key") and record.get("api_secret") else "Bakiye için anahtar eksik",
            "Spot işlem izni Binance tarafında ayrıca kontrol edilmelidir",
            "Para çekme işlemi bu sistemde kullanılmaz",
            "Futures ve margin bu sistemde kullanılmaz",
        ],
    }


def test_connection(user: str | None = DEFAULT_USER) -> dict:
    username = _safe_user(user)
    data = _container()
    record = (data.get("users") or {}).get(username, {})
    if not isinstance(record, dict) or not record.get("api_key") or not record.get("api_secret"):
        result = {
            "status": "blocked",
            "ready": False,
            "simple_status": "Binance bağlı değil",
            "blockers": ["API key ve secret kaydedilmemiş"],
            "checks": _permission_summary(record if isinstance(record, dict) else {}),
            "tested_at": now_iso(),
        }
        return {"status": "blocked", "ok": False, "user": username, "connection": _public_summary(record, result), "test": result}

    service = BinanceService(api_key=record.get("api_key"), api_secret=record.get("api_secret"), mode=_normalize_environment(record.get("environment")))
    account = service.account_check()
    ok = bool(account.get("ok"))
    mapped = account.get("mapped_error") or {}
    result = {
        "status": "ok" if ok else "review",
        "ready": ok,
        "simple_status": "Binance bağlantısı iyi" if ok else "Binance bağlantısı kontrol istiyor",
        "blockers": [] if ok else [mapped.get("message") or mapped.get("category") or "Binance bağlantı testi geçmedi"],
        "checks": _permission_summary(record),
        "binance_status_code": account.get("status_code"),
        "latency_ms": account.get("latency_ms"),
        "error_category": mapped.get("category"),
        "tested_at": now_iso(),
    }
    data.setdefault("users", {})[username]["last_test"] = result
    write_json_file(CREDENTIALS_FILE, data)
    return {"status": result["status"], "ok": ok, "user": username, "connection": _public_summary(data["users"][username], result), "test": result}


def build_api_connection_quality_report() -> dict:
    data = _container()
    users = data.get("users") or {}
    issues = []
    for username, record in users.items():
        if not isinstance(record, dict):
            issues.append(f"{username}: geçersiz kayıt")
            continue
        if record.get("api_secret") and _public_summary(record).get("secret_masked") == record.get("api_secret"):
            issues.append(f"{username}: secret maskelenmemiş")
        if _normalize_environment(record.get("environment")) == "mainnet" and not record.get("mainnet_confirmed_at"):
            issues.append(f"{username}: mainnet ekstra onayı eksik")
    return {
        "status": "ok" if not issues else "blocked",
        "users": len(users),
        "blockers": issues,
        "checks": [
            "secret frontend'e dönmez",
            "API key maskeli gösterilir",
            "testnet/mainnet bilgisi ayrı tutulur",
            "mainnet için ekstra açık onay gerekir",
            "mainnet seçimi kullanıcıya gerçek para uyarısı üretir",
            "withdraw/futures/margin sistem dışında tutulur",
        ],
    }
