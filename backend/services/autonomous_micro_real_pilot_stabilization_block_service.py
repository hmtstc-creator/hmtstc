from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_micro_real_pilot_control_evidence_loop_service import build_rev165_micro_pilot_feedback_decision_packet
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
        "auto_scale": False,
    }


def _policy(settings: dict | None) -> dict:
    p = _settings(settings, "autonomous_micro_real_pilot_stabilization")
    return {
        "min_evidence_count": max(1, _safe_int(p.get("min_evidence_count"), 1)),
        "min_confidence_score": max(0.0, min(100.0, _safe_float(p.get("min_confidence_score"), 70.0))),
        "max_repeat_probe_count": max(1, _safe_int(p.get("max_repeat_probe_count"), 1)),
        "max_negative_pnl_usdt": _safe_float(p.get("max_negative_pnl_usdt"), 0.0),
        "max_slippage_pct": max(0.0, _safe_float(p.get("max_slippage_pct"), 0.08)),
        "max_fee_pct": max(0.0, _safe_float(p.get("max_fee_pct"), 0.10)),
        "scale_auto_apply": _safe_bool(p.get("scale_auto_apply"), False),
        "owner_repeat_probe_confirmation": _safe_bool(p.get("owner_repeat_probe_confirmation"), False),
    }


def _entries(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    out: list[dict] = []
    for key in ("trade_journal", "journal", "audit_trail"):
        value = data.get(key)
        if isinstance(value, list):
            out.extend([x for x in value if isinstance(x, dict)])
    real = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    for key in ("trade_journal", "journal", "order_journal", "exchange_responses"):
        value = real.get(key)
        if isinstance(value, list):
            out.extend([x for x in value if isinstance(x, dict)])
    return out[-250:]


def _micro_entries(data: dict | None) -> list[dict]:
    rows = []
    for e in _entries(data):
        hay = " ".join(str(e.get(k, "")) for k in ("lane", "mode", "type", "event", "category", "decision")).lower()
        if "micro" in hay or "pilot" in hay:
            rows.append(e)
    return rows


def _metrics(entries: list[dict]) -> dict:
    if not entries:
        return {"count": 0, "realized_pnl_usdt": 0.0, "avg_slippage_pct": 0.0, "avg_fee_pct": 0.0, "rejected": 0, "partial_fill": 0, "stale": 0, "duplicate_intent": 0}
    intent_ids = [str(e.get("intent_id") or e.get("client_order_id") or "") for e in entries if e.get("intent_id") or e.get("client_order_id")]
    duplicate_count = len(intent_ids) - len(set(intent_ids))
    return {
        "count": len(entries),
        "realized_pnl_usdt": round(sum(_safe_float(e.get("realized_pnl_usdt"), _safe_float(e.get("pnl_usdt"), 0.0)) for e in entries), 6),
        "avg_slippage_pct": round(sum(_safe_float(e.get("slippage_pct"), 0.0) for e in entries) / max(len(entries), 1), 6),
        "avg_fee_pct": round(sum(_safe_float(e.get("fee_pct"), _safe_float(e.get("fee_usdt"), 0.0)) for e in entries) / max(len(entries), 1), 6),
        "rejected": len([e for e in entries if str(e.get("status") or "").lower() in {"rejected", "failed", "error"}]),
        "partial_fill": len([e for e in entries if str(e.get("fill_status") or e.get("status") or "").lower() in {"partial", "partially_filled"}]),
        "stale": len([e for e in entries if str(e.get("state") or e.get("status") or "").lower() in {"stale", "unknown", "orphan"}]),
        "duplicate_intent": duplicate_count,
    }


def _confidence(metrics: dict, policy: dict) -> float:
    score = 100.0
    if _safe_int(metrics.get("count"), 0) < policy["min_evidence_count"]:
        score -= 25
    if _safe_float(metrics.get("realized_pnl_usdt"), 0.0) < policy["max_negative_pnl_usdt"]:
        score -= 20
    if _safe_float(metrics.get("avg_slippage_pct"), 0.0) > policy["max_slippage_pct"]:
        score -= 15
    if _safe_float(metrics.get("avg_fee_pct"), 0.0) > policy["max_fee_pct"]:
        score -= 15
    score -= min(20, _safe_int(metrics.get("rejected"), 0) * 10)
    score -= min(15, _safe_int(metrics.get("partial_fill"), 0) * 7)
    score -= min(20, _safe_int(metrics.get("duplicate_intent"), 0) * 10)
    return round(max(0.0, min(100.0, score)), 2)


def build_rev166_micro_pilot_evidence_confidence_scorer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    entries = _micro_entries(data)
    metrics = _metrics(entries)
    score = _confidence(metrics, policy)
    checks = [
        _check("evidence_present", "ok" if metrics["count"] >= policy["min_evidence_count"] else "review", "Micro pilot evidence sample count checked.", required=False),
        _check("confidence_threshold", "ok" if score >= policy["min_confidence_score"] else "review", f"Evidence confidence score is {score}.", required=False),
        _check("secret_free_metrics", "ok", "Only aggregate metrics are returned."),
        _check("no_exchange_action", "ok", "Scorer cannot submit or close orders."),
    ]
    return {"engine": "autonomous_micro_pilot_evidence_confidence_scorer", "revision": 166, "status": _final_status(checks), "evidence_confidence": {"score": score, "threshold": policy["min_confidence_score"], "metrics": metrics, "decision": "CONFIDENT" if score >= policy["min_confidence_score"] else "INSUFFICIENT_EVIDENCE"}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "repeat_probe_gate"}


def build_rev167_controlled_repeat_probe_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    confidence = build_rev166_micro_pilot_evidence_confidence_scorer(data, settings, auth_store, username)
    rev165 = build_rev165_micro_pilot_feedback_decision_packet(data, settings, auth_store, username)
    metrics = (confidence.get("evidence_confidence") or {}).get("metrics", {})
    allowed = confidence.get("status") in {"ok", "review"} and rev165.get("status") != "blocked" and policy["owner_repeat_probe_confirmation"] and metrics.get("count", 0) <= policy["max_repeat_probe_count"]
    checks = [
        _check("rev165_not_blocked", "ok" if rev165.get("status") != "blocked" else "blocked", "Previous pilot control packet must not be blocked."),
        _check("owner_repeat_confirmation", "ok" if policy["owner_repeat_probe_confirmation"] else "blocked", "Owner repeat probe confirmation is explicit and required."),
        _check("repeat_count_guard", "ok" if metrics.get("count", 0) <= policy["max_repeat_probe_count"] else "blocked", "Repeat probe count is capped."),
        _check("preview_only", "ok", "Gate authorizes only a preview; no live submit."),
    ]
    return {"engine": "autonomous_controlled_repeat_probe_gate", "revision": 167, "status": _final_status(checks), "repeat_probe_gate": {"decision": "REPEAT_PROBE_PREVIEW_ALLOWED" if allowed else "REPEAT_PROBE_BLOCKED_OR_REVIEW", "max_repeat_probe_count": policy["max_repeat_probe_count"], "owner_confirmation": policy["owner_repeat_probe_confirmation"], "real_submit_close": "OFF", "next_action": "owner_review"}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "scale_freeze_controller"}


def build_rev168_micro_real_scale_freeze_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    confidence = build_rev166_micro_pilot_evidence_confidence_scorer(data, settings, auth_store, username)
    capital = build_rev145_capital_protection_summary(data, settings, auth_store, username)
    score = _safe_float((confidence.get("evidence_confidence") or {}).get("score"), 0.0)
    cap_summary = capital.get("capital_protection_summary") if isinstance(capital.get("capital_protection_summary"), dict) else capital.get("summary_result", {})
    freeze_reasons = []
    if score < policy["min_confidence_score"]:
        freeze_reasons.append("confidence_below_threshold")
    if policy["scale_auto_apply"]:
        freeze_reasons.append("auto_scale_flag_must_remain_off")
    if str(cap_summary.get("trade_action") or cap_summary.get("lot_action") or "hold").lower() in {"stop", "reduce", "halt"}:
        freeze_reasons.append("capital_defense_not_expandable")
    action = "FREEZE_SIZE" if freeze_reasons else "HOLD_SIZE_NO_SCALE"
    checks = [
        _check("auto_scale_disabled", "ok" if not policy["scale_auto_apply"] else "blocked", "Scale auto-apply must remain off."),
        _check("confidence_allows_no_expand", "ok" if score >= policy["min_confidence_score"] else "review", "Low confidence freezes scaling.", required=False),
        _check("no_size_apply", "ok", "Controller returns sizing advice only."),
    ]
    return {"engine": "autonomous_micro_real_scale_freeze_controller", "revision": 168, "status": _final_status(checks), "scale_freeze": {"action": action, "freeze_reasons": freeze_reasons, "auto_scale": "OFF", "recommended_size_action": "hold_or_reduce", "max_scale_change": 0}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "pilot_drift_anomaly_watch"}


def build_rev169_pilot_drift_anomaly_watch(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    metrics = _metrics(_micro_entries(data))
    anomalies = []
    if metrics["duplicate_intent"]:
        anomalies.append("duplicate_intent")
    if metrics["stale"]:
        anomalies.append("stale_or_unknown_order_state")
    if metrics["avg_slippage_pct"] > policy["max_slippage_pct"]:
        anomalies.append("slippage_drift")
    if metrics["avg_fee_pct"] > policy["max_fee_pct"]:
        anomalies.append("fee_drift")
    if metrics["rejected"]:
        anomalies.append("rejected_order")
    checks = [
        _check("no_duplicate_intent", "ok" if not metrics["duplicate_intent"] else "blocked", "Duplicate intent is a hard anomaly."),
        _check("no_stale_order_state", "ok" if not metrics["stale"] else "review", "Stale/unknown order state requires attention.", required=False),
        _check("cost_drift_inside_limit", "ok" if "slippage_drift" not in anomalies and "fee_drift" not in anomalies else "review", "Fee/slippage drift watch.", required=False),
        _check("attention_only", "ok", "Alerts are attention-only; no automatic exchange action."),
    ]
    return {"engine": "autonomous_pilot_drift_anomaly_watch", "revision": 169, "status": _final_status(checks), "anomaly_watch": {"anomalies": anomalies, "attention_level": "critical" if "duplicate_intent" in anomalies else ("review" if anomalies else "clear"), "metrics": metrics, "real_submit_close": "OFF"}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "micro_pilot_stabilization_decision"}


def build_rev170_micro_pilot_stabilization_decision_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    confidence = build_rev166_micro_pilot_evidence_confidence_scorer(data, settings, auth_store, username)
    repeat = build_rev167_controlled_repeat_probe_gate(data, settings, auth_store, username)
    freeze = build_rev168_micro_real_scale_freeze_controller(data, settings, auth_store, username)
    anomaly = build_rev169_pilot_drift_anomaly_watch(data, settings, auth_store, username)
    statuses = [confidence.get("status"), repeat.get("status"), freeze.get("status"), anomaly.get("status")]
    anomalies = (anomaly.get("anomaly_watch") or {}).get("anomalies", [])
    if "blocked" in statuses:
        decision = "NO-GO"
    elif anomalies or "review" in statuses:
        decision = "LIMITED-GO-REVIEW"
    else:
        decision = "LIMITED-GO-PREVIEW-ONLY"
    checks = [
        _check("evidence_confidence", confidence.get("status", "blocked"), "Rev166 evidence confidence."),
        _check("repeat_probe_gate", repeat.get("status", "blocked"), "Rev167 controlled repeat probe gate."),
        _check("scale_freeze", freeze.get("status", "blocked"), "Rev168 size freeze."),
        _check("anomaly_watch", anomaly.get("status", "blocked"), "Rev169 anomaly watch."),
        _check("no_auto_live_action", "ok", "Decision packet cannot place/close orders or scale capital."),
    ]
    return {"engine": "autonomous_micro_pilot_stabilization_decision_v2", "revision": 170, "status": _final_status(checks), "generated_at": now_iso(), "stabilization_decision": {"decision": decision, "real_submit_close": "OFF", "auto_scale": "OFF", "operator_action": "review_summary_only", "next_action": "continue_shadow_or_owner_approved_preview", "critical_anomalies": anomalies}, "summary_result": {"micro_pilot": decision, "evidence": (confidence.get("evidence_confidence") or {}).get("decision"), "scale": (freeze.get("scale_freeze") or {}).get("action"), "attention": (anomaly.get("anomaly_watch") or {}).get("attention_level"), "real_submit_close": "OFF"}, "outputs": {"evidence_confidence": confidence, "repeat_probe_gate": repeat, "scale_freeze": freeze, "anomaly_watch": anomaly}, "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev171_or_manual_launch_review"}


REV_BUILDERS = {166: build_rev166_micro_pilot_evidence_confidence_scorer, 167: build_rev167_controlled_repeat_probe_gate, 168: build_rev168_micro_real_scale_freeze_controller, 169: build_rev169_pilot_drift_anomaly_watch, 170: build_rev170_micro_pilot_stabilization_decision_v2}
REV_KEYS = {166: "autonomous_micro_pilot_evidence_confidence_scorer", 167: "autonomous_controlled_repeat_probe_gate", 168: "autonomous_micro_real_scale_freeze_controller", 169: "autonomous_pilot_drift_anomaly_watch", 170: "autonomous_micro_pilot_stabilization_decision_v2"}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_micro_real_pilot_stabilization_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev166-170 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 170:
        return {"revision": 170, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("evidence_confidence", "repeat_probe_gate", "scale_freeze", "anomaly_watch"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(166, 171)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_micro_pilot_stabilization_decision_v2"]
    return {"engine": "autonomous_micro_real_pilot_stabilization_block", "revision": 170, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("summary_result", {}), "stabilization_decision": final.get("stabilization_decision", {}), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "manual_review_before_any_repeat_probe_or_scaling"}


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
    return {"engine": "autonomous_micro_real_pilot_stabilization_quality_gate", "revision": int(revision), "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks), "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "contains_secret": False, "secret_values_returned": False}
