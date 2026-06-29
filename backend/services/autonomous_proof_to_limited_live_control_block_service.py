from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_live_edge_profitability_proof_block_service import build_rev175_profitability_proof_decision_packet
from services.autonomous_live_launch_readiness_block_service import build_rev155_live_launch_packet_v1
from services.autonomous_controlled_micro_real_pilot_readiness_block_service import build_rev160_micro_real_pilot_decision_packet
from services.autonomous_capital_scaling_profit_defense_block_service import build_rev145_capital_protection_summary


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "clear", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency", "stopped", "fail"}:
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


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    value = settings.get(key)
    return value if isinstance(value, dict) else {}


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {"name": name, "status": status, "required": required, "detail": detail}


def _totals(checks: list[dict]) -> dict:
    return {"total": len(checks), "ok": len([c for c in checks if c.get("status") == "ok"]), "review": len([c for c in checks if c.get("status") == "review"]), "blocked": len([c for c in checks if c.get("status") == "blocked"])}


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
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "owner_approval_required": True,
        "approval_gated": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
    }


def _policy(settings: dict | None) -> dict:
    p = _settings(settings, "autonomous_proof_to_limited_live_control")
    return {
        "owner_limited_live_confirmation": _safe_bool(p.get("owner_limited_live_confirmation"), False),
        "real_network_enable": _safe_bool(p.get("real_network_enable"), False),
        "real_submit_enable": _safe_bool(p.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(p.get("real_close_enable"), False),
        "activation_token_preview": str(p.get("activation_token_preview") or "").strip(),
        "required_activation_token": "HMTSTC-LIMITED-LIVE-PREVIEW",
        "max_session_minutes": max(1, _safe_int(p.get("max_session_minutes"), 45)),
        "max_trades_per_session": max(1, _safe_int(p.get("max_trades_per_session"), 3)),
        "max_session_notional_usdt": max(1.0, _safe_float(p.get("max_session_notional_usdt"), 15.0)),
        "max_session_loss_usdt": min(-0.01, _safe_float(p.get("max_session_loss_usdt"), -0.5)),
        "profit_lock_usdt": max(0.01, _safe_float(p.get("profit_lock_usdt"), 0.75)),
        "allowed_symbols": [str(x).upper() for x in p.get("allowed_symbols", []) if str(x).strip()] if isinstance(p.get("allowed_symbols"), list) else [],
    }


def _runtime(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    for key in ("limited_live_session", "live_session", "session_state"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def build_rev176_limited_live_eligibility_recheck(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    proof = build_rev175_profitability_proof_decision_packet(data, settings, auth_store, username)
    launch = build_rev155_live_launch_packet_v1(data, settings, auth_store, username)
    pilot = build_rev160_micro_real_pilot_decision_packet(data, settings, auth_store, username)
    policy = _policy(settings)
    proof_decision = ((proof.get("profitability_proof_decision") or {}).get("decision") or "")
    checks = [
        _check("profitability_proof_not_no_go", "ok" if proof_decision != "NO-GO" else "blocked", "Rev175 must not be NO-GO."),
        _check("launch_packet_not_blocked", "ok" if launch.get("status") != "blocked" else "blocked", "Rev155 launch packet must be review/ok."),
        _check("pilot_decision_not_blocked", "ok" if pilot.get("status") != "blocked" else "blocked", "Rev160 pilot decision must be review/ok."),
        _check("owner_confirmation", "ok" if policy["owner_limited_live_confirmation"] else "review", "Owner confirmation is required before any limited-live move.", required=False),
        _check("real_submit_close_remain_off", "ok" if not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "This block cannot enable submit/close."),
        _check("no_network_action", "ok" if not policy["real_network_enable"] else "review", "Network may only be reviewed, never executed here.", required=False),
    ]
    decision = "LIMITED_LIVE_REVIEW_READY" if _final_status(checks) == "ok" else ("BLOCKED" if any(c["status"] == "blocked" for c in checks if c.get("required", True)) else "REVIEW")
    return {"engine": "autonomous_limited_live_eligibility_recheck", "revision": 176, "status": _final_status(checks), "generated_at": now_iso(), "eligibility": {"decision": decision, "profitability_proof": proof_decision, "launch_status": launch.get("status"), "pilot_status": pilot.get("status"), "real_submit_close": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "activation_token_preview_owner_gate"}


def build_rev177_activation_token_preview_owner_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    settings = deepcopy(settings or {})
    policy = _policy(settings)
    token_ok = policy["activation_token_preview"] == policy["required_activation_token"]
    checks = [
        _check("owner_limited_live_confirmation", "ok" if policy["owner_limited_live_confirmation"] else "blocked", "Owner confirmation must be explicit."),
        _check("activation_token_preview", "ok" if token_ok else "blocked", "Activation token must match the documented preview token."),
        _check("submit_flag_off", "ok" if not policy["real_submit_enable"] else "blocked", "Submit flag remains off in generated package."),
        _check("close_flag_off", "ok" if not policy["real_close_enable"] else "blocked", "Close flag remains off in generated package."),
        _check("secret_free_token_gate", "ok", "Token gate returns no API secret/key/token material."),
    ]
    return {"engine": "autonomous_activation_token_preview_owner_gate", "revision": 177, "status": _final_status(checks), "activation_gate": {"gate": "PASS_PREVIEW" if _final_status(checks) == "ok" else "BLOCKED", "token_required": True, "token_value_returned": False, "owner_confirmation_required": True, "real_submit_close": "OFF", "network_action": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "micro_live_session_boundary_controller"}


def build_rev178_micro_live_session_boundary_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    session = _runtime(data)
    trade_count = _safe_int(session.get("trade_count"), 0)
    notional = _safe_float(session.get("session_notional_usdt"), 0.0)
    elapsed = _safe_int(session.get("elapsed_minutes"), 0)
    symbols = [str(x).upper() for x in session.get("symbols", [])] if isinstance(session.get("symbols"), list) else []
    whitelist = set(policy["allowed_symbols"])
    whitelist_ok = not whitelist or all(s in whitelist for s in symbols)
    checks = [
        _check("session_time_cap", "ok" if elapsed <= policy["max_session_minutes"] else "blocked", "Session duration cap is enforced."),
        _check("session_trade_cap", "ok" if trade_count <= policy["max_trades_per_session"] else "blocked", "Session trade count cap is enforced."),
        _check("session_notional_cap", "ok" if notional <= policy["max_session_notional_usdt"] else "blocked", "Session notional cap is enforced."),
        _check("symbol_whitelist", "ok" if whitelist_ok else "blocked", "Session symbols must remain inside whitelist."),
        _check("boundary_preview_only", "ok", "Boundary controller never submits/closes orders."),
    ]
    boundary = "SESSION_ALLOWED_PREVIEW" if _final_status(checks) == "ok" else "SESSION_BLOCKED"
    return {"engine": "autonomous_micro_live_session_boundary_controller", "revision": 178, "status": _final_status(checks), "session_boundary": {"decision": boundary, "max_session_minutes": policy["max_session_minutes"], "max_trades_per_session": policy["max_trades_per_session"], "max_session_notional_usdt": policy["max_session_notional_usdt"], "current_trade_count": trade_count, "current_session_notional_usdt": notional, "real_submit_close": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "real_time_loss_profit_tripwire"}


def build_rev179_real_time_loss_profit_tripwire(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    session = _runtime(data)
    pnl = _safe_float(session.get("realized_pnl_usdt"), _safe_float(session.get("pnl_usdt"), 0.0))
    unrealized = _safe_float(session.get("unrealized_pnl_usdt"), 0.0)
    effective_pnl = pnl + unrealized
    loss_hit = effective_pnl <= policy["max_session_loss_usdt"]
    profit_hit = effective_pnl >= policy["profit_lock_usdt"]
    action = "HALT_LOSS_TRIPWIRE" if loss_hit else ("LOCK_PROFIT_REVIEW" if profit_hit else "CONTINUE_MONITORING")
    checks = [
        _check("max_loss_tripwire", "blocked" if loss_hit else "ok", "Loss tripwire halts next-action recommendations."),
        _check("profit_lock_tripwire", "review" if profit_hit else "ok", "Profit lock requests review instead of increasing risk.", required=False),
        _check("no_emergency_close_submit", "ok", "Tripwire can recommend emergency attention but cannot close orders."),
        _check("runtime_audit_safe", "ok", "Payload is secret-free and runtime-write-free."),
    ]
    return {"engine": "autonomous_real_time_loss_profit_tripwire", "revision": 179, "status": _final_status(checks), "tripwire": {"action": action, "effective_pnl_usdt": round(effective_pnl, 6), "max_session_loss_usdt": policy["max_session_loss_usdt"], "profit_lock_usdt": policy["profit_lock_usdt"], "real_submit_close": "OFF", "emergency_close_submit": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "limited_live_control_decision_packet"}


def build_rev180_limited_live_control_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    eligibility = build_rev176_limited_live_eligibility_recheck(data, settings, auth_store, username)
    token = build_rev177_activation_token_preview_owner_gate(data, settings, auth_store, username)
    boundary = build_rev178_micro_live_session_boundary_controller(data, settings, auth_store, username)
    tripwire = build_rev179_real_time_loss_profit_tripwire(data, settings, auth_store, username)
    capital = build_rev145_capital_protection_summary(data, settings, auth_store, username)
    statuses = [eligibility.get("status"), token.get("status"), boundary.get("status"), tripwire.get("status")]
    if "blocked" in statuses:
        decision = "NO-GO"
    elif "review" in statuses:
        decision = "LIMITED-GO-REVIEW"
    else:
        decision = "LIMITED-GO-PREVIEW-ONLY"
    checks = [
        _check("eligibility_recheck", eligibility.get("status", "blocked"), "Rev176 eligibility recheck."),
        _check("activation_owner_gate", token.get("status", "blocked"), "Rev177 owner/token gate."),
        _check("session_boundary", boundary.get("status", "blocked"), "Rev178 session boundary."),
        _check("loss_profit_tripwire", tripwire.get("status", "blocked"), "Rev179 tripwire."),
        _check("real_submit_close_still_off", "ok", "Final packet cannot enable real submit/close."),
    ]
    summary = {"limited_live": decision, "session": (boundary.get("session_boundary") or {}).get("decision"), "tripwire": (tripwire.get("tripwire") or {}).get("action"), "capital": (capital.get("summary_result") or {}).get("capital_action", "review"), "real_submit_close": "OFF", "operator_action": "review_before_any_manual_activation"}
    return {"engine": "autonomous_limited_live_control_decision_packet", "revision": 180, "status": _final_status(checks), "generated_at": now_iso(), "limited_live_control_decision": {"decision": decision, "network": "OFF", "real_submit_close": "OFF", "auto_execute": "OFF", "auto_scale": "OFF", "operator_action": summary["operator_action"], "next_action": "manual_owner_review_or_continue_shadow"}, "summary_result": summary, "outputs": {"eligibility": eligibility, "activation_gate": token, "session_boundary": boundary, "tripwire": tripwire}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev181_or_manual_limited_live_review"}


REV_BUILDERS = {176: build_rev176_limited_live_eligibility_recheck, 177: build_rev177_activation_token_preview_owner_gate, 178: build_rev178_micro_live_session_boundary_controller, 179: build_rev179_real_time_loss_profit_tripwire, 180: build_rev180_limited_live_control_decision_packet}
REV_KEYS = {176: "autonomous_limited_live_eligibility_recheck", 177: "autonomous_activation_token_preview_owner_gate", 178: "autonomous_micro_live_session_boundary_controller", 179: "autonomous_real_time_loss_profit_tripwire", 180: "autonomous_limited_live_control_decision_packet"}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_proof_to_limited_live_control_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev176-180 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 180:
        return {"revision": 180, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("eligibility", "activation_gate", "session_boundary", "tripwire"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(176, 181)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_limited_live_control_decision_packet"]
    return {"engine": "autonomous_proof_to_limited_live_control_block", "revision": 180, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("summary_result", {}), "limited_live_control_decision": final.get("limited_live_control_decision", {}), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "manual_owner_review_before_limited_live_activation"}


def build_quality_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    preview = payload.get("command_preview", {})
    checks = [
        _check("route_payload_available", "ok" if payload.get("revision") == int(revision) else "blocked", "Revision payload is available."),
        _check("no_secret_exposure", "ok" if payload.get("contains_secret") is False and payload.get("secret_values_returned") is False else "blocked", "Payload does not expose secrets."),
        _check("network_default_off", "ok" if preview.get("network_default_off") is True and preview.get("sends_exchange_request") is False else "blocked", "No exchange network request."),
        _check("real_submit_default_off", "ok" if preview.get("real_submit_default_off") is True and preview.get("places_order") is False else "blocked", "Real submit is disabled."),
        _check("real_close_default_off", "ok" if preview.get("real_close_default_off") is True and preview.get("submits_close_order") is False else "blocked", "Real close is disabled."),
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "All decisions remain advisory/approval-gated."),
    ]
    return {"engine": "autonomous_proof_to_limited_live_control_quality_gate", "revision": int(revision), "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks), "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "contains_secret": False, "secret_values_returned": False}
