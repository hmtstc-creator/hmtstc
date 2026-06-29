from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "approved"}


def _reason(code: str, message: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "message": message, "action": action, "severity": severity, "priority": int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason("none", "No blocker.", "no_action", "ok", 999)
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda r: (weight.get(str(r.get("severity")), 2), int(r.get("priority", 50))))[0]


def _check(name: str, status: str, message: str, detail: dict | None = None) -> dict:
    return {"name": name, "status": status, "message": message, "detail": detail or {}}


def _totals(checks: list[dict]) -> dict:
    return {
        "total": len(checks),
        "ok": sum(1 for c in checks if c.get("status") == "ok"),
        "review": sum(1 for c in checks if c.get("status") == "review"),
        "blocked": sum(1 for c in checks if c.get("status") == "blocked"),
    }


def _final_status(checks: list[dict]) -> str:
    if any(c.get("status") == "blocked" for c in checks):
        return "blocked"
    if any(c.get("status") == "review" for c in checks):
        return "review"
    return "ok"


def _command_preview() -> dict:
    return {
        "places_order": False,
        "sends_exchange_request": False,
        "submits_close_order": False,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_scale": False,
        "auto_apply": False,
        "read_only": True,
        "approval_gated": True,
    }


def _policy(settings: dict | None, auth_store: dict | None = None) -> dict:
    settings = _as_dict(settings)
    live = _as_dict(settings.get("limited_live") or settings.get("live") or {})
    risk = _as_dict(settings.get("risk") or settings.get("risk_profile") or {})
    auth_store = _as_dict(auth_store)
    return {
        "owner_approval_required": True,
        "owner_approval": _truthy(live.get("owner_approval") or live.get("owner_approved") or settings.get("owner_approval")),
        "activation_token_preview": str(live.get("activation_token_preview") or settings.get("activation_token_preview") or "").strip(),
        "approval_scope": str(live.get("approval_scope") or "micro_live_preview").strip(),
        "session_id": str(live.get("session_id") or settings.get("session_id") or "preview-session").strip(),
        "allowed_symbols": _as_list(live.get("allowed_symbols")) or _as_list(settings.get("allowed_symbols")) or ["BTCUSDT", "ETHUSDT"],
        "max_notional": _safe_float(live.get("max_notional") or risk.get("max_notional") or settings.get("max_notional_usdt"), 25.0),
        "max_daily_loss": _safe_float(live.get("max_daily_loss") or risk.get("max_daily_loss") or settings.get("max_daily_loss_usdt"), 5.0),
        "session_minutes": _safe_int(live.get("session_minutes") or settings.get("session_minutes"), 30),
        "real_submit_enable": _truthy(settings.get("real_submit_enable") or live.get("real_submit_enable")),
        "real_close_enable": _truthy(settings.get("real_close_enable") or live.get("real_close_enable")),
        "auto_scale": _truthy(settings.get("auto_scale") or live.get("auto_scale")),
        "auto_apply": _truthy(settings.get("auto_apply") or live.get("auto_apply")),
        "owner_role_available": bool(_as_dict(auth_store).get("users") or auth_store),
    }


def _upstream(data: dict | None) -> dict:
    data = _as_dict(data)
    return {
        "risk_firewall": _as_dict(data.get("autonomous_live_risk_firewall_block") or data.get("live_risk_firewall_decision_packet")),
        "execution_reconciliation": _as_dict(data.get("autonomous_real_execution_reconciliation_block") or data.get("execution_reconciliation_report")),
        "opportunity_quality": _as_dict(data.get("autonomous_opportunity_quality_block") or data.get("autonomous_opportunity_quality_report")),
        "capital_preservation": _as_dict(data.get("autonomous_capital_preservation_usdt_dominance_block") or data.get("capital_preservation_decision_packet")),
        "production_data_integrity": _as_dict(data.get("autonomous_production_data_integrity_block") or data.get("production_data_integrity_report")),
    }


def _upstream_status(upstream: dict, key: str) -> str:
    payload = _as_dict(upstream.get(key))
    nested = _as_dict(payload.get(key))
    return str(payload.get("status") or nested.get("status") or nested.get("decision") or "review")


def _blockers(data: dict | None, settings: dict | None, auth_store: dict | None = None) -> list[dict]:
    policy = _policy(settings, auth_store)
    upstream = _upstream(data)
    reasons: list[dict] = []
    if policy["real_submit_enable"] or policy["real_close_enable"]:
        reasons.append(_reason("real_execution_flag_enabled", "Real submit/close flags must stay OFF during approval UX preview.", "turn_real_execution_flags_off", "critical", 0))
    if policy["auto_scale"] or policy["auto_apply"]:
        reasons.append(_reason("auto_scale_or_apply_enabled", "Auto-scale/auto-apply must stay OFF before owner-gated limited-live.", "turn_auto_scale_apply_off", "critical", 1))
    if not policy["owner_approval"]:
        reasons.append(_reason("owner_approval_missing", "Owner approval has not been granted for this limited-live session.", "review_and_approve_or_hold", "major", 10))
    if not policy["activation_token_preview"]:
        reasons.append(_reason("activation_token_preview_missing", "Activation token preview is missing; no live action can pass without preview scope.", "generate_activation_preview", "major", 11))
    if not policy["allowed_symbols"]:
        reasons.append(_reason("allowed_symbols_missing", "No allowed symbols are available for session preview.", "set_allowed_symbols", "major", 12))
    if policy["max_notional"] <= 0:
        reasons.append(_reason("max_notional_invalid", "Max notional must be positive and capped.", "set_micro_notional_cap", "major", 13))
    if policy["max_daily_loss"] <= 0:
        reasons.append(_reason("max_daily_loss_invalid", "Daily hard stop must be positive and explicit.", "set_daily_hard_stop", "major", 14))
    for key in ("production_data_integrity", "execution_reconciliation", "capital_preservation", "opportunity_quality"):
        status = _upstream_status(upstream, key)
        if status in {"blocked", "inconsistent", "emergency"}:
            reasons.append(_reason(f"{key}_blocked", f"{key} upstream status blocks approval UX.", "hold_until_upstream_ok", "major", 20))
    return reasons


def build_rev246_owner_approval_status_card(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings, auth_store)
    reasons = _blockers(data, settings, auth_store)
    critical = _critical(reasons)
    card = {
        "owner_approval": "approved" if policy["owner_approval"] else "missing",
        "approval_required": True,
        "scope": policy["approval_scope"],
        "session_id": policy["session_id"],
        "max_notional": policy["max_notional"],
        "allowed_symbols": policy["allowed_symbols"],
        "critical_blocker": critical,
        "owner_action": critical.get("action"),
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks = [
        _check("owner_approval_gate", "ok" if policy["owner_approval"] else "review", "Owner approval is required before live action."),
        _check("real_execution_default_off", "ok" if not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "Real submit/close stay OFF in UX block."),
        _check("auto_apply_scale_default_off", "ok" if not policy["auto_scale"] and not policy["auto_apply"] else "blocked", "Auto-apply and auto-scale stay OFF."),
    ]
    return {"engine": "owner_approval_status_card", "revision": 246, "status": _final_status(checks), "generated_at": now_iso(), "owner_approval_status_card": card, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev247_activation_blocker_compact_view"}


def build_rev247_activation_blocker_compact_view(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    reasons = sorted(_blockers(data, settings, auth_store), key=lambda r: int(r.get("priority", 50)))
    critical = _critical(reasons)
    view = {
        "blocker_count": len(reasons),
        "critical_blocker": critical,
        "visible_blocker": critical.get("code"),
        "noise_suppressed": max(0, len(reasons) - 1),
        "operator_action": critical.get("action"),
        "decision": "blocked" if critical.get("severity") in {"critical", "major"} else "ready",
    }
    checks = [_check("compact_blocker_priority", "ok", "Only the highest-priority blocker is surfaced in Summary."), _check("blocker_noise_control", "ok", "Secondary blockers stay below the fold.")]
    return {"engine": "activation_blocker_compact_view", "revision": 247, "status": "review" if reasons else "ok", "generated_at": now_iso(), "activation_blocker_compact_view": view, "blockers": reasons[:5], "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev248_session_approval_preview_panel"}


def build_rev248_session_approval_preview_panel(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings, auth_store)
    reasons = _blockers(data, settings, auth_store)
    critical = _critical(reasons)
    preview = {
        "session_id": policy["session_id"],
        "scope": policy["approval_scope"],
        "session_minutes": policy["session_minutes"],
        "allowed_symbols": policy["allowed_symbols"],
        "max_notional": policy["max_notional"],
        "max_daily_loss": policy["max_daily_loss"],
        "activation_token_preview_present": bool(policy["activation_token_preview"]),
        "activation_token_value_returned": False,
        "approval_ready": critical.get("severity") == "ok",
        "next_owner_action": "approve_limited_session" if critical.get("severity") == "ok" else critical.get("action"),
        "real_submit_close": "OFF",
    }
    checks = [
        _check("token_not_returned", "ok", "Activation token is treated as sensitive and never returned."),
        _check("session_boundary_present", "ok" if policy["session_id"] and policy["session_minutes"] > 0 else "review", "Session boundary is explicit."),
        _check("micro_caps_present", "ok" if policy["max_notional"] > 0 and policy["max_daily_loss"] > 0 else "review", "Micro notional and daily loss caps are explicit."),
    ]
    return {"engine": "session_approval_preview_panel", "revision": 248, "status": _final_status(checks), "generated_at": now_iso(), "session_approval_preview_panel": preview, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev249_emergency_halt_reduce_visual_state"}


def build_rev249_emergency_halt_reduce_visual_state(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    reasons = _blockers(data, settings, auth_store)
    critical = _critical(reasons)
    if critical.get("severity") == "critical":
        visual_state = "EMERGENCY"
    elif critical.get("severity") == "major":
        visual_state = "HOLD"
    elif reasons:
        visual_state = "REVIEW"
    else:
        visual_state = "READY_PREVIEW"
    state = {
        "visual_state": visual_state,
        "tone": "danger" if visual_state == "EMERGENCY" else "warning" if visual_state in {"HOLD", "REVIEW"} else "ok",
        "summary_text": "HOLD" if visual_state in {"HOLD", "REVIEW"} else visual_state,
        "critical_blocker": critical,
        "allowed_operator_buttons": ["review_blocker", "keep_hold"] if visual_state != "READY_PREVIEW" else ["review_preview", "owner_approve_preview"],
        "disabled_actions": ["auto_submit", "auto_close", "auto_scale", "auto_apply"],
        "real_submit_close": "OFF",
    }
    checks = [_check("unsafe_buttons_disabled", "ok", "Submit/close/scale/apply actions remain disabled in UX state."), _check("visual_state_defined", "ok", "Operator gets one compact visual state.")]
    return {"engine": "emergency_halt_reduce_visual_state", "revision": 249, "status": "ok" if visual_state == "READY_PREVIEW" else "review", "generated_at": now_iso(), "emergency_halt_reduce_visual_state": state, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev250_limited_live_operator_ux_packet"}


def build_rev250_limited_live_operator_ux_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    card_payload = build_rev246_owner_approval_status_card(data, settings, auth_store, username)
    blocker_payload = build_rev247_activation_blocker_compact_view(data, settings, auth_store, username)
    preview_payload = build_rev248_session_approval_preview_panel(data, settings, auth_store, username)
    state_payload = build_rev249_emergency_halt_reduce_visual_state(data, settings, auth_store, username)
    card = _as_dict(card_payload.get("owner_approval_status_card"))
    blocker = _as_dict(blocker_payload.get("activation_blocker_compact_view"))
    preview = _as_dict(preview_payload.get("session_approval_preview_panel"))
    state = _as_dict(state_payload.get("emergency_halt_reduce_visual_state"))
    critical = _as_dict(blocker.get("critical_blocker"))
    ready = bool(preview.get("approval_ready")) and card.get("owner_approval") == "approved"
    decision = "READY_FOR_OWNER_APPROVED_PREVIEW" if ready else "HOLD"
    packet = {
        "decision": decision,
        "operator_headline": decision if ready else "HOLD",
        "critical_blocker": critical,
        "owner_action": "approve_limited_session" if ready else critical.get("action"),
        "approval_status": card.get("owner_approval"),
        "session_preview": preview,
        "visual_state": state.get("visual_state"),
        "live_action_scope": preview.get("scope"),
        "allowed_max_notional": preview.get("max_notional"),
        "allowed_symbols": preview.get("allowed_symbols"),
        "stop_conditions": ["daily_hard_stop", "risk_firewall_halt", "reconciliation_inconsistent", "manual_attention", "session_timeout"],
        "summary_noise_policy": "show_one_blocker_only",
        "trade_allowed": False,
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks: list[dict] = []
    for payload in (card_payload, blocker_payload, preview_payload, state_payload):
        checks.extend(_as_list(payload.get("checks")))
    status = "ok" if ready else "review"
    if any(c.get("status") == "blocked" for c in checks):
        status = "blocked"
    return {"engine": "limited_live_operator_ux_packet", "revision": 250, "status": status, "generated_at": now_iso(), "limited_live_operator_ux_packet": packet, "owner_approval_status_card": card, "activation_blocker_compact_view": blocker, "session_approval_preview_panel": preview, "emergency_halt_reduce_visual_state": state, "checks": checks, "check_totals": _totals(checks), "summary_result": build_summary_for_revision(250, data, settings, auth_store, username), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev251_micro_live_execution_dry_proof"}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builders = {
        246: build_rev246_owner_approval_status_card,
        247: build_rev247_activation_blocker_compact_view,
        248: build_rev248_session_approval_preview_panel,
        249: build_rev249_emergency_halt_reduce_visual_state,
        250: build_rev250_limited_live_operator_ux_packet,
    }
    if int(revision) not in builders:
        raise ValueError(f"Unsupported Rev246-250 operator UX revision: {revision}")
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    rev246 = build_rev246_owner_approval_status_card(data, settings, auth_store, username)
    rev247 = build_rev247_activation_blocker_compact_view(data, settings, auth_store, username)
    rev248 = build_rev248_session_approval_preview_panel(data, settings, auth_store, username)
    rev249 = build_rev249_emergency_halt_reduce_visual_state(data, settings, auth_store, username)
    rev250 = build_rev250_limited_live_operator_ux_packet(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev246, rev247, rev248, rev249, rev250):
        checks.extend(_as_list(payload.get("checks")))
    packet = rev250.get("limited_live_operator_ux_packet", {})
    return {
        "engine": "limited_live_operator_approval_ux_block",
        "revision": 250,
        "status": rev250.get("status", "review"),
        "generated_at": now_iso(),
        "rev246_owner_approval_status_card": rev246,
        "rev247_activation_blocker_compact_view": rev247,
        "rev248_session_approval_preview_panel": rev248,
        "rev249_emergency_halt_reduce_visual_state": rev249,
        "rev250_limited_live_operator_ux_packet": rev250,
        "limited_live_operator_ux_packet": packet,
        "summary_result": build_summary_for_revision(250, data, settings, auth_store, username),
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev251_micro_live_execution_dry_proof",
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username) if int(revision) != 250 else None
    if int(revision) == 250:
        reasons = _blockers(data, settings, auth_store)
        critical = _critical(reasons)
        policy = _policy(settings, auth_store)
        ready = not reasons and policy["owner_approval"] and bool(policy["activation_token_preview"])
        return {
            "revision": 250,
            "decision": "READY_FOR_OWNER_APPROVED_PREVIEW" if ready else "HOLD",
            "operator_headline": "READY" if ready else "HOLD",
            "critical_issue": critical.get("code"),
            "owner_action": "approve_limited_session" if ready else critical.get("action"),
            "approval_status": "approved" if policy["owner_approval"] else "missing",
            "visual_state": "READY_PREVIEW" if ready else "HOLD",
            "allowed_max_notional": policy["max_notional"],
            "allowed_symbols": policy["allowed_symbols"],
            "session_minutes": policy["session_minutes"],
            "trade_allowed": False,
            "real_submit_close": "OFF",
            "auto_scale": "OFF",
            "auto_apply": "OFF",
        }
    body_key = {
        246: "owner_approval_status_card",
        247: "activation_blocker_compact_view",
        248: "session_approval_preview_panel",
        249: "emergency_halt_reduce_visual_state",
    }.get(int(revision), "summary")
    body = _as_dict(payload.get(body_key)) if payload else {}
    return {
        "revision": int(revision),
        "decision": body.get("decision") or body.get("visual_state") or payload.get("status", "review"),
        "critical_issue": _as_dict(body.get("critical_blocker")).get("code"),
        "owner_action": body.get("owner_action") or body.get("operator_action") or body.get("next_owner_action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    command = payload.get("command_preview", {})
    failures = []
    if command.get("places_order") or command.get("sends_exchange_request") or command.get("submits_close_order"):
        failures.append("unexpected_execution_side_effect")
    if command.get("real_submit_default_off") is not True or command.get("real_close_default_off") is not True:
        failures.append("real_execution_not_default_off")
    if payload.get("contains_secret") or payload.get("secret_values_returned"):
        failures.append("secret_leak")
    if command.get("auto_scale") or command.get("auto_apply"):
        failures.append("auto_scale_or_apply_enabled")
    return {"quality_gate": "FAIL" if failures else "PASS", "revision": int(revision), "engine": payload.get("engine"), "status": payload.get("status"), "failures": failures, "command_preview": command, "checked_at": now_iso()}
