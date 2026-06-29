from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_controlled_micro_real_pilot_readiness_block_service import build_rev160_micro_real_pilot_decision_packet
from services.autonomous_performance_observability_block_service import build_rev135_performance_sentinel_v2


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
    p = _settings(settings, "autonomous_micro_real_pilot_control_evidence_loop")
    old = _settings(settings, "autonomous_controlled_micro_real_pilot")
    return {
        "owner_probe_confirmation": _safe_bool(p.get("owner_probe_confirmation"), _safe_bool(old.get("owner_probe_confirmation"), False)),
        "probe_preview_enabled": _safe_bool(p.get("probe_preview_enabled"), False),
        "max_preview_notional_usdt": max(0.0, _safe_float(p.get("max_preview_notional_usdt"), _safe_float(old.get("max_probe_notional_usdt"), 3.0))),
        "max_probe_count": max(1, _safe_int(p.get("max_probe_count"), _safe_int(old.get("max_probe_count"), 1))),
        "max_allowed_slippage_pct": max(0.0, _safe_float(p.get("max_allowed_slippage_pct"), 0.08)),
        "max_allowed_fee_pct": max(0.0, _safe_float(p.get("max_allowed_fee_pct"), 0.10)),
        "max_latency_ms": max(1, _safe_int(p.get("max_latency_ms"), 1500)),
        "evidence_required_fields": p.get("evidence_required_fields") if isinstance(p.get("evidence_required_fields"), list) else ["intent_id", "symbol", "strategy", "notional_usdt", "decision", "risk_snapshot", "approval_snapshot"],
        "auto_promote_after_probe": _safe_bool(p.get("auto_promote_after_probe"), False),
    }


def _pilot_state(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    real = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    return real.get("micro_pilot") if isinstance(real.get("micro_pilot"), dict) else data.get("micro_pilot", {}) if isinstance(data.get("micro_pilot"), dict) else {}


def _journal_entries(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    candidates = []
    for key in ("trade_journal", "journal", "audit_trail"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend([x for x in value if isinstance(x, dict)])
    real = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    for key in ("trade_journal", "journal", "order_journal", "exchange_responses"):
        value = real.get(key)
        if isinstance(value, list):
            candidates.extend([x for x in value if isinstance(x, dict)])
    return candidates[-100:]


def _micro_probe_entries(data: dict | None) -> list[dict]:
    return [e for e in _journal_entries(data) if str(e.get("lane") or e.get("mode") or e.get("type") or "").lower() in {"micro-real", "micro_real", "micro_probe", "pilot"} or "micro" in str(e.get("event") or e.get("category") or "").lower()]


def _quality_from_entries(entries: list[dict]) -> dict:
    if not entries:
        return {"count": 0, "avg_slippage_pct": 0.0, "avg_fee_pct": 0.0, "max_latency_ms": 0, "rejected": 0, "partial_fill": 0, "realized_pnl_usdt": 0.0}
    slippages = [_safe_float(e.get("slippage_pct"), 0.0) for e in entries]
    fees = [_safe_float(e.get("fee_pct"), _safe_float(e.get("fee_usdt"), 0.0)) for e in entries]
    latencies = [_safe_int(e.get("latency_ms"), 0) for e in entries]
    return {
        "count": len(entries),
        "avg_slippage_pct": round(sum(slippages) / max(len(slippages), 1), 6),
        "avg_fee_pct": round(sum(fees) / max(len(fees), 1), 6),
        "max_latency_ms": max(latencies) if latencies else 0,
        "rejected": len([e for e in entries if str(e.get("status") or "").lower() in {"rejected", "failed", "error"}]),
        "partial_fill": len([e for e in entries if str(e.get("fill_status") or e.get("status") or "").lower() in {"partial", "partially_filled"}]),
        "realized_pnl_usdt": round(sum(_safe_float(e.get("realized_pnl_usdt"), _safe_float(e.get("pnl_usdt"), 0.0)) for e in entries), 6),
    }


def build_rev161_micro_probe_preview_contract(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    packet = build_rev160_micro_real_pilot_decision_packet(data, settings, auth_store, username)
    decision = (packet.get("pilot_decision_packet") or {}).get("decision")
    checks = [
        _check("rev160_packet_not_blocked", "ok" if decision in {"LIMITED-MICRO-PILOT-READY", "PILOT-REVIEW"} else "blocked", "Rev160 must allow review or ready state."),
        _check("owner_confirmation_required", "ok" if policy["owner_probe_confirmation"] else "blocked", "Owner confirmation is required before any live probe preview."),
        _check("preview_flag_off_by_default", "review" if policy["probe_preview_enabled"] else "ok", "Preview enable flag remains explicit and off by default."),
        _check("single_probe_contract", "ok" if policy["max_probe_count"] <= 1 else "review", "First controlled pilot remains one-probe only."),
        _check("notional_guard", "ok" if policy["max_preview_notional_usdt"] <= 10 else "review", "Preview notional stays conservative."),
        _check("no_network_or_order", "ok", "Contract only returns preview; it cannot submit or close."),
    ]
    return {
        "engine": "autonomous_micro_probe_preview_contract", "revision": 161, "status": _final_status(checks),
        "preview_contract": {"decision": "PREVIEW_ONLY", "probe_preview_enabled": policy["probe_preview_enabled"], "max_preview_notional_usdt": policy["max_preview_notional_usdt"], "max_probe_count": min(policy["max_probe_count"], 1), "required_owner_confirmation": True, "real_submit_close": "OFF"},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "evidence_capture_only",
    }


def build_rev162_micro_probe_evidence_recorder(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    pilot = _pilot_state(data)
    evidence = pilot.get("last_evidence") if isinstance(pilot.get("last_evidence"), dict) else {}
    missing = [f for f in policy["evidence_required_fields"] if f not in evidence]
    checks = [
        _check("evidence_schema_available", "ok", "Evidence schema is deterministic and secret-free."),
        _check("last_evidence_complete", "ok" if not missing else "review", "Missing evidence fields: " + ", ".join(missing[:8]), required=False),
        _check("secret_free_evidence", "ok" if not any("secret" in str(k).lower() or "key" in str(k).lower() for k in evidence.keys()) else "blocked", "Evidence keys must not expose secrets."),
        _check("runtime_write_preview_only", "ok", "Recorder describes journal fields; no file write occurs in this endpoint."),
    ]
    return {
        "engine": "autonomous_micro_probe_evidence_recorder", "revision": 162, "status": _final_status(checks),
        "evidence_contract": {"required_fields": policy["evidence_required_fields"], "last_evidence_complete": not missing, "missing_fields": missing, "journal_target": "secret_free_trade_journal", "runtime_write_in_route": False},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "pilot_outcome_reconciliation",
    }


def build_rev163_micro_probe_outcome_reconciler(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    entries = _micro_probe_entries(data)
    quality = _quality_from_entries(entries)
    checks = [
        _check("journal_entries_present", "ok" if entries else "review", "No micro probe journal entry found yet.", required=False),
        _check("no_rejected_probe", "ok" if quality["rejected"] == 0 else "blocked", "Rejected probe requires halt/review."),
        _check("no_unresolved_partial_fill", "ok" if quality["partial_fill"] == 0 else "review", "Partial fill requires manual attention."),
        _check("reconciliation_secret_free", "ok", "Only aggregate outcome metrics are returned."),
        _check("no_close_submit", "ok", "Reconciler cannot close positions."),
    ]
    return {
        "engine": "autonomous_micro_probe_outcome_reconciler", "revision": 163, "status": _final_status(checks),
        "outcome_reconciliation": {"micro_probe_entries": quality["count"], "quality": quality, "manual_attention": quality["rejected"] > 0 or quality["partial_fill"] > 0, "reconciled": bool(entries) and quality["rejected"] == 0},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "halt_or_demotion_gate",
    }


def build_rev164_micro_probe_auto_halt_demotion_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    rec = build_rev163_micro_probe_outcome_reconciler(data, settings, auth_store, username)
    quality = (rec.get("outcome_reconciliation") or {}).get("quality", {})
    perf = build_rev135_performance_sentinel_v2(data, settings, auth_store, username)
    halt_reasons = []
    if _safe_float(quality.get("avg_slippage_pct"), 0.0) > policy["max_allowed_slippage_pct"]:
        halt_reasons.append("slippage_above_limit")
    if _safe_float(quality.get("avg_fee_pct"), 0.0) > policy["max_allowed_fee_pct"]:
        halt_reasons.append("fee_above_limit")
    if _safe_int(quality.get("max_latency_ms"), 0) > policy["max_latency_ms"]:
        halt_reasons.append("latency_above_limit")
    if _safe_float(quality.get("realized_pnl_usdt"), 0.0) < 0:
        halt_reasons.append("probe_negative_pnl")
    if rec.get("status") == "blocked":
        halt_reasons.append("reconciliation_blocked")
    perf_result = perf.get("summary_result") if isinstance(perf.get("summary_result"), dict) else {}
    if str(perf_result.get("performance") or "normal").lower() in {"stop", "weak", "weak_stop"}:
        halt_reasons.append("performance_sentinel_weak")
    action = "HALT_MICRO_PILOT" if halt_reasons else "KEEP_REVIEW_ONLY"
    checks = [
        _check("reconciliation_not_blocked", "ok" if rec.get("status") != "blocked" else "blocked", "Outcome reconciliation must not be blocked."),
        _check("quality_inside_limits", "ok" if not halt_reasons else "review", "Halt reasons: " + (", ".join(halt_reasons) or "none"), required=False),
        _check("auto_promotion_disabled", "ok" if not policy["auto_promote_after_probe"] else "blocked", "Auto-promotion after a probe must remain disabled."),
        _check("demotion_preview_only", "ok", "Gate recommends halt/demotion but does not execute exchange actions."),
    ]
    return {
        "engine": "autonomous_micro_probe_auto_halt_demotion_gate", "revision": 164, "status": _final_status(checks),
        "halt_demotion": {"action": action, "halt_reasons": halt_reasons, "auto_promote_after_probe": policy["auto_promote_after_probe"], "size_action": "reduce_or_hold", "requires_owner_review": True},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "pilot_feedback_decision_packet",
    }


def build_rev165_micro_pilot_feedback_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    preview = build_rev161_micro_probe_preview_contract(data, settings, auth_store, username)
    evidence = build_rev162_micro_probe_evidence_recorder(data, settings, auth_store, username)
    rec = build_rev163_micro_probe_outcome_reconciler(data, settings, auth_store, username)
    halt = build_rev164_micro_probe_auto_halt_demotion_gate(data, settings, auth_store, username)
    statuses = [preview.get("status"), evidence.get("status"), rec.get("status"), halt.get("status")]
    halt_action = (halt.get("halt_demotion") or {}).get("action")
    if "blocked" in statuses or halt_action == "HALT_MICRO_PILOT":
        decision = "STOP_OR_FIX_BEFORE_NEXT_PROBE"
    elif "review" in statuses:
        decision = "REVIEW_BEFORE_NEXT_PROBE"
    else:
        decision = "ONE_MORE_PREVIEW_ALLOWED"
    checks = [
        _check("preview_contract", preview.get("status", "blocked"), "Rev161 preview contract."),
        _check("evidence_recorder", evidence.get("status", "blocked"), "Rev162 evidence recorder."),
        _check("outcome_reconciler", rec.get("status", "blocked"), "Rev163 outcome reconciliation."),
        _check("halt_demotion_gate", halt.get("status", "blocked"), "Rev164 halt/demotion gate."),
        _check("real_submit_close_default_off", "ok", "Decision packet cannot place or close orders."),
    ]
    return {
        "engine": "autonomous_micro_real_pilot_control_evidence_loop", "revision": 165, "status": _final_status(checks), "generated_at": now_iso(),
        "feedback_decision_packet": {"decision": decision, "next_action": "owner_review_required", "real_submit_close": "OFF", "auto_promotion": "OFF", "recommended_size_action": (halt.get("halt_demotion") or {}).get("size_action", "hold"), "halt_reasons": (halt.get("halt_demotion") or {}).get("halt_reasons", [])},
        "summary_result": {"pilot_control": decision, "evidence": evidence.get("status"), "outcome": rec.get("status"), "action": (halt.get("halt_demotion") or {}).get("action", "KEEP_REVIEW_ONLY"), "real_submit_close": "OFF"},
        "outputs": {"preview_contract": preview, "evidence_recorder": evidence, "outcome_reconciler": rec, "halt_demotion_gate": halt},
        "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True,
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "continue_paper_shadow_or_owner_approved_micro_probe_preview",
    }


REV_BUILDERS = {
    161: build_rev161_micro_probe_preview_contract,
    162: build_rev162_micro_probe_evidence_recorder,
    163: build_rev163_micro_probe_outcome_reconciler,
    164: build_rev164_micro_probe_auto_halt_demotion_gate,
    165: build_rev165_micro_pilot_feedback_decision_packet,
}

REV_KEYS = {
    161: "autonomous_micro_probe_preview_contract",
    162: "autonomous_micro_probe_evidence_recorder",
    163: "autonomous_micro_probe_outcome_reconciler",
    164: "autonomous_micro_probe_auto_halt_demotion_gate",
    165: "autonomous_micro_pilot_feedback_decision_packet",
}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_micro_real_pilot_control_evidence_loop", "revision": revision, "status": "blocked", "message": "Unsupported Rev161-165 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 165:
        return {"revision": 165, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("preview_contract", "evidence_contract", "outcome_reconciliation", "halt_demotion"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(161, 166)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_micro_pilot_feedback_decision_packet"]
    return {
        "engine": "autonomous_micro_real_pilot_control_evidence_loop_block", "revision": 165, "status": block_status,
        "generated_at": now_iso(), "username": username, "outputs": outputs,
        "summary_result": final.get("summary_result", {}), "feedback_decision_packet": final.get("feedback_decision_packet", {}),
        "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True,
        "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False,
        "next_allowed_step": "owner_review_before_any_micro_probe_repeat",
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
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "All actions remain advisory/approval-gated."),
    ]
    return {
        "engine": "autonomous_micro_real_pilot_control_evidence_loop_quality_gate", "revision": int(revision),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks),
        "checks": checks, "check_totals": _totals(checks), "network_default_off": True,
        "real_submit_default_off": True, "real_close_default_off": True, "contains_secret": False, "secret_values_returned": False,
    }
