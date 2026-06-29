from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from core.storage import now_iso
from services.real_trade_state_service import ensure_real_trade_state, open_real_positions


OPEN_STATUSES = {
    "submitted",
    "acknowledged",
    "partially_filled",
    "filled",
    "open",
    "closing",
    "closing_requested",
    "closing_submitted",
    "closing_partially_filled",
    "manual_attention_required",
    "orphan_detected",
}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, str):
            value = value.replace("USDT", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return fallback


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _checksum(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _simple_status(status: str) -> str:
    text = str(status or "").lower()
    if text in {"submitted", "acknowledged", "open", "filled", "partially_filled"}:
        return "İzleniyor"
    if text in {"closing", "closing_requested", "closing_submitted", "closing_partially_filled"}:
        return "Kapanıyor"
    if text in {"closed", "cancelled", "failed"}:
        return "Tamamlandı" if text == "closed" else "Kontrol gerekli"
    if text in {"manual_attention_required", "orphan_detected"}:
        return "Kontrol gerekli"
    return "Bekliyor"


def _position_view(position: dict) -> dict:
    pnl = _safe_float(position.get("pnl") or position.get("unrealized_pnl") or position.get("realized_pnl"), 0.0)
    return {
        "position_id": position.get("position_id") or position.get("id"),
        "symbol": position.get("symbol") or "-",
        "side": position.get("side") or position.get("mode") or "-",
        "status": position.get("status") or "open",
        "simple_status": _simple_status(position.get("status") or "open"),
        "pnl_usdt": pnl,
        "entry_price": position.get("entry_price") or position.get("price"),
        "quantity": position.get("quantity") or position.get("executed_qty"),
        "opened_at": position.get("opened_at") or position.get("time") or position.get("created_at"),
        "order_id": position.get("order_id") or position.get("source_order_id"),
    }


def _order_view(order: dict) -> dict:
    return {
        "order_id": order.get("order_id") or order.get("id"),
        "position_id": order.get("position_id"),
        "symbol": order.get("symbol") or "-",
        "side": order.get("side") or "-",
        "status": order.get("status") or "unknown",
        "simple_status": _simple_status(order.get("status") or "unknown"),
        "quote_order_qty": _safe_float(order.get("quote_order_qty") or order.get("usdt_size"), 0.0),
        "real_order_created": bool(order.get("real_order_created")),
        "dry_run": bool(order.get("dry_run")),
        "time": order.get("time") or order.get("created_at"),
        "binance_order_id": ((order.get("binance_response") or {}).get("data") or {}).get("orderId") or order.get("binance_order_id"),
    }


def _ensure_lifecycle_store(state: dict) -> dict:
    store = state.setdefault("order_lifecycle", {})
    store.setdefault("close_previews", [])
    store.setdefault("evidence", [])
    store.setdefault("events", [])
    store["close_previews"] = list(store.get("close_previews") or [])[-100:]
    store["evidence"] = list(store.get("evidence") or [])[-500:]
    store["events"] = list(store.get("events") or [])[-500:]
    return store


def append_lifecycle_event(state: dict, event_type: str, status: str, message: str, meta: dict | None = None, user: str = "system") -> dict:
    store = _ensure_lifecycle_store(state)
    event = {
        "event_id": _short_id("evt"),
        "event_type": event_type,
        "status": status,
        "message": message,
        "meta": meta or {},
        "user": user,
        "created_at": now_iso(),
    }
    store["events"].append(event)
    store["events"] = store["events"][-500:]
    return event


def build_live_order_lifecycle(data: dict, settings: dict | None = None, user: str = "default") -> dict:
    """Return the real-order lifecycle in plain language.

    This is a visibility layer. It does not submit orders. It makes the real
    order chain auditable: submit, exchange id, position tracking, close request,
    emergency close and evidence records.
    """
    state = ensure_real_trade_state(data)
    store = _ensure_lifecycle_store(state)
    orders = [_order_view(order) for order in list(state.get("orders") or [])[-50:]]
    positions = [_position_view(position) for position in list(state.get("positions") or [])[-50:]]
    open_positions = [_position_view(position) for position in open_real_positions(state)]
    open_orders = [order for order in orders if str(order.get("status") or "").lower() not in {"closed", "failed", "cancelled", "blocked"}]
    attention_positions = [p for p in positions if str(p.get("status") or "").lower() in {"manual_attention_required", "orphan_detected"}]
    last_evidence = list(store.get("evidence") or [])[-10:]
    lifecycle_steps = [
        {"key": "preview", "title": "Ön kontrol", "simple_text": "Emirden önce güvenlik kontrolü yapılır."},
        {"key": "submit", "title": "Emir gönder", "simple_text": "Sadece onay geçerse Binance emri denenir."},
        {"key": "exchange_id", "title": "Order ID kaydet", "simple_text": "Binance cevabı ve order id kayıt altına alınır."},
        {"key": "track", "title": "Pozisyonu izle", "simple_text": "Açık işlem kar/zarar ve durumuyla izlenir."},
        {"key": "close", "title": "Kapat", "simple_text": "Kapanış isteği ayrı kayıtla takip edilir."},
        {"key": "evidence", "title": "Kanıt kaydı", "simple_text": "Her adım checksum ile kayıt altına alınır."},
    ]
    blockers = []
    if bool(state.get("emergency_lock")):
        blockers.append("emergency_lock_active")
    if attention_positions:
        blockers.append("manual_attention_required")
    status = "review" if blockers else "ok"
    return {
        "status": status,
        "user": user,
        "simple_status": "Kontrol gerekli" if blockers else "İyi",
        "decision": "Kontrol gereken pozisyon var." if blockers else "Emir yaşam döngüsü izlenebilir durumda.",
        "open_position_count": len(open_positions),
        "open_order_count": len(open_orders),
        "evidence_count": len(store.get("evidence") or []),
        "last_order": orders[-1] if orders else None,
        "orders": list(reversed(orders[-20:])),
        "positions": list(reversed(positions[-20:])),
        "open_positions": open_positions,
        "close_previews": list(reversed(list(store.get("close_previews") or [])[-20:])),
        "recent_evidence": list(reversed(last_evidence)),
        "recent_events": list(reversed(list(store.get("events") or [])[-20:])),
        "lifecycle_steps": lifecycle_steps,
        "blockers": blockers,
        "checked_at": now_iso(),
    }


def build_close_preview(data: dict, settings: dict | None, payload: dict | None = None, user: str = "default") -> dict:
    """Create a close preview record without sending a real exchange order."""
    payload = payload or {}
    state = ensure_real_trade_state(data)
    store = _ensure_lifecycle_store(state)
    position_id = str(payload.get("position_id") or "").strip()
    positions = list(state.get("positions") or [])
    position = next((p for p in positions if str(p.get("position_id") or p.get("id") or "") == position_id), None)
    blockers = []
    if not position_id:
        blockers.append("position_id_missing")
    if position_id and not position:
        blockers.append("position_not_found")
    if position and str(position.get("status") or "").lower() not in OPEN_STATUSES:
        blockers.append("position_not_open")
    if bool(state.get("emergency_lock")):
        blockers.append("emergency_lock_active")

    preview = {
        "preview_id": _short_id("close_preview"),
        "position_id": position_id,
        "status": "blocked" if blockers else "ready",
        "simple_status": "Kapatılamaz" if blockers else "Kapatmaya hazır",
        "symbol": (position or {}).get("symbol") or payload.get("symbol") or "-",
        "side": (position or {}).get("side") or payload.get("side") or "-",
        "estimated_pnl_usdt": _safe_float((position or {}).get("pnl") or (position or {}).get("unrealized_pnl"), 0.0),
        "real_order_created": False,
        "blockers": blockers,
        "created_by": user,
        "created_at": now_iso(),
    }
    preview["checksum"] = _checksum(preview)
    store["close_previews"].append(preview)
    append_lifecycle_event(state, "close_preview", preview["status"], "Pozisyon kapatma ön izlemesi oluşturuldu.", {"preview_id": preview["preview_id"], "position_id": position_id}, user=user)
    return preview


def record_lifecycle_evidence(data: dict, payload: dict | None = None, user: str = "default") -> dict:
    """Append an auditable evidence record for an order/position lifecycle step."""
    payload = payload or {}
    state = ensure_real_trade_state(data)
    store = _ensure_lifecycle_store(state)
    evidence = {
        "evidence_id": _short_id("evidence"),
        "order_id": payload.get("order_id"),
        "position_id": payload.get("position_id"),
        "event_type": payload.get("event_type") or "manual_lifecycle_note",
        "status": payload.get("status") or "recorded",
        "note": payload.get("note") or "Emir yaşam döngüsü kanıtı kaydedildi.",
        "meta": payload.get("meta") if isinstance(payload.get("meta"), dict) else {},
        "created_by": user,
        "created_at": now_iso(),
    }
    evidence["checksum"] = _checksum(evidence)
    store["evidence"].append(evidence)
    store["evidence"] = store["evidence"][-500:]
    append_lifecycle_event(state, "evidence_record", "ok", "Emir kanıtı kaydedildi.", {"evidence_id": evidence["evidence_id"], "order_id": evidence.get("order_id"), "position_id": evidence.get("position_id")}, user=user)
    return {"status": "ok", "evidence": evidence, "evidence_count": len(store.get("evidence") or [])}
