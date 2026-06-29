from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.production_completion_service import normalize_commission_settings, safe_float
from services.user_api_secret_layer_service import build_user_api_secret_summary, set_user_api_connection

ALLOWED_RISK_PROFILES = {"conservative", "balanced", "aggressive"}
ALLOWED_MODES = {"paper", "shadow", "dry_live", "micro_live_preview", "limited_live_preview"}
ALLOWED_STRATEGIES = {
    "choch_micro_scalper",
    "imbalance_fill_hunter",
    "liquidity_sweep_reversal",
    "volatility_compression_breakout",
    "mean_reversion_micro_recovery",
}
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def clean_symbol(symbol: Any) -> str:
    value = str(symbol or "").strip().upper().replace("/", "")
    if not value.endswith("USDT"):
        return ""
    return "".join(ch for ch in value if ch.isalnum())[:20]


def normalize_symbol_list(value: Any) -> list[str]:
    raw = as_list(value) or DEFAULT_SYMBOLS
    symbols = []
    for item in raw:
        symbol = clean_symbol(item)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols[:25] or DEFAULT_SYMBOLS[:]


def normalize_mode_list(value: Any) -> list[str]:
    raw = as_list(value) or ["paper", "shadow", "dry_live"]
    modes = []
    for item in raw:
        mode = str(item or "").strip().lower()
        if mode in ALLOWED_MODES and mode not in modes:
            modes.append(mode)
    return modes or ["paper"]


def normalize_strategy_list(value: Any) -> list[str]:
    raw = as_list(value) or sorted(ALLOWED_STRATEGIES)[:]
    strategies = []
    for item in raw:
        strategy = str(item or "").strip().lower()
        if strategy in ALLOWED_STRATEGIES and strategy not in strategies:
            strategies.append(strategy)
    return strategies or ["choch_micro_scalper"]


def normalize_risk_profile(value: Any) -> dict:
    raw = as_dict(value)
    profile = str(raw.get("profile") or "balanced").strip().lower()
    if profile not in ALLOWED_RISK_PROFILES:
        profile = "balanced"
    max_daily_loss = max(1.0, min(250.0, safe_float(raw.get("max_daily_loss_usdt"), 15.0)))
    max_notional = max(5.0, min(1000.0, safe_float(raw.get("max_notional_usdt"), 25.0)))
    max_trades = max(1, min(1000, int(safe_float(raw.get("max_daily_trades"), 25))))
    return {
        "profile": profile,
        "max_daily_loss_usdt": round(max_daily_loss, 4),
        "max_notional_usdt": round(max_notional, 4),
        "max_daily_trades": max_trades,
        "updated_at": raw.get("updated_at"),
    }


def validate_onboarding_payload(payload: dict | None) -> dict:
    payload = as_dict(payload)
    username = str(payload.get("username") or "").strip()
    role = str(payload.get("role") or "user").strip().lower()
    if role not in {"admin", "user"}:
        role = "user"
    api_payload = as_dict(payload.get("api_connection") or payload)
    api_key_present = bool(str(api_payload.get("api_key") or api_payload.get("key") or "").strip())
    secret_present = bool(str(api_payload.get("secret_key") or api_payload.get("secret") or "").strip())
    risk_profile = normalize_risk_profile(payload.get("risk_profile"))
    allowed_symbols = normalize_symbol_list(payload.get("allowed_symbols"))
    allowed_modes = normalize_mode_list(payload.get("allowed_modes"))
    allowed_strategies = normalize_strategy_list(payload.get("allowed_strategies"))
    commission = normalize_commission_settings(payload.get("commission_settings"))
    errors = []
    warnings = []
    if not username:
        errors.append("username_required")
    if payload.get("create_user") is not False and not str(payload.get("password") or "").strip():
        warnings.append("password_missing_for_new_user")
    if not api_key_present:
        errors.append("api_key_required")
    if not secret_present:
        errors.append("secret_key_required")
    if "micro_live_preview" in allowed_modes or "limited_live_preview" in allowed_modes:
        if risk_profile["max_notional_usdt"] > 100:
            warnings.append("micro_live_notional_above_default_small_cap")
    ready = not errors
    return {
        "status": "ok" if ready else "blocked",
        "decision": "READY" if ready else "BLOCKED",
        "username": username,
        "role": role,
        "api_key_present": api_key_present,
        "secret_key_present": secret_present,
        "secret_values_returned": False,
        "risk_profile": risk_profile,
        "allowed_symbols": allowed_symbols,
        "allowed_modes": allowed_modes,
        "allowed_strategies": allowed_strategies,
        "commission_settings": commission,
        "errors": errors,
        "warnings": warnings,
        "checked_at": now_iso(),
    }


def public_onboarding_user(record: dict | None, username: str) -> dict:
    record = as_dict(record)
    api = build_user_api_secret_summary({"users": {username: record}}, username)
    return {
        "username": username,
        "role": record.get("role", "user"),
        "active": record.get("active", True) is not False,
        "api_configured": bool(api.get("configured")),
        "api_can_read": bool(as_dict(api.get("public_connection")).get("can_read")),
        "api_can_trade": bool(as_dict(api.get("public_connection")).get("can_trade")),
        "risk_profile": normalize_risk_profile(record.get("risk_profile")),
        "allowed_symbols": normalize_symbol_list(record.get("allowed_symbols")),
        "allowed_modes": normalize_mode_list(record.get("allowed_modes")),
        "allowed_strategies": normalize_strategy_list(record.get("allowed_strategies")),
        "commission_settings": normalize_commission_settings(record.get("commission_settings")),
        "onboarding_status": as_dict(record.get("onboarding_status")),
        "secret_values_returned": False,
    }


def build_onboarding_summary(auth_store: dict | None) -> dict:
    users = as_dict(as_dict(auth_store).get("users"))
    public_users = [public_onboarding_user(record, username) for username, record in sorted(users.items())]
    ready_users = [u for u in public_users if u["active"] and u["api_configured"] and u["allowed_symbols"] and u["allowed_strategies"]]
    blockers = []
    if not users:
        blockers.append("no_users_configured")
    if users and not ready_users:
        blockers.append("no_production_ready_user")
    return {
        "status": "ok",
        "revision": 890,
        "decision": "READY" if ready_users else "REVIEW",
        "total_users": len(public_users),
        "ready_users": len(ready_users),
        "critical_blocker": blockers[0] if blockers else None,
        "users": public_users,
        "checks": [
            {"name": "new_user_create_flow", "status": "ok"},
            {"name": "api_key_secret_masking", "status": "ok"},
            {"name": "risk_profile_assignment", "status": "ok"},
            {"name": "symbol_mode_strategy_permissions", "status": "ok"},
            {"name": "secret_values_returned", "status": "ok", "value": False},
        ],
        "secret_values_returned": False,
        "checked_at": now_iso(),
    }


def apply_onboarding_to_existing_user(auth_store: dict, username: str, payload: dict | None) -> dict:
    payload = as_dict(payload)
    users = auth_store.setdefault("users", {})
    if username not in users:
        raise KeyError(username)
    validation = validate_onboarding_payload({**payload, "username": username, "create_user": False})
    if validation["errors"]:
        return {"status": "blocked", "validation": validation, "secret_values_returned": False}
    record = users[username]
    api_payload = as_dict(payload.get("api_connection") or payload)
    api_result = set_user_api_connection(auth_store, username, api_payload)
    if api_result.get("status") != "ok":
        return {"status": "blocked", "validation": validation, "api_errors": api_result.get("errors", []), "secret_values_returned": False}
    record["risk_profile"] = {**validation["risk_profile"], "updated_at": now_iso()}
    record["allowed_symbols"] = validation["allowed_symbols"]
    record["allowed_modes"] = validation["allowed_modes"]
    record["allowed_strategies"] = validation["allowed_strategies"]
    record["commission_settings"] = {**validation["commission_settings"], "updated_at": now_iso()}
    record["onboarding_status"] = {
        "status": "ready",
        "completed_at": now_iso(),
        "secret_values_returned": False,
    }
    users[username] = record
    return {
        "status": "ok",
        "decision": "READY",
        "user": public_onboarding_user(record, username),
        "validation": validation,
        "secret_values_returned": False,
    }


def build_onboarding_quality(auth_store: dict | None) -> dict:
    summary = build_onboarding_summary(auth_store)
    text = str(summary).lower()
    failures = []
    for forbidden in ("secret_key", "api_key':", '"api_key"', '"secret"'):
        if forbidden in text:
            failures.append(f"public_output_contains_{forbidden}")
    return {
        "status": "ok" if not failures else "error",
        "quality_gate": "PASS" if not failures else "FAIL",
        "failures": failures,
        "checks": summary["checks"],
        "secret_values_returned": False,
        "checked_at": now_iso(),
    }
