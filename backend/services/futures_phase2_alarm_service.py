from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso
from services.futures_phase2_auto_close_gate_service import build_phase2_auto_close_gate
from services.futures_phase2_funding_control_service import build_phase2_funding_control


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def build_phase2_alarm_center(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    context = context or {}
    alarms: List[Dict[str, Any]] = []

    def add(severity: str, alarm_type: str, user_message: str, admin_detail: str, action: str = "observe") -> None:
        alarms.append({
            "severity": severity,
            "type": alarm_type,
            "user_message": user_message,
            "admin_detail": admin_detail,
            "recommended_action": action,
        })

    if connection.get("api_connected") is False or connection.get("connected") is False:
        add("critical", "api_disconnected", "Futures API bağlantısı kesildi.", "API readiness false döndü.", "block_new_orders")
    if not permission.get("futures_enabled"):
        add("info", "futures_disabled", "Futures şu an kapalı.", "Owner Futures yetkisini kapalı tutuyor.")
    if context.get("emergency_stop") or runtime.get("futures_emergency_stop"):
        add("critical", "emergency_stop", "Acil durdurma aktif.", "Emergency stop yeni emirleri bloke eder.", "block_and_review")
    if _num(context.get("daily_loss_usage_pct"), 0) >= 85:
        add("critical", "daily_loss_limit_near", "Günlük zarar limiti yaklaştı.", "Daily futures loss usage >= 85%.", "block_new_orders")
    if context.get("tp_sl_missing"):
        add("critical", "tp_sl_missing", "TP/SL koruması eksik.", "Korumasız Futures pozisyon/emir tespit edildi.", "block_or_close_preview")

    funding = build_phase2_funding_control(permission, context.get("funding") or context)
    if not funding.get("funding_gate_passed"):
        add("high", "funding_gate_block", "Funding riski yükseldi.", "; ".join(funding.get("blocking_reasons", [])), "pause_new_orders")
    elif funding.get("warnings"):
        add("warning", "funding_warning", "Funding riski takipte.", "; ".join(funding.get("warnings", [])))

    close_gate = build_phase2_auto_close_gate(runtime, permission, context)
    if close_gate.get("any_close_required"):
        severity = "critical" if close_gate.get("live_close_global_allowed") else "high"
        add(severity, "close_required", "Pozisyon kapatma önerisi var.", "Auto close gate close_required=True döndü.", "review_close_gate")

    new_trade_allowed = not any(a["severity"] == "critical" for a in alarms)
    return {
        "service": "futures_phase2_alarm_center",
        "phase": "Faz2-4",
        "checked_at": now_iso(),
        "alarm_count": len(alarms),
        "critical_count": sum(1 for a in alarms if a["severity"] == "critical"),
        "alarms": alarms,
        "new_trade_allowed": new_trade_allowed,
        "user_alarm_summary": "Kritik risk yok." if new_trade_allowed else "Kritik Futures riski var; yeni işlem durduruldu.",
        "admin_detail_enabled": True,
        "close_gate": close_gate,
    }
