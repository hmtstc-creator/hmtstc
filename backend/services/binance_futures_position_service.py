from __future__ import annotations
from typing import Any, Dict, List


def get_futures_positions(runtime: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    runtime = runtime or {}
    positions = runtime.get("futures_positions") or []
    return positions if isinstance(positions, list) else []


def build_futures_position_snapshot(runtime: Dict[str, Any] | None = None) -> Dict[str, Any]:
    positions = get_futures_positions(runtime)
    return {
        "service": "binance_futures_position",
        "market": "futures",
        "open_positions": positions,
        "open_position_count": len(positions),
        "liquidation_risk_visible": True,
        "position_endpoint": "GET /fapi/v3/positionRisk",
    }
