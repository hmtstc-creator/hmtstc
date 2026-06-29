"""Rev946-950 Production Monitoring & Alert service.

Secret-safe, network-free production monitoring contract. It consolidates VPS
service heartbeat, exchange adapter heartbeat, incident/freeze/halt alerts and
audit visibility into a compact operator decision packet. It never submits,
closes or emergency-closes real orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ready", "ok", "pass"}
    if value is None:
        return default
    return bool(value)


def _bounded(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, float(value))), 4)


def _payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "vps_backend_heartbeat_age_seconds": _num(payload.get("vps_backend_heartbeat_age_seconds"), 12),
        "scheduler_heartbeat_age_seconds": _num(payload.get("scheduler_heartbeat_age_seconds"), 18),
        "exchange_adapter_heartbeat_age_seconds": _num(payload.get("exchange_adapter_heartbeat_age_seconds"), 22),
        "max_allowed_heartbeat_age_seconds": _num(payload.get("max_allowed_heartbeat_age_seconds"), 60),
        "open_incidents": int(_num(payload.get("open_incidents"), 0)),
        "freeze_events_24h": int(_num(payload.get("freeze_events_24h"), 0)),
        "halt_events_24h": int(_num(payload.get("halt_events_24h"), 0)),
        "unacknowledged_alerts": int(_num(payload.get("unacknowledged_alerts"), 0)),
        "audit_events_24h": int(_num(payload.get("audit_events_24h"), 24)),
        "audit_visibility_enabled": _bool(payload.get("audit_visibility_enabled"), True),
        "secret_safe_logs": _bool(payload.get("secret_safe_logs"), True),
        "runtime_write_allowed": _bool(payload.get("runtime_write_allowed"), False),
        "real_submit_enabled": _bool(payload.get("real_submit_enabled"), False),
        "real_close_enabled": _bool(payload.get("real_close_enabled"), False),
        "emergency_close_enabled": _bool(payload.get("emergency_close_enabled"), False),
    }


def build_vps_service_heartbeat(model: dict[str, Any]) -> dict[str, Any]:
    max_age = max(1.0, _num(model["max_allowed_heartbeat_age_seconds"], 60))
    backend_age = _num(model["vps_backend_heartbeat_age_seconds"], 0)
    scheduler_age = _num(model["scheduler_heartbeat_age_seconds"], 0)
    worst_age = max(backend_age, scheduler_age)
    score = _bounded(100 - max(0.0, worst_age - max_age * 0.5) / max_age * 100)
    status = "PASS" if worst_age <= max_age else "REVIEW" if worst_age <= max_age * 2 else "BLOCKED"
    return {
        "status": status,
        "backend_heartbeat_age_seconds": backend_age,
        "scheduler_heartbeat_age_seconds": scheduler_age,
        "max_allowed_heartbeat_age_seconds": max_age,
        "score": score,
    }


def build_exchange_adapter_heartbeat(model: dict[str, Any]) -> dict[str, Any]:
    max_age = max(1.0, _num(model["max_allowed_heartbeat_age_seconds"], 60))
    adapter_age = _num(model["exchange_adapter_heartbeat_age_seconds"], 0)
    score = _bounded(100 - max(0.0, adapter_age - max_age * 0.5) / max_age * 120)
    status = "PASS" if adapter_age <= max_age else "REVIEW" if adapter_age <= max_age * 2 else "BLOCKED"
    return {
        "status": status,
        "exchange_adapter_heartbeat_age_seconds": adapter_age,
        "max_allowed_heartbeat_age_seconds": max_age,
        "score": score,
        "real_network_call_performed": False,
    }


def build_incident_alert_state(model: dict[str, Any]) -> dict[str, Any]:
    open_incidents = int(model["open_incidents"])
    freeze_events = int(model["freeze_events_24h"])
    halt_events = int(model["halt_events_24h"])
    unacked = int(model["unacknowledged_alerts"])
    score = _bounded(100 - open_incidents * 26 - unacked * 10 - halt_events * 8 - freeze_events * 4)
    if open_incidents > 0 or unacked >= 3:
        status = "BLOCKED"
    elif halt_events > 0 or freeze_events >= 3 or unacked > 0:
        status = "REVIEW"
    else:
        status = "PASS"
    return {
        "status": status,
        "open_incidents": open_incidents,
        "freeze_events_24h": freeze_events,
        "halt_events_24h": halt_events,
        "unacknowledged_alerts": unacked,
        "score": score,
    }


def build_audit_visibility(model: dict[str, Any]) -> dict[str, Any]:
    audit_enabled = bool(model["audit_visibility_enabled"])
    secret_safe = bool(model["secret_safe_logs"])
    audit_events = int(model["audit_events_24h"])
    runtime_write_allowed = bool(model["runtime_write_allowed"])
    status = "PASS" if audit_enabled and secret_safe and audit_events >= 1 and not runtime_write_allowed else "REVIEW"
    score = _bounded((35 if audit_enabled else 0) + (35 if secret_safe else 0) + min(20, audit_events) + (10 if not runtime_write_allowed else -20))
    return {
        "status": status,
        "audit_visibility_enabled": audit_enabled,
        "secret_safe_logs": secret_safe,
        "audit_events_24h": audit_events,
        "runtime_write_allowed": runtime_write_allowed,
        "score": score,
        "secret_values_returned": False,
    }


def build_production_monitoring_alert(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    model = _payload(payload)
    vps = build_vps_service_heartbeat(model)
    exchange = build_exchange_adapter_heartbeat(model)
    incident = build_incident_alert_state(model)
    audit = build_audit_visibility(model)
    checks = [vps, exchange, incident, audit]
    blocked = [name for name, row in zip(["vps_heartbeat", "exchange_adapter_heartbeat", "incident_alert", "audit_visibility"], checks) if row["status"] == "BLOCKED"]
    review = [name for name, row in zip(["vps_heartbeat", "exchange_adapter_heartbeat", "incident_alert", "audit_visibility"], checks) if row["status"] == "REVIEW"]
    unsafe_action_enabled = bool(model["real_submit_enabled"] or model["real_close_enabled"] or model["emergency_close_enabled"])
    average_score = round(sum(float(row["score"]) for row in checks) / len(checks), 4)
    if unsafe_action_enabled:
        decision = "MONITORING_BLOCKED"
        blocker = "real_action_flag_enabled"
        operator_action = "Disable real submit/close flags before production monitoring approval."
    elif blocked:
        decision = "MONITORING_BLOCKED"
        blocker = blocked[0]
        operator_action = "Resolve blocked monitoring condition before live operation."
    elif review:
        decision = "MONITORING_REVIEW"
        blocker = review[0]
        operator_action = "Review monitoring warning and acknowledge alert before repeat/live continuation."
    else:
        decision = "MONITORING_READY"
        blocker = "none"
        operator_action = "No operator action required; keep real actions approval-gated."
    return {
        "status": "ok",
        "revision": 950,
        "block": "Rev946-950 Production Monitoring & Alert",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "average_score": average_score,
        "vps_service_heartbeat": vps,
        "exchange_adapter_heartbeat": exchange,
        "incident_freeze_halt_alert": incident,
        "audit_trail_visibility": audit,
        "critical_blocker": blocker,
        "operator_action": operator_action,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "emergency_close_default_off": True,
        "auto_scale_default_off": True,
        "auto_apply_default_off": True,
        "auto_close_default_off": True,
        "real_network_call_performed": False,
        "secret_values_returned": False,
    }


def build_production_monitoring_alert_summary() -> dict[str, Any]:
    result = build_production_monitoring_alert()
    return {
        "status": result["status"],
        "revision": result["revision"],
        "decision": result["decision"],
        "average_score": result["average_score"],
        "vps_heartbeat": result["vps_service_heartbeat"]["status"],
        "exchange_heartbeat": result["exchange_adapter_heartbeat"]["status"],
        "incident_alert": result["incident_freeze_halt_alert"]["status"],
        "audit_visibility": result["audit_trail_visibility"]["status"],
        "open_incidents": result["incident_freeze_halt_alert"]["open_incidents"],
        "unacknowledged_alerts": result["incident_freeze_halt_alert"]["unacknowledged_alerts"],
        "critical_blocker": result["critical_blocker"],
        "operator_action": result["operator_action"],
        "real_submit_default_off": result["real_submit_default_off"],
        "real_close_default_off": result["real_close_default_off"],
        "secret_values_returned": result["secret_values_returned"],
    }
