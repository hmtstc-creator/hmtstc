from __future__ import annotations
from typing import Any, Dict
from core.auth import read_auth_store, write_auth_store
from services.binance_futures_models import normalize_permission, public_permission, now_iso


def get_user_futures_permission(username: str) -> Dict[str, Any]:
    store = read_auth_store()
    record = (store.get("users") or {}).get(username) or {}
    return normalize_permission(record)


def set_user_futures_permission(username: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    store = read_auth_store()
    users = store.setdefault("users", {})
    record = users.get(username)
    if not record:
        raise KeyError(username)
    current = normalize_permission(record)
    editable = {
        "futures_enabled", "futures_permission_status", "futures_max_leverage", "futures_allowed_symbols",
        "futures_long_enabled", "futures_short_enabled", "futures_margin_type", "futures_position_mode",
        "futures_daily_loss_limit", "futures_max_open_positions", "futures_max_notional_per_trade",
        "futures_commission_buy_pct", "futures_commission_sell_pct", "futures_environment", "futures_real_order_enabled",
        "futures_access_level", "futures_user_control_mode", "futures_emergency_stop", "owner_final_live_confirmed",
        "futures_min_take_profit_pct", "futures_max_take_profit_pct", "futures_min_stop_loss_pct",
        "futures_max_stop_loss_pct", "futures_min_liquidation_distance_pct",
    }
    for key in editable:
        if key in payload:
            current[key] = payload[key]
    if current.get("futures_enabled"):
        current["futures_permission_status"] = "enabled_by_owner"
    else:
        current["futures_permission_status"] = "disabled_by_owner"
    current = normalize_permission({"futures_permissions": current})
    current["updated_at"] = now_iso()
    record["futures_permissions"] = current
    users[username] = record
    write_auth_store(store)
    return public_permission(current, is_owner=True)


def list_futures_permissions() -> Dict[str, Any]:
    store = read_auth_store()
    return {
        "service": "binance_futures_permissions",
        "users": [
            {"username": username, "role": record.get("role", "user"), **public_permission(normalize_permission(record), is_owner=True)}
            for username, record in (store.get("users") or {}).items()
        ],
    }
