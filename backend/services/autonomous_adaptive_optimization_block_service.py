from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_performance_observability_block_service import (
    build_rev131_trade_performance_metrics_engine,
    build_rev132_strategy_performance_attribution,
    build_rev133_execution_quality_analytics,
    build_rev134_risk_adjusted_return_scoring,
    build_rev135_performance_sentinel_v2,
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
    }


def _perf_context(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    metrics = data.get("autonomous_trade_performance_metrics_engine") if isinstance(data.get("autonomous_trade_performance_metrics_engine"), dict) else build_rev131_trade_performance_metrics_engine(data, settings, auth_store, username)
    attribution = data.get("autonomous_strategy_performance_attribution") if isinstance(data.get("autonomous_strategy_performance_attribution"), dict) else build_rev132_strategy_performance_attribution(data, settings, auth_store, username)
    execution = data.get("autonomous_execution_quality_analytics") if isinstance(data.get("autonomous_execution_quality_analytics"), dict) else build_rev133_execution_quality_analytics(data, settings, auth_store, username)
    scoring = data.get("autonomous_risk_adjusted_return_scoring") if isinstance(data.get("autonomous_risk_adjusted_return_scoring"), dict) else build_rev134_risk_adjusted_return_scoring(data, settings, auth_store, username)
    sentinel = data.get("autonomous_performance_sentinel_v2") if isinstance(data.get("autonomous_performance_sentinel_v2"), dict) else build_rev135_performance_sentinel_v2(data, settings, auth_store, username)
    return {"metrics": metrics, "attribution": attribution, "execution": execution, "scoring": scoring, "sentinel": sentinel}


def _overall(ctx: dict) -> dict:
    return ctx.get("metrics", {}).get("metric_snapshot", {}).get("overall", {}) if isinstance(ctx.get("metrics", {}).get("metric_snapshot"), dict) else {}


def _whitelist(settings: dict) -> list[str]:
    source = _settings(settings, "autonomous_whitelist_daily_hard_stop").get("symbol_whitelist")
    if not source:
        source = _settings(settings, "autonomous_live_stabilization").get("symbol_whitelist")
    symbols = [str(s or "").upper().strip() for s in _as_list(source)]
    return [s for s in symbols if s]


def _strategy_rows(ctx: dict) -> list[dict]:
    rows = ctx.get("attribution", {}).get("attribution_table", [])
    return [row for row in _as_list(rows) if isinstance(row, dict)]


def _strategy_score(row: dict) -> float:
    pf = min(_safe_float(row.get("profit_factor"), 0.0), 3.0)
    expectancy = _safe_float(row.get("expectancy_usdt"), 0.0)
    win = _safe_float(row.get("win_rate"), 0.0)
    dd = _safe_float(row.get("max_drawdown_usdt"), 0.0)
    return round((pf * 24.0) + (win * 30.0) + (expectancy * 25.0) - (dd * 4.0), 4)


def build_rev136_adaptive_strategy_tuning_runtime(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _perf_context(data, settings, auth_store, username)
    rows = _strategy_rows(ctx)
    suggestions = []
    for row in rows:
        action = "hold"
        reason = "insufficient_or_neutral_evidence"
        if _safe_int(row.get("trade_count"), 0) >= 3 and row.get("attribution_signal") == "cautious_promotion":
            action, reason = "tighten_quality_threshold_slightly", "positive_expectancy_with_sample"
        if row.get("attribution_signal") == "demotion" or _safe_float(row.get("expectancy_usdt"), 0.0) < 0:
            action, reason = "reduce_frequency_or_cooldown", "negative_expectancy_or_demotion_signal"
        suggestions.append({
            "symbol": row.get("symbol", "UNKNOWN"),
            "strategy": row.get("strategy", "unknown"),
            "regime": row.get("regime", "unknown"),
            "score": _strategy_score(row),
            "suggested_action": action,
            "reason": reason,
            "auto_apply": False,
        })
    checks = [
        _check("performance_memory_available", "ok" if ctx.get("metrics", {}).get("revision") == 131 else "blocked", "Tuning consumes performance metrics."),
        _check("strategy_evidence_available", "ok" if rows else "review", "Strategy suggestions require attribution evidence."),
        _check("auto_apply_disabled", "ok", "Suggestions are preview-only and never auto-applied."),
    ]
    return {
        "engine": "autonomous_adaptive_strategy_tuning_runtime", "revision": 136, "status": _final_status(checks),
        "readiness": "ADAPTIVE_TUNING_PREVIEW_READY" if _final_status(checks) == "ok" else "ADAPTIVE_TUNING_REVIEW",
        "tuning_suggestions": suggestions[:20], "auto_apply_default_off": True,
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "symbol_rotation_controller",
    }


def build_rev137_symbol_rotation_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _perf_context(data, settings, auth_store, username)
    whitelist = _whitelist(settings)
    rows = _strategy_rows(ctx)
    symbol_bucket: dict[str, list[dict]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "UNKNOWN").upper()
        if whitelist and symbol not in whitelist:
            continue
        symbol_bucket.setdefault(symbol, []).append(row)
    priority, cooldown, neutral = [], [], []
    for symbol, items in symbol_bucket.items():
        avg_score = sum(_strategy_score(i) for i in items) / max(1, len(items))
        expectancy = sum(_safe_float(i.get("expectancy_usdt"), 0.0) for i in items) / max(1, len(items))
        demotions = len([i for i in items if i.get("attribution_signal") == "demotion"])
        record = {"symbol": symbol, "score": round(avg_score, 4), "avg_expectancy_usdt": round(expectancy, 6), "sample_count": sum(_safe_int(i.get("trade_count"), 0) for i in items)}
        if demotions or expectancy < 0 or avg_score < 40:
            cooldown.append({**record, "rotation_action": "cooldown"})
        elif avg_score >= 60 and expectancy >= 0:
            priority.append({**record, "rotation_action": "priority"})
        else:
            neutral.append({**record, "rotation_action": "watch"})
    checks = [
        _check("whitelist_respected", "ok", "Rotation never expands outside configured whitelist."),
        _check("symbol_evidence_available", "ok" if symbol_bucket else "review", "Symbol rotation uses observed symbol performance."),
        _check("cooldown_path_available", "ok", "Weak symbols can be cooled down without order submit."),
    ]
    return {
        "engine": "autonomous_symbol_rotation_controller", "revision": 137, "status": _final_status(checks),
        "readiness": "SYMBOL_ROTATION_READY" if _final_status(checks) == "ok" else "SYMBOL_ROTATION_REVIEW",
        "priority_symbols": sorted(priority, key=lambda x: x["score"], reverse=True),
        "cooldown_symbols": sorted(cooldown, key=lambda x: x["score"]),
        "watch_symbols": sorted(neutral, key=lambda x: x["score"], reverse=True),
        "whitelist_only": True,
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "market_regime_adaptation_v2",
    }


def _regime_from_data(data: dict) -> str:
    for key in ("market_regime", "current_market_regime", "regime"):
        value = str(data.get(key) or "").lower().strip()
        if value:
            return value
    vol = _safe_float(data.get("volatility") or data.get("market_volatility"), 0.0)
    liq = _safe_float(data.get("liquidity_score"), 1.0)
    if liq and liq < 0.35:
        return "low_liquidity"
    if vol > 0.08:
        return "high_volatility"
    if vol < 0.015:
        return "range"
    return "trend"


def build_rev138_market_regime_adaptation_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _perf_context(data, settings, auth_store, username)
    regime = _regime_from_data(data)
    rows = [r for r in _strategy_rows(ctx) if str(r.get("regime", "unknown")).lower() in {regime, "unknown"}]
    tradeable = regime not in {"low_liquidity", "emergency", "halt"}
    allowed = []
    blocked = []
    for row in rows:
        item = {"symbol": row.get("symbol"), "strategy": row.get("strategy"), "regime": row.get("regime"), "score": _strategy_score(row)}
        if not tradeable or row.get("attribution_signal") == "demotion" or _strategy_score(row) < 35:
            blocked.append({**item, "reason": "wrong_or_weak_regime"})
        else:
            allowed.append({**item, "reason": "regime_aligned"})
    if not tradeable:
        loop_recommendation = "halt_opportunity_loop"
    elif allowed:
        loop_recommendation = "allow_regime_aligned_opportunities"
    else:
        loop_recommendation = "hold_no_quality_regime_match"
    checks = [
        _check("regime_detected", "ok" if regime else "review", "Market regime is classified."),
        _check("non_tradeable_regime_blocks_loop", "ok" if tradeable else "review", "Low-liquidity/halt regimes stop opportunities."),
        _check("wrong_regime_strategy_block", "ok", "Strategy execution can be blocked by regime mismatch."),
    ]
    return {
        "engine": "autonomous_market_regime_adaptation_v2", "revision": 138, "status": _final_status(checks),
        "readiness": "REGIME_ADAPTATION_READY" if _final_status(checks) == "ok" else "REGIME_ADAPTATION_REVIEW",
        "market_regime": regime, "market_tradeable": tradeable,
        "allowed_strategy_candidates": sorted(allowed, key=lambda x: x["score"], reverse=True)[:10],
        "blocked_strategy_candidates": blocked[:10], "opportunity_loop_recommendation": loop_recommendation,
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "anti_overtrade_governor",
    }


def build_rev139_anti_overtrade_governor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _perf_context(data, settings, auth_store, username)
    policy = _settings(settings, "autonomous_adaptive_optimization")
    daily_cap = max(1, _safe_int(policy.get("daily_trade_cap"), 40))
    symbol_cap = max(1, _safe_int(policy.get("symbol_trade_cap"), 10))
    strategy_cap = max(1, _safe_int(policy.get("strategy_trade_cap"), 12))
    min_quality = _safe_float(policy.get("min_opportunity_quality_score"), 55.0)
    overall = _overall(ctx)
    trade_count = _safe_int(data.get("today_trade_count") or overall.get("trade_count"), 0)
    fee_impact = abs(_safe_float(overall.get("fee_impact_usdt"), 0.0))
    expectancy = _safe_float(overall.get("expectancy_usdt"), 0.0)
    perf_state = ctx.get("scoring", {}).get("risk_adjusted_score", {}).get("performance_state", "weak")
    quality_score = _safe_float(ctx.get("scoring", {}).get("risk_adjusted_score", {}).get("score"), 0.0)
    blocked_reasons = []
    if trade_count >= daily_cap:
        blocked_reasons.append("daily_trade_cap_reached")
    if expectancy <= 0 and fee_impact > 0:
        blocked_reasons.append("fee_drag_with_non_positive_expectancy")
    if perf_state in {"weak", "stop"}:
        blocked_reasons.append("performance_state_not_supportive")
    if quality_score < min_quality:
        blocked_reasons.append("opportunity_quality_below_threshold")
    decision = "allow_quality_only" if not blocked_reasons else ("cooldown" if "daily_trade_cap_reached" in blocked_reasons else "reduce_or_hold")
    checks = [
        _check("daily_cap_configured", "ok", "Daily trade cap is enforced in preview."),
        _check("fee_drag_guard", "review" if "fee_drag_with_non_positive_expectancy" in blocked_reasons else "ok", "Fee/slippage overtrading is detected."),
        _check("quality_threshold_guard", "review" if "opportunity_quality_below_threshold" in blocked_reasons else "ok", "Low quality opportunities are blocked."),
    ]
    return {
        "engine": "autonomous_anti_overtrade_governor", "revision": 139, "status": _final_status(checks),
        "readiness": "ANTI_OVERTRADE_READY" if _final_status(checks) == "ok" else "ANTI_OVERTRADE_REVIEW",
        "governor_decision": decision,
        "blocked_reasons": blocked_reasons,
        "caps": {"daily_trade_cap": daily_cap, "symbol_trade_cap": symbol_cap, "strategy_trade_cap": strategy_cap, "min_opportunity_quality_score": min_quality},
        "current": {"today_trade_count": trade_count, "expectancy_usdt": expectancy, "fee_impact_usdt": fee_impact, "performance_state": perf_state, "quality_score": quality_score},
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "optimization_review_report",
    }


def build_rev140_optimization_review_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    tuning = data.get("autonomous_adaptive_strategy_tuning_runtime") if isinstance(data.get("autonomous_adaptive_strategy_tuning_runtime"), dict) else build_rev136_adaptive_strategy_tuning_runtime(data, settings, auth_store, username)
    rotation = data.get("autonomous_symbol_rotation_controller") if isinstance(data.get("autonomous_symbol_rotation_controller"), dict) else build_rev137_symbol_rotation_controller(data, settings, auth_store, username)
    regime = data.get("autonomous_market_regime_adaptation_v2") if isinstance(data.get("autonomous_market_regime_adaptation_v2"), dict) else build_rev138_market_regime_adaptation_v2(data, settings, auth_store, username)
    overtrade = data.get("autonomous_anti_overtrade_governor") if isinstance(data.get("autonomous_anti_overtrade_governor"), dict) else build_rev139_anti_overtrade_governor(data, settings, auth_store, username)
    suggestions = tuning.get("tuning_suggestions", []) if isinstance(tuning.get("tuning_suggestions"), list) else []
    risky = [s for s in suggestions if s.get("suggested_action") in {"reduce_frequency_or_cooldown"}]
    candidate = [s for s in suggestions if s.get("suggested_action") == "tighten_quality_threshold_slightly"]
    action = "hold"
    if overtrade.get("governor_decision") in {"cooldown", "reduce_or_hold"} or risky:
        action = "reduce"
    if regime.get("market_tradeable") is False:
        action = "stop"
    elif candidate and not risky and overtrade.get("governor_decision") == "allow_quality_only":
        action = "tune"
    report = {
        "summary_action": action,
        "recommended_changes": candidate[:10],
        "risky_changes": risky[:10],
        "not_auto_apply": True,
        "priority_symbols": rotation.get("priority_symbols", [])[:5],
        "cooldown_symbols": rotation.get("cooldown_symbols", [])[:5],
        "regime_recommendation": regime.get("opportunity_loop_recommendation"),
        "overtrade_decision": overtrade.get("governor_decision"),
    }
    checks = [
        _check("preview_only_report", "ok", "Optimization report is suggestion-only."),
        _check("auto_apply_blocked", "ok", "No parameter is auto-applied."),
        _check("summary_action_minimal", "ok" if action in {"hold", "tune", "reduce", "stop"} else "blocked", "Summary only exposes hold/tune/reduce/stop."),
    ]
    return {
        "engine": "autonomous_optimization_review_report", "revision": 140, "status": _final_status(checks),
        "readiness": "OPTIMIZATION_REVIEW_READY" if _final_status(checks) == "ok" else "OPTIMIZATION_REVIEW_REVIEW",
        "optimization_report": report,
        "summary_result": {"optimization": action, "action": action},
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev141_capital_scaling_profit_defense_block",
    }


_BUILDERS = {
    136: build_rev136_adaptive_strategy_tuning_runtime,
    137: build_rev137_symbol_rotation_controller,
    138: build_rev138_market_regime_adaptation_v2,
    139: build_rev139_anti_overtrade_governor,
    140: build_rev140_optimization_review_report,
}

_NAMES = {
    136: "autonomous_adaptive_strategy_tuning_runtime",
    137: "autonomous_symbol_rotation_controller",
    138: "autonomous_market_regime_adaptation_v2",
    139: "autonomous_anti_overtrade_governor",
    140: "autonomous_optimization_review_report",
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = _BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_adaptive_optimization_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev136-140 revision.", "contains_secret": False}
    return builder(data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 136:
        return {"revision": 136, "status": payload.get("status"), "suggestion_count": len(payload.get("tuning_suggestions", [])), "auto_apply": False, "contains_secret": False}
    if int(revision) == 137:
        return {"revision": 137, "status": payload.get("status"), "priority_symbols": payload.get("priority_symbols", [])[:3], "cooldown_symbols": payload.get("cooldown_symbols", [])[:3], "whitelist_only": True, "contains_secret": False}
    if int(revision) == 138:
        return {"revision": 138, "status": payload.get("status"), "market_regime": payload.get("market_regime"), "market_tradeable": payload.get("market_tradeable"), "recommendation": payload.get("opportunity_loop_recommendation"), "contains_secret": False}
    if int(revision) == 139:
        return {"revision": 139, "status": payload.get("status"), "governor_decision": payload.get("governor_decision"), "blocked_reasons": payload.get("blocked_reasons", []), "contains_secret": False}
    if int(revision) == 140:
        return {"revision": 140, "status": payload.get("status"), **payload.get("summary_result", {}), "contains_secret": False}
    return {"revision": revision, "status": payload.get("status"), "contains_secret": False}


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs: dict[str, dict] = {}
    working = deepcopy(data)
    for revision in range(136, 141):
        key = _NAMES[revision]
        payload = _BUILDERS[revision](working, settings, auth_store, username)
        outputs[key] = payload
        working[key] = payload
    final = outputs["autonomous_optimization_review_report"]
    return {
        "engine": "autonomous_adaptive_optimization_block",
        "revision": 140,
        "status": final.get("status", "review"),
        "readiness": final.get("readiness", "OPTIMIZATION_REVIEW_REVIEW"),
        "outputs": outputs,
        "summary_result": final.get("summary_result", {}),
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "network_default_off": True,
        "auto_apply_default_off": True,
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev141_capital_scaling_profit_defense_block",
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    checks = [
        _check("payload_available", "ok" if payload.get("revision") == int(revision) else "blocked", "Revision payload is callable."),
        _check("no_exchange_network", "ok" if payload.get("command_preview", {}).get("sends_exchange_request") is False else "blocked", "No real exchange network call is allowed."),
        _check("no_real_submit", "ok" if payload.get("command_preview", {}).get("places_order") is False else "blocked", "Direct real submit remains OFF."),
        _check("no_real_close", "ok" if payload.get("command_preview", {}).get("submits_close_order") is False else "blocked", "Direct close remains OFF."),
        _check("auto_apply_off", "ok" if payload.get("command_preview", {}).get("auto_apply_default_off") is True else "blocked", "Adaptive optimization remains preview-only."),
        _check("secret_free", "ok" if payload.get("contains_secret") is False and payload.get("secret_values_returned") is False else "blocked", "No secret leaks in response."),
    ]
    return {
        "status": _final_status(checks),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL",
        "revision": int(revision),
        "engine": "autonomous_adaptive_optimization_quality_gate",
        "checks": checks,
        "check_totals": _totals(checks),
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_apply_default_off": True,
        "contains_secret": False,
    }
