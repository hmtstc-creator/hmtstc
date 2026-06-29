from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_performance_observability_block_service import (
    build_rev131_trade_performance_metrics_engine,
    build_rev134_risk_adjusted_return_scoring,
    build_rev135_performance_sentinel_v2,
)
from services.autonomous_adaptive_optimization_block_service import (
    build_rev137_symbol_rotation_controller,
    build_rev140_optimization_review_report,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "clear"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency"}:
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
    }


def _performance_context(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    metrics = data.get("autonomous_trade_performance_metrics_engine") if isinstance(data.get("autonomous_trade_performance_metrics_engine"), dict) else build_rev131_trade_performance_metrics_engine(data, settings, auth_store, username)
    scoring = data.get("autonomous_risk_adjusted_return_scoring") if isinstance(data.get("autonomous_risk_adjusted_return_scoring"), dict) else build_rev134_risk_adjusted_return_scoring(data, settings, auth_store, username)
    sentinel = data.get("autonomous_performance_sentinel_v2") if isinstance(data.get("autonomous_performance_sentinel_v2"), dict) else build_rev135_performance_sentinel_v2(data, settings, auth_store, username)
    rotation = data.get("autonomous_symbol_rotation_controller") if isinstance(data.get("autonomous_symbol_rotation_controller"), dict) else build_rev137_symbol_rotation_controller(data, settings, auth_store, username)
    optimization = data.get("autonomous_optimization_review_report") if isinstance(data.get("autonomous_optimization_review_report"), dict) else build_rev140_optimization_review_report(data, settings, auth_store, username)
    return {"metrics": metrics, "scoring": scoring, "sentinel": sentinel, "rotation": rotation, "optimization": optimization}


def _overall(ctx: dict) -> dict:
    snapshot = ctx.get("metrics", {}).get("metric_snapshot", {})
    return snapshot.get("overall", {}) if isinstance(snapshot, dict) and isinstance(snapshot.get("overall"), dict) else {}


def _capital_policy(settings: dict) -> dict:
    policy = _settings(settings, "autonomous_capital_scaling_profit_defense")
    return {
        "base_capital_usdt": _safe_float(policy.get("base_capital_usdt"), 1000.0),
        "current_capital_usdt": _safe_float(policy.get("current_capital_usdt"), _safe_float(policy.get("base_capital_usdt"), 1000.0)),
        "max_daily_loss_pct": _safe_float(policy.get("max_daily_loss_pct"), 1.0),
        "max_position_notional_pct": _safe_float(policy.get("max_position_notional_pct"), 5.0),
        "max_scaling_rate_pct": _safe_float(policy.get("max_scaling_rate_pct"), 5.0),
        "profit_reserve_pct": _safe_float(policy.get("profit_reserve_pct"), 35.0),
        "min_sample_trades_for_scale": _safe_int(policy.get("min_sample_trades_for_scale"), 30),
        "min_profit_factor_for_scale": _safe_float(policy.get("min_profit_factor_for_scale"), 1.25),
        "max_drawdown_pct_for_scale": _safe_float(policy.get("max_drawdown_pct_for_scale"), 3.0),
        "min_notional_usdt": _safe_float(policy.get("min_notional_usdt"), 10.0),
        "hard_max_notional_usdt": _safe_float(policy.get("hard_max_notional_usdt"), 200.0),
        "auto_apply_enabled": False,
    }


def _score_value(ctx: dict) -> float:
    score = ctx.get("scoring", {}).get("risk_adjusted_score")
    if score is None:
        score = ctx.get("sentinel", {}).get("risk_adjusted_score")
    return _safe_float(score, 0.0)


def _drawdown_pct(overall: dict, capital_usdt: float) -> float:
    dd = abs(_safe_float(overall.get("max_drawdown_usdt"), 0.0))
    return round((dd / max(capital_usdt, 1.0)) * 100.0, 4)


def _today_pnl(data: dict, overall: dict) -> float:
    return round(_safe_float(data.get("today_pnl_usdt"), _safe_float(overall.get("net_pnl_usdt"), 0.0)), 6)


def build_rev141_capital_growth_policy(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _performance_context(data, settings, auth_store, username)
    policy = _capital_policy(settings)
    overall = _overall(ctx)
    trades = _safe_int(overall.get("trade_count"), 0)
    win_rate = _safe_float(overall.get("win_rate"), 0.0)
    pf = _safe_float(overall.get("profit_factor"), 0.0)
    dd_pct = _drawdown_pct(overall, policy["current_capital_usdt"])
    score = _score_value(ctx)
    stable = trades >= policy["min_sample_trades_for_scale"] and pf >= policy["min_profit_factor_for_scale"] and win_rate >= 0.52 and dd_pct <= policy["max_drawdown_pct_for_scale"] and score >= 55
    action = "hold_capital"
    scale_pct = 0.0
    reason = "insufficient_stability_or_sample"
    if stable:
        action = "cautious_scale_preview"
        scale_pct = min(policy["max_scaling_rate_pct"], max(1.0, (pf - 1.0) * 3.0))
        reason = "sample_pf_drawdown_and_score_passed"
    if _safe_float(overall.get("expectancy_usdt"), 0.0) < 0 or ctx.get("sentinel", {}).get("action") in {"stop", "cooldown"}:
        action, scale_pct, reason = "do_not_scale", 0.0, "negative_expectancy_or_sentinel_stop"
    checks = [
        _check("sample_size_gate", "ok" if trades >= policy["min_sample_trades_for_scale"] else "review", "Capital growth needs enough trades."),
        _check("profit_factor_gate", "ok" if pf >= policy["min_profit_factor_for_scale"] else "review", "Growth blocked until PF is stable."),
        _check("drawdown_gate", "ok" if dd_pct <= policy["max_drawdown_pct_for_scale"] else "blocked", "Growth disabled when drawdown is high."),
        _check("auto_apply_disabled", "ok", "Capital growth is preview-only and approval-gated."),
    ]
    return {
        "engine": "autonomous_capital_growth_policy", "revision": 141, "status": _final_status(checks),
        "growth_policy": {"action": action, "suggested_scale_pct": round(scale_pct, 4), "reason": reason, "stable_for_growth": stable, "max_scaling_rate_pct": policy["max_scaling_rate_pct"]},
        "evidence": {"trade_count": trades, "win_rate": round(win_rate, 4), "profit_factor": round(pf, 4), "drawdown_pct": dd_pct, "risk_adjusted_score": round(score, 4)},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "profit_reserve_controller",
    }


def build_rev142_profit_reserve_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _performance_context(data, settings, auth_store, username)
    policy = _capital_policy(settings)
    overall = _overall(ctx)
    today_pnl = _today_pnl(data, overall)
    reserve_pct = policy["profit_reserve_pct"] if today_pnl > 0 else 0.0
    reserve_amount = round(max(0.0, today_pnl) * reserve_pct / 100.0, 6)
    deployable_profit = round(max(0.0, today_pnl) - reserve_amount, 6)
    action = "lock_profit_reserve" if reserve_amount > 0 else "no_reserve_needed"
    checks = [
        _check("reserve_policy_present", "ok", "Profit reserve policy prevents full redeployment of daily profit."),
        _check("positive_profit_required", "ok" if today_pnl > 0 else "review", "Reserve activates only when realized/current daily PnL is positive."),
        _check("usdt_reserve_guard", "ok", "Reserve is recommendation-only; no transfer or order is submitted."),
    ]
    return {
        "engine": "autonomous_profit_reserve_controller", "revision": 142, "status": _final_status(checks),
        "reserve_policy": {"action": action, "today_pnl_usdt": today_pnl, "reserve_pct": reserve_pct, "reserve_amount_usdt": reserve_amount, "deployable_profit_usdt": deployable_profit, "principle": "do_not_redeploy_all_profit"},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "drawdown_recovery_mode",
    }


def build_rev143_drawdown_recovery_mode(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _performance_context(data, settings, auth_store, username)
    policy = _capital_policy(settings)
    overall = _overall(ctx)
    dd_pct = _drawdown_pct(overall, policy["current_capital_usdt"])
    loss_streak = _safe_int(overall.get("consecutive_loss"), _safe_int(data.get("loss_streak"), 0))
    expectancy = _safe_float(overall.get("expectancy_usdt"), 0.0)
    if dd_pct >= policy["max_drawdown_pct_for_scale"] or loss_streak >= 3 or expectancy < 0:
        mode = "drawdown_recovery"
        action = "reduce_size_cooldown_and_limit_symbols"
        size_multiplier = 0.35 if dd_pct >= policy["max_drawdown_pct_for_scale"] else 0.5
    else:
        mode = "normal_defense"
        action = "hold_normal_risk"
        size_multiplier = 1.0
    checks = [
        _check("martingale_disabled", "ok", "No loss-recovery size increase is allowed."),
        _check("drawdown_measured", "ok", "Drawdown is converted to capital-relative pressure."),
        _check("safe_recovery_action", "ok", "Recovery path reduces size/frequency instead of chasing losses."),
    ]
    return {
        "engine": "autonomous_drawdown_recovery_mode", "revision": 143, "status": _final_status(checks),
        "recovery_mode": {"mode": mode, "action": action, "drawdown_pct": dd_pct, "loss_streak": loss_streak, "expectancy_usdt": round(expectancy, 6), "size_multiplier": size_multiplier, "martingale_allowed": False},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "dynamic_position_sizing_v2",
    }


def build_rev144_dynamic_position_sizing_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _performance_context(data, settings, auth_store, username)
    policy = _capital_policy(settings)
    overall = _overall(ctx)
    recovery = build_rev143_drawdown_recovery_mode(data, settings, auth_store, username).get("recovery_mode", {})
    score = max(0.0, min(100.0, _score_value(ctx)))
    today_pnl = _today_pnl(data, overall)
    volatility_penalty = min(0.5, max(0.0, _safe_float(data.get("volatility_score"), 0.0) / 200.0))
    liquidity_score = max(0.1, min(1.0, _safe_float(data.get("liquidity_score"), 80.0) / 100.0))
    base_notional = policy["current_capital_usdt"] * policy["max_position_notional_pct"] / 100.0
    score_multiplier = max(0.25, min(1.0, score / 75.0))
    pnl_multiplier = 0.7 if today_pnl < 0 else 1.0
    suggested = base_notional * score_multiplier * liquidity_score * (1.0 - volatility_penalty) * _safe_float(recovery.get("size_multiplier"), 1.0) * pnl_multiplier
    capped = min(policy["hard_max_notional_usdt"], max(policy["min_notional_usdt"], suggested))
    if recovery.get("mode") == "drawdown_recovery":
        sizing_action = "reduce"
    elif score >= 65 and today_pnl >= 0:
        sizing_action = "hold_or_cautious_increase_preview"
    elif score < 45 or today_pnl < 0:
        sizing_action = "reduce"
    else:
        sizing_action = "hold"
    checks = [
        _check("hard_cap_enforced", "ok", "Suggested notional is capped by hard max notional."),
        _check("min_notional_guard", "ok", "Minimum notional guard is explicit."),
        _check("approval_gated", "ok", "Dynamic sizing does not auto-apply."),
    ]
    return {
        "engine": "autonomous_dynamic_position_sizing_v2", "revision": 144, "status": _final_status(checks),
        "position_sizing": {"action": sizing_action, "suggested_notional_usdt": round(capped, 6), "raw_suggestion_usdt": round(suggested, 6), "hard_max_notional_usdt": policy["hard_max_notional_usdt"], "min_notional_usdt": policy["min_notional_usdt"], "risk_adjusted_score": round(score, 4), "today_pnl_usdt": today_pnl, "auto_apply": False},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "capital_protection_summary",
    }


def build_rev145_capital_protection_summary(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    growth = build_rev141_capital_growth_policy(data, settings, auth_store, username)
    reserve = build_rev142_profit_reserve_controller(data, settings, auth_store, username)
    recovery = build_rev143_drawdown_recovery_mode(data, settings, auth_store, username)
    sizing = build_rev144_dynamic_position_sizing_v2(data, settings, auth_store, username)
    growth_action = growth.get("growth_policy", {}).get("action", "hold_capital")
    reserve_action = reserve.get("reserve_policy", {}).get("action", "no_reserve_needed")
    recovery_mode = recovery.get("recovery_mode", {}).get("mode", "normal_defense")
    sizing_action = sizing.get("position_sizing", {}).get("action", "hold")
    if recovery_mode == "drawdown_recovery":
        decision = "dur" if recovery.get("recovery_mode", {}).get("drawdown_pct", 0) >= 3 else "azalt"
    elif growth_action == "cautious_scale_preview" and sizing_action == "hold_or_cautious_increase_preview":
        decision = "artir_onayli_preview"
    elif sizing_action == "reduce":
        decision = "azalt"
    else:
        decision = "tut"
    profit_lock_required = reserve_action == "lock_profit_reserve"
    checks = [
        _check("capital_growth_policy_ready", "ok" if growth.get("revision") == 141 else "blocked", "Growth policy available."),
        _check("profit_reserve_ready", "ok" if reserve.get("revision") == 142 else "blocked", "Profit reserve controller available."),
        _check("drawdown_recovery_ready", "ok" if recovery.get("revision") == 143 else "blocked", "Drawdown recovery available."),
        _check("dynamic_sizing_ready", "ok" if sizing.get("revision") == 144 else "blocked", "Dynamic sizing available."),
        _check("real_submit_off", "ok", "Capital protection summary is read-only/preview-only."),
    ]
    return {
        "engine": "autonomous_capital_protection_summary", "revision": 145, "status": _final_status(checks),
        "capital_protection": {"capital_protected": decision in {"dur", "azalt", "tut", "artir_onayli_preview"}, "trade_today": "stop" if decision == "dur" else "continue_guarded", "lot_decision": decision, "profit_lock_required": profit_lock_required, "growth_action": growth_action, "reserve_action": reserve_action, "recovery_mode": recovery_mode, "suggested_notional_usdt": sizing.get("position_sizing", {}).get("suggested_notional_usdt", 0)},
        "summary_result": {"capital": "protected", "today_trade": "stop" if decision == "dur" else "guarded", "lot": decision, "profit_lock": "required" if profit_lock_required else "not_required"},
        "outputs": {"growth": growth, "reserve": reserve, "recovery": recovery, "sizing": sizing},
        "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev146_live_autonomy_hardening",
    }


REV_BUILDERS = {
    141: build_rev141_capital_growth_policy,
    142: build_rev142_profit_reserve_controller,
    143: build_rev143_drawdown_recovery_mode,
    144: build_rev144_dynamic_position_sizing_v2,
    145: build_rev145_capital_protection_summary,
}

REV_KEYS = {
    141: "autonomous_capital_growth_policy",
    142: "autonomous_profit_reserve_controller",
    143: "autonomous_drawdown_recovery_mode",
    144: "autonomous_dynamic_position_sizing_v2",
    145: "autonomous_capital_protection_summary",
}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_capital_scaling_profit_defense_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev141-145 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 145:
        result = payload.get("summary_result", {})
        return {"revision": 145, **result, "check_totals": payload.get("check_totals", {}), "status": payload.get("status", "review")}
    key_payload = payload.get("growth_policy") or payload.get("reserve_policy") or payload.get("recovery_mode") or payload.get("position_sizing") or {}
    return {"revision": revision, "status": payload.get("status", "review"), "summary": key_payload, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(141, 146)}
    final = outputs["autonomous_capital_protection_summary"]
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    return {
        "engine": "autonomous_capital_scaling_profit_defense_block", "revision": 145, "status": block_status,
        "generated_at": now_iso(), "username": username,
        "outputs": outputs, "summary_result": final.get("summary_result", {}), "capital_protection": final.get("capital_protection", {}),
        "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True,
        "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False,
        "next_allowed_step": "rev146_autonomous_daily_session_lifecycle",
    }


def build_quality_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    preview = payload.get("command_preview", {})
    checks = [
        _check("route_payload_available", "ok" if payload.get("revision") == int(revision) else "blocked", "Revision payload is available."),
        _check("no_secret_exposure", "ok" if payload.get("contains_secret") is False and payload.get("secret_values_returned") is False else "blocked", "Payload does not expose secrets."),
        _check("network_default_off", "ok" if preview.get("network_default_off") is True and preview.get("sends_exchange_request") is False else "blocked", "No exchange network request."),
        _check("real_submit_default_off", "ok" if preview.get("real_submit_default_off") is True and preview.get("places_order") is False else "blocked", "Real order placement is disabled."),
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "Capital decisions are preview-only."),
    ]
    return {
        "engine": "autonomous_capital_scaling_profit_defense_quality_gate", "revision": int(revision),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks),
        "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True,
        "contains_secret": False, "secret_values_returned": False,
    }
