from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.intelligence_service import _safe_float, build_dynamic_risk_adjustment, get_model_rankings
from services.market_intelligence_final_service import build_market_regime_strategy_match, build_no_trade_cooldown_final


def _bot_settings(settings: dict | None) -> dict:
    return (settings or {}).get("bot") or {}


def _capital(settings: dict | None) -> float:
    bot = _bot_settings(settings)
    return max(0.0, _safe_float(bot.get("allocated_usdt") or bot.get("starting_capital_usdt") or bot.get("capital_usdt"), 1000.0))


def _models(data: dict) -> list[dict]:
    rows = get_model_rankings(data or {})
    return rows if isinstance(rows, list) else []


def _coin_cluster(symbol: str) -> str:
    s = str(symbol or "").upper()
    if s in {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}:
        return "major_liquid"
    if any(k in s for k in ["PEPE", "DOGE", "SHIB", "FLOKI", "BONK", "WIF"]):
        return "meme_high_beta"
    if any(k in s for k in ["USDC", "FDUSD", "TUSD", "DAI", "EUR", "TRY"]):
        return "stable_or_fiat_related"
    return "alt_spot"


def _scan_rows(data: dict) -> list[dict]:
    scan = (data or {}).get("last_scan") or {}
    rows = scan.get("scan_rows") or scan.get("candidates") or []
    return rows if isinstance(rows, list) else []


def build_usdt_reserve_policy(data: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    capital = _capital(settings)
    dynamic = build_dynamic_risk_adjustment(data or {}, settings)
    no_trade = build_no_trade_cooldown_final(data or {}, settings)
    regime = build_market_regime_strategy_match(data or {}, settings)
    blockers = []
    base_reserve = 0.72
    if dynamic.get("mode") in {"defensive", "risk_off"}:
        base_reserve = max(base_reserve, 0.86)
        blockers.append("dynamic_risk_defensive")
    if no_trade.get("status") != "ok":
        base_reserve = max(base_reserve, 0.90)
        blockers.append("no_trade_active")
    if regime.get("risk_posture") in {"defensive", "risk_off"} or regime.get("no_trade_bias"):
        base_reserve = max(base_reserve, 0.88)
        blockers.append("market_regime_defensive")
    if bool((data or {}).get("emergency_lock")):
        base_reserve = 1.0
        blockers.append("emergency_lock")
    reserve_usdt = round(capital * base_reserve, 2)
    deployable_usdt = round(max(0.0, capital - reserve_usdt), 2)
    return {
        "status": "blocked" if base_reserve >= 1.0 else ("review" if blockers else "ok"),
        "capital_usdt": round(capital, 2),
        "target_reserve_ratio": round(base_reserve, 4),
        "target_reserve_percent": round(base_reserve * 100, 2),
        "reserve_usdt": reserve_usdt,
        "deployable_usdt": deployable_usdt,
        "blockers": sorted(set(blockers)),
        "policy": "USDT reserve first; allocation never overrides real safety, no-trade or emergency lock.",
    }


def build_correlation_cluster_exposure(data: dict, settings: dict | None = None) -> dict:
    rows = _scan_rows(data or {})
    open_positions = (data or {}).get("positions") or []
    if not isinstance(open_positions, list):
        open_positions = []
    cluster_counts: dict[str, int] = defaultdict(int)
    quality_by_cluster: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        symbol = str(row.get("symbol") or row.get("coin") or "")
        cluster = str(row.get("cluster") or _coin_cluster(symbol))
        quality_by_cluster[cluster].append(_safe_float(row.get("quality_score") or row.get("score"), 50.0))
    for pos in open_positions:
        symbol = str(pos.get("symbol") or pos.get("coin") or "")
        cluster_counts[_coin_cluster(symbol)] += 1
    clusters = []
    for cluster, qualities in sorted(quality_by_cluster.items()):
        avg_quality = sum(qualities) / len(qualities) if qualities else 0
        active = cluster_counts.get(cluster, 0)
        cap = 2 if cluster == "major_liquid" else 1
        status = "blocked" if active > cap else ("review" if active == cap else "ok")
        clusters.append({
            "cluster": cluster,
            "candidate_count": len(qualities),
            "active_positions": active,
            "cluster_cap": cap,
            "avg_quality_score": round(avg_quality, 2),
            "status": status,
        })
    return {
        "status": "review" if any(c["status"] != "ok" for c in clusters) else "ok",
        "clusters": clusters,
        "rules": [
            "Major liquid cluster can carry more exposure than weak alt clusters.",
            "Meme/high-beta cluster is capped aggressively.",
            "Stable/fiat-related clusters are not allocation targets.",
        ],
    }


def build_portfolio_allocation_final(data: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    reserve = build_usdt_reserve_policy(data or {}, settings)
    cluster = build_correlation_cluster_exposure(data or {}, settings)
    rows = [r for r in _models(data or {}) if str(r.get("model_id") or "")]
    eligible = []
    for row in rows:
        score = _safe_float(row.get("final_score") or row.get("score"), 0)
        execution = _safe_float(row.get("execution_quality_score"), 65)
        drawdown = abs(_safe_float(row.get("max_drawdown_percent") or row.get("drawdown"), 0))
        trades = int(_safe_float(row.get("total_trades") or row.get("trade_count"), 0))
        is_eligible = bool(row.get("eligible_for_real", trades >= 5 and score >= 45))
        if not is_eligible:
            continue
        penalty = 0
        if execution < 55:
            penalty += 0.20
        if drawdown > 6:
            penalty += 0.20
        if trades < 10:
            penalty += 0.15
        weight_score = max(0.0, score * (1 - penalty))
        eligible.append({**row, "_weight_score": weight_score, "_allocation_penalty": round(penalty, 3)})
    eligible = sorted(eligible, key=lambda x: x.get("_weight_score", 0), reverse=True)[:5]
    total_weight_score = sum(_safe_float(m.get("_weight_score")) for m in eligible) or 1.0
    deployable = _safe_float(reserve.get("deployable_usdt"), 0)
    if reserve.get("status") == "blocked":
        deployable = 0.0
    allocations = []
    for model in eligible:
        raw_weight = _safe_float(model.get("_weight_score")) / total_weight_score
        capped_weight = min(raw_weight, 0.35)
        suggested = round(deployable * capped_weight, 2)
        allocations.append({
            "model_id": model.get("model_id"),
            "score": round(_safe_float(model.get("score") or model.get("final_score")), 2),
            "weight_percent": round(capped_weight * 100, 2),
            "suggested_usdt": suggested,
            "penalty": model.get("_allocation_penalty"),
            "reason": "score_weighted_usdt_reserve_with_execution_and_drawdown_penalty",
        })
    return {
        "revision": 32,
        "status": "blocked" if reserve.get("status") == "blocked" else ("review" if cluster.get("status") != "ok" else "ok"),
        "capital_usdt": reserve.get("capital_usdt"),
        "reserve_policy": reserve,
        "cluster_exposure": cluster,
        "deployable_usdt": round(deployable, 2),
        "max_model_weight_percent": 35,
        "allocations": allocations,
        "audit_policy": {
            "allocation_is_recommendation_only": True,
            "real_allocation_requires_owner_approval": True,
            "real_order_safety_cannot_be_overridden_by_allocation": True,
        },
    }


def build_allocation_audit_report(data: dict, settings: dict | None = None) -> dict:
    report = build_portfolio_allocation_final(data or {}, settings or {})
    allocation_count = len(report.get("allocations") or [])
    blockers = report.get("reserve_policy", {}).get("blockers") or []
    return {
        "revision": 32,
        "status": "review" if blockers else "ok",
        "allocation_count": allocation_count,
        "deployable_usdt": report.get("deployable_usdt"),
        "reserve_percent": report.get("reserve_policy", {}).get("target_reserve_percent"),
        "blockers": blockers,
        "audit_required_actions": [
            "allocation.preview",
            "allocation.owner_review",
            "real_order.safety_check",
        ],
        "policy": report.get("audit_policy"),
    }

# --- Level1 Rev52 Portfolio Allocation Final ---
def build_portfolio_allocation_schema() -> dict:
    return {
        "revision": 52,
        "status": "ok",
        "schema_version": "portfolio_allocation.v52",
        "read_only": True,
        "blocks": {
            "reserve_policy": ["capital_usdt", "target_reserve_percent", "reserve_usdt", "deployable_usdt", "blockers"],
            "cluster_exposure": ["cluster", "candidate_count", "active_positions", "cluster_cap", "status"],
            "active_risk_budget": ["capital_usdt", "active_usdt", "risk_budget_usdt", "used_risk_percent", "remaining_risk_usdt", "status"],
            "allocation_recommendation": ["decision", "recommended_action", "reason", "allocations", "warnings"],
        },
        "policy": {
            "usdt_reserve_first": True,
            "recommendation_only": True,
            "never_places_order": True,
            "never_unlocks_real_trading": True,
            "never_starts_pilot": True,
        },
    }


def _open_position_notional(position: dict) -> float:
    return max(
        0.0,
        _safe_float(position.get("notional_usdt") or position.get("allocated_usdt") or position.get("amount_usdt") or position.get("quote_order_qty") or position.get("quoteOrderQty"), 0.0),
    )


def build_active_risk_budget(data: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    capital = _capital(settings)
    bot = _bot_settings(settings)
    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    max_slots = int(_safe_float(bot.get("max_open_positions") or bot.get("slots") or 5, 5))
    max_slots = max(1, max_slots)
    per_trade_risk_percent = _safe_float(risk.get("per_trade_risk_percent") or risk.get("risk_per_trade_percent"), 1.0)
    total_budget_percent = _safe_float(risk.get("max_portfolio_risk_percent") or risk.get("portfolio_risk_percent"), min(12.0, max_slots * per_trade_risk_percent))
    total_budget_percent = max(0.0, min(100.0, total_budget_percent))
    positions = (data or {}).get("positions") or (data or {}).get("open_positions") or []
    if not isinstance(positions, list):
        positions = []
    active_usdt = sum(_open_position_notional(p) for p in positions if isinstance(p, dict))
    risk_budget_usdt = round(capital * total_budget_percent / 100.0, 2)
    used_risk_percent = round((active_usdt / risk_budget_usdt * 100.0) if risk_budget_usdt else 0.0, 2)
    remaining = round(max(0.0, risk_budget_usdt - active_usdt), 2)
    warnings = []
    if used_risk_percent >= 100:
        warnings.append("active_risk_budget_exhausted")
    elif used_risk_percent >= 75:
        warnings.append("active_risk_budget_near_limit")
    if len(positions) >= max_slots:
        warnings.append("slot_capacity_full")
    return {
        "revision": 52,
        "status": "blocked" if used_risk_percent >= 100 or len(positions) > max_slots else ("review" if warnings else "ok"),
        "capital_usdt": round(capital, 2),
        "active_usdt": round(active_usdt, 2),
        "risk_budget_percent": round(total_budget_percent, 2),
        "risk_budget_usdt": risk_budget_usdt,
        "used_risk_percent": used_risk_percent,
        "remaining_risk_usdt": remaining,
        "max_slots": max_slots,
        "used_slots": len(positions),
        "warnings": warnings,
        "policy": "Active risk budget is read-only and cannot open or close positions.",
    }


def build_allocation_recommendation_read_only_report(data: dict, settings: dict | None = None) -> dict:
    allocation = build_portfolio_allocation_final(data or {}, settings or {})
    reserve = allocation.get("reserve_policy") or {}
    cluster = allocation.get("cluster_exposure") or {}
    budget = build_active_risk_budget(data or {}, settings or {})
    warnings = []
    for bucket in (reserve.get("blockers") or [], budget.get("warnings") or []):
        if bucket not in warnings:
            warnings.append(bucket)
    if cluster.get("status") != "ok":
        warnings.append("cluster_exposure_review")
    if allocation.get("status") == "blocked" or budget.get("status") == "blocked":
        decision = "WAIT"
        action = "keep_usdt_reserve"
        reason = "Allocation is blocked by reserve/risk safety. No real action is allowed."
    elif warnings:
        decision = "WATCH"
        action = "paper_only_review"
        reason = "Allocation is available for review, but risk/cluster warnings exist."
    else:
        decision = "READY_TO_REVIEW"
        action = "owner_review_only"
        reason = "Portfolio allocation is within read-only policy and can be reviewed."
    return {
        "revision": 52,
        "status": "blocked" if decision == "WAIT" else ("review" if warnings else "ok"),
        "decision": decision,
        "recommended_action": action,
        "reason": reason,
        "read_only": True,
        "reserve_policy": reserve,
        "cluster_exposure": cluster,
        "active_risk_budget": budget,
        "allocations": allocation.get("allocations") or [],
        "warnings": warnings,
        "no_side_effect_policy": {
            "places_order": False,
            "unlocks_real_trading": False,
            "starts_pilot": False,
            "changes_settings": False,
        },
    }


def build_portfolio_visibility_summary(data: dict, settings: dict | None = None) -> dict:
    report = build_allocation_recommendation_read_only_report(data or {}, settings or {})
    reserve = report.get("reserve_policy") or {}
    budget = report.get("active_risk_budget") or {}
    clusters = (report.get("cluster_exposure") or {}).get("clusters") or []
    return {
        "revision": 52,
        "status": report.get("status", "review"),
        "decision": report.get("decision"),
        "recommended_action": report.get("recommended_action"),
        "read_only": True,
        "reserve_percent": reserve.get("target_reserve_percent"),
        "deployable_usdt": reserve.get("deployable_usdt"),
        "risk_used_percent": budget.get("used_risk_percent"),
        "remaining_risk_usdt": budget.get("remaining_risk_usdt"),
        "cluster_review_count": len([c for c in clusters if isinstance(c, dict) and c.get("status") != "ok"]),
        "allocation_count": len(report.get("allocations") or []),
        "warnings": report.get("warnings") or [],
        "summary_cards": {
            "reserve": f"{reserve.get('target_reserve_percent', 0)}%",
            "deployable": reserve.get("deployable_usdt", 0),
            "risk_used": f"{budget.get('used_risk_percent', 0)}%",
            "clusters_to_review": len([c for c in clusters if isinstance(c, dict) and c.get("status") != "ok"]),
        },
    }


def build_level1_52_portfolio_allocation_quality(data: dict, settings: dict | None = None) -> dict:
    schema = build_portfolio_allocation_schema()
    reserve = build_usdt_reserve_policy(data or {}, settings or {})
    cluster = build_correlation_cluster_exposure(data or {}, settings or {})
    budget = build_active_risk_budget(data or {}, settings or {})
    recommendation = build_allocation_recommendation_read_only_report(data or {}, settings or {})
    visibility = build_portfolio_visibility_summary(data or {}, settings or {})
    checks = {
        "schema": schema.get("status") == "ok" and schema.get("read_only") is True,
        "reserve_policy": "target_reserve_percent" in reserve and "deployable_usdt" in reserve,
        "cluster_exposure": isinstance(cluster.get("clusters"), list),
        "active_risk_budget": "used_risk_percent" in budget and "remaining_risk_usdt" in budget,
        "read_only_recommendation": recommendation.get("read_only") is True and recommendation.get("no_side_effect_policy", {}).get("places_order") is False,
        "summary_visibility": visibility.get("read_only") is True and "reserve_percent" in visibility,
    }
    blockers = [name for name, ok in checks.items() if not ok]
    return {
        "revision": 52,
        "status": "ok" if not blockers else "review",
        "checks": checks,
        "blockers": blockers,
        "schema": schema,
        "reserve_policy": reserve,
        "cluster_exposure": cluster,
        "active_risk_budget": budget,
        "recommendation": recommendation,
        "visibility": visibility,
        "required_endpoints": [
            "/api/intelligence/portfolio-allocation-schema-final",
            "/api/intelligence/portfolio-allocation-final",
            "/api/intelligence/usdt-reserve-policy",
            "/api/intelligence/cluster-exposure",
            "/api/intelligence/active-risk-budget",
            "/api/intelligence/allocation-recommendation",
            "/api/intelligence/portfolio-visibility",
            "/api/quality/level1-52/portfolio-allocation",
        ],
        "policy": {"read_only": True, "no_real_trade_side_effects": True},
    }
