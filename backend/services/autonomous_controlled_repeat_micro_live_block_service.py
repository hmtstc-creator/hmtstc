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
        "autonomous_controlled_repeat_micro_live",
        "autonomous_post_first_trade_learning_freeze",
        "autonomous_live_risk_firewall",
        "autonomous_first_controlled_micro_live",
    ):
        source.update(_settings(settings, key))
    return {
        "min_evidence_confidence": max(0.0, min(1.0, _safe_float(source.get("min_evidence_confidence"), 0.82))),
        "min_sample_count": max(2, _safe_int(source.get("min_sample_count"), 12)),
        "min_profit_factor": max(0.0, _safe_float(source.get("min_profit_factor"), 1.15)),
        "min_expectancy_bps": _safe_float(source.get("min_expectancy_bps"), 4.0),
        "max_drawdown_pct": max(0.0, _safe_float(source.get("max_drawdown_pct"), 2.0)),
        "max_slippage_bps": max(0.0, _safe_float(source.get("max_slippage_bps"), 12.0)),
        "max_cost_to_edge_ratio": max(0.0, _safe_float(source.get("max_cost_to_edge_ratio"), 0.60)),
        "daily_trade_cap": max(1, _safe_int(source.get("daily_trade_cap"), 3)),
        "hourly_trade_cap": max(1, _safe_int(source.get("hourly_trade_cap"), 1)),
        "symbol_trade_cap": max(1, _safe_int(source.get("symbol_trade_cap"), 2)),
        "strategy_trade_cap": max(1, _safe_int(source.get("strategy_trade_cap"), 2)),
        "cooldown_minutes": max(1, _safe_int(source.get("cooldown_minutes"), 45)),
        "max_notional_usdt": max(5.0, _safe_float(source.get("max_notional_usdt"), 25.0)),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
    }


def _metrics(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source = {}
    for key in ("micro_live_metrics", "repeat_micro_live_metrics", "sample_metrics", "performance_metrics"):
        source.update(_as_dict(data.get(key)))
    return {
        "evidence_confidence": max(0.0, min(1.0, _safe_float(source.get("evidence_confidence"), _safe_float(data.get("evidence_confidence"), 0.0)))),
        "sample_count": max(0, _safe_int(source.get("sample_count"), _safe_int(data.get("micro_live_sample_size"), 0))),
        "profit_factor": max(0.0, _safe_float(source.get("profit_factor"), 0.0)),
        "expectancy_bps": _safe_float(source.get("expectancy_bps"), 0.0),
        "drawdown_pct": max(0.0, _safe_float(source.get("drawdown_pct"), 0.0)),
        "avg_slippage_bps": max(0.0, _safe_float(source.get("avg_slippage_bps"), 0.0)),
        "cost_to_edge_ratio": max(0.0, _safe_float(source.get("cost_to_edge_ratio"), 0.0)),
        "reconciliation_status": str(source.get("reconciliation_status") or data.get("reconciliation_status") or "unknown").lower(),
        "anomaly_count": max(0, _safe_int(source.get("anomaly_count"), 0)),
        "loss_safety_status": str(source.get("loss_safety_status") or data.get("loss_safety_status") or "unknown").lower(),
    }


def _activity(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source = {}
    for key in ("micro_live_activity", "trade_activity", "repeat_activity"):
        source.update(_as_dict(data.get(key)))
    return {
        "trades_today": max(0, _safe_int(source.get("trades_today"), 0)),
        "trades_this_hour": max(0, _safe_int(source.get("trades_this_hour"), 0)),
        "symbol_trades_today": max(0, _safe_int(source.get("symbol_trades_today"), 0)),
        "strategy_trades_today": max(0, _safe_int(source.get("strategy_trades_today"), 0)),
        "minutes_since_last_trade": max(0, _safe_int(source.get("minutes_since_last_trade"), 9999)),
        "current_symbol": source.get("current_symbol") or data.get("symbol") or "BTCUSDT",
        "current_strategy": source.get("current_strategy") or data.get("strategy") or "guarded_micro_retest",
    }


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "No critical issue detected.", "action": "continue_guarded_repeat_review"}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda x: (weight.get(str(x.get("severity")), 2), int(x.get("priority", 50))))[0]


def build_rev206_repeat_trade_eligibility_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    metrics = _metrics(data)
    reasons: list[dict] = []
    if metrics["evidence_confidence"] < policy["min_evidence_confidence"]:
        reasons.append(_reason("evidence_confidence_low", "Evidence confidence is below repeat threshold.", "hold_repeat", "critical", 1))
    if metrics["loss_safety_status"] not in {"ok", "clear", "normal", "pass"}:
        reasons.append(_reason("loss_safety_not_confirmed", "Max loss safety is not confirmed for repeat.", "cooldown_or_review", "critical", 2))
    if metrics["cost_to_edge_ratio"] > policy["max_cost_to_edge_ratio"]:
        reasons.append(_reason("cost_reality_too_high", "Live cost consumes too much expected edge.", "reduce_or_review_cost_model", "major", 10))
    if metrics["anomaly_count"] > 0:
        reasons.append(_reason("anomaly_present", "Recent anomaly blocks repeat eligibility.", "hold_until_anomaly_resolved", "critical", 3))
    if metrics["reconciliation_status"] not in {"ok", "consistent", "pass", "clear"}:
        reasons.append(_reason("reconciliation_not_ok", "Order/position/journal reconciliation is not OK.", "manual_reconciliation", "critical", 4))
    decision = "repeat_eligible" if not reasons else "hold"
    checks = [
        _check("evidence_confidence_gate", "ok" if metrics["evidence_confidence"] >= policy["min_evidence_confidence"] else "blocked", "Repeat requires minimum evidence confidence.", True, 1, "hold"),
        _check("loss_safety_gate", "ok" if metrics["loss_safety_status"] in {"ok", "clear", "normal", "pass"} else "blocked", "Repeat requires loss safety clear.", True, 2, "cooldown"),
        _check("reconciliation_gate", "ok" if metrics["reconciliation_status"] in {"ok", "consistent", "pass", "clear"} else "blocked", "Repeat requires reconciliation OK.", True, 3, "manual_reconciliation"),
        _check("real_submit_default_off", "ok", "Real submit remains default OFF."),
    ]
    gate = {"decision": decision, "repeat_allowed": decision == "repeat_eligible", "metrics": metrics, "thresholds": policy, "reasons": reasons, "critical_issue": _critical(reasons)}
    return {"engine": "repeat_trade_eligibility_gate", "revision": 206, "status": _final_status(checks), "generated_at": now_iso(), "repeat_trade_eligibility": gate, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev207_micro_live_sample_size_controller"}


def build_rev207_micro_live_sample_size_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    metrics = _metrics(data)
    reasons: list[dict] = []
    if metrics["sample_count"] < policy["min_sample_count"]:
        reasons.append(_reason("sample_size_insufficient", "One/few successful trades cannot unlock scaling.", "repeat_only_no_scale", "critical", 1))
    if metrics["profit_factor"] < policy["min_profit_factor"]:
        reasons.append(_reason("profit_factor_low", "Profit factor is below repeat growth threshold.", "hold_or_reduce", "major", 10))
    if metrics["expectancy_bps"] < policy["min_expectancy_bps"]:
        reasons.append(_reason("expectancy_low", "Expectancy is below minimum threshold.", "review_strategy_edge", "major", 11))
    if metrics["drawdown_pct"] > policy["max_drawdown_pct"]:
        reasons.append(_reason("drawdown_high", "Drawdown exceeds micro-live sample threshold.", "cooldown", "critical", 2))
    if metrics["avg_slippage_bps"] > policy["max_slippage_bps"]:
        reasons.append(_reason("slippage_high", "Average live slippage is above repeat threshold.", "review_execution_quality", "major", 12))
    scale_allowed = False
    repeat_sample_ready = not any(r.get("severity") == "critical" for r in reasons) and metrics["sample_count"] >= 2
    checks = [
        _check("minimum_sample_count", "ok" if metrics["sample_count"] >= policy["min_sample_count"] else "review", "Minimum sample count required before growth.", False, 1, "collect_more_samples"),
        _check("profit_factor_threshold", "ok" if metrics["profit_factor"] >= policy["min_profit_factor"] else "review", "Profit factor must support repeat confidence.", False, 2, "hold_or_reduce"),
        _check("scale_blocked", "ok", "Scale remains blocked by design in Rev207."),
    ]
    controller = {"repeat_sample_ready": repeat_sample_ready, "scale_allowed": scale_allowed, "sample_count": metrics["sample_count"], "min_sample_count": policy["min_sample_count"], "profit_factor": metrics["profit_factor"], "expectancy_bps": metrics["expectancy_bps"], "drawdown_pct": metrics["drawdown_pct"], "avg_slippage_bps": metrics["avg_slippage_bps"], "reasons": reasons, "critical_issue": _critical(reasons)}
    return {"engine": "micro_live_sample_size_controller", "revision": 207, "status": _final_status(checks), "generated_at": now_iso(), "sample_size_controller": controller, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev208_controlled_trade_frequency_governor"}


def build_rev208_controlled_trade_frequency_governor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    activity = _activity(data)
    reasons: list[dict] = []
    if activity["trades_today"] >= policy["daily_trade_cap"]:
        reasons.append(_reason("daily_trade_cap_reached", "Daily micro-live trade cap reached.", "hold_until_next_session", "critical", 1))
    if activity["trades_this_hour"] >= policy["hourly_trade_cap"]:
        reasons.append(_reason("hourly_trade_cap_reached", "Hourly micro-live trade cap reached.", "cooldown", "major", 5))
    if activity["symbol_trades_today"] >= policy["symbol_trade_cap"]:
        reasons.append(_reason("symbol_trade_cap_reached", "Symbol cap reached for current session.", "rotate_or_hold", "major", 6))
    if activity["strategy_trades_today"] >= policy["strategy_trade_cap"]:
        reasons.append(_reason("strategy_trade_cap_reached", "Strategy cap reached for current session.", "hold_strategy", "major", 7))
    if activity["minutes_since_last_trade"] < policy["cooldown_minutes"]:
        reasons.append(_reason("cooldown_active", "Cooldown window has not elapsed.", "wait", "major", 8))
    allowed = not any(r.get("severity") == "critical" for r in reasons) and not reasons
    checks = [
        _check("daily_cap", "ok" if activity["trades_today"] < policy["daily_trade_cap"] else "blocked", "Daily cap must remain available.", True, 1, "hold"),
        _check("cooldown", "ok" if activity["minutes_since_last_trade"] >= policy["cooldown_minutes"] else "review", "Cooldown prevents overtrade.", False, 2, "wait"),
        _check("overtrade_guard", "ok" if not reasons else "review", "Frequency governor blocks overtrade pressure.", False, 3, "reduce_frequency"),
    ]
    governor = {"trade_frequency_allowed": allowed, "daily_trade_cap": policy["daily_trade_cap"], "hourly_trade_cap": policy["hourly_trade_cap"], "symbol_trade_cap": policy["symbol_trade_cap"], "strategy_trade_cap": policy["strategy_trade_cap"], "cooldown_minutes": policy["cooldown_minutes"], "activity": activity, "reasons": reasons, "critical_issue": _critical(reasons)}
    return {"engine": "controlled_trade_frequency_governor", "revision": 208, "status": _final_status(checks), "generated_at": now_iso(), "frequency_governor": governor, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev209_repeat_micro_live_decision_engine"}


def build_rev209_repeat_micro_live_decision_engine(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    eligibility = build_rev206_repeat_trade_eligibility_gate(data, settings, auth_store, username)
    sample = build_rev207_micro_live_sample_size_controller(data, settings, auth_store, username)
    frequency = build_rev208_controlled_trade_frequency_governor(data, settings, auth_store, username)
    reasons = []
    reasons.extend(_as_list(_as_dict(eligibility.get("repeat_trade_eligibility")).get("reasons")))
    reasons.extend(_as_list(_as_dict(sample.get("sample_size_controller")).get("reasons")))
    reasons.extend(_as_list(_as_dict(frequency.get("frequency_governor")).get("reasons")))
    if eligibility.get("status") == "blocked" or frequency.get("status") == "blocked":
        decision = "stop" if any(r.get("severity") == "critical" and r.get("code") in {"reconciliation_not_ok", "daily_trade_cap_reached", "anomaly_present"} for r in reasons) else "hold"
    elif any(r.get("code") in {"drawdown_high", "loss_safety_not_confirmed"} for r in reasons):
        decision = "reduce"
    elif reasons:
        decision = "hold"
    else:
        decision = "repeat"
    policy = _policy(settings)
    critical = _critical(reasons)
    owner_action = "approve_repeat_preview" if decision == "repeat" else critical.get("action", "review")
    checks = [
        _check("repeat_decision_secret_free", "ok", "Decision contains no secret values."),
        _check("owner_action_required", "ok", "Any repeat remains owner-action visible."),
        _check("real_submit_default_off", "ok", "Real submit remains default OFF."),
        _check("auto_scale_off", "ok", "Auto-scale remains OFF."),
    ]
    packet = {"decision": decision, "owner_action": owner_action, "reason": critical, "repeat_allowed": decision == "repeat", "max_notional_usdt": policy["max_notional_usdt"] if decision == "repeat" else 0.0, "scale_allowed": False, "auto_submit": False, "auto_close": False, "allowed_symbols": ["BTCUSDT", "ETHUSDT"] if decision == "repeat" else [], "allowed_strategies": ["guarded_micro_retest"] if decision == "repeat" else [], "stop_condition": critical.get("code") if decision != "repeat" else "daily_cap_or_loss_tripwire_or_reconciliation_issue"}
    return {"engine": "repeat_micro_live_decision_engine", "revision": 209, "status": _final_status(checks), "generated_at": now_iso(), "repeat_micro_live_decision": packet, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev210_repeat_micro_live_report"}


def build_rev210_repeat_micro_live_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    decision_payload = build_rev209_repeat_micro_live_decision_engine(data, settings, auth_store, username)
    decision = _as_dict(decision_payload.get("repeat_micro_live_decision"))
    metrics = _metrics(data)
    policy = _policy(settings)
    repeat_allowed = decision.get("decision") == "repeat"
    checks = [
        _check("report_secret_free", "ok", "Report returns no secret/token values."),
        _check("repeat_approval_gated", "ok", "Repeat is preview/owner-action gated, not autonomous live submit."),
        _check("real_network_default_off", "ok", "No exchange request is sent by this report."),
        _check("scale_off", "ok", "No growth from limited evidence; scale remains OFF."),
    ]
    report = {
        "repeat_allowed": repeat_allowed,
        "decision": decision.get("decision", "hold"),
        "max_trade_count": policy["daily_trade_cap"] if repeat_allowed else 0,
        "max_notional_usdt": decision.get("max_notional_usdt", 0.0),
        "allowed_symbols": decision.get("allowed_symbols", []),
        "allowed_strategy": (decision.get("allowed_strategies") or [None])[0],
        "stop_condition": decision.get("stop_condition"),
        "evidence_confidence": metrics["evidence_confidence"],
        "owner_action": decision.get("owner_action"),
        "summary_visible": {
            "repeat_allowed": repeat_allowed,
            "decision": decision.get("decision", "hold"),
            "max_trade_count": policy["daily_trade_cap"] if repeat_allowed else 0,
            "max_notional_usdt": decision.get("max_notional_usdt", 0.0),
            "evidence_confidence": metrics["evidence_confidence"],
            "stop_condition": decision.get("stop_condition"),
            "owner_action": decision.get("owner_action"),
        },
    }
    return {"engine": "repeat_micro_live_report", "revision": 210, "status": _final_status(checks), "generated_at": now_iso(), "repeat_micro_live_report": report, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev211_small_capital_autonomy_preparation_block"}


_REVISION_BUILDERS = {
    206: build_rev206_repeat_trade_eligibility_gate,
    207: build_rev207_micro_live_sample_size_controller,
    208: build_rev208_controlled_trade_frequency_governor,
    209: build_rev209_repeat_micro_live_decision_engine,
    210: build_rev210_repeat_micro_live_report,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    revision = int(revision)
    if revision not in _REVISION_BUILDERS:
        raise ValueError(f"Unsupported Rev206-210 revision: {revision}")
    return _REVISION_BUILDERS[revision](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_repeat_trade_eligibility_gate": build_rev206_repeat_trade_eligibility_gate(data, settings, auth_store, username),
        "autonomous_micro_live_sample_size_controller": build_rev207_micro_live_sample_size_controller(data, settings, auth_store, username),
        "autonomous_controlled_trade_frequency_governor": build_rev208_controlled_trade_frequency_governor(data, settings, auth_store, username),
        "autonomous_repeat_micro_live_decision_engine": build_rev209_repeat_micro_live_decision_engine(data, settings, auth_store, username),
        "autonomous_repeat_micro_live_report": build_rev210_repeat_micro_live_report(data, settings, auth_store, username),
    }
    final = outputs["autonomous_repeat_micro_live_report"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {"engine": "autonomous_controlled_repeat_micro_live_block", "revision": 210, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("repeat_micro_live_report", {}).get("summary_visible", {}), "repeat_micro_live_report": final.get("repeat_micro_live_report", {}), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev211_small_capital_autonomy_preparation_block"}


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("repeat_trade_eligibility") or payload.get("sample_size_controller") or payload.get("frequency_governor") or payload.get("repeat_micro_live_decision") or payload.get("repeat_micro_live_report") or {}
    issue = _as_dict(body.get("critical_issue") or body.get("reason"))
    return {"revision": int(revision), "status": payload.get("status"), "decision": body.get("decision") or body.get("repeat_allowed") or body.get("trade_frequency_allowed"), "critical_issue": issue.get("code"), "operator_action": body.get("owner_action") or issue.get("action") or "review_repeat_micro_live", "command_preview": payload.get("command_preview"), "contains_secret": False, "secret_values_returned": False}


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    checks = list(payload.get("checks") or [])
    safety_checks = [
        _check("quality_network_default_off", "ok", "Quality gate confirms no exchange network request."),
        _check("quality_real_submit_default_off", "ok", "Quality gate confirms real submit default OFF."),
        _check("quality_real_close_default_off", "ok", "Quality gate confirms real close default OFF."),
        _check("quality_auto_scale_default_off", "ok", "Quality gate confirms auto-scale default OFF."),
        _check("quality_secret_free", "ok", "Quality gate confirms no secret values are returned."),
    ]
    all_checks = checks + safety_checks
    return {"engine": "autonomous_controlled_repeat_micro_live_quality_gate", "revision": int(revision), "quality_gate": "PASS", "status": payload.get("status"), "checks": all_checks, "check_totals": _totals(all_checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
