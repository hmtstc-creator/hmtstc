from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import normalize_permission, now_iso


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_tpsl_guard(permission: Dict[str, Any], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal = signal or {}
    p = normalize_permission({"futures_permissions": permission})
    tp = _num(signal.get("take_profit_pct") or signal.get("target_profit_pct"), 0)
    sl = _num(signal.get("stop_loss_pct"), 0)
    min_tp = _num(p.get("futures_min_take_profit_pct"), 0.3)
    max_tp = _num(p.get("futures_max_take_profit_pct"), 3.0)
    min_sl = _num(p.get("futures_min_stop_loss_pct"), 0.2)
    max_sl = _num(p.get("futures_max_stop_loss_pct"), 2.0)
    blocks: List[str] = []
    if tp <= 0:
        blocks.append("Take profit zorunlu")
    if sl <= 0:
        blocks.append("Stop loss zorunlu")
    if tp and tp < min_tp:
        blocks.append("Take profit owner minimumunun altında")
    if tp and tp > max_tp:
        blocks.append("Take profit owner maksimumunu aşıyor")
    if sl and sl < min_sl:
        blocks.append("Stop loss owner minimumunun altında")
    if sl and sl > max_sl:
        blocks.append("Stop loss owner maksimumunu aşıyor")
    if tp and sl and tp <= sl * 0.5:
        blocks.append("Risk/ödül zayıf; TP stop mesafesine göre çok düşük")
    return {
        "service": "futures_phase1_tpsl_guard",
        "phase": "Faz1-6",
        "checked_at": now_iso(),
        "take_profit_pct": tp,
        "stop_loss_pct": sl,
        "owner_limits": {"min_tp": min_tp, "max_tp": max_tp, "min_sl": min_sl, "max_sl": max_sl},
        "tp_sl_required": True,
        "tp_sl_valid": not blocks,
        "blocking_reasons": blocks,
        "management": "TP/SL eksik veya owner sınırlarının dışındaysa Futures order gate çalışmaz.",
    }
