"""HMTSTC Futures VIP/Premium domain contracts.

Futures is intentionally separated from spot. Defaults are conservative:
- disabled unless owner enables it
- isolated margin
- one-way position mode
- max leverage 2x
- dry-run/testnet first, mainnet submit locked
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict

DEFAULT_FUTURES_PERMISSION: Dict[str, Any] = {
    "futures_enabled": False,
    "futures_permission_status": "disabled_by_owner",
    "futures_max_leverage": 2,
    "futures_allowed_symbols": ["BTCUSDT", "ETHUSDT"],
    "futures_long_enabled": True,
    "futures_short_enabled": False,
    "futures_margin_type": "isolated",
    "futures_position_mode": "one_way",
    "futures_daily_loss_limit": 25.0,
    "futures_max_open_positions": 1,
    "futures_max_notional_per_trade": 50.0,
    "futures_commission_buy_pct": 0.1,
    "futures_commission_sell_pct": 0.1,
    "futures_environment": "testnet",
    "futures_real_order_enabled": False,
    "futures_access_level": "futures_disabled",
    "futures_user_control_mode": "closed",
    "futures_emergency_stop": False,
    "owner_final_live_confirmed": False,
    "futures_min_take_profit_pct": 0.3,
    "futures_max_take_profit_pct": 3.0,
    "futures_min_stop_loss_pct": 0.2,
    "futures_max_stop_loss_pct": 2.0,
    "futures_min_liquidation_distance_pct": 5.0,
}

DEFAULT_FUTURES_CREDENTIAL: Dict[str, Any] = {
    "futures_api_key": "",
    "futures_secret": "",
    "environment": "testnet",
    "trade_permission": False,
    "withdraw_permission": False,
    "last_checked_at": None,
}

BINANCE_FUTURES_OFFICIAL_ENDPOINTS: Dict[str, str] = {
    "new_order": "POST /fapi/v1/order",
    "test_order": "POST /fapi/v1/order/test",
    "change_margin_type": "POST /fapi/v1/marginType",
    "change_position_mode": "POST /fapi/v1/positionSide/dual",
    "get_position_mode": "GET /fapi/v1/positionSide/dual",
    "change_initial_leverage": "POST /fapi/v1/leverage",
    "position_information_v3": "GET /fapi/v3/positionRisk",
    "user_trades": "GET /fapi/v1/userTrades",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def pct_value(value: Any, default: float = 0.1) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    if parsed < 0:
        return default
    return parsed * 100 if 0 < parsed < 0.01 else parsed


def normalize_margin_type(value: Any) -> str:
    value = str(value or "isolated").strip().lower()
    return "isolated" if value not in {"cross", "crossed"} else "cross"


def normalize_position_mode(value: Any) -> str:
    value = str(value or "one_way").strip().lower().replace("-", "_")
    return "hedge" if value in {"hedge", "hedge_mode"} else "one_way"


def normalize_permission(record: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = deepcopy(DEFAULT_FUTURES_PERMISSION)
    if isinstance(record, dict):
        raw.update(record.get("futures_permissions") or {})
        for key in list(DEFAULT_FUTURES_PERMISSION.keys()):
            if key in record and key not in raw:
                raw[key] = record[key]
    raw["futures_enabled"] = bool(raw.get("futures_enabled"))
    raw["futures_max_leverage"] = max(1, min(125, int(float(raw.get("futures_max_leverage") or 2))))
    raw["futures_margin_type"] = normalize_margin_type(raw.get("futures_margin_type"))
    if raw["futures_margin_type"] != "isolated":
        raw["futures_permission_status"] = "blocked_cross_margin"
    raw["futures_position_mode"] = normalize_position_mode(raw.get("futures_position_mode"))
    raw["futures_long_enabled"] = bool(raw.get("futures_long_enabled", True))
    raw["futures_short_enabled"] = bool(raw.get("futures_short_enabled", False))
    raw["futures_real_order_enabled"] = bool(raw.get("futures_real_order_enabled", False))
    raw["futures_emergency_stop"] = bool(raw.get("futures_emergency_stop", False))
    raw["owner_final_live_confirmed"] = bool(raw.get("owner_final_live_confirmed", False))
    raw["futures_access_level"] = str(raw.get("futures_access_level") or ("futures_testnet" if raw.get("futures_enabled") else "futures_disabled"))
    raw["futures_user_control_mode"] = str(raw.get("futures_user_control_mode") or "closed").lower()
    raw["futures_environment"] = "testnet" if str(raw.get("futures_environment") or "testnet").lower() != "mainnet" else "mainnet"
    raw["futures_commission_buy_pct"] = pct_value(raw.get("futures_commission_buy_pct"), 0.1)
    raw["futures_commission_sell_pct"] = pct_value(raw.get("futures_commission_sell_pct"), 0.1)
    return raw


def mask_api_key(value: str | None) -> str:
    key = str(value or "").strip()
    if not key:
        return "-"
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:4] + "***" + key[-4:]


def public_permission(permission: Dict[str, Any], is_owner: bool = False) -> Dict[str, Any]:
    visible = bool(permission.get("futures_enabled")) or is_owner
    return {
        "visible": visible,
        "vip_area": True,
        "futures_enabled": bool(permission.get("futures_enabled")),
        "permission_status": permission.get("futures_permission_status", "disabled_by_owner"),
        "max_leverage": permission.get("futures_max_leverage", 2),
        "allowed_symbols": permission.get("futures_allowed_symbols", []),
        "long_enabled": bool(permission.get("futures_long_enabled")),
        "short_enabled": bool(permission.get("futures_short_enabled")),
        "margin_type": permission.get("futures_margin_type", "isolated"),
        "position_mode": permission.get("futures_position_mode", "one_way"),
        "daily_loss_limit": permission.get("futures_daily_loss_limit", 0),
        "max_open_positions": permission.get("futures_max_open_positions", 1),
        "max_notional_per_trade": permission.get("futures_max_notional_per_trade", 0),
        "environment": permission.get("futures_environment", "testnet"),
        "real_order_enabled": bool(permission.get("futures_real_order_enabled", False)) if is_owner else False,
        "access_level": permission.get("futures_access_level", "futures_disabled") if is_owner else ("enabled" if permission.get("futures_enabled") else "hidden"),
        "user_control_mode": permission.get("futures_user_control_mode", "closed"),
        "emergency_stop": bool(permission.get("futures_emergency_stop", False)),
    }
