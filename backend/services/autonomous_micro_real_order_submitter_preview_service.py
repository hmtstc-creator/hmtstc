from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_exchange_adapter_hardening_service import build_autonomous_micro_real_exchange_adapter_hardening


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
    raw = settings.get("autonomous_micro_real_order_submitter_preview") if isinstance(settings.get("autonomous_micro_real_order_submitter_preview"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "direct_submit_enabled": _safe_bool(raw.get("direct_submit_enabled"), False),
        "manual_enable_flag": str(raw.get("manual_enable_flag") or "").strip(),
        "required_manual_enable_flag": "ENABLE_MICRO_REAL_SUBMITTER_REV91_ONLY",
        "require_source_revision": 89,
        "require_adapter_state": "BINANCE_ADAPTER_DRY_RUN_READY",
        "require_target_lane": "MICRO_REAL_EXCHANGE_ADAPTER_DRY_RUN",
        "max_order_notional_usdt": max(5.0, _safe_float(raw.get("max_order_notional_usdt"), 25.0)),
        "max_order_loss_usdt": max(0.25, _safe_float(raw.get("max_order_loss_usdt"), 1.0)),
        "daily_micro_order_cap": max(1, _safe_int(raw.get("daily_micro_order_cap"), 1)),
        "one_shot_micro_order_limit": 1,
        "allowed_symbols": [
            _clean_symbol(item) for item in raw.get("allowed_symbols", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
            if str(item or "").strip()
        ] if isinstance(raw.get("allowed_symbols", []), list) else ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"],
        "require_owner_confirmation_token": True,
        "owner_confirmation_token_prefix": "mro_own_",
        "idempotency_prefix": "mros_",
        "source_idempotency_prefix": "mrx_",
        "exchange": "binance",
        "network_calls_allowed": False,
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_exchange_adapter_hardening") if isinstance(data.get("autonomous_micro_real_exchange_adapter_hardening"), dict) else None
    if raw and raw.get("revision") == 89 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_exchange_adapter_hardening(data, settings, auth_store, username)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _submitter_id(username: str, adapter_id: str, source_key: str, symbol: str, notional: float) -> str:
    seed = f"rev90:{username}:{adapter_id}:{source_key}:{symbol}:{round(notional, 8)}"
    return "mros_" + sha256(seed.encode("utf-8")).hexdigest()[:24]


def _owner_token(submitter_id: str, username: str) -> str:
    # Preview-only deterministic token reference. It is not an authorization secret.
    seed = f"owner-confirm:{username}:{submitter_id}"
    return "mro_own_" + sha256(seed.encode("utf-8")).hexdigest()[:16]


def _historical_micro_counts(data: dict, symbol: str) -> dict:
    today = _today_key()
    items: list[dict] = []
    for key in ("micro_real_order_history", "order_submitter_history", "exchange_order_audit"):
        raw = data.get(key)
        if isinstance(raw, list):
            items.extend(item for item in raw if isinstance(item, dict))
    same_day = [item for item in items if str(item.get("created_at") or item.get("submitted_at") or item.get("date") or "").startswith(today)]
    same_symbol_day = [item for item in same_day if _clean_symbol(item.get("symbol")) == symbol]
    return {
        "today_key": today,
        "today_total": len(same_day),
        "today_symbol_total": len(same_symbol_day),
    }


def build_autonomous_micro_real_order_submitter_preview(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev90 final submitter preview and safety contract.

    This service converts the Rev89 dry-run adapter contract into the final
    micro-real submitter preview. It enforces idempotency, owner confirmation
    token requirements, one-shot/daily caps and the final preflight contract.
    It never sends exchange requests and never places orders in Rev90.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    request = source.get("adapter_request_preview") if isinstance(source.get("adapter_request_preview"), dict) else {}
    response = source.get("adapter_response_preview") if isinstance(source.get("adapter_response_preview"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []

    symbol = _clean_symbol(request.get("symbol") or source.get("symbol") or command.get("symbol"))
    notional = _safe_float(request.get("quoteOrderQty"), 0.0)
    source_key = str(request.get("newClientOrderId") or source.get("source_sandbox_idempotency_key") or "")
    adapter_id = str(source.get("adapter_id") or command.get("adapter_id") or "")
    submitter_id = _submitter_id(username, adapter_id, source_key, symbol, notional)
    owner_token = _owner_token(submitter_id, username)
    counts = _historical_micro_counts(data, symbol)

    if not policy["enabled"]:
        blockers.append("micro_real_order_submitter_preview_disabled")
    if source.get("revision") != policy["require_source_revision"]:
        blockers.append("exchange_adapter_revision_mismatch")
    if source.get("status") != "ok":
        blockers.append("exchange_adapter_not_ok")
    if source.get("adapter_state") != policy["require_adapter_state"]:
        blockers.append("exchange_adapter_state_not_dry_run_ready")
    if source.get("target_lane") != policy["require_target_lane"]:
        blockers.append("exchange_adapter_lane_mismatch")
    if command.get("approved_for_order_submitter_preview") is not True:
        blockers.append("source_not_approved_for_order_submitter_preview")
    if source.get("places_order") is not False or source.get("sends_exchange_request") is not False or source.get("writes_runtime_state") is not False:
        blockers.append("source_adapter_not_safely_read_only")
    if request.get("endpoint") != "/api/v3/order/test":
        blockers.append("adapter_request_not_test_order_endpoint")
    if request.get("dry_run") is not True:
        blockers.append("adapter_request_not_dry_run")
    if request.get("contains_secret") is not False or response.get("contains_secret") is not False:
        blockers.append("secret_guard_failed")
    if not source_key.startswith(policy["source_idempotency_prefix"]):
        blockers.append("source_idempotency_key_not_sandbox_scoped")
    if not adapter_id.startswith("mra89_"):
        blockers.append("adapter_id_invalid")
    if symbol not in policy["allowed_symbols"]:
        blockers.append("symbol_not_allowed_for_order_submitter_preview")
    if notional <= 0 or notional > policy["max_order_notional_usdt"]:
        blockers.append("order_notional_outside_final_contract")

    max_loss = _safe_float(source.get("approved_max_loss_usdt") or source.get("max_loss_usdt") or command.get("max_loss_usdt"), 0.0)
    if max_loss > policy["max_order_loss_usdt"]:
        blockers.append("order_loss_outside_final_contract")

    if counts["today_total"] >= policy["daily_micro_order_cap"]:
        blockers.append("daily_micro_order_cap_reached")
    if counts["today_symbol_total"] >= policy["one_shot_micro_order_limit"]:
        blockers.append("one_shot_micro_order_limit_reached_for_symbol")

    # Rev90 deliberately refuses actual submit even when the user attempts to set a manual flag.
    if policy["direct_submit_enabled"]:
        warnings.append("direct_submit_flag_detected_but_rev90_still_preview_only")
    if policy["manual_enable_flag"] == policy["required_manual_enable_flag"]:
        warnings.append("manual_enable_flag_present_but_reserved_for_rev91")
    else:
        warnings.append("manual_enable_flag_absent_direct_submit_locked")

    if not policy["network_calls_allowed"]:
        warnings.append("network_calls_disabled_no_exchange_request_will_be_sent")

    state = "MICRO_REAL_ORDER_SUBMITTER_BLOCKED" if blockers else "MICRO_REAL_ORDER_SUBMITTER_PREVIEW_READY"
    status = "blocked" if blockers else "ok"
    final_preflight = {
        "source_chain_ok": not any(item in blockers for item in [
            "exchange_adapter_revision_mismatch",
            "exchange_adapter_not_ok",
            "exchange_adapter_state_not_dry_run_ready",
            "exchange_adapter_lane_mismatch",
            "source_not_approved_for_order_submitter_preview",
        ]),
        "idempotency_ok": source_key.startswith(policy["source_idempotency_prefix"]) and submitter_id.startswith(policy["idempotency_prefix"]),
        "owner_confirmation_required": True,
        "owner_confirmation_token_preview": owner_token,
        "owner_confirmation_token_prefix_ok": owner_token.startswith(policy["owner_confirmation_token_prefix"]),
        "limits_ok": not any(item in blockers for item in [
            "order_notional_outside_final_contract",
            "order_loss_outside_final_contract",
            "daily_micro_order_cap_reached",
            "one_shot_micro_order_limit_reached_for_symbol",
        ]),
        "secret_guard_ok": "secret_guard_failed" not in blockers,
        "network_call_planned": False,
        "direct_submit_enabled": False,
        "submit_allowed_in_rev90": False,
    }
    score = max(0.0, min(100.0, _safe_float(source.get("adapter_score"), 0.0) - len(set(blockers)) * 15.0 - len(set(warnings)) * 1.0))

    return {
        "status": status,
        "revision": 90,
        "engine": "autonomous_micro_real_order_submitter_preview",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "submitter_state": state,
        "submitter_score": round(score, 2),
        "submitter_id": submitter_id,
        "owner_confirmation_token_preview": owner_token,
        "next_action": "PREPARE_REV91_FIRST_MICRO_REAL_CONTROLLED_EXECUTION" if status == "ok" else "KEEP_MICRO_REAL_ORDER_SUBMITTER_BLOCKED",
        "source_revision": source.get("revision"),
        "source_adapter_state": source.get("adapter_state"),
        "source_adapter_id": adapter_id,
        "source_sandbox_idempotency_key": source_key,
        "exchange": "binance",
        "symbol": symbol,
        "target_lane": "MICRO_REAL_ORDER_SUBMITTER_PREVIEW" if status == "ok" else "MICRO_REAL_BLOCKED",
        "final_safety_contract": {
            "max_order_notional_usdt": policy["max_order_notional_usdt"],
            "max_order_loss_usdt": policy["max_order_loss_usdt"],
            "daily_micro_order_cap": policy["daily_micro_order_cap"],
            "one_shot_micro_order_limit": policy["one_shot_micro_order_limit"],
            "allowed_symbols": policy["allowed_symbols"],
            "owner_confirmation_required": True,
            "manual_enable_flag_required_for_future_submit": policy["required_manual_enable_flag"],
            "direct_submit_default_off": True,
            "rev90_submit_disabled": True,
        },
        "final_preflight": final_preflight,
        "idempotency_guard": {
            "source_key": source_key,
            "submitter_key": submitter_id,
            "source_key_ok": source_key.startswith(policy["source_idempotency_prefix"]),
            "submitter_key_ok": submitter_id.startswith(policy["idempotency_prefix"]),
            "duplicate_guard_scope": f"{_today_key()}:{symbol}:{source_key}",
            "ok": source_key.startswith(policy["source_idempotency_prefix"]) and submitter_id.startswith(policy["idempotency_prefix"]),
        },
        "order_cap_guard": {
            **counts,
            "daily_micro_order_cap": policy["daily_micro_order_cap"],
            "one_shot_micro_order_limit": policy["one_shot_micro_order_limit"],
            "ok": counts["today_total"] < policy["daily_micro_order_cap"] and counts["today_symbol_total"] < policy["one_shot_micro_order_limit"],
        },
        "submit_request_preview": {
            "exchange": "binance",
            "endpoint": "/api/v3/order/test",
            "method": "POST",
            "symbol": symbol,
            "side": request.get("side"),
            "type": request.get("type"),
            "quoteOrderQty": notional,
            "newClientOrderId": submitter_id,
            "sourceClientOrderId": source_key,
            "recvWindow": request.get("recvWindow"),
            "dry_run": True,
            "network_call_planned": False,
            "contains_secret": False,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy": policy,
        "command_preview": {
            "type": "micro_real_order_submitter_preview_contract",
            "read_only": True,
            "auto_apply": False,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "source_revision": 90,
            "submitter_state": state,
            "next_action": "PREPARE_REV91_FIRST_MICRO_REAL_CONTROLLED_EXECUTION" if status == "ok" else "KEEP_MICRO_REAL_ORDER_SUBMITTER_BLOCKED",
            "symbol": symbol,
            "lane": "MICRO_REAL_ORDER_SUBMITTER_PREVIEW" if status == "ok" else "MICRO_REAL_BLOCKED",
            "submitter_id": submitter_id,
            "owner_confirmation_token_preview": owner_token,
            "requires_owner_confirmation": True,
            "direct_submit_enabled": False,
            "approved_for_first_micro_real_controlled_execution": status == "ok",
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    preflight = payload.get("final_preflight") if isinstance(payload.get("final_preflight"), dict) else {}
    cap = payload.get("order_cap_guard") if isinstance(payload.get("order_cap_guard"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 90,
        "engine": "autonomous_micro_real_order_submitter_preview_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "dry_run": True,
        "submitter_state": payload.get("submitter_state"),
        "submitter_score": payload.get("submitter_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "target_lane": payload.get("target_lane"),
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "owner_confirmation_required": preflight.get("owner_confirmation_required") is True,
        "direct_submit_enabled": False,
        "network_call_planned": False,
        "idempotency_ok": preflight.get("idempotency_ok") is True,
        "order_cap_ok": cap.get("ok") is True,
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
    }


def build_summary_autonomous_micro_real_order_submitter_preview(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_order_submitter_preview(data, settings, auth_store, username))


def build_autonomous_micro_real_order_submitter_preview_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_order_submitter_preview(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    request = payload.get("submit_request_preview") if isinstance(payload.get("submit_request_preview"), dict) else {}
    preflight = payload.get("final_preflight") if isinstance(payload.get("final_preflight"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_90": payload.get("revision") == 90,
        "exchange_adapter_chain_present": payload.get("source_revision") == 89,
        "final_safety_contract_present": isinstance(payload.get("final_safety_contract"), dict) and payload.get("final_safety_contract", {}).get("rev90_submit_disabled") is True,
        "owner_confirmation_token_present": str(payload.get("owner_confirmation_token_preview") or "").startswith("mro_own_"),
        "idempotency_enforced": payload.get("idempotency_guard", {}).get("ok") is True,
        "daily_order_cap_present": isinstance(payload.get("order_cap_guard"), dict) and "daily_micro_order_cap" in payload.get("order_cap_guard", {}),
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "direct_submit_disabled": preflight.get("direct_submit_enabled") is False and command.get("direct_submit_enabled") is False,
        "no_direct_order_placement": payload.get("places_order") is False and command.get("places_order") is False,
        "no_exchange_request": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False and request.get("network_call_planned") is False,
        "no_runtime_write": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "submit_request_is_test_endpoint": request.get("endpoint") == "/api/v3/order/test" and request.get("contains_secret") is False,
        "summary_revision_is_90": summary.get("revision") == 90,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 90,
        "engine": "autonomous_micro_real_order_submitter_preview_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_ORDER_SUBMITTER_PREVIEW_OK" if passed else "MICRO_REAL_ORDER_SUBMITTER_PREVIEW_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("submitter_state"),
        "sample_action": payload.get("next_action"),
    }
