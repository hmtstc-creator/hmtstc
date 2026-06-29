"""Rev936-940 Strategy & Filter Live Calibration service.

This module is intentionally network-free. It calibrates the existing three
filter / five strategy contracts from payload or safe deterministic defaults,
so production can review live-market readiness without opening a Binance order
or leaking credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FILTER_NAMES = (
    "liquidity_spread_intelligence",
    "choch_imbalance_reliability",
    "cost_adjusted_expectancy",
)

STRATEGY_NAMES = (
    "choch_micro_scalper",
    "imbalance_fill_hunter",
    "liquidity_sweep_reversal",
    "volatility_compression_breakout",
    "mean_reversion_micro_recovery",
)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _bounded(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, float(value))), 4)


def _payload_market(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "symbol": str(payload.get("symbol") or "BTCUSDT"),
        "spread_bps": _num(payload.get("spread_bps"), 3.2),
        "depth_usdt": _num(payload.get("depth_usdt"), 85000),
        "slippage_bps": _num(payload.get("slippage_bps"), 2.8),
        "latency_ms": _num(payload.get("latency_ms"), 180),
        "fee_rate_percent": _num(payload.get("fee_rate_percent"), 0.1),
        "platform_commission_percent": _num(payload.get("platform_commission_percent"), 0.1),
        "choch_score": _num(payload.get("choch_score"), 78),
        "imbalance_fill_probability": _num(payload.get("imbalance_fill_probability"), 0.68),
        "fake_breakout_risk": _num(payload.get("fake_breakout_risk"), 0.18),
        "expected_gross_edge_bps": _num(payload.get("expected_gross_edge_bps"), 22),
        "win_rate_estimate": _num(payload.get("win_rate_estimate"), 0.58),
        "avg_win_bps": _num(payload.get("avg_win_bps"), 18),
        "avg_loss_bps": _num(payload.get("avg_loss_bps"), 11),
    }


def calibrate_liquidity_spread_filter(market: dict[str, Any]) -> dict[str, Any]:
    spread_penalty = _num(market["spread_bps"]) * 4.5
    slippage_penalty = _num(market["slippage_bps"]) * 5.0
    depth_score = _bounded(_num(market["depth_usdt"]) / 1200)
    score = _bounded(100 - spread_penalty - slippage_penalty + depth_score * 0.18)
    decision = "PASS" if score >= 70 else "REVIEW" if score >= 55 else "BLOCK"
    return {
        "name": "liquidity_spread_intelligence",
        "score": score,
        "decision": decision,
        "spread_bps": market["spread_bps"],
        "slippage_bps": market["slippage_bps"],
        "depth_usdt": market["depth_usdt"],
        "calibrated_max_spread_bps": round(max(2.0, min(8.0, _num(market["spread_bps"]) * 1.35)), 4),
        "calibrated_max_slippage_bps": round(max(2.0, min(7.5, _num(market["slippage_bps"]) * 1.4)), 4),
    }


def calibrate_choch_imbalance_filter(market: dict[str, Any]) -> dict[str, Any]:
    choch_score = _num(market["choch_score"])
    fill_score = _num(market["imbalance_fill_probability"]) * 100
    fake_penalty = _num(market["fake_breakout_risk"]) * 100 * 0.55
    score = _bounded(choch_score * 0.52 + fill_score * 0.48 - fake_penalty)
    decision = "PASS" if score >= 68 else "REVIEW" if score >= 52 else "BLOCK"
    return {
        "name": "choch_imbalance_reliability",
        "score": score,
        "decision": decision,
        "choch_score": choch_score,
        "imbalance_fill_probability": market["imbalance_fill_probability"],
        "fake_breakout_risk": market["fake_breakout_risk"],
        "calibrated_min_choch_score": 72,
        "calibrated_min_fill_probability": 0.62,
    }


def calibrate_cost_expectancy_filter(market: dict[str, Any]) -> dict[str, Any]:
    total_cost_bps = (_num(market["fee_rate_percent"]) + _num(market["platform_commission_percent"])) * 100
    total_cost_bps += _num(market["spread_bps"]) + _num(market["slippage_bps"])
    raw_expectancy_bps = (_num(market["win_rate_estimate"]) * _num(market["avg_win_bps"])) - ((1 - _num(market["win_rate_estimate"])) * _num(market["avg_loss_bps"]))
    net_expectancy_bps = raw_expectancy_bps - total_cost_bps
    score = _bounded(50 + net_expectancy_bps * 2.4 - _num(market["latency_ms"]) / 45)
    decision = "PASS" if net_expectancy_bps >= 2.5 and score >= 62 else "REVIEW" if net_expectancy_bps > -2 else "BLOCK"
    return {
        "name": "cost_adjusted_expectancy",
        "score": score,
        "decision": decision,
        "raw_expectancy_bps": round(raw_expectancy_bps, 4),
        "estimated_total_cost_bps": round(total_cost_bps, 4),
        "net_expectancy_bps": round(net_expectancy_bps, 4),
        "latency_ms": market["latency_ms"],
        "calibrated_min_net_expectancy_bps": 2.5,
    }


def calibrate_strategy_parameters(market: dict[str, Any]) -> list[dict[str, Any]]:
    base_cost = calibrate_cost_expectancy_filter(market)
    structure = calibrate_choch_imbalance_filter(market)
    liquidity = calibrate_liquidity_spread_filter(market)
    profile = {
        "choch_micro_scalper": (structure["score"] * 0.48 + liquidity["score"] * 0.24 + base_cost["score"] * 0.28, 0.18, 0.10),
        "imbalance_fill_hunter": (structure["score"] * 0.43 + base_cost["score"] * 0.34 + liquidity["score"] * 0.23, 0.22, 0.12),
        "liquidity_sweep_reversal": (structure["score"] * 0.38 + liquidity["score"] * 0.34 + base_cost["score"] * 0.28, 0.16, 0.09),
        "volatility_compression_breakout": (liquidity["score"] * 0.45 + base_cost["score"] * 0.36 + structure["score"] * 0.19, 0.24, 0.13),
        "mean_reversion_micro_recovery": (base_cost["score"] * 0.42 + liquidity["score"] * 0.31 + structure["score"] * 0.27, 0.14, 0.08),
    }
    rows = []
    for name, (score, tp, sl) in profile.items():
        score = _bounded(score)
        rows.append({
            "name": name,
            "score": score,
            "decision": "ACTIVE_CANDIDATE" if score >= 70 else "REVIEW" if score >= 55 else "QUARANTINE_PREVIEW",
            "calibrated_take_profit_percent": round(tp, 4),
            "calibrated_stop_loss_percent": round(sl, 4),
            "max_signal_age_ms": int(max(250, 1500 - _num(market["latency_ms"]) * 2.2)),
            "cost_adjusted": True,
        })
    return rows


def build_strategy_filter_live_calibration(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    market = _payload_market(payload)
    filters = [
        calibrate_liquidity_spread_filter(market),
        calibrate_choch_imbalance_filter(market),
        calibrate_cost_expectancy_filter(market),
    ]
    strategies = calibrate_strategy_parameters(market)
    blockers = [f"filter_blocked:{item['name']}" for item in filters if item["decision"] == "BLOCK"]
    blockers += [f"strategy_quarantine:{item['name']}" for item in strategies if item["decision"] == "QUARANTINE_PREVIEW"]
    avg_filter = round(sum(item["score"] for item in filters) / len(filters), 4)
    avg_strategy = round(sum(item["score"] for item in strategies) / len(strategies), 4)
    if blockers:
        decision = "CALIBRATION_BLOCKED"
    elif avg_filter >= 68 and avg_strategy >= 66:
        decision = "CALIBRATION_READY"
    else:
        decision = "CALIBRATION_REVIEW"
    return {
        "status": "ok",
        "revision": 940,
        "decision": decision,
        "symbol": market["symbol"],
        "filters": filters,
        "strategies": strategies,
        "average_filter_score": avg_filter,
        "average_strategy_score": avg_strategy,
        "critical_blocker": blockers[0] if blockers else "none",
        "blockers": blockers,
        "operator_action": "Review blocked filters/strategies before live activation." if blockers else "Use calibrated thresholds in dry-run first.",
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_apply_default_off": True,
        "auto_scale_default_off": True,
        "real_network_call_performed": False,
        "secret_values_returned": False,
    }


def build_strategy_filter_live_calibration_summary() -> dict[str, Any]:
    result = build_strategy_filter_live_calibration()
    return {
        "status": "ok",
        "revision": 940,
        "decision": result["decision"],
        "symbol": result["symbol"],
        "average_filter_score": result["average_filter_score"],
        "average_strategy_score": result["average_strategy_score"],
        "filters_ready": sum(1 for f in result["filters"] if f["decision"] == "PASS"),
        "filters_total": len(result["filters"]),
        "strategies_active_candidates": sum(1 for s in result["strategies"] if s["decision"] == "ACTIVE_CANDIDATE"),
        "strategies_total": len(result["strategies"]),
        "critical_blocker": result["critical_blocker"],
        "operator_action": result["operator_action"],
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_apply_default_off": True,
        "secret_values_returned": False,
    }
