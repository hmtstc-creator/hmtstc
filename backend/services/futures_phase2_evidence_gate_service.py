from __future__ import annotations

from typing import Any, Dict
import hashlib
import json

from services.binance_futures_models import now_iso
from services.futures_phase2_alarm_service import build_phase2_alarm_center


def build_phase2_evidence_record(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    decision: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    decision = decision or {}
    alarm_center = build_phase2_alarm_center(runtime, permission, connection, decision)
    payload = {
        "created_at": now_iso(),
        "phase": "Faz2-5",
        "symbol": decision.get("symbol"),
        "side": decision.get("side"),
        "strategy_signal": decision.get("strategy_signal"),
        "filter_result": decision.get("filter_result"),
        "karabasan_futures_score": decision.get("karabasan_futures_score"),
        "funding": alarm_center.get("close_gate", {}).get("monitor", {}).get("positions", []),
        "alarms": alarm_center.get("alarms", []),
        "close_decisions": alarm_center.get("close_gate", {}).get("close_decisions", []),
        "new_trade_allowed": alarm_center.get("new_trade_allowed"),
        "order_preview": decision.get("order_preview"),
        "final_decision": "allow_monitoring" if alarm_center.get("new_trade_allowed") else "blocked_by_phase2_risk",
        "order_sent": False,
    }
    checksum = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {
        "service": "futures_phase2_evidence_gate",
        "phase": "Faz2-5",
        "decision_id": decision.get("decision_id") or f"FUT-P2-{checksum[:12]}",
        "evidence": payload,
        "checksum": checksum,
        "evidence_required_for_live": True,
        "immutable_policy": "Faz 2 alarm/close/funding kanıtı oluşmadan kiralık gerçek Futures akışı live kabul edilmez.",
        "admin_questions": [
            "Funding riski neydi?",
            "Pozisyon neden tutuldu veya kapatıldı?",
            "Hangi alarm yeni emri engelledi?",
            "Kullanıcıya hangi sade mesaj gösterildi?",
        ],
    }


def build_phase2_final_gate(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    context = context or {}
    evidence = build_phase2_evidence_record(runtime, permission, connection, context)
    alarms = evidence["evidence"].get("alarms", [])
    blockers = []
    if any(a.get("severity") == "critical" for a in alarms):
        blockers.append("Faz 2 kritik alarm var")
    if evidence["evidence"].get("final_decision") != "allow_monitoring":
        blockers.append("Faz 2 evidence final kararı izin vermiyor")
    if not evidence.get("checksum"):
        blockers.append("Evidence checksum oluşmadı")

    return {
        "service": "futures_phase2_final_gate",
        "phase": "Faz2-Final",
        "checked_at": now_iso(),
        "all_5_steps_present": True,
        "steps": {
            "funding_control": True,
            "live_position_monitor": True,
            "auto_close_gate": True,
            "alarm_center": True,
            "audit_evidence": True,
        },
        "phase2_ready": not blockers,
        "new_order_allowed_after_phase2": not blockers,
        "blocking_reasons": blockers,
        "evidence": evidence,
        "final_rule": "Faz 2 final gate yeşil olmadan kiralık gerçek Futures canlı kullanım hazırlığı tamam kabul edilmez.",
    }
