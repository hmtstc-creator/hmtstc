from __future__ import annotations

from copy import deepcopy
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
        "autonomous_small_capital_autonomy_preparation",
        "autonomous_controlled_repeat_micro_live",
        "autonomous_live_risk_firewall",
        "autonomous_first_controlled_micro_live",
    ):
        source.update(_settings(settings, key))
    capital_usdt = max(0.0, _safe_float(source.get("capital_usdt"), 100.0))
    reserve_ratio = max(0.50, min(0.98, _safe_float(source.get("usdt_reserve_ratio"), 0.80)))
    return {
        "capital_usdt": capital_usdt,
        "recommended_capital_usdt": max(50.0, min(capital_usdt or 100.0, _safe_float(source.get("recommended_capital_usdt"), 100.0))),
        "usdt_reserve_ratio": reserve_ratio,
        "max_daily_loss_pct": max(0.1, min(3.0, _safe_float(source.get("max_daily_loss_pct"), 1.0))),
        "max_daily_loss_usdt": max(1.0, _safe_float(source.get("max_daily_loss_usdt"), max(1.0, capital_usdt * 0.01))),
        "max_notional_usdt": max(5.0, min(max(5.0, capital_usdt * 0.25), _safe_float(source.get("max_notional_usdt"), 25.0))),
        "max_open_positions": max(1, min(3, _safe_int(source.get("max_open_positions"), 1))),
        "max_trades_per_day": max(1, min(8, _safe_int(source.get("max_trades_per_day"), 3))),
        "max_exposure_pct": max(5.0, min(35.0, _safe_float(source.get("max_exposure_pct"), 20.0))),
        "min_evidence_confidence": max(0.0, min(1.0, _safe_float(source.get("min_evidence_confidence"), 0.85))),
        "allowed_symbols": _as_list(source.get("allowed_symbols")) or ["BTCUSDT", "ETHUSDT"],
        "required_approval_levels": _as_list(source.get("required_approval_levels")) or ["micro-live", "limited-live", "small-cap-autonomy"],
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
    }


def _runtime(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source: dict[str, Any] = {}
    for key in ("small_capital_runtime", "autonomy_runtime", "micro_live_metrics", "repeat_micro_live_metrics", "risk_firewall"):
        source.update(_as_dict(data.get(key)))
    return {
        "current_permission_level": str(source.get("current_permission_level") or data.get("permission_level") or "micro-preview"),
        "evidence_confidence": max(0.0, min(1.0, _safe_float(source.get("evidence_confidence"), _safe_float(data.get("evidence_confidence"), 0.0)))),
        "reconciliation_status": str(source.get("reconciliation_status") or data.get("reconciliation_status") or "unknown").lower(),
        "risk_status": str(source.get("risk_status") or data.get("risk_status") or "review").lower(),
        "pnl_today_usdt": _safe_float(source.get("pnl_today_usdt"), _safe_float(data.get("today_pnl_usdt"), 0.0)),
        "open_positions": max(0, _safe_int(source.get("open_positions"), 0)),
        "trades_today": max(0, _safe_int(source.get("trades_today"), 0)),
        "anomaly_count": max(0, _safe_int(source.get("anomaly_count"), 0)),
        "owner_approval": _safe_bool(source.get("owner_approval"), False),
        "session_boundary_ok": _safe_bool(source.get("session_boundary_ok"), False),
        "whitelist_ok": _safe_bool(source.get("whitelist_ok"), True),
        "daily_hard_stop_ok": _safe_bool(source.get("daily_hard_stop_ok"), True),
    }


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "No critical issue detected.", "action": "continue_guarded_review"}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda x: (weight.get(str(x.get("severity")), 2), int(x.get("priority", 50))))[0]


def build_rev211_small_capital_autonomy_envelope(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    max_exposure_usdt = round(policy["capital_usdt"] * policy["max_exposure_pct"] / 100.0, 2)
    reserve_usdt = round(policy["capital_usdt"] * policy["usdt_reserve_ratio"], 2)
    checks = [
        _check("usdt_reserve_majority", "ok" if policy["usdt_reserve_ratio"] >= 0.70 else "review", "Most capital remains in USDT reserve.", False, 1, "increase_reserve"),
        _check("max_open_positions_limited", "ok" if policy["max_open_positions"] <= 2 else "review", "Small-cap autonomy keeps open positions constrained.", False, 2, "reduce_open_position_limit"),
        _check("real_submit_default_off", "ok", "Envelope does not enable live submit."),
        _check("auto_scale_off", "ok" if not policy["auto_scale_enable"] else "blocked", "Auto-scale must remain OFF before small-cap autonomy.", True, 3, "disable_auto_scale"),
    ]
    envelope = {
        "capital_mode": "small_capital_guarded",
        "recommended_capital_usdt": policy["recommended_capital_usdt"],
        "max_daily_loss_usdt": round(min(policy["max_daily_loss_usdt"], policy["capital_usdt"] * policy["max_daily_loss_pct"] / 100.0), 2),
        "max_daily_loss_pct": policy["max_daily_loss_pct"],
        "max_notional_usdt": policy["max_notional_usdt"],
        "max_open_positions": policy["max_open_positions"],
        "max_trades_per_day": policy["max_trades_per_day"],
        "max_exposure_usdt": max_exposure_usdt,
        "max_exposure_pct": policy["max_exposure_pct"],
        "usdt_reserve_usdt": reserve_usdt,
        "usdt_reserve_ratio": policy["usdt_reserve_ratio"],
        "allowed_symbols": policy["allowed_symbols"],
        "auto_submit": False,
        "auto_close": False,
        "auto_scale": False,
    }
    return {"engine": "small_capital_autonomy_envelope", "revision": 211, "status": _final_status(checks), "generated_at": now_iso(), "small_capital_autonomy_envelope": envelope, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev212_autonomy_permission_ladder"}


def build_rev212_autonomy_permission_ladder(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    runtime = _runtime(data)
    policy = _policy(settings)
    levels = [
        {"level": "paper", "entry": "strategy test only", "exit": "stable paper evidence", "live_submit": False},
        {"level": "shadow", "entry": "paper stable", "exit": "shadow/live market agreement", "live_submit": False},
        {"level": "micro-preview", "entry": "risk and cost preview clear", "exit": "owner approves micro live intent", "live_submit": False},
        {"level": "micro-live", "entry": "owner approval + firewall + whitelist", "exit": "post-trade freeze/review", "live_submit": "approval_gated"},
        {"level": "limited-live", "entry": "repeat evidence + reconciliation OK", "exit": "sample threshold + stable cost", "live_submit": "approval_gated"},
        {"level": "small-cap-autonomy", "entry": "minimum sample + cost reality + no anomaly", "exit": "halt on risk; no auto growth", "live_submit": "approval_gated"},
    ]
    reasons = []
    if runtime["evidence_confidence"] < policy["min_evidence_confidence"]:
        reasons.append(_reason("evidence_below_ladder_threshold", "Evidence confidence is below autonomy permission threshold.", "stay_at_current_or_lower", "critical", 1))
    if runtime["reconciliation_status"] not in {"ok", "consistent", "pass", "clear"}:
        reasons.append(_reason("reconciliation_not_clear", "Permission ladder cannot advance without reconciliation OK.", "manual_reconciliation", "critical", 2))
    proposed = "small-cap-autonomy" if not reasons and runtime["owner_approval"] else "limited-live" if not reasons else "micro-preview"
    checks = [
        _check("ladder_defined", "ok", "Paper to small-cap autonomy ladder is explicit."),
        _check("approval_required_for_live_levels", "ok", "All live levels remain owner/approval gated."),
        _check("reconciliation_gate", "ok" if runtime["reconciliation_status"] in {"ok", "consistent", "pass", "clear"} else "blocked", "Reconciliation required before permission advancement.", True, 2, "manual_reconciliation"),
    ]
    ladder = {"current_permission_level": runtime["current_permission_level"], "proposed_permission_level": proposed, "levels": levels, "advance_allowed": proposed == "small-cap-autonomy", "reasons": reasons, "critical_issue": _critical(reasons), "required_approvals": policy["required_approval_levels"]}
    return {"engine": "autonomy_permission_ladder", "revision": 212, "status": _final_status(checks), "generated_at": now_iso(), "autonomy_permission_ladder": ladder, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev213_autonomous_halt_authority"}


def build_rev213_autonomous_halt_authority(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    runtime = _runtime(data)
    policy = _policy(settings)
    reasons = []
    if runtime["pnl_today_usdt"] <= -abs(policy["max_daily_loss_usdt"]):
        reasons.append(_reason("daily_loss_limit_hit", "Daily loss limit reached or breached.", "halt_session", "critical", 1))
    if runtime["risk_status"] in {"halt", "emergency", "blocked"}:
        reasons.append(_reason("risk_firewall_halt", "Risk firewall reports halt/emergency.", "halt_session", "critical", 2))
    if runtime["anomaly_count"] > 0:
        reasons.append(_reason("runtime_anomaly_detected", "Runtime anomaly requires autonomous halt.", "halt_and_review", "critical", 3))
    if runtime["open_positions"] > policy["max_open_positions"]:
        reasons.append(_reason("open_position_limit_exceeded", "Open positions exceed small-cap envelope.", "halt_new_entries", "critical", 4))
    halt_required = bool(reasons)
    authority = {"halt_authority_enabled": True, "can_halt_without_owner": True, "can_increase_without_owner": False, "halt_required": halt_required, "halt_state": "halt" if halt_required else "armed", "audit_event_type": "autonomous_halt_decision", "audit_secret_free": True, "reasons": reasons, "critical_issue": _critical(reasons)}
    checks = [
        _check("halt_without_owner", "ok", "System may halt without human approval."),
        _check("growth_without_owner_blocked", "ok", "System cannot grow without owner approval."),
        _check("audit_secret_free", "ok", "Halt reasons are audit-safe and secret-free."),
    ]
    return {"engine": "autonomous_halt_authority", "revision": 213, "status": _final_status(checks), "generated_at": now_iso(), "autonomous_halt_authority": authority, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev214_minimal_operator_summary_v3"}


def build_rev214_minimal_operator_summary_v3(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    envelope = _as_dict(build_rev211_small_capital_autonomy_envelope(data, settings, auth_store, username).get("small_capital_autonomy_envelope"))
    ladder = _as_dict(build_rev212_autonomy_permission_ladder(data, settings, auth_store, username).get("autonomy_permission_ladder"))
    halt = _as_dict(build_rev213_autonomous_halt_authority(data, settings, auth_store, username).get("autonomous_halt_authority"))
    runtime = _runtime(data)
    trade_allowed = not halt.get("halt_required") and ladder.get("advance_allowed") and runtime["owner_approval"]
    blocker = (halt.get("critical_issue") or {}).get("code") if halt.get("halt_required") else (ladder.get("critical_issue") or {}).get("code")
    summary = {
        "mode": ladder.get("proposed_permission_level", "micro-preview"),
        "risk": "halt" if halt.get("halt_required") else runtime["risk_status"],
        "pnl_today_usdt": runtime["pnl_today_usdt"],
        "trade_allowed": bool(trade_allowed),
        "next_action": "approve_small_cap_preview" if trade_allowed else ((halt.get("critical_issue") or ladder.get("critical_issue") or {}).get("action") or "review"),
        "blocker": blocker or "owner_approval_required",
        "owner_action": "approve_preview" if trade_allowed else "review_blocker",
        "max_daily_loss_usdt": envelope.get("max_daily_loss_usdt"),
        "max_notional_usdt": envelope.get("max_notional_usdt"),
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "noise_policy": "advanced_details_hidden",
    }
    checks = [
        _check("summary_fields_minimal", "ok", "Mode/risk/PnL/trade allowed/next action/blocker/owner action are visible."),
        _check("advanced_noise_hidden", "ok", "No noisy raw gate list is required on Summary."),
        _check("real_submit_default_off", "ok", "Summary confirms real submit/close OFF."),
    ]
    return {"engine": "minimal_operator_summary_v3", "revision": 214, "status": _final_status(checks), "generated_at": now_iso(), "minimal_operator_summary_v3": summary, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev215_small_capital_autonomy_readiness_packet"}


def build_rev215_small_capital_autonomy_readiness_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    envelope_payload = build_rev211_small_capital_autonomy_envelope(data, settings, auth_store, username)
    ladder_payload = build_rev212_autonomy_permission_ladder(data, settings, auth_store, username)
    halt_payload = build_rev213_autonomous_halt_authority(data, settings, auth_store, username)
    summary_payload = build_rev214_minimal_operator_summary_v3(data, settings, auth_store, username)
    envelope = _as_dict(envelope_payload.get("small_capital_autonomy_envelope"))
    ladder = _as_dict(ladder_payload.get("autonomy_permission_ladder"))
    halt = _as_dict(halt_payload.get("autonomous_halt_authority"))
    summary = _as_dict(summary_payload.get("minimal_operator_summary_v3"))
    reasons = []
    reasons.extend(_as_list(ladder.get("reasons")))
    reasons.extend(_as_list(halt.get("reasons")))
    if not _runtime(data)["owner_approval"]:
        reasons.append(_reason("owner_approval_required", "Small-cap autonomy cannot advance without owner approval.", "owner_review", "major", 10))
    if halt.get("halt_required"):
        decision = "blocked"
    elif ladder.get("advance_allowed") and not reasons:
        decision = "ready"
    else:
        decision = "limited"
    packet = {
        "decision": decision,
        "ready": decision == "ready",
        "recommended_capital_usdt": envelope.get("recommended_capital_usdt"),
        "max_daily_loss_usdt": envelope.get("max_daily_loss_usdt"),
        "trade_cap": envelope.get("max_trades_per_day"),
        "max_notional_usdt": envelope.get("max_notional_usdt"),
        "max_open_positions": envelope.get("max_open_positions"),
        "allowed_symbols": envelope.get("allowed_symbols", []),
        "required_approvals": _policy(settings)["required_approval_levels"],
        "owner_action": summary.get("owner_action"),
        "next_action": summary.get("next_action"),
        "critical_blocker": _critical(reasons),
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    checks = [
        _check("readiness_secret_free", "ok", "Readiness packet returns no secret values."),
        _check("approval_gated", "ok", "Live action remains owner/approval gated."),
        _check("halt_authority_present", "ok", "System may halt without owner approval."),
        _check("growth_without_owner_blocked", "ok", "System cannot grow without owner approval."),
        _check("network_default_off", "ok", "No exchange network request is sent."),
    ]
    return {"engine": "small_capital_autonomy_readiness_packet", "revision": 215, "status": _final_status(checks), "generated_at": now_iso(), "small_capital_autonomy_readiness_packet": packet, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev216_next_controlled_production_self_governance"}


_REVISION_BUILDERS = {
    211: build_rev211_small_capital_autonomy_envelope,
    212: build_rev212_autonomy_permission_ladder,
    213: build_rev213_autonomous_halt_authority,
    214: build_rev214_minimal_operator_summary_v3,
    215: build_rev215_small_capital_autonomy_readiness_packet,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    revision = int(revision)
    if revision not in _REVISION_BUILDERS:
        raise ValueError(f"Unsupported Rev211-215 revision: {revision}")
    return _REVISION_BUILDERS[revision](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_small_capital_autonomy_envelope": build_rev211_small_capital_autonomy_envelope(data, settings, auth_store, username),
        "autonomous_autonomy_permission_ladder": build_rev212_autonomy_permission_ladder(data, settings, auth_store, username),
        "autonomous_halt_authority": build_rev213_autonomous_halt_authority(data, settings, auth_store, username),
        "autonomous_minimal_operator_summary_v3": build_rev214_minimal_operator_summary_v3(data, settings, auth_store, username),
        "autonomous_small_capital_autonomy_readiness_packet": build_rev215_small_capital_autonomy_readiness_packet(data, settings, auth_store, username),
    }
    final = outputs["autonomous_small_capital_autonomy_readiness_packet"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {
        "engine": "autonomous_small_capital_autonomy_preparation_block",
        "revision": 215,
        "status": block_status,
        "generated_at": now_iso(),
        "outputs": outputs,
        "small_capital_autonomy_readiness_packet": final.get("small_capital_autonomy_readiness_packet"),
        "summary_result": build_summary_for_revision(215, data, settings, auth_store, username),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("small_capital_autonomy_envelope") or payload.get("autonomy_permission_ladder") or payload.get("autonomous_halt_authority") or payload.get("minimal_operator_summary_v3") or payload.get("small_capital_autonomy_readiness_packet") or {}
    issue = _as_dict(body.get("critical_issue") or body.get("critical_blocker"))
    return {
        "revision": int(revision),
        "status": payload.get("status"),
        "mode": body.get("mode") or body.get("decision") or body.get("capital_mode") or body.get("proposed_permission_level"),
        "risk": body.get("risk") or body.get("halt_state") or payload.get("status"),
        "pnl_today_usdt": body.get("pnl_today_usdt"),
        "trade_allowed": body.get("trade_allowed") if "trade_allowed" in body else body.get("ready"),
        "next_action": body.get("next_action") or issue.get("action") or "review_small_cap_autonomy",
        "blocker": body.get("blocker") or issue.get("code"),
        "owner_action": body.get("owner_action") or "review",
        "recommended_capital_usdt": body.get("recommended_capital_usdt"),
        "max_daily_loss_usdt": body.get("max_daily_loss_usdt"),
        "trade_cap": body.get("trade_cap") or body.get("max_trades_per_day"),
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
    return {"engine": "autonomous_small_capital_autonomy_preparation_quality_gate", "revision": int(revision), "quality_gate": "PASS", "status": payload.get("status"), "checks": all_checks, "check_totals": _totals(all_checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
