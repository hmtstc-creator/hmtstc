from __future__ import annotations

from collections import Counter
from copy import deepcopy
from uuid import uuid4

from core.storage import now_iso
from services.real_trade_state_service import ensure_real_trade_state, open_real_positions

REAL_POSITION_STATUSES = [
    "planned",
    "previewed",
    "confirmed",
    "submitted",
    "acknowledged",
    "partially_filled",
    "filled",
    "open",
    "closing_requested",
    "closing_submitted",
    "closing_partially_filled",
    "closed",
    "failed",
    "rejected",
    "cancelled",
    "manual_attention_required",
    "reconciled",
    "orphan_detected",
]

OPEN_LIFECYCLE_STATUSES = {
    "submitted",
    "acknowledged",
    "partially_filled",
    "filled",
    "open",
    "closing_requested",
    "closing_submitted",
    "closing_partially_filled",
    "manual_attention_required",
    "orphan_detected",
}

TERMINAL_LIFECYCLE_STATUSES = {"closed", "failed", "rejected", "cancelled", "reconciled"}
MANUAL_ATTENTION_STATUSES = {"manual_attention_required", "orphan_detected"}

VALID_TRANSITIONS = {
    "planned": {"previewed", "cancelled", "failed"},
    "previewed": {"confirmed", "submitted", "cancelled", "failed"},
    "confirmed": {"submitted", "cancelled", "failed"},
    "submitted": {"acknowledged", "partially_filled", "filled", "open", "rejected", "failed", "manual_attention_required"},
    "acknowledged": {"partially_filled", "filled", "open", "rejected", "failed", "manual_attention_required"},
    "partially_filled": {"filled", "open", "closing_requested", "manual_attention_required", "failed"},
    "filled": {"open", "closing_requested", "manual_attention_required"},
    "open": {"closing_requested", "manual_attention_required", "orphan_detected"},
    "closing_requested": {"closing_submitted", "manual_attention_required", "failed"},
    "closing_submitted": {"closing_partially_filled", "closed", "failed", "manual_attention_required"},
    "closing_partially_filled": {"closed", "manual_attention_required", "failed"},
    "manual_attention_required": {"closing_requested", "closed", "reconciled"},
    "orphan_detected": {"manual_attention_required", "reconciled", "closing_requested"},
    "closed": set(),
    "failed": set(),
    "rejected": set(),
    "cancelled": set(),
    "reconciled": set(),
}

BINANCE_STATUS_TO_LIFECYCLE = {
    "NEW": "submitted",
    "PENDING_NEW": "submitted",
    "PARTIALLY_FILLED": "partially_filled",
    "FILLED": "filled",
    "CANCELED": "cancelled",
    "CANCELLED": "cancelled",
    "REJECTED": "rejected",
    "EXPIRED": "failed",
    "EXPIRED_IN_MATCH": "failed",
}


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(str(value).replace(",", "."))
    except Exception:
        return fallback


def _now() -> str:
    return now_iso()


def _position_id() -> str:
    return f"real_{uuid4().hex}"


def status_group(status: str) -> str:
    status = str(status or "").lower()
    if status in TERMINAL_LIFECYCLE_STATUSES:
        return "terminal"
    if status in MANUAL_ATTENTION_STATUSES:
        return "manual_attention"
    if status in OPEN_LIFECYCLE_STATUSES:
        return "open"
    return "pre_open"


def build_lifecycle_event(from_status: str | None, to_status: str, reason: str, meta: dict | None = None, actor: str = "system") -> dict:
    return {
        "at": _now(),
        "from": from_status,
        "to": to_status,
        "reason": str(reason or "lifecycle_transition"),
        "actor": actor or "system",
        "meta": deepcopy(meta or {}),
    }


def normalize_position_lifecycle(position: dict) -> dict:
    if not isinstance(position, dict):
        position = {}
    status = str(position.get("status") or "planned").strip().lower()
    if status not in REAL_POSITION_STATUSES:
        status = "manual_attention_required"
    position.setdefault("position_id", position.get("id") or _position_id())
    position["status"] = status
    position.setdefault("created_at", position.get("opened_at") or _now())
    position.setdefault("updated_at", position.get("created_at") or _now())
    lifecycle = position.setdefault("lifecycle", [])
    if not isinstance(lifecycle, list):
        position["lifecycle"] = lifecycle = []
    if not lifecycle:
        lifecycle.append(build_lifecycle_event(None, status, "lifecycle_initialized"))
    position["manual_attention_required"] = bool(position.get("manual_attention_required") or status in MANUAL_ATTENTION_STATUSES)
    position.setdefault("manual_attention_reason", "" if not position["manual_attention_required"] else "status_requires_manual_attention")
    position.setdefault("order_links", [])
    if not isinstance(position.get("order_links"), list):
        position["order_links"] = [position.get("order_links")]
    position.setdefault("realized_pnl", 0.0)
    position.setdefault("unrealized_pnl", 0.0)
    position.setdefault("commission", 0.0)
    position.setdefault("commission_asset", "")
    position.setdefault("avg_fill_price", position.get("entry_price") or position.get("price") or None)
    position.setdefault("quantity", position.get("executed_qty") or position.get("orig_qty") or position.get("quantity") or None)
    position.setdefault("quote_order_qty", position.get("quote_order_qty") or position.get("usdt_size") or None)
    position["lifecycle_summary"] = {
        "status": status,
        "status_group": status_group(status),
        "events": len(lifecycle),
        "last_reason": lifecycle[-1].get("reason") if lifecycle else None,
        "manual_attention_required": bool(position.get("manual_attention_required")),
    }
    return position


def ensure_position_lifecycles(data: dict) -> dict:
    state = ensure_real_trade_state(data)
    state["positions"] = [normalize_position_lifecycle(p) for p in state.get("positions", []) or []]
    state.setdefault("position_history", [])
    if not isinstance(state.get("position_history"), list):
        state["position_history"] = []
    return state


def find_position(state: dict, position_id: str) -> dict | None:
    for item in state.get("positions", []) or []:
        if str(item.get("position_id") or item.get("id") or "") == str(position_id):
            return item
    return None


def position_by_order_link(state: dict, order_id: str) -> dict | None:
    order_id = str(order_id or "")
    if not order_id:
        return None
    for item in state.get("positions", []) or []:
        links = [str(x) for x in item.get("order_links", []) or []]
        if order_id in links or str(item.get("client_order_id") or "") == order_id or str(item.get("order_id") or "") == order_id:
            return item
    return None


def transition_position(state: dict, position_id: str, to_status: str, reason: str = "manual_transition", meta: dict | None = None, actor: str = "system") -> dict:
    to_status = str(to_status or "").strip().lower()
    if to_status not in REAL_POSITION_STATUSES:
        return {"status": "blocked", "reason": "invalid_target_status", "allowed_statuses": REAL_POSITION_STATUSES}
    position = find_position(state, position_id)
    if not position:
        return {"status": "blocked", "reason": "position_not_found", "position_id": position_id}
    normalize_position_lifecycle(position)
    current = str(position.get("status") or "planned")
    allowed = VALID_TRANSITIONS.get(current, set())
    if to_status not in allowed and to_status != current:
        return {"status": "blocked", "reason": "invalid_lifecycle_transition", "from": current, "to": to_status, "allowed": sorted(allowed)}
    if to_status != current:
        position.setdefault("lifecycle", []).append(build_lifecycle_event(current, to_status, reason, meta=meta or {}, actor=actor))
    position["status"] = to_status
    position["updated_at"] = _now()
    position["manual_attention_required"] = to_status in MANUAL_ATTENTION_STATUSES
    if position["manual_attention_required"]:
        position["manual_attention_reason"] = reason or "manual_attention_required"
        state["manual_attention_required"] = True
    normalize_position_lifecycle(position)
    if to_status in TERMINAL_LIFECYCLE_STATUSES:
        archive_closed_position(state, position, reason=reason)
    return {"status": "ok", "position": position, "from": current, "to": to_status, "event": position.get("lifecycle", [])[-1]}


def create_planned_position(state: dict, symbol: str, side: str, quote_order_qty: float, reason: str = "position_planned", meta: dict | None = None) -> dict:
    position = normalize_position_lifecycle({
        "position_id": _position_id(),
        "status": "planned",
        "symbol": str(symbol or "").upper(),
        "side": str(side or "BUY").upper(),
        "quote_order_qty": quote_order_qty,
        "lifecycle": [build_lifecycle_event(None, "planned", reason, meta=meta or {})],
    })
    state.setdefault("positions", []).append(position)
    return position


def create_preview_position(state: dict, preview: dict, user: str = "system") -> dict:
    preview_id = str((preview or {}).get("preview_id") or f"preview_{uuid4().hex}")
    existing = position_by_order_link(state, preview_id)
    if existing:
        return normalize_position_lifecycle(existing)
    position = create_planned_position(
        state,
        symbol=(preview or {}).get("symbol"),
        side=(preview or {}).get("side"),
        quote_order_qty=_safe_float((preview or {}).get("quote_order_qty")),
        reason="order_preview_created",
        meta={"preview_id": preview_id, "user": user},
    )
    position.setdefault("order_links", []).append(preview_id)
    transition_position(state, position["position_id"], "previewed", reason="order_preview_ready", meta={"preview_id": preview_id, "blockers": (preview or {}).get("blockers", [])}, actor=user)
    return position


def lifecycle_status_from_binance_response(response: dict) -> str:
    if not response or not response.get("ok"):
        return "failed"
    data = response.get("data") or {}
    raw_status = str(data.get("status") or "NEW").upper()
    lifecycle = BINANCE_STATUS_TO_LIFECYCLE.get(raw_status, "acknowledged")
    executed = _safe_float(data.get("executedQty") or data.get("executed_qty"), 0.0)
    orig = _safe_float(data.get("origQty") or data.get("orig_qty"), 0.0)
    if lifecycle == "filled" and executed > 0:
        return "open"
    if executed > 0 and orig > executed:
        return "partially_filled"
    return lifecycle


def create_position_from_order_record(state: dict, order_record: dict, response: dict | None = None, user: str = "system") -> dict:
    response = response if response is not None else (order_record or {}).get("binance_response") or {}
    client_order_id = str((order_record or {}).get("order_id") or (order_record or {}).get("id") or f"order_{uuid4().hex}")
    preview_id = str(((order_record or {}).get("safety") or {}).get("preview_id") or ((order_record or {}).get("payload_snapshot") or {}).get("preview_id") or "")
    existing = position_by_order_link(state, client_order_id) or position_by_order_link(state, preview_id)
    status = lifecycle_status_from_binance_response(response)
    meta = {"client_order_id": client_order_id, "preview_id": preview_id, "binance_status": ((response or {}).get("data") or {}).get("status")}
    if existing:
        if client_order_id and client_order_id not in (existing.get("order_links") or []):
            existing.setdefault("order_links", []).append(client_order_id)
        result = transition_position(state, existing["position_id"], status if status in VALID_TRANSITIONS.get(existing.get("status"), set()) else "manual_attention_required", reason="binance_order_response", meta=meta, actor=user)
        return result.get("position", existing)
    position = normalize_position_lifecycle({
        "position_id": _position_id(),
        "status": "submitted" if status not in {"failed", "rejected", "cancelled"} else status,
        "symbol": (order_record or {}).get("symbol"),
        "side": (order_record or {}).get("side"),
        "quote_order_qty": (order_record or {}).get("quote_order_qty"),
        "client_order_id": client_order_id,
        "order_links": [x for x in [preview_id, client_order_id] if x],
        "opened_at": _now(),
        "safety_snapshot": (order_record or {}).get("safety"),
        "binance_response_snapshot": deepcopy(response or {}),
        "lifecycle": [build_lifecycle_event(None, "submitted" if status not in {"failed", "rejected", "cancelled"} else status, "binance_order_submitted", meta=meta, actor=user)],
    })
    state.setdefault("positions", []).append(position)
    if status == "open" and position.get("status") == "submitted":
        # Submitted -> filled -> open keeps a complete lifecycle chain.
        transition_position(state, position["position_id"], "filled", reason="binance_filled", meta=meta, actor=user)
        transition_position(state, position["position_id"], "open", reason="position_opened", meta=meta, actor=user)
    elif status not in {position.get("status"), "submitted"}:
        transition_position(state, position["position_id"], status, reason="binance_order_response", meta=meta, actor=user)
    return normalize_position_lifecycle(position)


def archive_closed_position(state: dict, position: dict, reason: str = "closed") -> dict:
    normalize_position_lifecycle(position)
    entry = deepcopy(position)
    entry["archived_at"] = _now()
    entry["archive_reason"] = reason
    history = state.setdefault("position_history", [])
    if not any(str(x.get("position_id")) == str(position.get("position_id")) and x.get("status") == position.get("status") for x in history):
        history.append(entry)
    state["position_history"] = history[-1000:]
    return entry


def detect_orphan_orders(state: dict, create_markers: bool = False) -> dict:
    ensure_position_lifecycles({"real_trade": state})
    orphans = []
    for order in state.get("orders", []) or []:
        if not order.get("real_order_created"):
            continue
        order_id = str(order.get("order_id") or order.get("id") or "")
        if not order_id:
            continue
        if not position_by_order_link(state, order_id):
            orphans.append({"order_id": order_id, "symbol": order.get("symbol"), "side": order.get("side"), "status": order.get("status")})
            if create_markers:
                marker = normalize_position_lifecycle({
                    "position_id": _position_id(),
                    "status": "orphan_detected",
                    "symbol": order.get("symbol"),
                    "side": order.get("side"),
                    "quote_order_qty": order.get("quote_order_qty"),
                    "order_links": [order_id],
                    "manual_attention_required": True,
                    "manual_attention_reason": "real_order_without_position",
                    "lifecycle": [build_lifecycle_event(None, "orphan_detected", "real_order_without_position", meta={"order_id": order_id})],
                })
                state.setdefault("positions", []).append(marker)
    if orphans:
        state["manual_attention_required"] = True
    return {"status": "review" if orphans else "ok", "orphan_count": len(orphans), "orphans": orphans}


def build_position_timeline(state: dict, position_id: str) -> dict:
    ensure_position_lifecycles({"real_trade": state})
    position = find_position(state, position_id)
    if not position:
        return {"status": "not_found", "position_id": position_id, "events": []}
    return {
        "status": "ok",
        "position_id": position.get("position_id"),
        "symbol": position.get("symbol"),
        "current_status": position.get("status"),
        "manual_attention_required": bool(position.get("manual_attention_required")),
        "events": position.get("lifecycle", []) or [],
        "order_links": position.get("order_links", []) or [],
        "summary": position.get("lifecycle_summary") or {},
    }


def build_real_position_lifecycle_report(data: dict) -> dict:
    state = ensure_position_lifecycles(data)
    orphan_report = detect_orphan_orders(state, create_markers=False)
    positions = state.get("positions", []) or []
    orders = state.get("orders", []) or []
    counts = Counter(str(p.get("status") or "unknown") for p in positions)
    open_positions = [p for p in positions if str(p.get("status")) in OPEN_LIFECYCLE_STATUSES]
    manual = [p for p in positions if p.get("manual_attention_required") or str(p.get("status")) in MANUAL_ATTENTION_STATUSES]
    lifecycle_events = sum(len(p.get("lifecycle", []) or []) for p in positions)
    exposure = sum(_safe_float(p.get("quote_order_qty") or p.get("usdt_size") or 0) for p in open_positions)
    return {
        "status": "review" if manual or orphan_report.get("orphan_count") else "ok",
        "positions_count": len(positions),
        "open_positions_count": len(open_positions),
        "manual_attention_count": len(manual),
        "orders_count": len(orders),
        "status_counts": dict(counts),
        "lifecycle_events": lifecycle_events,
        "open_exposure_usdt": round(exposure, 6),
        "orphan_report": orphan_report,
        "allowed_statuses": REAL_POSITION_STATUSES,
        "valid_transitions": {k: sorted(v) for k, v in VALID_TRANSITIONS.items()},
        "terminal_statuses": sorted(TERMINAL_LIFECYCLE_STATUSES),
        "open_statuses": sorted(OPEN_LIFECYCLE_STATUSES),
        "positions": positions[-200:],
        "position_history": state.get("position_history", [])[-200:],
        "message": "Real position lifecycle Paper/Shadow state'ten ayrıdır; manual attention durumları real order akışını kilitlemelidir.",
    }


def build_reconciliation_report(data: dict, balances: dict | None = None) -> dict:
    state = ensure_position_lifecycles(data)
    tracked = [p for p in state.get("positions", []) or [] if str(p.get("status")) in OPEN_LIFECYCLE_STATUSES]
    issues = []
    non_usdt_assets = []
    if balances and balances.get("balances_readable"):
        for row in balances.get("balances", []) or []:
            total = _safe_float(row.get("total"), 0.0)
            if row.get("asset") != "USDT" and total > 0:
                non_usdt_assets.append(row)
    elif balances:
        issues.append("balance_not_readable")
    if non_usdt_assets and not tracked:
        issues.append("binance_asset_without_tracked_position")
    if tracked and balances and balances.get("balances_readable") and not non_usdt_assets:
        issues.append("tracked_position_without_binance_asset")
    orphan_report = detect_orphan_orders(state, create_markers=True)
    if orphan_report.get("orphan_count"):
        issues.append("orphan_order_detected")
    if issues:
        state["manual_attention_required"] = True
        state["real_trade_locked_by_reconciliation"] = True
        state["reconciliation_required"] = True
    return {
        "status": "ok" if not issues else "review",
        "issues": sorted(set(issues)),
        "tracked_open_positions": len(tracked),
        "binance_non_usdt_assets": non_usdt_assets,
        "orphan_report": orphan_report,
        "manual_attention_required": bool(state.get("manual_attention_required")),
        "checked_at": _now(),
    }


def build_emergency_close_lifecycle_preview(data: dict) -> dict:
    state = ensure_position_lifecycles(data)
    positions = [p for p in state.get("positions", []) or [] if str(p.get("status")) in OPEN_LIFECYCLE_STATUSES]
    previews = []
    blockers = []
    for p in positions:
        symbol = str(p.get("symbol") or "").upper()
        qty = p.get("quantity") or p.get("executed_qty") or None
        if not symbol:
            blockers.append("position_missing_symbol")
        if qty in {None, "", 0, "0"}:
            blockers.append("position_missing_quantity")
        previews.append({
            "position_id": p.get("position_id"),
            "symbol": symbol,
            "current_status": p.get("status"),
            "close_side": "SELL" if str(p.get("side") or "BUY").upper() == "BUY" else "BUY",
            "quantity": qty,
            "requires_binance_filter_validation": True,
            "requires_confirmation_token": True,
            "timeline_events": len(p.get("lifecycle", []) or []),
        })
    return {
        "status": "preview",
        "auto_close": False,
        "positions_count": len(positions),
        "positions": previews,
        "blockers": sorted(set(blockers)),
        "message": "Rev20: otomatik close yok; emergency close için önce lifecycle-aware dry-run preview, sonra owner confirmation token gerekir.",
    }
