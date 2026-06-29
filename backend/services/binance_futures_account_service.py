from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_connection_service import get_futures_connection_summary
from services.binance_futures_models import BINANCE_FUTURES_OFFICIAL_ENDPOINTS


def build_futures_account_snapshot(username: str) -> Dict[str, Any]:
    connection = get_futures_connection_summary(username)
    return {
        "service": "binance_futures_account",
        "market": "futures",
        "mode": connection.get("environment", "testnet"),
        "read_only_ready": bool(connection.get("api_key_configured") and connection.get("secret_configured") and connection.get("withdraw_safe")),
        "trade_permission": bool(connection.get("trade_permission")),
        "withdraw_safe": bool(connection.get("withdraw_safe")),
        "official_endpoints": {
            "position_mode": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["get_position_mode"],
            "user_trades": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["user_trades"],
        },
        "note": "Offline-safe snapshot; canlı ağ çağrısı production adapter fazında yapılır.",
    }
