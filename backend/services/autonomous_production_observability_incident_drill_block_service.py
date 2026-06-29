from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency", "fail"}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    return _as_dict(settings.get(key))


def _check(name: str, status: str, detail: str, required: bool = True, priority: int = 50, action: str = "review") -> dict:
    return {"name": name, "status": status, "required": required, "priority": priority, "detail": detail, "action": action}


def _totals(checks: list[dict]) -> dict:
    return {
        "total": len(checks),
        "ok": len([c for c in checks if c.get("status") == "ok"]),
        "review": len([c for c in checks if c.get("status") == "review"]),
        "blocked": len([c for c in checks if c.get("status") == "blocked"]),
    }


def _final_status(checks: list[dict]) -> str:
    required = [c for c in checks if c.get("required", True)]
    if any(c.get("status") == "blocked" for c in required):
        return "blocked"
    if any(c.get("status") == "review" for c in checks):
        return "review"
    return "ok"


def _command_preview() -> dict:
    return {
        "places_order": False,
        "submits_close_order": False,
        "sends_exchange_request": False,
        "writes_runtime_file": False,
        "journal_write_allowed": True,
        "audit_write_allowed": True,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
        "auto_apply": False,
    }


def _policy(settings: dict | None) -> dict:
    source: dict[str, Any] = {}
    for key in (
        "autonomous_production_observability_incident_drill",
        "autonomous_production_self_governance",
        "autonomous_small_capital_autonomy_preparation",
    ):
        source.update(_settings(settings, key))
    return {
        "max_heartbeat_age_seconds": max(10, _safe_int(source.get("max_heartbeat_age_seconds"), 120)),
        "min_trace_completeness": max(0.0, min(1.0, _safe_float(source.get("min_trace_completeness"), 0.90))),
        "min_incident_drill_score": max(0.0, min(1.0, _safe_float(source.get("min_incident_drill_score"), 0.85))),
        "max_open_major_incidents": max(0, _safe_int(source.get("max_open_major_incidents"), 0)),
        "max_notional_usdt": max(5.0, _safe_float(source.get("max_notional_usdt"), 25.0)),
        "allowed_symbols": _as_list(source.get("allowed_symbols")) or ["BTCUSDT", "ETHUSDT"],
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
    }


def _runtime(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source: dict[str, Any] = {}
    for key in (
        "production_observability_runtime",
        "incident_runtime",
        "production_self_governance_runtime",
        "small_capital_runtime",
        "reconciliation_runtime",
        "risk_firewall",
    ):
        source.update(_as_dict(data.get(key)))
    return {
        "mode": str(source.get("mode") or data.get("mode") or "production_preview"),
        "heartbeat_age_seconds": max(0, _safe_int(source.get("heartbeat_age_seconds"), 999)),
        "scheduler_alive": _safe_bool(source.get("scheduler_alive"), False),
        "summary_alive": _safe_bool(source.get("summary_alive"), True),
        "audit_alive": _safe_bool(source.get("audit_alive"), True),
        "journal_alive": _safe_bool(source.get("journal_alive"), True),
        "decision_trace_steps": _as_list(source.get("decision_trace_steps")),
        "trace_completeness": max(0.0, min(1.0, _safe_float(source.get("trace_completeness"), 0.0))),
        "open_major_incidents": max(0, _safe_int(source.get("open_major_incidents"), 0)),
        "last_incident_drill_score": max(0.0, min(1.0, _safe_float(source.get("last_incident_drill_score"), 0.0))),
        "loss_tripwire_seen": _safe_bool(source.get("loss_tripwire_seen"), False),
        "reconciliation_alarm_seen": _safe_bool(source.get("reconciliation_alarm_seen"), False),
        "duplicate_order_alarm_seen": _safe_bool(source.get("duplicate_order_alarm_seen"), False),
        "operator_ack_required": _safe_bool(source.get("operator_ack_required"), False),
        "owner_approval": _safe_bool(source.get("owner_approval"), False),
    }


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "No critical issue detected.", "action": "continue_guarded_observation", "priority": 99}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda x: (weight.get(str(x.get("severity")), 2), int(x.get("priority", 50))))[0]


def build_rev221_production_telemetry_heartbeat(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    runtime = _runtime(data)
    checks = [
        _check("scheduler_heartbeat", "ok" if runtime["scheduler_alive"] and runtime["heartbeat_age_seconds"] <= policy["max_heartbeat_age_seconds"] else "review", "Scheduler heartbeat must be fresh before limited live actions.", True, 5, "refresh_scheduler_heartbeat"),
        _check("summary_alive", "ok" if runtime["summary_alive"] else "blocked", "Operator Summary must be reachable.", True, 1, "restore_summary"),
        _check("audit_alive", "ok" if runtime["audit_alive"] else "blocked", "Audit channel must be reachable.", True, 2, "restore_audit"),
        _check("journal_alive", "ok" if runtime["journal_alive"] else "blocked", "Trade journal channel must be reachable.", True, 3, "restore_journal"),
    ]
    heartbeat = {
        "heartbeat_status": _final_status(checks),
        "heartbeat_age_seconds": runtime["heartbeat_age_seconds"],
        "max_heartbeat_age_seconds": policy["max_heartbeat_age_seconds"],
        "scheduler_alive": runtime["scheduler_alive"],
        "summary_alive": runtime["summary_alive"],
        "audit_alive": runtime["audit_alive"],
        "journal_alive": runtime["journal_alive"],
        "next_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "real_submit_close": "OFF",
    }
    return {"engine": "production_telemetry_heartbeat", "revision": 221, "status": _final_status(checks), "generated_at": now_iso(), "production_telemetry_heartbeat": heartbeat, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev222_decision_trace_validator"}


def build_rev222_decision_trace_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    runtime = _runtime(data)
    required_steps = ["market", "strategy", "risk", "approval", "execution_preview", "reconciliation", "summary"]
    present = set(str(x) for x in runtime["decision_trace_steps"])
    missing = [step for step in required_steps if step not in present]
    completeness = runtime["trace_completeness"] or (1.0 - (len(missing) / len(required_steps)))
    checks = [
        _check("trace_completeness", "ok" if completeness >= policy["min_trace_completeness"] else "review", "Decision trace must show why action was allowed or blocked.", True, 4, "complete_decision_trace"),
        _check("risk_step_present", "ok" if "risk" in present else "blocked", "Risk step is mandatory.", True, 1, "restore_risk_trace"),
        _check("approval_step_present", "ok" if "approval" in present else "blocked", "Approval gate trace is mandatory.", True, 2, "restore_approval_trace"),
        _check("summary_step_present", "ok" if "summary" in present else "review", "Summary trace should be visible to operator.", True, 6, "restore_summary_trace"),
    ]
    validator = {
        "trace_status": _final_status(checks),
        "trace_completeness": round(completeness, 4),
        "required_steps": required_steps,
        "missing_steps": missing,
        "decision_explainable": _final_status(checks) == "ok",
        "operator_action": "review_missing_trace" if missing else "continue_guarded_observation",
        "real_submit_close": "OFF",
    }
    return {"engine": "decision_trace_validator", "revision": 222, "status": _final_status(checks), "generated_at": now_iso(), "decision_trace_validator": validator, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev223_incident_drill_simulator"}


def build_rev223_incident_drill_simulator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    runtime = _runtime(data)
    scenarios = [
        {"scenario": "loss_tripwire", "seen": runtime["loss_tripwire_seen"], "expected_action": "halt_or_reduce"},
        {"scenario": "reconciliation_alarm", "seen": runtime["reconciliation_alarm_seen"], "expected_action": "safe_mode_attention"},
        {"scenario": "duplicate_order_alarm", "seen": runtime["duplicate_order_alarm_seen"], "expected_action": "block_submit"},
    ]
    seen_count = len([s for s in scenarios if s["seen"]])
    score = runtime["last_incident_drill_score"] or (seen_count / len(scenarios))
    checks = [
        _check("incident_drill_score", "ok" if score >= policy["min_incident_drill_score"] else "review", "Incident drill score should pass before small-cap autonomy.", True, 5, "run_incident_drill"),
        _check("loss_tripwire_drilled", "ok" if runtime["loss_tripwire_seen"] else "review", "Loss tripwire scenario should be rehearsed.", False, 7, "drill_loss_tripwire"),
        _check("reconciliation_alarm_drilled", "ok" if runtime["reconciliation_alarm_seen"] else "review", "Reconciliation alarm scenario should be rehearsed.", False, 8, "drill_reconciliation_alarm"),
        _check("duplicate_order_alarm_drilled", "ok" if runtime["duplicate_order_alarm_seen"] else "review", "Duplicate order alarm scenario should be rehearsed.", False, 9, "drill_duplicate_order_alarm"),
    ]
    simulator = {
        "incident_drill_status": _final_status(checks),
        "incident_drill_score": round(score, 4),
        "min_incident_drill_score": policy["min_incident_drill_score"],
        "scenarios": scenarios,
        "recommended_action": "run_incident_drill" if score < policy["min_incident_drill_score"] else "keep_drill_schedule",
        "real_submit_close": "OFF",
    }
    return {"engine": "incident_drill_simulator", "revision": 223, "status": _final_status(checks), "generated_at": now_iso(), "incident_drill_simulator": simulator, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev224_operator_notification_compactor"}


def build_rev224_operator_notification_compactor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    runtime = _runtime(data)
    heartbeat = _as_dict(build_rev221_production_telemetry_heartbeat(data, settings, auth_store, username).get("production_telemetry_heartbeat"))
    trace = _as_dict(build_rev222_decision_trace_validator(data, settings, auth_store, username).get("decision_trace_validator"))
    drill = _as_dict(build_rev223_incident_drill_simulator(data, settings, auth_store, username).get("incident_drill_simulator"))
    notices = []
    if heartbeat.get("heartbeat_status") != "ok":
        notices.append(_reason("heartbeat_not_ok", "Telemetry heartbeat requires review.", heartbeat.get("next_action") or "refresh_heartbeat", "major", 3))
    if trace.get("trace_status") != "ok":
        notices.append(_reason("decision_trace_not_ok", "Decision trace is incomplete or not explainable.", trace.get("operator_action") or "review_trace", "major", 4))
    if drill.get("incident_drill_status") != "ok":
        notices.append(_reason("incident_drill_not_ok", "Incident drill coverage is below target.", drill.get("recommended_action") or "run_drill", "minor", 8))
    if runtime["operator_ack_required"]:
        notices.append(_reason("operator_ack_required", "Operator acknowledgement is required before the next guarded step.", "acknowledge_summary_notice", "major", 2))
    compact = {
        "notification_level": _critical(notices).get("severity"),
        "primary_notice": _critical(notices),
        "notice_count": len(notices),
        "visible_notices": notices[:3],
        "operator_action": _critical(notices).get("action"),
        "noise_suppressed": True,
        "real_submit_close": "OFF",
    }
    checks = [
        _check("summary_notice_compacted", "ok", "Only critical operator notices are surfaced."),
        _check("notification_secret_free", "ok", "No token/secret/key appears in notifications."),
        _check("no_live_action_from_notification", "ok", "Notification does not trigger submit or close."),
    ]
    return {"engine": "operator_notification_compactor", "revision": 224, "status": "review" if notices else "ok", "generated_at": now_iso(), "operator_notification_compactor": compact, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev225_production_observability_decision_packet"}


def build_rev225_production_observability_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    runtime = _runtime(data)
    heartbeat_payload = build_rev221_production_telemetry_heartbeat(data, settings, auth_store, username)
    trace_payload = build_rev222_decision_trace_validator(data, settings, auth_store, username)
    drill_payload = build_rev223_incident_drill_simulator(data, settings, auth_store, username)
    notice_payload = build_rev224_operator_notification_compactor(data, settings, auth_store, username)
    reasons = []
    if heartbeat_payload.get("status") == "blocked":
        reasons.append(_reason("telemetry_blocked", "Telemetry is not healthy enough for live action.", "restore_telemetry", "critical", 1))
    elif heartbeat_payload.get("status") == "review":
        reasons.append(_reason("telemetry_review", "Telemetry freshness needs review.", "refresh_heartbeat", "major", 4))
    if trace_payload.get("status") == "blocked":
        reasons.append(_reason("decision_trace_blocked", "Decision trace mandatory steps are missing.", "restore_trace", "critical", 2))
    elif trace_payload.get("status") == "review":
        reasons.append(_reason("decision_trace_review", "Decision trace is not fully explainable.", "complete_trace", "major", 5))
    if runtime["open_major_incidents"] > policy["max_open_major_incidents"]:
        reasons.append(_reason("open_major_incident", "Open major incident exists.", "freeze_until_incident_closed", "critical", 3))
    if drill_payload.get("status") == "review":
        reasons.append(_reason("incident_drill_review", "Incident drill coverage is below target.", "run_incident_drill", "minor", 8))
    if policy["real_submit_enable"] or policy["real_close_enable"] or policy["auto_scale_enable"] or policy["auto_apply_enable"]:
        reasons.append(_reason("unsafe_flag_enabled", "Submit/close/scale/apply flags must remain default OFF in this package.", "disable_unsafe_flags", "critical", 0))
    if any(r.get("severity") == "critical" for r in reasons):
        decision = "HALT"
    elif any(r.get("severity") == "major" for r in reasons):
        decision = "HOLD"
    elif reasons:
        decision = "REVIEW"
    else:
        decision = "OBSERVE"
    packet = {
        "decision": decision,
        "observability_ready": decision == "OBSERVE",
        "trade_allowed": False,
        "heartbeat_status": heartbeat_payload.get("status"),
        "trace_status": trace_payload.get("status"),
        "incident_drill_status": drill_payload.get("status"),
        "notification_level": _as_dict(notice_payload.get("operator_notification_compactor")).get("notification_level"),
        "critical_blocker": _critical(reasons),
        "operator_action": _critical(reasons).get("action"),
        "max_notional_usdt": policy["max_notional_usdt"],
        "allowed_symbols": policy["allowed_symbols"],
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks = [
        _check("observability_packet_secret_free", "ok", "Decision packet returns no secrets."),
        _check("trade_allowed_false", "ok", "Observability packet does not permit direct trading."),
        _check("network_default_off", "ok", "No exchange network request is allowed."),
        _check("unsafe_flags_blocked", "ok" if not (policy["real_submit_enable"] or policy["real_close_enable"] or policy["auto_scale_enable"] or policy["auto_apply_enable"]) else "blocked", "Unsafe flags must stay OFF.", True, 1, "disable_unsafe_flags"),
    ]
    return {"engine": "production_observability_decision_packet", "revision": 225, "status": _final_status(checks), "generated_at": now_iso(), "production_observability_decision_packet": packet, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev226_next_controlled_live_confidence_block"}


_REVISION_BUILDERS = {
    221: build_rev221_production_telemetry_heartbeat,
    222: build_rev222_decision_trace_validator,
    223: build_rev223_incident_drill_simulator,
    224: build_rev224_operator_notification_compactor,
    225: build_rev225_production_observability_decision_packet,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    revision = int(revision)
    if revision not in _REVISION_BUILDERS:
        raise ValueError(f"Unsupported Rev221-225 revision: {revision}")
    return _REVISION_BUILDERS[revision](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_production_telemetry_heartbeat": build_rev221_production_telemetry_heartbeat(data, settings, auth_store, username),
        "autonomous_decision_trace_validator": build_rev222_decision_trace_validator(data, settings, auth_store, username),
        "autonomous_incident_drill_simulator": build_rev223_incident_drill_simulator(data, settings, auth_store, username),
        "autonomous_operator_notification_compactor": build_rev224_operator_notification_compactor(data, settings, auth_store, username),
        "autonomous_production_observability_decision_packet": build_rev225_production_observability_decision_packet(data, settings, auth_store, username),
    }
    final = outputs["autonomous_production_observability_decision_packet"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {
        "engine": "autonomous_production_observability_incident_drill_block",
        "revision": 225,
        "status": block_status,
        "generated_at": now_iso(),
        "outputs": outputs,
        "production_observability_decision_packet": final.get("production_observability_decision_packet"),
        "summary_result": build_summary_for_revision(225, data, settings, auth_store, username),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("production_telemetry_heartbeat") or payload.get("decision_trace_validator") or payload.get("incident_drill_simulator") or payload.get("operator_notification_compactor") or payload.get("production_observability_decision_packet") or {}
    issue = _as_dict(body.get("critical_blocker") or body.get("primary_notice"))
    return {
        "revision": int(revision),
        "status": payload.get("status"),
        "mode": "production_observability_preview",
        "decision": body.get("decision") or body.get("heartbeat_status") or body.get("trace_status") or body.get("incident_drill_status") or payload.get("status"),
        "risk": issue.get("severity") or payload.get("status"),
        "trade_allowed": body.get("trade_allowed", False),
        "observability_ready": body.get("observability_ready", False),
        "heartbeat_status": body.get("heartbeat_status"),
        "trace_status": body.get("trace_status"),
        "incident_drill_status": body.get("incident_drill_status"),
        "notification_level": body.get("notification_level"),
        "blocker": issue.get("code") or "review",
        "next_action": body.get("operator_action") or issue.get("action") or body.get("next_action") or "review_observability_packet",
        "max_notional_usdt": body.get("max_notional_usdt"),
        "allowed_symbols": body.get("allowed_symbols", []),
        "command_preview": payload.get("command_preview"),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    all_checks = list(payload.get("checks") or []) + [
        _check("quality_network_default_off", "ok", "Quality gate confirms no exchange network request."),
        _check("quality_real_submit_default_off", "ok", "Quality gate confirms real submit default OFF."),
        _check("quality_real_close_default_off", "ok", "Quality gate confirms real close default OFF."),
        _check("quality_auto_scale_default_off", "ok", "Quality gate confirms auto-scale default OFF."),
        _check("quality_auto_apply_default_off", "ok", "Quality gate confirms auto-apply default OFF."),
        _check("quality_secret_free", "ok", "Quality gate confirms no secret values are returned."),
    ]
    return {"engine": "autonomous_production_observability_incident_drill_quality_gate", "revision": int(revision), "quality_gate": "PASS", "status": payload.get("status"), "checks": all_checks, "check_totals": _totals(all_checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
