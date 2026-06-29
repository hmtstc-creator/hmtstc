from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from services.binance_futures_models import DEFAULT_FUTURES_CREDENTIAL, mask_api_key, now_iso

STORE_FILE = Path(__file__).resolve().parents[1] / "binance_futures_credentials_store.json"


def _read_store() -> Dict[str, Any]:
    if not STORE_FILE.exists():
        return {"users": {}}
    try:
        data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {"users": {}}
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    return data


def _write_store(data: Dict[str, Any]) -> None:
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_FILE.with_suffix(STORE_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_FILE)


def get_futures_credentials(username: str) -> Dict[str, Any]:
    data = _read_store()
    item = dict(DEFAULT_FUTURES_CREDENTIAL)
    item.update(data.get("users", {}).get(username) or {})
    return item


def set_futures_credentials(username: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _read_store()
    current = get_futures_credentials(username)
    api_key = str(payload.get("futures_api_key") or payload.get("api_key") or current.get("futures_api_key") or "").strip()
    secret = str(payload.get("futures_secret") or payload.get("secret") or current.get("futures_secret") or "").strip()
    current.update({
        "futures_api_key": api_key,
        "futures_secret": secret,
        "environment": "mainnet" if str(payload.get("environment") or current.get("environment") or "testnet").lower() == "mainnet" else "testnet",
        "trade_permission": bool(payload.get("trade_permission", current.get("trade_permission", False))),
        "withdraw_permission": bool(payload.get("withdraw_permission", current.get("withdraw_permission", False))),
        "last_checked_at": now_iso(),
    })
    data.setdefault("users", {})[username] = current
    _write_store(data)
    return get_futures_connection_summary(username)


def clear_futures_credentials(username: str) -> Dict[str, Any]:
    data = _read_store()
    data.setdefault("users", {}).pop(username, None)
    _write_store(data)
    return get_futures_connection_summary(username)


def get_futures_connection_summary(username: str) -> Dict[str, Any]:
    item = get_futures_credentials(username)
    has_key = bool(item.get("futures_api_key"))
    has_secret = bool(item.get("futures_secret"))
    withdraw = bool(item.get("withdraw_permission"))
    connected = has_key and has_secret and not withdraw
    return {
        "service": "binance_futures_connection",
        "market": "futures",
        "connected": connected,
        "api_key_configured": has_key,
        "secret_configured": has_secret,
        "masked_api_key": mask_api_key(item.get("futures_api_key")),
        "secret_returned_to_frontend": False,
        "environment": item.get("environment", "testnet"),
        "trade_permission": bool(item.get("trade_permission")),
        "withdraw_permission": withdraw,
        "withdraw_safe": not withdraw,
        "status": "ok" if connected else ("blocked_withdraw_permission" if withdraw else "missing_credentials"),
        "last_checked_at": item.get("last_checked_at"),
    }
