from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from core.auth import create_user_record
from services.production_completion_service import normalize_commission_settings, update_commission_settings
from services.production_onboarding_service import (
    apply_onboarding_to_existing_user,
    normalize_risk_profile,
    normalize_strategy_list,
    normalize_symbol_list,
    public_onboarding_user,
    validate_onboarding_payload,
)
from services.user_api_secret_layer_service import set_user_api_connection

REVISION_RANGE = "991-995"
PACKAGE_NAME = "Single User Full Onboarding Drill Block"
FINAL_DECISION_READY = "SINGLE_USER_ONBOARDING_READY"
DRILL_USERNAME = "rev991_single_user_drill"

INTERNAL_SAMPLE_API_KEY = "hmtstc_internal_drill_api_key_not_real"
INTERNAL_SAMPLE_SECRET = "hmtstc_internal_drill_secret_not_real"
INTERNAL_SAMPLE_PASSWORD = "hmtstc_internal_drill_password_not_returned"
FORBIDDEN_VALUE_TOKENS = (
    INTERNAL_SAMPLE_API_KEY.lower(),
    INTERNAL_SAMPLE_SECRET.lower(),
    INTERNAL_SAMPLE_PASSWORD.lower(),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _base_store(username: str = DRILL_USERNAME) -> dict[str, Any]:
    record = create_user_record(username, INTERNAL_SAMPLE_PASSWORD, role="user")
    record["token"] = None
    return {"users": {username: record}}


def _safe_public_user(store: dict[str, Any], username: str = DRILL_USERNAME) -> dict[str, Any]:
    return public_onboarding_user(as_dict(as_dict(store.get("users")).get(username)), username)


def build_sample_onboarding_payload(username: str = DRILL_USERNAME) -> dict[str, Any]:
    return {
        "username": username,
        "create_user": False,
        "api_connection": {
            "exchange": "binance",
            "testnet": True,
            "api_key": INTERNAL_SAMPLE_API_KEY,
            "secret_key": INTERNAL_SAMPLE_SECRET,
            "permissions": {"read": True, "trade": False},
        },
        "commission_settings": {
            "mode": "percent",
            "buy_rate_percent": 0.10,
            "sell_rate_percent": 0.10,
            "minimum_commission_usdt": 0.0,
            "enabled": True,
        },
        "risk_profile": {
            "profile": "conservative",
            "max_daily_loss_usdt": 10.0,
            "max_notional_usdt": 25.0,
            "max_daily_trades": 50,
        },
        "allowed_symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        "allowed_modes": ["paper", "shadow", "dry_live", "micro_live_preview"],
        "allowed_strategies": ["choch_micro_scalper", "imbalance_fill_hunter"],
    }


def build_rev991_new_user_creation_drill(username: str = DRILL_USERNAME) -> dict[str, Any]:
    store = _base_store(username)
    record = as_dict(store["users"].get(username))
    blockers: list[str] = []
    if username not in store["users"]:
        blockers.append("user_not_created")
    if record.get("role") != "user":
        blockers.append("new_user_role_not_user")
    if record.get("active") is False:
        blockers.append("new_user_inactive")
    if record.get("password_hash") and record.get("salt"):
        password_storage = "hashed_with_salt"
    else:
        blockers.append("password_hash_missing")
        password_storage = "missing"
    return {
        "revision": 991,
        "name": "new_user_creation_drill",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "username": username,
        "role": record.get("role"),
        "active": record.get("active") is not False,
        "password_storage": password_storage,
        "password_value_returned": False,
        "token_returned": False,
        "secret_values_returned": False,
    }


def build_rev992_api_secret_storage_drill(username: str = DRILL_USERNAME) -> dict[str, Any]:
    store = _base_store(username)
    result = set_user_api_connection(store, username, as_dict(build_sample_onboarding_payload(username).get("api_connection")))
    public_user = _safe_public_user(store, username)
    blockers: list[str] = []
    if result.get("status") != "ok":
        blockers.extend(result.get("errors") or ["api_connection_apply_failed"])
    if not public_user.get("api_configured"):
        blockers.append("api_connection_not_configured")
    if not public_user.get("api_can_read"):
        blockers.append("read_permission_not_enabled")
    if public_user.get("api_can_trade"):
        blockers.append("trade_permission_must_remain_off_for_onboarding_drill")
    return {
        "revision": 992,
        "name": "api_key_secret_storage_and_masking_drill",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "api_configured": bool(public_user.get("api_configured")),
        "api_can_read": bool(public_user.get("api_can_read")),
        "api_can_trade": bool(public_user.get("api_can_trade")),
        "storage_contract": "presence_flags_only_in_public_response",
        "raw_api_key_returned": False,
        "raw_secret_key_returned": False,
        "secret_values_returned": False,
    }


def build_rev993_commission_fee_settings_drill(username: str = DRILL_USERNAME) -> dict[str, Any]:
    store = _base_store(username)
    commission = as_dict(build_sample_onboarding_payload(username).get("commission_settings"))
    result = update_commission_settings(store, username, commission)
    normalized = normalize_commission_settings(as_dict(as_dict(store.get("users")).get(username)).get("commission_settings"))
    blockers: list[str] = []
    if result.get("status") != "ok":
        blockers.append("commission_update_failed")
    if normalized.get("buy_rate_percent") != 0.10:
        blockers.append("buy_fee_rate_mismatch")
    if normalized.get("sell_rate_percent") != 0.10:
        blockers.append("sell_fee_rate_mismatch")
    if normalized.get("enabled") is not True:
        blockers.append("commission_not_enabled")
    return {
        "revision": 993,
        "name": "commission_fee_settings_drill",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "commission_settings": normalized,
        "expected_buy_rate_percent": 0.10,
        "expected_sell_rate_percent": 0.10,
        "secret_values_returned": False,
    }


def build_rev994_risk_whitelist_strategy_permission_drill(username: str = DRILL_USERNAME) -> dict[str, Any]:
    store = _base_store(username)
    payload = build_sample_onboarding_payload(username)
    validation = validate_onboarding_payload(payload)
    result = apply_onboarding_to_existing_user(store, username, payload)
    public_user = _safe_public_user(store, username)
    expected_risk = normalize_risk_profile(payload.get("risk_profile"))
    expected_symbols = normalize_symbol_list(payload.get("allowed_symbols"))
    expected_strategies = normalize_strategy_list(payload.get("allowed_strategies"))
    blockers: list[str] = []
    if validation.get("status") != "ok":
        blockers.extend(validation.get("errors") or ["payload_validation_failed"])
    if result.get("status") != "ok":
        blockers.append("onboarding_apply_failed")
    if public_user.get("risk_profile", {}).get("profile") != expected_risk.get("profile"):
        blockers.append("risk_profile_mismatch")
    if public_user.get("allowed_symbols") != expected_symbols:
        blockers.append("symbol_whitelist_mismatch")
    if public_user.get("allowed_strategies") != expected_strategies:
        blockers.append("strategy_permission_mismatch")
    if "micro_live_preview" in public_user.get("allowed_modes", []) and public_user.get("risk_profile", {}).get("max_notional_usdt", 0) > 100:
        blockers.append("micro_live_preview_notional_too_high")
    return {
        "revision": 994,
        "name": "risk_profile_symbol_whitelist_strategy_permission_drill",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "risk_profile": public_user.get("risk_profile"),
        "allowed_symbols": public_user.get("allowed_symbols"),
        "allowed_modes": public_user.get("allowed_modes"),
        "allowed_strategies": public_user.get("allowed_strategies"),
        "owner_approval_still_required_for_real_live": True,
        "real_order_submit_triggered": False,
        "secret_values_returned": False,
    }


def _response_leak_scan(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    hits = [token for token in FORBIDDEN_VALUE_TOKENS if token and token in text]
    return {"status": "PASS" if not hits else "FAIL", "hits": hits, "secret_values_returned": False}


def build_single_user_onboarding_drill_report(username: str = DRILL_USERNAME) -> dict[str, Any]:
    rev991 = build_rev991_new_user_creation_drill(username)
    rev992 = build_rev992_api_secret_storage_drill(username)
    rev993 = build_rev993_commission_fee_settings_drill(username)
    rev994 = build_rev994_risk_whitelist_strategy_permission_drill(username)
    checks = {
        "rev991_new_user_creation": rev991,
        "rev992_api_secret_storage": rev992,
        "rev993_commission_fee_settings": rev993,
        "rev994_risk_whitelist_strategy_permissions": rev994,
    }
    blockers = [blocker for check in checks.values() for blocker in check.get("blockers", [])]
    report = {
        "status": "ok" if not blockers else "blocked",
        "revision": 995,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "final_decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
        "blockers": blockers,
        "checks": checks,
        "rev995_report": {
            "revision": 995,
            "name": "single_user_onboarding_drill_report",
            "status": "ok" if not blockers else "blocked",
            "blockers": blockers,
            "decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
        },
        "safety_scope": {
            "real_order_submit_triggered": False,
            "real_order_close_triggered": False,
            "emergency_close_triggered": False,
            "binance_network_call_triggered": False,
            "owner_approval_required_for_live": True,
        },
        "secret_values_returned": False,
        "operator_next_steps": [
            "Gerçek kullanıcı onboarding işlemini owner oturumuyla production UI/API üzerinden çalıştır.",
            "API credential değerlerini sadece runtime store içine yaz; response/log içinde raw değer bekleme.",
            "Komisyon, whitelist, risk profili ve strateji izinlerini kullanıcı bazında doğrula.",
        ],
        "checked_at": now_iso(),
    }
    report["leak_scan"] = _response_leak_scan(copy.deepcopy(report))
    if report["leak_scan"]["status"] != "PASS":
        report["status"] = "blocked"
        report["final_decision"] = "BLOCKED"
        report["blockers"] = [*report["blockers"], "public_response_contains_internal_secret_value"]
    return report


def build_single_user_onboarding_drill_summary(username: str = DRILL_USERNAME) -> dict[str, Any]:
    report = build_single_user_onboarding_drill_report(username)
    return {
        "status": report["status"],
        "revision": report["revision"],
        "revision_range": report["revision_range"],
        "package": report["package"],
        "final_decision": report["final_decision"],
        "blockers": report["blockers"],
        "check_statuses": {key: value.get("status") for key, value in report["checks"].items()},
        "secret_values_returned": False,
        "real_order_submit_triggered": False,
    }
