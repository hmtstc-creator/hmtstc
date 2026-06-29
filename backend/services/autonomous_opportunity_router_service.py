from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_market_scanner_service import build_autonomous_market_scanner
from services.strategy_selection_engine_service import build_strategy_selection_engine
from services.risk_brain_service import build_risk_brain
from services.autonomous_execution_governor_service import build_autonomous_execution_governor
from services.autonomous_performance_sentinel_service import build_autonomous_performance_sentinel
from services.autonomous_capital_allocator_service import build_autonomous_capital_allocator


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if value is None:
        return fallback
    return bool(value)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_opportunity_router") if isinstance(settings.get("autonomous_opportunity_router"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "max_routes": max(1, min(20, _safe_int(raw.get("max_routes"), 5))),
        "min_route_score": _clamp(_safe_float(raw.get("min_route_score"), 62.0), 1.0, 100.0),
        "min_trade_score": _clamp(_safe_float(raw.get("min_trade_score"), 70.0), 1.0, 100.0),
        "max_spread_pct": _clamp(_safe_float(raw.get("max_spread_pct"), 0.35), 0.01, 5.0),
        "max_volatility_pct": _clamp(_safe_float(raw.get("max_volatility_pct"), 12.0), 0.5, 100.0),
        "prefer_micro_real": _safe_bool(raw.get("prefer_micro_real"), True),
        "read_only": True,
        "auto_apply": False,
    }


def _candidate_symbol(candidate: dict) -> str:
    return str(candidate.get("symbol") or candidate.get("pair") or "").upper().strip()


def _strategy_for_symbol(strategy_payload: dict, symbol: str, fallback: str) -> str:
    ranked = strategy_payload.get("ranked_strategies") or strategy_payload.get("strategy_candidates") or []
    if isinstance(ranked, list):
        for item in ranked:
            if isinstance(item, dict) and str(item.get("symbol") or "").upper() == symbol and item.get("strategy"):
                return str(item.get("strategy"))
    selected = strategy_payload.get("selected_strategy") or strategy_payload.get("primary_strategy")
    return str(selected or fallback or "micro_scalp_watch")


def _strategy_confidence(strategy_payload: dict) -> float:
    return _clamp(_safe_float(strategy_payload.get("confidence") or strategy_payload.get("strategy_confidence"), 0.0))


def _route_score(candidate: dict, strategy_confidence: float, risk: dict, capital: dict, performance: dict, execution: dict, policy: dict) -> tuple[float, list[str]]:
    reasons: list[str] = []
    base = _safe_float(candidate.get("priority_score") or candidate.get("source_score") or candidate.get("score"), 0.0)
    spread = _safe_float(candidate.get("spread_pct") or candidate.get("spread"), 0.0)
    volatility = _safe_float(candidate.get("volatility") or candidate.get("volatility_pct"), 0.0)
    risk_score = _safe_float(risk.get("risk_score") or risk.get("confidence") or risk.get("budget_score"), 55.0)
    allocation_state = str(capital.get("allocation_state") or "UNKNOWN").upper()
    performance_state = str(performance.get("performance_state") or performance.get("recommended_action") or "WATCH").upper()
    execution_state = str(execution.get("execution_state") or "blocked").lower()

    score = base * 0.48 + strategy_confidence * 0.18 + risk_score * 0.14
    score += 10.0 if allocation_state in {"READY", "ALLOCATABLE", "NORMAL", "OK"} else 0.0
    score += 8.0 if performance_state in {"CONTINUE", "LOCK_PROFIT", "WATCH"} else -10.0
    score += 6.0 if execution_state in {"ready", "paper_ready"} else -8.0
    score -= max(spread - 0.10, 0.0) * 22.0
    score -= max(volatility - 6.0, 0.0) * 1.35

    if spread > policy["max_spread_pct"]:
        reasons.append("spread_above_router_limit")
    if volatility > policy["max_volatility_pct"]:
        reasons.append("volatility_above_router_limit")
    if not candidate.get("eligible", True):
        reasons.append("scanner_candidate_not_eligible")
    if allocation_state == "BLOCKED":
        reasons.append("capital_allocator_blocked")
    if performance_state in {"COOLDOWN", "STOP_AND_PROTECT"}:
        reasons.append("performance_sentinel_blocks_new_route")
    if execution.get("status") == "blocked" and execution.get("execution_lane") not in {"paper", None}:
        reasons.append("execution_governor_blocked")
    return round(_clamp(score), 2), sorted(set(reasons))


def _route_state(routes: list[dict], blockers: set[str], warnings: set[str], policy: dict) -> str:
    if not policy["enabled"]:
        return "DISABLED"
    if blockers:
        return "BLOCKED"
    if not routes:
        return "WAIT"
    top = routes[0]
    if top.get("route_score", 0.0) >= policy["min_trade_score"] and top.get("route_action") in {"PAPER_ROUTE", "MICRO_REAL_ROUTE", "REAL_ROUTE"}:
        return "ROUTE_READY"
    if warnings:
        return "WATCH"
    return "WATCH"


def build_autonomous_opportunity_router(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev76 read-only opportunity router.

    Turns scanner candidates into a ranked route queue by combining market quality,
    strategy selection, risk brain, capital allocation, execution governor and
    performance sentinel. It never places orders and never writes runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    scanner = build_autonomous_market_scanner(data, settings)
    strategy = build_strategy_selection_engine(data, settings)
    risk = build_risk_brain(data, settings)
    capital = build_autonomous_capital_allocator(data, settings, auth_store, username)
    execution = build_autonomous_execution_governor(data, settings, auth_store, username)
    performance = build_autonomous_performance_sentinel(data, settings, auth_store, username)

    blockers = set(scanner.get("blockers") or [])
    warnings = set(scanner.get("warnings") or [])
    if not policy["enabled"]:
        blockers.add("opportunity_router_disabled")
    if performance.get("performance_state") in {"COOLDOWN", "STOP_AND_PROTECT"}:
        blockers.add("performance_sentinel_blocks_new_entries")
    if capital.get("allocation_state") == "BLOCKED":
        blockers.add("capital_allocator_blocked")
    if execution.get("execution_state") == "blocked" and execution.get("execution_lane") not in {"paper", "none"}:
        blockers.add("execution_governor_blocked")

    candidates = scanner.get("best_symbols") if isinstance(scanner.get("best_symbols"), list) else []
    strategy_confidence = _strategy_confidence(strategy)
    routes: list[dict] = []
    execution_lane = str(execution.get("execution_lane") or "none")
    for index, candidate in enumerate(candidates[: policy["max_routes"] * 2], start=1):
        if not isinstance(candidate, dict):
            continue
        symbol = _candidate_symbol(candidate)
        score, route_reasons = _route_score(candidate, strategy_confidence, risk, capital, performance, execution, policy)
        if score < policy["min_route_score"]:
            route_reasons.append("route_score_below_threshold")
        strategy_name = _strategy_for_symbol(strategy, symbol, candidate.get("strategy_hint"))
        if blockers or route_reasons:
            action = "SKIP_ROUTE" if blockers else "WATCH_ROUTE"
        elif execution_lane == "paper":
            action = "PAPER_ROUTE"
        elif execution_lane == "micro_real":
            action = "MICRO_REAL_ROUTE"
        elif execution_lane == "real":
            action = "REAL_ROUTE"
        else:
            action = "WATCH_ROUTE"
        routes.append({
            "rank": index,
            "symbol": symbol or "-",
            "strategy": strategy_name,
            "route_score": score,
            "route_action": action,
            "execution_lane": execution_lane,
            "suggested_notional_usdt": execution.get("suggested_order_usdt", 0.0) if action in {"MICRO_REAL_ROUTE", "REAL_ROUTE"} else 0.0,
            "source_score": candidate.get("source_score"),
            "spread_pct": candidate.get("spread_pct"),
            "volatility": candidate.get("volatility"),
            "reasons": sorted(set(route_reasons)) if route_reasons else ["route_candidate_ready"],
        })
    routes = sorted(routes, key=lambda item: item["route_score"], reverse=True)[: policy["max_routes"]]
    state = _route_state(routes, blockers, warnings, policy)
    status = "ok" if state == "ROUTE_READY" else ("blocked" if state == "BLOCKED" else "review")
    primary = routes[0] if routes else {}
    return {
        "status": status,
        "revision": 76,
        "engine": "autonomous_opportunity_router",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "route_state": state,
        "primary_symbol": primary.get("symbol"),
        "primary_strategy": primary.get("strategy"),
        "primary_action": primary.get("route_action", "WAIT"),
        "route_count": len(routes),
        "routes": routes,
        "blockers": sorted(blockers),
        "warnings": sorted(warnings)[:10],
        "inputs": {
            "scanner_revision": scanner.get("revision"),
            "strategy_revision": strategy.get("revision"),
            "risk_revision": risk.get("revision"),
            "capital_revision": capital.get("revision"),
            "execution_revision": execution.get("revision"),
            "performance_revision": performance.get("revision"),
            "execution_lane": execution.get("execution_lane"),
            "performance_state": performance.get("performance_state"),
            "allocation_state": capital.get("allocation_state"),
        },
        "policy": policy,
        "command_preview": {
            "type": "opportunity_route_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "writes_runtime_state": False,
            "requires_execution_governor": True,
            "source_revision": 76,
            "action": primary.get("route_action", "WAIT"),
            "symbol": primary.get("symbol"),
            "strategy": primary.get("strategy"),
        },
    }


def build_summary_autonomous_opportunity_router(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_opportunity_router(data, settings, auth_store, username)
    return {
        "status": payload.get("status"),
        "revision": 76,
        "engine": "autonomous_opportunity_router_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "route_state": payload.get("route_state"),
        "primary_symbol": payload.get("primary_symbol"),
        "primary_strategy": payload.get("primary_strategy"),
        "primary_action": payload.get("primary_action"),
        "route_count": payload.get("route_count", 0),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_autonomous_opportunity_router_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_opportunity_router(data, settings, auth_store, username)
    summary = build_summary_autonomous_opportunity_router(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    checks = {
        "revision_76": payload.get("revision") == 76 and summary.get("revision") == 76,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "source_chain_visible": {"scanner_revision", "strategy_revision", "risk_revision", "capital_revision", "execution_revision", "performance_revision"}.issubset(inputs.keys()),
        "route_contract": isinstance(payload.get("routes"), list) and all({"symbol", "strategy", "route_score", "route_action"}.issubset(route.keys()) for route in payload.get("routes", [])),
        "summary_minimal": {"route_state", "primary_symbol", "primary_action", "attention_required"}.issubset(summary.keys()),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "signed_payload" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 76,
        "engine": "autonomous_opportunity_router_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "route_state": payload.get("route_state"),
        "route_count": payload.get("route_count", 0),
    }
