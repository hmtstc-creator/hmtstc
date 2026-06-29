from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_live_launch_readiness_block_service import build_rev155_live_launch_packet_v1
from services.autonomous_live_stabilization_block_service import build_rev130_first_live_stabilization_report
from services.autonomous_performance_observability_block_service import build_rev135_performance_sentinel_v2
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
    }


def _policy(settings: dict | None) -> dict:
    p = _settings(settings, "autonomous_controlled_micro_real_pilot")
    launch = _settings(settings, "autonomous_live_launch_readiness")
    symbols = p.get("pilot_symbols") or launch.get("launch_symbols") or ["BTCUSDT"]
    strategies = p.get("pilot_strategies") or launch.get("launch_strategies") or ["choch_imbalance"]
    seed_capital = max(0.0, _safe_float(p.get("seed_capital_usdt"), _safe_float(launch.get("seed_capital_usdt"), 100.0)))
    max_notional = max(0.0, _safe_float(p.get("max_probe_notional_usdt"), min(_safe_float(launch.get("max_live_notional_usdt"), 25.0), max(seed_capital * 0.03, 0.0))))
    return {
        "owner_probe_confirmation": _safe_bool(p.get("owner_probe_confirmation"), _safe_bool(launch.get("owner_launch_confirmation"), False)),
        "micro_probe_enabled": _safe_bool(p.get("micro_probe_enabled"), False),
        "read_only_exchange_check_passed": _safe_bool(p.get("read_only_exchange_check_passed"), False),
        "permission_snapshot_fresh": _safe_bool(p.get("permission_snapshot_fresh"), False),
        "permission_drift_detected": _safe_bool(p.get("permission_drift_detected"), False),
        "dry_run_shadow_hours": max(0, _safe_int(p.get("dry_run_shadow_hours"), _safe_int(launch.get("dry_run_observed_hours"), 0))),
        "min_shadow_hours": max(1, _safe_int(p.get("min_shadow_hours"), 12)),
        "shadow_match_rate_pct": max(0.0, min(100.0, _safe_float(p.get("shadow_match_rate_pct"), 0.0))),
        "min_shadow_match_rate_pct": max(0.0, min(100.0, _safe_float(p.get("min_shadow_match_rate_pct"), 95.0))),
        "max_shadow_discrepancy_count": max(0, _safe_int(p.get("max_shadow_discrepancy_count"), 1)),
        "shadow_discrepancy_count": max(0, _safe_int(p.get("shadow_discrepancy_count"), 0)),
        "seed_capital_usdt": seed_capital,
        "max_probe_notional_usdt": max_notional,
        "daily_loss_limit_usdt": max(0.0, _safe_float(p.get("daily_loss_limit_usdt"), _safe_float(launch.get("daily_loss_limit_usdt"), 3.0))),
        "daily_trade_cap": max(1, _safe_int(p.get("daily_trade_cap"), _safe_int(launch.get("daily_trade_cap"), 5))),
        "max_open_positions": max(1, _safe_int(p.get("max_open_positions"), 1)),
        "max_probe_count": max(1, _safe_int(p.get("max_probe_count"), 1)),
        "pilot_symbols": [str(s).strip().upper() for s in symbols if str(s).strip()][:6],
        "pilot_strategies": [str(s).strip() for s in strategies if str(s).strip()][:6],
        "allowed_order_type": str(p.get("allowed_order_type") or "MARKET_OR_LIMIT_PREVIEW").upper(),
        "auto_escalation_enabled": _safe_bool(p.get("auto_escalation_enabled"), False),
    }


def _auth_for_user(auth_store: dict | None, username: str) -> dict:
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    users = auth_store.get("users") if isinstance(auth_store.get("users"), dict) else {}
    return users.get(username) if isinstance(users.get(username), dict) else {}


def _open_positions(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    real = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    positions = real.get("positions") if isinstance(real.get("positions"), list) else data.get("positions")
    if not isinstance(positions, list):
        return []
    return [p for p in positions if isinstance(p, dict) and str(p.get("status") or "").lower() not in {"closed", "cancelled", "resolved"}]


def _whitelist(settings: dict | None) -> set[str]:
    candidates = []
    for key in ("autonomous_whitelist_daily_hard_stop", "autonomous_live_stabilization", "autonomous_live_launch_readiness", "autonomous_controlled_micro_real_pilot"):
        section = _settings(settings, key)
        for field in ("symbol_whitelist", "launch_symbols", "allowed_symbols", "pilot_symbols"):
            value = section.get(field)
            if isinstance(value, list):
                candidates.extend(value)
    return {str(x).strip().upper() for x in candidates if str(x).strip()}


def _launch_packet(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    return build_rev155_live_launch_packet_v1(data, settings, auth_store, username)


def build_rev156_controlled_micro_probe_eligibility_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    launch = _launch_packet(data, settings, auth_store, username)
    packet = launch.get("launch_packet", {}) if isinstance(launch.get("launch_packet"), dict) else {}
    whitelist = _whitelist(settings)
    symbol_ok = bool(policy["pilot_symbols"]) and all(s in whitelist for s in policy["pilot_symbols"]) if whitelist else bool(policy["pilot_symbols"])
    notional_cap = min(policy["max_probe_notional_usdt"], max(policy["seed_capital_usdt"] * 0.03, 0.0))
    checks = [
        _check("launch_packet_ready", "ok" if packet.get("decision") in {"LIMITED-LAUNCH-READY", "LIMITED-REVIEW"} else "blocked", "Rev155 launch packet must not be NO-LAUNCH."),
        _check("owner_probe_confirmation", "ok" if policy["owner_probe_confirmation"] else "blocked", "Owner confirmation is required before any controlled micro probe."),
        _check("explicit_probe_flag_off_by_default", "review" if policy["micro_probe_enabled"] else "ok", "Micro probe flag is explicit and remains disabled by default."),
        _check("symbol_whitelist_bound", "ok" if symbol_ok else "blocked", "Pilot symbols must stay inside whitelist."),
        _check("single_probe_limit", "ok" if policy["max_probe_count"] <= 1 else "review", "First pilot should allow one micro probe only."),
        _check("probe_notional_conservative", "ok" if notional_cap <= max(policy["seed_capital_usdt"] * 0.03, 10.0) else "review", "Probe notional is constrained below the seed envelope."),
        _check("real_submit_close_default_off", "ok", "Eligibility gate does not place or close orders."),
    ]
    return {
        "engine": "autonomous_controlled_micro_probe_eligibility_gate", "revision": 156, "status": _final_status(checks),
        "eligibility": {"decision": "ELIGIBLE_REVIEW" if _final_status(checks) == "ok" else _final_status(checks).upper(), "max_probe_notional_usdt": round(notional_cap, 6), "max_probe_count": min(policy["max_probe_count"], 1), "symbols": policy["pilot_symbols"], "strategies": policy["pilot_strategies"], "owner_confirmed": policy["owner_probe_confirmation"], "micro_probe_enabled": policy["micro_probe_enabled"]},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "dry_run_shadow_execution_monitor",
    }


def build_rev157_live_dry_run_shadow_execution_monitor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    shadow_records = data.get("shadow_execution_records") if isinstance(data.get("shadow_execution_records"), list) else []
    observed = len(shadow_records)
    mismatches = len([r for r in shadow_records if isinstance(r, dict) and str(r.get("status") or "").lower() in {"mismatch", "drift", "failed"}])
    discrepancy_count = max(policy["shadow_discrepancy_count"], mismatches)
    checks = [
        _check("shadow_hours_complete", "ok" if policy["dry_run_shadow_hours"] >= policy["min_shadow_hours"] else "review", "Dry-run shadow observation window should be complete."),
        _check("shadow_match_rate", "ok" if policy["shadow_match_rate_pct"] >= policy["min_shadow_match_rate_pct"] else "review", "Shadow execution plan should match expected journal/position flow."),
        _check("shadow_discrepancy_limit", "ok" if discrepancy_count <= policy["max_shadow_discrepancy_count"] else "blocked", "Unexpected shadow discrepancies are capped."),
        _check("observations_available", "ok" if observed > 0 or policy["dry_run_shadow_hours"] >= policy["min_shadow_hours"] else "review", "Either records or sufficient configured observation is required."),
        _check("network_default_off", "ok", "Shadow monitor is read-only and performs no exchange call."),
    ]
    return {
        "engine": "autonomous_live_dry_run_shadow_execution_monitor", "revision": 157, "status": _final_status(checks),
        "shadow_monitor": {"observed_records": observed, "shadow_hours": policy["dry_run_shadow_hours"], "required_hours": policy["min_shadow_hours"], "match_rate_pct": policy["shadow_match_rate_pct"], "discrepancy_count": discrepancy_count, "recommendation": "continue_shadow" if _final_status(checks) != "ok" else "ready_for_permission_recheck"},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "exchange_permission_drift_detector",
    }


def build_rev158_exchange_readiness_permission_drift_detector(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    auth = _auth_for_user(auth_store, username)
    checks = [
        _check("api_key_present", "ok" if _safe_bool(auth.get("api_key_present"), False) else "blocked", "API key presence is checked without exposing its value."),
        _check("secret_present", "ok" if _safe_bool(auth.get("secret_present"), False) else "blocked", "Secret presence is checked without exposing its value."),
        _check("read_permission", "ok" if _safe_bool(auth.get("read_permission"), False) else "blocked", "Read-only permission must be available for reconciliation."),
        _check("trade_permission_review", "ok" if _safe_bool(auth.get("trade_permission"), False) else "review", "Trade permission is required only after approval-gated launch."),
        _check("permission_snapshot_fresh", "ok" if policy["permission_snapshot_fresh"] or policy["read_only_exchange_check_passed"] else "review", "Permission snapshot should be recently verified."),
        _check("permission_drift_absent", "ok" if not policy["permission_drift_detected"] else "blocked", "Any permission drift blocks pilot progression."),
        _check("no_secret_response", "ok", "No API key, token or secret value is returned."),
    ]
    return {
        "engine": "autonomous_exchange_readiness_permission_drift_detector", "revision": 158, "status": _final_status(checks),
        "permission_readiness": {"api_key_present": _safe_bool(auth.get("api_key_present"), False), "secret_present": _safe_bool(auth.get("secret_present"), False), "read_permission": _safe_bool(auth.get("read_permission"), False), "trade_permission": _safe_bool(auth.get("trade_permission"), False), "permission_snapshot_fresh": policy["permission_snapshot_fresh"], "permission_drift_detected": policy["permission_drift_detected"]},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "pilot_risk_envelope_enforcer",
    }


def build_rev159_pilot_risk_envelope_enforcer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    capital = build_rev145_capital_protection_summary(data, settings, auth_store, username)
    perf = build_rev135_performance_sentinel_v2(data, settings, auth_store, username)
    open_positions = _open_positions(data)
    emergency = _safe_bool(data.get("emergency_stop"), False) or _safe_bool((data.get("real_trade") or {}).get("emergency_lock") if isinstance(data.get("real_trade"), dict) else False, False)
    today_pnl = _safe_float(data.get("today_pnl_usdt"), _safe_float(data.get("daily_pnl_usdt"), 0.0))
    checks = [
        _check("emergency_clear", "ok" if not emergency else "blocked", "Emergency state blocks the pilot."),
        _check("daily_loss_not_hit", "ok" if today_pnl >= -abs(policy["daily_loss_limit_usdt"]) else "blocked", "Daily hard stop must not be breached."),
        _check("open_position_limit", "ok" if len(open_positions) < policy["max_open_positions"] else "blocked", "Open position count must stay below pilot envelope."),
        _check("performance_not_stop", "ok" if str((perf.get("summary_result") or {}).get("performance") or "normal").lower() not in {"stop", "weak_stop"} else "review", "Performance sentinel must not request stop."),
        _check("capital_protection_not_stop", "ok" if str((capital.get("summary_result") or {}).get("trade") or "hold").lower() not in {"stop", "halt"} else "blocked", "Capital protection must not request halt."),
        _check("max_notional_hard_cap", "ok" if policy["max_probe_notional_usdt"] <= max(policy["seed_capital_usdt"] * 0.03, 10.0) else "review", "Micro probe notional stays inside hard cap."),
    ]
    return {
        "engine": "autonomous_pilot_risk_envelope_enforcer", "revision": 159, "status": _final_status(checks),
        "risk_envelope": {"seed_capital_usdt": policy["seed_capital_usdt"], "max_probe_notional_usdt": min(policy["max_probe_notional_usdt"], max(policy["seed_capital_usdt"] * 0.03, 0.0)), "daily_loss_limit_usdt": policy["daily_loss_limit_usdt"], "daily_trade_cap": policy["daily_trade_cap"], "max_open_positions": policy["max_open_positions"], "current_open_positions": len(open_positions), "today_pnl_usdt": today_pnl, "emergency": emergency},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "micro_real_pilot_decision_packet",
    }


def build_rev160_micro_real_pilot_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    eligibility = build_rev156_controlled_micro_probe_eligibility_gate(data, settings, auth_store, username)
    shadow = build_rev157_live_dry_run_shadow_execution_monitor(data, settings, auth_store, username)
    permission = build_rev158_exchange_readiness_permission_drift_detector(data, settings, auth_store, username)
    envelope = build_rev159_pilot_risk_envelope_enforcer(data, settings, auth_store, username)
    stabilization = build_rev130_first_live_stabilization_report(data, settings, auth_store, username)
    statuses = [eligibility.get("status"), shadow.get("status"), permission.get("status"), envelope.get("status"), stabilization.get("status")]
    if "blocked" in statuses:
        decision = "NO-PILOT"
        next_action = "fix_blockers"
    elif "review" in statuses:
        decision = "PILOT-REVIEW"
        next_action = "owner_review_shadow_and_permissions"
    else:
        decision = "LIMITED-MICRO-PILOT-READY"
        next_action = "one_probe_preview_after_owner_approval"
    checks = [
        _check("eligibility_gate", eligibility.get("status", "blocked"), "Rev156 eligibility result."),
        _check("shadow_monitor", shadow.get("status", "blocked"), "Rev157 shadow monitor result."),
        _check("permission_drift", permission.get("status", "blocked"), "Rev158 permission drift result."),
        _check("risk_envelope", envelope.get("status", "blocked"), "Rev159 risk envelope result."),
        _check("live_stabilization", stabilization.get("status", "blocked"), "Rev130 stabilization should remain acceptable."),
        _check("real_submit_close_default_off", "ok", "Decision packet cannot place or close orders."),
    ]
    env = envelope.get("risk_envelope", {}) if isinstance(envelope.get("risk_envelope"), dict) else {}
    eli = eligibility.get("eligibility", {}) if isinstance(eligibility.get("eligibility"), dict) else {}
    return {
        "engine": "autonomous_micro_real_pilot_decision_packet", "revision": 160, "status": _final_status(checks),
        "pilot_decision_packet": {"decision": decision, "next_action": next_action, "max_probe_notional_usdt": env.get("max_probe_notional_usdt", eli.get("max_probe_notional_usdt", 0.0)), "daily_loss_limit_usdt": env.get("daily_loss_limit_usdt", 0.0), "daily_trade_cap": env.get("daily_trade_cap", 0), "symbols": eli.get("symbols", []), "strategies": eli.get("strategies", []), "probe_count": eli.get("max_probe_count", 0), "real_submit_close": "OFF"},
        "summary_result": {"pilot": decision, "notional": env.get("max_probe_notional_usdt", eli.get("max_probe_notional_usdt", 0.0)), "max_loss": env.get("daily_loss_limit_usdt", 0.0), "trade_cap": env.get("daily_trade_cap", 0), "next": next_action},
        "outputs": {"eligibility": eligibility, "shadow_monitor": shadow, "permission_drift": permission, "risk_envelope": envelope, "stabilization": stabilization},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "controlled_micro_probe_preview_only",
    }


REV_BUILDERS = {
    156: build_rev156_controlled_micro_probe_eligibility_gate,
    157: build_rev157_live_dry_run_shadow_execution_monitor,
    158: build_rev158_exchange_readiness_permission_drift_detector,
    159: build_rev159_pilot_risk_envelope_enforcer,
    160: build_rev160_micro_real_pilot_decision_packet,
}

REV_KEYS = {
    156: "autonomous_controlled_micro_probe_eligibility_gate",
    157: "autonomous_live_dry_run_shadow_execution_monitor",
    158: "autonomous_exchange_readiness_permission_drift_detector",
    159: "autonomous_pilot_risk_envelope_enforcer",
    160: "autonomous_micro_real_pilot_decision_packet",
}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_controlled_micro_real_pilot_readiness_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev156-160 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 160:
        return {"revision": 160, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("eligibility", "shadow_monitor", "permission_readiness", "risk_envelope"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(156, 161)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_micro_real_pilot_decision_packet"]
    return {
        "engine": "autonomous_controlled_micro_real_pilot_readiness_block", "revision": 160, "status": block_status,
        "generated_at": now_iso(), "username": username, "outputs": outputs,
        "summary_result": final.get("summary_result", {}), "pilot_decision_packet": final.get("pilot_decision_packet", {}),
        "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True,
        "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False,
        "next_allowed_step": "one_probe_preview_after_owner_review_no_auto_submit",
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
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "Pilot readiness actions are advisory/approval-gated."),
    ]
    return {
        "engine": "autonomous_controlled_micro_real_pilot_readiness_quality_gate", "revision": int(revision),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks),
        "checks": checks, "check_totals": _totals(checks), "network_default_off": True,
        "real_submit_default_off": True, "real_close_default_off": True, "contains_secret": False, "secret_values_returned": False,
    }
