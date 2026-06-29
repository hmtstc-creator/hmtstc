from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_micro_real_pilot_stabilization_block_service import build_rev170_micro_pilot_stabilization_decision_v2
from services.autonomous_performance_observability_block_service import (
    build_rev131_trade_performance_metrics_engine,
    build_rev132_strategy_performance_attribution,
    build_rev133_execution_quality_analytics,
    build_rev134_risk_adjusted_return_scoring,
    build_rev135_performance_sentinel_v2,
)
from services.autonomous_capital_scaling_profit_defense_block_service import build_rev145_capital_protection_summary


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "clear", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency", "stopped", "fail"}:
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


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {"name": name, "status": status, "required": required, "detail": detail}


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
    p = _settings(settings, "autonomous_live_edge_profitability_proof")
    return {
        "min_trade_count": max(1, _safe_int(p.get("min_trade_count"), 5)),
        "min_profit_factor": max(0.0, _safe_float(p.get("min_profit_factor"), 1.15)),
        "min_expectancy_usdt": _safe_float(p.get("min_expectancy_usdt"), 0.0),
        "min_risk_adjusted_score": max(0.0, min(100.0, _safe_float(p.get("min_risk_adjusted_score"), 55.0))),
        "max_cost_to_edge_ratio": max(0.05, _safe_float(p.get("max_cost_to_edge_ratio"), 0.45)),
        "max_allocation_notional_usdt": max(1.0, _safe_float(p.get("max_allocation_notional_usdt"), 10.0)),
        "learning_auto_apply": _safe_bool(p.get("learning_auto_apply"), False),
        "real_submit_enable": _safe_bool(p.get("real_submit_enable"), False),
        "owner_profitability_confirmation": _safe_bool(p.get("owner_profitability_confirmation"), False),
        "allowed_symbols": [str(x).upper() for x in p.get("allowed_symbols", []) if str(x).strip()] if isinstance(p.get("allowed_symbols"), list) else [],
    }


def _overall_metrics(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    payload = build_rev131_trade_performance_metrics_engine(data, settings, auth_store, username)
    snapshot = payload.get("metric_snapshot") if isinstance(payload.get("metric_snapshot"), dict) else {}
    return snapshot.get("overall") if isinstance(snapshot.get("overall"), dict) else {}


def _risk_score(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    payload = build_rev134_risk_adjusted_return_scoring(data, settings, auth_store, username)
    score = payload.get("risk_adjusted_score") if isinstance(payload.get("risk_adjusted_score"), dict) else {}
    return score


def _candidate_rows(data: dict, settings: dict, auth_store: dict, username: str) -> list[dict]:
    payload = build_rev132_strategy_performance_attribution(data, settings, auth_store, username)
    rows = payload.get("attribution_table") if isinstance(payload.get("attribution_table"), list) else []
    candidates = []
    for row in rows:
        signal = str(row.get("attribution_signal") or "hold")
        symbol = str(row.get("symbol") or row.get("group_0") or "UNKNOWN").upper()
        strategy = str(row.get("strategy") or row.get("group_1") or "unknown")
        regime = str(row.get("regime") or row.get("group_2") or "unknown")
        expectancy = _safe_float(row.get("expectancy_usdt"), 0.0)
        pf = _safe_float(row.get("profit_factor"), 0.0)
        count = _safe_int(row.get("trade_count"), 0)
        if signal in {"cautious_promotion", "hold"} and expectancy >= 0 and pf >= 1:
            candidates.append({"symbol": symbol, "strategy": strategy, "regime": regime, "trade_count": count, "profit_factor": pf, "expectancy_usdt": expectancy, "allocation_signal": signal})
    return candidates[:10]


def build_rev171_post_pilot_edge_validation_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    stabilization = build_rev170_micro_pilot_stabilization_decision_v2(data, settings, auth_store, username)
    overall = _overall_metrics(data, settings, auth_store, username)
    score = _risk_score(data, settings, auth_store, username)
    trade_count = _safe_int(overall.get("trade_count"), 0)
    profit_factor = _safe_float(overall.get("profit_factor"), 0.0)
    expectancy = _safe_float(overall.get("expectancy_usdt"), 0.0)
    risk_score = _safe_float(score.get("score"), 0.0)
    decision = "EDGE_VALIDATED_PREVIEW" if trade_count >= policy["min_trade_count"] and profit_factor >= policy["min_profit_factor"] and expectancy >= policy["min_expectancy_usdt"] and risk_score >= policy["min_risk_adjusted_score"] and stabilization.get("status") != "blocked" else "EDGE_NOT_PROVEN"
    checks = [
        _check("micro_pilot_stabilized", "ok" if stabilization.get("status") != "blocked" else "blocked", "Rev170 stabilization must not be blocked."),
        _check("sample_size", "ok" if trade_count >= policy["min_trade_count"] else "review", "Trade sample size is checked before any edge claim.", required=False),
        _check("profit_factor", "ok" if profit_factor >= policy["min_profit_factor"] else "review", "Profit factor must exceed minimum edge policy.", required=False),
        _check("positive_expectancy", "ok" if expectancy >= policy["min_expectancy_usdt"] else "review", "Expectancy must be non-negative."),
        _check("risk_adjusted_score", "ok" if risk_score >= policy["min_risk_adjusted_score"] else "review", "Risk-adjusted score is checked."),
        _check("preview_only", "ok", "Edge gate cannot submit or close orders."),
    ]
    return {"engine": "autonomous_post_pilot_edge_validation_gate", "revision": 171, "status": _final_status(checks), "edge_validation": {"decision": decision, "trade_count": trade_count, "profit_factor": profit_factor, "expectancy_usdt": expectancy, "risk_adjusted_score": risk_score, "real_submit_close": "OFF"}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "fee_slippage_break_even_controller"}


def build_rev172_fee_slippage_break_even_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    overall = _overall_metrics(data, settings, auth_store, username)
    execution = build_rev133_execution_quality_analytics(data, settings, auth_store, username).get("execution_quality", {})
    gross = abs(_safe_float(overall.get("gross_pnl_usdt"), _safe_float(overall.get("net_pnl_usdt"), 0.0)))
    fee = abs(_safe_float(overall.get("fee_impact_usdt"), _safe_float(execution.get("fee_impact_usdt"), 0.0)))
    slippage = abs(_safe_float(overall.get("slippage_impact_usdt"), 0.0))
    total_cost = fee + slippage
    edge = max(abs(_safe_float(overall.get("expectancy_usdt"), 0.0)) * max(1, _safe_int(overall.get("trade_count"), 1)), gross, 0.000001)
    ratio = round(total_cost / edge, 6)
    action = "TRADE_COST_OK" if ratio <= policy["max_cost_to_edge_ratio"] else "HOLD_COST_TOO_HIGH"
    checks = [
        _check("fee_slippage_ratio", "ok" if ratio <= policy["max_cost_to_edge_ratio"] else "review", "Fee/slippage must not consume the edge."),
        _check("execution_rejects", "ok" if _safe_int(execution.get("rejected_order_count"), 0) == 0 else "blocked", "Rejected orders block profitability proof."),
        _check("no_live_action", "ok", "Controller is analytical only."),
    ]
    return {"engine": "autonomous_fee_slippage_break_even_controller", "revision": 172, "status": _final_status(checks), "break_even": {"action": action, "cost_to_edge_ratio": ratio, "max_cost_to_edge_ratio": policy["max_cost_to_edge_ratio"], "fee_usdt": round(fee, 6), "slippage_usdt": round(slippage, 6), "real_submit_close": "OFF"}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "strategy_symbol_micro_allocation_matrix"}


def build_rev173_strategy_symbol_micro_allocation_matrix(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    candidates = _candidate_rows(data, settings, auth_store, username)
    whitelist = set(policy["allowed_symbols"])
    rows = []
    for row in candidates:
        whitelist_ok = not whitelist or row["symbol"] in whitelist
        score = max(0.0, min(100.0, row["profit_factor"] * 25 + row["expectancy_usdt"] * 20 + min(row["trade_count"], 20)))
        notional = round(min(policy["max_allocation_notional_usdt"], max(1.0, score / 100 * policy["max_allocation_notional_usdt"])), 4) if whitelist_ok else 0.0
        rows.append({**row, "allocation_score": round(score, 4), "whitelist_ok": whitelist_ok, "recommended_notional_usdt": notional, "auto_apply": False})
    checks = [
        _check("candidate_matrix", "ok" if rows else "review", "Symbol/strategy allocation matrix is generated.", required=False),
        _check("whitelist_respected", "ok" if all(r.get("whitelist_ok") for r in rows) else "blocked", "Allocation cannot recommend whitelist-external symbols."),
        _check("max_notional_guard", "ok" if all(_safe_float(r.get("recommended_notional_usdt"), 0.0) <= policy["max_allocation_notional_usdt"] for r in rows) else "blocked", "Micro allocation cap is enforced."),
        _check("auto_apply_off", "ok", "Allocation matrix is preview-only."),
    ]
    return {"engine": "autonomous_strategy_symbol_micro_allocation_matrix", "revision": 173, "status": _final_status(checks), "allocation_matrix": {"rows": rows, "max_allocation_notional_usdt": policy["max_allocation_notional_usdt"], "auto_apply": "OFF", "real_submit_close": "OFF"}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "learning_lock_regression_watch"}


def build_rev174_learning_lock_regression_watch(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    sentinel = build_rev135_performance_sentinel_v2(data, settings, auth_store, username)
    action = ((sentinel.get("sentinel_summary") or {}).get("daily") or {}).get("action", "cooldown")
    learning_lock = policy["learning_auto_apply"] or action in {"cooldown", "stop"}
    reasons = []
    if policy["learning_auto_apply"]:
        reasons.append("learning_auto_apply_must_remain_off")
    if action in {"cooldown", "stop"}:
        reasons.append("performance_regression_guard")
    checks = [
        _check("learning_auto_apply_disabled", "ok" if not policy["learning_auto_apply"] else "blocked", "Learning/tuning auto-apply must remain disabled."),
        _check("performance_regression_watch", "ok" if action not in {"cooldown", "stop"} else "review", "Cooldown/stop states lock learning changes.", required=False),
        _check("secret_free_learning_lock", "ok", "No secret or runtime writes are returned."),
    ]
    return {"engine": "autonomous_learning_lock_regression_watch", "revision": 174, "status": _final_status(checks), "learning_lock": {"locked": learning_lock, "reasons": reasons, "sentinel_action": action, "auto_apply": "OFF", "next_action": "hold_learning_changes" if learning_lock else "preview_only_review"}, "auto_apply_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "profitability_proof_decision_packet"}


def build_rev175_profitability_proof_decision_packet(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    policy = _policy(settings)
    edge = build_rev171_post_pilot_edge_validation_gate(data, settings, auth_store, username)
    cost = build_rev172_fee_slippage_break_even_controller(data, settings, auth_store, username)
    allocation = build_rev173_strategy_symbol_micro_allocation_matrix(data, settings, auth_store, username)
    learning = build_rev174_learning_lock_regression_watch(data, settings, auth_store, username)
    capital = build_rev145_capital_protection_summary(data, settings, auth_store, username)
    statuses = [edge.get("status"), cost.get("status"), allocation.get("status"), learning.get("status")]
    allocation_rows = ((allocation.get("allocation_matrix") or {}).get("rows") or [])[:3]
    if "blocked" in statuses or policy["real_submit_enable"]:
        decision = "NO-GO"
    elif "review" in statuses or not policy["owner_profitability_confirmation"]:
        decision = "SHADOW_CONTINUE_REVIEW"
    else:
        decision = "LIMITED_MICRO_PREVIEW_ONLY"
    checks = [
        _check("edge_validation", edge.get("status", "blocked"), "Rev171 edge gate."),
        _check("cost_break_even", cost.get("status", "blocked"), "Rev172 cost controller."),
        _check("allocation_matrix", allocation.get("status", "blocked"), "Rev173 allocation matrix."),
        _check("learning_lock", learning.get("status", "blocked"), "Rev174 learning lock."),
        _check("owner_profitability_confirmation", "ok" if policy["owner_profitability_confirmation"] else "review", "Owner confirmation is needed before any micro preview.", required=False),
        _check("real_submit_stays_off", "ok" if not policy["real_submit_enable"] else "blocked", "Real submit flag must stay off in this block."),
        _check("no_auto_live_action", "ok", "Decision packet cannot place/close orders or scale capital."),
    ]
    summary = {"profitability": decision, "edge": (edge.get("edge_validation") or {}).get("decision"), "cost": (cost.get("break_even") or {}).get("action"), "allocation": "available" if allocation_rows else "none", "learning": "locked" if (learning.get("learning_lock") or {}).get("locked") else "preview", "real_submit_close": "OFF"}
    return {"engine": "autonomous_profitability_proof_decision_packet", "revision": 175, "status": _final_status(checks), "generated_at": now_iso(), "profitability_proof_decision": {"decision": decision, "top_allocations": allocation_rows, "capital_context": capital.get("summary_result", {}), "operator_action": "review_summary_only", "next_action": "continue_shadow_until_edge_is_proven", "real_submit_close": "OFF", "auto_apply": "OFF"}, "summary_result": summary, "outputs": {"edge_validation": edge, "break_even": cost, "allocation_matrix": allocation, "learning_lock": learning}, "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev176_or_manual_profitability_review"}


REV_BUILDERS = {171: build_rev171_post_pilot_edge_validation_gate, 172: build_rev172_fee_slippage_break_even_controller, 173: build_rev173_strategy_symbol_micro_allocation_matrix, 174: build_rev174_learning_lock_regression_watch, 175: build_rev175_profitability_proof_decision_packet}
REV_KEYS = {171: "autonomous_post_pilot_edge_validation_gate", 172: "autonomous_fee_slippage_break_even_controller", 173: "autonomous_strategy_symbol_micro_allocation_matrix", 174: "autonomous_learning_lock_regression_watch", 175: "autonomous_profitability_proof_decision_packet"}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_live_edge_profitability_proof_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev171-175 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 175:
        return {"revision": 175, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("edge_validation", "break_even", "allocation_matrix", "learning_lock"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(171, 176)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_profitability_proof_decision_packet"]
    return {"engine": "autonomous_live_edge_profitability_proof_block", "revision": 175, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("summary_result", {}), "profitability_proof_decision": final.get("profitability_proof_decision", {}), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "manual_profitability_review_before_any_real_activation"}


def build_quality_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    preview = payload.get("command_preview", {})
    checks = [
        _check("route_payload_available", "ok" if payload.get("revision") == int(revision) else "blocked", "Revision payload is available."),
        _check("no_secret_exposure", "ok" if payload.get("contains_secret") is False and payload.get("secret_values_returned") is False else "blocked", "Payload does not expose secrets."),
        _check("network_default_off", "ok" if preview.get("network_default_off") is True and preview.get("sends_exchange_request") is False else "blocked", "No exchange network request."),
        _check("real_submit_default_off", "ok" if preview.get("real_submit_default_off") is True and preview.get("places_order") is False else "blocked", "Real submit is disabled."),
        _check("real_close_default_off", "ok" if preview.get("real_close_default_off") is True and preview.get("submits_close_order") is False else "blocked", "Real close is disabled."),
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "All decisions remain advisory/approval-gated."),
    ]
    return {"engine": "autonomous_live_edge_profitability_proof_quality_gate", "revision": int(revision), "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks), "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "contains_secret": False, "secret_values_returned": False}
