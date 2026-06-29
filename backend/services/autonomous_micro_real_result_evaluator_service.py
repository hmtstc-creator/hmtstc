from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_exit_manager_service import build_autonomous_micro_real_exit_manager


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


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_result_evaluator") if isinstance(settings.get("autonomous_micro_real_result_evaluator"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 93,
        "learning_memory_update_enabled": _safe_bool(raw.get("learning_memory_update_enabled"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "direct_order_enabled": _safe_bool(raw.get("direct_order_enabled"), False),
        "min_realized_roi_pct_for_repeat": _safe_float(raw.get("min_realized_roi_pct_for_repeat"), 0.15),
        "max_negative_roi_pct_before_tighten": abs(_safe_float(raw.get("max_negative_roi_pct_before_tighten"), 0.35)),
        "max_fee_pct_of_notional": max(0.01, _safe_float(raw.get("max_fee_pct_of_notional"), 0.20)),
        "max_slippage_pct": max(0.01, _safe_float(raw.get("max_slippage_pct"), 0.25)),
        "max_latency_ms": max(1.0, _safe_float(raw.get("max_latency_ms"), 2500.0)),
        "min_quality_score_for_promotion": max(1.0, _safe_float(raw.get("min_quality_score_for_promotion"), 70.0)),
        "sample_guard_required": _safe_bool(raw.get("sample_guard_required"), True),
        "min_completed_micro_real_samples": max(1, int(_safe_float(raw.get("min_completed_micro_real_samples"), 3))),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_exit_manager") if isinstance(data.get("autonomous_micro_real_exit_manager"), dict) else None
    if raw and raw.get("revision") == 93 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_exit_manager(data, settings, auth_store, username)


def _latest_fill(data: dict, source: dict) -> dict:
    """Return a sanitized micro-real fill/result snapshot.

    The evaluator can consume a real safe runtime snapshot when supplied by a
    future tracker, but it also produces a deterministic preview from Rev93 data
    so Summary/quality gates remain usable without exchange calls.
    """
    candidates = []
    for key in ("micro_real_exit_fill", "micro_real_result", "micro_real_closed_position", "realized_micro_real_trade"):
        value = data.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    fills = data.get("micro_real_fills")
    if isinstance(fills, list) and fills:
        candidates.extend([item for item in fills if isinstance(item, dict)])
    if candidates:
        fill = deepcopy(candidates[-1])
    else:
        intent = source.get("exit_intent") if isinstance(source.get("exit_intent"), dict) else {}
        plan = source.get("exit_order_plan_preview") if isinstance(source.get("exit_order_plan_preview"), dict) else {}
        fill = {
            "symbol": source.get("symbol") or plan.get("symbol") or "UNKNOWN",
            "side": plan.get("side") or "SELL",
            "quantity": plan.get("quantity") or 0,
            "entry_price": 10000.0,
            "exit_price": 10000.0 + (_safe_float(intent.get("unrealized_pnl_usdt"), 0.0) / max(_safe_float(plan.get("quantity"), 0.0), 0.00000001)),
            "gross_pnl_usdt": _safe_float(intent.get("unrealized_pnl_usdt"), 0.0),
            "fee_usdt": 0.02,
            "slippage_usdt": 0.01,
            "latency_ms": 450,
            "closed_at": now_iso(),
            "source": "rev94_preview_from_exit_manager",
        }
    return fill


def _metrics(fill: dict) -> dict:
    qty = abs(_safe_float(fill.get("quantity"), 0.0))
    entry = _safe_float(fill.get("entry_price"), 0.0)
    exit_price = _safe_float(fill.get("exit_price"), 0.0)
    notional = abs(_safe_float(fill.get("notional_usdt"), 0.0)) or abs(qty * entry)
    gross = _safe_float(fill.get("gross_pnl_usdt"), 0.0)
    if gross == 0.0 and qty > 0 and entry > 0 and exit_price > 0:
        side = str(fill.get("entry_side") or "BUY").upper()
        gross = (exit_price - entry) * qty if side == "BUY" else (entry - exit_price) * qty
    fee = abs(_safe_float(fill.get("fee_usdt"), 0.0))
    slippage = abs(_safe_float(fill.get("slippage_usdt"), 0.0))
    net = gross - fee - slippage
    roi = (net / notional * 100.0) if notional > 0 else 0.0
    fee_pct = (fee / notional * 100.0) if notional > 0 else 0.0
    slippage_pct = (slippage / notional * 100.0) if notional > 0 else 0.0
    return {
        "quantity": qty,
        "entry_price": entry,
        "exit_price": exit_price,
        "notional_usdt": round(notional, 6),
        "gross_pnl_usdt": round(gross, 6),
        "fee_usdt": round(fee, 6),
        "slippage_usdt": round(slippage, 6),
        "net_pnl_usdt": round(net, 6),
        "realized_roi_pct": round(roi, 4),
        "fee_pct_of_notional": round(fee_pct, 4),
        "slippage_pct": round(slippage_pct, 4),
        "latency_ms": round(_safe_float(fill.get("latency_ms"), 0.0), 2),
        "profitable_after_costs": net > 0,
    }


def _samples(data: dict) -> int:
    for key in ("micro_real_completed_sample_count", "completed_micro_real_samples"):
        if key in data:
            return max(0, int(_safe_float(data.get(key), 0)))
    fills = data.get("micro_real_fills")
    return len(fills) if isinstance(fills, list) else 0


def build_autonomous_micro_real_result_evaluator(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev94 micro-real result evaluator.

    Evaluates a completed/previewed micro-real exit result. It analyzes realized
    PnL, fees, slippage, latency and strategy learning feedback without sending
    exchange requests, placing orders or writing runtime state by default.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    command = source.get("command_preview") if isinstance(source.get("command_preview"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("micro_real_result_evaluator_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_exit_manager_revision_mismatch")
    if command.get("approved_for_micro_real_result_evaluator") is not True:
        warnings.append("exit_manager_not_final_close_ready")
    if policy["network_calls_allowed"]:
        blockers.append("network_calls_must_remain_disabled_for_rev94")
    if policy["direct_order_enabled"]:
        blockers.append("direct_order_must_remain_disabled_for_rev94")

    fill = _latest_fill(data, source)
    metrics = _metrics(fill)
    if metrics["notional_usdt"] <= 0:
        blockers.append("result_notional_missing")
    if metrics["quantity"] <= 0:
        blockers.append("result_quantity_missing")
    if metrics["fee_pct_of_notional"] > policy["max_fee_pct_of_notional"]:
        warnings.append("fee_cost_above_policy")
    if metrics["slippage_pct"] > policy["max_slippage_pct"]:
        warnings.append("slippage_above_policy")
    if metrics["latency_ms"] > policy["max_latency_ms"]:
        warnings.append("latency_above_policy")

    completed_samples = _samples(data)
    sample_guard_passed = completed_samples >= policy["min_completed_micro_real_samples"]
    if policy["sample_guard_required"] and not sample_guard_passed:
        warnings.append("sample_guard_collect_more_micro_real_results")

    roi = metrics["realized_roi_pct"]
    quality_base = 78.0
    if metrics["profitable_after_costs"]:
        quality_base += min(12.0, max(0.0, roi) * 2.0)
    else:
        quality_base -= min(25.0, abs(roi) * 8.0 + 8.0)
    quality_base -= len(set(blockers)) * 18.0 + len(set(warnings)) * 4.0
    result_quality_score = max(0.0, min(100.0, quality_base))

    if blockers:
        recommendation = "BLOCK_RESULT_REVIEW"
        evaluator_state = "MICRO_REAL_RESULT_BLOCKED"
        status = "blocked"
    elif roi <= -policy["max_negative_roi_pct_before_tighten"]:
        recommendation = "TIGHTEN_OR_COOLDOWN"
        evaluator_state = "MICRO_REAL_RESULT_TIGHTEN"
        status = "review"
    elif metrics["profitable_after_costs"] and roi >= policy["min_realized_roi_pct_for_repeat"] and sample_guard_passed and result_quality_score >= policy["min_quality_score_for_promotion"]:
        recommendation = "ALLOW_PROMOTION_REVIEW"
        evaluator_state = "MICRO_REAL_RESULT_PROMOTION_REVIEW"
        status = "ok"
    elif metrics["profitable_after_costs"]:
        recommendation = "REPEAT_SMALL_PROBE"
        evaluator_state = "MICRO_REAL_RESULT_REPEAT_SMALL"
        status = "review"
    else:
        recommendation = "HOLD_AND_COLLECT_EVIDENCE"
        evaluator_state = "MICRO_REAL_RESULT_REVIEW"
        status = "review"

    evaluator_id = "mrre_" + sha256(f"rev94:{username}:{source.get('exit_plan_id')}:{metrics['net_pnl_usdt']}:{metrics['realized_roi_pct']}".encode("utf-8")).hexdigest()[:24]
    learning_delta = {
        "signal_accuracy": "positive" if metrics["profitable_after_costs"] else "negative",
        "strategy_feedback": "reinforce" if recommendation in {"ALLOW_PROMOTION_REVIEW", "REPEAT_SMALL_PROBE"} else "tighten_or_observe",
        "risk_feedback": "within_micro_real_limits" if not blockers else "blocked_by_policy",
        "cost_feedback": "costs_ok" if "fee_cost_above_policy" not in warnings and "slippage_above_policy" not in warnings else "costs_need_tightening",
        "memory_update_preview_only": True,
    }

    return {
        "status": status,
        "revision": 94,
        "engine": "autonomous_micro_real_result_evaluator",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "evaluator_state": evaluator_state,
        "evaluator_id": evaluator_id,
        "result_quality_score": round(result_quality_score, 2),
        "source_revision": source.get("revision"),
        "source_exit_plan_id": source.get("exit_plan_id"),
        "symbol": fill.get("symbol") or source.get("symbol"),
        "result_snapshot": {
            "symbol": fill.get("symbol") or source.get("symbol"),
            "side": fill.get("side"),
            "closed_at": fill.get("closed_at") or now_iso(),
            "source": fill.get("source") or "provided_runtime_snapshot",
            "contains_secret": False,
        },
        "realized_result": metrics,
        "cost_analysis": {
            "fee_pct_of_notional": metrics["fee_pct_of_notional"],
            "slippage_pct": metrics["slippage_pct"],
            "latency_ms": metrics["latency_ms"],
            "fee_policy_ok": metrics["fee_pct_of_notional"] <= policy["max_fee_pct_of_notional"],
            "slippage_policy_ok": metrics["slippage_pct"] <= policy["max_slippage_pct"],
            "latency_policy_ok": metrics["latency_ms"] <= policy["max_latency_ms"],
        },
        "sample_guard": {
            "completed_micro_real_samples": completed_samples,
            "required_samples": policy["min_completed_micro_real_samples"],
            "passed": sample_guard_passed,
        },
        "learning_memory_feedback": learning_delta,
        "promotion_signal": {
            "recommendation": recommendation,
            "allow_promotion_review": recommendation == "ALLOW_PROMOTION_REVIEW",
            "allow_size_increase": False,
            "requires_next_controller": True,
        },
        "safety_contract": {
            "network_calls_allowed": policy["network_calls_allowed"],
            "direct_order_enabled": policy["direct_order_enabled"],
            "runtime_write_enabled": policy["runtime_write_enabled"],
            "learning_memory_update_enabled": policy["learning_memory_update_enabled"],
            "contains_secret": False,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": policy,
        "command_preview": {
            "type": "micro_real_result_evaluator_preview",
            "source_revision": 94,
            "evaluator_state": evaluator_state,
            "next_action": recommendation,
            "symbol": fill.get("symbol") or source.get("symbol"),
            "lane": "MICRO_REAL_RESULT_EVALUATOR",
            "read_only": True,
            "auto_apply": False,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "approved_for_micro_real_promotion_demotion_controller": recommendation in {"ALLOW_PROMOTION_REVIEW", "REPEAT_SMALL_PROBE", "TIGHTEN_OR_COOLDOWN"} and not blockers,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    result = payload.get("realized_result") if isinstance(payload.get("realized_result"), dict) else {}
    promotion = payload.get("promotion_signal") if isinstance(payload.get("promotion_signal"), dict) else {}
    sample = payload.get("sample_guard") if isinstance(payload.get("sample_guard"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 94,
        "engine": "autonomous_micro_real_result_evaluator_summary",
        "generated_at": payload.get("generated_at"),
        "evaluator_state": payload.get("evaluator_state"),
        "result_quality_score": payload.get("result_quality_score"),
        "next_action": command.get("next_action"),
        "symbol": payload.get("symbol"),
        "net_pnl_usdt": result.get("net_pnl_usdt"),
        "realized_roi_pct": result.get("realized_roi_pct"),
        "profitable_after_costs": result.get("profitable_after_costs"),
        "recommendation": promotion.get("recommendation"),
        "allow_promotion_review": promotion.get("allow_promotion_review") is True,
        "sample_guard_passed": sample.get("passed") is True,
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "read_only": True,
    }


def build_summary_autonomous_micro_real_result_evaluator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_result_evaluator(data, settings, auth_store, username))


def build_autonomous_micro_real_result_evaluator_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_result_evaluator(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    metrics = payload.get("realized_result") if isinstance(payload.get("realized_result"), dict) else {}
    checks = {
        "revision_is_94": payload.get("revision") == 94,
        "source_exit_manager_chain_present": payload.get("source_revision") == 93,
        "realized_result_present": isinstance(metrics, dict) and "net_pnl_usdt" in metrics and "realized_roi_pct" in metrics,
        "cost_analysis_present": isinstance(payload.get("cost_analysis"), dict),
        "learning_feedback_present": isinstance(payload.get("learning_memory_feedback"), dict) and payload.get("learning_memory_feedback", {}).get("memory_update_preview_only") is True,
        "promotion_signal_present": isinstance(payload.get("promotion_signal"), dict),
        "service_does_not_place_order": payload.get("places_order") is False and command.get("places_order") is False,
        "service_does_not_execute_network_call": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False,
        "service_does_not_write_runtime": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "secret_safe": payload.get("safety_contract", {}).get("contains_secret") is False and payload.get("result_snapshot", {}).get("contains_secret") is False,
        "summary_revision_is_94": _summary_from_payload(payload).get("revision") == 94,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 94,
        "engine": "autonomous_micro_real_result_evaluator_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_RESULT_EVALUATOR_OK" if passed else "MICRO_REAL_RESULT_EVALUATOR_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_state": payload.get("evaluator_state"),
        "sample_action": command.get("next_action"),
    }
