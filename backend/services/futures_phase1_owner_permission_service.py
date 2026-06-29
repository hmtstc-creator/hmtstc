from __future__ import annotations

from typing import Any, Dict

from services.binance_futures_models import normalize_permission, public_permission, now_iso

ACCESS_LEVELS = [
    "futures_disabled",
    "futures_testnet",
    "futures_read_only",
    "futures_dry_run",
    "futures_live_ready",
    "futures_live_allowed",
    "futures_suspended",
]


def normalize_access_level(value: Any) -> str:
    text = str(value or "futures_disabled").strip().lower()
    return text if text in ACCESS_LEVELS else "futures_disabled"


def build_owner_permission_plan(username: str, permission: Dict[str, Any]) -> Dict[str, Any]:
    p = normalize_permission({"futures_permissions": permission})
    access = normalize_access_level(p.get("futures_access_level") or ("futures_live_allowed" if p.get("futures_real_order_enabled") else ("futures_testnet" if p.get("futures_enabled") else "futures_disabled")))
    return {
        "service": "futures_phase1_owner_permission_plan",
        "phase": "Faz1-2",
        "username": username,
        "updated_at": now_iso(),
        "access_levels": ACCESS_LEVELS,
        "current_access_level": access,
        "permission": public_permission(p, is_owner=True),
        "owner_only_controls": {
            "futures_visible": p.get("futures_enabled"),
            "testnet_allowed": access in {"futures_testnet", "futures_dry_run", "futures_live_ready", "futures_live_allowed"},
            "read_only_allowed": access in {"futures_read_only", "futures_dry_run", "futures_live_ready", "futures_live_allowed"},
            "dry_run_allowed": access in {"futures_dry_run", "futures_live_ready", "futures_live_allowed"},
            "live_allowed": access == "futures_live_allowed" and p.get("futures_real_order_enabled") is True,
            "short_allowed": bool(p.get("futures_short_enabled")),
            "hedge_allowed": p.get("futures_position_mode") == "hedge",
            "max_leverage": p.get("futures_max_leverage"),
            "max_notional_per_trade": p.get("futures_max_notional_per_trade"),
            "daily_loss_limit": p.get("futures_daily_loss_limit"),
        },
        "safety_rule": "Kullanıcı kendi Futures erişim seviyesini değiştiremez; tüm live ve short/hedge izinleri owner-only kalır.",
    }
