from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso
from services.futures_phase2_live_position_service import build_phase2_live_position_monitor


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def build_phase2_auto_close_gate(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    context = context or {}
    monitor = build_phase2_live_position_monitor(runtime, permission, context)
    close_mode = str(permission.get("futures_auto_close_mode") or context.get("close_mode") or "suggest_close")
    close_decisions: List[Dict[str, Any]] = []

    for p in monitor.get("positions", []):
        reasons: List[str] = []
        if p.get("risk_status") == "critical":
            reasons.append("Pozisyon kritik risk seviyesinde")
        if _num(p.get("karabasan_score"), 70) < _num(permission.get("futures_min_hold_karabasan_score"), 55):
            reasons.append("Karabasan Futures skoru tutma eşiğinin altına düştü")
        if p.get("funding_gate_passed") is False:
            reasons.append("Funding gate pozisyon tutma için riskli")
        if _num(context.get("daily_loss_usage_pct"), 0) >= _num(permission.get("futures_auto_close_daily_loss_usage_pct"), 85):
            reasons.append("Günlük zarar limiti yaklaşım eşiği aşıldı")
        if context.get("emergency_stop"):
            reasons.append("Emergency stop aktif")
        if context.get("btc_reverse_move") or _num(context.get("btc_reverse_move_pct"), 0) >= 1.5:
            reasons.append("BTC ters hareket riski")

        close_required = bool(reasons)
        mode = close_mode
        live_close_allowed = close_required and mode in {"auto_close_safe", "force_close_emergency"} and bool(permission.get("futures_live_permission"))
        if context.get("emergency_stop") and mode == "force_close_emergency":
            live_close_allowed = bool(permission.get("futures_live_permission"))
        close_decisions.append({
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "close_required": close_required,
            "close_mode": mode,
            "live_close_allowed": live_close_allowed,
            "close_preview_only": not live_close_allowed,
            "close_reasons": reasons,
            "recommended_action": "close_preview" if close_required else "hold",
            "admin_note": "Canlı kapatma owner/live permission ve safety kilitlerine bağlıdır.",
        })

    return {
        "service": "futures_phase2_auto_close_gate",
        "phase": "Faz2-3",
        "checked_at": now_iso(),
        "close_mode": close_mode,
        "monitor": monitor,
        "close_decisions": close_decisions,
        "any_close_required": any(item["close_required"] for item in close_decisions),
        "live_close_global_allowed": any(item["live_close_allowed"] for item in close_decisions),
        "new_order_allowed": monitor.get("new_order_allowed") and not any(item["close_required"] for item in close_decisions),
        "user_message": "Pozisyon kapatma önerisi var." if any(item["close_required"] for item in close_decisions) else "Pozisyonlar tutulabilir görünüyor.",
    }
