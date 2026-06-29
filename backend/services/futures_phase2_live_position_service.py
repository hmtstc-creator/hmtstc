from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso
from services.futures_phase2_funding_control_service import build_phase2_funding_control


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _position_risk_status(distance_pct: float, pnl_pct: float) -> str:
    if distance_pct < 3 or pnl_pct <= -5:
        return "critical"
    if distance_pct < 7 or pnl_pct <= -2.5:
        return "warning"
    return "safe"


def build_phase2_live_position_monitor(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    context = context or {}
    positions: List[Dict[str, Any]] = context.get("positions") or runtime.get("futures_open_positions") or runtime.get("futures_positions") or []
    monitored: List[Dict[str, Any]] = []
    critical_count = 0

    for p in positions:
        entry = _num(p.get("entry_price"), 0)
        mark = _num(p.get("mark_price"), entry)
        liq = _num(p.get("liquidation_price"), 0)
        side = str(p.get("side") or p.get("position_side") or "long").lower()
        qty = _num(p.get("quantity"), _num(p.get("qty"), 1))
        direction = -1 if side in {"short", "sell"} else 1
        raw_pnl = _num(p.get("unrealized_pnl"), (mark - entry) * qty * direction if entry else 0)
        notional = abs(_num(p.get("notional"), mark * qty if mark else 0))
        pnl_pct = (raw_pnl / notional * 100) if notional else _num(p.get("unrealized_pnl_pct"), 0)
        distance = abs((mark - liq) / mark * 100) if mark and liq else _num(p.get("liquidation_distance_pct"), 99)
        funding = build_phase2_funding_control(permission, {**p, **context.get("funding", {})})
        status = _position_risk_status(distance, pnl_pct)
        if not funding.get("funding_gate_passed") and status == "safe":
            status = "warning"
        if status == "critical":
            critical_count += 1
        monitored.append({
            "symbol": p.get("symbol", "UNKNOWN"),
            "side": side,
            "entry_price": entry,
            "mark_price": mark,
            "liquidation_price": liq,
            "leverage": _num(p.get("leverage"), _num(permission.get("futures_max_leverage"), 2)),
            "notional": round(notional, 4),
            "margin_used": _num(p.get("margin_used"), _num(p.get("isolated_margin"), 0)),
            "unrealized_pnl": round(raw_pnl, 4),
            "unrealized_pnl_pct": round(pnl_pct, 4),
            "liquidation_distance_pct": round(distance, 4),
            "funding_gate_passed": funding.get("funding_gate_passed"),
            "funding_risk_score": funding.get("funding_risk_score"),
            "tp_sl_status": p.get("tp_sl_status", "required"),
            "karabasan_score": _num(p.get("karabasan_futures_score"), _num(context.get("karabasan_futures_score"), 70)),
            "position_age": p.get("position_age") or p.get("opened_at") or "unknown",
            "risk_status": status,
        })

    return {
        "service": "futures_phase2_live_position_monitor",
        "phase": "Faz2-2",
        "checked_at": now_iso(),
        "polling_hint_seconds": 5,
        "position_count": len(monitored),
        "critical_position_count": critical_count,
        "positions": monitored,
        "new_order_allowed": critical_count == 0,
        "monitor_required_for_live": True,
        "user_summary": "Açık Futures pozisyonları izleniyor." if monitored else "Açık Futures pozisyon yok.",
        "admin_detail_enabled": True,
    }
