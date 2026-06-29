from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from hashlib import sha256
from typing import Any

from services.autonomous_binance_live_permission_symbol_rules_service import build_autonomous_binance_live_permission_symbol_rules


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
    symbol = str(value or "BTCUSDT").strip().upper().replace("/", "")
    return "".join(ch for ch in symbol if ch.isalnum()) or "BTCUSDT"


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_submit_emergency_rehearsal") if isinstance(settings.get("autonomous_micro_real_submit_emergency_rehearsal"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 102,
        "symbol": _clean_symbol(raw.get("symbol") or "BTCUSDT"),
        "side": str(raw.get("side") or "BUY").upper(),
        "order_type": str(raw.get("order_type") or "MARKET").upper(),
        "probe_notional_usdt": max(1.0, min(_safe_float(raw.get("probe_notional_usdt"), 5.0), 25.0)),
        "max_probe_notional_usdt": max(1.0, min(_safe_float(raw.get("max_probe_notional_usdt"), 10.0), 50.0)),
        "max_expected_loss_usdt": max(0.1, min(_safe_float(raw.get("max_expected_loss_usdt"), 1.0), 5.0)),
        "reference_price": max(0.00000001, _safe_float(raw.get("reference_price"), 50000.0)),
        "allow_network_calls": _safe_bool(raw.get("allow_network_calls"), False),
        "allow_direct_orders": _safe_bool(raw.get("allow_direct_orders"), False),
        "allow_real_submit": _safe_bool(raw.get("allow_real_submit"), False),
        "allow_runtime_write": _safe_bool(raw.get("allow_runtime_write"), False),
        "owner_confirmation_required": _safe_bool(raw.get("owner_confirmation_required"), True),
        "owner_confirmation_present": _safe_bool(raw.get("owner_confirmation_present"), False),
        "emergency_close_rehearsal_required": _safe_bool(raw.get("emergency_close_rehearsal_required"), True),
        "emergency_close_path_configured": _safe_bool(raw.get("emergency_close_path_configured"), True),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_binance_live_permission_symbol_rules") if isinstance(data.get("autonomous_binance_live_permission_symbol_rules"), dict) else None
    if raw and raw.get("revision") == 102 and raw.get("engine") == "autonomous_binance_live_permission_symbol_rules":
        return raw
    return build_autonomous_binance_live_permission_symbol_rules(data, settings, auth_store, username)


def _symbol_rule(source: dict, symbol: str) -> dict:
    for row in source.get("symbol_rules") or []:
        if isinstance(row, dict) and row.get("symbol") == symbol:
            return row
    return {"symbol": symbol, "ok": False, "min_notional": 0, "step_size": "0", "tick_size": "0", "issues": ["symbol_rule_missing"]}


def _quantize_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _build_submit_rehearsal(policy: dict, symbol_rule: dict) -> dict:
    step = _decimal(symbol_rule.get("step_size"), "0.000001")
    tick = _decimal(symbol_rule.get("tick_size"), "0.01")
    price = _quantize_down(_decimal(policy["reference_price"], "0"), tick)
    qty = _quantize_down(_decimal(policy["probe_notional_usdt"], "0") / max(price, Decimal("0.00000001")), step)
    notional = qty * price
    seed = f"rev103-submit:{policy['symbol']}:{policy['side']}:{policy['order_type']}:{policy['probe_notional_usdt']}"
    issues: list[str] = []
    min_notional = _decimal(symbol_rule.get("min_notional"), "0")
    if not symbol_rule.get("ok"):
        issues.append("symbol_rule_not_ready")
    if notional < min_notional:
        issues.append("below_min_notional")
    if float(notional) > policy["max_probe_notional_usdt"]:
        issues.append("above_max_probe_notional")
    if policy["side"] not in {"BUY", "SELL"}:
        issues.append("invalid_side")
    if policy["order_type"] not in {"MARKET", "LIMIT"}:
        issues.append("invalid_order_type")
    return {
        "status": "ok" if not issues else "blocked",
        "type": "micro_real_submit_dry_run_rehearsal",
        "symbol": policy["symbol"],
        "side": policy["side"],
        "order_type": policy["order_type"],
        "quantity_preview": str(qty.normalize()),
        "price_preview": str(price.normalize()),
        "notional_preview_usdt": float(notional),
        "max_probe_notional_usdt": policy["max_probe_notional_usdt"],
        "max_expected_loss_usdt": policy["max_expected_loss_usdt"],
        "idempotency_key_preview": sha256(seed.encode("utf-8")).hexdigest()[:32],
        "exchange_payload_preview": {
            "symbol": policy["symbol"],
            "side": policy["side"],
            "type": policy["order_type"],
            "quantity": str(qty.normalize()),
            "dry_run_only": True,
        },
        "issues": issues,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
    }


def _build_emergency_rehearsal(policy: dict, submit: dict) -> dict:
    issues: list[str] = []
    if policy["emergency_close_rehearsal_required"] and not policy["emergency_close_path_configured"]:
        issues.append("emergency_close_path_missing")
    if submit.get("status") != "ok":
        issues.append("submit_rehearsal_not_ready")
    close_side = "SELL" if policy["side"] == "BUY" else "BUY"
    seed = f"rev103-emergency-close:{policy['symbol']}:{submit.get('idempotency_key_preview')}"
    return {
        "status": "ok" if not issues else "blocked",
        "type": "emergency_close_rehearsal",
        "symbol": policy["symbol"],
        "close_side_preview": close_side,
        "trigger_policy": "manual_or_safety_supervisor_emergency_only",
        "close_payload_preview": {
            "symbol": policy["symbol"],
            "side": close_side,
            "type": "MARKET",
            "quantity": submit.get("quantity_preview", "0"),
            "dry_run_only": True,
        },
        "emergency_rehearsal_id": sha256(seed.encode("utf-8")).hexdigest()[:32],
        "issues": issues,
        "places_order": False,
        "closes_position": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
    }


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {"name": name, "status": status, "required": required, "detail": detail}


def build_autonomous_micro_real_submit_emergency_rehearsal(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data = data if isinstance(data, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    symbol_rule = _symbol_rule(source, policy["symbol"])
    submit = _build_submit_rehearsal(policy, symbol_rule)
    emergency = _build_emergency_rehearsal(policy, submit)

    source_command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    source_safety = source.get("safety_contract") if isinstance(source.get("safety_contract"), dict) else {}
    checks = [
        _check("rehearsal_enabled", "ok" if policy["enabled"] else "blocked", "Rev103 rehearsal policy must be enabled."),
        _check("source_revision_102", "ok" if source.get("revision") == 102 else "blocked", "Rev103 must be fed by Rev102 Binance permission and symbol rules."),
        _check("source_not_blocked", "ok" if source.get("status") != "blocked" else "blocked", f"Rev102 source status: {source.get('status', 'unknown')}"),
        _check("source_does_not_call_exchange", "ok" if source_command.get("sends_exchange_request") is False else "blocked", "Upstream verifier must not call the exchange."),
        _check("source_secret_free", "ok" if source_safety.get("contains_secret") is False else "blocked", "No secret value may be present in the source contract."),
        _check("network_calls_disabled", "ok" if not policy["allow_network_calls"] else "blocked", "Rev103 is rehearsal-only; network calls stay disabled."),
        _check("direct_orders_disabled", "ok" if not policy["allow_direct_orders"] else "blocked", "Direct orders stay disabled."),
        _check("real_submit_disabled", "ok" if not policy["allow_real_submit"] else "blocked", "Real submit stays disabled in Rev103."),
        _check("runtime_write_disabled", "ok" if not policy["allow_runtime_write"] else "blocked", "Runtime writes stay disabled."),
        _check("owner_confirmation_required", "ok" if policy["owner_confirmation_required"] else "blocked", "Owner confirmation remains mandatory for later live action."),
        _check("owner_confirmation_not_consumed", "ok" if not policy["owner_confirmation_present"] else "review", "Rev103 may detect but must not consume owner confirmation.", required=False),
        _check("submit_rehearsal_ok", "ok" if submit.get("status") == "ok" else "blocked", "Dry-run submit payload must pass local guards."),
        _check("emergency_close_rehearsal_ok", "ok" if emergency.get("status") == "ok" else "blocked", "Emergency close rehearsal must be available before live submit."),
    ]
    blockers = [c for c in checks if c["status"] == "blocked" and c.get("required")]
    reviews = [c for c in checks if c["status"] == "review"]
    status = "blocked" if blockers else ("review" if reviews or source.get("status") == "review" else "ok")
    readiness = {
        "ok": "MICRO_REAL_REHEARSAL_READY_PREVIEW",
        "review": "MICRO_REAL_REHEARSAL_REVIEW",
        "blocked": "MICRO_REAL_REHEARSAL_BLOCKED",
    }[status]
    seed = f"rev103:{username}:{policy['symbol']}:{status}:{submit.get('idempotency_key_preview')}:{emergency.get('emergency_rehearsal_id')}"
    return {
        "status": status,
        "revision": 103,
        "engine": "autonomous_micro_real_submit_emergency_rehearsal",
        "generated_at": now_iso(),
        "source_revision": source.get("revision"),
        "source_status": source.get("status"),
        "readiness": readiness,
        "mode": "dry_run_rehearsal_only",
        "policy": {
            "symbol": policy["symbol"],
            "probe_notional_usdt": policy["probe_notional_usdt"],
            "max_probe_notional_usdt": policy["max_probe_notional_usdt"],
            "max_expected_loss_usdt": policy["max_expected_loss_usdt"],
            "owner_confirmation_required": policy["owner_confirmation_required"],
            "secret_values_returned": False,
        },
        "symbol_rule_used": symbol_rule,
        "submit_rehearsal": submit,
        "emergency_close_rehearsal": emergency,
        "checks": checks,
        "check_totals": {"total": len(checks), "ok": len([c for c in checks if c["status"] == "ok"]), "review": len(reviews), "blocked": len(blockers)},
        "blockers": [c["name"] for c in blockers],
        "warnings": [c["name"] for c in reviews],
        "command_preview": {
            "type": "micro_real_submit_and_emergency_close_rehearsal_report",
            "read_only": True,
            "dry_run": True,
            "places_order": False,
            "closes_position": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "direct_order_enabled": False,
            "real_submit_enabled": False,
            "requires_manual_owner_approval": True,
            "next_allowed_step": "runtime_audit_store_and_idempotency_lock" if status != "blocked" else "resolve_rehearsal_blockers",
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
            "emergency_close_required_before_live_submit": True,
        },
        "audit_evidence": {
            "evidence_id": sha256(seed.encode("utf-8")).hexdigest()[:24],
            "source_engine": source.get("engine"),
            "source_status": source.get("status"),
            "readiness": readiness,
            "blocked_count": len(blockers),
            "review_count": len(reviews),
        },
        "read_only": True,
        "dry_run": True,
        "places_order": False,
        "closes_position": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    submit = payload.get("submit_rehearsal") if isinstance(payload.get("submit_rehearsal"), dict) else {}
    emergency = payload.get("emergency_close_rehearsal") if isinstance(payload.get("emergency_close_rehearsal"), dict) else {}
    return {
        "status": payload.get("status", "review"),
        "revision": 103,
        "engine": "autonomous_micro_real_submit_emergency_rehearsal_summary",
        "generated_at": payload.get("generated_at"),
        "readiness": payload.get("readiness"),
        "source_revision": payload.get("source_revision"),
        "source_status": payload.get("source_status"),
        "symbol": (payload.get("policy") or {}).get("symbol"),
        "submit_rehearsal_status": submit.get("status"),
        "emergency_close_rehearsal_status": emergency.get("status"),
        "notional_preview_usdt": submit.get("notional_preview_usdt"),
        "idempotency_key_preview": submit.get("idempotency_key_preview"),
        "check_totals": payload.get("check_totals") or {},
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "next_allowed_step": command.get("next_allowed_step"),
        "read_only": True,
        "dry_run": True,
        "direct_order_placement": False,
        "exchange_request": False,
        "runtime_write": False,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_micro_real_submit_emergency_rehearsal(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_submit_emergency_rehearsal(data, settings, auth_store, username))


def _sample_data() -> dict:
    source = {
        "status": "review",
        "revision": 102,
        "engine": "autonomous_binance_live_permission_symbol_rules",
        "readiness": "BINANCE_LIVE_PERMISSION_SYMBOL_RULES_REVIEW",
        "symbol_rules": [
            {"symbol": "BTCUSDT", "status": "TRADING", "quote_asset": "USDT", "min_notional": 5.0, "step_size": "0.000001", "tick_size": "0.01", "ok": True, "issues": []}
        ],
        "command_preview": {"read_only": True, "places_order": False, "closes_position": False, "sends_exchange_request": False, "writes_runtime_state": False, "real_submit_enabled": False},
        "safety_contract": {"contains_secret": False, "secret_values_returned": False, "direct_order_placement": False, "exchange_request": False, "runtime_write": False},
    }
    return {"autonomous_binance_live_permission_symbol_rules": source}


def build_autonomous_micro_real_submit_emergency_rehearsal_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_submit_emergency_rehearsal(
        data or _sample_data(),
        settings or {"autonomous_micro_real_submit_emergency_rehearsal": {"enabled": True, "symbol": "BTCUSDT", "probe_notional_usdt": 6, "reference_price": 50000}},
        auth_store or {"users": {username: {"role": "owner", "api_key_present": True, "secret_present": True, "read_permission": True, "trade_permission": False}}},
        username,
    )
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    safety = payload.get("safety_contract") if isinstance(payload.get("safety_contract"), dict) else {}
    submit = payload.get("submit_rehearsal") if isinstance(payload.get("submit_rehearsal"), dict) else {}
    emergency = payload.get("emergency_close_rehearsal") if isinstance(payload.get("emergency_close_rehearsal"), dict) else {}
    checks = {
        "revision_is_103": payload.get("revision") == 103,
        "source_revision_is_102": payload.get("source_revision") == 102,
        "readiness_present": payload.get("readiness") in {"MICRO_REAL_REHEARSAL_READY_PREVIEW", "MICRO_REAL_REHEARSAL_REVIEW", "MICRO_REAL_REHEARSAL_BLOCKED"},
        "submit_rehearsal_present": submit.get("type") == "micro_real_submit_dry_run_rehearsal",
        "emergency_close_rehearsal_present": emergency.get("type") == "emergency_close_rehearsal",
        "idempotency_preview_present": bool(submit.get("idempotency_key_preview")),
        "does_not_place_order": command.get("places_order") is False,
        "does_not_close_position": command.get("closes_position") is False,
        "does_not_call_exchange": command.get("sends_exchange_request") is False,
        "does_not_write_runtime": command.get("writes_runtime_state") is False,
        "real_submit_off": command.get("real_submit_enabled") is False,
        "contract_secret_free": safety.get("contains_secret") is False and safety.get("secret_values_returned") is False,
        "summary_revision_is_103": _summary_from_payload(payload).get("revision") == 103,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 103,
        "engine": "autonomous_micro_real_submit_emergency_rehearsal_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_SUBMIT_EMERGENCY_REHEARSAL_OK" if passed else "MICRO_REAL_SUBMIT_EMERGENCY_REHEARSAL_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_readiness": payload.get("readiness"),
        "sample_totals": payload.get("check_totals") or {},
    }
