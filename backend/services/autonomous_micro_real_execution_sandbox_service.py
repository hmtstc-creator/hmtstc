from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_approval_gate_service import build_autonomous_micro_real_approval_gate
from services.user_api_secret_layer_service import public_api_connection


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_execution_sandbox") if isinstance(settings.get("autonomous_micro_real_execution_sandbox"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "dry_run": _safe_bool(raw.get("dry_run"), True),
        "live_ready_preview": _safe_bool(raw.get("live_ready_preview"), True),
        "require_approval_state": "MICRO_REAL_APPROVAL_READY",
        "require_owner_confirmation": True,
        "require_target_lane": "MICRO_REAL_APPROVAL_PREVIEW",
        "max_sandbox_notional_usdt": max(5.0, _safe_float(raw.get("max_sandbox_notional_usdt"), 25.0)),
        "max_sandbox_loss_usdt": max(0.25, _safe_float(raw.get("max_sandbox_loss_usdt"), 1.0)),
        "allowed_symbols": [str(item).strip().upper().replace("/", "") for item in raw.get("allowed_symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]) if str(item or "").strip()] if isinstance(raw.get("allowed_symbols", []), list) else ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
        "idempotency_prefix": "mrx_",
        "source_idempotency_prefix": "mrp_",
        "exchange": "binance",
        "order_side": str(raw.get("order_side") or "BUY").upper(),
        "order_type": str(raw.get("order_type") or "MARKET").upper(),
        "read_only": True,
        "auto_apply": False,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
    }


def _approval(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_approval_gate") if isinstance(data.get("autonomous_micro_real_approval_gate"), dict) else None
    if raw and raw.get("revision") == 87 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_approval_gate(data, settings, auth_store, username)


def _api_connection(auth_store: dict | None, username: str) -> dict:
    users = (auth_store or {}).get("users") if isinstance((auth_store or {}).get("users"), dict) else {}
    record = users.get(username) if isinstance(users, dict) else {}
    return public_api_connection(record if isinstance(record, dict) else {})


def _sandbox_id(username: str, approval_id: str, source_key: str, symbol: str, notional: float) -> str:
    seed = f"rev88:{username}:{approval_id}:{source_key}:{symbol}:{round(notional, 4)}"
    return "mrx_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


def _normalize_exchange_payload(symbol: str, side: str, order_type: str, notional: float, sandbox_key: str) -> dict:
    return {
        "exchange": "binance",
        "endpoint": "/api/v3/order",
        "method": "POST",
        "symbol": symbol,
        "side": side if side in {"BUY", "SELL"} else "BUY",
        "type": order_type if order_type in {"MARKET", "LIMIT"} else "MARKET",
        "quoteOrderQty": round(max(0.0, notional), 4),
        "newClientOrderId": sandbox_key,
        "timeInForce": None,
        "normalized": True,
        "contains_secret": False,
    }


def _sandbox_state(blockers: list[str], warnings: list[str], api_ready: bool, dry_run: bool, live_ready_preview: bool) -> str:
    if blockers:
        return "MICRO_REAL_EXECUTION_BLOCKED"
    if dry_run:
        return "MICRO_REAL_EXECUTION_DRY_RUN_READY"
    if api_ready and live_ready_preview:
        return "MICRO_REAL_EXECUTION_LIVE_READY_PREVIEW"
    if warnings:
        return "MICRO_REAL_EXECUTION_REVIEW"
    return "MICRO_REAL_EXECUTION_READY"


def _next_action(state: str) -> str:
    if state == "MICRO_REAL_EXECUTION_LIVE_READY_PREVIEW":
        return "PREPARE_REV89_EXCHANGE_ADAPTER_HARDENING"
    if state == "MICRO_REAL_EXECUTION_DRY_RUN_READY":
        return "KEEP_MICRO_REAL_SANDBOX_DRY_RUN_AND_VALIDATE_ADAPTER_INPUTS"
    if state == "MICRO_REAL_EXECUTION_REVIEW":
        return "REVIEW_MICRO_REAL_SANDBOX_WARNINGS"
    if state == "MICRO_REAL_EXECUTION_READY":
        return "HOLD_UNTIL_EXCHANGE_ADAPTER_HARDENING"
    return "KEEP_MICRO_REAL_EXECUTION_BLOCKED"


def build_autonomous_micro_real_execution_sandbox(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev88 dry-run execution sandbox for a micro-real approval ticket.

    This is the final bridge before hardening the exchange adapter. It accepts
    only a Rev87 approved micro-real gate, normalizes the future Binance order
    payload, enforces idempotency/notional/loss/API/safety guards and returns a
    dry-run/live-ready preview. It never places orders, never sends exchange
    requests and never writes runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    approval = _approval(data, settings, auth_store, username)
    command = approval.get("command_preview") if isinstance(approval.get("command_preview"), dict) else {}
    api = _api_connection(auth_store, username)

    blockers: list[str] = []
    warnings: list[str] = []

    approval_state = str(approval.get("approval_state") or "UNKNOWN")
    approval_status = str(approval.get("status") or "review")
    symbol = _clean_symbol(approval.get("symbol") or command.get("symbol"))
    notional = _safe_float(approval.get("approved_notional_usdt"), _safe_float(command.get("notional_usdt"), 0.0))
    max_loss = _safe_float(approval.get("approved_max_loss_usdt"), _safe_float(command.get("max_loss_usdt"), 0.0))
    source_key = str(approval.get("source_idempotency_key") or command.get("source_idempotency_key") or "")
    approval_id = str(approval.get("approval_id") or "")
    api_ready = bool(api.get("configured") and api.get("trade_enabled") and "trade" in (api.get("permissions") or []))

    if not policy["enabled"]:
        blockers.append("micro_real_execution_sandbox_disabled")
    if approval.get("revision") != 87:
        blockers.append("micro_real_approval_gate_revision_mismatch")
    if approval_status != "ok":
        blockers.append("micro_real_approval_gate_not_ok")
    if approval_state != policy["require_approval_state"]:
        blockers.append("micro_real_approval_state_not_ready")
    if approval.get("requires_owner_confirmation") is not True or command.get("requires_owner_confirmation") is not True:
        blockers.append("owner_confirmation_not_required_by_source")
    if not approval_id.startswith("mra_"):
        blockers.append("missing_or_invalid_approval_id")
    if not source_key.startswith(policy["source_idempotency_prefix"]):
        blockers.append("missing_or_invalid_source_idempotency_key")
    if command.get("approved_for_later_execution_bridge") is not True:
        blockers.append("approval_not_marked_for_later_execution_bridge")
    if approval.get("target_lane") != policy["require_target_lane"]:
        blockers.append("approval_target_lane_not_micro_real_preview")
    if command.get("places_order") is not False or command.get("sends_exchange_request") is not False or command.get("writes_runtime_state") is not False:
        blockers.append("source_command_not_safely_read_only")
    if notional <= 0 or notional > policy["max_sandbox_notional_usdt"]:
        blockers.append("sandbox_notional_outside_bounds")
    if max_loss <= 0 or max_loss > policy["max_sandbox_loss_usdt"]:
        blockers.append("sandbox_loss_outside_bounds")
    if symbol == "UNKNOWN":
        blockers.append("missing_symbol")
    if symbol not in policy["allowed_symbols"]:
        blockers.append("symbol_not_allowed_for_micro_real_sandbox")

    if not api.get("configured"):
        blockers.append("api_credentials_missing")
    elif not api_ready:
        blockers.append("api_trade_permission_not_ready")
    if api.get("exchange") != policy["exchange"]:
        blockers.append("unsupported_exchange_for_micro_real_sandbox")

    safety = data.get("autonomous_safety_supervisor") if isinstance(data.get("autonomous_safety_supervisor"), dict) else {}
    if safety.get("kill_switch_active") or safety.get("safe_mode_required") or safety.get("safety_state") in {"KILL_SWITCH", "SAFE_MODE", "BLOCKED"}:
        blockers.append("safety_supervisor_blocks_micro_real_execution")

    if policy["dry_run"]:
        warnings.append("dry_run_active_no_exchange_request_will_be_sent")
    if policy["live_ready_preview"] and api_ready and not blockers:
        warnings.append("live_ready_preview_only_submitter_still_disabled")

    sandbox_key = _sandbox_id(username, approval_id, source_key, symbol, notional)
    exchange_payload = _normalize_exchange_payload(symbol, policy["order_side"], policy["order_type"], notional, sandbox_key)
    state = _sandbox_state(blockers, warnings, api_ready, policy["dry_run"], policy["live_ready_preview"])
    status = "blocked" if blockers else ("ok" if state in {"MICRO_REAL_EXECUTION_DRY_RUN_READY", "MICRO_REAL_EXECUTION_LIVE_READY_PREVIEW", "MICRO_REAL_EXECUTION_READY"} else "review")
    score = _clamp(_safe_float(approval.get("approval_score"), 0.0) - min(70.0, len(set(blockers)) * 15.0) - min(10.0, len(set(warnings)) * 1.0))

    return {
        "status": status,
        "revision": 88,
        "engine": "autonomous_micro_real_execution_sandbox",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "dry_run": policy["dry_run"],
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "sandbox_state": state,
        "sandbox_score": round(score, 2),
        "next_action": _next_action(state),
        "source_revision": approval.get("revision"),
        "source_approval_state": approval_state,
        "source_approval_score": approval.get("approval_score"),
        "source_approval_id": approval_id,
        "source_idempotency_key": source_key,
        "sandbox_idempotency_key": sandbox_key,
        "duplicate_guard_key": sha256(f"{username}:{source_key}:{approval_id}".encode("utf-8")).hexdigest()[:32],
        "symbol": symbol,
        "target_lane": "MICRO_REAL_EXECUTION_SANDBOX" if status != "blocked" else "MICRO_REAL_BLOCKED",
        "notional_usdt": round(min(notional, policy["max_sandbox_notional_usdt"]), 4),
        "max_loss_usdt": round(min(max_loss, policy["max_sandbox_loss_usdt"]), 4),
        "owner_confirmation_required": True,
        "api_permission_ready": api_ready,
        "api_connection": {
            "configured": api.get("configured"),
            "exchange": api.get("exchange"),
            "environment": api.get("environment"),
            "trade_enabled": api.get("trade_enabled"),
            "permissions": api.get("permissions") or [],
            "fingerprint": api.get("fingerprint"),
            "secret_returned": False,
        },
        "exchange_payload_preview": exchange_payload,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy": policy,
        "inputs": {
            "micro_real_approval_gate_revision": approval.get("revision"),
            "approval_state": approval_state,
            "approval_status": approval_status,
            "approval_id": approval_id,
            "source_idempotency_key": source_key,
            "api_readiness": api.get("readiness"),
            "kill_switch_active": bool(safety.get("kill_switch_active")),
            "safe_mode_required": bool(safety.get("safe_mode_required")),
        },
        "command_preview": {
            "type": "micro_real_execution_sandbox_preview",
            "read_only": True,
            "auto_apply": False,
            "dry_run": policy["dry_run"],
            "live_ready_preview": bool(policy["live_ready_preview"] and api_ready and not blockers),
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "source_revision": 88,
            "sandbox_state": state,
            "next_action": _next_action(state),
            "symbol": symbol,
            "lane": "MICRO_REAL_EXECUTION_SANDBOX" if status != "blocked" else "MICRO_REAL_BLOCKED",
            "notional_usdt": round(min(notional, policy["max_sandbox_notional_usdt"]), 4),
            "max_loss_usdt": round(min(max_loss, policy["max_sandbox_loss_usdt"]), 4),
            "source_approval_id": approval_id,
            "source_idempotency_key": source_key,
            "sandbox_idempotency_key": sandbox_key,
            "exchange_payload_preview": exchange_payload,
            "requires_owner_confirmation": True,
            "approved_for_exchange_adapter_hardening": status != "blocked",
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 88,
        "engine": "autonomous_micro_real_execution_sandbox_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "dry_run": payload.get("dry_run"),
        "sandbox_state": payload.get("sandbox_state"),
        "sandbox_score": payload.get("sandbox_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "target_lane": payload.get("target_lane"),
        "notional_usdt": payload.get("notional_usdt"),
        "max_loss_usdt": payload.get("max_loss_usdt"),
        "api_permission_ready": payload.get("api_permission_ready"),
        "owner_confirmation_required": payload.get("owner_confirmation_required"),
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
    }


def build_summary_autonomous_micro_real_execution_sandbox(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_execution_sandbox(data, settings, auth_store, username))


def build_autonomous_micro_real_execution_sandbox_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_execution_sandbox(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    exchange_payload = payload.get("exchange_payload_preview") if isinstance(payload.get("exchange_payload_preview"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_88": payload.get("revision") == 88,
        "micro_real_approval_chain_present": payload.get("source_revision") == 87,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": payload.get("places_order") is False and command.get("places_order") is False,
        "no_exchange_request": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False,
        "no_runtime_write": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "dry_run_or_blocked": payload.get("dry_run") is True or payload.get("status") == "blocked",
        "idempotency_guard_present": str(payload.get("sandbox_idempotency_key") or "").startswith("mrx_") and bool(payload.get("duplicate_guard_key")),
        "bounded_notional": _safe_float(payload.get("notional_usdt"), 0.0) <= _safe_float((payload.get("policy") or {}).get("max_sandbox_notional_usdt"), 0.0),
        "bounded_loss": _safe_float(payload.get("max_loss_usdt"), 0.0) <= _safe_float((payload.get("policy") or {}).get("max_sandbox_loss_usdt"), 0.0),
        "exchange_payload_normalized": exchange_payload.get("normalized") is True and exchange_payload.get("contains_secret") is False,
        "owner_confirmation_required": payload.get("owner_confirmation_required") is True and command.get("requires_owner_confirmation") is True,
        "summary_revision_is_88": summary.get("revision") == 88,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 88,
        "engine": "autonomous_micro_real_execution_sandbox_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_EXECUTION_SANDBOX_OK" if passed else "MICRO_REAL_EXECUTION_SANDBOX_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("sandbox_state"),
        "sample_action": payload.get("next_action"),
    }
