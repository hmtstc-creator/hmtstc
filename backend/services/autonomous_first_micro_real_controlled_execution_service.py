from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_order_submitter_preview_service import build_autonomous_micro_real_order_submitter_preview


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if value is None:
        return fallback
    return bool(value)


def _clean_symbol(value: Any) -> str:
    symbol = str(value or "UNKNOWN").strip().upper().replace("/", "")
    return "".join(ch for ch in symbol if ch.isalnum()) or "UNKNOWN"


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_first_micro_real_controlled_execution") if isinstance(settings.get("autonomous_first_micro_real_controlled_execution"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "direct_submit_enabled": _safe_bool(raw.get("direct_submit_enabled"), False),
        "manual_enable_flag": str(raw.get("manual_enable_flag") or "").strip(),
        "required_manual_enable_flag": "ENABLE_FIRST_MICRO_REAL_CONTROLLED_EXECUTION_REV91",
        "owner_confirmation_token": str(raw.get("owner_confirmation_token") or "").strip(),
        "required_source_revision": 90,
        "required_source_state": "MICRO_REAL_ORDER_SUBMITTER_PREVIEW_READY",
        "required_source_lane": "MICRO_REAL_ORDER_SUBMITTER_PREVIEW",
        "max_single_order_notional_usdt": max(5.0, _safe_float(raw.get("max_single_order_notional_usdt"), 15.0)),
        "max_single_order_loss_usdt": max(0.10, _safe_float(raw.get("max_single_order_loss_usdt"), 0.75)),
        "daily_micro_submit_cap": max(1, _safe_int(raw.get("daily_micro_submit_cap"), 1)),
        "single_symbol_daily_cap": 1,
        "allowed_symbols": [
            _clean_symbol(item) for item in raw.get("allowed_symbols", ["BTCUSDT", "ETHUSDT"])
            if str(item or "").strip()
        ] if isinstance(raw.get("allowed_symbols", []), list) else ["BTCUSDT", "ETHUSDT"],
        "require_emergency_close_ready": _safe_bool(raw.get("require_emergency_close_ready"), True),
        "emergency_close_ready": _safe_bool(raw.get("emergency_close_ready"), False),
        "kill_switch_active": _safe_bool(raw.get("kill_switch_active"), False),
        "safe_mode_active": _safe_bool(raw.get("safe_mode_active"), False),
        "api_trade_permission_verified": _safe_bool(raw.get("api_trade_permission_verified"), False),
        "balance_reconciliation_required": _safe_bool(raw.get("balance_reconciliation_required"), True),
        "balance_reconciliation_ok": _safe_bool(raw.get("balance_reconciliation_ok"), False),
        "exchange": "binance",
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "direct_submit_default_off": True,
        "audit_evidence_required": True,
        "post_submit_tracker_required": True,
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_order_submitter_preview") if isinstance(data.get("autonomous_micro_real_order_submitter_preview"), dict) else None
    if raw and raw.get("revision") == 90 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_order_submitter_preview(data, settings, auth_store, username)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _history_counts(data: dict, symbol: str) -> dict:
    today = _today_key()
    items: list[dict] = []
    for key in ("micro_real_execution_audit", "micro_real_order_history", "exchange_order_audit", "micro_real_submit_history"):
        raw = data.get(key)
        if isinstance(raw, list):
            items.extend(item for item in raw if isinstance(item, dict))
    submitted = [item for item in items if str(item.get("created_at") or item.get("submitted_at") or item.get("date") or "").startswith(today)]
    same_symbol = [item for item in submitted if _clean_symbol(item.get("symbol")) == symbol]
    return {
        "today_key": today,
        "today_submit_total": len(submitted),
        "today_symbol_submit_total": len(same_symbol),
    }


def _execution_id(username: str, source_id: str, symbol: str, notional: float) -> str:
    seed = f"rev91:{username}:{source_id}:{symbol}:{round(notional, 8)}"
    return "fmre_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


def _audit_id(execution_id: str, source_id: str) -> str:
    return "audit_" + sha256(f"{execution_id}:{source_id}".encode("utf-8")).hexdigest()[:20]


def _submit_request(source: dict, execution_id: str, allow_network: bool) -> dict:
    src = source.get("submit_request_preview") if isinstance(source.get("submit_request_preview"), dict) else {}
    return {
        "exchange": "binance",
        "endpoint": "/api/v3/order",
        "method": "POST",
        "symbol": _clean_symbol(src.get("symbol") or source.get("symbol")),
        "side": src.get("side"),
        "type": src.get("type"),
        "quoteOrderQty": _safe_float(src.get("quoteOrderQty"), 0.0),
        "newClientOrderId": execution_id,
        "sourceClientOrderId": src.get("newClientOrderId") or source.get("submitter_id"),
        "recvWindow": src.get("recvWindow"),
        "dry_run": not allow_network,
        "network_call_planned": allow_network,
        "contains_secret": False,
    }


def build_autonomous_first_micro_real_controlled_execution(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev91 first controlled micro-real execution gate.

    The service creates a one-shot micro-real execution contract from Rev90.
    It supports live-ready planning only when explicit enable flag, owner token,
    emergency guard, API trade permission and balance reconciliation are all OK.
    The implementation never performs a network call itself and never writes
    runtime state; it only returns the final submit plan and audit evidence model.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    contract = source.get("final_safety_contract") if isinstance(source.get("final_safety_contract"), dict) else {}
    request = source.get("submit_request_preview") if isinstance(source.get("submit_request_preview"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []

    symbol = _clean_symbol(request.get("symbol") or source.get("symbol") or command.get("symbol"))
    notional = _safe_float(request.get("quoteOrderQty"), 0.0)
    max_loss = _safe_float(contract.get("max_order_loss_usdt"), 0.0)
    source_submitter_id = str(source.get("submitter_id") or request.get("newClientOrderId") or "")
    expected_owner_token = str(source.get("owner_confirmation_token_preview") or "")
    execution_id = _execution_id(username, source_submitter_id, symbol, notional)
    counts = _history_counts(data, symbol)

    if not policy["enabled"]:
        blockers.append("first_micro_real_controlled_execution_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_submitter_revision_mismatch")
    if source.get("status") != "ok":
        blockers.append("source_submitter_not_ok")
    if source.get("submitter_state") != policy["required_source_state"]:
        blockers.append("source_submitter_state_not_ready")
    if source.get("target_lane") != policy["required_source_lane"]:
        blockers.append("source_submitter_lane_mismatch")
    if command.get("approved_for_first_micro_real_controlled_execution") is not True:
        blockers.append("source_not_approved_for_first_micro_real_controlled_execution")
    if source.get("places_order") is not False or source.get("sends_exchange_request") is not False or source.get("writes_runtime_state") is not False:
        blockers.append("source_submitter_not_safely_preview_only")
    if not source_submitter_id.startswith("mros_"):
        blockers.append("source_submitter_id_invalid")
    if not expected_owner_token.startswith("mro_own_"):
        blockers.append("owner_confirmation_token_source_missing")
    if symbol not in policy["allowed_symbols"]:
        blockers.append("symbol_not_allowed_for_first_micro_execution")
    if notional <= 0 or notional > policy["max_single_order_notional_usdt"]:
        blockers.append("first_micro_notional_outside_contract")
    if max_loss > policy["max_single_order_loss_usdt"]:
        blockers.append("first_micro_loss_outside_contract")
    if counts["today_submit_total"] >= policy["daily_micro_submit_cap"]:
        blockers.append("daily_micro_submit_cap_reached")
    if counts["today_symbol_submit_total"] >= policy["single_symbol_daily_cap"]:
        blockers.append("single_symbol_daily_micro_submit_cap_reached")
    if policy["kill_switch_active"]:
        blockers.append("kill_switch_active")
    if policy["safe_mode_active"]:
        blockers.append("safe_mode_active")
    if policy["require_emergency_close_ready"] and not policy["emergency_close_ready"]:
        blockers.append("emergency_close_not_ready")
    if not policy["api_trade_permission_verified"]:
        blockers.append("api_trade_permission_not_verified")
    if policy["balance_reconciliation_required"] and not policy["balance_reconciliation_ok"]:
        blockers.append("balance_reconciliation_not_ok")

    manual_flag_ok = policy["manual_enable_flag"] == policy["required_manual_enable_flag"]
    owner_token_ok = policy["owner_confirmation_token"] == expected_owner_token and bool(expected_owner_token)
    direct_submit_requested = policy["direct_submit_enabled"] is True
    network_allowed = policy["network_calls_allowed"] is True
    runtime_write_enabled = policy["runtime_write_enabled"] is True

    if not direct_submit_requested:
        warnings.append("direct_submit_default_off_preview_only")
    if not manual_flag_ok:
        blockers.append("manual_enable_flag_missing_or_invalid")
    if not owner_token_ok:
        blockers.append("owner_confirmation_token_missing_or_invalid")
    if direct_submit_requested and not network_allowed:
        blockers.append("network_calls_not_allowed_for_live_submit")
    if direct_submit_requested and not runtime_write_enabled:
        blockers.append("runtime_write_not_enabled_for_audit_tracker")

    live_ready = not blockers and direct_submit_requested and manual_flag_ok and owner_token_ok and network_allowed and runtime_write_enabled
    state = "FIRST_MICRO_REAL_LIVE_READY" if live_ready else ("FIRST_MICRO_REAL_REVIEW" if not blockers else "FIRST_MICRO_REAL_BLOCKED")
    status = "ok" if live_ready else ("review" if not blockers else "blocked")
    submit_request = _submit_request(source, execution_id, live_ready)
    audit = {
        "audit_id": _audit_id(execution_id, source_submitter_id),
        "execution_id": execution_id,
        "source_submitter_id": source_submitter_id,
        "symbol": symbol,
        "notional_usdt": round(notional, 8),
        "max_loss_usdt": round(max_loss, 8),
        "owner_confirmation_matched": owner_token_ok,
        "manual_enable_flag_matched": manual_flag_ok,
        "contains_secret": False,
        "write_scope": "runtime_safe_micro_real_audit" if runtime_write_enabled else "preview_only_no_runtime_write",
    }
    tracker = {
        "tracker_id": "mrt_" + sha256(execution_id.encode("utf-8")).hexdigest()[:20],
        "expected_states": ["NEW", "ACKNOWLEDGED", "FILLED", "PARTIALLY_FILLED", "REJECTED", "EXPIRED"],
        "post_submit_status_tracker_required": True,
        "enabled_after_submit": live_ready,
        "contains_secret": False,
    }
    score = max(0.0, min(100.0, _safe_float(source.get("submitter_score"), 0.0) - len(set(blockers)) * 12.0 - len(set(warnings)) * 1.0))

    return {
        "status": status,
        "revision": 91,
        "engine": "autonomous_first_micro_real_controlled_execution",
        "generated_at": now_iso(),
        "read_only": not live_ready,
        "auto_apply": False,
        "dry_run": not live_ready,
        "places_order": live_ready,
        "sends_exchange_request": live_ready,
        "writes_runtime_state": live_ready,
        "execution_state": state,
        "execution_score": round(score, 2),
        "execution_id": execution_id,
        "source_revision": source.get("revision"),
        "source_submitter_state": source.get("submitter_state"),
        "source_submitter_id": source_submitter_id,
        "exchange": "binance",
        "symbol": symbol,
        "target_lane": "FIRST_MICRO_REAL_CONTROLLED_EXECUTION" if live_ready else "MICRO_REAL_EXECUTION_PREVIEW_LOCKED",
        "live_submit_ready": live_ready,
        "live_submit_blocked_reason_count": len(set(blockers)),
        "final_live_safety_contract": {
            "explicit_enable_required": True,
            "manual_enable_flag_required": policy["required_manual_enable_flag"],
            "owner_confirmation_token_required": True,
            "emergency_close_ready_required": policy["require_emergency_close_ready"],
            "api_trade_permission_required": True,
            "balance_reconciliation_required": policy["balance_reconciliation_required"],
            "daily_micro_submit_cap": policy["daily_micro_submit_cap"],
            "single_symbol_daily_cap": policy["single_symbol_daily_cap"],
            "max_single_order_notional_usdt": policy["max_single_order_notional_usdt"],
            "max_single_order_loss_usdt": policy["max_single_order_loss_usdt"],
            "allowed_symbols": policy["allowed_symbols"],
        },
        "live_preflight": {
            "source_chain_ok": not any(item in blockers for item in [
                "source_submitter_revision_mismatch",
                "source_submitter_not_ok",
                "source_submitter_state_not_ready",
                "source_submitter_lane_mismatch",
                "source_not_approved_for_first_micro_real_controlled_execution",
            ]),
            "manual_enable_flag_ok": manual_flag_ok,
            "owner_confirmation_token_ok": owner_token_ok,
            "emergency_close_ready": policy["emergency_close_ready"],
            "api_trade_permission_verified": policy["api_trade_permission_verified"],
            "balance_reconciliation_ok": policy["balance_reconciliation_ok"],
            "kill_switch_clear": not policy["kill_switch_active"],
            "safe_mode_clear": not policy["safe_mode_active"],
            "order_caps_ok": not any(item in blockers for item in ["daily_micro_submit_cap_reached", "single_symbol_daily_micro_submit_cap_reached"]),
            "network_calls_allowed": network_allowed,
            "runtime_write_enabled": runtime_write_enabled,
            "direct_submit_enabled": direct_submit_requested,
            "live_submit_ready": live_ready,
        },
        "history_guard": {
            **counts,
            "daily_micro_submit_cap": policy["daily_micro_submit_cap"],
            "single_symbol_daily_cap": policy["single_symbol_daily_cap"],
            "ok": counts["today_submit_total"] < policy["daily_micro_submit_cap"] and counts["today_symbol_submit_total"] < policy["single_symbol_daily_cap"],
        },
        "submit_request_final_preview": submit_request,
        "exchange_response_model": {
            "expected_ack_fields": ["symbol", "orderId", "clientOrderId", "transactTime", "status"],
            "normalize_status": True,
            "contains_secret": False,
            "network_call_executed_by_this_service": False,
        },
        "post_submit_status_tracker": tracker,
        "audit_evidence": audit,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": {k: v for k, v in policy.items() if k not in {"owner_confirmation_token"}},
        "command_preview": {
            "type": "first_micro_real_controlled_execution_contract",
            "source_revision": 91,
            "execution_state": state,
            "next_action": "SUBMIT_FIRST_MICRO_REAL_ORDER" if live_ready else "KEEP_FIRST_MICRO_REAL_LOCKED",
            "symbol": symbol,
            "lane": "FIRST_MICRO_REAL_CONTROLLED_EXECUTION" if live_ready else "MICRO_REAL_EXECUTION_PREVIEW_LOCKED",
            "execution_id": execution_id,
            "requires_owner_confirmation": True,
            "requires_manual_enable_flag": True,
            "read_only": not live_ready,
            "auto_apply": False,
            "dry_run": not live_ready,
            "places_order": live_ready,
            "sends_exchange_request": live_ready,
            "writes_runtime_state": live_ready,
            "live_submit_ready": live_ready,
            "approved_for_micro_real_position_tracker": live_ready,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    preflight = payload.get("live_preflight") if isinstance(payload.get("live_preflight"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 91,
        "engine": "autonomous_first_micro_real_controlled_execution_summary",
        "generated_at": payload.get("generated_at"),
        "execution_state": payload.get("execution_state"),
        "execution_score": payload.get("execution_score"),
        "next_action": payload.get("command_preview", {}).get("next_action") if isinstance(payload.get("command_preview"), dict) else None,
        "symbol": payload.get("symbol"),
        "target_lane": payload.get("target_lane"),
        "live_submit_ready": payload.get("live_submit_ready") is True,
        "places_order": payload.get("places_order") is True,
        "sends_exchange_request": payload.get("sends_exchange_request") is True,
        "writes_runtime_state": payload.get("writes_runtime_state") is True,
        "manual_enable_flag_ok": preflight.get("manual_enable_flag_ok") is True,
        "owner_confirmation_token_ok": preflight.get("owner_confirmation_token_ok") is True,
        "emergency_close_ready": preflight.get("emergency_close_ready") is True,
        "api_trade_permission_verified": preflight.get("api_trade_permission_verified") is True,
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
    }


def build_summary_autonomous_first_micro_real_controlled_execution(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_first_micro_real_controlled_execution(data, settings, auth_store, username))


def build_autonomous_first_micro_real_controlled_execution_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_first_micro_real_controlled_execution(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    request = payload.get("submit_request_final_preview") if isinstance(payload.get("submit_request_final_preview"), dict) else {}
    preflight = payload.get("live_preflight") if isinstance(payload.get("live_preflight"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_91": payload.get("revision") == 91,
        "source_submitter_chain_present": payload.get("source_revision") == 90,
        "final_live_safety_contract_present": isinstance(payload.get("final_live_safety_contract"), dict) and payload.get("final_live_safety_contract", {}).get("explicit_enable_required") is True,
        "owner_confirmation_gate_present": "owner_confirmation_token_ok" in preflight,
        "manual_enable_gate_present": "manual_enable_flag_ok" in preflight,
        "emergency_close_guard_present": "emergency_close_ready" in preflight,
        "api_trade_permission_guard_present": "api_trade_permission_verified" in preflight,
        "history_guard_present": isinstance(payload.get("history_guard"), dict) and "daily_micro_submit_cap" in payload.get("history_guard", {}),
        "submit_request_uses_real_endpoint_when_live": request.get("endpoint") == "/api/v3/order",
        "secret_safe": request.get("contains_secret") is False and payload.get("audit_evidence", {}).get("contains_secret") is False,
        "service_does_not_execute_network_call": payload.get("exchange_response_model", {}).get("network_call_executed_by_this_service") is False,
        "post_submit_tracker_present": isinstance(payload.get("post_submit_status_tracker"), dict) and payload.get("post_submit_status_tracker", {}).get("post_submit_status_tracker_required") is True,
        "summary_revision_is_91": summary.get("revision") == 91,
        "preview_mode_remains_locked_without_explicit_flags": (payload.get("live_submit_ready") is False and command.get("places_order") is False) or payload.get("live_submit_ready") is True,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 91,
        "engine": "autonomous_first_micro_real_controlled_execution_quality",
        "generated_at": now_iso(),
        "quality_status": "FIRST_MICRO_REAL_CONTROLLED_EXECUTION_OK" if passed else "FIRST_MICRO_REAL_CONTROLLED_EXECUTION_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("execution_state"),
        "sample_action": command.get("next_action"),
    }
