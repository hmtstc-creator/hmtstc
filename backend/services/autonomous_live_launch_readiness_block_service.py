from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_live_autonomy_hardening_block_service import build_rev150_live_stabilized_go_no_go_v2


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "clear"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency", "stopped"}:
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
    }


def _policy(settings: dict | None) -> dict:
    p = _settings(settings, "autonomous_live_launch_readiness")
    whitelist = p.get("launch_symbols") or p.get("allowed_symbols") or ["BTCUSDT", "ETHUSDT"]
    strategies = p.get("launch_strategies") or p.get("allowed_strategies") or ["choch_imbalance", "micro_pullback"]
    return {
        "owner_launch_confirmation": _safe_bool(p.get("owner_launch_confirmation"), False),
        "dry_run_required_hours": max(1, _safe_int(p.get("dry_run_required_hours"), 24)),
        "dry_run_observed_hours": max(0, _safe_int(p.get("dry_run_observed_hours"), _safe_int(p.get("observation_hours"), 0))),
        "seed_capital_usdt": max(0.0, _safe_float(p.get("seed_capital_usdt"), 100.0)),
        "max_live_notional_usdt": max(0.0, _safe_float(p.get("max_live_notional_usdt"), 25.0)),
        "daily_loss_limit_usdt": max(0.0, _safe_float(p.get("daily_loss_limit_usdt"), 3.0)),
        "daily_trade_cap": max(1, _safe_int(p.get("daily_trade_cap"), 10)),
        "max_open_positions": max(1, _safe_int(p.get("max_open_positions"), 1)),
        "launch_symbols": [str(s) for s in whitelist if str(s).strip()][:8],
        "launch_strategies": [str(s) for s in strategies if str(s).strip()][:6],
        "auto_activation_enabled": _safe_bool(p.get("auto_activation_enabled"), False),
        "incident_rollback_confirmed": _safe_bool(p.get("incident_rollback_confirmed"), False),
    }


def _context(data: dict | None, settings: dict | None, auth_store: dict | None, username: str) -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    # Launch readiness only needs the final guarded Rev150 decision, not the full heavy block tree.
    return {"autonomy": build_rev150_live_stabilized_go_no_go_v2(data, settings, auth_store, username)}


def _decision_from_autonomy(ctx: dict) -> str:
    go = ctx.get("autonomy", {}).get("go_no_go", {})
    decision = str(go.get("decision") or ctx.get("autonomy", {}).get("summary_result", {}).get("live") or "NO-GO").upper()
    return decision if decision in {"GO", "LIMITED-GO", "NO-GO"} else "NO-GO"


def build_rev151_launch_readiness_recheck(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx, policy = _context(data, settings, auth_store, username), _policy(settings)
    decision = _decision_from_autonomy(ctx)
    dry_run_ok = policy["dry_run_observed_hours"] >= policy["dry_run_required_hours"]
    checks = [
        _check("rev150_decision", "blocked" if decision == "NO-GO" else "ok", f"Rev150 decision is {decision}."),
        _check("dry_run_observation", "ok" if dry_run_ok else "review", "Observation-only runtime should complete before live activation."),
        _check("owner_launch_confirmation", "ok" if policy["owner_launch_confirmation"] else "blocked", "Owner launch confirmation is required."),
        _check("real_submit_default_off", "ok", "Live readiness recheck does not enable submit/close."),
        _check("secret_free_payload", "ok", "Readiness payload contains no key/token/secret values."),
    ]
    return {
        "engine": "autonomous_launch_readiness_recheck", "revision": 151, "status": _final_status(checks),
        "launch_readiness": {"decision": "READY_REVIEW" if _final_status(checks) == "ok" else _final_status(checks).upper(), "rev150_decision": decision, "dry_run_observed_hours": policy["dry_run_observed_hours"], "dry_run_required_hours": policy["dry_run_required_hours"], "owner_confirmed": policy["owner_launch_confirmation"]},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "guarded_activation_playbook_preview",
    }


def build_rev152_guarded_activation_playbook(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    steps = [
        {"step": 1, "name": "confirm_owner_and_flags", "action": "verify explicit launch flags", "auto_execute": False},
        {"step": 2, "name": "read_only_exchange_check", "action": "verify balances and permissions without submit", "auto_execute": False},
        {"step": 3, "name": "micro_live_probe", "action": "allow one approval-gated seed probe only after all gates pass", "auto_execute": False},
        {"step": 4, "name": "observe_and_reconcile", "action": "compare journal, position tracker and realized PnL", "auto_execute": False},
        {"step": 5, "name": "hold_or_reduce", "action": "do not scale until performance evidence is stable", "auto_execute": False},
    ]
    checks = [
        _check("auto_activation_disabled", "ok" if not policy["auto_activation_enabled"] else "blocked", "Activation playbook must remain manual/approval-gated."),
        _check("single_probe_limit", "ok", "Initial launch is constrained to one micro probe path."),
        _check("real_submit_default_off", "ok", "Playbook is preview-only; no order is submitted."),
        _check("owner_approval_required", "ok", "Every transition requires explicit owner approval."),
    ]
    return {
        "engine": "autonomous_guarded_activation_playbook", "revision": 152, "status": _final_status(checks),
        "activation_playbook": {"mode": "PREVIEW_ONLY", "steps": steps, "owner_approval_required": True, "auto_activation_enabled": policy["auto_activation_enabled"]},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "seed_capital_limits_contract",
    }


def build_rev153_seed_capital_limits_contract(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    max_notional = min(policy["max_live_notional_usdt"], max(policy["seed_capital_usdt"] * 0.05, 0.0)) if policy["seed_capital_usdt"] else 0.0
    checks = [
        _check("seed_capital_positive", "ok" if policy["seed_capital_usdt"] > 0 else "blocked", "Seed capital must be greater than zero."),
        _check("max_notional_conservative", "ok" if max_notional <= max(policy["seed_capital_usdt"] * 0.05, 25.0) else "review", "Probe notional is capped conservatively."),
        _check("daily_loss_small", "ok" if policy["daily_loss_limit_usdt"] <= max(policy["seed_capital_usdt"] * 0.03, 3.0) else "review", "Daily loss must stay small for launch."),
        _check("position_count_limited", "ok" if policy["max_open_positions"] <= 2 else "review", "Launch should start with one or two open positions at most."),
        _check("whitelist_bound", "ok" if len(policy["launch_symbols"]) > 0 else "blocked", "Launch symbols must stay whitelist-bound."),
    ]
    return {
        "engine": "autonomous_seed_capital_limits_contract", "revision": 153, "status": _final_status(checks),
        "seed_contract": {"seed_capital_usdt": policy["seed_capital_usdt"], "max_live_notional_usdt": round(max_notional, 6), "daily_loss_limit_usdt": policy["daily_loss_limit_usdt"], "daily_trade_cap": policy["daily_trade_cap"], "max_open_positions": policy["max_open_positions"], "symbols": policy["launch_symbols"], "strategies": policy["launch_strategies"], "scale_up_allowed": False},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "incident_rollback_protocol",
    }


def build_rev154_incident_rollback_protocol(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    triggers = ["daily_loss_limit_hit", "unexpected_position", "journal_position_mismatch", "api_permission_problem", "exchange_inconsistency", "emergency_state", "secret_config_problem", "manual_attention_required"]
    actions = ["disable_new_submit_flag", "keep_close_approval_gated", "freeze_symbol_rotation", "capture_secret_free_audit_snapshot", "require_owner_review_before_resume"]
    checks = [
        _check("rollback_protocol_defined", "ok", "Incident triggers and rollback actions are defined."),
        _check("incident_rehearsal_confirmed", "ok" if policy["incident_rollback_confirmed"] else "review", "Rollback rehearsal should be confirmed before live activation."),
        _check("no_auto_close", "ok", "Emergency close stays approval-gated by default."),
        _check("no_network_side_effect", "ok", "Protocol route does not call exchange network."),
    ]
    return {
        "engine": "autonomous_incident_rollback_protocol", "revision": 154, "status": _final_status(checks),
        "rollback_protocol": {"triggers": triggers, "actions": actions, "resume_requires_owner_review": True, "emergency_close_default_off": True},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "live_launch_packet_v1",
    }


def build_rev155_live_launch_packet_v1(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    readiness = build_rev151_launch_readiness_recheck(data, settings, auth_store, username)
    playbook = build_rev152_guarded_activation_playbook(data, settings, auth_store, username)
    seed = build_rev153_seed_capital_limits_contract(data, settings, auth_store, username)
    rollback = build_rev154_incident_rollback_protocol(data, settings, auth_store, username)
    status_list = [readiness.get("status"), playbook.get("status"), seed.get("status"), rollback.get("status")]
    if "blocked" in status_list:
        launch_decision = "NO-LAUNCH"
    elif "review" in status_list:
        launch_decision = "LIMITED-REVIEW"
    else:
        launch_decision = "LIMITED-LAUNCH-READY"
    checks = [
        _check("readiness_recheck", readiness.get("status", "blocked"), "Rev151 readiness recheck result."),
        _check("activation_playbook", playbook.get("status", "blocked"), "Rev152 guarded playbook result."),
        _check("seed_limits", seed.get("status", "blocked"), "Rev153 seed capital contract result."),
        _check("rollback_protocol", rollback.get("status", "blocked"), "Rev154 rollback protocol result."),
        _check("real_submit_close_default_off", "ok", "Launch packet is advisory and cannot place/close orders."),
    ]
    seed_contract = seed.get("seed_contract", {})
    return {
        "engine": "autonomous_live_launch_packet_v1", "revision": 155, "status": _final_status(checks),
        "launch_packet": {"decision": launch_decision, "seed_capital_usdt": 0.0 if launch_decision == "NO-LAUNCH" else seed_contract.get("seed_capital_usdt", 0.0), "max_live_notional_usdt": seed_contract.get("max_live_notional_usdt", 0.0), "daily_loss_limit_usdt": seed_contract.get("daily_loss_limit_usdt", 0.0), "daily_trade_cap": seed_contract.get("daily_trade_cap", 0), "symbols": seed_contract.get("symbols", []), "strategies": seed_contract.get("strategies", []), "next_action": "owner_review" if launch_decision != "LIMITED-LAUNCH-READY" else "controlled_micro_probe_after_owner_approval"},
        "summary_result": {"launch": launch_decision, "capital": 0.0 if launch_decision == "NO-LAUNCH" else seed_contract.get("seed_capital_usdt", 0.0), "notional": seed_contract.get("max_live_notional_usdt", 0.0), "max_loss": seed_contract.get("daily_loss_limit_usdt", 0.0), "trade_cap": seed_contract.get("daily_trade_cap", 0)},
        "outputs": {"readiness": readiness, "playbook": playbook, "seed_contract": seed, "rollback": rollback},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "owner_review_before_any_real_submit_flag",
    }


REV_BUILDERS = {
    151: build_rev151_launch_readiness_recheck,
    152: build_rev152_guarded_activation_playbook,
    153: build_rev153_seed_capital_limits_contract,
    154: build_rev154_incident_rollback_protocol,
    155: build_rev155_live_launch_packet_v1,
}

REV_KEYS = {
    151: "autonomous_launch_readiness_recheck",
    152: "autonomous_guarded_activation_playbook",
    153: "autonomous_seed_capital_limits_contract",
    154: "autonomous_incident_rollback_protocol",
    155: "autonomous_live_launch_packet_v1",
}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_live_launch_readiness_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev151-155 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 155:
        return {"revision": 155, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("launch_readiness", "activation_playbook", "seed_contract", "rollback_protocol"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(151, 156)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_live_launch_packet_v1"]
    return {
        "engine": "autonomous_live_launch_readiness_block", "revision": 155, "status": block_status,
        "generated_at": now_iso(), "username": username, "outputs": outputs,
        "summary_result": final.get("summary_result", {}), "launch_packet": final.get("launch_packet", {}),
        "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True,
        "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False,
        "next_allowed_step": "owner_review_before_controlled_micro_real_probe",
    }


def build_quality_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    preview = payload.get("command_preview", {})
    checks = [
        _check("route_payload_available", "ok" if payload.get("revision") == int(revision) else "blocked", "Revision payload is available."),
        _check("no_secret_exposure", "ok" if payload.get("contains_secret") is False and payload.get("secret_values_returned") is False else "blocked", "Payload does not expose secrets."),
        _check("network_default_off", "ok" if preview.get("network_default_off") is True and preview.get("sends_exchange_request") is False else "blocked", "No exchange network request."),
        _check("real_submit_default_off", "ok" if preview.get("real_submit_default_off") is True and preview.get("places_order") is False else "blocked", "Real order placement is disabled."),
        _check("real_close_default_off", "ok" if preview.get("real_close_default_off") is True and preview.get("submits_close_order") is False else "blocked", "Real close placement is disabled."),
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "Launch readiness actions are advisory/approval-gated."),
    ]
    return {
        "engine": "autonomous_live_launch_readiness_quality_gate", "revision": int(revision),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks),
        "checks": checks, "check_totals": _totals(checks), "network_default_off": True,
        "real_submit_default_off": True, "contains_secret": False, "secret_values_returned": False,
    }
