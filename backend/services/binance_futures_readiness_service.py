from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_account_service import build_futures_account_snapshot
from services.binance_futures_models import BINANCE_FUTURES_OFFICIAL_ENDPOINTS, normalize_permission, public_permission
from services.binance_futures_risk_service import build_futures_risk_settings


def build_futures_readiness(username: str, permission: Dict[str, Any], connection: Dict[str, Any]) -> Dict[str, Any]:
    p = normalize_permission({"futures_permissions": permission})
    checks = [
        {"key": "futures_default_closed", "ok": not bool(p.get("futures_real_order_enabled")), "label": "Gerçek mainnet emir kapalı"},
        {"key": "owner_enabled", "ok": bool(p.get("futures_enabled")), "label": "Owner Futures yetkisi verdi"},
        {"key": "api_connected", "ok": bool(connection.get("connected")), "label": "Futures API bağlı"},
        {"key": "secret_hidden", "ok": connection.get("secret_returned_to_frontend") is False, "label": "Secret frontend'e dönmüyor"},
        {"key": "withdraw_safe", "ok": not bool(connection.get("withdraw_permission")), "label": "Withdraw izni yok"},
        {"key": "isolated", "ok": p.get("futures_margin_type") == "isolated", "label": "Isolated margin zorunlu"},
        {"key": "one_way", "ok": p.get("futures_position_mode") == "one_way", "label": "One-way mode"},
        {"key": "leverage_limit", "ok": int(p.get("futures_max_leverage") or 0) <= 2, "label": "Başlangıç leverage limiti konservatif"},
        {"key": "testnet_first", "ok": p.get("futures_environment") == "testnet", "label": "Testnet/read-only/dry-run zinciri"},
    ]
    return {
        "service": "binance_futures_readiness",
        "username": username,
        "market": "futures",
        "visible_to_user": bool(p.get("futures_enabled")),
        "permission": public_permission(p),
        "connection": connection,
        "risk_settings": build_futures_risk_settings(p),
        "account": build_futures_account_snapshot(username),
        "official_endpoint_contract": BINANCE_FUTURES_OFFICIAL_ENDPOINTS,
        "checks": checks,
        "ready": all(item["ok"] for item in checks),
        "status": "ready" if all(item["ok"] for item in checks) else "blocked_or_pending",
    }
