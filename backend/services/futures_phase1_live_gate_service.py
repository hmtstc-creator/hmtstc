from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import BINANCE_FUTURES_OFFICIAL_ENDPOINTS, normalize_permission, now_iso
from services.binance_futures_production_gate_service import build_production_live_gate
from services.binance_futures_readiness_service import build_futures_readiness

PHASE1_LIVE_STATES = [
    "disabled",
    "testnet_only",
    "mainnet_read_only",
    "live_pending_owner",
    "live_ready_locked",
    "live_enabled",
]


def _is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "open"}


def build_phase1_real_futures_live_gate(
    runtime: Dict[str, Any],
    settings: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Single truth gate for real Binance Futures order activation.

    This gate does not submit an order. It produces a deterministic owner-facing
    contract that must be green before the order layer can use /fapi/v1/order.
    """
    signal = signal or {}
    p = normalize_permission({"futures_permissions": permission})
    base_gate = build_production_live_gate(runtime, settings, p, connection, signal)
    readiness = build_futures_readiness(str(signal.get("user") or "default"), p, connection)

    blocks: List[str] = []
    if not p.get("futures_enabled"):
        blocks.append("Futures VIP yetkisi owner tarafından açılmadı")
    if p.get("futures_environment") != "mainnet":
        blocks.append("Gerçek emir için mainnet ortamı seçili değil")
    if not p.get("futures_real_order_enabled"):
        blocks.append("Owner live emir ana kilidini açmadı")
    if not _is_true(signal.get("owner_final_live_confirmed")):
        blocks.append("Owner son canlı emir onayı yok")
    if not connection.get("connected"):
        blocks.append("Futures API bağlantısı yok")
    if not connection.get("trade_permission"):
        blocks.append("Futures trade izni doğrulanmadı")
    if connection.get("withdraw_permission"):
        blocks.append("Withdraw izni açık; güvenlik nedeniyle live yasak")
    if readiness.get("status") == "blocked":
        blocks.append("Readiness kontrolü blocked")
    if not base_gate.get("live_order_allowed"):
        blocks.extend([x for x in base_gate.get("blocking_reasons", []) if x not in blocks])

    current_state = "live_enabled" if not blocks else (
        "live_ready_locked" if p.get("futures_real_order_enabled") and p.get("futures_environment") == "mainnet" else
        "live_pending_owner" if p.get("futures_environment") == "mainnet" else
        "testnet_only" if p.get("futures_environment") == "testnet" else "disabled"
    )
    return {
        "service": "futures_phase1_real_live_gate",
        "phase": "Faz1-1",
        "checked_at": now_iso(),
        "live_state_flow": PHASE1_LIVE_STATES,
        "current_state": current_state,
        "real_order_allowed": not blocks,
        "real_order_endpoint": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["new_order"],
        "test_order_endpoint": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["test_order"],
        "base_gate": base_gate,
        "readiness": readiness,
        "blocking_reasons": blocks,
        "owner_management": {
            "required_switches": [
                "futures_enabled",
                "futures_environment=mainnet",
                "futures_real_order_enabled",
                "owner_final_live_confirmed",
            ],
            "cannot_be_changed_by_user": True,
            "mainnet_submit_remains_blocked_until_gate_green": True,
        },
    }
