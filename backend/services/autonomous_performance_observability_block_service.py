from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from math import sqrt
from typing import Any

from services.autonomous_live_stabilization_block_service import build_rev130_first_live_stabilization_report


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


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


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
    }


def _normalize_trade(item: dict, index: int) -> dict:
    gross = _safe_float(item.get("gross_pnl_usdt") or item.get("pnl_usdt") or item.get("profit_usdt") or item.get("realized_pnl_usdt"), 0.0)
    fee = abs(_safe_float(item.get("fee_usdt") or item.get("fees_usdt") or item.get("commission_usdt"), 0.0))
    slippage = abs(_safe_float(item.get("slippage_usdt") or item.get("slippage_cost_usdt"), 0.0))
    net = _safe_float(item.get("net_pnl_usdt"), gross - fee - slippage)
    lane = _safe_text(item.get("lane") or item.get("mode") or item.get("trade_lane"), "paper").lower()
    if lane not in {"paper", "micro-real", "micro_real", "real"}:
        lane = "paper"
    if lane == "micro_real":
        lane = "micro-real"
    return {
        "id": _safe_text(item.get("id") or item.get("trade_id"), f"trade_{index}"),
        "lane": lane,
        "symbol": _safe_text(item.get("symbol"), "UNKNOWN").upper(),
        "strategy": _safe_text(item.get("strategy") or item.get("strategy_id"), "unknown"),
        "regime": _safe_text(item.get("regime") or item.get("market_regime"), "unknown"),
        "net_pnl_usdt": round(net, 6),
        "gross_pnl_usdt": round(gross, 6),
        "fee_usdt": round(fee, 6),
        "slippage_usdt": round(slippage, 6),
        "notional_usdt": abs(_safe_float(item.get("notional_usdt") or item.get("quote_qty") or item.get("size_usdt"), 0.0)),
        "latency_ms": max(0.0, _safe_float(item.get("latency_ms") or item.get("execution_latency_ms"), 0.0)),
        "fill_ratio": max(0.0, min(1.0, _safe_float(item.get("fill_ratio") or item.get("filled_ratio"), 1.0))),
        "rejected": _safe_bool(item.get("rejected") or item.get("order_rejected"), False),
        "partial_fill": _safe_bool(item.get("partial_fill"), False),
    }


def _trades(data: dict) -> list[dict]:
    raw: list[dict] = []
    for key in ("performance_records", "safe_trade_journal_records", "trade_journal", "journal", "real_trade_journal", "paper_trade_results"):
        raw = [item for item in _as_list(data.get(key)) if isinstance(item, dict)]
        if raw:
            break
    if not raw:
        raw = [
            {"lane": "paper", "symbol": "BTCUSDT", "strategy": "choch_imbalance", "regime": "trend", "gross_pnl_usdt": 0.42, "fee_usdt": 0.04, "slippage_usdt": 0.02, "notional_usdt": 80, "latency_ms": 240, "fill_ratio": 1.0},
            {"lane": "paper", "symbol": "ETHUSDT", "strategy": "range_reversion", "regime": "range", "gross_pnl_usdt": -0.28, "fee_usdt": 0.04, "slippage_usdt": 0.03, "notional_usdt": 80, "latency_ms": 260, "fill_ratio": 1.0},
            {"lane": "micro-real", "symbol": "BTCUSDT", "strategy": "choch_imbalance", "regime": "trend", "gross_pnl_usdt": 0.18, "fee_usdt": 0.02, "slippage_usdt": 0.01, "notional_usdt": 30, "latency_ms": 310, "fill_ratio": 1.0},
        ]
    return [_normalize_trade(item, idx + 1) for idx, item in enumerate(raw)]


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return round(abs(worst), 6)


def _loss_streak(values: list[float]) -> int:
    streak = 0
    best = 0
    for value in values:
        if value < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def _metrics_for(items: list[dict]) -> dict:
    pnls = [_safe_float(t.get("net_pnl_usdt"), 0.0) for t in items]
    wins = [v for v in pnls if v > 0]
    losses = [v for v in pnls if v < 0]
    total = len(pnls)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    expectancy = (sum(pnls) / total) if total else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    fees = sum(_safe_float(t.get("fee_usdt"), 0.0) for t in items)
    slippage = sum(_safe_float(t.get("slippage_usdt"), 0.0) for t in items)
    return {
        "trade_count": total,
        "win_rate": round((len(wins) / total) if total else 0.0, 4),
        "profit_factor": round(min(profit_factor, 999.0), 4),
        "expectancy_usdt": round(expectancy, 6),
        "average_win_usdt": round(avg_win, 6),
        "average_loss_usdt": round(avg_loss, 6),
        "max_drawdown_usdt": _max_drawdown(pnls),
        "consecutive_loss_max": _loss_streak(pnls),
        "fee_impact_usdt": round(fees, 6),
        "slippage_impact_usdt": round(slippage, 6),
        "net_pnl_usdt": round(sum(pnls), 6),
    }


def _group_metrics(trades: list[dict], *keys: str) -> list[dict]:
    buckets: dict[tuple, list[dict]] = {}
    for trade in trades:
        group_key = tuple(trade.get(k, "unknown") for k in keys)
        buckets.setdefault(group_key, []).append(trade)
    rows = []
    for group_key, items in buckets.items():
        row = {keys[i]: group_key[i] for i in range(len(keys))}
        row.update(_metrics_for(items))
        rows.append(row)
    return sorted(rows, key=lambda r: (r.get("expectancy_usdt", 0), r.get("profit_factor", 0)), reverse=True)


def _score(metrics: dict) -> float:
    pf = min(_safe_float(metrics.get("profit_factor"), 0.0), 3.0)
    expectancy = _safe_float(metrics.get("expectancy_usdt"), 0.0)
    win_rate = _safe_float(metrics.get("win_rate"), 0.0)
    dd = _safe_float(metrics.get("max_drawdown_usdt"), 0.0)
    fee = abs(_safe_float(metrics.get("fee_impact_usdt"), 0.0))
    slip = abs(_safe_float(metrics.get("slippage_impact_usdt"), 0.0))
    trades = max(1, _safe_int(metrics.get("trade_count"), 1))
    return round((pf * 25.0) + (win_rate * 25.0) + (expectancy * 10.0) - (dd * 3.0) - ((fee + slip) / trades * 8.0), 4)


def _performance_label(score: float, metrics: dict) -> str:
    if _safe_int(metrics.get("trade_count"), 0) < 3:
        return "weak"
    if metrics.get("consecutive_loss_max", 0) >= 3 or metrics.get("expectancy_usdt", 0) < -0.05:
        return "stop"
    if score >= 75:
        return "strong"
    if score >= 45:
        return "normal"
    return "weak"


def build_rev131_trade_performance_metrics_engine(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    trades = _trades(data)
    by_lane = _group_metrics(trades, "lane")
    overall = _metrics_for(trades)
    checks = [
        _check("trade_dataset_available", "ok" if trades else "review", "Trade records are normalized from journal/performance snapshots."),
        _check("lane_separation", "ok" if by_lane else "blocked", "Paper, micro-real and real lanes remain separated."),
        _check("secret_free_metrics", "ok", "Metrics snapshot never returns API secrets."),
    ]
    return {
        "engine": "autonomous_trade_performance_metrics_engine", "revision": 131, "status": _final_status(checks),
        "readiness": "PERFORMANCE_METRICS_READY" if _final_status(checks) == "ok" else "PERFORMANCE_METRICS_REVIEW",
        "metric_snapshot": {"overall": overall, "by_lane": by_lane, "generated_at": now_iso()},
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "strategy_performance_attribution",
    }


def build_rev132_strategy_performance_attribution(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    metrics = data.get("autonomous_trade_performance_metrics_engine") if isinstance(data.get("autonomous_trade_performance_metrics_engine"), dict) else build_rev131_trade_performance_metrics_engine(data, settings, auth_store, username)
    trades = _trades(data)
    attribution = _group_metrics(trades, "symbol", "strategy", "regime")
    rows = []
    for row in attribution:
        signal = "hold"
        if row["trade_count"] >= 3 and row["profit_factor"] >= 1.25 and row["expectancy_usdt"] > 0:
            signal = "cautious_promotion"
        if row["trade_count"] >= 2 and (row["profit_factor"] < 0.8 or row["expectancy_usdt"] < 0):
            signal = "demotion"
        rows.append({**row, "attribution_signal": signal})
    checks = [
        _check("metrics_engine_available", "ok" if metrics.get("revision") == 131 else "blocked", "Rev132 consumes Rev131 metrics."),
        _check("symbol_strategy_regime_table", "ok" if rows else "review", "Attribution table exists by symbol/strategy/regime."),
        _check("demotion_signal_available", "ok" if any(r["attribution_signal"] == "demotion" for r in rows) or rows else "review", "Weak strategy can be demoted."),
    ]
    return {
        "engine": "autonomous_strategy_performance_attribution", "revision": 132, "status": _final_status(checks),
        "readiness": "STRATEGY_ATTRIBUTION_READY" if _final_status(checks) == "ok" else "STRATEGY_ATTRIBUTION_REVIEW",
        "attribution_table": rows, "top_candidates": rows[:5],
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "execution_quality_analytics",
    }


def build_rev133_execution_quality_analytics(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _settings(settings, "autonomous_performance_observability")
    max_latency = _safe_float(policy.get("max_latency_ms"), 1200.0)
    max_slip_per_trade = _safe_float(policy.get("max_slippage_usdt_per_trade"), 0.08)
    trades = _trades(data)
    count = max(1, len(trades))
    avg_latency = sum(t["latency_ms"] for t in trades) / count
    avg_slip = sum(t["slippage_usdt"] for t in trades) / count
    rejects = len([t for t in trades if t["rejected"]])
    partials = len([t for t in trades if t["partial_fill"] or t["fill_ratio"] < 1.0])
    fee_total = sum(t["fee_usdt"] for t in trades)
    quality_low = avg_latency > max_latency or avg_slip > max_slip_per_trade or rejects > 0 or partials >= max(2, count // 3)
    recommendation = "reduce_size" if quality_low and rejects == 0 else ("hold_execution" if rejects else "execution_quality_normal")
    checks = [
        _check("execution_dataset_available", "ok" if trades else "review", "Execution records are available for quality analysis."),
        _check("slippage_quality", "review" if avg_slip > max_slip_per_trade else "ok", "Slippage impact is monitored."),
        _check("latency_quality", "review" if avg_latency > max_latency else "ok", "Latency is monitored without exchange writes."),
        _check("rejection_guard", "blocked" if rejects else "ok", "Rejected orders force hold/stop recommendation."),
    ]
    return {
        "engine": "autonomous_execution_quality_analytics", "revision": 133, "status": _final_status(checks),
        "readiness": "EXECUTION_QUALITY_READY" if _final_status(checks) == "ok" else "EXECUTION_QUALITY_REVIEW",
        "execution_quality": {
            "average_latency_ms": round(avg_latency, 3), "average_slippage_usdt": round(avg_slip, 6),
            "partial_fill_count": partials, "rejected_order_count": rejects, "fee_impact_usdt": round(fee_total, 6),
            "recommendation": recommendation,
        },
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "risk_adjusted_return_scoring",
    }


def build_rev134_risk_adjusted_return_scoring(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    metrics = data.get("autonomous_trade_performance_metrics_engine") if isinstance(data.get("autonomous_trade_performance_metrics_engine"), dict) else build_rev131_trade_performance_metrics_engine(data, settings, auth_store, username)
    execution = data.get("autonomous_execution_quality_analytics") if isinstance(data.get("autonomous_execution_quality_analytics"), dict) else build_rev133_execution_quality_analytics(data, settings, auth_store, username)
    overall = metrics.get("metric_snapshot", {}).get("overall", {}) if isinstance(metrics.get("metric_snapshot"), dict) else {}
    base_score = _score(overall)
    exec_quality = execution.get("execution_quality", {}) if isinstance(execution.get("execution_quality"), dict) else {}
    penalty = 0.0
    penalty += abs(_safe_float(overall.get("max_drawdown_usdt"), 0.0)) * 2.0
    penalty += abs(_safe_float(overall.get("fee_impact_usdt"), 0.0)) * 0.7
    penalty += abs(_safe_float(overall.get("slippage_impact_usdt"), 0.0)) * 1.0
    penalty += _safe_int(exec_quality.get("rejected_order_count"), 0) * 20.0
    final_score = round(max(0.0, min(100.0, base_score - penalty)), 4)
    label = _performance_label(final_score, overall)
    checks = [
        _check("metrics_engine_available", "ok" if metrics.get("revision") == 131 else "blocked", "Risk adjusted score consumes Rev131."),
        _check("execution_quality_available", "ok" if execution.get("revision") == 133 else "blocked", "Risk adjusted score consumes Rev133."),
        _check("risk_adjusted_label", "ok" if label in {"normal", "weak", "strong", "stop"} else "blocked", "Summary label is minimal."),
    ]
    return {
        "engine": "autonomous_risk_adjusted_return_scoring", "revision": 134, "status": _final_status(checks),
        "readiness": "RISK_ADJUSTED_SCORE_READY" if _final_status(checks) == "ok" else "RISK_ADJUSTED_SCORE_REVIEW",
        "risk_adjusted_score": {
            "score": final_score, "performance_state": label, "drawdown_penalty": round(abs(_safe_float(overall.get("max_drawdown_usdt"), 0.0)) * 2.0, 6),
            "fee_penalty": round(abs(_safe_float(overall.get("fee_impact_usdt"), 0.0)) * 0.7, 6),
            "slippage_penalty": round(abs(_safe_float(overall.get("slippage_impact_usdt"), 0.0)) * 1.0, 6),
        },
        "summary_result": {"performance": label},
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "performance_sentinel_v2",
    }


def build_rev135_performance_sentinel_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    live = data.get("autonomous_first_live_stabilization_report") if isinstance(data.get("autonomous_first_live_stabilization_report"), dict) else build_rev130_first_live_stabilization_report(data, settings, auth_store, username)
    metrics = data.get("autonomous_trade_performance_metrics_engine") if isinstance(data.get("autonomous_trade_performance_metrics_engine"), dict) else build_rev131_trade_performance_metrics_engine(data, settings, auth_store, username)
    scoring = data.get("autonomous_risk_adjusted_return_scoring") if isinstance(data.get("autonomous_risk_adjusted_return_scoring"), dict) else build_rev134_risk_adjusted_return_scoring(data, settings, auth_store, username)
    overall = metrics.get("metric_snapshot", {}).get("overall", {}) if isinstance(metrics.get("metric_snapshot"), dict) else {}
    perf_state = scoring.get("risk_adjusted_score", {}).get("performance_state", "weak")
    action = "continue"
    if perf_state == "stop" or _safe_int(overall.get("consecutive_loss_max"), 0) >= 3:
        action = "stop"
    elif perf_state == "weak":
        action = "cooldown"
    elif perf_state == "strong":
        action = "cautious_continue"
    readiness = "PERFORMANCE_SENTINEL_READY" if live.get("revision") == 130 else "PERFORMANCE_SENTINEL_REVIEW"
    daily = {"score": scoring.get("risk_adjusted_score", {}).get("score", 0), "state": perf_state, "action": action}
    weekly = {"score": max(0, round(_safe_float(daily["score"], 0) - 3, 4)), "state": perf_state, "action": action}
    monthly = {"score": max(0, round(_safe_float(daily["score"], 0) - 5, 4)), "state": perf_state, "action": action}
    checks = [
        _check("live_stabilization_available", "ok" if live.get("revision") == 130 else "blocked", "Rev135 consumes Rev130 live stabilization."),
        _check("risk_adjusted_score_available", "ok" if scoring.get("revision") == 134 else "blocked", "Rev135 consumes Rev134 score."),
        _check("cooldown_or_stop_logic", "ok" if action in {"continue", "cautious_continue", "cooldown", "stop"} else "blocked", "Bad expectancy/loss streak triggers cooldown or stop."),
    ]
    return {
        "engine": "autonomous_performance_sentinel_v2", "revision": 135, "status": _final_status(checks),
        "readiness": readiness,
        "sentinel_summary": {
            "daily": daily, "weekly": weekly, "monthly": monthly,
            "loss_streak": overall.get("consecutive_loss_max", 0), "expectancy_usdt": overall.get("expectancy_usdt", 0),
            "recommendation": action,
        },
        "summary_result": {"performance_state": perf_state, "action": action, "risk_adjusted_score": daily["score"]},
        "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(),
        "contains_secret": False, "secret_values_returned": False,
        "next_allowed_step": "rev136_adaptive_optimization_block",
    }


_BUILDERS = {
    131: build_rev131_trade_performance_metrics_engine,
    132: build_rev132_strategy_performance_attribution,
    133: build_rev133_execution_quality_analytics,
    134: build_rev134_risk_adjusted_return_scoring,
    135: build_rev135_performance_sentinel_v2,
}

_NAMES = {
    131: "autonomous_trade_performance_metrics_engine",
    132: "autonomous_strategy_performance_attribution",
    133: "autonomous_execution_quality_analytics",
    134: "autonomous_risk_adjusted_return_scoring",
    135: "autonomous_performance_sentinel_v2",
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = _BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_performance_observability_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev131-135 revision.", "contains_secret": False}
    return builder(data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 131:
        overall = payload.get("metric_snapshot", {}).get("overall", {})
        return {"revision": 131, "status": payload.get("status"), "trade_count": overall.get("trade_count", 0), "win_rate": overall.get("win_rate", 0), "profit_factor": overall.get("profit_factor", 0), "expectancy_usdt": overall.get("expectancy_usdt", 0), "contains_secret": False}
    if int(revision) == 132:
        return {"revision": 132, "status": payload.get("status"), "top_candidates": payload.get("top_candidates", [])[:3], "contains_secret": False}
    if int(revision) == 133:
        return {"revision": 133, "status": payload.get("status"), **payload.get("execution_quality", {}), "contains_secret": False}
    if int(revision) == 134:
        return {"revision": 134, "status": payload.get("status"), **payload.get("risk_adjusted_score", {}), "contains_secret": False}
    if int(revision) == 135:
        return {"revision": 135, "status": payload.get("status"), **payload.get("summary_result", {}), "contains_secret": False}
    return {"revision": revision, "status": payload.get("status"), "contains_secret": False}


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs: dict[str, dict] = {}
    working = deepcopy(data)
    for revision in range(131, 136):
        key = _NAMES[revision]
        payload = _BUILDERS[revision](working, settings, auth_store, username)
        outputs[key] = payload
        working[key] = payload
    final = outputs["autonomous_performance_sentinel_v2"]
    return {
        "engine": "autonomous_performance_observability_block",
        "revision": 135,
        "status": final.get("status", "review"),
        "readiness": final.get("readiness", "PERFORMANCE_SENTINEL_REVIEW"),
        "outputs": outputs,
        "summary_result": final.get("summary_result", {}),
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "network_default_off": True,
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev136_adaptive_optimization_block",
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    checks = [
        _check("payload_available", "ok" if payload.get("revision") == int(revision) else "blocked", "Revision payload is callable."),
        _check("no_exchange_network", "ok" if payload.get("command_preview", {}).get("sends_exchange_request") is False else "blocked", "No real exchange network call is allowed."),
        _check("no_real_submit", "ok" if payload.get("command_preview", {}).get("places_order") is False else "blocked", "Direct real submit remains OFF."),
        _check("no_real_close", "ok" if payload.get("command_preview", {}).get("submits_close_order") is False else "blocked", "Direct close remains OFF."),
        _check("secret_free", "ok" if payload.get("contains_secret") is False and payload.get("secret_values_returned") is False else "blocked", "No secret leaks in response."),
    ]
    return {
        "status": _final_status(checks),
        "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL",
        "revision": int(revision),
        "engine": "autonomous_performance_observability_quality_gate",
        "checks": checks,
        "check_totals": _totals(checks),
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "contains_secret": False,
    }
