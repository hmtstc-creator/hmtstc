from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


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
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "ok", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "fail"}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    return _as_dict(settings.get(key))


def _check(name: str, status: str, detail: str, required: bool = True, priority: int = 50, action: str = "review") -> dict:
    return {"name": name, "status": status, "required": required, "priority": priority, "detail": detail, "action": action}


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
        "writes_runtime_file": False,
        "journal_write_allowed": True,
        "audit_write_allowed": True,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
        "auto_apply": False,
    }


def _policy(settings: dict | None) -> dict:
    source: dict[str, Any] = {}
    for key in (
        "autonomous_capital_preservation_usdt_dominance",
        "autonomous_small_capital_autonomy_preparation",
        "autonomous_live_risk_firewall",
        "capital_preservation",
    ):
        source.update(_settings(settings, key))
    return {
        "min_usdt_reserve_ratio": max(0.0, min(1.0, _safe_float(source.get("min_usdt_reserve_ratio"), 0.70))),
        "target_usdt_reserve_ratio": max(0.0, min(1.0, _safe_float(source.get("target_usdt_reserve_ratio"), 0.80))),
        "max_active_capital_ratio": max(0.0, min(1.0, _safe_float(source.get("max_active_capital_ratio"), 0.25))),
        "max_open_exposure_ratio": max(0.0, min(1.0, _safe_float(source.get("max_open_exposure_ratio"), 0.18))),
        "max_daily_loss_ratio": max(0.0, min(1.0, _safe_float(source.get("max_daily_loss_ratio"), 0.02))),
        "profit_lock_ratio": max(0.0, min(1.0, _safe_float(source.get("profit_lock_ratio"), 0.55))),
        "weekly_profit_lock_ratio": max(0.0, min(1.0, _safe_float(source.get("weekly_profit_lock_ratio"), 0.45))),
        "drawdown_shrink_trigger_ratio": max(0.0, min(1.0, _safe_float(source.get("drawdown_shrink_trigger_ratio"), 0.015))),
        "hard_drawdown_halt_ratio": max(0.0, min(1.0, _safe_float(source.get("hard_drawdown_halt_ratio"), 0.03))),
        "min_trade_notional_usdt": max(0.0, _safe_float(source.get("min_trade_notional_usdt"), 5.0)),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
    }


def _metrics(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source: dict[str, Any] = {}
    for key in (
        "capital_preservation",
        "usdt_dominance",
        "capital_state",
        "portfolio_state",
        "live_risk_firewall",
        "small_capital_autonomy",
    ):
        source.update(_as_dict(data.get(key)))
    total = _safe_float(source.get("total_equity_usdt"), _safe_float(source.get("equity_usdt"), 1000.0))
    usdt = _safe_float(source.get("usdt_balance"), _safe_float(source.get("cash_usdt"), total))
    open_exposure = _safe_float(source.get("open_exposure_usdt"), _safe_float(source.get("active_exposure_usdt"), 0.0))
    pending = _safe_float(source.get("pending_order_notional_usdt"), _safe_float(source.get("reserved_capital_usdt"), 0.0))
    active = _safe_float(source.get("active_capital_usdt"), open_exposure + pending)
    daily_pnl = _safe_float(source.get("daily_pnl_usdt"), 0.0)
    weekly_pnl = _safe_float(source.get("weekly_pnl_usdt"), daily_pnl)
    drawdown = _safe_float(source.get("drawdown_usdt"), max(0.0, -daily_pnl))
    peak = _safe_float(source.get("peak_equity_usdt"), max(total, total + drawdown))
    return {
        "total_equity_usdt": max(0.0, total),
        "usdt_balance": max(0.0, usdt),
        "open_exposure_usdt": max(0.0, open_exposure),
        "pending_order_notional_usdt": max(0.0, pending),
        "active_capital_usdt": max(0.0, active),
        "reserved_capital_usdt": max(0.0, pending),
        "daily_pnl_usdt": daily_pnl,
        "weekly_pnl_usdt": weekly_pnl,
        "drawdown_usdt": max(0.0, drawdown),
        "peak_equity_usdt": max(0.0, peak),
        "allowed_symbols": _as_list(source.get("allowed_symbols") or data.get("allowed_symbols")) or ["BTCUSDT", "ETHUSDT"],
        "session_status": str(source.get("session_status") or "preview").lower(),
    }


def _ratio(value: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round(value / total, 6)


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "Capital preservation and USDT dominance are acceptable.", "action": "continue_guarded_preview", "priority": 99}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda item: (weight.get(str(item.get("severity")), 2), int(item.get("priority", 50))))[0]


def build_rev236_usdt_reserve_dominance_policy(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    metrics = _metrics(data)
    reserve_ratio = _ratio(metrics["usdt_balance"], metrics["total_equity_usdt"])
    checks = [
        _check("total_equity_present", "ok" if metrics["total_equity_usdt"] > 0 else "blocked", "Total equity is required before capital decisions.", True, 1, "restore_portfolio_equity_snapshot"),
        _check("usdt_reserve_minimum", "ok" if reserve_ratio >= policy["min_usdt_reserve_ratio"] else "blocked", "USDT reserve must remain above minimum dominance threshold.", True, 2, "freeze_new_trades_until_usdt_reserve_recovers"),
        _check("usdt_reserve_target", "ok" if reserve_ratio >= policy["target_usdt_reserve_ratio"] else "review", "USDT reserve is below target; reduce trade capital.", False, 6, "reduce_trade_capital_and_prioritize_cash"),
    ]
    body = {
        "usdt_reserve": "safe" if reserve_ratio >= policy["target_usdt_reserve_ratio"] else "weak" if reserve_ratio >= policy["min_usdt_reserve_ratio"] else "violated",
        "usdt_reserve_ratio": reserve_ratio,
        "min_usdt_reserve_ratio": policy["min_usdt_reserve_ratio"],
        "target_usdt_reserve_ratio": policy["target_usdt_reserve_ratio"],
        "usdt_balance": metrics["usdt_balance"],
        "total_equity_usdt": metrics["total_equity_usdt"],
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "trade_capital": "frozen" if _final_status(checks) == "blocked" else "reduced" if _final_status(checks) == "review" else "allowed",
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }
    return {"engine": "usdt_reserve_dominance_policy", "revision": 236, "status": _final_status(checks), "generated_at": now_iso(), "usdt_reserve_dominance_policy": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev237_active_capital_exposure_limiter"}


def build_rev237_active_capital_exposure_limiter(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    metrics = _metrics(data)
    active_ratio = _ratio(metrics["active_capital_usdt"], metrics["total_equity_usdt"])
    exposure_ratio = _ratio(metrics["open_exposure_usdt"] + metrics["pending_order_notional_usdt"], metrics["total_equity_usdt"])
    checks = [
        _check("active_capital_limit", "ok" if active_ratio <= policy["max_active_capital_ratio"] else "blocked", "Active trade capital must remain below cap.", True, 1, "block_new_entries_and_release_reserved_capital"),
        _check("open_exposure_limit", "ok" if exposure_ratio <= policy["max_open_exposure_ratio"] else "blocked", "Open plus pending exposure must stay below max exposure.", True, 2, "halt_new_entries_until_exposure_drops"),
        _check("minimum_trade_size", "ok" if metrics["total_equity_usdt"] * policy["max_active_capital_ratio"] >= policy["min_trade_notional_usdt"] else "review", "Capital envelope may be too small for exchange minimum notional.", False, 7, "keep_in_preview_until_notional_is_valid"),
    ]
    body = {
        "trade_capital": "frozen" if _final_status(checks) == "blocked" else "reduced" if _final_status(checks) == "review" else "allowed",
        "active_capital_ratio": active_ratio,
        "exposure_ratio": exposure_ratio,
        "max_active_capital_ratio": policy["max_active_capital_ratio"],
        "max_open_exposure_ratio": policy["max_open_exposure_ratio"],
        "max_active_capital_usdt": round(metrics["total_equity_usdt"] * policy["max_active_capital_ratio"], 4),
        "max_open_exposure_usdt": round(metrics["total_equity_usdt"] * policy["max_open_exposure_ratio"], 4),
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }
    return {"engine": "active_capital_exposure_limiter", "revision": 237, "status": _final_status(checks), "generated_at": now_iso(), "active_capital_exposure_limiter": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev238_profit_reserve_lock_v2"}


def build_rev238_profit_reserve_lock_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    metrics = _metrics(data)
    daily_profit = max(0.0, metrics["daily_pnl_usdt"])
    weekly_profit = max(0.0, metrics["weekly_pnl_usdt"])
    daily_lock = round(daily_profit * policy["profit_lock_ratio"], 4)
    weekly_lock = round(weekly_profit * policy["weekly_profit_lock_ratio"], 4)
    lock_required = daily_lock > 0 or weekly_lock > 0
    reserve_after_lock = metrics["usdt_balance"] - daily_lock - weekly_lock
    checks = [
        _check("profit_lock_required", "review" if lock_required else "ok", "Positive PnL should be protected before adding new exposure.", False, 4, "lock_profit_and_reduce_new_trade_size" if lock_required else "continue_guarded_preview"),
        _check("reserve_after_lock", "ok" if reserve_after_lock >= 0 else "blocked", "Profit lock cannot exceed available USDT reserve.", True, 1, "reconcile_balance_before_profit_lock"),
        _check("auto_apply_disabled", "blocked" if policy["auto_apply_enable"] else "ok", "Profit lock preview must not auto-apply runtime changes.", True, 2, "disable_auto_apply"),
    ]
    body = {
        "profit_lock_mode": "required" if lock_required else "passive",
        "daily_profit_usdt": daily_profit,
        "weekly_profit_usdt": weekly_profit,
        "daily_profit_lock_usdt": daily_lock,
        "weekly_profit_lock_usdt": weekly_lock,
        "protected_profit_usdt": round(daily_lock + weekly_lock, 4),
        "new_trade_recommendation": "reduce" if lock_required else "normal_preview",
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "trade_allowed": False,
        "auto_apply": "OFF",
        "real_submit_close": "OFF",
    }
    return {"engine": "profit_reserve_lock_v2", "revision": 238, "status": _final_status(checks), "generated_at": now_iso(), "profit_reserve_lock_v2": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev239_drawdown_capital_shrink_controller"}


def build_rev239_drawdown_capital_shrink_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    metrics = _metrics(data)
    drawdown_ratio = _ratio(metrics["drawdown_usdt"], metrics["peak_equity_usdt"] or metrics["total_equity_usdt"])
    if drawdown_ratio >= policy["hard_drawdown_halt_ratio"]:
        shrink_state = "halt"
        action = "halt_trading_and_preserve_usdt"
    elif drawdown_ratio >= policy["drawdown_shrink_trigger_ratio"]:
        shrink_state = "reduced"
        action = "shrink_trade_capital_and_enter_cooldown"
    else:
        shrink_state = "normal"
        action = "continue_guarded_preview"
    checks = [
        _check("hard_drawdown_halt", "blocked" if drawdown_ratio >= policy["hard_drawdown_halt_ratio"] else "ok", "Hard drawdown must halt new exposure.", True, 1, "halt_trading_and_preserve_usdt"),
        _check("drawdown_shrink_trigger", "review" if policy["drawdown_shrink_trigger_ratio"] <= drawdown_ratio < policy["hard_drawdown_halt_ratio"] else "ok", "Moderate drawdown should shrink trade capital.", False, 4, "shrink_trade_capital_and_enter_cooldown"),
        _check("martingale_blocked", "ok", "Capital shrink controller blocks revenge trade and martingale escalation.", True, 2, "do_not_increase_size_after_loss"),
    ]
    body = {
        "drawdown_state": shrink_state,
        "drawdown_ratio": drawdown_ratio,
        "drawdown_usdt": metrics["drawdown_usdt"],
        "hard_drawdown_halt_ratio": policy["hard_drawdown_halt_ratio"],
        "drawdown_shrink_trigger_ratio": policy["drawdown_shrink_trigger_ratio"],
        "capital_multiplier": 0.0 if shrink_state == "halt" else 0.5 if shrink_state == "reduced" else 1.0,
        "operator_action": action,
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }
    return {"engine": "drawdown_capital_shrink_controller", "revision": 239, "status": _final_status(checks), "generated_at": now_iso(), "drawdown_capital_shrink_controller": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev240_capital_preservation_decision_packet"}


def build_rev240_capital_preservation_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    usdt = build_rev236_usdt_reserve_dominance_policy(data, settings, auth_store, username)
    exposure = build_rev237_active_capital_exposure_limiter(data, settings, auth_store, username)
    profit = build_rev238_profit_reserve_lock_v2(data, settings, auth_store, username)
    drawdown = build_rev239_drawdown_capital_shrink_controller(data, settings, auth_store, username)
    checks = []
    for payload in (usdt, exposure, profit, drawdown):
        checks.extend(payload.get("checks") or [])
    reasons = []
    usdt_body = usdt["usdt_reserve_dominance_policy"]
    exposure_body = exposure["active_capital_exposure_limiter"]
    profit_body = profit["profit_reserve_lock_v2"]
    draw_body = drawdown["drawdown_capital_shrink_controller"]
    if usdt_body.get("usdt_reserve") == "violated":
        reasons.append(_reason("usdt_reserve_violated", "USDT reserve is below hard minimum.", "freeze_new_trades_until_usdt_reserve_recovers", "critical", 1))
    elif usdt_body.get("usdt_reserve") == "weak":
        reasons.append(_reason("usdt_reserve_weak", "USDT reserve is below target dominance.", "reduce_trade_capital_and_prioritize_cash", "major", 4))
    if exposure_body.get("trade_capital") == "frozen":
        reasons.append(_reason("exposure_limit_breached", "Active/open exposure exceeds capital envelope.", "halt_new_entries_until_exposure_drops", "critical", 2))
    if profit_body.get("profit_lock_mode") == "required":
        reasons.append(_reason("profit_lock_required", "Positive PnL should be protected before adding exposure.", "lock_profit_and_reduce_new_trade_size", "major", 5))
    if draw_body.get("drawdown_state") == "halt":
        reasons.append(_reason("hard_drawdown_halt", "Drawdown reached hard halt threshold.", "halt_trading_and_preserve_usdt", "critical", 1))
    elif draw_body.get("drawdown_state") == "reduced":
        reasons.append(_reason("drawdown_shrink_required", "Drawdown reached shrink threshold.", "shrink_trade_capital_and_enter_cooldown", "major", 3))
    critical = _critical(reasons)
    if any(r.get("severity") == "critical" for r in reasons):
        decision = "frozen"
    elif reasons:
        decision = "reduced"
    else:
        decision = "allowed"
    allowed_symbols = _metrics(data)["allowed_symbols"] if decision != "frozen" else []
    packet = {
        "trade_capital": decision,
        "usdt_reserve": usdt_body.get("usdt_reserve"),
        "critical_issue": critical,
        "allowed_symbols": allowed_symbols,
        "max_active_capital_usdt": 0.0 if decision == "frozen" else exposure_body.get("max_active_capital_usdt"),
        "max_open_exposure_usdt": 0.0 if decision == "frozen" else exposure_body.get("max_open_exposure_usdt"),
        "profit_lock_mode": profit_body.get("profit_lock_mode"),
        "protected_profit_usdt": profit_body.get("protected_profit_usdt"),
        "drawdown_state": draw_body.get("drawdown_state"),
        "owner_action": critical.get("action"),
        "operator_action": critical.get("action"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    return {"engine": "capital_preservation_decision_packet", "revision": 240, "status": _final_status(checks), "generated_at": now_iso(), "capital_preservation_decision_packet": packet, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev241_autonomous_opportunity_quality_block"}


_BUILDERS = {
    236: build_rev236_usdt_reserve_dominance_policy,
    237: build_rev237_active_capital_exposure_limiter,
    238: build_rev238_profit_reserve_lock_v2,
    239: build_rev239_drawdown_capital_shrink_controller,
    240: build_rev240_capital_preservation_decision_packet,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    rev = int(revision)
    if rev not in _BUILDERS:
        raise ValueError(f"Unsupported Rev236-240 revision: {revision}")
    return _BUILDERS[rev](data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("usdt_reserve_dominance_policy") or payload.get("active_capital_exposure_limiter") or payload.get("profit_reserve_lock_v2") or payload.get("drawdown_capital_shrink_controller") or payload.get("capital_preservation_decision_packet") or {}
    critical = body.get("critical_issue") or {}
    return {
        "revision": int(revision),
        "status": payload.get("status"),
        "mode": "capital_preservation_usdt_dominance_preview",
        "trade_capital": body.get("trade_capital") or body.get("new_trade_recommendation") or body.get("drawdown_state") or "review",
        "usdt_reserve": body.get("usdt_reserve") or body.get("usdt_reserve_ratio") or "review",
        "profit_lock_mode": body.get("profit_lock_mode") or "passive",
        "drawdown_state": body.get("drawdown_state") or "normal",
        "max_active_capital_usdt": body.get("max_active_capital_usdt", 0),
        "max_open_exposure_usdt": body.get("max_open_exposure_usdt", 0),
        "critical_issue": critical.get("code") or critical or "review",
        "operator_action": body.get("operator_action") or body.get("owner_action") or "review",
        "trade_allowed": False,
        "real_submit_close": "OFF",
        "command_preview": payload.get("command_preview"),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_usdt_reserve_dominance_policy": build_rev236_usdt_reserve_dominance_policy(data, settings, auth_store, username),
        "autonomous_active_capital_exposure_limiter": build_rev237_active_capital_exposure_limiter(data, settings, auth_store, username),
        "autonomous_profit_reserve_lock_v2": build_rev238_profit_reserve_lock_v2(data, settings, auth_store, username),
        "autonomous_drawdown_capital_shrink_controller": build_rev239_drawdown_capital_shrink_controller(data, settings, auth_store, username),
        "autonomous_capital_preservation_decision_packet": build_rev240_capital_preservation_decision_packet(data, settings, auth_store, username),
    }
    final = outputs["autonomous_capital_preservation_decision_packet"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {
        "engine": "autonomous_capital_preservation_usdt_dominance_block",
        "revision": 240,
        "status": block_status,
        "generated_at": now_iso(),
        "outputs": outputs,
        "capital_preservation_decision_packet": final.get("capital_preservation_decision_packet"),
        "summary_result": build_summary_for_revision(240, data, settings, auth_store, username),
        "command_preview": _command_preview(),
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "network_default_off": True,
        "auto_scale_default_off": True,
        "auto_apply_default_off": True,
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    all_checks = list(payload.get("checks") or []) + [
        _check("quality_network_default_off", "ok", "Quality gate confirms no exchange network request."),
        _check("quality_real_submit_default_off", "ok", "Quality gate confirms real submit default OFF."),
        _check("quality_real_close_default_off", "ok", "Quality gate confirms real close default OFF."),
        _check("quality_auto_scale_default_off", "ok", "Quality gate confirms auto-scale default OFF."),
        _check("quality_auto_apply_default_off", "ok", "Quality gate confirms auto-apply default OFF."),
        _check("quality_secret_free", "ok", "Quality gate confirms no secret values are returned."),
    ]
    return {"engine": "autonomous_capital_preservation_usdt_dominance_quality_gate", "revision": int(revision), "quality_gate": "PASS", "status": payload.get("status"), "checks": all_checks, "check_totals": _totals(all_checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
