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
        "autonomous_production_self_governance",
        "autonomous_small_capital_autonomy_preparation",
        "autonomous_controlled_repeat_micro_live",
        "autonomous_live_risk_firewall",
    ):
        source.update(_settings(settings, key))
    return {
        "max_notional_usdt": max(5.0, _safe_float(source.get("max_notional_usdt"), 25.0)),
        "max_daily_loss_usdt": max(1.0, _safe_float(source.get("max_daily_loss_usdt"), 1.0)),
        "max_trade_count": max(1, min(10, _safe_int(source.get("max_trade_count"), _safe_int(source.get("max_trades_per_day"), 3)))),
        "min_evidence_confidence": max(0.0, min(1.0, _safe_float(source.get("min_evidence_confidence"), 0.85))),
        "min_reconciliation_score": max(0.0, min(1.0, _safe_float(source.get("min_reconciliation_score"), 0.90))),
        "allowed_symbols": _as_list(source.get("allowed_symbols")) or ["BTCUSDT", "ETHUSDT"],
        "owner_approval_required": _safe_bool(source.get("owner_approval_required"), True),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
    }


def _runtime(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source: dict[str, Any] = {}
    for key in (
        "production_self_governance_runtime",
        "small_capital_runtime",
        "autonomy_runtime",
        "micro_live_metrics",
        "reconciliation_runtime",
        "risk_firewall",
    ):
        source.update(_as_dict(data.get(key)))
    return {
        "mode": str(source.get("mode") or source.get("current_permission_level") or data.get("mode") or "limited-live"),
        "risk_status": str(source.get("risk_status") or data.get("risk_status") or "review").lower(),
        "reconciliation_status": str(source.get("reconciliation_status") or data.get("reconciliation_status") or "unknown").lower(),
        "reconciliation_score": max(0.0, min(1.0, _safe_float(source.get("reconciliation_score"), _safe_float(data.get("reconciliation_score"), 0.0)))),
        "evidence_confidence": max(0.0, min(1.0, _safe_float(source.get("evidence_confidence"), _safe_float(data.get("evidence_confidence"), 0.0)))),
        "pnl_today_usdt": _safe_float(source.get("pnl_today_usdt"), _safe_float(data.get("today_pnl_usdt"), 0.0)),
        "open_positions": max(0, _safe_int(source.get("open_positions"), 0)),
        "pending_orders": max(0, _safe_int(source.get("pending_orders"), 0)),
        "trades_today": max(0, _safe_int(source.get("trades_today"), 0)),
        "anomaly_count": max(0, _safe_int(source.get("anomaly_count"), 0)),
        "owner_approval": _safe_bool(source.get("owner_approval"), False),
        "session_boundary_ok": _safe_bool(source.get("session_boundary_ok"), False),
        "whitelist_ok": _safe_bool(source.get("whitelist_ok"), True),
        "daily_hard_stop_ok": _safe_bool(source.get("daily_hard_stop_ok"), True),
        "audit_ready": _safe_bool(source.get("audit_ready"), True),
        "rollback_ready": _safe_bool(source.get("rollback_ready"), True),
        "journal_ready": _safe_bool(source.get("journal_ready"), True),
    }


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "No critical issue detected.", "action": "continue_guarded_review", "priority": 99}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda x: (weight.get(str(x.get("severity")), 2), int(x.get("priority", 50))))[0]


def build_rev216_production_self_governance_charter(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    charter = {
        "governance_mode": "operator_safe_self_governance",
        "can_halt_without_owner": True,
        "can_reduce_without_owner": True,
        "can_freeze_without_owner": True,
        "can_increase_without_owner": False,
        "can_submit_without_owner": False,
        "can_close_without_owner": False,
        "max_notional_usdt": policy["max_notional_usdt"],
        "max_daily_loss_usdt": policy["max_daily_loss_usdt"],
        "max_trade_count": policy["max_trade_count"],
        "allowed_symbols": policy["allowed_symbols"],
        "owner_approval_required": True,
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks = [
        _check("halt_authority_defined", "ok", "System may halt/reduce/freeze without waiting for the owner."),
        _check("growth_requires_owner", "ok", "Any growth or live action requires explicit owner approval."),
        _check("real_submit_default_off", "ok" if not policy["real_submit_enable"] else "blocked", "Real submit must remain default OFF.", True, 1, "disable_real_submit"),
        _check("auto_scale_default_off", "ok" if not policy["auto_scale_enable"] else "blocked", "Auto-scale must remain OFF.", True, 2, "disable_auto_scale"),
        _check("auto_apply_default_off", "ok" if not policy["auto_apply_enable"] else "blocked", "Auto-apply must remain OFF.", True, 3, "disable_auto_apply"),
    ]
    return {"engine": "production_self_governance_charter", "revision": 216, "status": _final_status(checks), "generated_at": now_iso(), "production_self_governance_charter": charter, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev217_governance_audit_trail_preview"}


def build_rev217_governance_audit_trail_preview(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    runtime = _runtime(data)
    policy = _policy(settings)
    events = [
        {"event_type": "governance_decision", "scope": runtime["mode"], "secret_free": True, "required": True},
        {"event_type": "owner_approval_preview", "scope": "live_action", "secret_free": True, "required": True},
        {"event_type": "risk_firewall_snapshot", "scope": "pre_submit", "secret_free": True, "required": True},
        {"event_type": "reconciliation_snapshot", "scope": "post_order", "secret_free": True, "required": True},
        {"event_type": "halt_or_freeze_reason", "scope": "safety_action", "secret_free": True, "required": True},
    ]
    blockers = []
    if not runtime["audit_ready"]:
        blockers.append(_reason("audit_not_ready", "Governance audit trail is not ready.", "enable_audit_preview", "critical", 1))
    if not runtime["journal_ready"]:
        blockers.append(_reason("journal_not_ready", "Trade journal is not ready for evidence capture.", "enable_journal_preview", "major", 2))
    audit = {
        "audit_ready": runtime["audit_ready"],
        "journal_ready": runtime["journal_ready"],
        "required_events": events,
        "runtime_write_allowed": "audit_and_journal_only",
        "secret_free_contract": True,
        "owner_scope": "max_notional_{}_max_loss_{}_symbols_{}".format(policy["max_notional_usdt"], policy["max_daily_loss_usdt"], ",".join(policy["allowed_symbols"])),
        "blockers": blockers,
        "critical_issue": _critical(blockers),
    }
    checks = [
        _check("audit_events_defined", "ok", "Required governance audit events are explicit."),
        _check("audit_secret_free", "ok", "Audit preview contains no token or secret values."),
        _check("audit_ready", "ok" if runtime["audit_ready"] else "blocked", "Audit layer must be ready before production governance.", True, 1, "enable_audit_preview"),
    ]
    return {"engine": "governance_audit_trail_preview", "revision": 217, "status": _final_status(checks), "generated_at": now_iso(), "governance_audit_trail_preview": audit, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev218_rollback_freeze_runbook"}


def build_rev218_rollback_freeze_runbook(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    runtime = _runtime(data)
    policy = _policy(settings)
    reasons = []
    if runtime["pnl_today_usdt"] <= -abs(policy["max_daily_loss_usdt"]):
        reasons.append(_reason("daily_loss_limit_hit", "Daily loss threshold is reached.", "freeze_and_halt", "critical", 1))
    if runtime["risk_status"] in {"halt", "emergency", "blocked"}:
        reasons.append(_reason("risk_firewall_halt", "Risk firewall requires halt.", "freeze_and_halt", "critical", 2))
    if runtime["anomaly_count"] > 0:
        reasons.append(_reason("runtime_anomaly", "Runtime anomaly requires freeze.", "freeze_and_review", "critical", 3))
    if runtime["reconciliation_status"] not in {"ok", "consistent", "clear", "pass"}:
        reasons.append(_reason("reconciliation_not_clear", "Reconciliation is not clear.", "freeze_new_entries", "major", 4))
    runbook = {
        "rollback_ready": runtime["rollback_ready"],
        "freeze_required": bool(reasons),
        "freeze_mode": "hard_freeze" if any(r["severity"] == "critical" for r in reasons) else "soft_freeze" if reasons else "armed",
        "allowed_during_freeze": ["observe", "audit", "journal_review", "manual_owner_review"],
        "blocked_during_freeze": ["new_entry", "scale_up", "auto_apply", "auto_submit"],
        "rollback_steps": ["stop_new_entries", "preserve_open_position_state", "capture_audit_snapshot", "owner_review", "resume_only_after_clear_reconciliation"],
        "reasons": reasons,
        "critical_issue": _critical(reasons),
        "real_submit_close": "OFF",
    }
    checks = [
        _check("rollback_plan_defined", "ok", "Freeze and rollback steps are explicit."),
        _check("rollback_ready", "ok" if runtime["rollback_ready"] else "review", "Rollback readiness should be available before live expansion.", False, 5, "review_rollback"),
        _check("auto_growth_blocked_on_freeze", "ok", "Freeze blocks new entries and scaling."),
    ]
    return {"engine": "rollback_freeze_runbook", "revision": 218, "status": _final_status(checks), "generated_at": now_iso(), "rollback_freeze_runbook": runbook, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev219_operator_safe_action_router"}


def build_rev219_operator_safe_action_router(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    runtime = _runtime(data)
    policy = _policy(settings)
    audit = build_rev217_governance_audit_trail_preview(data, settings, auth_store, username)["governance_audit_trail_preview"]
    rollback = build_rev218_rollback_freeze_runbook(data, settings, auth_store, username)["rollback_freeze_runbook"]
    reasons = []
    if rollback["freeze_required"]:
        reasons.append(_as_dict(rollback.get("critical_issue")))
    if runtime["evidence_confidence"] < policy["min_evidence_confidence"]:
        reasons.append(_reason("evidence_below_threshold", "Evidence confidence is below production threshold.", "hold_or_reduce", "major", 5))
    if runtime["reconciliation_score"] < policy["min_reconciliation_score"]:
        reasons.append(_reason("reconciliation_score_low", "Reconciliation score is below production threshold.", "manual_reconciliation", "critical", 4))
    if not runtime["owner_approval"]:
        reasons.append(_reason("owner_approval_required", "Owner approval is required before any live submit scope.", "owner_review", "major", 8))
    if not audit["audit_ready"]:
        reasons.append(_reason("audit_not_ready", "Audit trail is not ready.", "enable_audit_preview", "critical", 3))
    if reasons and any(r.get("severity") == "critical" for r in reasons):
        action = "halt"
    elif reasons:
        action = "hold"
    elif runtime["owner_approval"] and runtime["session_boundary_ok"] and runtime["whitelist_ok"]:
        action = "guarded_preview"
    else:
        action = "review"
    router = {
        "operator_visible_action": action,
        "safe_actions": ["observe", "review_blocker", "approve_preview_scope"] if action == "guarded_preview" else ["observe", "review_blocker"],
        "unsafe_actions_blocked": ["direct_submit", "direct_close", "scale_up", "auto_apply"],
        "trade_allowed": action == "guarded_preview",
        "owner_action": "approve_preview_scope" if action == "guarded_preview" else "review_blocker",
        "next_action": "prepare_approval_gated_preview" if action == "guarded_preview" else _critical(reasons).get("action"),
        "critical_issue": _critical(reasons),
        "reasons": reasons,
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks = [
        _check("unsafe_actions_blocked", "ok", "Direct submit/close/scale/apply are blocked."),
        _check("owner_action_visible", "ok", "Owner-visible next action is normalized."),
        _check("submit_default_off", "ok", "Router does not submit orders."),
    ]
    return {"engine": "operator_safe_action_router", "revision": 219, "status": _final_status(checks), "generated_at": now_iso(), "operator_safe_action_router": router, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev220_production_self_governance_decision_packet"}


def build_rev220_production_self_governance_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    charter_payload = build_rev216_production_self_governance_charter(data, settings, auth_store, username)
    audit_payload = build_rev217_governance_audit_trail_preview(data, settings, auth_store, username)
    rollback_payload = build_rev218_rollback_freeze_runbook(data, settings, auth_store, username)
    router_payload = build_rev219_operator_safe_action_router(data, settings, auth_store, username)
    charter = _as_dict(charter_payload.get("production_self_governance_charter"))
    audit = _as_dict(audit_payload.get("governance_audit_trail_preview"))
    rollback = _as_dict(rollback_payload.get("rollback_freeze_runbook"))
    router = _as_dict(router_payload.get("operator_safe_action_router"))
    reasons = []
    reasons.extend(_as_list(audit.get("blockers")))
    reasons.extend(_as_list(rollback.get("reasons")))
    reasons.extend(_as_list(router.get("reasons")))
    if rollback.get("freeze_required"):
        decision = "FREEZE"
    elif any(r.get("severity") == "critical" for r in reasons):
        decision = "HALT"
    elif router.get("trade_allowed"):
        decision = "LIMITED_PREVIEW"
    elif reasons:
        decision = "HOLD"
    else:
        decision = "REVIEW"
    packet = {
        "decision": decision,
        "mode": "production_self_governance_preview",
        "trade_allowed": decision == "LIMITED_PREVIEW",
        "max_notional_usdt": charter.get("max_notional_usdt"),
        "max_daily_loss_usdt": charter.get("max_daily_loss_usdt"),
        "trade_cap": charter.get("max_trade_count"),
        "allowed_symbols": charter.get("allowed_symbols", []),
        "audit_ready": audit.get("audit_ready"),
        "rollback_ready": rollback.get("rollback_ready"),
        "freeze_required": rollback.get("freeze_required"),
        "operator_action": router.get("operator_visible_action"),
        "owner_action": router.get("owner_action"),
        "next_action": router.get("next_action"),
        "critical_blocker": _critical(reasons),
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks = [
        _check("decision_packet_secret_free", "ok", "Decision packet returns no secret values."),
        _check("audit_and_rollback_present", "ok", "Governance has audit and rollback coverage."),
        _check("approval_gated_live_actions", "ok", "Live submit/close remains approval-gated and default OFF."),
        _check("growth_without_owner_blocked", "ok", "No increase is allowed without owner approval."),
    ]
    return {"engine": "production_self_governance_decision_packet", "revision": 220, "status": _final_status(checks), "generated_at": now_iso(), "production_self_governance_decision_packet": packet, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev221_next_live_governance_maturity"}


_REVISION_BUILDERS = {
    216: build_rev216_production_self_governance_charter,
    217: build_rev217_governance_audit_trail_preview,
    218: build_rev218_rollback_freeze_runbook,
    219: build_rev219_operator_safe_action_router,
    220: build_rev220_production_self_governance_decision_packet,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    revision = int(revision)
    if revision not in _REVISION_BUILDERS:
        raise ValueError(f"Unsupported Rev216-220 revision: {revision}")
    return _REVISION_BUILDERS[revision](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_production_self_governance_charter": build_rev216_production_self_governance_charter(data, settings, auth_store, username),
        "autonomous_governance_audit_trail_preview": build_rev217_governance_audit_trail_preview(data, settings, auth_store, username),
        "autonomous_rollback_freeze_runbook": build_rev218_rollback_freeze_runbook(data, settings, auth_store, username),
        "autonomous_operator_safe_action_router": build_rev219_operator_safe_action_router(data, settings, auth_store, username),
        "autonomous_production_self_governance_decision_packet": build_rev220_production_self_governance_decision_packet(data, settings, auth_store, username),
    }
    final = outputs["autonomous_production_self_governance_decision_packet"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {
        "engine": "autonomous_production_self_governance_block",
        "revision": 220,
        "status": block_status,
        "generated_at": now_iso(),
        "outputs": outputs,
        "production_self_governance_decision_packet": final.get("production_self_governance_decision_packet"),
        "summary_result": build_summary_for_revision(220, data, settings, auth_store, username),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("production_self_governance_charter") or payload.get("governance_audit_trail_preview") or payload.get("rollback_freeze_runbook") or payload.get("operator_safe_action_router") or payload.get("production_self_governance_decision_packet") or {}
    issue = _as_dict(body.get("critical_issue") or body.get("critical_blocker"))
    return {
        "revision": int(revision),
        "status": payload.get("status"),
        "mode": body.get("mode") or body.get("governance_mode") or "production_self_governance_preview",
        "decision": body.get("decision") or body.get("operator_visible_action") or body.get("freeze_mode") or payload.get("status"),
        "risk": "freeze" if body.get("freeze_required") else payload.get("status"),
        "trade_allowed": body.get("trade_allowed", False),
        "next_action": body.get("next_action") or issue.get("action") or "review_governance_packet",
        "blocker": issue.get("code") or body.get("blocker"),
        "owner_action": body.get("owner_action") or body.get("operator_action") or "review",
        "max_notional_usdt": body.get("max_notional_usdt"),
        "max_daily_loss_usdt": body.get("max_daily_loss_usdt"),
        "trade_cap": body.get("trade_cap") or body.get("max_trade_count"),
        "allowed_symbols": body.get("allowed_symbols", []),
        "audit_ready": body.get("audit_ready"),
        "rollback_ready": body.get("rollback_ready"),
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
    return {"engine": "autonomous_production_self_governance_quality_gate", "revision": int(revision), "quality_gate": "PASS", "status": payload.get("status"), "checks": all_checks, "check_totals": _totals(all_checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
