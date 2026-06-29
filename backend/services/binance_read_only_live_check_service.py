from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.auth import read_auth_store
from core.config import DEFAULT_USER
from services.binance_service import BinanceService
from services.user_api_secret_layer_service import public_api_connection

REVISION_RANGE = "986-990"
PACKAGE_NAME = "Real Binance Read-Only Live Check Block"
FINAL_DECISION_READY = "BINANCE_READ_ONLY_READY"
NETWORK_FLAG = "BINANCE_READ_ONLY_LIVE_CHECK_ENABLED"
LEGACY_NETWORK_FLAG = "BINANCE_READ_ONLY_VERIFY_ENABLED"
READ_ONLY_ENDPOINTS = ("ping", "server_time", "account", "balances")
FORBIDDEN_RESPONSE_TOKENS = (
    "x-mbx-apikey",
    "signature=",
    "api_secret=",
    "api_key=",
    "api_key_value",
    "secret_key=",
    "encrypted_secret_key_value",
    "binance_api_secret",
)

ROOT_DIR = Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disabled", ""}:
        return False
    return default


def _current_user_record(store: dict | None, username: str) -> dict[str, Any]:
    users = _as_dict(_as_dict(store).get("users"))
    return _as_dict(users.get(username) or users.get(DEFAULT_USER) or {})


def _network_enabled() -> bool:
    return _env_bool(NETWORK_FLAG, False) or _env_bool(LEGACY_NETWORK_FLAG, False)


def _service_runtime_public(service: BinanceService) -> dict[str, Any]:
    public = _as_dict(service.runtime.public())
    return {
        "mode": public.get("mode"),
        "base_url": public.get("base_url"),
        "testnet": bool(public.get("testnet")),
        "has_api_key": bool(public.get("has_api_key")),
        "has_api_secret": bool(public.get("has_api_secret")),
        "real_trading_enabled": bool(public.get("real_trading_enabled")),
        "real_trading_dry_run": bool(public.get("real_trading_dry_run")),
        "max_order_usdt": public.get("max_order_usdt"),
        "daily_loss_limit_usdt": public.get("daily_loss_limit_usdt"),
        "weekly_loss_limit_usdt": public.get("weekly_loss_limit_usdt"),
        "max_open_positions": public.get("max_open_positions"),
        "allowed_symbols": public.get("allowed_symbols") or [],
        "blocked_symbols": public.get("blocked_symbols") or [],
        "recv_window": public.get("recv_window"),
        "timeout_seconds": public.get("timeout_seconds"),
    }


def _safe_error_category(response: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(response, dict):
        return None
    mapped = _as_dict(response.get("mapped_error"))
    if not mapped:
        return None
    return {"code": mapped.get("code"), "category": mapped.get("category")}


def _sanitize_balance_rows(rows: list[Any], limit: int = 25) -> list[dict[str, Any]]:
    safe_rows: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        total = row.get("total")
        free = row.get("free")
        locked = row.get("locked")
        safe_rows.append({
            "asset": str(row.get("asset") or ""),
            "has_free": bool(float(free or 0)) if str(free or "0").replace(".", "", 1).isdigit() else bool(free),
            "has_locked": bool(float(locked or 0)) if str(locked or "0").replace(".", "", 1).isdigit() else bool(locked),
            "has_balance": bool(float(total or 0)) if str(total or "0").replace(".", "", 1).isdigit() else bool(total),
        })
    return safe_rows


def build_rev986_api_secret_masking_check(username: str = DEFAULT_USER, store: dict | None = None, service: BinanceService | None = None) -> dict[str, Any]:
    store = read_auth_store() if store is None else store
    service = service or BinanceService()
    record = _current_user_record(store, username)
    public_connection = public_api_connection(record)
    runtime_public = _service_runtime_public(service)
    configured = bool(public_connection.get("configured") or (runtime_public.get("has_api_key") and runtime_public.get("has_api_secret")))
    blockers: list[str] = []
    if public_connection.get("configured") and not public_connection.get("can_read"):
        blockers.append("read_permission_missing")
    if runtime_public.get("has_api_key") != runtime_public.get("has_api_secret"):
        blockers.append("runtime_key_secret_presence_mismatch")
    return {
        "revision": 986,
        "name": "api_key_secret_presence_and_masking_check",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "configured": configured,
        "public_connection": public_connection,
        "runtime_public": runtime_public,
        "masking_policy": "Only booleans and permission flags are returned; raw API key and secret values are never returned.",
        "secret_values_returned": False,
    }


def build_rev987_binance_account_read_only_check(service: BinanceService | None = None) -> dict[str, Any]:
    service = service or BinanceService()
    network_enabled = _network_enabled()
    runtime_public = _service_runtime_public(service)
    if not network_enabled:
        return {
            "revision": 987,
            "name": "binance_account_read_only_check",
            "status": "skipped",
            "blockers": [],
            "network_enabled": False,
            "decision": "SKIPPED_BY_DEFAULT_OFF",
            "endpoint": "GET /api/v3/account",
            "method_scope": "GET_ONLY_SIGNED_READ",
            "latency_ms": None,
            "mapped_error": None,
            "secret_values_returned": False,
        }
    response = service.account_check()
    ok = bool(response.get("ok"))
    return {
        "revision": 987,
        "name": "binance_account_read_only_check",
        "status": "ok" if ok else "blocked",
        "blockers": [] if ok else ["binance_account_read_only_failed"],
        "network_enabled": True,
        "decision": "PASS" if ok else "BLOCKED",
        "endpoint": "GET /api/v3/account",
        "method_scope": "GET_ONLY_SIGNED_READ",
        "account_access": ok,
        "latency_ms": response.get("latency_ms"),
        "status_code": response.get("status_code"),
        "mapped_error": _safe_error_category(response),
        "permissions_summary_available": isinstance(response.get("data"), dict),
        "secret_values_returned": False,
    }


def build_rev988_balance_read_only_check(service: BinanceService | None = None) -> dict[str, Any]:
    service = service or BinanceService()
    network_enabled = _network_enabled()
    if not network_enabled:
        return {
            "revision": 988,
            "name": "balance_read_only_check",
            "status": "skipped",
            "blockers": [],
            "network_enabled": False,
            "decision": "SKIPPED_BY_DEFAULT_OFF",
            "endpoint": "GET /api/v3/account -> balances",
            "asset_count": 0,
            "non_zero_asset_count": 0,
            "sample_assets": [],
            "secret_values_returned": False,
        }
    response = service.balances()
    ok = bool(response.get("ok"))
    balances = _as_dict(response.get("data")).get("balances") or [] if ok else []
    safe_assets = _sanitize_balance_rows(balances)
    return {
        "revision": 988,
        "name": "balance_read_only_check",
        "status": "ok" if ok else "blocked",
        "blockers": [] if ok else ["balance_read_only_failed"],
        "network_enabled": True,
        "decision": "PASS" if ok else "BLOCKED",
        "endpoint": "GET /api/v3/account -> balances",
        "latency_ms": response.get("latency_ms"),
        "status_code": response.get("status_code"),
        "mapped_error": _safe_error_category(response),
        "asset_count": len(balances),
        "non_zero_asset_count": len(safe_assets),
        "sample_assets": safe_assets,
        "balance_amounts_returned": False,
        "secret_values_returned": False,
    }


def build_rev989_permission_drift_trade_permission_check(username: str = DEFAULT_USER, store: dict | None = None, service: BinanceService | None = None) -> dict[str, Any]:
    store = read_auth_store() if store is None else store
    service = service or BinanceService()
    record = _current_user_record(store, username)
    public_connection = public_api_connection(record)
    runtime_public = _service_runtime_public(service)
    drift: list[str] = []
    warnings: list[str] = []
    if public_connection.get("configured") and not public_connection.get("can_read"):
        drift.append("app_permission_read_disabled")
    if public_connection.get("can_trade"):
        warnings.append("app_trade_permission_enabled_review_required")
    if runtime_public.get("real_trading_enabled") is True:
        drift.append("runtime_real_trading_enabled_must_remain_off_for_read_only_block")
    if runtime_public.get("has_api_key") != runtime_public.get("has_api_secret"):
        drift.append("runtime_key_secret_presence_mismatch")
    return {
        "revision": 989,
        "name": "permission_drift_trade_permission_check",
        "status": "ok" if not drift else "blocked",
        "blockers": drift,
        "warnings": warnings,
        "public_connection": {
            "configured": bool(public_connection.get("configured")),
            "can_read": bool(public_connection.get("can_read")),
            "can_trade": bool(public_connection.get("can_trade")),
            "testnet": bool(public_connection.get("testnet")),
            "exchange": public_connection.get("exchange"),
            "secret_values_returned": False,
        },
        "runtime_safety": {
            "real_trading_enabled": bool(runtime_public.get("real_trading_enabled")),
            "real_submit_not_checked_or_called": True,
            "real_close_not_checked_or_called": True,
        },
        "secret_values_returned": False,
    }


def _response_leak_scan(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    hits = [token for token in FORBIDDEN_RESPONSE_TOKENS if token in text]
    return {"status": "PASS" if not hits else "FAIL", "hits": hits, "secret_values_returned": False}


def build_binance_read_only_live_check_report(username: str = DEFAULT_USER, store: dict | None = None, service: BinanceService | None = None) -> dict[str, Any]:
    store = read_auth_store() if store is None else store
    service = service or BinanceService()
    rev986 = build_rev986_api_secret_masking_check(username, store, service)
    rev987 = build_rev987_binance_account_read_only_check(service)
    rev988 = build_rev988_balance_read_only_check(service)
    rev989 = build_rev989_permission_drift_trade_permission_check(username, store, service)
    checks = {
        "rev986_api_secret_masking": rev986,
        "rev987_account_read_only": rev987,
        "rev988_balance_read_only": rev988,
        "rev989_permission_drift": rev989,
    }
    blockers: list[str] = []
    for key, payload in checks.items():
        for blocker in payload.get("blockers", []):
            blockers.append(f"{key}:{blocker}")
    network_enabled = _network_enabled()
    if network_enabled and (rev987.get("status") != "ok" or rev988.get("status") != "ok"):
        blockers.append("live_read_only_network_failed")
    report = {
        "status": "ok" if not blockers else "blocked",
        "revision": 990,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "final_decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
        "blockers": sorted(set(blockers)),
        "network_flag": NETWORK_FLAG,
        "legacy_network_flag": LEGACY_NETWORK_FLAG,
        "network_enabled": network_enabled,
        "read_only_scope": {
            "allowed_methods": ["GET /api/v3/ping", "GET /api/v3/time", "GET /api/v3/account"],
            "forbidden_methods": ["POST /api/v3/order", "DELETE /api/v3/order", "POST /api/v3/order/test"],
            "real_order_submit_triggered": False,
            "real_order_close_triggered": False,
            "emergency_close_triggered": False,
        },
        "checks": checks,
        "operator_next_steps": [
            "VPS üzerinde read-only API key/secret app credential layer veya runtime env üzerinden tanımlı olmalı.",
            f"Gerçek read-only canlı kontrol için sadece {NETWORK_FLAG}=true yapılmalı; submit/close flagleri OFF kalmalı.",
            "Account ve balance kontrolleri PASS olmadan Paket 5 onboarding drill'e üretim kararı verilmemeli.",
        ],
        "secret_values_returned": False,
        "checked_at": _now_iso(),
    }
    report["leak_scan"] = _response_leak_scan(report)
    if report["leak_scan"]["status"] != "PASS":
        report["status"] = "blocked"
        report["final_decision"] = "BLOCKED"
        report["blockers"] = sorted(set(report["blockers"] + ["secret_response_leak_detected"]))
    return report


def build_binance_read_only_live_check_summary(username: str = DEFAULT_USER, store: dict | None = None) -> dict[str, Any]:
    report = build_binance_read_only_live_check_report(username=username, store=store)
    return {
        "status": report.get("status"),
        "revision": report.get("revision"),
        "revision_range": REVISION_RANGE,
        "final_decision": report.get("final_decision"),
        "blockers": report.get("blockers"),
        "network_enabled": bool(report.get("network_enabled")),
        "account_read_only_status": _as_dict(_as_dict(report.get("checks")).get("rev987_account_read_only")).get("status"),
        "balance_read_only_status": _as_dict(_as_dict(report.get("checks")).get("rev988_balance_read_only")).get("status"),
        "permission_drift_status": _as_dict(_as_dict(report.get("checks")).get("rev989_permission_drift")).get("status"),
        "secret_values_returned": False,
    }
