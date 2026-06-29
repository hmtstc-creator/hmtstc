from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from core.storage import now_iso
from services.real_trade_state_service import ensure_real_trade_state, lock_real_trading
from services.real_position_lifecycle_service import OPEN_LIFECYCLE_STATUSES, ensure_position_lifecycles

DUST_USDT_ESTIMATE = 1.0
BALANCE_TOLERANCE = 1e-8
PNL_TOLERANCE = 1e-9


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(str(value).replace(",", "."))
    except Exception:
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _asset_from_symbol(symbol: str) -> str:
    symbol = str(symbol or "").upper().strip()
    if symbol.endswith("USDT"):
        return symbol[:-4]
    return symbol


def _quote_asset(symbol: str) -> str:
    symbol = str(symbol or "").upper().strip()
    if symbol.endswith("USDT"):
        return "USDT"
    return ""


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _date_key(value: Any | None = None) -> str:
    dt = _parse_dt(value) or datetime.now()
    return dt.date().isoformat()


def _week_key(value: Any | None = None) -> str:
    dt = _parse_dt(value) or datetime.now()
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def normalize_balance_rows(balances_payload: dict | None) -> list[dict]:
    if not isinstance(balances_payload, dict):
        return []
    raw_rows = balances_payload.get("balances") or balances_payload.get("assets") or []
    if not isinstance(raw_rows, list):
        return []
    rows = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        asset = str(row.get("asset") or row.get("symbol") or "").upper().strip()
        if not asset:
            continue
        free = _safe_float(row.get("free"), 0.0)
        locked = _safe_float(row.get("locked"), 0.0)
        total = _safe_float(row.get("total"), free + locked)
        if total <= BALANCE_TOLERANCE and free <= BALANCE_TOLERANCE and locked <= BALANCE_TOLERANCE:
            continue
        rows.append({"asset": asset, "free": free, "locked": locked, "total": total})
    return rows


def build_real_wallet_snapshot(balances_payload: dict | None) -> dict:
    readable = bool(isinstance(balances_payload, dict) and balances_payload.get("balances_readable"))
    rows = normalize_balance_rows(balances_payload)
    usdt = next((row for row in rows if row.get("asset") == "USDT"), {"asset": "USDT", "free": 0.0, "locked": 0.0, "total": 0.0})
    non_usdt = [row for row in rows if row.get("asset") != "USDT"]
    return {
        "status": "ok" if readable else "blocked",
        "balances_readable": readable,
        "snapshot_at": now_iso(),
        "usdt": usdt,
        "assets_count": len(rows),
        "non_usdt_assets_count": len(non_usdt),
        "non_usdt_assets": non_usdt,
        "dust_threshold_usdt_estimate": DUST_USDT_ESTIMATE,
        "note": "Real wallet snapshot sadece Binance spot balance verisidir; Paper Lab wallet ile karıştırılmaz.",
    }


def ensure_reconciliation_state(state: dict) -> dict:
    state.setdefault("balance_snapshots", [])
    if not isinstance(state.get("balance_snapshots"), list):
        state["balance_snapshots"] = []
    state.setdefault("balance_reconciliation_history", [])
    if not isinstance(state.get("balance_reconciliation_history"), list):
        state["balance_reconciliation_history"] = []
    state.setdefault("pnl_history", [])
    if not isinstance(state.get("pnl_history"), list):
        state["pnl_history"] = []
    state.setdefault("reconciliation_required", False)
    return state


def capture_balance_snapshot(state: dict, balances_payload: dict | None, phase: str, order: dict | None = None, reason: str = "balance_snapshot") -> dict:
    ensure_reconciliation_state(state)
    wallet = build_real_wallet_snapshot(balances_payload)
    order = order or {}
    snapshot = {
        "snapshot_id": f"bal_{uuid4().hex}",
        "phase": str(phase or "manual").strip().lower(),
        "reason": str(reason or "balance_snapshot"),
        "created_at": now_iso(),
        "order_id": order.get("id") or order.get("order_id") or order.get("client_order_id"),
        "preview_id": order.get("preview_id") or ((order.get("payload_snapshot") or {}).get("preview_id") if isinstance(order.get("payload_snapshot"), dict) else None),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "quote_order_qty": _safe_float(order.get("quote_order_qty") or order.get("quoteOrderQty"), 0.0),
        "wallet": wallet,
    }
    state.setdefault("balance_snapshots", []).append(snapshot)
    state["balance_snapshots"] = state["balance_snapshots"][-300:]
    state["last_balance_snapshot"] = snapshot
    if snapshot["phase"] == "pre_order":
        state["last_pre_order_balance_snapshot"] = snapshot
    if snapshot["phase"] == "post_order":
        state["last_post_order_balance_snapshot"] = snapshot
    return snapshot


def _open_positions_by_asset(data: dict) -> tuple[list[dict], Counter]:
    state = ensure_position_lifecycles(data)
    positions = []
    counter = Counter()
    for p in state.get("positions", []) or []:
        status = str(p.get("status") or "").lower()
        if status not in OPEN_LIFECYCLE_STATUSES:
            continue
        symbol = str(p.get("symbol") or "").upper()
        asset = _asset_from_symbol(symbol)
        positions.append(p)
        if asset:
            counter[asset] += 1
    return positions, counter


def compare_bot_exchange_state(data: dict, balances_payload: dict | None) -> dict:
    state = ensure_real_trade_state(data)
    ensure_reconciliation_state(state)
    open_positions, position_assets = _open_positions_by_asset(data)
    wallet = build_real_wallet_snapshot(balances_payload)
    asset_rows = {row["asset"]: row for row in wallet.get("non_usdt_assets", [])}
    issues: list[str] = []
    warnings: list[str] = []

    if not wallet.get("balances_readable"):
        issues.append("balance_not_readable")

    for asset, row in asset_rows.items():
        if row.get("total", 0.0) <= BALANCE_TOLERANCE:
            continue
        if asset not in position_assets:
            warnings.append(f"binance_asset_without_tracked_position:{asset}")

    for asset, count in position_assets.items():
        if asset == "USDT":
            continue
        row = asset_rows.get(asset)
        if not row or row.get("total", 0.0) <= BALANCE_TOLERANCE:
            issues.append(f"tracked_position_without_binance_asset:{asset}")

    status = "ok"
    if issues:
        status = "blocked"
    elif warnings:
        status = "review"

    return {
        "status": status,
        "checked_at": now_iso(),
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "wallet": wallet,
        "open_positions_count": len(open_positions),
        "tracked_assets": dict(position_assets),
        "binance_assets": list(asset_rows.keys()),
        "manual_attention_required": status != "ok",
        "real_trade_locked_by_reconciliation": status in {"blocked", "review"},
    }


def apply_mismatch_lock(data: dict, compare_report: dict) -> dict:
    state = ensure_real_trade_state(data)
    ensure_reconciliation_state(state)
    status = str((compare_report or {}).get("status") or "review").lower()
    blockers = list((compare_report or {}).get("issues") or [])
    warnings = list((compare_report or {}).get("warnings") or [])
    locked = status in {"blocked", "review"}
    if locked:
        reason = blockers[0] if blockers else (warnings[0] if warnings else "reconciliation_review_required")
        lock_real_trading(state, f"reconciliation:{reason}")
        state["manual_attention_required"] = True
        state["reconciliation_required"] = True
        state["real_trade_locked_by_reconciliation"] = True
        state["reconciliation_lock_reason"] = reason
    else:
        state["real_trade_locked_by_reconciliation"] = False
        state["reconciliation_lock_reason"] = None
        state["reconciliation_required"] = False
    return {
        "locked": locked,
        "reason": state.get("reconciliation_lock_reason"),
        "owner_unlocked": bool(state.get("owner_unlocked")),
        "manual_attention_required": bool(state.get("manual_attention_required")),
        "reconciliation_required": bool(state.get("reconciliation_required")),
    }


def _position_entry_value(position: dict) -> float:
    return _safe_float(position.get("entry_value_usdt") or position.get("quote_order_qty") or position.get("usdt_size") or position.get("notional"), 0.0)


def _position_exit_value(position: dict) -> float:
    return _safe_float(position.get("exit_value_usdt") or position.get("close_value_usdt") or position.get("exit_notional"), 0.0)


def _position_commission(position: dict) -> float:
    return _safe_float(position.get("commission") or position.get("fee") or position.get("fees_usdt"), 0.0)


def _position_side(position: dict) -> str:
    return str(position.get("side") or "BUY").upper().strip()


def calculate_realized_pnl(data: dict) -> dict:
    state = ensure_position_lifecycles(data)
    closed = []
    for source in [state.get("position_history", []), state.get("positions", [])]:
        for position in source or []:
            if str(position.get("status") or "").lower() not in {"closed", "reconciled"}:
                continue
            entry_value = _position_entry_value(position)
            exit_value = _position_exit_value(position)
            commission = _position_commission(position)
            explicit = position.get("realized_pnl")
            if explicit not in {None, ""} and abs(_safe_float(explicit, 0.0)) > PNL_TOLERANCE:
                pnl = _safe_float(explicit, 0.0) - commission
            else:
                side = _position_side(position)
                pnl = (exit_value - entry_value - commission) if side == "BUY" else (entry_value - exit_value - commission)
            row = {
                "position_id": position.get("position_id"),
                "symbol": position.get("symbol"),
                "closed_at": position.get("closed_at") or position.get("updated_at"),
                "entry_value_usdt": round(entry_value, 8),
                "exit_value_usdt": round(exit_value, 8),
                "commission_usdt": round(commission, 8),
                "realized_pnl_usdt": round(pnl, 8),
            }
            closed.append(row)
    total = round(sum(row["realized_pnl_usdt"] for row in closed), 8)
    return {"status": "ok", "realized_pnl_usdt": total, "closed_positions_count": len(closed), "positions": closed[-100:]}


def calculate_unrealized_pnl(data: dict, price_map: dict | None = None) -> dict:
    state = ensure_position_lifecycles(data)
    price_map = {str(k).upper(): _safe_float(v, 0.0) for k, v in (price_map or {}).items()}
    rows = []
    missing_prices = []
    for position in state.get("positions", []) or []:
        status = str(position.get("status") or "").lower()
        if status not in OPEN_LIFECYCLE_STATUSES:
            continue
        symbol = str(position.get("symbol") or "").upper()
        entry_price = _safe_float(position.get("avg_fill_price") or position.get("entry_price") or position.get("price"), 0.0)
        quantity = _safe_float(position.get("quantity") or position.get("executed_qty"), 0.0)
        current = _safe_float(position.get("current_price") or position.get("mark_price") or price_map.get(symbol), 0.0)
        commission = _position_commission(position)
        if current <= 0 or quantity <= 0 or entry_price <= 0:
            explicit = _safe_float(position.get("unrealized_pnl"), 0.0)
            if abs(explicit) <= PNL_TOLERANCE:
                missing_prices.append(symbol or str(position.get("position_id")))
            pnl = explicit
        else:
            side = _position_side(position)
            pnl = ((current - entry_price) * quantity - commission) if side == "BUY" else ((entry_price - current) * quantity - commission)
        rows.append({
            "position_id": position.get("position_id"),
            "symbol": symbol,
            "status": status,
            "entry_price": round(entry_price, 8),
            "current_price": round(current, 8),
            "quantity": round(quantity, 8),
            "commission_usdt": round(commission, 8),
            "unrealized_pnl_usdt": round(pnl, 8),
        })
    total = round(sum(row["unrealized_pnl_usdt"] for row in rows), 8)
    return {"status": "review" if missing_prices else "ok", "unrealized_pnl_usdt": total, "open_positions_count": len(rows), "missing_prices": sorted(set(missing_prices)), "positions": rows[-100:]}


def calculate_commission_fee(data: dict) -> dict:
    state = ensure_position_lifecycles(data)
    by_asset = defaultdict(float)
    total_usdt = 0.0
    rows = []
    for position in list(state.get("positions", []) or []) + list(state.get("position_history", []) or []):
        commission = _position_commission(position)
        asset = str(position.get("commission_asset") or "USDT").upper() or "USDT"
        by_asset[asset] += commission
        if asset == "USDT":
            total_usdt += commission
        rows.append({"position_id": position.get("position_id"), "symbol": position.get("symbol"), "commission": round(commission, 8), "asset": asset})
    for order in state.get("orders", []) or []:
        commission = _safe_float(order.get("commission") or order.get("fee") or order.get("fees_usdt"), 0.0)
        if commission <= 0:
            continue
        asset = str(order.get("commission_asset") or "USDT").upper() or "USDT"
        by_asset[asset] += commission
        if asset == "USDT":
            total_usdt += commission
        rows.append({"order_id": order.get("id") or order.get("order_id"), "symbol": order.get("symbol"), "commission": round(commission, 8), "asset": asset})
    return {"status": "ok", "commission_usdt": round(total_usdt, 8), "by_asset": {k: round(v, 8) for k, v in sorted(by_asset.items())}, "rows": rows[-200:]}


def build_daily_weekly_pnl(data: dict) -> dict:
    realized = calculate_realized_pnl(data)
    state = ensure_position_lifecycles(data)
    daily = defaultdict(float)
    weekly = defaultdict(float)
    for row in realized.get("positions", []) or []:
        key = row.get("closed_at")
        pnl = _safe_float(row.get("realized_pnl_usdt"), 0.0)
        daily[_date_key(key)] += pnl
        weekly[_week_key(key)] += pnl
    today = _date_key()
    this_week = _week_key()
    report = {
        "status": "ok",
        "daily_pnl": {k: round(v, 8) for k, v in sorted(daily.items())},
        "weekly_pnl": {k: round(v, 8) for k, v in sorted(weekly.items())},
        "today_pnl_usdt": round(daily.get(today, 0.0), 8),
        "this_week_pnl_usdt": round(weekly.get(this_week, 0.0), 8),
        "today": today,
        "this_week": this_week,
    }
    state["daily_pnl"] = report["today_pnl_usdt"]
    state["weekly_pnl"] = report["this_week_pnl_usdt"]
    return report


def build_manual_reconciliation_report(data: dict, balances_payload: dict | None = None) -> dict:
    compare = compare_bot_exchange_state(data, balances_payload)
    lock = apply_mismatch_lock(data, compare)
    state = ensure_real_trade_state(data)
    instructions = []
    if compare.get("issues"):
        instructions.append("Borsa bakiyesi ile bot pozisyon state'i uyuşmuyor; real trading kilitli kalmalı.")
    if compare.get("warnings"):
        instructions.append("Borsada bot tarafından takip edilmeyen asset görünüyor; manuel doğrulama gerekli.")
    if not instructions:
        instructions.append("Reconciliation temiz; yine de canlı emir öncesi owner readiness kontrolü yapılmalı.")
    report = {
        "status": compare.get("status"),
        "created_at": now_iso(),
        "compare": compare,
        "lock": lock,
        "manual_attention_required": bool(lock.get("manual_attention_required")),
        "reconciliation_required": bool(lock.get("reconciliation_required")),
        "instructions": instructions,
        "separation": {
            "paper_wallet_is_separate": True,
            "real_wallet_is_binance_spot": True,
            "paper_reset_must_not_touch_real_balances": True,
        },
    }
    state["last_manual_reconciliation_report"] = report
    return report


def build_balance_reconciliation_report(data: dict, balances_payload: dict | None) -> dict:
    state = ensure_real_trade_state(data)
    ensure_reconciliation_state(state)
    compare = compare_bot_exchange_state(data, balances_payload)
    lock = apply_mismatch_lock(data, compare)
    report = {
        "status": compare.get("status"),
        "checked_at": now_iso(),
        "issues": compare.get("issues", []),
        "warnings": compare.get("warnings", []),
        "manual_attention_required": bool(lock.get("manual_attention_required")),
        "real_trade_locked_by_reconciliation": bool(lock.get("locked")),
        "reconciliation_required": bool(lock.get("reconciliation_required")),
        "lock_reason": lock.get("reason"),
        "wallet": compare.get("wallet"),
        "open_positions_count": compare.get("open_positions_count", 0),
        "tracked_assets": compare.get("tracked_assets", {}),
        "binance_assets": compare.get("binance_assets", []),
        "separation": {
            "paper_wallet_is_separate": True,
            "real_wallet_is_binance_spot": True,
            "paper_reset_must_not_touch_real_balances": True,
        },
    }
    state["last_balance_reconciliation"] = report
    state.setdefault("balance_reconciliation_history", []).append(report)
    state["balance_reconciliation_history"] = state["balance_reconciliation_history"][-100:]
    return report


def build_real_pnl_report(data: dict, price_map: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    ensure_reconciliation_state(state)
    realized = calculate_realized_pnl(data)
    unrealized = calculate_unrealized_pnl(data, price_map=price_map)
    fees = calculate_commission_fee(data)
    periods = build_daily_weekly_pnl(data)
    total = round(_safe_float(realized.get("realized_pnl_usdt"), 0.0) + _safe_float(unrealized.get("unrealized_pnl_usdt"), 0.0), 8)
    report = {
        "status": "review" if unrealized.get("status") == "review" else "ok",
        "calculated_at": now_iso(),
        "realized": realized,
        "unrealized": unrealized,
        "fees": fees,
        "periods": periods,
        "total_pnl_usdt": total,
    }
    state["last_real_pnl_report"] = report
    state.setdefault("pnl_history", []).append(report)
    state["pnl_history"] = state["pnl_history"][-300:]
    state["realized_pnl"] = realized.get("realized_pnl_usdt", 0.0)
    state["unrealized_pnl"] = unrealized.get("unrealized_pnl_usdt", 0.0)
    state["total_pnl"] = total
    return report


def build_reconciliation_dashboard_summary(data: dict, balances_payload: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    last = state.get("last_balance_reconciliation")
    if not last:
        last = build_balance_reconciliation_report(data, balances_payload or {"balances_readable": False, "balances": []})
    pnl = state.get("last_real_pnl_report") or build_real_pnl_report(data)
    return {
        "status": last.get("status", "not_run"),
        "checked_at": last.get("checked_at"),
        "issues_count": len(last.get("issues") or []),
        "warnings_count": len(last.get("warnings") or []),
        "manual_attention_required": bool(last.get("manual_attention_required")),
        "real_trade_locked_by_reconciliation": bool(last.get("real_trade_locked_by_reconciliation")),
        "reconciliation_required": bool(last.get("reconciliation_required")),
        "lock_reason": last.get("lock_reason"),
        "realized_pnl_usdt": ((pnl.get("realized") or {}).get("realized_pnl_usdt")),
        "unrealized_pnl_usdt": ((pnl.get("unrealized") or {}).get("unrealized_pnl_usdt")),
        "total_pnl_usdt": pnl.get("total_pnl_usdt"),
        "today_pnl_usdt": ((pnl.get("periods") or {}).get("today_pnl_usdt")),
        "this_week_pnl_usdt": ((pnl.get("periods") or {}).get("this_week_pnl_usdt")),
    }


def build_balance_reconciliation_full_report(data: dict, settings: dict | None = None, balances_payload: dict | None = None, price_map: dict | None = None) -> dict:
    balances_payload = balances_payload if balances_payload is not None else {"balances_readable": False, "balances": []}
    state = ensure_real_trade_state(data)
    ensure_reconciliation_state(state)
    reconciliation = build_balance_reconciliation_report(data, balances_payload)
    manual = build_manual_reconciliation_report(data, balances_payload)
    pnl = build_real_pnl_report(data, price_map=price_map)
    summary = build_reconciliation_dashboard_summary(data, balances_payload)
    report = {
        "status": "blocked" if reconciliation.get("status") == "blocked" else ("review" if reconciliation.get("status") == "review" or pnl.get("status") == "review" else "ok"),
        "generated_at": now_iso(),
        "reconciliation": reconciliation,
        "manual_report": manual,
        "pnl": pnl,
        "summary": summary,
        "snapshots_count": len(state.get("balance_snapshots") or []),
    }
    state["last_balance_pnl_reconciliation_report"] = report
    return report


def build_money_separation_report(data: dict, settings: dict | None = None, balances_payload: dict | None = None) -> dict:
    state = ensure_real_trade_state(data)
    paper_models = ((data.get("paper_lab") or {}).get("models") or []) if isinstance(data.get("paper_lab"), dict) else []
    paper_positions = data.get("positions", []) if isinstance(data.get("positions"), list) else []
    wallet = build_real_wallet_snapshot(balances_payload or (state.get("last_balance_reconciliation") or {}).get("wallet", {}))
    return {
        "status": "ok",
        "paper_lab": {
            "models_count": len(paper_models),
            "open_positions_count": len(paper_positions),
            "virtual_wallet_default_usdt": 1000,
            "is_virtual": True,
        },
        "real_wallet": {
            "balances_readable": wallet.get("balances_readable"),
            "usdt_total": (wallet.get("usdt") or {}).get("total", 0.0),
            "assets_count": wallet.get("assets_count", 0),
            "is_binance_spot": True,
        },
        "rules": [
            "Paper Lab PnL gerçek para değildir.",
            "Real Wallet sadece Binance spot balance üzerinden okunur.",
            "Paper reset real wallet/order/position state'i silmemelidir.",
            "Real approval gerçek trade açmaz.",
        ],
    }


def build_real_wallet_integrity_report(data: dict, balances_payload: dict | None) -> dict:
    state = ensure_real_trade_state(data)
    wallet = build_real_wallet_snapshot(balances_payload)
    reconciliation = state.get("last_balance_reconciliation") or {}
    pnl = state.get("last_real_pnl_report") or {}
    checks = {
        "balance_readable": "ok" if wallet.get("balances_readable") else "blocked",
        "usdt_present": "ok" if wallet.get("usdt") is not None else "review",
        "paper_real_separated": "ok",
        "reconciliation_recent": "ok" if reconciliation.get("checked_at") else "review",
        "mismatch_lock_ready": "ok" if "real_trade_locked_by_reconciliation" in state else "review",
        "pnl_report_ready": "ok" if pnl.get("calculated_at") else "review",
    }
    ok_count = sum(1 for value in checks.values() if value == "ok")
    return {
        "status": "ok" if ok_count >= 4 and checks["balance_readable"] != "blocked" else "review",
        "integrity_score": round(ok_count / len(checks) * 100, 2),
        "checks": checks,
        "wallet": wallet,
        "last_reconciliation_status": reconciliation.get("status", "not_run"),
        "real_trade_locked_by_reconciliation": bool(state.get("real_trade_locked_by_reconciliation")),
        "realized_pnl": ((pnl.get("realized") or {}).get("realized_pnl_usdt")),
        "unrealized_pnl": ((pnl.get("unrealized") or {}).get("unrealized_pnl_usdt")),
    }
