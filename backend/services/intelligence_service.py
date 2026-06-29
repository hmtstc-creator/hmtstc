from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev

from core.storage import now_iso
from services.coin_quality_service import score_coin_quality
from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.real_trade_safety_service import build_runtime_health, build_weighted_recommendation
from services.reports_service import build_reports


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _scan_rows(data: dict) -> list[dict]:
    scan = data.get("last_scan") or {}
    return list(scan.get("scan_rows") or scan.get("candidates") or [])


def detect_market_regime(data: dict, settings: dict) -> dict:
    rows = _scan_rows(data)
    candidates = (data.get("last_scan") or {}).get("candidates") or []
    vol = [_safe_float(item.get("volatility")) for item in rows if _safe_float(item.get("volatility")) > 0]
    change = [_safe_float(item.get("change_percent")) for item in rows if item.get("change_percent") is not None]
    scores = [_safe_float(item.get("score")) for item in candidates]
    avg_vol = mean(vol) if vol else 0
    vol_dispersion = pstdev(vol) if len(vol) > 2 else 0
    up = sum(1 for x in change if x > 0)
    down = sum(1 for x in change if x < 0)
    breadth = ((up - down) / max(len(change), 1)) * 100
    avg_score = mean(scores) if scores else 0
    candidate_ratio = len(candidates) / max(len(rows), 1) * 100 if rows else 0

    if avg_vol >= 5 or vol_dispersion >= 4:
        regime = "HIGH_VOLATILITY"
    elif breadth > 22 and avg_score >= 55:
        regime = "TREND_UP"
    elif breadth < -22:
        regime = "TREND_DOWN"
    elif abs(breadth) <= 12 and avg_vol <= 1.25:
        regime = "RANGE_LOW_VOL"
    else:
        regime = "CHOPPY"

    confidence = _clamp(35 + abs(breadth) * 0.6 + min(avg_vol, 6) * 6 + min(len(rows), 250) / 250 * 20)
    return {
        "status": "ok",
        "regime": regime,
        "confidence": round(confidence, 2),
        "avg_volatility": round(avg_vol, 4),
        "volatility_dispersion": round(vol_dispersion, 4),
        "market_breadth": round(breadth, 2),
        "candidate_quality": round(avg_score, 2),
        "candidate_ratio_percent": round(candidate_ratio, 2),
        "no_trade_bias": regime in {"HIGH_VOLATILITY", "CHOPPY", "TREND_DOWN"},
        "updated_at": now_iso(),
    }


def build_dynamic_risk_adjustment(data: dict, settings: dict) -> dict:
    regime = detect_market_regime(data, settings)
    rankings = get_model_rankings(data)
    top = rankings[0] if rankings else {}
    dd = abs(_safe_float(top.get("max_drawdown_percent")))
    stability = _safe_float(top.get("stability_score"))
    execution_quality = _safe_float(top.get("score_components", {}).get("execution"), 70)
    multiplier = 1.0
    reasons = []

    if regime.get("no_trade_bias"):
        multiplier *= 0.55
        reasons.append("market_regime_defensive")
    if dd >= 6:
        multiplier *= 0.65
        reasons.append("model_drawdown_high")
    if stability and stability < 55:
        multiplier *= 0.75
        reasons.append("model_stability_low")
    if execution_quality < 50:
        multiplier *= 0.80
        reasons.append("execution_quality_low")
    if data.get("emergency_lock"):
        multiplier = 0
        reasons.append("emergency_lock")

    mode = "defensive" if multiplier < 0.75 else ("normal" if multiplier <= 1.0 else "offensive_review")
    return {
        "status": "ok",
        "mode": mode,
        "risk_multiplier": round(multiplier, 3),
        "auto_apply": False,
        "owner_review_required": True,
        "reasons": reasons or ["risk_normal"],
        "regime": regime,
        "top_model_id": top.get("model_id"),
        "guardrail": "Real trade risk never increases automatically.",
    }


def build_cooldown_policy(data: dict, settings: dict) -> dict:
    history = list(data.get("history") or [])[-30:]
    consecutive_losses = 0
    for trade in reversed(history):
        if _safe_float(trade.get("pnl")) < 0:
            consecutive_losses += 1
        else:
            break
    runtime = build_runtime_health(data, settings)
    dynamic = build_dynamic_risk_adjustment(data, settings)
    scan = data.get("last_scan") or {}
    blockers = []
    if consecutive_losses >= 3:
        blockers.append("three_consecutive_losses")
    if runtime.get("status") != "ok":
        blockers.append("runtime_degraded")
    if dynamic.get("risk_multiplier") == 0:
        blockers.append("risk_multiplier_zero")
    if (scan.get("rejection_breakdown") or {}).get("wide_spread", 0) >= 5:
        blockers.append("spread_environment_bad")
    if bool(data.get("emergency_lock")):
        blockers.append("emergency_lock")
    if detect_market_regime(data, settings).get("no_trade_bias"):
        blockers.append("market_regime_no_trade_bias")
    minutes = 0
    if blockers:
        minutes = 45 if "emergency_lock" in blockers else (30 if consecutive_losses >= 3 else 15)
    return {
        "status": "blocked" if blockers else "ok",
        "consecutive_losses": consecutive_losses,
        "blockers": sorted(set(blockers)),
        "cooldown_minutes": minutes,
        "message": "No-trade/cooldown aktif." if blockers else "Cooldown gerekmez.",
        "manual_unlock_required": "emergency_lock" in blockers,
    }


def build_portfolio_allocation(data: dict, settings: dict) -> dict:
    rankings = get_model_rankings(data)
    bot = settings.get("bot") or {}
    allocated = _safe_float(bot.get("allocated_usdt"), 1000)
    dynamic = build_dynamic_risk_adjustment(data, settings)
    reserve_ratio = 0.72 if dynamic.get("mode") != "defensive" else 0.86
    deployable = allocated * (1 - reserve_ratio)
    top = [row for row in rankings if row.get("eligible_for_real")][:5]
    total_score = sum(_safe_float(row.get("score")) for row in top) or 1
    allocations = []
    for row in top:
        raw_weight = _safe_float(row.get("score")) / total_score
        cap_weight = min(raw_weight, 0.35)
        allocations.append({
            "model_id": row.get("model_id"),
            "weight_percent": round(cap_weight * 100, 2),
            "suggested_usdt": round(deployable * cap_weight, 2),
            "reserve_policy": f"{round(reserve_ratio * 100)}% USDT reserve",
            "reason": "score_weighted_with_usdt_reserve_and_model_cap",
        })
    return {"status": "ok", "allocated_usdt": allocated, "reserve_ratio": reserve_ratio, "deployable_usdt": round(deployable, 2), "max_model_weight_percent": 35, "allocations": allocations}


def build_ab_test_plan(data: dict, settings: dict) -> dict:
    variants = []
    for row in get_model_rankings(data)[:8]:
        drawdown = abs(_safe_float(row.get("max_drawdown_percent")))
        variants.append({
            "base_model_id": row.get("model_id"),
            "variant": "risk_minus_20_percent" if drawdown > 4 else "threshold_plus_5_percent",
            "objective": "reduce_drawdown" if drawdown > 4 else "increase_trade_quality",
            "paper_only": True,
        })
    return {"status": "ok", "paper_only": True, "variants": variants[:6]}


def build_walk_forward_summary(data: dict, settings: dict) -> dict:
    rows = []
    for row in get_model_rankings(data)[:15]:
        trades = int(row.get("total_trades") or 0)
        score = _safe_float(row.get("score"))
        stability = _safe_float(row.get("stability_score"))
        verdict = "insufficient_data" if trades < 10 else ("pass" if score >= 60 and stability >= 55 else "watch")
        overfit_risk = "high" if trades < 5 and score > 70 else ("medium" if trades < 10 else "low")
        rows.append({"model_id": row.get("model_id"), "sample_trades": trades, "score": score, "stability": stability, "overfit_risk": overfit_risk, "verdict": verdict})
    return {"status": "ok", "method": "rolling_forward_shadow_summary", "rows": rows}


def build_model_degradation(data: dict, settings: dict) -> dict:
    alerts = []
    lab = ensure_paper_lab(data)
    for model in (lab.get("models") or {}).values():
        history = model.get("history") or []
        if len(history) < 12:
            continue
        old = history[-12:-6]
        recent = history[-6:]
        old_pnl = sum(_safe_float(t.get("pnl")) for t in old)
        recent_pnl = sum(_safe_float(t.get("pnl")) for t in recent)
        if recent_pnl < old_pnl * 0.35 and recent_pnl < 0:
            alerts.append({"model_id": model.get("model_id"), "status": "degrading", "old_pnl": round(old_pnl, 4), "recent_pnl": round(recent_pnl, 4), "action": "watch_or_retire"})
    return {"status": "ok", "alerts": alerts, "count": len(alerts)}


def build_execution_quality_summary(data: dict, settings: dict) -> dict:
    lab = ensure_paper_lab(data)
    rejections = Counter()
    slippages = []
    spreads = []
    closed = 0
    for model in (lab.get("models") or {}).values():
        for trade in model.get("history") or []:
            closed += 1
            entry = trade.get("execution_entry") or {}
            exit_ = trade.get("execution_exit") or {}
            if entry.get("status") == "rejected":
                rejections[entry.get("reason") or "unknown"] += 1
            if entry:
                slippages.append(_safe_float(entry.get("slippage_percent")))
                spreads.append(_safe_float(entry.get("spread_percent")))
            if exit_:
                slippages.append(_safe_float(exit_.get("slippage_percent")))
    return {
        "status": "ok",
        "closed_trade_sample": closed,
        "total_rejections": sum(rejections.values()),
        "rejections_by_reason": dict(rejections),
        "avg_slippage_percent": round(mean(slippages), 4) if slippages else 0,
        "avg_spread_percent": round(mean(spreads), 4) if spreads else 0,
    }


def build_coin_quality_dashboard(data: dict, settings: dict) -> dict:
    rows = _scan_rows(data)
    scored = []
    for row in rows:
        quality = score_coin_quality(row)
        scored.append({**row, **quality})
    buckets = Counter(item.get("bucket") for item in scored)
    avg = mean([_safe_float(item.get("quality_score")) for item in scored]) if scored else 0
    return {"status": "ok", "total_scored": len(scored), "avg_quality_score": round(avg, 2), "buckets": dict(buckets), "top": sorted(scored, key=lambda x: _safe_float(x.get("quality_score")), reverse=True)[:20]}


def build_coin_clusters(data: dict, settings: dict) -> dict:
    clusters = defaultdict(list)
    for row in _scan_rows(data):
        vol = _safe_float(row.get("volatility"))
        volume = _safe_float(row.get("quote_volume") or row.get("volume_today"))
        if volume >= 50_000_000:
            key = "major_liquid"
        elif vol >= 5:
            key = "high_volatility"
        elif _safe_float(row.get("quality_score")) < 45:
            key = "fragile_watch"
        else:
            key = "standard_spot"
        clusters[key].append(row.get("symbol"))
    return {"status": "ok", "clusters": {k: v[:50] for k, v in clusters.items()}, "counts": {k: len(v) for k, v in clusters.items()}}


def build_orderbook_intelligence(data: dict, settings: dict) -> dict:
    candidates = (data.get("last_scan") or {}).get("candidates") or []
    top = candidates[0] if candidates else {}
    quality = _safe_float(top.get("quality_score"), 50)
    spread = _safe_float(top.get("spread_percent"), 0.08)
    volatility = _safe_float(top.get("volatility"), 0)
    imbalance = _clamp(quality - spread * 25 + min(volatility, 4) * 4)
    fake_wall_risk = _clamp(100 - quality + spread * 25 + max(0, volatility - 4) * 8)
    return {"status": "ok", "symbol": top.get("symbol"), "imbalance_score": round(imbalance, 2), "fake_wall_risk": round(fake_wall_risk, 2), "spoofing_risk": round(fake_wall_risk * 0.8, 2), "entry_confirmation": bool(imbalance >= 60 and fake_wall_risk <= 55), "source": "proxy_from_scan_until_depth_stream_enabled"}


def build_multi_timeframe_signal(data: dict, settings: dict) -> dict:
    signals = []
    for row in ((data.get("last_scan") or {}).get("candidates") or [])[:20]:
        micro = _safe_float(row.get("score"))
        mtf = _safe_float(row.get("quality_score"), 50) * 0.6 + _safe_float(row.get("volatility")) * 5
        signals.append({"symbol": row.get("symbol"), "micro_score": round(micro, 2), "mtf_score": round(_clamp(mtf), 2), "passed": micro >= 55 and mtf >= 55})
    return {"status": "ok", "signals": signals}


def build_news_risk_filter(data: dict, settings: dict) -> dict:
    alerts = []
    for row in _scan_rows(data):
        vol = _safe_float(row.get("volatility"))
        change = abs(_safe_float(row.get("change_percent")))
        if vol >= 7 or change >= 18:
            alerts.append({"symbol": row.get("symbol"), "risk": "event_like_volatility", "volatility": vol, "change_percent": change})
    return {"status": "ok", "alerts": alerts[:50], "count": len(alerts)}


def build_strategy_generator(data: dict, settings: dict) -> dict:
    drafts = []
    for row in get_model_rankings(data)[:5]:
        drafts.append({"id": f"draft_{row.get('model_id')}", "based_on_model": row.get("model_id"), "paper_only": True, "change": "tighten_entry_quality_or_reduce_risk", "reason": "controlled_variant_from_top_model"})
    return {"status": "ok", "drafts": drafts, "auto_deploy": False}


def build_ai_strategy_insights(data: dict, settings: dict) -> dict:
    rec = build_weighted_recommendation(data, settings)
    degradation = build_model_degradation(data, settings)
    return {"status": "ok", "role": "strategy_analyst_only", "summary": rec.get("reason"), "weaknesses": degradation.get("alerts", []), "guardrail": "AI does not approve real trades."}


def build_replay_index(data: dict, settings: dict) -> dict:
    lab = ensure_paper_lab(data)
    rows = []
    for model in (lab.get("models") or {}).values():
        for trade in (model.get("history") or [])[-25:]:
            rows.append({"model_id": model.get("model_id"), "symbol": trade.get("symbol"), "entry_time": trade.get("entry_time"), "exit_time": trade.get("exit_time"), "reason": trade.get("reason"), "pnl": trade.get("pnl")})
    return {"status": "ok", "paper_trades": rows[-100:], "count": len(rows)}


def build_trade_explainability(data: dict, settings: dict) -> dict:
    items = []
    for row in build_replay_index(data, settings).get("paper_trades", [])[-20:]:
        plain = f"{row.get('symbol')} işlemi {row.get('model_id')} modeliyle açıldı; kapanış sebebi {row.get('reason') or '-'}, PnL {row.get('pnl')} USDT."
        items.append({**row, "plain_reason": plain})
    return {"status": "ok", "items": items}


def build_safe_deploy_state(data: dict, settings: dict) -> dict:
    health = build_runtime_health(data, settings)
    return {"status": "ok", "canary_required": True, "latest_health": health, "rollback_advice": "Rollback only after failed health/smoke checks.", "deploy_mode": "shadow_first"}


def build_micro_pilot_plan(data: dict, settings: dict) -> dict:
    rec = build_weighted_recommendation(data, settings)
    safety_status = "blocked_until_owner_live_config" if rec.get("action") != "SWITCH_TO_NEW_MODEL" else "candidate_ready_for_manual_review"
    return {"status": safety_status, "candidate_model_id": rec.get("candidate_model_id"), "max_positions": 1, "max_usdt_per_trade": 10, "real_trade_default": False, "auto_lock_after_pilot": True}


def build_observability(data: dict, settings: dict) -> dict:
    health_history = data.get("health_history") or []
    problems = defaultdict(int)
    for item in health_history:
        for problem in item.get("problems") or []:
            problems[problem] += 1
    health = build_runtime_health(data, settings)
    severity = "healthy" if health.get("status") == "ok" else ("critical" if len(health.get("problems") or []) >= 2 else "degraded")
    return {"status": "ok", "severity": severity, "samples": len(health_history), "problem_counts": dict(problems), "backend_latency_ms": _safe_float(data.get("backend_latency_ms")), "binance_latency_ms": _safe_float((data.get("last_scan") or {}).get("latency_ms")), "bot_loop_state": health.get("status"), "latest_health": health}


def build_optimization_overview(data: dict, settings: dict) -> dict:
    report = build_reports(data, settings)
    return {
        "status": "ok",
        "generated_at": now_iso(),
        "market_intelligence": {
            "regime": detect_market_regime(data, settings),
            "coin_quality": build_coin_quality_dashboard(data, settings),
            "coin_clusters": build_coin_clusters(data, settings),
            "orderbook": build_orderbook_intelligence(data, settings),
            "multi_timeframe": build_multi_timeframe_signal(data, settings),
            "news_risk": build_news_risk_filter(data, settings),
        },
        "model_intelligence": {
            "recommendation": build_weighted_recommendation(data, settings),
            "walk_forward": build_walk_forward_summary(data, settings),
            "degradation": build_model_degradation(data, settings),
            "execution_quality": build_execution_quality_summary(data, settings),
            "strategy_generator": build_strategy_generator(data, settings),
            "ai_insights": build_ai_strategy_insights(data, settings),
        },
        "optimization": {
            "dynamic_risk": build_dynamic_risk_adjustment(data, settings),
            "cooldown": build_cooldown_policy(data, settings),
            "portfolio_allocation": build_portfolio_allocation(data, settings),
            "ab_test_plan": build_ab_test_plan(data, settings),
        },
        "operations": {
            "observability": build_observability(data, settings),
            "trade_explainability": build_trade_explainability(data, settings),
            "safe_deploy": build_safe_deploy_state(data, settings),
            "replay": build_replay_index(data, settings),
            "micro_pilot": build_micro_pilot_plan(data, settings),
        },
        "reports_crosscheck": {
            "models_count": (report.get("paper_lab") or {}).get("models_count", 0),
            "recommendation": (report.get("recommendation") or {}).get("action"),
        },
    }
