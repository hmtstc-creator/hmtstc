from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso
from services.futures_phase1_live_gate_service import build_phase1_real_futures_live_gate
from services.futures_phase1_owner_permission_service import build_owner_permission_plan
from services.futures_phase1_user_control_service import build_user_futures_control_contract
from services.futures_phase1_karabasan_bridge_service import build_futures_karabasan_execution_bridge
from services.futures_phase1_order_preview_service import build_phase1_order_preview
from services.futures_phase1_tpsl_guard_service import build_tpsl_guard
from services.futures_phase1_liquidation_engine_service import build_liquidation_risk_engine


def build_phase1_real_futures_final_gate(
    username: str,
    runtime: Dict[str, Any],
    settings: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal = signal or {}
    checks = {
        "live_gate": build_phase1_real_futures_live_gate(runtime, settings, permission, connection, signal),
        "owner_permission": build_owner_permission_plan(username, permission),
        "user_control": build_user_futures_control_contract(permission, signal.get("control_mode")),
        "karabasan_bridge": build_futures_karabasan_execution_bridge(runtime, settings, permission, connection, signal),
        "order_preview": build_phase1_order_preview(runtime, settings, permission, connection, signal),
        "tp_sl_guard": build_tpsl_guard(permission, signal),
        "liquidation_engine": build_liquidation_risk_engine(permission, signal),
    }
    blockers: List[str] = []
    if not checks["live_gate"].get("real_order_allowed"):
        blockers.extend(checks["live_gate"].get("blocking_reasons", []))
    if checks["user_control"].get("new_order_blocked"):
        blockers.extend(checks["user_control"].get("blocking_reasons", []))
    if checks["karabasan_bridge"].get("decision") != "allow_execution_gate":
        blockers.extend(checks["karabasan_bridge"].get("blocking_reasons", []))
    if checks["order_preview"].get("status") == "blocked":
        blockers.extend(checks["order_preview"].get("blocking_reasons", []))
    if not checks["tp_sl_guard"].get("tp_sl_valid"):
        blockers.extend(checks["tp_sl_guard"].get("blocking_reasons", []))
    if not checks["liquidation_engine"].get("liquidation_gate_passed"):
        blockers.extend(checks["liquidation_engine"].get("blocking_reasons", []))
    unique = []
    for item in blockers:
        if item and item not in unique:
            unique.append(item)
    return {
        "service": "futures_phase1_real_futures_final_gate",
        "phase": "Faz1-Final",
        "checked_at": now_iso(),
        "all_7_steps_present": True,
        "real_order_allowed": not unique,
        "checks": checks,
        "blocking_reasons": unique,
        "final_rule": "Bu final gate yeşil olmadan gerçek Binance Futures emri gönderilmez.",
    }
