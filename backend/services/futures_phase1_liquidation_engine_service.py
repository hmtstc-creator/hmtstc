from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import normalize_permission, now_iso


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_liquidation_risk_engine(permission: Dict[str, Any], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal = signal or {}
    p = normalize_permission({"futures_permissions": permission})
    side = str(signal.get("side") or "long").lower()
    entry = _num(signal.get("entry_price") or signal.get("mark_price"), 0)
    mark = _num(signal.get("mark_price"), entry)
    leverage = max(1.0, min(_num(signal.get("leverage"), p.get("futures_max_leverage", 2)), float(p.get("futures_max_leverage", 2))))
    liq = _num(signal.get("liquidation_price"), 0)
    sl_pct = _num(signal.get("stop_loss_pct"), 0)
    min_distance = _num(p.get("futures_min_liquidation_distance_pct"), 5.0)

    if entry > 0 and liq <= 0:
        # Conservative approximation for isolated one-way preview; exchange value wins when provided.
        liq = entry * (1 - (0.85 / leverage)) if side == "long" else entry * (1 + (0.85 / leverage))
    distance_pct = 0.0
    if mark > 0 and liq > 0:
        distance_pct = abs(mark - liq) / mark * 100
    sl_to_liq_gap_pct = max(0.0, distance_pct - sl_pct)
    blocks: List[str] = []
    if entry <= 0 or mark <= 0:
        blocks.append("Entry/mark price hesaplanamadı")
    if distance_pct < min_distance:
        blocks.append("Liquidation mesafesi owner minimumunun altında")
    if sl_pct <= 0:
        blocks.append("Stop loss yok; liquidation riski değerlendirilemez")
    if sl_to_liq_gap_pct < 2.0:
        blocks.append("Stop loss liquidation seviyesine çok yakın")
    if leverage > float(p.get("futures_max_leverage", 2)):
        blocks.append("Leverage owner limitini aşıyor")

    if blocks:
        risk_status = "blocked"
    elif distance_pct < min_distance + 2:
        risk_status = "danger"
    elif distance_pct < min_distance + 5:
        risk_status = "warning"
    else:
        risk_status = "safe"

    return {
        "service": "futures_phase1_liquidation_risk_engine",
        "phase": "Faz1-7",
        "checked_at": now_iso(),
        "symbol": signal.get("symbol", "BTCUSDT"),
        "side": side,
        "entry_price": round(entry, 6),
        "mark_price": round(mark, 6),
        "liquidation_price": round(liq, 6),
        "leverage": leverage,
        "liquidation_distance_pct": round(distance_pct, 4),
        "stop_loss_pct": sl_pct,
        "stop_to_liquidation_gap_pct": round(sl_to_liq_gap_pct, 4),
        "minimum_required_distance_pct": min_distance,
        "risk_status": risk_status,
        "liquidation_gate_passed": risk_status in {"safe", "warning"} and not blocks,
        "blocking_reasons": blocks,
        "user_message": "Likidasyon güvenliği uygun." if risk_status in {"safe", "warning"} and not blocks else "Likidasyon riski nedeniyle işlem engellendi.",
    }
