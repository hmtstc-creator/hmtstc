from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from core.storage import append_audit, now_iso
from services.binance_service import load_binance_runtime_config
from services.real_trade_state_service import ensure_real_trade_state, lock_real_trading, open_real_positions
from services.real_trade_service import build_real_readiness, read_real_balances


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    return bool(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, default)).replace(",", "."))
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(str(os.getenv(name, default)).replace(",", ".")))
    except Exception:
        return int(default)


def _symbols(name: str, default: str = "BTCUSDT,ETHUSDT") -> list[str]:
    return [x.strip().upper() for x in str(os.getenv(name, default) or "").split(",") if x.strip()]


def pilot_config() -> dict:
    runtime = load_binance_runtime_config()
    max_order = min(_env_float("REAL_PILOT_MAX_ORDER_USDT", 5), float(runtime.max_order_usdt or 5))
    max_open = min(_env_int("REAL_PILOT_MAX_OPEN_POSITIONS", 1), int(runtime.max_open_positions or 1))
    return {
        "enabled": _env_bool("REAL_PILOT_ENABLED", False),
        "max_order_usdt": max(1, max_order),
        "max_open_positions": max(1, max_open),
        "max_daily_trades": max(1, _env_int("REAL_PILOT_MAX_DAILY_TRADES", 3)),
        "daily_loss_limit_usdt": max(0.1, _env_float("REAL_PILOT_DAILY_LOSS_LIMIT_USDT", 2)),
        "duration_minutes": max(5, min(_env_int("REAL_PILOT_DURATION_MINUTES", 60), 240)),
        "allowed_symbols": _symbols("REAL_PILOT_ALLOWED_SYMBOLS"),
        "require_approval": _env_bool("REAL_PILOT_REQUIRE_APPROVAL", True),
        "auto_lock_after_finish": True,
        "runtime_max_order_usdt": runtime.max_order_usdt,
        "runtime_max_open_positions": runtime.max_open_positions,
        "dry_run": runtime.real_trading_dry_run,
        "env_real_trading_enabled": runtime.real_trading_enabled,
    }


def _parse_dt(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None




def _append_pilot_event(data: dict, event: str, status: str, message: str, meta: dict | None = None, user: str | None = None) -> dict:
    state = ensure_real_trade_state(data)
    pilot = state.setdefault("pilot", {})
    item = {
        "event_id": f"pilot_evt_{uuid4().hex[:12]}",
        "event": event,
        "status": status,
        "message": message,
        "at": now_iso(),
        "user": user,
        "meta": meta or {},
    }
    pilot.setdefault("evidence_chain", []).append(item)
    pilot["evidence_chain"] = pilot["evidence_chain"][-200:]
    append_audit(
        data,
        event,
        status,
        message,
        meta={"category": "trading", "severity": "critical" if status in {"ok", "blocked"} else "warning", **(meta or {})},
        user=user or "system",
    )
    return item


def _build_final_report(data: dict, settings: dict, reason: str, user: str | None = None) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    orders = state.get("orders", []) or []
    positions = state.get("positions", []) or []
    started = _parse_dt(pilot.get("started_at"))
    def after_start(row: dict) -> bool:
        if not started:
            return True
        dt = _parse_dt(row.get("time") or row.get("created_at") or row.get("submitted_at") or row.get("updated_at"))
        return bool(dt and dt >= started)
    pilot_orders = [o for o in orders if isinstance(o, dict) and after_start(o)]
    pilot_positions = [p for p in positions if isinstance(p, dict) and after_start(p)]
    report = {
        "report_id": f"pilot_report_{uuid4().hex[:12]}",
        "status": "final",
        "reason": reason,
        "pilot_id": pilot.get("pilot_id"),
        "started_at": pilot.get("started_at"),
        "stopped_at": now_iso(),
        "expires_at": pilot.get("expires_at"),
        "orders_total": len(pilot_orders),
        "orders_blocked": len([o for o in pilot_orders if str(o.get("status")) == "blocked"]),
        "orders_dry_run_ready": len([o for o in pilot_orders if str(o.get("status")) == "dry_run_ready"]),
        "positions_total": len(pilot_positions),
        "open_positions": len(open_real_positions(state)),
        "daily_loss": float(pilot.get("daily_loss") or 0),
        "orders_count": int(pilot.get("orders_count") or 0),
        "max_order_usdt": pilot.get("max_order_usdt"),
        "max_open_positions": pilot.get("max_open_positions"),
        "max_daily_trades": pilot.get("max_daily_trades"),
        "daily_loss_limit_usdt": pilot.get("daily_loss_limit_usdt"),
        "locked_after_finish": True,
        "manual_attention_required": bool(state.get("manual_attention_required")),
        "generated_by": user or "system",
        "generated_at": now_iso(),
    }
    pilot["final_report"] = report
    pilot["last_report"] = report
    return report

def ensure_pilot_state(data: dict) -> dict:
    state = ensure_real_trade_state(data)
    pilot = state.setdefault("pilot", {})
    cfg = pilot_config()
    defaults = {
        "active": False,
        "started_at": None,
        "expires_at": None,
        "orders_count": 0,
        "daily_loss": 0,
        "locked_after_finish": True,
        "allowed_symbols": cfg["allowed_symbols"],
        "max_order_usdt": cfg["max_order_usdt"],
        "max_open_positions": cfg["max_open_positions"],
        "max_daily_trades": cfg["max_daily_trades"],
        "daily_loss_limit_usdt": cfg["daily_loss_limit_usdt"],
        "duration_minutes": cfg["duration_minutes"],
        "status": "off",
        "pilot_id": None,
        "phase": "idle",
        "started_by": None,
        "stopped_at": None,
        "stopped_by": None,
        "stop_reason": None,
        "evidence_chain": [],
        "final_report": None,
        "last_report": None,
    }
    for key, value in defaults.items():
        pilot.setdefault(key, value)
    expires = _parse_dt(pilot.get("expires_at"))
    if pilot.get("active") and expires and datetime.now() >= expires:
        pilot["active"] = False
        pilot["status"] = "expired_auto_locked"
        pilot["phase"] = "expired"
        pilot["stopped_at"] = now_iso()
        pilot["stop_reason"] = "expired"
        lock_real_trading(state, "pilot_expired_auto_lock")
        _append_pilot_event(data, "real_pilot.expired_auto_lock", "ok", "Mikro pilot süre dolduğu için otomatik kilitlendi.", {"expires_at": pilot.get("expires_at")}, user="system")
    return pilot


def _pilot_balance_snapshot() -> dict:
    if str(os.getenv("HMTSTC_OFFLINE_QUALITY_CHECK", "")).lower() in {"1", "true", "yes"}:
        return {"status": "offline_check", "balances_readable": False, "offline_quality_check": True}
    return read_real_balances()


def pilot_readiness(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    cfg = pilot_config()
    readiness = build_real_readiness(data, settings)
    if str(os.getenv("HMTSTC_OFFLINE_QUALITY_CHECK", "")).lower() in {"1", "true", "yes"}:
        readiness = {**(readiness or {}), "status": "offline_ready", "ready_for_dry_run": True, "ready_for_real_order": False}
    balances = _pilot_balance_snapshot()
    blockers: list[str] = []
    warnings: list[str] = []

    if not cfg["enabled"]:
        blockers.append("pilot_env_disabled")
    if not readiness.get("ready_for_dry_run"):
        blockers.append("binance_dry_run_not_ready")
    if not state.get("owner_unlocked"):
        blockers.append("owner_unlock_missing")
    if state.get("emergency_lock") or data.get("emergency_lock"):
        blockers.append("emergency_lock_active")
    if state.get("manual_attention_required"):
        blockers.append("manual_attention_required")
    if state.get("real_trade_locked_by_reconciliation"):
        blockers.append("balance_reconciliation_lock_active")
    if len(open_real_positions(state)) >= cfg["max_open_positions"]:
        blockers.append("pilot_max_open_positions_reached")
    if int(pilot.get("orders_count") or 0) >= cfg["max_daily_trades"]:
        blockers.append("pilot_max_daily_trades_reached")
    if float(pilot.get("daily_loss") or 0) <= -abs(cfg["daily_loss_limit_usdt"]):
        blockers.append("pilot_daily_loss_limit_reached")
    if not cfg["allowed_symbols"]:
        warnings.append("pilot_allowed_symbols_empty")
    if balances.get("status") != "ok":
        warnings.append("balance_not_readable_for_pilot")

    status = "ready" if not blockers else "blocked"
    pilot_snapshot = {k: v for k, v in pilot.items() if k not in {"last_report", "final_report"}}
    return {
        "status": status,
        "pilot_active": bool(pilot.get("active")),
        "config": cfg,
        "pilot": pilot_snapshot,
        "readiness_status": readiness.get("status"),
        "ready_for_dry_run": bool(readiness.get("ready_for_dry_run")),
        "ready_for_real_order": bool(readiness.get("ready_for_real_order")),
        "open_positions": len(open_real_positions(state)),
        "orders_count": int(pilot.get("orders_count") or 0),
        "daily_loss": float(pilot.get("daily_loss") or 0),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "checked_at": now_iso(),
    }


def start_pilot(data: dict, settings: dict, user: str, minutes: int | None = None) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    report = pilot_readiness(data, settings)
    if report.get("blockers"):
        _append_pilot_event(data, "real_pilot.start", "blocked", "Mikro pilot başlatma safety tarafından engellendi.", {"endpoint": "/api/real/pilot/start", "blockers": report.get("blockers")}, user=user)
        return {"status": "blocked", "blockers": report.get("blockers"), "readiness": report}
    cfg = report["config"]
    duration = max(5, min(int(minutes or cfg["duration_minutes"]), 240))
    now = datetime.now()
    pilot_id = f"pilot_{uuid4().hex[:12]}"
    pilot.update({
        "active": True,
        "status": "active",
        "phase": "running",
        "pilot_id": pilot_id,
        "started_by": user,
        "started_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(minutes=duration)).isoformat(timespec="seconds"),
        "orders_count": 0,
        "daily_loss": 0,
        "max_order_usdt": cfg["max_order_usdt"],
        "max_open_positions": cfg["max_open_positions"],
        "max_daily_trades": cfg["max_daily_trades"],
        "daily_loss_limit_usdt": cfg["daily_loss_limit_usdt"],
        "allowed_symbols": cfg["allowed_symbols"],
        "duration_minutes": duration,
        "locked_after_finish": True,
        "stopped_at": None,
        "stopped_by": None,
        "stop_reason": None,
        "final_report": None,
    })
    _append_pilot_event(data, "real_pilot.start", "ok", "Mikro pilot başlatıldı.", {"endpoint": "/api/real/pilot/start", "pilot_id": pilot_id, "after": pilot}, user=user)
    return {"status": "ok", "pilot": pilot, "readiness": pilot_readiness(data, settings)}


def stop_pilot(data: dict, user: str, reason: str = "manual_stop", settings: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    before = dict(pilot)
    pilot["active"] = False
    pilot["status"] = f"stopped_{reason}"
    pilot["phase"] = "finished" if reason in {"manual_stop", "finalize"} else str(reason or "stopped")
    pilot["stopped_at"] = now_iso()
    pilot["stopped_by"] = user
    pilot["stop_reason"] = reason
    report = _build_final_report(data, settings or {}, reason=reason, user=user)
    lock_real_trading(state, f"pilot_{reason}_auto_lock")
    _append_pilot_event(data, "real_pilot.stop", "ok", "Mikro pilot durduruldu, final rapor üretildi ve real trading kilitlendi.", {"endpoint": "/api/real/pilot/stop", "before": before, "after": pilot, "final_report_id": report.get("report_id")}, user=user)
    return {"status": "ok", "pilot": pilot, "lock_reason": state.get("lock_reason"), "final_report": report}


def build_pilot_report(data: dict, settings: dict) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    orders = state.get("orders", []) or []
    pilot_started = _parse_dt(pilot.get("started_at"))
    pilot_orders = []
    if pilot_started:
        for order in orders:
            dt = _parse_dt(order.get("time") or order.get("created_at"))
            if dt and dt >= pilot_started:
                pilot_orders.append(order)
    else:
        pilot_orders = orders[-20:]
    blocked = [o for o in pilot_orders if str(o.get("status")) == "blocked"]
    dry_ready = [o for o in pilot_orders if str(o.get("status")) == "dry_run_ready"]
    pilot_snapshot = {k: v for k, v in pilot.items() if k not in {"last_report", "final_report"}}
    report = {
        "status": "active" if pilot.get("active") else "inactive",
        "pilot": pilot_snapshot,
        "orders_total": len(pilot_orders),
        "orders_blocked": len(blocked),
        "orders_dry_run_ready": len(dry_ready),
        "open_positions": len(open_real_positions(state)),
        "daily_loss": float(pilot.get("daily_loss") or 0),
        "readiness": pilot_readiness(data, settings),
        "last_orders": pilot_orders[-20:],
        "generated_at": now_iso(),
    }
    pilot["last_report"] = report
    return report



def build_pilot_visibility(data: dict, settings: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    readiness = pilot_readiness(data, settings or {})
    expires = _parse_dt(pilot.get("expires_at"))
    seconds_left = None
    if expires:
        seconds_left = max(0, int((expires - datetime.now()).total_seconds()))
    return {
        "status": "active" if pilot.get("active") else str(pilot.get("status") or "inactive"),
        "active": bool(pilot.get("active")),
        "phase": pilot.get("phase") or "idle",
        "pilot_id": pilot.get("pilot_id"),
        "started_at": pilot.get("started_at"),
        "expires_at": pilot.get("expires_at"),
        "seconds_left": seconds_left,
        "orders_count": int(pilot.get("orders_count") or 0),
        "max_daily_trades": int(pilot.get("max_daily_trades") or 0),
        "daily_loss": float(pilot.get("daily_loss") or 0),
        "daily_loss_limit_usdt": float(pilot.get("daily_loss_limit_usdt") or 0),
        "max_order_usdt": pilot.get("max_order_usdt"),
        "max_open_positions": pilot.get("max_open_positions"),
        "open_positions": len(open_real_positions(state)),
        "auto_lock_after_finish": True,
        "locked_after_finish": bool(pilot.get("locked_after_finish", True)),
        "manual_attention_required": bool(state.get("manual_attention_required")),
        "readiness_status": readiness.get("status"),
        "blockers": readiness.get("blockers") or [],
        "warnings": readiness.get("warnings") or [],
        "last_report": pilot.get("final_report") or pilot.get("last_report"),
        "evidence_count": len(pilot.get("evidence_chain") or []),
        "last_evidence": (pilot.get("evidence_chain") or [])[-5:],
        "checked_at": now_iso(),
    }


def validate_pilot_order_guard(data: dict, payload: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    payload = payload or {}
    blockers: list[str] = []
    symbol = str(payload.get("symbol") or "").upper().strip()
    quote = 0.0
    try:
        quote = float(str(payload.get("quote_order_qty") or payload.get("quoteOrderQty") or 0).replace(",", "."))
    except Exception:
        quote = 0.0
    if not pilot.get("active"):
        blockers.append("pilot_not_active")
    if symbol and pilot.get("allowed_symbols") and symbol not in pilot.get("allowed_symbols", []):
        blockers.append("pilot_symbol_not_allowed")
    if quote and quote > float(pilot.get("max_order_usdt") or 0):
        blockers.append("pilot_max_order_usdt_exceeded")
    if len(open_real_positions(state)) >= int(pilot.get("max_open_positions") or 1):
        blockers.append("pilot_max_open_positions_reached")
    if int(pilot.get("orders_count") or 0) >= int(pilot.get("max_daily_trades") or 1):
        blockers.append("pilot_max_daily_trades_reached")
    if float(pilot.get("daily_loss") or 0) <= -abs(float(pilot.get("daily_loss_limit_usdt") or 0)):
        blockers.append("pilot_daily_loss_limit_reached")
    pilot_snapshot = {k: v for k, v in pilot.items() if k not in {"last_report", "final_report"}}
    return {"status": "ok" if not blockers else "blocked", "blockers": blockers, "pilot": pilot_snapshot, "checked_at": now_iso()}


def record_pilot_order_attempt(data: dict, payload: dict | None = None, status: str = "attempt", user: str | None = None) -> dict:
    state = ensure_real_trade_state(data)
    pilot = ensure_pilot_state(data)
    guard = validate_pilot_order_guard(data, payload)
    if guard.get("status") == "ok" and status in {"dry_run_ready", "submitted", "filled", "ok"}:
        pilot["orders_count"] = int(pilot.get("orders_count") or 0) + 1
    event = _append_pilot_event(data, "real_pilot.order_attempt", guard.get("status", status), "Pilot order guard değerlendirildi.", {"payload": payload or {}, "guard": guard, "attempt_status": status}, user=user)
    return {"status": guard.get("status"), "event": event, "guard": guard, "orders_count": pilot.get("orders_count")}


def finalize_pilot_controller(data: dict, settings: dict | None = None, user: str = "system", reason: str = "finalize") -> dict:
    return stop_pilot(data, user=user, reason=reason, settings=settings or {})
