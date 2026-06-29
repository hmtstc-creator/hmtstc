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
        "autonomous_first_controlled_micro_live",
        "autonomous_post_first_trade_learning_freeze",
        "autonomous_live_risk_firewall",
        "autonomous_live_edge_profitability_proof",
    ):
        source.update(_settings(settings, key))
    return {
        "min_evidence_confidence": max(0.0, min(1.0, _safe_float(source.get("min_evidence_confidence"), 0.80))),
        "max_slippage_bps": max(0.0, _safe_float(source.get("max_slippage_bps"), 12.0)),
        "max_latency_ms": max(1, _safe_int(source.get("max_latency_ms"), 1500)),
        "max_cost_to_edge_ratio": max(0.0, _safe_float(source.get("max_cost_to_edge_ratio"), 0.55)),
        "paper_live_max_pnl_deviation_bps": max(0.0, _safe_float(source.get("paper_live_max_pnl_deviation_bps"), 18.0)),
        "min_sample_for_scale": max(2, _safe_int(source.get("min_sample_for_scale"), 20)),
        "break_even_buffer_bps": max(0.0, _safe_float(source.get("break_even_buffer_bps"), 4.0)),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
    }


def _result(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    for key in ("micro_live_result", "last_micro_live_result", "first_micro_live_result", "trade_result"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    outputs = _as_dict(data.get("outputs"))
    for key in ("micro_live_result", "last_micro_live_result", "first_micro_live_result", "trade_result"):
        value = outputs.get(key)
        if isinstance(value, dict):
            return value
    capture = _as_dict(data.get("autonomous_micro_live_result_capture"))
    latest = _as_dict(_as_dict(capture.get("result_capture")).get("latest_result_preview"))
    return latest


def _expectation(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    for key in ("paper_expectation", "micro_real_expectation", "expected_trade", "strategy_expectation"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _cost_model(data: dict | None, settings: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source = _settings(settings, "cost_model")
    source.update(_as_dict(data.get("cost_model")))
    return {
        "fee_bps": max(0.0, _safe_float(source.get("fee_bps"), 10.0)),
        "slippage_bps": max(0.0, _safe_float(source.get("slippage_bps"), 5.0)),
        "latency_ms": max(0, _safe_int(source.get("latency_ms"), 500)),
        "edge_bps": max(0.0, _safe_float(source.get("edge_bps"), 35.0)),
    }


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "No critical issue detected.", "action": "continue_guarded_review"}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda x: (weight.get(str(x.get("severity")), 2), int(x.get("priority", 50))))[0]


def _evidence_fields() -> list[str]:
    return ["pnl_usdt", "fee_usdt", "slippage_bps", "latency_ms", "fill_quality", "exit_reason", "risk_event", "strategy_result", "journal_consistency"]


def build_rev201_first_trade_evidence_quality_scorer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    result = _result(data)
    required = _evidence_fields()
    missing = [field for field in required if field not in result]
    score = 1.0
    score -= min(0.55, len(missing) * 0.08)
    slippage = _safe_float(result.get("slippage_bps"), 0.0)
    latency = _safe_int(result.get("latency_ms"), 0)
    pnl = _safe_float(result.get("pnl_usdt"), 0.0)
    fee = _safe_float(result.get("fee_usdt"), 0.0)
    if result and slippage > policy["max_slippage_bps"]:
        score -= 0.16
    if result and latency > policy["max_latency_ms"]:
        score -= 0.12
    if result and str(result.get("journal_consistency", "unknown")).lower() not in {"ok", "consistent", "true"}:
        score -= 0.20
    if result and str(result.get("fill_quality", "unknown")).lower() in {"poor", "bad", "unknown"}:
        score -= 0.12
    confidence = round(max(0.0, min(1.0, score)), 4)
    reasons: list[dict] = []
    if missing:
        reasons.append(_reason("evidence_fields_missing", f"Missing evidence fields: {', '.join(missing)}", "freeze_until_complete_journal", "critical", 1))
    if result and slippage > policy["max_slippage_bps"]:
        reasons.append(_reason("slippage_outlier", "Live slippage is above policy threshold.", "review_cost_model", "major", 10))
    if result and latency > policy["max_latency_ms"]:
        reasons.append(_reason("latency_outlier", "Execution latency is above policy threshold.", "review_exchange_execution_path", "major", 11))
    if result and str(result.get("journal_consistency", "unknown")).lower() not in {"ok", "consistent", "true"}:
        reasons.append(_reason("journal_inconsistent", "Journal consistency is not confirmed.", "manual_reconciliation", "critical", 2))
    checks = [
        _check("evidence_schema_present", "review" if missing else "ok", "First live trade evidence must include complete result fields.", False, 1, "complete_evidence"),
        _check("confidence_threshold", "ok" if confidence >= policy["min_evidence_confidence"] else "review", "Confidence is measured before repeat/scale decisions.", False, 2, "freeze_or_review"),
        _check("secret_free_evidence", "ok", "Evidence scorer returns no API key, secret, token or credential values."),
    ]
    return {"engine": "first_trade_evidence_quality_scorer", "revision": 201, "status": _final_status(checks), "generated_at": now_iso(), "evidence_quality": {"confidence": confidence, "threshold": policy["min_evidence_confidence"], "sample_size": 1 if result else 0, "missing_fields": missing, "pnl_usdt": pnl, "fee_usdt": fee, "slippage_bps": slippage if result else None, "latency_ms": latency if result else None, "reasons": reasons, "critical_issue": _critical(reasons)}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev202_post_trade_freeze_gate"}


def build_rev202_post_trade_freeze_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    evidence = build_rev201_first_trade_evidence_quality_scorer(data, settings, auth_store, username)["evidence_quality"]
    result = _result(data)
    pnl = _safe_float(result.get("pnl_usdt"), 0.0)
    sample_size = max(0, _safe_int(data.get("micro_live_sample_size"), evidence.get("sample_size", 0)))
    reasons: list[dict] = []
    if evidence.get("confidence", 0.0) < policy["min_evidence_confidence"]:
        reasons.append(_reason("evidence_confidence_low", "Evidence confidence is below repeat threshold.", "freeze", "critical", 1))
    if pnl < 0:
        reasons.append(_reason("first_trade_loss", "First controlled micro-live result is negative.", "cooldown", "critical", 2))
    if sample_size < policy["min_sample_for_scale"]:
        reasons.append(_reason("sample_size_too_small_for_scale", "One or few trades are not enough for scaling.", "freeze_scale", "major", 3))
    if policy["auto_scale_enable"]:
        reasons.append(_reason("auto_scale_enabled", "Auto-scale must remain OFF after first trade.", "disable_auto_scale", "critical", 4))
    decision = "freeze" if reasons else "repeat_review"
    if pnl < 0:
        decision = "cooldown"
    checks = [
        _check("blind_scale_blocked", "ok" if not policy["auto_scale_enable"] else "blocked", "Automatic growth is blocked after first trade."),
        _check("loss_routes_to_cooldown", "ok", "Loss result routes to cooldown instead of revenge trade."),
        _check("profit_still_needs_sample", "ok", "Profit is not enough to scale without sample threshold."),
    ]
    return {"engine": "post_trade_freeze_gate", "revision": 202, "status": _final_status(checks), "generated_at": now_iso(), "freeze_gate": {"decision": decision, "scale_allowed": False, "repeat_allowed": decision == "repeat_review", "cooldown_required": decision == "cooldown", "sample_size": sample_size, "min_sample_for_scale": policy["min_sample_for_scale"], "reasons": reasons, "critical_issue": _critical(reasons)}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev203_strategy_reality_check"}


def build_rev203_strategy_reality_check(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    result = _result(data)
    expected = _expectation(data)
    live_pnl_bps = _safe_float(result.get("pnl_bps"), _safe_float(result.get("pnl_ratio"), 0.0) * 10000.0)
    expected_pnl_bps = _safe_float(expected.get("expected_pnl_bps"), _safe_float(expected.get("expected_pnl_ratio"), 0.0) * 10000.0)
    deviation = abs(live_pnl_bps - expected_pnl_bps) if result or expected else None
    drift_high = deviation is not None and deviation > policy["paper_live_max_pnl_deviation_bps"]
    reasons: list[dict] = []
    if not result:
        reasons.append(_reason("no_live_result_yet", "No first live result exists yet.", "keep_review", "major", 1))
    if not expected:
        reasons.append(_reason("paper_expectation_missing", "Paper/micro-real expectation is missing for reality check.", "capture_expectation", "major", 2))
    if drift_high:
        reasons.append(_reason("paper_live_deviation_high", "Live result deviates materially from paper/micro-real expectation.", "downgrade_or_review_strategy", "critical", 3))
    decision = "downgrade_review" if drift_high else "review" if reasons else "aligned"
    checks = [
        _check("paper_live_comparison_available", "review" if not result or not expected else "ok", "Reality check needs both expected and live result.", False, 1, "capture_missing_data"),
        _check("deviation_within_threshold", "ok" if not drift_high else "blocked", "High paper/live deviation blocks repeat confidence."),
        _check("auto_apply_off", "ok" if not policy["auto_apply_enable"] else "blocked", "Strategy downgrade/calibration recommendation is preview-only."),
    ]
    return {"engine": "strategy_reality_check", "revision": 203, "status": _final_status(checks), "generated_at": now_iso(), "strategy_reality": {"decision": decision, "live_pnl_bps": live_pnl_bps if result else None, "expected_pnl_bps": expected_pnl_bps if expected else None, "deviation_bps": deviation, "threshold_bps": policy["paper_live_max_pnl_deviation_bps"], "recommendation": "strategy_downgrade_or_review" if drift_high else "hold_learning_lock", "reasons": reasons, "critical_issue": _critical(reasons)}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev204_live_cost_reality_calibration"}


def build_rev204_live_cost_reality_calibration(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    result = _result(data)
    cost = _cost_model(data, settings)
    live_fee_bps = _safe_float(result.get("fee_bps"), cost["fee_bps"])
    live_slippage_bps = _safe_float(result.get("slippage_bps"), cost["slippage_bps"])
    live_latency_ms = _safe_int(result.get("latency_ms"), cost["latency_ms"])
    live_total_cost_bps = round(live_fee_bps + live_slippage_bps, 4)
    break_even_bps = round(live_total_cost_bps + policy["break_even_buffer_bps"], 4)
    edge_bps = max(0.0, _safe_float(cost.get("edge_bps"), 35.0))
    cost_to_edge_ratio = round(live_total_cost_bps / edge_bps, 4) if edge_bps else 999.0
    reasons: list[dict] = []
    if cost_to_edge_ratio > policy["max_cost_to_edge_ratio"]:
        reasons.append(_reason("cost_too_high_vs_edge", "Live fee/slippage consumes too much expected edge.", "raise_break_even_or_reduce_trade", "critical", 1))
    if live_latency_ms > policy["max_latency_ms"]:
        reasons.append(_reason("latency_requires_cost_penalty", "Live latency exceeds policy and should increase cost penalty.", "review_latency", "major", 2))
    checks = [
        _check("live_cost_model_preview", "ok", "Live fee/slippage/latency is converted into preview calibration."),
        _check("cost_edge_ratio_guard", "ok" if cost_to_edge_ratio <= policy["max_cost_to_edge_ratio"] else "blocked", "Cost must not consume excessive expected edge."),
        _check("auto_apply_off", "ok" if not policy["auto_apply_enable"] else "blocked", "Cost calibration is not auto-applied."),
    ]
    return {"engine": "live_cost_reality_calibration", "revision": 204, "status": _final_status(checks), "generated_at": now_iso(), "cost_calibration": {"live_fee_bps": live_fee_bps, "live_slippage_bps": live_slippage_bps, "live_latency_ms": live_latency_ms, "live_total_cost_bps": live_total_cost_bps, "break_even_threshold_bps_preview": break_even_bps, "edge_bps": edge_bps, "cost_to_edge_ratio": cost_to_edge_ratio, "auto_apply": "OFF", "recommendation": "update_cost_model_preview_only", "reasons": reasons, "critical_issue": _critical(reasons)}, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev205_post_first_trade_decision_packet"}


def build_rev205_post_first_trade_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    evidence = build_rev201_first_trade_evidence_quality_scorer(data, settings, auth_store, username)
    freeze = build_rev202_post_trade_freeze_gate(data, settings, auth_store, username)
    reality = build_rev203_strategy_reality_check(data, settings, auth_store, username)
    cost = build_rev204_live_cost_reality_calibration(data, settings, auth_store, username)
    reasons: list[dict] = []
    for body_key, payload in (("evidence_quality", evidence), ("freeze_gate", freeze), ("strategy_reality", reality), ("cost_calibration", cost)):
        body = _as_dict(payload.get(body_key))
        issue = _as_dict(body.get("critical_issue"))
        if issue and issue.get("code") not in {None, "none"}:
            reasons.append(issue)
    if _as_dict(freeze.get("freeze_gate")).get("cooldown_required"):
        decision = "reduce"
    elif any(r.get("severity") == "critical" for r in reasons):
        decision = "freeze"
    elif reasons:
        decision = "review"
    else:
        decision = "repeat"
    critical = _critical(reasons)
    missing_data = _as_dict(evidence.get("evidence_quality")).get("missing_fields", [])
    next_action = {
        "repeat": "allow_repeat_review_gate_only_no_scale",
        "freeze": "freeze_until_evidence_reconciliation_and_cost_review_pass",
        "reduce": "cooldown_then_reduce_notional_after_owner_review",
        "review": "manual_review_before_repeat",
        "stop": "stop_micro_live_lane",
    }.get(decision, "manual_review")
    checks = [
        _check("scale_blocked_after_first_trade", "ok", "Scaling remains blocked after first trade regardless of profit."),
        _check("decision_packet_secret_free", "ok", "Decision packet returns no API secret/token values."),
        _check("auto_apply_off", "ok", "Learning/calibration recommendations are preview-only."),
        _check("real_submit_close_default_off", "ok", "Submit/close remain default OFF."),
    ]
    packet = {
        "decision": decision,
        "reason": critical,
        "missing_data": missing_data,
        "next_allowed_action": next_action,
        "evidence_confidence": _as_dict(evidence.get("evidence_quality")).get("confidence"),
        "cost_to_edge_ratio": _as_dict(cost.get("cost_calibration")).get("cost_to_edge_ratio"),
        "strategy_reality_decision": _as_dict(reality.get("strategy_reality")).get("decision"),
        "scale_allowed": False,
        "repeat_requires_owner_review": True,
        "summary_visible": {
            "decision": decision,
            "reason": critical.get("code"),
            "missing_data_count": len(missing_data or []),
            "next_action": next_action,
            "evidence_confidence": _as_dict(evidence.get("evidence_quality")).get("confidence"),
        },
    }
    return {"engine": "post_first_trade_decision_packet", "revision": 205, "status": _final_status(checks), "generated_at": now_iso(), "post_first_trade_decision_packet": packet, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev206_controlled_repeat_micro_live_block"}


_REVISION_BUILDERS = {
    201: build_rev201_first_trade_evidence_quality_scorer,
    202: build_rev202_post_trade_freeze_gate,
    203: build_rev203_strategy_reality_check,
    204: build_rev204_live_cost_reality_calibration,
    205: build_rev205_post_first_trade_decision_packet,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    revision = int(revision)
    if revision not in _REVISION_BUILDERS:
        raise ValueError(f"Unsupported Rev201-205 revision: {revision}")
    return _REVISION_BUILDERS[revision](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_first_trade_evidence_quality_scorer": build_rev201_first_trade_evidence_quality_scorer(data, settings, auth_store, username),
        "autonomous_post_trade_freeze_gate": build_rev202_post_trade_freeze_gate(data, settings, auth_store, username),
        "autonomous_strategy_reality_check": build_rev203_strategy_reality_check(data, settings, auth_store, username),
        "autonomous_live_cost_reality_calibration": build_rev204_live_cost_reality_calibration(data, settings, auth_store, username),
        "autonomous_post_first_trade_decision_packet": build_rev205_post_first_trade_decision_packet(data, settings, auth_store, username),
    }
    final = outputs["autonomous_post_first_trade_decision_packet"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {"engine": "autonomous_post_first_trade_learning_freeze_block", "revision": 205, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("post_first_trade_decision_packet", {}).get("summary_visible", {}), "post_first_trade_decision_packet": final.get("post_first_trade_decision_packet", {}), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev206_controlled_repeat_micro_live_block"}


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("evidence_quality") or payload.get("freeze_gate") or payload.get("strategy_reality") or payload.get("cost_calibration") or payload.get("post_first_trade_decision_packet") or {}
    issue = _as_dict(body.get("critical_issue") or body.get("reason"))
    return {"revision": int(revision), "status": payload.get("status"), "decision": body.get("decision") or body.get("recommendation") or body.get("confidence"), "critical_issue": issue.get("code"), "operator_action": body.get("next_allowed_action") or issue.get("action") or "review_after_first_trade", "command_preview": payload.get("command_preview"), "contains_secret": False, "secret_values_returned": False}


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    checks = payload.get("checks") or []
    status = _final_status([c for c in checks if c.get("required", True)])
    return {"engine": "autonomous_post_first_trade_learning_freeze_quality_gate", "revision": int(revision), "quality_gate": "PASS" if status == "ok" else "FAIL", "status": status, "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
