from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_execution_sandbox_service import build_autonomous_micro_real_execution_sandbox
from services.binance_service import map_binance_error


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


def _decimal(value: Any, fallback: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(fallback))


def _decimal_places(step: Decimal) -> int:
    if step <= 0:
        return 8
    exponent = step.normalize().as_tuple().exponent
    return abs(exponent) if exponent < 0 else 0


def _floor_to_step(value: Any, step: Any) -> Decimal:
    v = _decimal(value)
    s = _decimal(step)
    if s <= 0:
        return v
    return (v / s).to_integral_value(rounding=ROUND_DOWN) * s


def _as_number(value: Decimal) -> float:
    return float(value.normalize()) if value == value.to_integral() else float(value)


def _clean_symbol(value: Any) -> str:
    symbol = str(value or "UNKNOWN").strip().upper().replace("/", "")
    return "".join(ch for ch in symbol if ch.isalnum()) or "UNKNOWN"


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_exchange_adapter_hardening") if isinstance(settings.get("autonomous_micro_real_exchange_adapter_hardening"), dict) else {}
    symbol_rules = raw.get("symbol_rules") if isinstance(raw.get("symbol_rules"), dict) else {}
    default_rules = {
        "BTCUSDT": {"min_notional": 5.0, "step_size": "0.000001", "tick_size": "0.01", "quantity_precision": 6, "price_precision": 2},
        "ETHUSDT": {"min_notional": 5.0, "step_size": "0.0001", "tick_size": "0.01", "quantity_precision": 4, "price_precision": 2},
        "BNBUSDT": {"min_notional": 5.0, "step_size": "0.001", "tick_size": "0.01", "quantity_precision": 3, "price_precision": 2},
        "SOLUSDT": {"min_notional": 5.0, "step_size": "0.01", "tick_size": "0.01", "quantity_precision": 2, "price_precision": 2},
    }
    merged_rules = deepcopy(default_rules)
    for key, value in symbol_rules.items():
        if isinstance(value, dict):
            merged_rules[_clean_symbol(key)] = {**merged_rules.get(_clean_symbol(key), {}), **value}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "exchange": "binance",
        "adapter_version": "rev89_binance_spot_adapter_v1",
        "require_source_revision": 88,
        "require_sandbox_states": ["MICRO_REAL_EXECUTION_DRY_RUN_READY", "MICRO_REAL_EXECUTION_LIVE_READY_PREVIEW", "MICRO_REAL_EXECUTION_READY"],
        "require_target_lane": "MICRO_REAL_EXECUTION_SANDBOX",
        "allowed_order_types": ["MARKET", "LIMIT"],
        "allowed_sides": ["BUY", "SELL"],
        "default_order_type": "MARKET",
        "max_timestamp_drift_ms": int(_safe_float(raw.get("max_timestamp_drift_ms"), 1000)),
        "recv_window_ms": int(_safe_float(raw.get("recv_window_ms"), 5000)),
        "rate_limit_weight_budget": int(_safe_float(raw.get("rate_limit_weight_budget"), 1)),
        "max_retry_attempts": int(_safe_float(raw.get("max_retry_attempts"), 0)),
        "symbol_rules": merged_rules,
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
    }


@dataclass(frozen=True)
class ExchangeAdapterRequest:
    exchange: str
    endpoint: str
    method: str
    symbol: str
    side: str
    order_type: str
    quote_order_qty: float
    new_client_order_id: str
    recv_window: int
    dry_run: bool = True

    def public(self) -> dict:
        return {
            "exchange": self.exchange,
            "endpoint": self.endpoint,
            "method": self.method,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "quoteOrderQty": self.quote_order_qty,
            "newClientOrderId": self.new_client_order_id,
            "recvWindow": self.recv_window,
            "dry_run": self.dry_run,
            "contains_secret": False,
        }


@dataclass(frozen=True)
class ExchangeAdapterResponse:
    ok: bool
    status_code: int | None
    adapter_state: str
    mapped_error: dict | None = None
    latency_ms: float | None = None

    def public(self) -> dict:
        return {
            "ok": self.ok,
            "status_code": self.status_code,
            "adapter_state": self.adapter_state,
            "mapped_error": self.mapped_error,
            "latency_ms": self.latency_ms,
            "contains_secret": False,
        }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_execution_sandbox") if isinstance(data.get("autonomous_micro_real_execution_sandbox"), dict) else None
    if raw and raw.get("revision") == 88 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_execution_sandbox(data, settings, auth_store, username)


def _normalize_payload(source_payload: dict, policy: dict) -> tuple[dict, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    preview = source_payload.get("exchange_payload_preview") if isinstance(source_payload.get("exchange_payload_preview"), dict) else {}
    command = source_payload.get("command_preview") if isinstance(source_payload.get("command_preview"), dict) else {}
    symbol = _clean_symbol(preview.get("symbol") or source_payload.get("symbol") or command.get("symbol"))
    side = str(preview.get("side") or "BUY").upper().strip()
    order_type = str(preview.get("type") or policy["default_order_type"]).upper().strip()
    notional = _decimal(preview.get("quoteOrderQty"), str(source_payload.get("notional_usdt") or command.get("notional_usdt") or 0))
    client_order_id = str(preview.get("newClientOrderId") or source_payload.get("sandbox_idempotency_key") or "")
    rules = policy["symbol_rules"].get(symbol) if isinstance(policy["symbol_rules"].get(symbol), dict) else {}
    min_notional = _decimal(rules.get("min_notional"), "5")
    step_size = _decimal(rules.get("step_size"), "0.000001")
    tick_size = _decimal(rules.get("tick_size"), "0.01")

    if symbol == "UNKNOWN" or not symbol.endswith("USDT"):
        blockers.append("binance_symbol_invalid_or_not_usdt_spot")
    if side not in policy["allowed_sides"]:
        blockers.append("binance_order_side_invalid")
    if order_type not in policy["allowed_order_types"]:
        blockers.append("binance_order_type_invalid")
    if notional <= 0:
        blockers.append("binance_quote_order_qty_invalid")
    if min_notional and notional < min_notional:
        blockers.append("binance_min_notional_not_met")
    if not client_order_id.startswith("mrx_"):
        blockers.append("binance_client_order_id_not_sandbox_scoped")
    if str(preview.get("endpoint") or "") != "/api/v3/order":
        blockers.append("binance_endpoint_not_order_endpoint")
    if str(preview.get("method") or "").upper() != "POST":
        blockers.append("binance_method_not_post")

    estimated_price = _decimal(rules.get("reference_price"), "0")
    normalized_qty = None
    normalized_price = None
    if estimated_price > 0 and notional > 0:
        normalized_qty = _floor_to_step(notional / estimated_price, step_size)
        if normalized_qty <= 0:
            blockers.append("binance_step_size_normalized_quantity_zero")
    else:
        warnings.append("reference_price_not_available_quantity_preview_skipped")
    if order_type == "LIMIT":
        requested_price = _decimal(preview.get("price") or rules.get("reference_price"), "0")
        normalized_price = _floor_to_step(requested_price, tick_size)
        if normalized_price <= 0:
            blockers.append("binance_limit_price_invalid")

    normalized = ExchangeAdapterRequest(
        exchange="binance",
        endpoint="/api/v3/order/test",
        method="POST",
        symbol=symbol,
        side=side if side in policy["allowed_sides"] else "BUY",
        order_type=order_type if order_type in policy["allowed_order_types"] else policy["default_order_type"],
        quote_order_qty=round(float(notional), 8),
        new_client_order_id=client_order_id,
        recv_window=policy["recv_window_ms"],
        dry_run=True,
    ).public()
    normalized.update({
        "source_endpoint": preview.get("endpoint"),
        "normalized_for_test_order_endpoint": True,
        "quantity_preview": _as_number(normalized_qty) if normalized_qty is not None else None,
        "price_preview": _as_number(normalized_price) if normalized_price is not None else None,
        "precision": {
            "step_size": str(step_size),
            "tick_size": str(tick_size),
            "quantity_precision": int(rules.get("quantity_precision") or _decimal_places(step_size)),
            "price_precision": int(rules.get("price_precision") or _decimal_places(tick_size)),
        },
        "filter_checks": {
            "MIN_NOTIONAL": {"required": float(min_notional), "actual": float(notional), "ok": not bool(min_notional and notional < min_notional)},
            "LOT_SIZE": {"step_size": str(step_size), "quantity_preview": _as_number(normalized_qty) if normalized_qty is not None else None, "ok": normalized_qty is None or normalized_qty > 0},
            "PRICE_FILTER": {"tick_size": str(tick_size), "price_preview": _as_number(normalized_price) if normalized_price is not None else None, "ok": order_type != "LIMIT" or (normalized_price is not None and normalized_price > 0)},
        },
    })
    return normalized, blockers, warnings


def build_autonomous_micro_real_exchange_adapter_hardening(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev89 Binance adapter hardening layer.

    It standardizes the exchange adapter contract after Rev88 sandbox, validates
    Binance request shape, symbol filters, precision, timestamp/rate-limit guard,
    response/error mapping and secret redaction. It is still dry-run only: no
    exchange request is sent and no runtime state is written.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("micro_real_exchange_adapter_hardening_disabled")
    if source.get("revision") != policy["require_source_revision"]:
        blockers.append("micro_real_execution_sandbox_revision_mismatch")
    if source.get("status") != "ok":
        blockers.append("micro_real_execution_sandbox_not_ok")
    if source.get("sandbox_state") not in policy["require_sandbox_states"]:
        blockers.append("micro_real_execution_sandbox_state_not_ready")
    if source.get("target_lane") != policy["require_target_lane"]:
        blockers.append("micro_real_execution_sandbox_lane_mismatch")
    if command.get("approved_for_exchange_adapter_hardening") is not True:
        blockers.append("source_not_approved_for_exchange_adapter_hardening")
    if source.get("places_order") is not False or source.get("sends_exchange_request") is not False or source.get("writes_runtime_state") is not False:
        blockers.append("source_command_not_safely_read_only")

    normalized_payload, payload_blockers, payload_warnings = _normalize_payload(source, policy)
    blockers.extend(payload_blockers)
    warnings.extend(payload_warnings)

    timestamp_drift_ms = int(_safe_float((settings.get("exchange_clock") or {}).get("timestamp_drift_ms") if isinstance(settings.get("exchange_clock"), dict) else 0, 0))
    if abs(timestamp_drift_ms) > policy["max_timestamp_drift_ms"]:
        blockers.append("binance_timestamp_drift_exceeds_guard")

    if policy["rate_limit_weight_budget"] < 1:
        blockers.append("binance_rate_limit_budget_exhausted")
    if policy["max_retry_attempts"] > 0:
        warnings.append("retry_policy_preview_only_no_network_call")

    simulated_response = ExchangeAdapterResponse(
        ok=not blockers,
        status_code=None,
        adapter_state="BINANCE_ADAPTER_DRY_RUN_READY" if not blockers else "BINANCE_ADAPTER_BLOCKED",
        mapped_error=None if not blockers else map_binance_error({"code": "LOCAL_GUARD", "msg": ",".join(sorted(set(blockers)))[:180]}),
        latency_ms=0.0,
    ).public()

    adapter_state = "BINANCE_ADAPTER_BLOCKED" if blockers else "BINANCE_ADAPTER_DRY_RUN_READY"
    status = "blocked" if blockers else "ok"
    score = max(0.0, min(100.0, _safe_float(source.get("sandbox_score"), 0.0) - len(set(blockers)) * 12.0 - len(set(warnings)) * 1.0))
    adapter_id = "mra89_" + sha256(f"rev89:{username}:{normalized_payload.get('newClientOrderId')}:{normalized_payload.get('symbol')}".encode("utf-8")).hexdigest()[:24]

    return {
        "status": status,
        "revision": 89,
        "engine": "autonomous_micro_real_exchange_adapter_hardening",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "adapter_state": adapter_state,
        "adapter_score": round(score, 2),
        "adapter_id": adapter_id,
        "next_action": "PREPARE_REV90_ORDER_SUBMITTER_PREVIEW_CONTRACT" if status == "ok" else "KEEP_MICRO_REAL_EXCHANGE_ADAPTER_BLOCKED",
        "source_revision": source.get("revision"),
        "source_sandbox_state": source.get("sandbox_state"),
        "source_sandbox_idempotency_key": source.get("sandbox_idempotency_key"),
        "exchange": "binance",
        "symbol": normalized_payload.get("symbol"),
        "target_lane": "MICRO_REAL_EXCHANGE_ADAPTER_DRY_RUN" if status == "ok" else "MICRO_REAL_BLOCKED",
        "adapter_request_preview": normalized_payload,
        "adapter_response_preview": simulated_response,
        "timestamp_guard": {
            "drift_ms": timestamp_drift_ms,
            "max_drift_ms": policy["max_timestamp_drift_ms"],
            "ok": abs(timestamp_drift_ms) <= policy["max_timestamp_drift_ms"],
        },
        "rate_limit_guard": {
            "weight_budget": policy["rate_limit_weight_budget"],
            "max_retry_attempts": policy["max_retry_attempts"],
            "ok": policy["rate_limit_weight_budget"] >= 1,
            "network_call_planned": False,
        },
        "secret_guard": {
            "request_contains_secret": False,
            "response_contains_secret": False,
            "api_key_returned": False,
            "api_secret_returned": False,
            "ok": True,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy": policy,
        "command_preview": {
            "type": "micro_real_exchange_adapter_hardening_preview",
            "read_only": True,
            "auto_apply": False,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "source_revision": 89,
            "adapter_state": adapter_state,
            "next_action": "PREPARE_REV90_ORDER_SUBMITTER_PREVIEW_CONTRACT" if status == "ok" else "KEEP_MICRO_REAL_EXCHANGE_ADAPTER_BLOCKED",
            "symbol": normalized_payload.get("symbol"),
            "lane": "MICRO_REAL_EXCHANGE_ADAPTER_DRY_RUN" if status == "ok" else "MICRO_REAL_BLOCKED",
            "adapter_id": adapter_id,
            "source_sandbox_idempotency_key": source.get("sandbox_idempotency_key"),
            "adapter_request_preview": normalized_payload,
            "approved_for_order_submitter_preview": status == "ok",
            "requires_owner_confirmation": True,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 89,
        "engine": "autonomous_micro_real_exchange_adapter_hardening_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "dry_run": True,
        "adapter_state": payload.get("adapter_state"),
        "adapter_score": payload.get("adapter_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "target_lane": payload.get("target_lane"),
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "timestamp_ok": ((payload.get("timestamp_guard") or {}).get("ok") is True),
        "rate_limit_ok": ((payload.get("rate_limit_guard") or {}).get("ok") is True),
        "secret_guard_ok": ((payload.get("secret_guard") or {}).get("ok") is True),
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
    }


def build_summary_autonomous_micro_real_exchange_adapter_hardening(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_exchange_adapter_hardening(data, settings, auth_store, username))


def build_autonomous_micro_real_exchange_adapter_hardening_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_exchange_adapter_hardening(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    request = payload.get("adapter_request_preview") if isinstance(payload.get("adapter_request_preview"), dict) else {}
    response = payload.get("adapter_response_preview") if isinstance(payload.get("adapter_response_preview"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_89": payload.get("revision") == 89,
        "micro_real_sandbox_chain_present": payload.get("source_revision") == 88,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": payload.get("places_order") is False and command.get("places_order") is False,
        "no_exchange_request": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False,
        "no_runtime_write": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "adapter_contract_present": request.get("exchange") == "binance" and request.get("endpoint") == "/api/v3/order/test",
        "binance_payload_normalized": request.get("normalized_for_test_order_endpoint") is True and request.get("contains_secret") is False,
        "response_mapping_present": response.get("contains_secret") is False and "adapter_state" in response,
        "timestamp_guard_present": isinstance(payload.get("timestamp_guard"), dict) and "max_drift_ms" in payload.get("timestamp_guard", {}),
        "rate_limit_guard_present": isinstance(payload.get("rate_limit_guard"), dict) and payload.get("rate_limit_guard", {}).get("network_call_planned") is False,
        "secret_guard_ok": payload.get("secret_guard", {}).get("ok") is True,
        "summary_revision_is_89": summary.get("revision") == 89,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 89,
        "engine": "autonomous_micro_real_exchange_adapter_hardening_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_EXCHANGE_ADAPTER_HARDENING_OK" if passed else "MICRO_REAL_EXCHANGE_ADAPTER_HARDENING_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("adapter_state"),
        "sample_action": payload.get("next_action"),
    }
