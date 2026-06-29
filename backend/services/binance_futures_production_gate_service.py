from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_models import now_iso, normalize_permission, BINANCE_FUTURES_OFFICIAL_ENDPOINTS
from services.binance_futures_readiness_service import build_futures_readiness
from services.binance_futures_karabasan_service import build_karabasan_futures_score
from services.binance_futures_risk_service import futures_hard_blocks

LIVE_STATUS_FLOW = ["disabled", "testnet_only", "mainnet_read_only", "live_pending", "live_enabled"]

def build_production_live_gate(runtime: Dict[str, Any], settings: Dict[str, Any], permission: Dict[str, Any], connection: Dict[str, Any], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal = signal or {}
    p = normalize_permission({"futures_permissions": permission})
    readiness = build_futures_readiness(str(signal.get("user") or "default"), p, connection)
    karabasan = build_karabasan_futures_score(runtime, settings, p, connection, signal)
    blocks: List[str] = []
    if not p.get("futures_enabled"):
        blocks.append("Owner Futures yetkisi vermedi")
    if p.get("futures_environment") != "mainnet":
        blocks.append("Mainnet ortamı seçili değil")
    if not p.get("futures_real_order_enabled"):
        blocks.append("Production live emir kilidi kapalı")
    if not connection.get("connected"):
        blocks.append("Futures API bağlı değil")
    if not connection.get("trade_permission"):
        blocks.append("Futures trade izni doğrulanmadı")
    if connection.get("withdraw_permission"):
        blocks.append("Withdraw izni açık; canlı emir yasak")
    if readiness.get("status") == "blocked":
        blocks.append("Futures readiness blocked")
    if karabasan.get("decision") != "allow":
        blocks.append("Karabasan Futures izin vermedi")
    blocks.extend(futures_hard_blocks(p, connection, signal, open_positions=len(runtime.get("futures_open_positions", [])), daily_loss=float(runtime.get("futures_daily_loss", 0) or 0)))
    return {
        "service": "binance_futures_production_live_gate",
        "checked_at": now_iso(),
        "status_flow": LIVE_STATUS_FLOW,
        "current_status": "live_enabled" if not blocks else ("live_pending" if p.get("futures_real_order_enabled") else "disabled"),
        "live_order_allowed": not blocks,
        "real_order_endpoint": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["new_order"],
        "preflight": {"readiness": readiness, "karabasan_futures": karabasan},
        "blocking_reasons": blocks,
        "management": "Owner onayı + readiness + Karabasan + TP/SL + risk gate geçmeden gerçek emir gönderilmez.",
    }
