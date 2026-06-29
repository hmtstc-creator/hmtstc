from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_proof_to_limited_live_control_block_service import (
    build_rev176_limited_live_eligibility_recheck,
    build_rev177_activation_token_preview_owner_gate,
    build_rev178_micro_live_session_boundary_controller,
    build_rev179_real_time_loss_profit_tripwire,
    build_rev180_limited_live_control_decision_packet,
)


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


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    value = settings.get(key)
    return value if isinstance(value, dict) else {}


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
    rehearsal = _settings(settings, "autonomous_limited_live_activation_rehearsal")
    previous = _settings(settings, "autonomous_proof_to_limited_live_control")
    source = {**previous, **rehearsal}
    allowed_symbols = source.get("allowed_symbols")
    if not isinstance(allowed_symbols, list) or not allowed_symbols:
        allowed_symbols = ["BTCUSDT", "ETHUSDT"]
    return {
        "owner_limited_live_confirmation": _safe_bool(source.get("owner_limited_live_confirmation"), False),
        "owner_approval_preview": _safe_bool(source.get("owner_approval_preview"), False),
        "api_readiness": _safe_bool(source.get("api_readiness"), False),
        "whitelist_ready": _safe_bool(source.get("whitelist_ready"), bool(allowed_symbols)),
        "daily_hard_stop_ready": _safe_bool(source.get("daily_hard_stop_ready"), False),
        "session_boundary_ready": _safe_bool(source.get("session_boundary_ready"), True),
        "journal_ready": _safe_bool(source.get("journal_ready"), False),
        "exchange_permission_ready": _safe_bool(source.get("exchange_permission_ready"), False),
        "emergency_guard_ready": _safe_bool(source.get("emergency_guard_ready"), False),
        "real_network_enable": _safe_bool(source.get("real_network_enable"), False),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "activation_token_preview": str(source.get("activation_token_preview") or "").strip(),
        "required_activation_token": "HMTSTC-LIMITED-LIVE-PREVIEW",
        "approval_scope": str(source.get("approval_scope") or "limited-live-preview-only"),
        "max_session_minutes": max(1, _safe_int(source.get("max_session_minutes"), 45)),
        "max_trades_per_session": max(1, _safe_int(source.get("max_trades_per_session"), 3)),
        "max_session_notional_usdt": max(1.0, _safe_float(source.get("max_session_notional_usdt"), 15.0)),
        "max_session_loss_usdt": min(-0.01, _safe_float(source.get("max_session_loss_usdt"), -0.5)),
        "max_order_notional_usdt": max(1.0, _safe_float(source.get("max_order_notional_usdt"), 5.0)),
        "allowed_symbols": [str(x).upper().strip() for x in allowed_symbols if str(x).strip()],
    }


def _runtime(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    for key in ("limited_live_rehearsal", "limited_live_session", "live_session", "session_state"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _order_preview(data: dict | None, policy: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    candidate = data.get("selected_opportunity") if isinstance(data.get("selected_opportunity"), dict) else {}
    symbol = str(candidate.get("symbol") or (policy["allowed_symbols"][0] if policy["allowed_symbols"] else "BTCUSDT")).upper()
    strategy = str(candidate.get("strategy") or candidate.get("strategy_id") or "limited_live_rehearsal_probe")
    notional = min(policy["max_order_notional_usdt"], policy["max_session_notional_usdt"])
    return {
        "symbol": symbol,
        "strategy": strategy,
        "side": str(candidate.get("side") or "BUY").upper(),
        "notional_usdt": round(notional, 6),
        "max_loss_usdt": policy["max_session_loss_usdt"],
        "network_action": "OFF",
        "submit_action": "OFF",
        "preview_only": True,
    }


def _critical_issue(checks: list[dict]) -> dict:
    candidates = [c for c in checks if c.get("status") in {"blocked", "review"}]
    if not candidates:
        return {"name": "none", "status": "ok", "detail": "Activation rehearsal is ready.", "action": "continue_shadow_or_manual_review"}
    return sorted(candidates, key=lambda c: (0 if c.get("status") == "blocked" else 1, int(c.get("priority", 50))))[0]


def build_rev181_activation_preflight_matrix(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    previous_snapshot = data.get("autonomous_proof_to_limited_live_control_block") if isinstance(data.get("autonomous_proof_to_limited_live_control_block"), dict) else {}
    previous_status = str(previous_snapshot.get("status") or data.get("proof_to_limited_live_status") or "review")
    token_ok = policy["activation_token_preview"] == policy["required_activation_token"]
    checks = [
        _check("owner_approval", "ok" if policy["owner_limited_live_confirmation"] else "blocked", "Explicit owner approval is required.", priority=1, action="confirm_owner_limited_live_preview"),
        _check("activation_token_preview", "ok" if token_ok else "blocked", "Activation token preview must match documented value; token value is not returned.", priority=2, action="enter_preview_token"),
        _check("api_readiness", "ok" if policy["api_readiness"] else "blocked", "API readiness must be confirmed without exposing secrets.", priority=3, action="verify_api_readiness"),
        _check("whitelist", "ok" if policy["whitelist_ready"] and policy["allowed_symbols"] else "blocked", "Allowed symbol whitelist is mandatory.", priority=4, action="set_allowed_symbols"),
        _check("daily_hard_stop", "ok" if policy["daily_hard_stop_ready"] else "blocked", "Daily hard stop must be active before limited-live activation.", priority=5, action="enable_daily_hard_stop_guard"),
        _check("session_boundary", "ok" if policy["session_boundary_ready"] else "blocked", "Session boundary and max duration/trade cap must be ready.", priority=6, action="repair_session_boundary"),
        _check("max_notional", "ok" if policy["max_session_notional_usdt"] > 0 and policy["max_order_notional_usdt"] <= policy["max_session_notional_usdt"] else "blocked", "Order notional must be positive and within session cap.", priority=7, action="reduce_max_notional"),
        _check("tripwire", "ok" if policy["max_session_loss_usdt"] < 0 else "blocked", "Loss tripwire must use a negative stop value.", priority=8, action="set_loss_tripwire"),
        _check("journal_readiness", "ok" if policy["journal_ready"] else "blocked", "Journal/evidence path must be ready.", priority=9, action="verify_journal_path"),
        _check("exchange_permission", "ok" if policy["exchange_permission_ready"] else "blocked", "Exchange permission drift check must pass before live path review.", priority=10, action="verify_exchange_permissions"),
        _check("emergency_guard", "ok" if policy["emergency_guard_ready"] else "blocked", "Emergency guard must be ready.", priority=11, action="verify_emergency_guard"),
        _check("real_network_default_off", "ok" if not policy["real_network_enable"] else "blocked", "Real network calls remain default OFF in rehearsal.", priority=12, action="turn_network_flag_off"),
        _check("real_submit_close_default_off", "ok" if not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "Submit/close flags must remain OFF.", priority=13, action="turn_submit_close_off"),
        _check("previous_control_packet", "ok" if previous_status != "blocked" else "review", "Rev180 control packet should be at least review-ready.", required=False, priority=30, action="review_rev180_blocker"),
    ]
    status = _final_status(checks)
    decision = "activation_ready" if status == "ok" else ("activation_blocked" if any(c.get("status") == "blocked" for c in checks if c.get("required", True)) else "activation_review")
    critical = _critical_issue(checks)
    return {
        "engine": "autonomous_activation_preflight_matrix",
        "revision": 181,
        "status": status,
        "generated_at": now_iso(),
        "activation_preflight": {
            "decision": decision,
            "critical_blocker": critical,
            "allowed_symbols": policy["allowed_symbols"],
            "allowed_max_notional_usdt": policy["max_session_notional_usdt"],
            "live_action_scope": "preview_only_no_submit_no_close",
            "network": "OFF",
            "real_submit_close": "OFF",
        },
        "checks": checks,
        "check_totals": _totals(checks),
        "auto_apply_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "limited_live_rehearsal_runner",
    }


def build_rev182_limited_live_rehearsal_runner(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    preflight = build_rev181_activation_preflight_matrix(data, settings, auth_store, username)
    previous_boundary = build_rev178_micro_live_session_boundary_controller(data, settings, auth_store, username)
    preview = _order_preview(data, policy)
    preflight_passable = preflight.get("status") in {"ok", "review"}
    risk_approval = preflight_passable and previous_boundary.get("status") != "blocked"
    chain = [
        {"step": "session_start", "status": "ok", "mode": "rehearsal"},
        {"step": "opportunity_select", "status": "ok", "symbol": preview["symbol"], "strategy": preview["strategy"]},
        {"step": "order_preview", "status": "ok", "order": preview},
        {"step": "risk_approval", "status": "ok" if risk_approval else "blocked", "source": "preflight_matrix_and_session_boundary"},
        {"step": "activation_decision", "status": "ready" if risk_approval else "blocked", "network": "OFF", "submit": "OFF"},
    ]
    checks = [
        _check("preflight_ready", "ok" if preflight_passable else "blocked", "Preflight must not have a required blocker before rehearsal can be ready.", priority=1, action="clear_preflight_blocker"),
        _check("session_boundary_not_blocked", "ok" if previous_boundary.get("status") != "blocked" else "blocked", "Session boundary must not be blocked.", priority=2, action="repair_session_boundary"),
        _check("order_preview_only", "ok" if preview.get("preview_only") else "blocked", "Runner can only create an order preview.", priority=3, action="force_preview_only"),
        _check("no_network_request", "ok" if not policy["real_network_enable"] else "blocked", "No real network call is allowed in rehearsal.", priority=4, action="turn_network_flag_off"),
        _check("no_submit_close", "ok" if not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "Submit/close remains OFF.", priority=5, action="turn_submit_close_off"),
    ]
    status = _final_status(checks)
    return {
        "engine": "autonomous_limited_live_rehearsal_runner",
        "revision": 182,
        "status": status,
        "generated_at": now_iso(),
        "rehearsal_runner": {
            "decision": "ready" if status == "ok" else "blocked",
            "chain": chain,
            "order_preview": preview,
            "real_network": "OFF",
            "real_submit_close": "OFF",
        },
        "checks": checks,
        "check_totals": _totals(checks),
        "auto_apply_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "activation_failure_reason_normalizer",
    }


def _collect_blockers(*payloads: dict) -> list[dict]:
    blockers: list[dict] = []
    for payload in payloads:
        for check in payload.get("checks") or []:
            if isinstance(check, dict) and check.get("status") in {"blocked", "review"}:
                blockers.append(check)
    dedup: dict[str, dict] = {}
    for item in blockers:
        name = str(item.get("name") or "unknown")
        current = dedup.get(name)
        if not current or int(item.get("priority", 50)) < int(current.get("priority", 50)):
            dedup[name] = item
    return sorted(dedup.values(), key=lambda c: (0 if c.get("status") == "blocked" else 1, int(c.get("priority", 50))))


def build_rev183_activation_failure_reason_normalizer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    preflight = build_rev181_activation_preflight_matrix(data, settings, auth_store, username)
    runner = build_rev182_limited_live_rehearsal_runner(data, settings, auth_store, username)
    blockers = _collect_blockers(preflight, runner)
    critical = blockers[0] if blockers else _critical_issue([])
    checks = [
        _check("failure_reasons_prioritized", "ok", "Failure reasons are normalized by priority and severity."),
        _check("summary_noise_control", "ok", "Summary exposes only the highest priority blocker."),
        _check("actionable_operator_step", "ok" if critical.get("action") else "review", "Critical blocker includes a direct operator action.", required=False),
        _check("no_secret_in_reason", "ok", "Reasons never include tokens, keys or secret values."),
    ]
    return {
        "engine": "autonomous_activation_failure_reason_normalizer",
        "revision": 183,
        "status": _final_status(checks),
        "generated_at": now_iso(),
        "failure_normalizer": {
            "decision": "clear" if not blockers else ("blocked" if critical.get("status") == "blocked" else "review"),
            "critical_blocker": critical,
            "blocker_count": len([b for b in blockers if b.get("status") == "blocked"]),
            "review_count": len([b for b in blockers if b.get("status") == "review"]),
            "operator_action": critical.get("action") or "continue_shadow",
            "summary_visible_issue": critical.get("name"),
        },
        "normalized_reasons": blockers[:10],
        "checks": checks,
        "check_totals": _totals(checks),
        "auto_apply_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "owner_approval_audit_contract",
    }


def build_rev184_owner_approval_audit_contract(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    token_ok = policy["activation_token_preview"] == policy["required_activation_token"]
    session = _runtime(data)
    session_id = str(session.get("session_id") or f"preview-{username}-limited-live")[:96]
    approval = {
        "approval_preview": bool(policy["owner_approval_preview"] or policy["owner_limited_live_confirmation"]),
        "activation_token_present": bool(policy["activation_token_preview"]),
        "activation_token_value_returned": False,
        "activation_token_valid": token_ok,
        "timestamp_utc": now_iso(),
        "scope": policy["approval_scope"],
        "max_notional_usdt": policy["max_session_notional_usdt"],
        "max_order_notional_usdt": policy["max_order_notional_usdt"],
        "max_loss_usdt": policy["max_session_loss_usdt"],
        "session_id": session_id,
        "allowed_symbols": policy["allowed_symbols"],
        "network": "OFF",
        "real_submit_close": "OFF",
    }
    checks = [
        _check("owner_approval_preview", "ok" if approval["approval_preview"] else "blocked", "Owner approval preview must exist before live action scope can pass.", priority=1, action="create_owner_approval_preview"),
        _check("activation_token_valid", "ok" if token_ok else "blocked", "Token preview must be valid, but token value is never returned.", priority=2, action="enter_preview_token"),
        _check("scope_bound", "ok" if policy["approval_scope"] else "blocked", "Approval scope must be explicit.", priority=3, action="define_approval_scope"),
        _check("session_id_bound", "ok" if session_id else "blocked", "Session ID is required for auditability.", priority=4, action="create_session_id"),
        _check("notional_bound", "ok" if policy["max_session_notional_usdt"] > 0 else "blocked", "Max notional must be bounded.", priority=5, action="set_max_notional"),
        _check("no_runtime_token", "ok", "Runtime activation token is not persisted or returned."),
        _check("no_secret_response", "ok", "Contract contains no API key/secret or token value."),
        _check("no_live_action_without_owner", "ok" if approval["approval_preview"] else "blocked", "No live action can pass without owner approval.", priority=6, action="confirm_owner_approval"),
    ]
    return {
        "engine": "autonomous_owner_approval_audit_contract",
        "revision": 184,
        "status": _final_status(checks),
        "generated_at": now_iso(),
        "owner_approval_audit_contract": approval,
        "checks": checks,
        "check_totals": _totals(checks),
        "auto_apply_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "limited_live_activation_rehearsal_report",
    }


def build_rev185_limited_live_activation_rehearsal_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    preflight = build_rev181_activation_preflight_matrix(data, settings, auth_store, username)
    runner = build_rev182_limited_live_rehearsal_runner(data, settings, auth_store, username)
    normalizer = build_rev183_activation_failure_reason_normalizer(data, settings, auth_store, username)
    audit = build_rev184_owner_approval_audit_contract(data, settings, auth_store, username)
    tripwire = build_rev179_real_time_loss_profit_tripwire(data, settings, auth_store, username)
    statuses = [preflight.get("status"), runner.get("status"), normalizer.get("status"), audit.get("status"), tripwire.get("status")]
    critical = (normalizer.get("failure_normalizer") or {}).get("critical_blocker") or _critical_issue([])
    policy = _policy(settings)
    if "blocked" in statuses:
        decision = "blocked"
        operator_action = critical.get("action") or "clear_activation_blocker"
    elif "review" in statuses:
        decision = "review"
        operator_action = "manual_owner_review_before_activation"
    else:
        decision = "activation_ready"
        operator_action = "owner_may_review_limited_live_preview"
    report = {
        "decision": decision,
        "critical_blocker": critical,
        "live_action_scope": "preview_only_no_real_submit_no_close",
        "allowed_max_notional_usdt": policy["max_session_notional_usdt"],
        "allowed_symbols": policy["allowed_symbols"],
        "stop_conditions": [
            f"session_loss <= {policy['max_session_loss_usdt']} USDT",
            f"session_minutes > {policy['max_session_minutes']}",
            f"trade_count > {policy['max_trades_per_session']}",
            "any emergency_guard or exchange_permission drift",
            "owner approval or session boundary missing",
        ],
        "operator_action": operator_action,
        "summary_visible": {
            "activation": decision,
            "blocker": critical.get("name"),
            "action": operator_action,
            "real_submit_close": "OFF",
            "network": "OFF",
        },
    }
    checks = [
        _check("preflight_matrix", preflight.get("status", "blocked"), "Rev181 preflight matrix."),
        _check("rehearsal_runner", runner.get("status", "blocked"), "Rev182 rehearsal runner."),
        _check("failure_normalizer", normalizer.get("status", "blocked"), "Rev183 failure normalizer."),
        _check("approval_audit_contract", audit.get("status", "blocked"), "Rev184 owner approval audit contract."),
        _check("tripwire_available", "ok" if tripwire.get("status") != "blocked" else "blocked", "Tripwire must be available before activation rehearsal report."),
        _check("real_submit_close_still_off", "ok", "Report cannot enable real submit/close."),
        _check("network_still_off", "ok", "Report cannot send exchange requests."),
    ]
    return {
        "engine": "autonomous_limited_live_activation_rehearsal_report",
        "revision": 185,
        "status": _final_status(checks),
        "generated_at": now_iso(),
        "activation_rehearsal_report": report,
        "summary_result": report["summary_visible"],
        "outputs": {"preflight_matrix": preflight, "rehearsal_runner": runner, "failure_normalizer": normalizer, "owner_approval_audit_contract": audit},
        "checks": checks,
        "check_totals": _totals(checks),
        "auto_apply_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev186_execution_reconciliation_or_manual_owner_review",
    }


REV_BUILDERS = {
    181: build_rev181_activation_preflight_matrix,
    182: build_rev182_limited_live_rehearsal_runner,
    183: build_rev183_activation_failure_reason_normalizer,
    184: build_rev184_owner_approval_audit_contract,
    185: build_rev185_limited_live_activation_rehearsal_report,
}
REV_KEYS = {
    181: "autonomous_activation_preflight_matrix",
    182: "autonomous_limited_live_rehearsal_runner",
    183: "autonomous_activation_failure_reason_normalizer",
    184: "autonomous_owner_approval_audit_contract",
    185: "autonomous_limited_live_activation_rehearsal_report",
}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_limited_live_activation_rehearsal_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev181-185 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 185:
        return {"revision": 185, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("activation_preflight", "rehearsal_runner", "failure_normalizer", "owner_approval_audit_contract"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(181, 186)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_limited_live_activation_rehearsal_report"]
    return {
        "engine": "autonomous_limited_live_activation_rehearsal_block",
        "revision": 185,
        "status": block_status,
        "generated_at": now_iso(),
        "username": username,
        "outputs": outputs,
        "summary_result": final.get("summary_result", {}),
        "activation_rehearsal_report": final.get("activation_rehearsal_report", {}),
        "auto_apply_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev186_real_execution_reconciliation_block",
    }


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
    return {
        "engine": "autonomous_limited_live_activation_rehearsal_quality_gate",
        "revision": int(revision),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL",
        "status": _final_status(checks),
        "checks": checks,
        "check_totals": _totals(checks),
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "contains_secret": False,
        "secret_values_returned": False,
    }
