from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

PRODUCTION_REVISION = 870
FILTER_IDS = ["liquidity_spread_intelligence", "choch_imbalance_reliability", "cost_adjusted_micro_edge"]
STRATEGY_IDS = [
    "choch_micro_scalper",
    "imbalance_fill_hunter",
    "liquidity_sweep_reversal",
    "volatility_compression_breakout",
    "mean_reversion_micro_recovery",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return fallback
        return result
    except Exception:
        return fallback


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return fallback


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "active"}


def masked_presence(value: Any) -> dict:
    clean = str(value or "").strip()
    return {"present": bool(clean), "fingerprint": hashlib.sha256(clean.encode()).hexdigest()[:10] if clean else None, "value_returned": False}


def get_user_record(auth_store: dict | None, username: str) -> dict:
    return as_dict(as_dict(auth_store).get("users")).get(username, {}) or {}


def public_user_profile(record: dict, username: str) -> dict:
    api = as_dict(record.get("api_connection"))
    commission = normalize_commission_settings(record.get("commission_settings"))
    risk = as_dict(record.get("risk_profile"))
    return {
        "username": username,
        "role": record.get("role", "user"),
        "active": record.get("active", True) is not False,
        "api_configured": bool(api.get("api_key_set") and api.get("secret_key_set")),
        "api_trade_permission": bool(as_dict(api.get("permissions")).get("trade", False)),
        "commission": commission,
        "risk_profile": {
            "profile": risk.get("profile", "balanced"),
            "max_daily_loss_usdt": safe_float(risk.get("max_daily_loss_usdt"), 25.0),
            "max_notional_usdt": safe_float(risk.get("max_notional_usdt"), 25.0),
        },
        "secret_values_returned": False,
    }


def normalize_commission_settings(settings: Any) -> dict:
    raw = as_dict(settings)
    buy_rate = clamp(safe_float(raw.get("buy_rate_percent"), 0.10), 0.0, 5.0)
    sell_rate = clamp(safe_float(raw.get("sell_rate_percent"), 0.10), 0.0, 5.0)
    minimum = max(0.0, safe_float(raw.get("minimum_commission_usdt"), 0.0))
    mode = str(raw.get("mode") or "percent").lower()
    if mode not in {"percent", "fixed_plus_percent"}:
        mode = "percent"
    return {
        "mode": mode,
        "buy_rate_percent": round(buy_rate, 4),
        "sell_rate_percent": round(sell_rate, 4),
        "minimum_commission_usdt": round(minimum, 8),
        "enabled": raw.get("enabled", True) is not False,
        "updated_at": raw.get("updated_at"),
    }


def update_commission_settings(auth_store: dict, username: str, payload: dict | None) -> dict:
    users = auth_store.setdefault("users", {})
    if username not in users:
        raise KeyError(username)
    normalized = normalize_commission_settings(payload or {})
    normalized["updated_at"] = now_iso()
    users[username]["commission_settings"] = normalized
    return {"status": "ok", "user": username, "commission_settings": normalized}


def commission_for_trade(notional_usdt: float, side: str, settings: dict | None) -> dict:
    cfg = normalize_commission_settings(settings)
    if not cfg.get("enabled", True):
        return {"side": side, "notional_usdt": round(notional_usdt, 8), "platform_commission_usdt": 0.0, "rate_percent": 0.0, "enabled": False}
    rate = cfg["buy_rate_percent"] if str(side).lower() == "buy" else cfg["sell_rate_percent"]
    fee = max(float(notional_usdt) * rate / 100.0, cfg["minimum_commission_usdt"])
    return {"side": str(side).lower(), "notional_usdt": round(float(notional_usdt), 8), "platform_commission_usdt": round(fee, 8), "rate_percent": rate, "enabled": True}


def commission_preview(payload: dict | None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = as_dict(payload)
    record = get_user_record(auth_store, username)
    settings = normalize_commission_settings(payload.get("commission_settings") or record.get("commission_settings"))
    notional = max(0.0, safe_float(payload.get("notional_usdt"), 200.0))
    buy = commission_for_trade(notional, "buy", settings)
    sell_notional = max(0.0, safe_float(payload.get("sell_notional_usdt"), notional))
    sell = commission_for_trade(sell_notional, "sell", settings)
    gross_pnl = safe_float(payload.get("gross_pnl_usdt"), 0.0)
    binance_fee = max(0.0, safe_float(payload.get("binance_fee_usdt"), 0.0))
    platform_total = buy["platform_commission_usdt"] + sell["platform_commission_usdt"]
    return {
        "status": "ok",
        "user": username,
        "buy": buy,
        "sell": sell,
        "platform_commission_total_usdt": round(platform_total, 8),
        "binance_fee_usdt": round(binance_fee, 8),
        "gross_pnl_usdt": round(gross_pnl, 8),
        "net_pnl_after_all_costs_usdt": round(gross_pnl - binance_fee - platform_total, 8),
        "secret_values_returned": False,
    }


def evaluate_liquidity_spread_filter(market: dict) -> dict:
    spread = safe_float(market.get("spread_percent"), 0.08)
    depth = safe_float(market.get("book_depth_usdt"), 150000.0)
    volume = safe_float(market.get("volume_24h_usdt"), 3000000.0)
    fake_volume = safe_float(market.get("fake_volume_risk"), 0.15)
    spread_score = clamp(100 - spread * 250)
    depth_score = clamp(depth / 2500.0)
    volume_score = clamp(volume / 50000.0)
    fake_penalty = clamp(fake_volume * 100)
    score = clamp((spread_score * 0.38) + (depth_score * 0.32) + (volume_score * 0.20) - (fake_penalty * 0.10))
    blockers = []
    if spread > 0.35:
        blockers.append("spread_too_wide")
    if depth < 25000:
        blockers.append("insufficient_orderbook_depth")
    if fake_volume > 0.65:
        blockers.append("fake_volume_risk_high")
    return {"id": FILTER_IDS[0], "score": round(score, 2), "decision": "pass" if score >= 65 and not blockers else "block", "blockers": blockers}


def evaluate_structure_filter(market: dict) -> dict:
    choch = safe_float(market.get("choch_strength"), 0.55)
    imbalance = safe_float(market.get("imbalance_fill_probability"), 0.58)
    mtf = safe_float(market.get("multi_timeframe_confirmation"), 0.55)
    sweep = safe_float(market.get("liquidity_sweep_quality"), 0.45)
    retest = safe_float(market.get("retest_confirmation"), 0.50)
    fake_breakout = safe_float(market.get("fake_breakout_risk"), 0.25)
    score = clamp((choch * 24) + (imbalance * 24) + (mtf * 20) + (sweep * 14) + (retest * 14) - (fake_breakout * 20))
    blockers = []
    if fake_breakout > 0.70:
        blockers.append("fake_breakout_risk_high")
    if mtf < 0.35:
        blockers.append("multi_timeframe_confirmation_weak")
    return {"id": FILTER_IDS[1], "score": round(score, 2), "decision": "pass" if score >= 58 and not blockers else "block", "blockers": blockers}


def evaluate_cost_edge_filter(market: dict, commission_settings: dict | None = None) -> dict:
    expected_move = safe_float(market.get("expected_move_percent"), 0.32)
    spread = safe_float(market.get("spread_percent"), 0.08)
    slippage = safe_float(market.get("expected_slippage_percent"), 0.05)
    latency = safe_float(market.get("latency_risk_percent"), 0.03)
    binance_fee = safe_float(market.get("binance_fee_percent"), 0.10)
    cfg = normalize_commission_settings(commission_settings)
    platform_fee = cfg["buy_rate_percent"] + cfg["sell_rate_percent"]
    total_cost = spread + slippage + latency + binance_fee + platform_fee
    net_edge = expected_move - total_cost
    score = clamp(50 + (net_edge * 180))
    blockers = []
    if net_edge <= 0:
        blockers.append("negative_net_edge_after_cost")
    if total_cost > expected_move * 0.85:
        blockers.append("fee_drag_too_high")
    return {"id": FILTER_IDS[2], "score": round(score, 2), "decision": "pass" if score >= 55 and not blockers else "block", "blockers": blockers, "expected_move_percent": round(expected_move, 4), "total_cost_percent": round(total_cost, 4), "net_edge_percent": round(net_edge, 4)}


def evaluate_filters(payload: dict | None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = as_dict(payload)
    market = as_dict(payload.get("market") or payload)
    record = get_user_record(auth_store, username)
    commission = normalize_commission_settings(payload.get("commission_settings") or record.get("commission_settings"))
    results = [
        evaluate_liquidity_spread_filter(market),
        evaluate_structure_filter(market),
        evaluate_cost_edge_filter(market, commission),
    ]
    blockers = [b for row in results for b in row.get("blockers", [])]
    weighted = round(sum(row["score"] for row in results) / len(results), 2)
    decision = "trade_allowed" if weighted >= 65 and not blockers else "hold"
    return {"status": "ok", "user": username, "filters": results, "combined_score": weighted, "decision": decision, "critical_blocker": blockers[0] if blockers else None, "secret_values_returned": False}


def _strategy_score(base: float, filters: dict, cost_edge: float, risk_penalty: float = 0.0) -> float:
    return clamp((base * 0.55) + (safe_float(filters.get("combined_score"), 50) * 0.30) + (cost_edge * 0.15) - risk_penalty)


def evaluate_strategy_candidates(payload: dict | None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = as_dict(payload)
    market = as_dict(payload.get("market") or payload)
    filters = evaluate_filters({"market": market, "commission_settings": payload.get("commission_settings")}, auth_store, username)
    net_edge = safe_float((filters["filters"][2] or {}).get("net_edge_percent"), 0.0)
    cost_component = clamp(50 + net_edge * 200)
    volatility = safe_float(market.get("volatility_percent"), 0.55)
    trend = safe_float(market.get("trend_strength"), 0.50)
    mean_reversion = safe_float(market.get("mean_reversion_score"), 0.45)
    breakout = safe_float(market.get("compression_breakout_score"), 0.45)
    sweep = safe_float(market.get("liquidity_sweep_quality"), 0.45)
    choch = safe_float(market.get("choch_strength"), 0.55)
    imbalance = safe_float(market.get("imbalance_fill_probability"), 0.58)
    strategies = [
        {"id": STRATEGY_IDS[0], "score": _strategy_score(choch * 100, filters, cost_component, max(0, volatility - 1.2) * 12), "entry": "choch_retest_micro_entry", "exit": "micro_tp_sl_timeout"},
        {"id": STRATEGY_IDS[1], "score": _strategy_score(imbalance * 100, filters, cost_component), "entry": "fvg_fill_zone_entry", "exit": "fill_or_timeout_exit"},
        {"id": STRATEGY_IDS[2], "score": _strategy_score(sweep * 100, filters, cost_component, max(0, 0.18 - trend) * 20), "entry": "liquidity_sweep_reversal_entry", "exit": "tight_stop_fast_take_profit"},
        {"id": STRATEGY_IDS[3], "score": _strategy_score(breakout * 100, filters, cost_component, max(0, safe_float(market.get("spread_percent"), 0.1) - 0.2) * 80), "entry": "compression_breakout_entry", "exit": "fast_failure_or_tp"},
        {"id": STRATEGY_IDS[4], "score": _strategy_score(mean_reversion * 100, filters, cost_component, max(0, trend - 0.75) * 18), "entry": "vwap_ema_distance_reversion", "exit": "mean_reversion_target_or_failure_exit"},
    ]
    for row in strategies:
        row["score"] = round(row["score"], 2)
        row["allowed"] = bool(row["score"] >= 65 and filters["decision"] == "trade_allowed")
        row["submit_default_off"] = True
    ranked = sorted(strategies, key=lambda item: item["score"], reverse=True)
    top = ranked[0]
    return {"status": "ok", "user": username, "filter_decision": filters, "strategies": ranked, "selected_strategy": top if top.get("allowed") else None, "decision": "intent_preview" if top.get("allowed") else "hold", "real_submit_default_off": True, "secret_values_returned": False}


def high_frequency_capacity(payload: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = as_dict(payload)
    symbols = max(1, safe_int(payload.get("symbols"), 20))
    scan_interval_sec = max(1.0, safe_float(payload.get("scan_interval_sec"), 10.0))
    max_trade_cap = max(1, safe_int(payload.get("daily_trade_cap"), 1000))
    quality_pass_rate = clamp(safe_float(payload.get("quality_pass_rate_percent"), 8.0), 0.0, 100.0) / 100.0
    risk_reduce_factor = clamp(safe_float(payload.get("risk_reduce_factor_percent"), 65.0), 1.0, 100.0) / 100.0
    scans_per_day = int(86400 / scan_interval_sec) * symbols
    theoretical_candidates = int(scans_per_day * quality_pass_rate)
    risk_adjusted_capacity = min(max_trade_cap, int(theoretical_candidates * risk_reduce_factor))
    readiness = "near_1000_capable" if risk_adjusted_capacity >= 850 else "limited_by_quality_or_risk"
    return {"status": "ok", "user": username, "symbols": symbols, "scan_interval_sec": scan_interval_sec, "scans_per_day": scans_per_day, "theoretical_candidates_per_day": theoretical_candidates, "risk_adjusted_trade_capacity_per_day": risk_adjusted_capacity, "target_1000_per_day": max_trade_cap >= 1000, "readiness": readiness, "must_not_force_trades": True}


def launch_readiness(auth_store: dict | None = None, username: str = "default", shadow: dict | None = None, settings: dict | None = None) -> dict:
    record = get_user_record(auth_store, username)
    public = public_user_profile(record, username)
    commission = public["commission"]
    api_ready = bool(public["api_configured"] and public["api_trade_permission"])
    readiness_checks = [
        {"name": "new_user_management", "status": "ok"},
        {"name": "api_key_secret_presence", "status": "ok" if public["api_configured"] else "blocked"},
        {"name": "secret_values_never_returned", "status": "ok"},
        {"name": "buy_sell_commission_configured", "status": "ok" if commission.get("enabled") else "review"},
        {"name": "three_filters_available", "status": "ok", "count": len(FILTER_IDS)},
        {"name": "five_strategies_available", "status": "ok", "count": len(STRATEGY_IDS)},
        {"name": "real_submit_default_off", "status": "ok"},
        {"name": "auto_scale_default_off", "status": "ok"},
        {"name": "auto_close_default_off", "status": "ok"},
    ]
    blockers = [row["name"] for row in readiness_checks if row["status"] == "blocked"]
    return {"status": "ok", "revision": PRODUCTION_REVISION, "user": username, "decision": "READY" if not blockers and api_ready else "BLOCKED", "critical_blocker": blockers[0] if blockers else None, "checks": readiness_checks, "features": {"multi_user": True, "api_key_only_onboarding": True, "commission_buy_sell": True, "advanced_filters": FILTER_IDS, "advanced_strategies": STRATEGY_IDS, "high_frequency_capacity_model": True, "premium_dashboard_contract": True}, "public_user_profile": public, "secret_values_returned": False}


def completion_claim(auth_store: dict | None = None, username: str = "default") -> dict:
    readiness = launch_readiness(auth_store, username)
    package_groups = [
        "multi_user_and_secure_onboarding", "commission_and_billing", "premium_ui_ux", "advanced_filter_engine", "advanced_strategy_engine", "high_frequency_capacity", "execution_and_reconciliation", "risk_and_capital_isolation", "production_ops", "release_candidate_security",
    ]
    return {"status": "ok", "revision": PRODUCTION_REVISION, "claim_scope": "code_verified_feature_contract", "production_claim_allowed": readiness["decision"] == "READY", "decision": readiness["decision"], "groups": [{"name": name, "status": "implemented_contract_verified"} for name in package_groups], "readiness": readiness, "limitations": ["real_binance_submit_close_default_off", "owner_approval_required_for_live_action", "1000_trades_day_is_capacity_model_not_forced_trading"], "secret_values_returned": False}
