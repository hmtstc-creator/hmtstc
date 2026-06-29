"""Rev941-945 High-Frequency Safety Capacity service.

Network-free dry-run capacity model for the 1000 trades/day target. The service
combines trade cadence, Binance-style request budget, fee/commission burden,
overtrade pressure and quality constraints. It never submits or closes real
orders; it produces a reviewable decision contract for production operators.
"""
from __future__ import annotations

from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _bounded(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, float(value))), 4)


def _payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "target_trades_per_day": _int(payload.get("target_trades_per_day"), 1000),
        "symbols_scanned": _int(payload.get("symbols_scanned"), 40),
        "scan_interval_seconds": _num(payload.get("scan_interval_seconds"), 8),
        "avg_requests_per_trade": _num(payload.get("avg_requests_per_trade"), 5),
        "daily_request_budget": _int(payload.get("daily_request_budget"), 90000),
        "quality_acceptance_rate": _num(payload.get("quality_acceptance_rate"), 0.08),
        "expected_gross_edge_bps": _num(payload.get("expected_gross_edge_bps"), 24),
        "avg_spread_bps": _num(payload.get("avg_spread_bps"), 2.6),
        "avg_slippage_bps": _num(payload.get("avg_slippage_bps"), 2.4),
        "binance_fee_percent": _num(payload.get("binance_fee_percent"), 0.1),
        "platform_commission_percent": _num(payload.get("platform_commission_percent"), 0.1),
        "max_loss_streak": _int(payload.get("max_loss_streak"), 3),
        "loss_streak_observed": _int(payload.get("loss_streak_observed"), 1),
        "risk_halt_events": _int(payload.get("risk_halt_events"), 0),
        "latency_ms": _num(payload.get("latency_ms"), 170),
        "avg_trade_notional_usdt": _num(payload.get("avg_trade_notional_usdt"), 25),
    }


def build_capacity_simulation(model: dict[str, Any]) -> dict[str, Any]:
    scans_per_day = 86400 / max(1.0, _num(model["scan_interval_seconds"], 8))
    raw_opportunities = scans_per_day * max(1, _int(model["symbols_scanned"], 1))
    quality_accepted = int(raw_opportunities * max(0.0, min(1.0, _num(model["quality_acceptance_rate"], 0.0))))
    target = _int(model["target_trades_per_day"], 1000)
    realistic_capacity = min(target, quality_accepted)
    utilization = realistic_capacity / max(1, target)
    score = _bounded(utilization * 100 - max(0, target - quality_accepted) / max(1, target) * 35)
    return {
        "target_trades_per_day": target,
        "raw_opportunities_per_day": int(raw_opportunities),
        "quality_accepted_candidates": quality_accepted,
        "realistic_trade_capacity": int(realistic_capacity),
        "capacity_utilization_percent": round(utilization * 100, 4),
        "capacity_score": score,
        "decision": "CAPACITY_READY" if score >= 80 else "CAPACITY_REVIEW" if score >= 55 else "CAPACITY_BLOCKED",
    }


def build_rate_limit_budget(model: dict[str, Any], capacity: dict[str, Any]) -> dict[str, Any]:
    request_load = int(capacity["realistic_trade_capacity"] * _num(model["avg_requests_per_trade"], 5))
    scan_load = int((86400 / max(1.0, _num(model["scan_interval_seconds"], 8))) * 0.6)
    total_load = request_load + scan_load
    budget = max(1, _int(model["daily_request_budget"], 1))
    usage = total_load / budget
    score = _bounded(100 - max(0.0, usage - 0.65) * 170)
    return {
        "daily_request_budget": budget,
        "estimated_trade_request_load": request_load,
        "estimated_scan_request_load": scan_load,
        "estimated_total_request_load": total_load,
        "budget_usage_percent": round(usage * 100, 4),
        "rate_limit_score": score,
        "decision": "RATE_LIMIT_READY" if usage <= 0.75 else "RATE_LIMIT_REVIEW" if usage <= 0.92 else "RATE_LIMIT_BLOCKED",
    }


def build_fee_burden(model: dict[str, Any]) -> dict[str, Any]:
    fee_bps = (_num(model["binance_fee_percent"], 0.1) + _num(model["platform_commission_percent"], 0.1)) * 100
    market_cost_bps = _num(model["avg_spread_bps"], 0) + _num(model["avg_slippage_bps"], 0)
    total_cost_bps = fee_bps + market_cost_bps
    net_edge_bps = _num(model["expected_gross_edge_bps"], 0) - total_cost_bps
    daily_notional = _num(model["avg_trade_notional_usdt"], 0) * _int(model["target_trades_per_day"], 0)
    daily_cost_usdt = round(daily_notional * total_cost_bps / 10000, 6)
    score = _bounded(50 + net_edge_bps * 3.2 - max(0, _num(model["latency_ms"], 0) - 250) / 35)
    return {
        "expected_gross_edge_bps": model["expected_gross_edge_bps"],
        "estimated_total_cost_bps": round(total_cost_bps, 4),
        "net_edge_after_fee_bps": round(net_edge_bps, 4),
        "estimated_daily_notional_usdt": round(daily_notional, 4),
        "estimated_daily_cost_usdt": daily_cost_usdt,
        "fee_burden_score": score,
        "decision": "FEE_BURDEN_READY" if net_edge_bps >= 2.5 and score >= 60 else "FEE_BURDEN_REVIEW" if net_edge_bps >= -2 else "FEE_BURDEN_BLOCKED",
    }


def build_overtrade_stress(model: dict[str, Any], capacity: dict[str, Any], fee: dict[str, Any]) -> dict[str, Any]:
    loss_ratio = _int(model["loss_streak_observed"], 0) / max(1, _int(model["max_loss_streak"], 1))
    halt_penalty = _int(model["risk_halt_events"], 0) * 18
    utilization = _num(capacity["capacity_utilization_percent"], 0) / 100
    fee_drag = max(0.0, -_num(fee["net_edge_after_fee_bps"], 0)) * 6
    score = _bounded(100 - loss_ratio * 38 - halt_penalty - max(0, utilization - 0.86) * 45 - fee_drag)
    if score < 45 or _int(model["risk_halt_events"], 0) >= 2:
        decision = "OVERTRADE_BLOCKED"
    elif score < 68 or loss_ratio >= 0.75:
        decision = "OVERTRADE_REVIEW"
    else:
        decision = "OVERTRADE_SAFE"
    return {
        "loss_streak_observed": model["loss_streak_observed"],
        "max_loss_streak": model["max_loss_streak"],
        "risk_halt_events": model["risk_halt_events"],
        "capacity_utilization_percent": capacity["capacity_utilization_percent"],
        "overtrade_score": score,
        "decision": decision,
    }


def build_high_frequency_safety_capacity(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    model = _payload(payload)
    capacity = build_capacity_simulation(model)
    rate_limit = build_rate_limit_budget(model, capacity)
    fee = build_fee_burden(model)
    overtrade = build_overtrade_stress(model, capacity, fee)
    blockers = []
    for prefix, row in (("capacity", capacity), ("rate_limit", rate_limit), ("fee", fee), ("overtrade", overtrade)):
        if str(row["decision"]).endswith("BLOCKED"):
            blockers.append(f"{prefix}:{row['decision']}")
    average_score = round((capacity["capacity_score"] + rate_limit["rate_limit_score"] + fee["fee_burden_score"] + overtrade["overtrade_score"]) / 4, 4)
    if blockers:
        decision = "HF_CAPACITY_BLOCKED"
    elif average_score >= 72 and overtrade["decision"] == "OVERTRADE_SAFE":
        decision = "HF_CAPACITY_READY"
    else:
        decision = "HF_CAPACITY_REVIEW"
    return {
        "status": "ok",
        "revision": 945,
        "decision": decision,
        "average_score": average_score,
        "critical_blocker": blockers[0] if blockers else "none",
        "blockers": blockers,
        "capacity_simulation": capacity,
        "rate_limit_budget": rate_limit,
        "fee_commission_burden": fee,
        "overtrade_firewall_stress": overtrade,
        "operator_action": "Reduce target cadence or improve net edge before live usage." if blockers else "Run dry-run only; do not enable real submit from capacity alone.",
        "target_trades_per_day": model["target_trades_per_day"],
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_apply_default_off": True,
        "auto_scale_default_off": True,
        "real_network_call_performed": False,
        "secret_values_returned": False,
    }


def build_high_frequency_safety_capacity_summary() -> dict[str, Any]:
    result = build_high_frequency_safety_capacity()
    cap = result["capacity_simulation"]
    rate = result["rate_limit_budget"]
    fee = result["fee_commission_burden"]
    over = result["overtrade_firewall_stress"]
    return {
        "status": "ok",
        "revision": 945,
        "decision": result["decision"],
        "average_score": result["average_score"],
        "target_trades_per_day": result["target_trades_per_day"],
        "realistic_trade_capacity": cap["realistic_trade_capacity"],
        "capacity_score": cap["capacity_score"],
        "rate_limit_score": rate["rate_limit_score"],
        "budget_usage_percent": rate["budget_usage_percent"],
        "fee_burden_score": fee["fee_burden_score"],
        "net_edge_after_fee_bps": fee["net_edge_after_fee_bps"],
        "overtrade_score": over["overtrade_score"],
        "critical_blocker": result["critical_blocker"],
        "operator_action": result["operator_action"],
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_apply_default_off": True,
        "secret_values_returned": False,
    }
