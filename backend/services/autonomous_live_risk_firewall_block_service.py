from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency", "fail"}:
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


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    value = settings.get(key)
    return value if isinstance(value, dict) else {}


def _check(name: str, status: str, detail: str, required: bool = True, priority: int = 50, action: str = "review") -> dict:
    return {"name": name, "status": status, "required": required, "priority": priority, "detail": detail, "action": action}


def _totals(checks: list[dict]) -> dict:
    return {"total": len(checks), "ok": len([c for c in checks if c.get("status") == "ok"]), "review": len([c for c in checks if c.get("status") == "review"]), "blocked": len([c for c in checks if c.get("status") == "blocked"])}


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
        "writes_runtime_file": False,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "owner_approval_required": True,
        "approval_gated": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
    }


def _policy(settings: dict | None) -> dict:
    source = {
        **_settings(settings, "autonomous_limited_live_activation_rehearsal"),
        **_settings(settings, "autonomous_real_execution_reconciliation"),
        **_settings(settings, "autonomous_live_risk_firewall"),
    }
    return {
        "real_network_enable": _safe_bool(source.get("real_network_enable"), False),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
        "max_daily_loss_usdt": max(0.0, _safe_float(source.get("max_daily_loss_usdt"), 5.0)),
        "max_notional_usdt": max(0.0, _safe_float(source.get("max_notional_usdt"), 10.0)),
        "max_total_exposure_usdt": max(0.0, _safe_float(source.get("max_total_exposure_usdt"), 25.0)),
        "min_usdt_reserve_ratio": max(0.0, min(1.0, _safe_float(source.get("min_usdt_reserve_ratio"), 0.80))),
        "max_open_positions": max(0, _safe_int(source.get("max_open_positions"), 2)),
        "max_pending_orders": max(0, _safe_int(source.get("max_pending_orders"), 2)),
        "max_spread_bps": max(0.0, _safe_float(source.get("max_spread_bps"), 18.0)),
        "max_fee_slippage_bps": max(0.0, _safe_float(source.get("max_fee_slippage_bps"), 35.0)),
        "max_volatility_score": max(0.0, _safe_float(source.get("max_volatility_score"), 75.0)),
        "min_liquidity_score": max(0.0, _safe_float(source.get("min_liquidity_score"), 40.0)),
        "profit_lock_daily_usdt": max(0.0, _safe_float(source.get("profit_lock_daily_usdt"), 3.0)),
        "profit_lock_weekly_usdt": max(0.0, _safe_float(source.get("profit_lock_weekly_usdt"), 10.0)),
        "loss_reduce_threshold_usdt": max(0.0, _safe_float(source.get("loss_reduce_threshold_usdt"), 1.0)),
        "loss_cooldown_threshold_usdt": max(0.0, _safe_float(source.get("loss_cooldown_threshold_usdt"), 2.5)),
        "loss_halt_threshold_usdt": max(0.0, _safe_float(source.get("loss_halt_threshold_usdt"), 4.0)),
        "consecutive_loss_reduce": max(1, _safe_int(source.get("consecutive_loss_reduce"), 1)),
        "consecutive_loss_cooldown": max(1, _safe_int(source.get("consecutive_loss_cooldown"), 2)),
        "consecutive_loss_halt": max(1, _safe_int(source.get("consecutive_loss_halt"), 3)),
        "allowed_symbols": [str(x).upper().strip() for x in source.get("allowed_symbols", ["BTCUSDT", "ETHUSDT"]) if str(x).strip()],
    }


def _as_list(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def _collect(data: dict | None, *keys: str) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    result: list[dict] = []
    sources = [data]
    for parent in ("real_trade", "exchange", "position_state", "order_state", "portfolio", "risk", "market"):
        if isinstance(data.get(parent), dict):
            sources.append(data[parent])
    for source in sources:
        for key in keys:
            result.extend(_as_list(source.get(key)))
    return result


def _notional(item: dict) -> float:
    for key in ("notional_usdt", "notional", "quote_qty", "quoteQty", "position_notional_usdt", "reserved_usdt", "exposure_usdt"):
        if key in item:
            return abs(_safe_float(item.get(key), 0.0))
    price = _safe_float(item.get("price") or item.get("avg_price") or item.get("mark_price"), 0.0)
    qty = abs(_safe_float(item.get("qty") or item.get("quantity") or item.get("size"), 0.0))
    return abs(price * qty)


def _symbol(item: dict) -> str:
    return str(item.get("symbol") or item.get("pair") or "UNKNOWN").upper()


def _state(item: dict) -> str:
    return str(item.get("canonical_state") or item.get("status") or item.get("state") or "unknown").strip().lower()


def _daily_pnl(data: dict | None) -> float:
    data = data if isinstance(data, dict) else {}
    for key in ("today_pnl", "daily_pnl", "daily_realized_pnl", "realized_pnl_today", "pnl_today"):
        if key in data:
            return _safe_float(data.get(key), 0.0)
    for parent in ("performance", "real_trade", "portfolio", "summary", "risk"):
        src = data.get(parent)
        if isinstance(src, dict):
            for key in ("today_pnl", "daily_pnl", "daily_realized_pnl", "realized_pnl_today", "pnl_today"):
                if key in src:
                    return _safe_float(src.get(key), 0.0)
    return 0.0


def _weekly_pnl(data: dict | None) -> float:
    data = data if isinstance(data, dict) else {}
    for key in ("weekly_pnl", "week_pnl", "realized_pnl_week"):
        if key in data:
            return _safe_float(data.get(key), 0.0)
    for parent in ("performance", "real_trade", "portfolio"):
        src = data.get(parent)
        if isinstance(src, dict):
            for key in ("weekly_pnl", "week_pnl", "realized_pnl_week"):
                if key in src:
                    return _safe_float(src.get(key), 0.0)
    return 0.0


def _consecutive_losses(data: dict | None) -> int:
    data = data if isinstance(data, dict) else {}
    for key in ("consecutive_losses", "loss_streak", "consecutive_loss_count"):
        if key in data:
            return max(0, _safe_int(data.get(key), 0))
    for parent in ("performance", "real_trade", "risk"):
        src = data.get(parent)
        if isinstance(src, dict):
            for key in ("consecutive_losses", "loss_streak", "consecutive_loss_count"):
                if key in src:
                    return max(0, _safe_int(src.get(key), 0))
    return 0


def _wallet(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source = data.get("wallet") if isinstance(data.get("wallet"), dict) else data.get("portfolio") if isinstance(data.get("portfolio"), dict) else {}
    total = _safe_float(source.get("total_usdt") or source.get("equity_usdt") or source.get("wallet_value_usdt"), 0.0)
    free = _safe_float(source.get("free_usdt") or source.get("available_usdt") or source.get("usdt_free"), total)
    if total <= 0 and free > 0:
        total = free
    reserve_ratio = free / total if total > 0 else 1.0
    return {"total_usdt": round(total, 6), "free_usdt": round(free, 6), "reserve_ratio": round(reserve_ratio, 6)}


def _market(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source = data.get("market") if isinstance(data.get("market"), dict) else data.get("market_state") if isinstance(data.get("market_state"), dict) else {}
    return {
        "symbol": str(source.get("symbol") or data.get("symbol") or "UNKNOWN").upper(),
        "spread_bps": _safe_float(source.get("spread_bps"), 0.0),
        "fee_slippage_bps": _safe_float(source.get("fee_slippage_bps") or source.get("cost_bps"), 0.0),
        "volatility_score": _safe_float(source.get("volatility_score"), 0.0),
        "liquidity_score": _safe_float(source.get("liquidity_score"), 100.0),
        "session_status": str(source.get("session_status") or data.get("session_status") or "open").lower(),
        "strategy_risk_score": _safe_float(source.get("strategy_risk_score"), _safe_float(data.get("strategy_risk_score"), 0.0)),
        "symbol_risk_score": _safe_float(source.get("symbol_risk_score"), _safe_float(data.get("symbol_risk_score"), 0.0)),
    }


def _issue(code: str, severity: str, detail: str, action: str, priority: int = 50, scope: str = "risk") -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority, "scope": scope}


def _critical_issue(issues: list[dict]) -> dict:
    if not issues:
        return {"code": "none", "severity": "ok", "detail": "Risk firewall is clear.", "action": "continue_preview"}
    return sorted(issues, key=lambda x: ({"critical": 0, "major": 1, "minor": 2, "ok": 3}.get(x.get("severity"), 2), int(x.get("priority", 50))))[0]


def build_rev191_multi_layer_risk_firewall(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    market = _market(data)
    daily_pnl = _daily_pnl(data)
    orders = _collect(data, "orders", "exchange_orders", "order_statuses")
    positions = _collect(data, "positions", "open_positions", "real_positions")
    exposure = sum(_notional(p) for p in positions) + sum(_notional(o) for o in orders if _state(o) in {"open", "new", "pending", "partial", "partially_filled"})
    issues: list[dict] = []
    if daily_pnl <= -policy["max_daily_loss_usdt"]:
        issues.append(_issue("daily_loss_limit_reached", "critical", "Daily loss limit is reached or exceeded.", "halt_new_trades", 1, "daily_loss"))
    if exposure > policy["max_total_exposure_usdt"]:
        issues.append(_issue("max_exposure_exceeded", "critical", "Total open plus pending exposure exceeds policy.", "halt_new_trades_reduce_exposure_preview", 2, "exposure"))
    if market["symbol"] not in {"UNKNOWN", *policy["allowed_symbols"]}:
        issues.append(_issue("symbol_not_allowed", "major", "Candidate symbol is outside whitelist.", "block_submit_symbol", 5, "symbol"))
    if market["spread_bps"] > policy["max_spread_bps"]:
        issues.append(_issue("spread_too_wide", "major", "Spread is above allowed threshold.", "reduce_or_hold", 10, "market"))
    if market["fee_slippage_bps"] > policy["max_fee_slippage_bps"]:
        issues.append(_issue("fee_slippage_too_high", "major", "Cost estimate is above allowed threshold.", "hold_for_cost_recheck", 11, "cost"))
    if market["volatility_score"] > policy["max_volatility_score"]:
        issues.append(_issue("volatility_too_high", "major", "Volatility score is above firewall threshold.", "cooldown", 12, "market"))
    if market["liquidity_score"] < policy["min_liquidity_score"]:
        issues.append(_issue("liquidity_too_low", "major", "Liquidity score is below firewall threshold.", "hold", 13, "market"))
    if market["session_status"] in {"halt", "closed", "blocked", "emergency"}:
        issues.append(_issue("session_not_open", "critical", "Session status does not allow live submit.", "halt_new_trades", 3, "session"))
    if market["strategy_risk_score"] >= 80:
        issues.append(_issue("strategy_risk_high", "major", "Strategy risk score is high.", "review_or_reduce", 20, "strategy"))
    checks = [
        _check("multi_layer_inputs", "ok", "Daily loss, exposure, symbol, strategy, volatility, liquidity, spread, fee/slippage and session status evaluated."),
        _check("major_risk_blocks_submit", "blocked" if any(i["severity"] in {"critical", "major"} for i in issues) else "ok", "Any major risk blocks live submit."),
        _check("real_network_submit_close_default_off", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "Network/submit/close remains OFF."),
        _check("auto_scale_apply_default_off", "ok" if not policy["auto_scale_enable"] and not policy["auto_apply_enable"] else "blocked", "Auto-scale and auto-apply remain OFF."),
    ]
    decision = "halt" if any(i["severity"] == "critical" for i in issues) else "cooldown" if any(i["action"] == "cooldown" for i in issues) else "reduce" if issues else "trade_allowed"
    return {"engine": "autonomous_multi_layer_risk_firewall", "revision": 191, "status": _final_status(checks), "generated_at": now_iso(), "risk_firewall": {"decision": decision, "issues": issues, "critical_issue": _critical_issue(issues), "daily_pnl_usdt": round(daily_pnl, 6), "total_exposure_usdt": round(exposure, 6), "market": market, "allowed_symbols": policy["allowed_symbols"], "real_submit": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev192_real_time_exposure_guard"}


def build_rev192_real_time_exposure_guard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    positions = _collect(data, "positions", "open_positions", "real_positions")
    orders = _collect(data, "orders", "exchange_orders", "order_statuses", "pending_orders")
    open_positions = [p for p in positions if _notional(p) > 0 and _state(p) not in {"closed", "filled_closed"}]
    pending_orders = [o for o in orders if _state(o) in {"open", "new", "pending", "partial", "partially_filled"}]
    wallet = _wallet(data)
    open_exposure = sum(_notional(p) for p in open_positions)
    pending_exposure = sum(_notional(o) for o in pending_orders)
    total_exposure = open_exposure + pending_exposure
    issues: list[dict] = []
    if len(open_positions) > policy["max_open_positions"]:
        issues.append(_issue("too_many_open_positions", "major", "Open position count exceeds policy.", "halt_new_trades", 10, "positions"))
    if len(pending_orders) > policy["max_pending_orders"]:
        issues.append(_issue("too_many_pending_orders", "major", "Pending order count exceeds policy.", "halt_new_trades_cancel_review", 11, "orders"))
    if total_exposure > policy["max_total_exposure_usdt"]:
        issues.append(_issue("exposure_limit_exceeded", "critical", "Total exposure exceeds max exposure.", "halt_new_trades", 1, "exposure"))
    if wallet["reserve_ratio"] < policy["min_usdt_reserve_ratio"]:
        issues.append(_issue("usdt_reserve_below_policy", "major", "Free USDT reserve ratio is below policy.", "reduce_or_hold", 12, "reserve"))
    checks = [
        _check("exposure_inputs", "ok", "Open positions, pending orders, reserved capital and USDT reserve evaluated."),
        _check("exposure_limit", "blocked" if any(i["severity"] in {"critical", "major"} for i in issues) else "ok", "Exposure breach blocks new live submit."),
        _check("network_submit_close_off", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "No real exchange action."),
    ]
    decision = "halt" if any(i["severity"] == "critical" for i in issues) else "attention" if issues else "clear"
    return {"engine": "autonomous_real_time_exposure_guard", "revision": 192, "status": _final_status(checks), "generated_at": now_iso(), "exposure_guard": {"decision": decision, "open_positions": len(open_positions), "pending_orders": len(pending_orders), "open_exposure_usdt": round(open_exposure, 6), "pending_exposure_usdt": round(pending_exposure, 6), "total_exposure_usdt": round(total_exposure, 6), "max_allowed_exposure_usdt": policy["max_total_exposure_usdt"], "wallet": wallet, "issues": issues, "critical_issue": _critical_issue(issues)}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev193_profit_lock_enforcement_preview"}


def build_rev193_profit_lock_enforcement_preview(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    daily = _daily_pnl(data)
    weekly = _weekly_pnl(data)
    mode = "passive"
    recommendation = "continue_preview"
    if policy["profit_lock_daily_usdt"] and daily >= policy["profit_lock_daily_usdt"]:
        mode = "required"
        recommendation = "protect_profit_reduce_or_stop_new_trades"
    elif policy["profit_lock_weekly_usdt"] and weekly >= policy["profit_lock_weekly_usdt"]:
        mode = "active"
        recommendation = "tighten_risk_and_reduce_frequency"
    checks = [
        _check("profit_lock_thresholds", "ok", "Daily and weekly profit protection thresholds evaluated."),
        _check("profit_lock_enforcement", "review" if mode in {"active", "required"} else "ok", "Profit lock can reduce/stop new trade previews.", required=False, action=recommendation),
        _check("auto_scale_apply_default_off", "ok" if not policy["auto_scale_enable"] and not policy["auto_apply_enable"] else "blocked", "Profit lock cannot auto-scale/apply."),
        _check("network_submit_close_off", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "No real exchange action."),
    ]
    return {"engine": "autonomous_profit_lock_enforcement_preview", "revision": 193, "status": _final_status(checks), "generated_at": now_iso(), "profit_lock": {"mode": mode, "decision": "reduce" if mode == "active" else "halt_new_trades" if mode == "required" else "trade_allowed", "daily_pnl_usdt": round(daily, 6), "weekly_pnl_usdt": round(weekly, 6), "recommendation": recommendation, "auto_apply": "OFF", "auto_scale": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev194_loss_escalation_ladder"}


def build_rev194_loss_escalation_ladder(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    daily_loss = max(0.0, -_daily_pnl(data))
    streak = _consecutive_losses(data)
    decision = "trade_allowed"
    action = "continue_preview"
    severity = "ok"
    if daily_loss >= policy["max_daily_loss_usdt"] or daily_loss >= policy["loss_halt_threshold_usdt"] or streak >= policy["consecutive_loss_halt"]:
        decision, action, severity = "halt", "halt_new_trades", "critical"
    elif daily_loss >= policy["loss_cooldown_threshold_usdt"] or streak >= policy["consecutive_loss_cooldown"]:
        decision, action, severity = "cooldown", "cooldown_block_revenge_trade", "major"
    elif daily_loss >= policy["loss_reduce_threshold_usdt"] or streak >= policy["consecutive_loss_reduce"]:
        decision, action, severity = "reduce", "reduce_size_and_frequency", "minor"
    issue = [] if severity == "ok" else [_issue("loss_escalation_active", severity, "Loss ladder threshold was reached.", action, 1, "loss_ladder")]
    checks = [
        _check("loss_ladder_thresholds", "ok", "First loss, consecutive loss, cooldown, halt and emergency thresholds evaluated."),
        _check("revenge_trade_martingale_blocked", "ok", "Revenge trade and martingale escalation are not allowed."),
        _check("loss_ladder_decision", "blocked" if severity in {"critical", "major"} else "review" if severity == "minor" else "ok", "Loss ladder controls new trade permission.", action=action),
        _check("network_submit_close_off", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "No real exchange action."),
    ]
    return {"engine": "autonomous_loss_escalation_ladder", "revision": 194, "status": _final_status(checks), "generated_at": now_iso(), "loss_ladder": {"decision": decision, "operator_action": action, "daily_loss_usdt": round(daily_loss, 6), "consecutive_losses": streak, "martingale_allowed": False, "revenge_trade_allowed": False, "issues": issue, "critical_issue": _critical_issue(issue)}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev195_live_risk_firewall_decision_packet"}


def _combine_decision(*decisions: str) -> str:
    order = ["emergency", "halt", "cooldown", "reduce", "trade_allowed", "clear"]
    cleaned = [str(d or "").lower() for d in decisions]
    if any(d in {"emergency"} for d in cleaned):
        return "emergency"
    if any(d in {"halt", "halt_new_trades"} for d in cleaned):
        return "halt"
    if any(d in {"cooldown", "attention"} for d in cleaned):
        return "cooldown"
    if any(d == "reduce" for d in cleaned):
        return "reduce"
    return "trade_allowed"


def build_rev195_live_risk_firewall_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    r191 = build_rev191_multi_layer_risk_firewall(data, settings, auth_store, username)
    r192 = build_rev192_real_time_exposure_guard(data, settings, auth_store, username)
    r193 = build_rev193_profit_lock_enforcement_preview(data, settings, auth_store, username)
    r194 = build_rev194_loss_escalation_ladder(data, settings, auth_store, username)
    risk_issues = (r191.get("risk_firewall", {}).get("issues") or []) + (r192.get("exposure_guard", {}).get("issues") or []) + (r194.get("loss_ladder", {}).get("issues") or [])
    decision = _combine_decision(r191.get("risk_firewall", {}).get("decision"), r192.get("exposure_guard", {}).get("decision"), r193.get("profit_lock", {}).get("decision"), r194.get("loss_ladder", {}).get("decision"))
    exposure = r192.get("exposure_guard", {})
    score = min(100, len([i for i in risk_issues if i.get("severity") == "critical"]) * 35 + len([i for i in risk_issues if i.get("severity") == "major"]) * 20 + len([i for i in risk_issues if i.get("severity") == "minor"]) * 10)
    critical = _critical_issue(risk_issues)
    operator_action = critical.get("action") if critical.get("code") != "none" else r193.get("profit_lock", {}).get("recommendation", "continue_preview")
    checks = [
        _check("risk_firewall_packet_ready", "ok", "Combined risk, exposure, profit lock and loss ladder decision produced."),
        _check("trade_permission", "blocked" if decision in {"halt", "emergency"} else "review" if decision in {"reduce", "cooldown"} else "ok", "Risk firewall controls trade permission.", action=operator_action),
        _check("live_submit_approval_gated", "ok" if not policy["real_submit_enable"] else "blocked", "Real submit remains default OFF/approval-gated."),
        _check("real_network_close_default_off", "ok" if not policy["real_network_enable"] and not policy["real_close_enable"] else "blocked", "Real network/close remains OFF."),
        _check("auto_scale_apply_default_off", "ok" if not policy["auto_scale_enable"] and not policy["auto_apply_enable"] else "blocked", "Auto-scale/apply remain OFF."),
    ]
    summary_visible = {"trade_permission": decision, "reason": critical.get("code"), "max_allowed_exposure_usdt": policy["max_total_exposure_usdt"], "allowed_symbols": policy["allowed_symbols"], "session_risk_score": score, "operator_action": operator_action}
    return {"engine": "autonomous_live_risk_firewall_decision_packet", "revision": 195, "status": _final_status(checks), "generated_at": now_iso(), "live_risk_firewall_packet": {"decision": decision, "reason": critical, "max_allowed_exposure_usdt": policy["max_total_exposure_usdt"], "current_exposure_usdt": exposure.get("total_exposure_usdt", 0), "allowed_symbols": policy["allowed_symbols"], "session_risk_score": score, "profit_lock_mode": r193.get("profit_lock", {}).get("mode"), "operator_action": operator_action, "summary_visible": summary_visible, "real_submit": "OFF", "real_close": "OFF", "auto_scale": "OFF"}, "checks": checks, "check_totals": _totals(checks), "summary_result": summary_visible, "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev196_first_micro_live_intent_contract"}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builders = {191: build_rev191_multi_layer_risk_firewall, 192: build_rev192_real_time_exposure_guard, 193: build_rev193_profit_lock_enforcement_preview, 194: build_rev194_loss_escalation_ladder, 195: build_rev195_live_risk_firewall_decision_packet}
    builder = builders.get(int(revision))
    if not builder:
        return {"engine": "autonomous_live_risk_firewall_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev191-195 revision.", "contains_secret": False}
    return builder(data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_multi_layer_risk_firewall": build_rev191_multi_layer_risk_firewall(data, settings, auth_store, username),
        "autonomous_real_time_exposure_guard": build_rev192_real_time_exposure_guard(data, settings, auth_store, username),
        "autonomous_profit_lock_enforcement_preview": build_rev193_profit_lock_enforcement_preview(data, settings, auth_store, username),
        "autonomous_loss_escalation_ladder": build_rev194_loss_escalation_ladder(data, settings, auth_store, username),
        "autonomous_live_risk_firewall_decision_packet": build_rev195_live_risk_firewall_decision_packet(data, settings, auth_store, username),
    }
    final = outputs["autonomous_live_risk_firewall_decision_packet"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {"engine": "autonomous_live_risk_firewall_block", "revision": 195, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("summary_result", {}), "live_risk_firewall_packet": final.get("live_risk_firewall_packet", {}), "auto_apply_default_off": True, "auto_scale_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev196_first_controlled_micro_live_block"}


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("risk_firewall") or payload.get("exposure_guard") or payload.get("profit_lock") or payload.get("loss_ladder") or payload.get("live_risk_firewall_packet") or {}
    return {"revision": int(revision), "status": payload.get("status"), "decision": body.get("decision") or body.get("mode"), "critical_issue": (body.get("critical_issue") or body.get("reason") or {}).get("code"), "operator_action": body.get("operator_action") or body.get("recommendation"), "command_preview": payload.get("command_preview"), "contains_secret": False, "secret_values_returned": False}


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    checks = payload.get("checks") or []
    return {"engine": "autonomous_live_risk_firewall_quality_gate", "revision": int(revision), "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks), "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
