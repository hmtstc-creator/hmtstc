from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_order_execution_planner_service import build_autonomous_order_execution_planner


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
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
    raw = settings.get("autonomous_execution_simulator") if isinstance(settings.get("autonomous_execution_simulator"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_simulation_score": _clamp(_safe_float(raw.get("min_simulation_score"), 70.0), 1.0, 100.0),
        "maker_fee_pct": max(0.0, _safe_float(raw.get("maker_fee_pct"), 0.10)),
        "taker_fee_pct": max(0.0, _safe_float(raw.get("taker_fee_pct"), 0.10)),
        "default_spread_pct": max(0.0, _safe_float(raw.get("default_spread_pct"), 0.06)),
        "default_slippage_pct": max(0.0, _safe_float(raw.get("default_slippage_pct"), 0.08)),
        "max_cost_pct": max(0.01, _safe_float(raw.get("max_cost_pct"), 0.35)),
        "max_latency_ms": max(10.0, _safe_float(raw.get("max_latency_ms"), 1200.0)),
        "read_only": True,
        "auto_apply": False,
    }


def _planner(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_order_execution_planner") if isinstance(data.get("autonomous_order_execution_planner"), dict) else None
    return raw or build_autonomous_order_execution_planner(data, settings, auth_store, username)


def _market_context(data: dict, symbol: str | None, policy: dict) -> dict:
    rows = ((data.get("last_scan") or {}).get("scan_rows") if isinstance(data.get("last_scan"), dict) else []) or []
    match = None
    for row in rows:
        if isinstance(row, dict) and row.get("symbol") == symbol:
            match = row
            break
    match = match or {}
    spread_pct = _safe_float(match.get("spread_pct"), policy["default_spread_pct"])
    volatility = _safe_float(match.get("volatility"), 0.0)
    liquidity_score = _safe_float(match.get("liquidity_score"), _safe_float(match.get("score"), 50.0))
    simulated_latency_ms = max(25.0, 250.0 + (volatility * 28.0) + (max(0.0, spread_pct) * 180.0))
    return {
        "symbol": symbol,
        "spread_pct": round(spread_pct, 4),
        "volatility": round(volatility, 4),
        "liquidity_score": round(_clamp(liquidity_score), 2),
        "simulated_latency_ms": round(simulated_latency_ms, 2),
    }


def _estimate(plan: dict, market: dict, policy: dict) -> dict:
    order_plan = plan.get("order_plan") if isinstance(plan.get("order_plan"), dict) else {}
    exchange_payload = order_plan.get("exchange_payload_preview") if isinstance(order_plan.get("exchange_payload_preview"), dict) else {}
    notional = _safe_float(exchange_payload.get("notional_usdt"), 0.0)
    fee_pct = policy["taker_fee_pct"]
    spread_pct = _safe_float(market.get("spread_pct"), policy["default_spread_pct"])
    slippage_pct = policy["default_slippage_pct"] + (_safe_float(market.get("volatility"), 0.0) * 0.008)
    estimated_cost_pct = fee_pct + spread_pct + slippage_pct
    estimated_cost_usdt = notional * estimated_cost_pct / 100.0
    return {
        "notional_usdt": round(notional, 4),
        "fee_pct": round(fee_pct, 4),
        "spread_pct": round(spread_pct, 4),
        "slippage_pct": round(slippage_pct, 4),
        "estimated_cost_pct": round(estimated_cost_pct, 4),
        "estimated_cost_usdt": round(estimated_cost_usdt, 4),
        "expected_fill_type": "SIMULATED_MARKET_FILL" if notional > 0 else "NO_FILL",
        "partial_fill_risk": estimated_cost_pct > (policy["max_cost_pct"] * 0.75) or market.get("liquidity_score", 0) < 45,
    }


def _score(plan: dict, estimate: dict, market: dict, policy: dict, blockers: list[str], warnings: list[str]) -> float:
    score = _safe_float(plan.get("planner_score"), 0.0) * 0.74
    if plan.get("planner_state") == "READY":
        score += 12.0
    else:
        blockers.append("order_plan_not_ready")
    if _safe_float(estimate.get("estimated_cost_pct"), 99.0) <= policy["max_cost_pct"]:
        score += 8.0
    else:
        blockers.append("estimated_execution_cost_too_high")
    if _safe_float(market.get("simulated_latency_ms"), 99999.0) <= policy["max_latency_ms"]:
        score += 4.0
    else:
        warnings.append("simulated_latency_above_policy")
    if _safe_float(market.get("liquidity_score"), 0.0) >= 50.0:
        score += 4.0
    else:
        warnings.append("liquidity_score_weak")
    if estimate.get("partial_fill_risk"):
        warnings.append("partial_fill_risk_detected")
        score -= 5.0
    if blockers:
        score -= min(40.0, len(blockers) * 16.0)
    if warnings:
        score -= min(15.0, len(warnings) * 3.0)
    return round(_clamp(score), 2)


def build_autonomous_execution_simulator(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev80 read-only execution simulator.

    Takes the Rev79 order execution plan and simulates fill cost, slippage,
    fee and latency before any exchange request is allowed. It is a dry-run
    safety layer: no order placement, no runtime write, no exchange request.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    planner = _planner(data, settings, auth_store, username)
    blockers = list(planner.get("blockers") or [])
    warnings = list(planner.get("warnings") or [])

    if not policy["enabled"]:
        blockers.append("execution_simulator_disabled")

    order_plan = planner.get("order_plan") if isinstance(planner.get("order_plan"), dict) else {}
    exchange_payload = order_plan.get("exchange_payload_preview") if isinstance(order_plan.get("exchange_payload_preview"), dict) else {}
    symbol = exchange_payload.get("symbol")
    lane = str(order_plan.get("lane") or "WATCH").upper()
    market = _market_context(data, symbol, policy)
    estimate = _estimate(planner, market, policy)
    simulation_score = _score(planner, estimate, market, policy, blockers, warnings)

    if blockers:
        simulation_state = "BLOCKED"
        simulation_action = "NO_EXECUTION_SIMULATION_APPROVAL"
    elif simulation_score >= policy["min_simulation_score"]:
        simulation_state = "READY"
        simulation_action = f"APPROVE_{lane}_DRY_RUN_PLAN"
    else:
        simulation_state = "REVIEW"
        simulation_action = "REVIEW_EXECUTION_COST_AND_FILL_RISK"

    generated_at = now_iso()
    simulation_id = f"SIM-{generated_at}-{symbol or 'NONE'}-{lane}"
    simulated_fill = {
        "simulation_id": simulation_id,
        "source_plan_id": order_plan.get("plan_id"),
        "lane": lane,
        "symbol": symbol,
        "side": exchange_payload.get("side"),
        "order_type": exchange_payload.get("order_type"),
        "notional_usdt": estimate.get("notional_usdt"),
        "fill_model": estimate.get("expected_fill_type"),
        "cost_model": estimate,
        "market_context": market,
        "approved_for_execution_governor": simulation_state == "READY",
    }

    return {
        "status": "ok" if simulation_state == "READY" else ("blocked" if simulation_state == "BLOCKED" else "review"),
        "revision": 80,
        "engine": "autonomous_execution_simulator",
        "generated_at": generated_at,
        "read_only": True,
        "auto_apply": False,
        "simulation_state": simulation_state,
        "simulation_action": simulation_action,
        "simulation_score": simulation_score,
        "simulated_fill": simulated_fill,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "inputs": {
            "planner_revision": planner.get("revision"),
            "planner_state": planner.get("planner_state"),
            "planner_action": planner.get("planner_action"),
            "planner_score": planner.get("planner_score"),
            "source_plan_id": order_plan.get("plan_id"),
        },
        "policy": policy,
        "command_preview": {
            "type": "execution_simulation_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "simulates_fill_only": True,
            "requires_order_plan": True,
            "source_revision": 80,
            "simulation_state": simulation_state,
            "simulation_action": simulation_action,
            "lane": lane,
            "symbol": symbol,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    fill = payload.get("simulated_fill") if isinstance(payload.get("simulated_fill"), dict) else {}
    cost = fill.get("cost_model") if isinstance(fill.get("cost_model"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 80,
        "engine": "autonomous_execution_simulator_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "simulation_state": payload.get("simulation_state"),
        "simulation_action": payload.get("simulation_action"),
        "simulation_score": payload.get("simulation_score"),
        "lane": fill.get("lane"),
        "symbol": fill.get("symbol"),
        "estimated_cost_pct": cost.get("estimated_cost_pct"),
        "estimated_cost_usdt": cost.get("estimated_cost_usdt"),
        "partial_fill_risk": cost.get("partial_fill_risk"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_execution_simulator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_execution_simulator(data, settings, auth_store, username))


def build_autonomous_execution_simulator_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_execution_simulator(data, settings, auth_store, username)
    summary = _summary_from_payload(payload)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    fill = payload.get("simulated_fill") if isinstance(payload.get("simulated_fill"), dict) else {}
    cost = fill.get("cost_model") if isinstance(fill.get("cost_model"), dict) else {}
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
    checks = {
        "revision_80": payload.get("revision") == 80 and summary.get("revision") == 80,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False and command.get("sends_exchange_request") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "simulation_only": command.get("simulates_fill_only") is True,
        "fill_contract": {"simulation_id", "source_plan_id", "lane", "symbol", "cost_model", "market_context"}.issubset(fill.keys()),
        "cost_contract": {"estimated_cost_pct", "estimated_cost_usdt", "fee_pct", "spread_pct", "slippage_pct"}.issubset(cost.keys()),
        "source_chain_visible": {"planner_revision", "planner_state", "planner_action", "source_plan_id"}.issubset(inputs.keys()),
        "summary_minimal": {"simulation_state", "simulation_action", "estimated_cost_pct", "attention_required"}.issubset(summary.keys()),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "secret_key" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 80,
        "engine": "autonomous_execution_simulator_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "simulation_state": payload.get("simulation_state"),
        "simulation_action": payload.get("simulation_action"),
        "simulation_score": payload.get("simulation_score"),
    }
