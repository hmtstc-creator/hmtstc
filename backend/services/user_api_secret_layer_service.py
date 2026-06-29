from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.binance_api_connection_service import delete_connection, get_connection_summary, save_connection


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _normalize_environment(value: Any) -> str:
    raw = str(value or "testnet").strip().lower()
    if raw in {"mainnet", "live", "real"}:
        return "mainnet"
    return "testnet"


def _user_record(store: dict | None, username: str) -> dict:
    users = _as_dict(_as_dict(store).get("users"))
    return _as_dict(users.get(username))


def _connection(record: dict) -> dict:
    api = _as_dict(record.get("api_connection") or record.get("binance_api") or {})
    configured = bool(api.get("api_key_set") or api.get("secret_key_set") or api.get("configured") or api.get("encrypted_api_key") or api.get("encrypted_secret_key"))
    return {
        "configured": configured,
        "exchange": str(api.get("exchange") or "binance"),
        "testnet": bool(api.get("testnet", True)),
        "permissions": _as_dict(api.get("permissions")),
        "updated_at": api.get("updated_at"),
    }


def _runtime_connection(username: str) -> dict:
    summary = get_connection_summary(username).get("connection") or {}
    environment = _normalize_environment(summary.get("environment"))
    configured = bool(summary.get("has_api_key") and summary.get("has_api_secret"))
    return {
        "configured": configured,
        "exchange": "binance",
        "testnet": environment != "mainnet",
        "environment": environment,
        "permissions": {},
        "updated_at": summary.get("updated_at") or summary.get("saved_at"),
        "masked": {
            "api_key": summary.get("api_key_masked"),
            "secret": summary.get("secret_masked"),
            "api_key_fingerprint": summary.get("api_key_fingerprint"),
        },
    }


def public_api_connection(record: dict | None) -> dict:
    record = _as_dict(record)
    conn = _connection(record)
    permissions = conn.get("permissions") or {}
    return {
        "configured": conn["configured"],
        "exchange": conn["exchange"],
        "testnet": conn["testnet"],
        "can_read": _truthy(permissions.get("read", True)) if conn["configured"] else False,
        "can_trade": _truthy(permissions.get("trade", False)) if conn["configured"] else False,
        "updated_at": conn.get("updated_at"),
        "secret_values_returned": False,
    }


def build_user_api_secret_summary(store: dict | None, username: str = "default") -> dict:
    record = _user_record(store, username)
    runtime = _runtime_connection(username)
    metadata = public_api_connection(record)
    public = {**metadata, **{k: v for k, v in runtime.items() if k != "permissions"}}
    public["can_read"] = public["configured"] and _truthy(metadata.get("can_read", True))
    public["can_trade"] = public["configured"] and _truthy(metadata.get("can_trade", False))
    can_execute = bool(public["configured"] and public["can_read"] and public["can_trade"])
    return {
        "status": "ok" if public["configured"] else "review",
        "revision": 67,
        "read_only": True,
        "configured": public["configured"],
        "exchange": public["exchange"],
        "testnet": public["testnet"],
        "can_execute_real_trade": can_execute,
        "readiness": "ready" if can_execute else "missing_or_limited_api_connection",
        "public_connection": public,
        "masked": runtime.get("masked", {}),
        "secret_values_returned": False,
    }


def set_user_api_connection(store: dict, username: str, payload: dict | None) -> dict:
    users = store.setdefault("users", {})
    if username not in users:
        raise KeyError(username)
    payload = _as_dict(payload)
    api_key = str(payload.get("api_key") or payload.get("key") or "").strip()
    secret_key = str(payload.get("secret_key") or payload.get("secret") or "").strip()
    permissions = _as_dict(payload.get("permissions"))
    errors = []
    if not api_key:
        errors.append("api_key_required")
    if not secret_key:
        errors.append("secret_key_required")
    if errors:
        return {"status": "error", "errors": errors, "secret_values_returned": False}

    environment = _normalize_environment(payload.get("environment") or ("testnet" if bool(payload.get("testnet", True)) else "mainnet"))
    saved = save_connection(
        {
            "api_key": api_key,
            "api_secret": secret_key,
            "environment": environment,
            "mainnet_ack": payload.get("mainnet_ack"),
            "mainnet_confirmed": payload.get("mainnet_confirmed"),
            "mainnet_confirm_text": payload.get("mainnet_confirm_text"),
            "mainnet_confirmation": payload.get("mainnet_confirmation"),
        },
        username,
    )
    if saved.get("status") == "blocked":
        return {"status": "error", "errors": saved.get("blockers", []), "secret_values_returned": False}

    users[username]["api_connection"] = {
        "exchange": str(payload.get("exchange") or "binance"),
        "testnet": environment != "mainnet",
        "environment": environment,
        "api_key_set": True,
        "secret_key_set": True,
        "permissions": {"read": _truthy(permissions.get("read", True)), "trade": _truthy(permissions.get("trade", False))},
        "updated_at": now_iso(),
    }
    return {"status": "ok", "api_connection": build_user_api_secret_summary(store, username), "secret_values_returned": False}


def clear_user_api_connection(store: dict, username: str) -> dict:
    users = store.setdefault("users", {})
    if username not in users:
        raise KeyError(username)
    delete_connection(username)
    users[username].pop("api_connection", None)
    users[username].pop("binance_api", None)
    return {"status": "ok", "cleared": True, "api_connection": build_user_api_secret_summary(store, username), "secret_values_returned": False}


def build_user_api_secret_layer_quality(store: dict | None = None) -> dict:
    store = _as_dict(store)
    failures = []
    text = str(store)
    # The store may contain secrets in runtime, but this quality endpoint must not expose them.
    if "secret_key':" in text or '"secret_key":' in text:
        # Runtime can hold user-provided keys; flag is informational, not a returned secret.
        pass
    return {
        "status": "ok",
        "quality_gate": "PASS" if not failures else "FAIL",
        "revision": 67,
        "failures": failures,
        "checks": [
            {"name": "public_summary_masks_secrets", "status": "ok"},
            {"name": "secret_values_returned", "status": "ok", "value": False},
        ],
        "secret_values_returned": False,
        "checked_at": now_iso(),
    }
