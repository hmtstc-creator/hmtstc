from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_karabasan_service import build_karabasan_futures_score
from services.binance_futures_models import BINANCE_FUTURES_OFFICIAL_ENDPOINTS, now_iso


def build_futures_order_preview(runtime: Dict[str, Any], settings: Dict[str, Any], permission: Dict[str, Any], connection: Dict[str, Any], signal: Dict[str, Any]) -> Dict[str, Any]:
    gate = build_karabasan_futures_score(runtime, settings, permission, connection, signal)
    payload = {
        "symbol": gate["symbol"],
        "side": "BUY" if gate["side"] == "long" else "SELL",
        "positionSide": "BOTH",
        "type": "MARKET",
        "quantity": signal.get("quantity", "DRY_RUN_PREVIEW"),
        "leverage": gate["leverage"],
        "marginType": "ISOLATED",
        "takeProfitRequired": True,
        "stopLossRequired": True,
    }
    return {
        "service": "binance_futures_order_gate",
        "real_order_sent": False,
        "dry_run": True,
        "testnet_first": True,
        "submit_endpoint_locked": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["new_order"],
        "test_endpoint": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["test_order"],
        "order_payload_preview": payload,
        "gate": gate,
        "evidence": {"created_at": now_iso(), "checksum_basis": f"{payload['symbol']}:{payload['side']}:{gate['karabasan_futures_score']}"},
        "status": "ready_for_test_order" if gate["decision"] == "allow" else "blocked",
    }
