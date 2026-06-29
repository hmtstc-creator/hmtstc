from __future__ import annotations
from typing import Any, Dict
from services.karabasan_score_service import build_karabasan_score
from services.binance_futures_risk_service import calculate_futures_risk_score, futures_hard_blocks


def build_karabasan_futures_score(runtime: Dict[str, Any], settings: Dict[str, Any], permission: Dict[str, Any], connection: Dict[str, Any], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal = signal or {"symbol": "ETHUSDT", "side": "long", "target_profit_pct": 1.0, "take_profit_pct": 1.0, "stop_loss_pct": 0.8, "leverage": 2}
    spot = build_karabasan_score(runtime, settings, {**signal, "market": "futures"})
    risk = calculate_futures_risk_score(permission, signal, runtime)
    final_score = round(float(spot.get("karabasan_score", 0)) * 0.70 + float(risk.get("futures_risk_score", 0)) * 0.30, 2)
    open_count = len(runtime.get("futures_positions") or []) if isinstance(runtime, dict) else 0
    daily_loss = float(((runtime.get("futures_daily") or {}) if isinstance(runtime, dict) else {}).get("loss_usdt") or 0)
    blocks = futures_hard_blocks(permission, connection, signal, open_count, daily_loss)
    if final_score < 65:
        blocks.append("Karabasan Futures skoru düşük")
    decision = "allow" if not blocks and final_score >= 65 else "block"
    confidence = "strong" if final_score >= 80 and not blocks else "controlled" if decision == "allow" else "blocked"
    return {
        "symbol": signal.get("symbol", "ETHUSDT"),
        "market": "futures",
        "side": str(signal.get("side") or "long").lower(),
        "leverage": int(float(signal.get("leverage") or 2)),
        "margin_type": permission.get("futures_margin_type", "isolated"),
        "position_mode": permission.get("futures_position_mode", "one_way"),
        "target_profit_pct": float(signal.get("take_profit_pct") or signal.get("target_profit_pct") or 1.0),
        "stop_loss_pct": float(signal.get("stop_loss_pct") or 0.8),
        "karabasan_spot_score": spot.get("karabasan_score", 0),
        "futures_risk_score": risk.get("futures_risk_score", 0),
        "karabasan_futures_score": final_score,
        "decision": decision,
        "confidence": confidence,
        "liquidation_distance_status": "safe" if float(signal.get("liquidation_distance_pct") or 10) >= 5 else "risky",
        "funding_risk": "low" if abs(float(signal.get("funding_rate_pct") or 0.01)) <= 0.03 else "high",
        "risk_breakdown": risk.get("parts", {}),
        "main_reasons": ["Spot piyasa uygun" if spot.get("decision") == "allow" else "Spot Karabasan beklemede", "Liquidation mesafesi güvenli", "Funding riski düşük"],
        "blocking_reasons": blocks,
        "spot_karabasan": spot,
    }
