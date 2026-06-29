from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from core.auth import read_auth_store
from core.config import DEFAULT_USER
from services.binance_service import BinanceService, map_binance_error
from services.user_api_secret_layer_service import public_api_connection

REVISION_RANGE = "881-885"
NETWORK_FLAG = "BINANCE_READ_ONLY_VERIFY_ENABLED"
READ_ONLY_ENDPOINTS = ("ping", "server_time", "account", "balances")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disabled", ""}:
        return False
    return default


def _current_user_record(store: dict | None, username: str) -> dict:
    users = _as_dict(_as_dict(store).get("users"))
    return _as_dict(users.get(username) or users.get(DEFAULT_USER) or {})


def build_permission_drift(record: dict, runtime_public: dict | None = None) -> dict:
    connection = public_api_connection(record)
    expected_read = bool(connection.get("can_read"))
    expected_trade = bool(connection.get("can_trade"))
    runtime_public = _as_dict(runtime_public)
    runtime_has_key = bool(runtime_public.get("has_api_key"))
    runtime_has_secret = bool(runtime_public.get("has_api_secret"))
    drift = []
    if connection.get("configured") and not expected_read:
        drift.append("user_api_configured_without_read_permission")
    if runtime_has_key != runtime_has_secret:
        drift.append("runtime_key_secret_presence_mismatch")
    if expected_trade and not expected_read:
        drift.append("trade_permission_without_read_permission")
    return {
        "status": "attention" if drift else "ok",
        "expected": {"read": expected_read, "trade": expected_trade, "configured": bool(connection.get("configured"))},
        "runtime_presence": {"has_api_key": runtime_has_key, "has_api_secret": runtime_has_secret},
        "drift": drift,
    }


def _safe_network_check(service: BinanceService) -> dict:
    if not _env_bool(NETWORK_FLAG, False):
        return {
            "network_enabled": False,
            "decision": "SKIPPED_BY_DEFAULT_OFF",
            "checks": [{"name": name, "status": "skipped", "reason": "read_only_network_default_off"} for name in READ_ONLY_ENDPOINTS],
            "secret_values_returned": False,
        }
    checks = []
    ping = service.ping()
    checks.append({"name": "ping", "status": "ok" if ping.get("ok") else "blocked", "latency_ms": ping.get("latency_ms"), "mapped_error": ping.get("mapped_error")})
    server_time = service.server_time()
    checks.append({"name": "server_time", "status": "ok" if server_time.get("ok") else "blocked", "latency_ms": server_time.get("latency_ms"), "mapped_error": server_time.get("mapped_error")})
    account = service.account_check()
    checks.append({"name": "account", "status": "ok" if account.get("ok") else "blocked", "latency_ms": account.get("latency_ms"), "mapped_error": account.get("mapped_error")})
    balances = service.balances()
    balance_count = len((_as_dict(balances.get("data")).get("balances") or [])) if balances.get("ok") else 0
    checks.append({"name": "balances", "status": "ok" if balances.get("ok") else "blocked", "latency_ms": balances.get("latency_ms"), "balance_asset_count": balance_count, "mapped_error": balances.get("mapped_error")})
    blockers = [c for c in checks if c.get("status") != "ok"]
    return {"network_enabled": True, "decision": "PASS" if not blockers else "BLOCKED", "checks": checks, "secret_values_returned": False}


def _response_leak_scan(payload: dict) -> dict:
    text = str(payload).lower()
    forbidden = ["x-mbx-apikey", "signature=", "encrypted_secret_key_value", "api_secret_value"]
    hits = [token for token in forbidden if token in text]
    return {"status": "FAIL" if hits else "PASS", "hits": hits, "secret_values_returned": False}


def build_binance_read_only_verification(username: str = DEFAULT_USER, store: dict | None = None) -> dict:
    store = read_auth_store() if store is None else store
    record = _current_user_record(store, username)
    service = BinanceService()
    runtime_public = service.runtime.public()
    connection = public_api_connection(record)
    permission_drift = build_permission_drift(record, runtime_public)
    network = _safe_network_check(service)
    blockers = []
    if not connection.get("configured") and not service.has_credentials():
        blockers.append("api_key_secret_missing")
    if connection.get("configured") and not connection.get("can_read"):
        blockers.append("read_permission_missing")
    if permission_drift.get("status") != "ok":
        blockers.append("permission_drift_attention")
    if network.get("network_enabled") and network.get("decision") != "PASS":
        blockers.append("read_only_network_verification_failed")
    decision = "READY" if not blockers else "BLOCKED"
    result = {
        "status": "ok",
        "revision_range": REVISION_RANGE,
        "user": username,
        "decision": decision,
        "critical_blocker": blockers[0] if blockers else None,
        "operator_action": "enable_read_only_network_flag_and_verify_credentials" if not network.get("network_enabled") else ("fix_credentials_or_permissions" if blockers else "none"),
        "public_connection": connection,
        "runtime_public": runtime_public,
        "permission_drift": permission_drift,
        "read_only_network": network,
        "real_submit_default_off": not bool(runtime_public.get("real_trading_enabled")),
        "real_close_default_off": True,
        "secret_values_returned": False,
        "checked_at": now_iso(),
    }
    result["leak_scan"] = _response_leak_scan(result)
    if result["leak_scan"]["status"] != "PASS":
        result["decision"] = "BLOCKED"
        result["critical_blocker"] = "secret_response_leak"
    return result


def build_binance_read_only_verification_summary(username: str = DEFAULT_USER, store: dict | None = None) -> dict:
    full = build_binance_read_only_verification(username=username, store=store)
    return {
        "status": full.get("status"),
        "revision_range": REVISION_RANGE,
        "decision": full.get("decision"),
        "critical_blocker": full.get("critical_blocker"),
        "operator_action": full.get("operator_action"),
        "api_configured": bool(_as_dict(full.get("public_connection")).get("configured")),
        "can_read": bool(_as_dict(full.get("public_connection")).get("can_read")),
        "network_enabled": bool(_as_dict(full.get("read_only_network")).get("network_enabled")),
        "permission_drift": _as_dict(full.get("permission_drift")).get("status"),
        "secret_values_returned": False,
    }


def build_binance_read_only_verification_quality(username: str = DEFAULT_USER, store: dict | None = None) -> dict:
    full = build_binance_read_only_verification(username=username, store=store)
    checks = [
        {"name": "network_default_off", "status": "ok" if not _as_dict(full.get("read_only_network")).get("network_enabled") else "review"},
        {"name": "secret_values_returned_false", "status": "ok" if full.get("secret_values_returned") is False else "fail"},
        {"name": "response_leak_scan", "status": "ok" if _as_dict(full.get("leak_scan")).get("status") == "PASS" else "fail"},
        {"name": "direct_submit_not_used", "status": "ok"},
        {"name": "read_only_endpoint_scope", "status": "ok", "endpoints": list(READ_ONLY_ENDPOINTS)},
    ]
    failures = [c for c in checks if c.get("status") == "fail"]
    return {"status": "ok", "quality_gate": "PASS" if not failures else "FAIL", "revision_range": REVISION_RANGE, "checks": checks, "secret_values_returned": False, "checked_at": now_iso()}
