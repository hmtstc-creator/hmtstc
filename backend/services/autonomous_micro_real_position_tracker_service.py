from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_first_micro_real_controlled_execution_service import build_autonomous_first_micro_real_controlled_execution


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


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _age_minutes(value: Any) -> float | None:
    ts = _parse_ts(value)
    if not ts:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 60.0)


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_position_tracker") if isinstance(settings.get("autonomous_micro_real_position_tracker"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 91,
        "required_source_state": "FIRST_MICRO_REAL_LIVE_READY",
        "allowed_states": ["NEW", "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "REJECTED", "EXPIRED", "CANCELED"],
        "stale_open_order_minutes": max(1, _safe_int(raw.get("stale_open_order_minutes"), 15)),
        "stale_partial_fill_minutes": max(1, _safe_int(raw.get("stale_partial_fill_minutes"), 7)),
        "max_position_age_minutes": max(5, _safe_int(raw.get("max_position_age_minutes"), 240)),
        "max_unrealized_loss_usdt": max(0.05, _safe_float(raw.get("max_unrealized_loss_usdt"), 0.75)),
        "balance_reconciliation_required": _safe_bool(raw.get("balance_reconciliation_required"), True),
        "balance_reconciliation_ok": _safe_bool(raw.get("balance_reconciliation_ok"), False),
        "exchange_balance_snapshot_fresh": _safe_bool(raw.get("exchange_balance_snapshot_fresh"), False),
        "direct_close_enabled": _safe_bool(raw.get("direct_close_enabled"), False),
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "kill_switch_active": _safe_bool(raw.get("kill_switch_active"), False),
        "safe_mode_active": _safe_bool(raw.get("safe_mode_active"), False),
        "default_stop_loss_pct": max(0.05, _safe_float(raw.get("default_stop_loss_pct"), 0.75)),
        "default_take_profit_pct": max(0.05, _safe_float(raw.get("default_take_profit_pct"), 1.20)),
        "default_trailing_pct": max(0.05, _safe_float(raw.get("default_trailing_pct"), 0.45)),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_first_micro_real_controlled_execution") if isinstance(data.get("autonomous_first_micro_real_controlled_execution"), dict) else None
    if raw and raw.get("revision") == 91 and "command_preview" in raw:
        return raw
    return build_autonomous_first_micro_real_controlled_execution(data, settings, auth_store, username)


def _latest_order_status(data: dict, execution_id: str, symbol: str) -> dict:
    candidates: list[dict] = []
    for key in ("micro_real_order_status", "micro_real_exchange_responses", "micro_real_submit_history", "exchange_order_audit"):
        raw = data.get(key)
        if isinstance(raw, list):
            candidates.extend(item for item in raw if isinstance(item, dict))
        elif isinstance(raw, dict):
            candidates.append(raw)
    matched = []
    for item in candidates:
        ids = {str(item.get("execution_id") or ""), str(item.get("clientOrderId") or ""), str(item.get("newClientOrderId") or "")}
        item_symbol = _clean_symbol(item.get("symbol"))
        if execution_id in ids or (item_symbol == symbol and item.get("status")):
            matched.append(item)
    if not matched:
        return {}
    return sorted(matched, key=lambda item: str(item.get("updated_at") or item.get("transactTime") or item.get("created_at") or ""), reverse=True)[0]


def _normalize_status(raw: Any) -> str:
    status = str(raw or "PENDING_SUBMIT").strip().upper().replace(" ", "_")
    aliases = {
        "ACK": "ACKNOWLEDGED",
        "ACCEPTED": "ACKNOWLEDGED",
        "PARTIAL": "PARTIALLY_FILLED",
        "PARTIAL_FILL": "PARTIALLY_FILLED",
        "CANCELLED": "CANCELED",
    }
    return aliases.get(status, status or "PENDING_SUBMIT")


def _position_snapshot(data: dict, symbol: str, order: dict, source: dict) -> dict:
    positions = []
    for key in ("micro_real_positions", "real_positions", "open_real_positions"):
        raw = data.get(key)
        if isinstance(raw, list):
            positions.extend(item for item in raw if isinstance(item, dict))
    for item in positions:
        if _clean_symbol(item.get("symbol") or item.get("pair")) == symbol:
            return item
    request = source.get("submit_request_final_preview") if isinstance(source.get("submit_request_final_preview"), dict) else {}
    qty = _safe_float(order.get("executedQty") or order.get("quantity") or order.get("qty"), 0.0)
    notional = _safe_float(request.get("quoteOrderQty") or source.get("audit_evidence", {}).get("notional_usdt") if isinstance(source.get("audit_evidence"), dict) else 0.0, 0.0)
    entry_price = _safe_float(order.get("avgPrice") or order.get("price"), 0.0)
    if qty <= 0 and entry_price > 0:
        qty = notional / entry_price
    return {
        "symbol": symbol,
        "side": request.get("side") or "BUY",
        "quantity": qty,
        "entry_price": entry_price,
        "notional_usdt": notional,
        "opened_at": order.get("updated_at") or order.get("created_at") or source.get("generated_at"),
        "source": "derived_from_execution_contract",
    }


def _pnl(position: dict, data: dict, fallback_notional: float) -> dict:
    entry = _safe_float(position.get("entry_price") or position.get("avg_entry_price"), 0.0)
    qty = _safe_float(position.get("quantity") or position.get("qty") or position.get("executedQty"), 0.0)
    mark = _safe_float(position.get("mark_price") or position.get("last_price") or data.get("micro_real_mark_price"), 0.0)
    notional = _safe_float(position.get("notional_usdt"), fallback_notional)
    if entry <= 0 or qty <= 0 or mark <= 0:
        return {"entry_price": entry, "mark_price": mark, "quantity": qty, "notional_usdt": notional, "unrealized_pnl_usdt": 0.0, "roi_pct": 0.0, "estimate_available": False}
    pnl = (mark - entry) * qty
    roi = (pnl / max(notional, 0.0001)) * 100.0
    return {"entry_price": entry, "mark_price": mark, "quantity": qty, "notional_usdt": notional, "unrealized_pnl_usdt": round(pnl, 8), "roi_pct": round(roi, 4), "estimate_available": True}


def _exit_preview(position: dict, pnl: dict, policy: dict) -> dict:
    entry = _safe_float(pnl.get("entry_price"), 0.0)
    if entry <= 0:
        return {"available": False, "reason": "entry_price_missing", "direct_close_default_off": True}
    stop = entry * (1 - policy["default_stop_loss_pct"] / 100.0)
    take = entry * (1 + policy["default_take_profit_pct"] / 100.0)
    trail = entry * (1 - policy["default_trailing_pct"] / 100.0)
    return {
        "available": True,
        "stop_loss_price_preview": round(stop, 8),
        "take_profit_price_preview": round(take, 8),
        "trailing_stop_price_preview": round(trail, 8),
        "exit_manager_required": True,
        "direct_close_default_off": True,
        "direct_close_enabled": policy["direct_close_enabled"],
        "network_calls_allowed": policy["network_calls_allowed"],
    }


def build_autonomous_micro_real_position_tracker(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev92 micro-real position tracker.

    Tracks the first micro-real order/position after Rev91 without placing or
    closing orders. It normalizes order state, estimates PnL, checks stale
    positions and surfaces whether manual attention is required.
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
        blockers.append("micro_real_position_tracker_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_execution_revision_mismatch")
    if command.get("approved_for_micro_real_position_tracker") is not True:
        blockers.append("source_not_approved_for_micro_real_position_tracker")
    if source.get("execution_state") != policy["required_source_state"]:
        warnings.append("source_execution_not_live_ready_tracker_preview_only")
    if source.get("places_order") is not True:
        warnings.append("source_execution_has_not_placed_order_yet")
    if policy["kill_switch_active"]:
        blockers.append("kill_switch_active")
    if policy["safe_mode_active"]:
        blockers.append("safe_mode_active")
    if policy["balance_reconciliation_required"] and not policy["balance_reconciliation_ok"]:
        blockers.append("balance_reconciliation_not_ok")
    if not policy["exchange_balance_snapshot_fresh"]:
        warnings.append("exchange_balance_snapshot_not_fresh")

    symbol = _clean_symbol(source.get("symbol") or command.get("symbol"))
    execution_id = str(source.get("execution_id") or command.get("execution_id") or "")
    order = _latest_order_status(data, execution_id, symbol)
    order_status = _normalize_status(order.get("status") if order else None)
    if order_status not in policy["allowed_states"] and order_status != "PENDING_SUBMIT":
        blockers.append("unknown_exchange_order_status")

    audit = source.get("audit_evidence") if isinstance(source.get("audit_evidence"), dict) else {}
    fallback_notional = _safe_float(audit.get("notional_usdt"), 0.0)
    position = _position_snapshot(data, symbol, order, source)
    pnl = _pnl(position, data, fallback_notional)
    position_age = _age_minutes(position.get("opened_at") or order.get("updated_at") or order.get("created_at"))
    order_age = _age_minutes(order.get("updated_at") or order.get("created_at") or source.get("generated_at"))

    if order_status in {"NEW", "ACKNOWLEDGED"} and order_age is not None and order_age > policy["stale_open_order_minutes"]:
        blockers.append("stale_open_order_attention_required")
    if order_status == "PARTIALLY_FILLED" and order_age is not None and order_age > policy["stale_partial_fill_minutes"]:
        blockers.append("stale_partial_fill_attention_required")
    if position_age is not None and position_age > policy["max_position_age_minutes"]:
        warnings.append("position_age_above_policy")
    if _safe_float(pnl.get("unrealized_pnl_usdt"), 0.0) < -policy["max_unrealized_loss_usdt"]:
        blockers.append("unrealized_loss_above_micro_guard")
    if order_status in {"REJECTED", "EXPIRED", "CANCELED"}:
        blockers.append("exchange_order_terminal_not_filled")

    filled = order_status == "FILLED" or _safe_float(position.get("quantity") or position.get("qty"), 0.0) > 0
    partial = order_status == "PARTIALLY_FILLED"
    manual_attention = bool(blockers) or partial or order_status in {"REJECTED", "EXPIRED", "CANCELED"}
    tracker_state = "MICRO_REAL_POSITION_TRACKING"
    status = "ok"
    if blockers:
        tracker_state = "MICRO_REAL_POSITION_ATTENTION_REQUIRED"
        status = "blocked"
    elif partial or warnings:
        tracker_state = "MICRO_REAL_POSITION_REVIEW"
        status = "review"
    elif not filled:
        tracker_state = "MICRO_REAL_POSITION_WAITING_FOR_FILL"
        status = "review"

    score = max(0.0, min(100.0, _safe_float(source.get("execution_score"), 75.0) - len(set(blockers)) * 14.0 - len(set(warnings)) * 2.0))
    exit_preview = _exit_preview(position, pnl, policy)
    tracker_id = "mrpt_" + sha256(f"rev92:{username}:{execution_id}:{symbol}".encode("utf-8")).hexdigest()[:24]

    return {
        "status": status,
        "revision": 92,
        "engine": "autonomous_micro_real_position_tracker",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "tracker_state": tracker_state,
        "tracker_score": round(score, 2),
        "tracker_id": tracker_id,
        "source_revision": source.get("revision"),
        "source_execution_id": execution_id,
        "source_execution_state": source.get("execution_state"),
        "symbol": symbol,
        "target_lane": "MICRO_REAL_POSITION_TRACKER",
        "order_status": order_status,
        "position_status": "OPEN" if filled else ("PARTIAL" if partial else "PENDING"),
        "filled": bool(filled),
        "partial_fill": bool(partial),
        "manual_attention_required": manual_attention,
        "stale_position_guard": {
            "order_age_minutes": round(order_age, 2) if order_age is not None else None,
            "position_age_minutes": round(position_age, 2) if position_age is not None else None,
            "stale_open_order_minutes": policy["stale_open_order_minutes"],
            "stale_partial_fill_minutes": policy["stale_partial_fill_minutes"],
            "max_position_age_minutes": policy["max_position_age_minutes"],
            "ok": not any(item.startswith("stale_") for item in blockers),
        },
        "balance_reconciliation": {
            "required": policy["balance_reconciliation_required"],
            "ok": policy["balance_reconciliation_ok"],
            "exchange_balance_snapshot_fresh": policy["exchange_balance_snapshot_fresh"],
            "blocks_tracker": policy["balance_reconciliation_required"] and not policy["balance_reconciliation_ok"],
        },
        "position_snapshot": {
            "symbol": symbol,
            "side": position.get("side") or "BUY",
            "quantity": _safe_float(position.get("quantity") or position.get("qty"), 0.0),
            "entry_price": pnl.get("entry_price"),
            "mark_price": pnl.get("mark_price"),
            "notional_usdt": pnl.get("notional_usdt"),
            "opened_at": position.get("opened_at"),
            "source": position.get("source") or "runtime_snapshot",
        },
        "pnl_estimate": pnl,
        "exit_preview": exit_preview,
        "exchange_status_model": {
            "normalized_status": order_status,
            "allowed_states": policy["allowed_states"],
            "has_exchange_order_snapshot": bool(order),
            "network_call_executed_by_this_service": False,
            "contains_secret": False,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": {k: v for k, v in policy.items() if k not in set()},
        "command_preview": {
            "type": "micro_real_position_tracker_preview",
            "source_revision": 92,
            "tracker_state": tracker_state,
            "next_action": "HANDOFF_TO_MICRO_REAL_EXIT_MANAGER" if status == "ok" and filled else ("MANUAL_ATTENTION_REQUIRED" if manual_attention else "WAIT_FOR_FILL_OR_STATUS_UPDATE"),
            "symbol": symbol,
            "lane": "MICRO_REAL_POSITION_TRACKER",
            "read_only": True,
            "auto_apply": False,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "approved_for_micro_real_exit_manager": status == "ok" and filled and not manual_attention,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 92,
        "engine": "autonomous_micro_real_position_tracker_summary",
        "generated_at": payload.get("generated_at"),
        "tracker_state": payload.get("tracker_state"),
        "tracker_score": payload.get("tracker_score"),
        "next_action": command.get("next_action"),
        "symbol": payload.get("symbol"),
        "order_status": payload.get("order_status"),
        "position_status": payload.get("position_status"),
        "filled": payload.get("filled") is True,
        "partial_fill": payload.get("partial_fill") is True,
        "manual_attention_required": payload.get("manual_attention_required") is True,
        "unrealized_pnl_usdt": payload.get("pnl_estimate", {}).get("unrealized_pnl_usdt") if isinstance(payload.get("pnl_estimate"), dict) else None,
        "roi_pct": payload.get("pnl_estimate", {}).get("roi_pct") if isinstance(payload.get("pnl_estimate"), dict) else None,
        "balance_reconciliation_ok": payload.get("balance_reconciliation", {}).get("ok") is True if isinstance(payload.get("balance_reconciliation"), dict) else False,
        "stale_guard_ok": payload.get("stale_position_guard", {}).get("ok") is True if isinstance(payload.get("stale_position_guard"), dict) else False,
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
    }


def build_summary_autonomous_micro_real_position_tracker(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_position_tracker(data, settings, auth_store, username))


def build_autonomous_micro_real_position_tracker_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_position_tracker(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_is_92": payload.get("revision") == 92,
        "source_execution_chain_present": payload.get("source_revision") == 91,
        "position_status_normalized": payload.get("order_status") in ["PENDING_SUBMIT", "NEW", "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "REJECTED", "EXPIRED", "CANCELED"],
        "balance_reconciliation_surface_present": isinstance(payload.get("balance_reconciliation"), dict) and "exchange_balance_snapshot_fresh" in payload.get("balance_reconciliation", {}),
        "stale_guard_present": isinstance(payload.get("stale_position_guard"), dict) and "stale_open_order_minutes" in payload.get("stale_position_guard", {}),
        "pnl_estimate_present": isinstance(payload.get("pnl_estimate"), dict) and "unrealized_pnl_usdt" in payload.get("pnl_estimate", {}),
        "exit_preview_present": isinstance(payload.get("exit_preview"), dict) and payload.get("exit_preview", {}).get("direct_close_default_off") is True,
        "manual_attention_flag_present": "manual_attention_required" in payload,
        "service_does_not_place_order": payload.get("places_order") is False and command.get("places_order") is False,
        "service_does_not_execute_network_call": payload.get("sends_exchange_request") is False and payload.get("exchange_status_model", {}).get("network_call_executed_by_this_service") is False,
        "service_does_not_write_runtime": payload.get("writes_runtime_state") is False,
        "secret_safe": payload.get("exchange_status_model", {}).get("contains_secret") is False,
        "summary_revision_is_92": _summary_from_payload(payload).get("revision") == 92,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 92,
        "engine": "autonomous_micro_real_position_tracker_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_POSITION_TRACKER_OK" if passed else "MICRO_REAL_POSITION_TRACKER_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_state": payload.get("tracker_state"),
        "sample_action": command.get("next_action"),
    }
