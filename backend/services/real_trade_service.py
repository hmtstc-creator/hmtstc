from __future__ import annotations

from uuid import uuid4
import os
from copy import deepcopy

from core.storage import append_audit, now_iso
from services.binance_service import BinanceService, load_binance_runtime_config
from services.real_trade_state_service import (
    append_real_order,
    append_real_position,
    consume_confirmation_token,
    create_confirmation_token,
    ensure_real_trade_state,
    is_unlock_valid,
    lock_real_trading,
    open_real_positions,
    unlock_real_trading,
)
from services.real_trade_safety_service import build_runtime_health
from services.real_position_lifecycle_service import (
    build_emergency_close_lifecycle_preview,
    build_position_timeline,
    build_real_position_lifecycle_report,
    create_position_from_order_record,
    create_preview_position,
    detect_orphan_orders,
    ensure_position_lifecycles,
    normalize_position_lifecycle,
    transition_position,
)
from services.real_balance_service import (
    build_balance_reconciliation_full_report,
    build_balance_reconciliation_report,
    build_manual_reconciliation_report,
    build_money_separation_report,
    build_real_pnl_report,
    build_real_wallet_integrity_report,
    capture_balance_snapshot,
)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return fallback


def _normalize_blockers(blockers: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in blockers if str(item).strip()})


def _order_payload_snapshot(symbol: str, side: str, quote_order_qty: float, validation: dict | None = None, preview_id: str | None = None) -> dict:
    payload = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quoteOrderQty": quote_order_qty,
    }
    return {
        "preview_id": preview_id,
        "payload": payload,
        "validation": deepcopy(validation or {}),
        "sensitive_fields_removed": True,
        "binance_endpoint": "POST /api/v3/order",
    }


def _audit_meta_for_order(endpoint: str, record: dict, safety: dict | None = None, role: str = "owner") -> dict:
    return {
        "category": "trading",
        "severity": "blocked" if record.get("status") == "blocked" else "critical",
        "endpoint": endpoint,
        "symbol": record.get("symbol"),
        "side": record.get("side"),
        "quote_order_qty": record.get("quote_order_qty"),
        "order_id": record.get("order_id") or record.get("id"),
        "dry_run": bool(record.get("dry_run")),
        "real_order_created": bool(record.get("real_order_created")),
        "blockers": record.get("blockers") or (safety or {}).get("blockers", []),
        "payload_snapshot": record.get("payload_snapshot") or (safety or {}).get("payload_snapshot"),
        "confirmation": record.get("confirmation") or {},
        "safety_summary": {
            "status": (safety or {}).get("status"),
            "real_order_allowed": (safety or {}).get("real_order_allowed"),
            "dry_run": (safety or {}).get("dry_run"),
        },
        "role": role,
    }


def build_binance_health() -> dict:
    service = BinanceService()
    if str(os.getenv("HMTSTC_OFFLINE_QUALITY_CHECK", "")).lower() in {"1", "true", "yes"}:
        summary = {
            "status": "offline_check",
            "mode": service.mode,
            "base_url": service.base_url,
            "testnet": service.runtime.testnet,
            "public_connection": False,
            "server_time_ok": False,
            "api_key_saved": service.runtime.has_api_key,
            "api_secret_saved": service.runtime.has_api_secret,
            "account_access": False,
            "runtime_config": service.runtime.public(),
            "offline_quality_check": True,
        }
        status = "offline"
    else:
        summary = service.summary()
        status = "ok" if summary.get("public_connection") and summary.get("server_time_ok") else "blocked"
    return {
        "status": status,
        "summary": summary,
        "permission": {
            "account_access": bool(summary.get("account_access")),
            "spot_only_design": True,
            "withdraw_endpoint_present": False,
            "futures_margin_endpoints_present": False,
            "note": "Binance API withdraw iznini kapalı tut; IP whitelist önerilir.",
        },
    }


def read_real_balances() -> dict:
    service = BinanceService()
    balances = service.balances()
    if not balances.get("ok"):
        return {"status": "blocked", "balances_readable": False, "error": balances.get("error"), "raw": balances}
    items = balances.get("data", {}).get("balances", [])
    usdt = next((row for row in items if row.get("asset") == "USDT"), {"free": 0, "locked": 0, "total": 0})
    return {"status": "ok", "balances_readable": True, "usdt": usdt, "balances": items, "count": len(items)}


def build_real_readiness(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    ensure_position_lifecycles(data)
    runtime = load_binance_runtime_config()
    health = build_runtime_health(data, settings)
    binance = build_binance_health()
    balances = read_real_balances() if runtime.has_api_key and runtime.has_api_secret else {"status": "blocked", "balances_readable": False, "error": "credentials_missing"}
    blockers = []
    if not runtime.has_api_key or not runtime.has_api_secret:
        blockers.append("binance_credentials_missing")
    if binance.get("status") != "ok":
        blockers.append("binance_public_health_blocked")
    if not (binance.get("summary") or {}).get("account_access"):
        blockers.append("binance_account_access_missing")
    if not balances.get("balances_readable"):
        blockers.append("balance_not_readable")
    if not runtime.real_trading_enabled:
        blockers.append("env_real_trading_disabled")
    if runtime.real_trading_dry_run:
        blockers.append("dry_run_active")
    if not is_unlock_valid(state):
        blockers.append("owner_unlock_missing_or_expired")
    if state.get("emergency_lock") or data.get("emergency_lock"):
        blockers.append("emergency_lock_active")
    if state.get("real_trade_locked_by_reconciliation"):
        blockers.append("balance_reconciliation_lock_active")
    if state.get("manual_attention_required"):
        blockers.append("manual_attention_required")
    if health.get("status") != "ok":
        blockers.append("runtime_health_degraded")
    if len(open_real_positions(state)) >= runtime.max_open_positions:
        blockers.append("max_open_real_positions_reached")
    ready_for_dry_run = runtime.has_api_key and runtime.has_api_secret and binance.get("status") == "ok"
    ready_for_real_order = not blockers and runtime.real_trading_enabled and not runtime.real_trading_dry_run and is_unlock_valid(state)
    payload = {
        "status": "ready" if ready_for_real_order else ("dry_run_ready" if ready_for_dry_run else "blocked"),
        "env": runtime.public(),
        "binance": binance,
        "balances": balances,
        "runtime_health": health,
        "real_state": {
            "owner_unlocked": bool(state.get("owner_unlocked")),
            "unlock_valid": is_unlock_valid(state),
            "unlock_expires_at": state.get("unlock_expires_at"),
            "pilot_active": bool((state.get("pilot") or {}).get("active")),
            "emergency_lock": bool(state.get("emergency_lock") or data.get("emergency_lock")),
            "open_positions": len(open_real_positions(state)),
        },
        "ready_for_dry_run": ready_for_dry_run,
        "ready_for_real_order": ready_for_real_order,
        "blockers": blockers,
        "checked_at": now_iso(),
    }
    state["last_readiness"] = payload
    return payload


def build_order_safety_report(data: dict, settings: dict, order: dict, user: str = "system", role: str = "owner") -> dict:
    state = ensure_real_trade_state(data)
    runtime = load_binance_runtime_config()
    service = BinanceService()
    symbol = str((order or {}).get("symbol") or "").upper().strip()
    side = str((order or {}).get("side") or "BUY").upper().strip()
    quote_order_qty = _safe_float((order or {}).get("quote_order_qty", (order or {}).get("usdt_size", 0)))
    quantity = (order or {}).get("quantity")
    price = (order or {}).get("price")
    preview_id = str((order or {}).get("preview_id") or f"preview_{uuid4().hex}")
    readiness = build_real_readiness(data, settings)
    validation = service.validate_market_order_payload(symbol, side, quote_order_qty, quantity=quantity, price=price)
    blockers = list(readiness.get("blockers", [])) + list(validation.get("blockers", []))
    warnings = list(validation.get("warnings", []))
    if quote_order_qty > runtime.max_order_usdt:
        blockers.append("max_order_usdt_exceeded")
    if side == "BUY" and readiness.get("balances", {}).get("usdt", {}).get("free", 0) < quote_order_qty:
        blockers.append("insufficient_usdt_balance")
    if len(open_real_positions(state)) >= runtime.max_open_positions:
        blockers.append("max_open_positions_reached")
    blockers = _normalize_blockers(blockers)
    warnings = _normalize_blockers(warnings)
    token_item = None
    preview_payload = {"symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "preview_id": preview_id}
    if not blockers:
        token_item = create_confirmation_token(state, preview_payload, ttl_seconds=60, user=user, role=role, preview_id=preview_id)
    payload_snapshot = _order_payload_snapshot(symbol, side, quote_order_qty, validation=validation, preview_id=preview_id)
    preview_position = create_preview_position(state, {"preview_id": preview_id, "symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "blockers": blockers}, user=user)
    return {
        "status": "blocked" if blockers else "ready_for_confirmation",
        "preview_id": preview_id,
        "preview_position_id": preview_position.get("position_id"),
        "dry_run": runtime.real_trading_dry_run,
        "real_order_allowed": False if runtime.real_trading_dry_run else not blockers,
        "symbol": symbol,
        "side": side,
        "quote_order_qty": quote_order_qty,
        "payload": validation.get("payload"),
        "payload_snapshot": payload_snapshot,
        "blockers": blockers,
        "warnings": warnings,
        "confirmation_token": token_item.get("token") if token_item else None,
        "confirmation_token_id": token_item.get("token_id") if token_item else None,
        "confirmation_payload_hash": token_item.get("payload_hash") if token_item else None,
        "confirmation_expires_at": token_item.get("expires_at") if token_item else None,
        "readiness": readiness,
        "symbol_validation": validation,
        "blocker_matrix": {
            "readiness": list(readiness.get("blockers", [])),
            "symbol_validation": list(validation.get("blockers", [])),
            "balance": ["insufficient_usdt_balance"] if "insufficient_usdt_balance" in blockers else [],
            "limits": [x for x in blockers if x in {"max_order_usdt_exceeded", "max_open_positions_reached"}],
            "confirmation": [],
        },
    }


def dry_run_order(data: dict, settings: dict, order: dict, user: str, role: str = "owner") -> dict:
    state = ensure_real_trade_state(data)
    safety = build_order_safety_report(data, settings, order, user=user, role=role)
    order_id = f"dry_{uuid4().hex}"
    record = {
        "id": order_id,
        "order_id": order_id,
        "time": now_iso(),
        "status": "blocked" if safety.get("blockers") else "dry_run_ready",
        "dry_run": True,
        "real_order_created": False,
        "symbol": safety.get("symbol"),
        "side": safety.get("side"),
        "quote_order_qty": safety.get("quote_order_qty"),
        "safety": safety,
        "payload": safety.get("payload"),
        "payload_snapshot": safety.get("payload_snapshot"),
        "blockers": safety.get("blockers", []),
        "result": "no_binance_order_sent",
    }
    append_real_order(state, record)
    append_audit(data, "real_order.dry_run", record["status"], "Real order dry-run kontrolü tamamlandı.", meta=_audit_meta_for_order("/api/real/orders/dry-run", record, safety, role=role), user=user)
    return record


def place_real_order(data: dict, settings: dict, order: dict, user: str, role: str = "owner") -> dict:
    state = ensure_real_trade_state(data)
    runtime = load_binance_runtime_config()
    symbol = str((order or {}).get("symbol") or "").upper().strip()
    side = str((order or {}).get("side") or "BUY").upper().strip()
    quote_order_qty = _safe_float((order or {}).get("quote_order_qty", (order or {}).get("usdt_size", 0)))
    token = str((order or {}).get("confirmation_token") or "")
    preview_id = str((order or {}).get("preview_id") or "")
    safety = build_order_safety_report(data, settings, {"symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "preview_id": preview_id or None}, user=user, role=role)
    token_result = consume_confirmation_token(state, token, {"symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "preview_id": preview_id or safety.get("preview_id")}, user=user, role=role, preview_id=preview_id or safety.get("preview_id"))
    blockers = list(safety.get("blockers", []))
    if not token_result.get("ok"):
        blockers.append(token_result.get("reason") or "confirmation_token_invalid")
    if runtime.real_trading_dry_run:
        blockers.append("dry_run_active_real_place_blocked")
    if not runtime.real_trading_enabled:
        blockers.append("env_real_trading_disabled")
    if blockers:
        record = {"id": f"blocked_{uuid4().hex}", "time": now_iso(), "status": "blocked", "dry_run": runtime.real_trading_dry_run, "real_order_created": False, "symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "blockers": _normalize_blockers(blockers), "safety": safety, "payload_snapshot": safety.get("payload_snapshot"), "confirmation": token_result}
        append_real_order(state, record)
        append_audit(data, "real_order.place_blocked", "blocked", "Gerçek emir safety/confirmation tarafından engellendi.", meta=_audit_meta_for_order("/api/real/orders/place", record, safety, role=role), user=user)
        return record
    pre_snapshot = capture_balance_snapshot(state, read_real_balances(), phase="pre_order", order={"symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "preview_id": preview_id}, reason="before_real_order_place")
    service = BinanceService()
    client_order_id = f"hmtstc_{uuid4().hex[:24]}"
    response = service.place_market_order(symbol, side, quote_order_qty, new_client_order_id=client_order_id)
    post_snapshot = capture_balance_snapshot(state, read_real_balances(), phase="post_order", order={"id": client_order_id, "symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "preview_id": preview_id}, reason="after_real_order_place")
    status = "submitted" if response.get("ok") else "failed"
    record = {"id": client_order_id, "order_id": client_order_id, "time": now_iso(), "status": status, "dry_run": False, "real_order_created": bool(response.get("ok")), "symbol": symbol, "side": side, "quote_order_qty": quote_order_qty, "safety": safety, "payload_snapshot": safety.get("payload_snapshot"), "confirmation": token_result, "binance_response": response, "pre_balance_snapshot_id": pre_snapshot.get("snapshot_id"), "post_balance_snapshot_id": post_snapshot.get("snapshot_id")}
    append_real_order(state, record)
    if response.get("ok"):
        position = create_position_from_order_record(state, record, response=response, user=user)
        record["position_id"] = position.get("position_id")
    else:
        detect_orphan_orders(state, create_markers=False)
    append_audit(data, "real_order.place", "ok" if response.get("ok") else "error", "Gerçek emir denemesi kaydedildi.", meta={**_audit_meta_for_order("/api/real/orders/place", record, safety, role=role), "binance_response": response, "position_id": record.get("position_id")}, user=user)
    return record


def reconcile_real_positions(data: dict, settings: dict) -> dict:
    ensure_position_lifecycles(data)
    balances = read_real_balances()
    report = build_balance_reconciliation_full_report(data, settings, balances_payload=balances)
    report["balances"] = balances
    state = ensure_real_trade_state(data)
    state["last_reconciliation"] = report
    rec = report.get("reconciliation", {})
    append_audit(data, "real_balance.reconcile", report.get("status", "review"), "Real balance/PnL reconciliation tamamlandı.", meta={"category": "trading", "severity": "critical" if report.get("status") == "blocked" else "warning", "issues": rec.get("issues", []), "warnings": rec.get("warnings", []), "real_trade_locked_by_reconciliation": rec.get("real_trade_locked_by_reconciliation")}, user=data.get("username") or "system")
    return report


def capture_real_balance_snapshot(data: dict, phase: str, order: dict | None = None, balances_payload: dict | None = None, reason: str = "manual_balance_snapshot") -> dict:
    state = ensure_real_trade_state(data)
    balances = balances_payload if balances_payload is not None else read_real_balances()
    snapshot = capture_balance_snapshot(state, balances, phase=phase, order=order or {}, reason=reason)
    append_audit(data, "real_balance.snapshot", "ok" if snapshot.get("wallet", {}).get("balances_readable") else "review", "Real balance snapshot kaydedildi.", meta={"category": "trading", "severity": "notice", "phase": phase, "snapshot_id": snapshot.get("snapshot_id"), "order_id": snapshot.get("order_id")}, user=data.get("username") or "system")
    return {"status": "ok", "snapshot": snapshot}


def build_real_pnl(data: dict, settings: dict | None = None, price_map: dict | None = None) -> dict:
    report = build_real_pnl_report(data, price_map=price_map)
    append_audit(data, "real_pnl.calculate", report.get("status", "ok"), "Real PnL raporu hesaplandı.", meta={"category": "trading", "severity": "notice", "total_pnl_usdt": report.get("total_pnl_usdt")}, user=data.get("username") or "system")
    return report


def build_manual_reconciliation(data: dict, settings: dict | None = None) -> dict:
    balances = read_real_balances()
    report = build_manual_reconciliation_report(data, balances)
    append_audit(data, "real_balance.manual_reconciliation", report.get("status", "review"), "Manual reconciliation raporu üretildi.", meta={"category": "trading", "severity": "critical" if report.get("status") == "blocked" else "warning", "reconciliation_required": report.get("reconciliation_required")}, user=data.get("username") or "system")
    return report


def build_real_wallet_integrity(data: dict, settings: dict | None = None) -> dict:
    balances = read_real_balances()
    state = ensure_real_trade_state(data)
    report = build_real_wallet_integrity_report(data, balances)
    state["last_wallet_integrity"] = report
    return report


def build_real_money_separation(data: dict, settings: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    balances = state.get("last_balance_reconciliation", {}).get("wallet", {})
    return build_money_separation_report(data, settings or {}, balances)


def emergency_close_preview(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    preview = build_emergency_close_lifecycle_preview(data)
    state["last_emergency_close_preview"] = preview
    return preview


def build_real_lifecycle(data: dict, settings: dict | None = None) -> dict:
    return build_real_position_lifecycle_report(data)


def build_real_position_timeline(data: dict, position_id: str) -> dict:
    state = ensure_real_trade_state(data)
    return build_position_timeline(state, position_id)


def detect_real_position_orphans(data: dict, create_markers: bool = False) -> dict:
    state = ensure_real_trade_state(data)
    return detect_orphan_orders(state, create_markers=create_markers)


def transition_real_position(data: dict, position_id: str, to_status: str, reason: str = "manual_transition", meta: dict | None = None, user: str = "system") -> dict:
    state = ensure_real_trade_state(data)
    result = transition_position(state, position_id, to_status, reason=reason, meta=meta or {}, actor=user)
    append_audit(data, "real_position.transition", result.get("status", "review"), "Real position lifecycle transition denemesi.", meta={"category": "trading", "severity": "warning" if result.get("status") == "ok" else "blocked", "position_id": position_id, "to_status": to_status, "result": result}, user=user)
    return result


def owner_unlock(data: dict, user: str, minutes: int = 30) -> dict:
    state = ensure_real_trade_state(data)
    unlock_real_trading(state, user, minutes)
    append_audit(data, "real_trading.owner_unlock", "ok", "Real trading owner unlock süresi başlatıldı.", meta={"category": "security", "severity": "critical", "endpoint": "/api/real/unlock", "minutes": minutes, "role": "owner"}, user=user)
    return {"status": "ok", "owner_unlocked": True, "unlock_expires_at": state.get("unlock_expires_at"), "minutes": minutes}


def owner_lock(data: dict, user: str, reason: str = "manual_lock") -> dict:
    state = ensure_real_trade_state(data)
    lock_real_trading(state, reason)
    append_audit(data, "real_trading.owner_lock", "ok", "Real trading owner kilidi kapatıldı.", meta={"category": "security", "severity": "critical", "endpoint": "/api/real/lock", "reason": reason, "role": "owner"}, user=user)
    return {"status": "ok", "owner_unlocked": False, "reason": reason}
