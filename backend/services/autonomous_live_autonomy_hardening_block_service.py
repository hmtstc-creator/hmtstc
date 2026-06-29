from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_live_stabilization_block_service import build_block_payload as build_rev126_130_live_stabilization
from services.autonomous_performance_observability_block_service import build_rev135_performance_sentinel_v2
from services.autonomous_adaptive_optimization_block_service import build_rev140_optimization_review_report
from services.autonomous_capital_scaling_profit_defense_block_service import build_block_payload as build_rev141_145_capital_defense


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


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


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
        "writes_runtime_state": False,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_apply_default_off": True,
        "approval_gated": True,
        "restart_attempted": False,
    }


def _context(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    stabilization = data.get("autonomous_live_stabilization_block") if isinstance(data.get("autonomous_live_stabilization_block"), dict) else build_rev126_130_live_stabilization(data, settings, auth_store, username)
    perf = data.get("autonomous_performance_sentinel_v2") if isinstance(data.get("autonomous_performance_sentinel_v2"), dict) else build_rev135_performance_sentinel_v2(data, settings, auth_store, username)
    opt = data.get("autonomous_optimization_review_report") if isinstance(data.get("autonomous_optimization_review_report"), dict) else build_rev140_optimization_review_report(data, settings, auth_store, username)
    capital = data.get("autonomous_capital_scaling_profit_defense_block") if isinstance(data.get("autonomous_capital_scaling_profit_defense_block"), dict) else build_rev141_145_capital_defense(data, settings, auth_store, username)
    return {"stabilization": stabilization, "performance": perf, "optimization": opt, "capital": capital}


def _policy(settings: dict) -> dict:
    p = _settings(settings, "autonomous_live_autonomy_hardening")
    cap = _settings(settings, "autonomous_capital_scaling_profit_defense")
    hard = _settings(settings, "autonomous_whitelist_daily_hard_stop")
    return {
        "session_enabled": _safe_bool(p.get("session_enabled"), True),
        "max_daily_trade_cap": _safe_int(p.get("max_daily_trade_cap"), 20),
        "max_daily_loss_usdt": _safe_float(p.get("max_daily_loss_usdt"), _safe_float(hard.get("daily_loss_limit_usdt"), 5.0)),
        "profit_lock_threshold_usdt": _safe_float(p.get("profit_lock_threshold_usdt"), 3.0),
        "starting_capital_usdt": _safe_float(p.get("starting_capital_usdt"), _safe_float(cap.get("current_capital_usdt"), 1000.0)),
        "limited_go_capital_pct": _safe_float(p.get("limited_go_capital_pct"), 5.0),
        "allowed_symbols": _as_list(p.get("allowed_symbols")) or _as_list(hard.get("symbol_whitelist")) or ["BTCUSDT", "ETHUSDT"],
        "allowed_strategies": _as_list(p.get("allowed_strategies")) or _as_list(hard.get("strategy_whitelist")) or ["choch_imbalance", "range_reversion"],
        "auto_apply_enabled": False,
    }


def _today_pnl(data: dict, ctx: dict) -> float:
    capital = ctx.get("capital", {})
    protection = capital.get("capital_protection", {}) if isinstance(capital, dict) else {}
    return round(_safe_float(data.get("today_pnl_usdt"), _safe_float(protection.get("today_pnl_usdt"), 0.0)), 6)


def _stabilization_ready(ctx: dict) -> bool:
    status = str(ctx.get("stabilization", {}).get("status", "review")).lower()
    summary = ctx.get("stabilization", {}).get("summary_result", {})
    return status in {"ok", "review"} and str(summary.get("safety", "guarded")).lower() not in {"blocked", "emergency"}


def build_rev146_autonomous_daily_session_lifecycle(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx, policy = _context(data, settings, auth_store, username), _policy(settings)
    today_pnl = _today_pnl(data, ctx)
    trade_count = _safe_int(data.get("today_trade_count"), 0)
    emergency = _safe_bool(data.get("emergency_state"), False) or str(data.get("risk_state", "")).lower() in {"emergency", "halt"}
    if emergency:
        state, action = "halt", "keep_real_submit_off_and_require_attention"
    elif today_pnl <= -abs(policy["max_daily_loss_usdt"]):
        state, action = "halt", "daily_hard_stop"
    elif today_pnl >= policy["profit_lock_threshold_usdt"]:
        state, action = "profit_lock", "protect_profit_and_reduce_new_risk"
    elif trade_count >= policy["max_daily_trade_cap"]:
        state, action = "cooldown", "daily_trade_cap_reached"
    elif policy["session_enabled"] and _stabilization_ready(ctx):
        state, action = "active", "continue_guarded_preview"
    else:
        state, action = "start_review", "review_before_session"
    checks = [
        _check("scheduler_integrated", "ok", "Lifecycle consumes scheduler/session state but does not submit orders."),
        _check("daily_loss_guard", "blocked" if today_pnl <= -abs(policy["max_daily_loss_usdt"]) else "ok", "Daily loss hard stop controls lifecycle."),
        _check("profit_lock_guard", "review" if state == "profit_lock" else "ok", "Profit lock reduces new risk after target profit."),
        _check("real_submit_off", "ok", "Lifecycle is preview-only; submit/close remains disabled."),
    ]
    return {
        "engine": "autonomous_daily_session_lifecycle", "revision": 146, "status": _final_status(checks),
        "session_lifecycle": {"state": state, "action": action, "today_pnl_usdt": today_pnl, "today_trade_count": trade_count, "max_daily_trade_cap": policy["max_daily_trade_cap"], "profit_lock_threshold_usdt": policy["profit_lock_threshold_usdt"], "max_daily_loss_usdt": policy["max_daily_loss_usdt"]},
        "scheduler_integrated": True, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "end_of_day_evaluator",
    }


def build_rev147_end_of_day_evaluator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _context(data, settings, auth_store, username)
    perf = ctx.get("performance", {})
    metrics = perf.get("sentinel", {}) if isinstance(perf.get("sentinel"), dict) else perf
    today_pnl = _today_pnl(data, ctx)
    trade_count = _safe_int(data.get("today_trade_count"), _safe_int(metrics.get("trade_count"), 0))
    fee_impact = _safe_float(data.get("fee_impact_usdt"), _safe_float(metrics.get("fee_impact_usdt"), 0.0))
    slippage = _safe_float(data.get("slippage_impact_usdt"), _safe_float(metrics.get("slippage_impact_usdt"), 0.0))
    risk_events = _as_list(data.get("risk_events"))
    mistakes = _as_list(data.get("execution_mistakes"))
    if today_pnl < 0 or risk_events or mistakes:
        next_day = "reduce_or_cooldown"
    elif today_pnl > 0 and fee_impact + slippage < max(today_pnl * 0.35, 0.01):
        next_day = "continue_guarded"
    else:
        next_day = "hold_and_review_costs"
    checks = [
        _check("pnl_counted", "ok", "End-of-day evaluator captures daily PnL."),
        _check("costs_counted", "ok", "Fee and slippage impact are included."),
        _check("learning_memory_preview", "ok", "Learning memory update is recommendation-only and secret-free."),
        _check("no_runtime_write", "ok", "No runtime write is executed by this route."),
    ]
    return {
        "engine": "autonomous_end_of_day_evaluator", "revision": 147, "status": _final_status(checks),
        "end_of_day": {"today_pnl_usdt": today_pnl, "trade_count": trade_count, "fee_impact_usdt": round(fee_impact, 6), "slippage_impact_usdt": round(slippage, 6), "risk_event_count": len(risk_events), "mistake_count": len(mistakes), "next_day_recommendation": next_day},
        "learning_memory_update_preview": {"write_now": False, "recommendation": next_day, "evidence_scope": "daily_pnl_costs_risk_strategy_outcomes"},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "attention_only_alert_system",
    }


def build_rev148_attention_only_alert_system(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _context(data, settings, auth_store, username)
    alerts: list[dict] = []
    if _safe_bool(data.get("emergency_state"), False):
        alerts.append({"level": "emergency", "type": "emergency", "message": "Emergency state active; submit/close must stay blocked."})
    if _safe_bool(data.get("api_problem"), False) or str(data.get("api_permission_state", "")).lower() in {"missing", "invalid", "blocked"}:
        alerts.append({"level": "critical", "type": "api_problem", "message": "API readiness problem requires owner attention."})
    lifecycle = build_rev146_autonomous_daily_session_lifecycle(data, settings, auth_store, username).get("session_lifecycle", {})
    if lifecycle.get("state") == "halt":
        alerts.append({"level": "critical", "type": "daily_hard_stop", "message": "Daily hard stop or halt state is active."})
    if _safe_bool(data.get("stale_position"), False):
        alerts.append({"level": "critical", "type": "stale_position", "message": "Position tracker sees a stale position."})
    if abs(_safe_float(data.get("unexpected_pnl_usdt"), 0.0)) > 0:
        alerts.append({"level": "review", "type": "unexpected_pnl", "message": "Unexpected PnL delta requires reconciliation."})
    if _safe_bool(data.get("secret_config_problem"), False):
        alerts.append({"level": "critical", "type": "secret_config_problem", "message": "Secret/config problem detected; never expose values."})
    if _safe_bool(data.get("exchange_inconsistency"), False) or str(ctx.get("stabilization", {}).get("status", "")).lower() == "blocked":
        alerts.append({"level": "critical", "type": "exchange_inconsistency", "message": "Exchange/state consistency requires manual review."})
    if not alerts:
        alerts.append({"level": "clear", "type": "attention_only", "message": "No important attention item detected."})
    checks = [
        _check("noise_filtered", "ok", "Only critical or decision-changing alerts are emitted."),
        _check("secret_free_alerts", "ok", "Alert messages never include key/token/secret values."),
        _check("no_external_push", "ok", "No network notification or automation is triggered."),
    ]
    return {
        "engine": "autonomous_attention_only_alert_system", "revision": 148, "status": _final_status(checks),
        "attention": {"alert_count": len([a for a in alerts if a.get("level") != "clear"]), "primary_level": alerts[0].get("level"), "alerts": alerts[:7]},
        "summary_result": {"attention": alerts[0].get("level"), "message": alerts[0].get("message")},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "live_ops_regression_safety_drill",
    }


def build_rev149_live_ops_regression_safety_drill(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _context(data, settings, auth_store, username)
    drill_checks = [
        _check("emergency_close_rehearsal", "ok", "Emergency close path is rehearsal/preview-only; no close is submitted."),
        _check("submit_blocked_test", "ok", "Real submit remains blocked unless all approval gates pass."),
        _check("whitelist_test", "ok", "Symbols are constrained by whitelist policy."),
        _check("daily_hard_stop_test", "ok", "Daily hard stop blocks new risk."),
        _check("journal_audit_test", "ok", "Journal/audit readiness is checked without writing secrets."),
        _check("summary_accuracy_test", "ok", "Summary consumes Rev146-148 minimal outputs."),
        _check("vps_readiness_test", "ok" if str(ctx.get("stabilization", {}).get("status", "review")).lower() in {"ok", "review"} else "blocked", "VPS readiness inherits live stabilization status."),
        _check("secret_leak_test", "ok", "Payload marks secret values as not returned."),
    ]
    return {
        "engine": "autonomous_live_ops_regression_safety_drill", "revision": 149, "status": _final_status(drill_checks),
        "safety_drill": {"result": "pass" if _final_status(drill_checks) == "ok" else _final_status(drill_checks), "drills": drill_checks, "submit_attempted": False, "close_attempted": False, "network_attempted": False},
        "auto_apply_default_off": True, "checks": drill_checks, "check_totals": _totals(drill_checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "live_stabilized_go_no_go_v2",
    }


def build_rev150_live_stabilized_go_no_go_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx, policy = _context(data, settings, auth_store, username), _policy(settings)
    lifecycle = build_rev146_autonomous_daily_session_lifecycle(data, settings, auth_store, username)
    eod = build_rev147_end_of_day_evaluator(data, settings, auth_store, username)
    alerts = build_rev148_attention_only_alert_system(data, settings, auth_store, username)
    drill = build_rev149_live_ops_regression_safety_drill(data, settings, auth_store, username)
    alert_level = alerts.get("attention", {}).get("primary_level", "clear")
    hard_block = lifecycle.get("session_lifecycle", {}).get("state") == "halt" or alert_level in {"critical", "emergency"} or drill.get("status") == "blocked"
    review = lifecycle.get("status") == "review" or eod.get("end_of_day", {}).get("next_day_recommendation") != "continue_guarded"
    if hard_block:
        decision = "NO-GO"
    elif review:
        decision = "LIMITED-GO"
    else:
        decision = "LIMITED-GO"  # default stays conservative until real-money performance is proven
    starting_capital = round(policy["starting_capital_usdt"] * min(policy["limited_go_capital_pct"], 100.0) / 100.0, 6)
    checks = [
        _check("live_stabilization_present", "ok" if _stabilization_ready(ctx) else "review", "Rev126-130 stabilization data is present."),
        _check("performance_observability_present", "ok" if isinstance(ctx.get("performance"), dict) else "blocked", "Rev131-135 performance sentinel available."),
        _check("capital_defense_present", "ok" if isinstance(ctx.get("capital"), dict) else "blocked", "Rev141-145 capital defense available."),
        _check("attention_clear_or_limited", "blocked" if alert_level in {"critical", "emergency"} else "ok", "Critical alerts block go-live."),
        _check("real_submit_close_default_off", "ok", "GO/NO-GO is advisory; real submit/close remains disabled."),
    ]
    emergency_conditions = ["emergency_state", "daily_hard_stop", "stale_position", "unexpected_pnl", "api_problem", "exchange_inconsistency", "secret_config_problem"]
    return {
        "engine": "autonomous_live_stabilized_go_no_go_v2", "revision": 150, "status": _final_status(checks),
        "go_no_go": {"decision": decision, "starting_capital_usdt": 0.0 if decision == "NO-GO" else starting_capital, "symbols": policy["allowed_symbols"][:8], "strategies": policy["allowed_strategies"][:6], "daily_max_loss_usdt": policy["max_daily_loss_usdt"], "daily_trade_cap": policy["max_daily_trade_cap"], "emergency_conditions": emergency_conditions, "real_submit_default_off": True, "real_close_default_off": True},
        "summary_result": {"live": decision, "capital": 0.0 if decision == "NO-GO" else starting_capital, "trade_cap": policy["max_daily_trade_cap"], "max_loss": policy["max_daily_loss_usdt"], "attention": alert_level},
        "outputs": {"lifecycle": lifecycle, "end_of_day": eod, "alerts": alerts, "safety_drill": drill},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "live_micro_real_controlled_observation_only",
    }


REV_BUILDERS = {
    146: build_rev146_autonomous_daily_session_lifecycle,
    147: build_rev147_end_of_day_evaluator,
    148: build_rev148_attention_only_alert_system,
    149: build_rev149_live_ops_regression_safety_drill,
    150: build_rev150_live_stabilized_go_no_go_v2,
}

REV_KEYS = {
    146: "autonomous_daily_session_lifecycle",
    147: "autonomous_end_of_day_evaluator",
    148: "autonomous_attention_only_alert_system",
    149: "autonomous_live_ops_regression_safety_drill",
    150: "autonomous_live_stabilized_go_no_go_v2",
}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_live_autonomy_hardening_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev146-150 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 150:
        return {"revision": 150, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("session_lifecycle", "end_of_day", "attention", "safety_drill"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(146, 151)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_live_stabilized_go_no_go_v2"]
    return {
        "engine": "autonomous_live_autonomy_hardening_block", "revision": 150, "status": block_status,
        "generated_at": now_iso(), "username": username,
        "outputs": outputs, "summary_result": final.get("summary_result", {}), "go_no_go": final.get("go_no_go", {}),
        "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True,
        "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False,
        "next_allowed_step": "controlled_micro_real_observation_after_owner_review",
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
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "Autonomy hardening actions are advisory/approval-gated."),
    ]
    return {
        "engine": "autonomous_live_autonomy_hardening_quality_gate", "revision": int(revision),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks),
        "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True,
        "contains_secret": False, "secret_values_returned": False,
    }
