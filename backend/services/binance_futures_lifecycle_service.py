from __future__ import annotations
import hashlib, json
from typing import Any, Dict, List
from services.binance_futures_position_service import get_futures_positions
from services.binance_futures_models import now_iso


def evidence_checksum(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_futures_lifecycle(runtime: Dict[str, Any] | None = None) -> Dict[str, Any]:
    runtime = runtime or {}
    positions = get_futures_positions(runtime)
    history = runtime.get("futures_lifecycle_history") or []
    if not isinstance(history, list): history = []
    rows: List[Dict[str, Any]] = []
    for item in positions:
        row = {
            "symbol": item.get("symbol", "BTCUSDT"),
            "side": item.get("side", "long"),
            "entry_price": item.get("entry_price", 0),
            "mark_price": item.get("mark_price", 0),
            "liquidation_price": item.get("liquidation_price", 0),
            "unrealized_pnl": item.get("unrealized_pnl", 0),
            "funding_fee": item.get("funding_fee", 0),
            "status": item.get("status", "open"),
        }
        row["evidence_checksum"] = evidence_checksum(row)
        rows.append(row)
    return {
        "service": "binance_futures_lifecycle",
        "market": "futures",
        "real_order_sent": False,
        "open_positions": rows,
        "history": history[-50:],
        "close_preview_enabled": True,
        "updated_at": now_iso(),
    }
