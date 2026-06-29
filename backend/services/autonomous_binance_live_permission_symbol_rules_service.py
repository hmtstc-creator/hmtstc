from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from services.autonomous_live_config_governance_service import build_autonomous_live_config_governance


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "ok"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "none"}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _decimal(value: Any, fallback: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(fallback))


def _clean_symbol(value: Any) -> str:
    symbol = str(value or "UNKNOWN").strip().upper().replace("/", "")
    return "".join(ch for ch in symbol if ch.isalnum()) or "UNKNOWN"


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_binance_live_permission_symbol_rules") if isinstance(settings.get("autonomous_binance_live_permission_symbol_rules"), dict) else {}
    default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
    symbols = raw.get("symbol_whitelist") if isinstance(raw.get("symbol_whitelist"), list) else default_symbols
    clean_symbols = [_clean_symbol(item) for item in symbols if _clean_symbol(item) != "UNKNOWN"] or default_symbols
    default_rules = {
        "BTCUSDT": {"min_notional": 5.0, "step_size": "0.000001", "tick_size": "0.01", "status": "TRADING", "quote_asset": "USDT"},
        "ETHUSDT": {"min_notional": 5.0, "step_size": "0.0001", "tick_size": "0.01", "status": "TRADING", "quote_asset": "USDT"},
        "BNBUSDT": {"min_notional": 5.0, "step_size": "0.001", "tick_size": "0.01", "status": "TRADING", "quote_asset": "USDT"},
        "SOLUSDT": {"min_notional": 5.0, "step_size": "0.01", "tick_size": "0.01", "status": "TRADING", "quote_asset": "USDT"},
    }
    configured_rules = raw.get("symbol_rules_snapshot") if isinstance(raw.get("symbol_rules_snapshot"), dict) else {}
    merged = deepcopy(default_rules)
    for key, value in configured_rules.items():
        if isinstance(value, dict):
            sym = _clean_symbol(key)
            merged[sym] = {**merged.get(sym, {}), **value}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 101,
        "exchange": "binance",
        "account_type": str(raw.get("account_type") or "spot"),
        "require_read_permission": _safe_bool(raw.get("require_read_permission"), True),
        "require_trade_permission": _safe_bool(raw.get("require_trade_permission"), False),
        "require_micro_real_flag": _safe_bool(raw.get("require_micro_real_flag"), False),
        "symbol_whitelist": clean_symbols,
        "symbol_rules_snapshot": merged,
        "max_symbol_count": int(max(1, min(_safe_float(raw.get("max_symbol_count"), 6), 20))),
        "max_timestamp_drift_ms": int(max(250, min(_safe_float(raw.get("max_timestamp_drift_ms"), 1000), 5000))),
        "allow_network_calls": _safe_bool(raw.get("allow_network_calls"), False),
        "allow_direct_orders": _safe_bool(raw.get("allow_direct_orders"), False),
        "allow_real_submit": _safe_bool(raw.get("allow_real_submit"), False),
        "allow_runtime_write": _safe_bool(raw.get("allow_runtime_write"), False),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_live_config_governance") if isinstance(data.get("autonomous_live_config_governance"), dict) else None
    if raw and raw.get("revision") == 101 and raw.get("engine") == "autonomous_live_config_governance":
        return raw
    return build_autonomous_live_config_governance(data, settings, auth_store, username)


def _user_state(auth_store: dict, username: str) -> dict:
    users = auth_store.get("users") if isinstance(auth_store, dict) and isinstance(auth_store.get("users"), dict) else {}
    user = users.get(username) if isinstance(users.get(username), dict) else {}
    # Never expose key/secret values. Only expose presence and permission booleans.
    api_ref_present = bool(user.get("api_ref") or user.get("binance_api_ref") or user.get("secret_ref") or user.get("api_key_ref"))
    api_key_present = bool(user.get("api_key_present") or user.get("binance_api_key_present") or api_ref_present)
    secret_present = bool(user.get("secret_present") or user.get("binance_secret_present") or user.get("secret_ref") or user.get("api_secret_ref"))
    return {
        "role": str(user.get("role") or user.get("user_role") or "user"),
        "api_key_present": api_key_present,
        "api_secret_present": secret_present,
        "api_reference_present": api_ref_present,
        "read_permission": _safe_bool(user.get("read_permission") if "read_permission" in user else (user.get("can_read") if "can_read" in user else user.get("binance_read_permission")), api_key_present),
        "trade_permission": _safe_bool(user.get("trade_permission") if "trade_permission" in user else (user.get("can_trade") if "can_trade" in user else user.get("binance_trade_permission")), False),
        "permission_source": "auth_store_metadata_only",
        "secret_values_returned": False,
    }


def _clock_state(settings: dict, policy: dict) -> dict:
    clock = settings.get("exchange_clock") if isinstance(settings.get("exchange_clock"), dict) else {}
    drift = abs(_safe_float(clock.get("timestamp_drift_ms"), 0.0))
    return {
        "timestamp_drift_ms": drift,
        "max_timestamp_drift_ms": policy["max_timestamp_drift_ms"],
        "ok": drift <= policy["max_timestamp_drift_ms"],
        "source": "settings.exchange_clock.preview",
    }


def _validate_symbol(symbol: str, rules: dict) -> dict:
    min_notional = _decimal(rules.get("min_notional"), "0")
    step_size = _decimal(rules.get("step_size"), "0")
    tick_size = _decimal(rules.get("tick_size"), "0")
    status = str(rules.get("status") or "UNKNOWN").upper()
    quote_asset = str(rules.get("quote_asset") or ("USDT" if symbol.endswith("USDT") else "UNKNOWN")).upper()
    issues: list[str] = []
    if not symbol.endswith("USDT") or quote_asset != "USDT":
        issues.append("symbol_not_usdt_spot")
    if status != "TRADING":
        issues.append("symbol_not_trading")
    if min_notional <= 0:
        issues.append("min_notional_missing_or_invalid")
    if step_size <= 0:
        issues.append("step_size_missing_or_invalid")
    if tick_size <= 0:
        issues.append("tick_size_missing_or_invalid")
    return {
        "symbol": symbol,
        "status": status,
        "quote_asset": quote_asset,
        "min_notional": float(min_notional) if min_notional >= 0 else 0.0,
        "step_size": str(step_size),
        "tick_size": str(tick_size),
        "ok": not issues,
        "issues": issues,
    }


def _permission_checks(source: dict, policy: dict, user: dict, clock: dict, symbol_rows: list[dict]) -> dict[str, list[dict]]:
    def check(name: str, status: str, detail: str, required: bool = True) -> dict:
        return {"name": name, "status": status, "required": required, "detail": detail}

    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    safe_config = source.get("safe_runtime_config_snapshot") if isinstance(source.get("safe_runtime_config_snapshot"), dict) else {}
    flags = safe_config.get("flags") if isinstance(safe_config.get("flags"), dict) else {}
    bad_symbols = [row["symbol"] for row in symbol_rows if not row.get("ok")]
    return {
        "source_contract": [
            check("source_revision_101", "ok" if source.get("revision") == policy["required_source_revision"] else "blocked", "Rev102 must be fed by Rev101 live config governance."),
            check("source_not_blocked", "ok" if source.get("status") != "blocked" else "blocked", f"Rev101 source status: {source.get('status', 'unknown')}"),
            check("source_read_only", "ok" if command.get("places_order") is False and command.get("sends_exchange_request") is False else "blocked", "Upstream config governance must remain read-only."),
        ],
        "binance_permission_metadata": [
            check("api_key_reference_present", "ok" if user["api_key_present"] else "review", "API key reference/presence metadata is visible without exposing the key.", required=False),
            check("api_secret_reference_present", "ok" if user["api_secret_present"] else "review", "API secret reference/presence metadata is visible without exposing the secret.", required=False),
            check("read_permission_metadata", "ok" if user["read_permission"] else "blocked", "Read permission is required before live permission verification can progress.", required=policy["require_read_permission"]),
            check("trade_permission_metadata", "ok" if user["trade_permission"] else "review", "Trade permission is evidence only in Rev102; it does not enable submit.", required=policy["require_trade_permission"]),
        ],
        "symbol_rules_snapshot": [
            check("symbol_whitelist_present", "ok" if len(symbol_rows) > 0 else "blocked", "At least one whitelisted symbol must have rules."),
            check("symbol_count_within_cap", "ok" if len(symbol_rows) <= policy["max_symbol_count"] else "blocked", f"Symbol count: {len(symbol_rows)}, cap: {policy['max_symbol_count']}"),
            check("all_symbols_valid_for_usdt_spot", "ok" if not bad_symbols else "blocked", "Invalid symbols: " + (", ".join(bad_symbols) if bad_symbols else "none")),
        ],
        "live_safety_flags": [
            check("network_calls_disabled", "ok" if not policy["allow_network_calls"] and flags.get("HMTSTC_EXCHANGE_NETWORK_ENABLED") is False else "blocked", "Rev102 is permission/symbol verification preview only; no network calls."),
            check("direct_orders_disabled", "ok" if not policy["allow_direct_orders"] and flags.get("HMTSTC_DIRECT_ORDER_ENABLED") is False else "blocked", "Direct orders remain disabled."),
            check("real_submit_disabled", "ok" if not policy["allow_real_submit"] and flags.get("HMTSTC_REAL_SUBMIT_ENABLED") is False else "blocked", "Real submit remains disabled."),
            check("runtime_write_disabled", "ok" if not policy["allow_runtime_write"] and flags.get("HMTSTC_RUNTIME_WRITE_ENABLED") is False else "blocked", "Runtime writes remain disabled."),
            check("micro_real_flag_review_only", "ok" if flags.get("HMTSTC_MICRO_REAL_ENABLED") is False or not policy["require_micro_real_flag"] else "review", "Micro-real flag is not consumed for submit in Rev102.", required=False),
        ],
        "clock_and_secret_hygiene": [
            check("timestamp_drift_preview_ok", "ok" if clock["ok"] else "blocked", f"Timestamp drift preview: {clock['timestamp_drift_ms']} ms."),
            check("secret_values_not_returned", "ok" if user["secret_values_returned"] is False and safe_config.get("secret_values_returned") is False else "blocked", "Only metadata/booleans are returned; no API key/secret values."),
        ],
    }


def _flatten(checks: dict[str, list[dict]]) -> list[dict]:
    rows: list[dict] = []
    for section, items in checks.items():
        for item in items:
            row = dict(item)
            row["section"] = section
            rows.append(row)
    return rows


def build_autonomous_binance_live_permission_symbol_rules(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev102 Binance live permission + symbol rules verifier.

    This is still a read-only/live-preview layer. It verifies metadata needed for
    later live checks: API permission flags, secret-free key presence, timestamp
    drift preview, and Binance spot symbol rule snapshots. It never calls
    Binance, never places or closes orders, and never writes runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    user = _user_state(auth_store, username)
    clock = _clock_state(settings, policy)
    symbols = policy["symbol_whitelist"][: policy["max_symbol_count"]]
    symbol_rows = [_validate_symbol(symbol, policy["symbol_rules_snapshot"].get(symbol, {})) for symbol in symbols]
    checks = _permission_checks(source, policy, user, clock, symbol_rows)
    rows = _flatten(checks)
    blockers = [row for row in rows if row.get("required") and row.get("status") == "blocked"]
    reviews = [row for row in rows if row.get("status") == "review"]
    if not policy["enabled"]:
        blockers.append({"name": "binance_live_permission_symbol_rules_disabled", "status": "blocked", "required": True, "detail": "Rev102 policy is disabled.", "section": "policy"})
    status = "ok" if not blockers and not reviews else ("blocked" if blockers else "review")
    readiness = "BINANCE_LIVE_PERMISSION_SYMBOL_RULES_READY" if status == "ok" else ("BINANCE_LIVE_PERMISSION_SYMBOL_RULES_BLOCKED" if blockers else "BINANCE_LIVE_PERMISSION_SYMBOL_RULES_REVIEW")
    seed = f"rev102|{username}|{source.get('revision')}|{readiness}|{len(blockers)}|{len(reviews)}|{','.join(symbols)}"
    return {
        "status": status,
        "revision": 102,
        "engine": "autonomous_binance_live_permission_symbol_rules",
        "generated_at": now_iso(),
        "source_revision": source.get("revision"),
        "source_status": source.get("status"),
        "readiness": readiness,
        "governance_mode": "read_only_binance_permission_symbol_rules_preview",
        "exchange": policy["exchange"],
        "account_type": policy["account_type"],
        "permission_metadata": user,
        "timestamp_guard": clock,
        "symbol_rules": symbol_rows,
        "check_sections": checks,
        "check_totals": {
            "total": len(rows),
            "ok": len([row for row in rows if row.get("status") == "ok"]),
            "review": len(reviews),
            "blocked": len(blockers),
        },
        "blockers": [row.get("name") for row in blockers],
        "warnings": [row.get("name") for row in reviews],
        "command_preview": {
            "type": "binance_live_permission_symbol_rules_report",
            "read_only": True,
            "places_order": False,
            "closes_position": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "direct_order_enabled": False,
            "real_submit_enabled": False,
            "requires_manual_owner_approval": True,
            "next_allowed_step": "micro_real_submit_dry_run_rehearsal" if status != "blocked" else "resolve_binance_permission_or_symbol_rule_blockers",
        },
        "safety_contract": {
            "contains_secret": False,
            "secret_values_returned": False,
            "direct_order_placement": False,
            "exchange_request": False,
            "runtime_write": False,
            "approval_gated": True,
            "auto_apply": False,
            "manual_go_live_required": True,
        },
        "audit_evidence": {
            "evidence_id": sha256(seed.encode("utf-8")).hexdigest()[:24],
            "source_engine": source.get("engine"),
            "source_status": source.get("status"),
            "readiness": readiness,
            "symbol_count": len(symbol_rows),
            "blocked_count": len(blockers),
            "review_count": len(reviews),
        },
        "read_only": True,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    return {
        "status": payload.get("status", "review"),
        "revision": 102,
        "engine": "autonomous_binance_live_permission_symbol_rules_summary",
        "generated_at": payload.get("generated_at"),
        "readiness": payload.get("readiness"),
        "source_revision": payload.get("source_revision"),
        "source_status": payload.get("source_status"),
        "exchange": payload.get("exchange"),
        "account_type": payload.get("account_type"),
        "check_totals": payload.get("check_totals") or {},
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "timestamp_guard": payload.get("timestamp_guard") or {},
        "symbol_count": len(payload.get("symbol_rules") or []),
        "permission_metadata": {
            "api_key_present": (payload.get("permission_metadata") or {}).get("api_key_present"),
            "api_secret_present": (payload.get("permission_metadata") or {}).get("api_secret_present"),
            "read_permission": (payload.get("permission_metadata") or {}).get("read_permission"),
            "trade_permission": (payload.get("permission_metadata") or {}).get("trade_permission"),
            "secret_values_returned": False,
        },
        "next_allowed_step": command.get("next_allowed_step"),
        "read_only": True,
        "dry_run": True,
        "direct_order_placement": False,
        "exchange_request": False,
        "runtime_write": False,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_binance_live_permission_symbol_rules(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_binance_live_permission_symbol_rules(data, settings, auth_store, username))


def _sample_data() -> dict:
    source = {
        "status": "ok",
        "revision": 101,
        "engine": "autonomous_live_config_governance",
        "readiness": "CONFIG_READY_PREVIEW",
        "generated_at": "2026-05-24T00:00:00Z",
        "safe_runtime_config_snapshot": {
            "flags": {
                "HMTSTC_EXCHANGE_NETWORK_ENABLED": False,
                "HMTSTC_DIRECT_ORDER_ENABLED": False,
                "HMTSTC_REAL_SUBMIT_ENABLED": False,
                "HMTSTC_RUNTIME_WRITE_ENABLED": False,
                "HMTSTC_OWNER_CONFIRMATION_REQUIRED": True,
                "HMTSTC_MICRO_REAL_ENABLED": False,
            },
            "secret_values_returned": False,
        },
        "command_preview": {"read_only": True, "places_order": False, "sends_exchange_request": False, "writes_runtime_state": False, "real_submit_enabled": False},
        "safety_contract": {"contains_secret": False, "direct_order_placement": False, "exchange_request": False, "runtime_write": False},
    }
    return {"autonomous_live_config_governance": source}


def build_autonomous_binance_live_permission_symbol_rules_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    sample_auth = {"users": {username: {"role": "owner", "api_key_present": True, "secret_present": True, "read_permission": True, "trade_permission": False, "secret_ref": "masked"}}}
    payload = build_autonomous_binance_live_permission_symbol_rules(
        data or _sample_data(),
        settings or {"autonomous_binance_live_permission_symbol_rules": {"enabled": True}, "exchange_clock": {"timestamp_drift_ms": 50}},
        auth_store or sample_auth,
        username,
    )
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    safety = payload.get("safety_contract") if isinstance(payload.get("safety_contract"), dict) else {}
    totals = payload.get("check_totals") if isinstance(payload.get("check_totals"), dict) else {}
    checks = {
        "revision_is_102": payload.get("revision") == 102,
        "source_revision_is_101": payload.get("source_revision") == 101,
        "readiness_present": payload.get("readiness") in {"BINANCE_LIVE_PERMISSION_SYMBOL_RULES_READY", "BINANCE_LIVE_PERMISSION_SYMBOL_RULES_REVIEW", "BINANCE_LIVE_PERMISSION_SYMBOL_RULES_BLOCKED"},
        "permission_metadata_secret_free": (payload.get("permission_metadata") or {}).get("secret_values_returned") is False,
        "symbol_rules_present": len(payload.get("symbol_rules") or []) > 0,
        "timestamp_guard_present": isinstance(payload.get("timestamp_guard"), dict),
        "does_not_place_order": command.get("places_order") is False,
        "does_not_close_position": command.get("closes_position") is False,
        "does_not_call_exchange": command.get("sends_exchange_request") is False,
        "does_not_write_runtime": command.get("writes_runtime_state") is False,
        "real_submit_off": command.get("real_submit_enabled") is False,
        "contract_secret_free": safety.get("contains_secret") is False and safety.get("secret_values_returned") is False,
        "sample_has_no_required_blockers": totals.get("blocked", 1) == 0,
        "summary_revision_is_102": _summary_from_payload(payload).get("revision") == 102,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 102,
        "engine": "autonomous_binance_live_permission_symbol_rules_quality",
        "generated_at": now_iso(),
        "quality_status": "BINANCE_LIVE_PERMISSION_SYMBOL_RULES_OK" if passed else "BINANCE_LIVE_PERMISSION_SYMBOL_RULES_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_readiness": payload.get("readiness"),
        "sample_totals": totals,
    }
