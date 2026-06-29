from __future__ import annotations

from typing import Any, Dict

from services.binance_futures_models import now_iso
from services.futures_phase2_alarm_service import build_phase2_alarm_center
from services.futures_phase2_evidence_gate_service import build_phase2_final_gate
from services.futures_phase2_live_position_service import build_phase2_live_position_monitor
from services.futures_phase3_user_experience_service import build_phase3_user_futures_experience


def build_phase3_admin_operations_panel(
    username: str,
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    context = context or {}
    monitor = build_phase2_live_position_monitor(runtime, permission, context)
    alarms = build_phase2_alarm_center(runtime, permission, connection, context)
    final_gate = build_phase2_final_gate(runtime, permission, connection, context)
    user_view = build_phase3_user_futures_experience(runtime, permission, connection, context)
    live_allowed = bool(permission.get("futures_real_order_enabled") and permission.get("owner_final_live_confirmed"))
    readiness_state = "live_ready" if live_allowed and final_gate.get("phase2_final_gate_passed", final_gate.get("phase2_ready", False)) else "not_live_ready"
    return {
        "service": "futures_phase3_admin_operations_panel",
        "phase": "Faz3-2",
        "checked_at": now_iso(),
        "username": username,
        "admin_sections": [
            "user_permission", "live_gate", "api_readiness", "bot_mode",
            "open_positions", "karabasan_futures", "risk_status",
            "daily_pnl", "owner_receivable", "alarms",
            "last_order_attempt", "blocking_reason", "lifecycle",
        ],
        "operation_summary": {
            "futures_enabled": bool(permission.get("futures_enabled")),
            "access_level": permission.get("futures_access_level"),
            "bot_mode": permission.get("futures_user_control_mode"),
            "live_allowed_by_owner": live_allowed,
            "readiness_state": readiness_state,
            "critical_alarm_count": alarms.get("critical_count", 0),
            "open_position_count": monitor.get("open_position_count", 0),
        },
        "decision_questions": {
            "can_user_use_live": readiness_state == "live_ready",
            "is_risk_high": alarms.get("critical_count", 0) > 0 or monitor.get("global_risk_status") in {"danger", "blocked"},
            "why_no_trade": final_gate.get("blocking_reasons") or alarms.get("alarms") or ["Blok yok; fırsat bekleniyor."],
            "should_position_be_closed": any(a.get("type") == "close_required" for a in alarms.get("alarms", [])),
            "api_healthy": bool(connection.get("api_connected", connection.get("connected", False))),
        },
        "user_view_preview": user_view,
        "monitor": monitor,
        "alarms": alarms,
        "phase2_final_gate": final_gate,
    }
