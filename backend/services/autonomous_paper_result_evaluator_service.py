from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_paper_execution_runner_service import build_autonomous_paper_execution_runner


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
    raw = settings.get("autonomous_paper_result_evaluator") if isinstance(settings.get("autonomous_paper_result_evaluator"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_runner_score": _clamp(_safe_float(raw.get("min_runner_score"), 72.0), 1.0, 100.0),
        "min_quality_score": _clamp(_safe_float(raw.get("min_quality_score"), 68.0), 1.0, 100.0),
        "target_move_pct": _safe_float(raw.get("target_move_pct"), 0.45),
        "adverse_move_pct": _safe_float(raw.get("adverse_move_pct"), -0.20),
        "breakeven_buffer_pct": max(0.0, _safe_float(raw.get("breakeven_buffer_pct"), 0.04)),
        "read_only": True,
        "auto_apply": False,
        "paper_only": True,
    }


def _runner(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_paper_execution_runner") if isinstance(data.get("autonomous_paper_execution_runner"), dict) else None
    return raw or build_autonomous_paper_execution_runner(data, settings, auth_store, username)


def _effective_move_pct(fill: dict, policy: dict, runner: dict) -> float:
    explicit = fill.get("paper_exit_move_pct")
    if explicit is not None:
        return _safe_float(explicit, 0.0)
    warnings = runner.get("warnings") if isinstance(runner.get("warnings"), list) else []
    blockers = runner.get("blockers") if isinstance(runner.get("blockers"), list) else []
    if blockers:
        return policy["adverse_move_pct"]
    if warnings:
        return policy["target_move_pct"] * 0.45
    return policy["target_move_pct"]


def _pnl(fill: dict, policy: dict, runner: dict) -> dict:
    notional = max(0.0, _safe_float(fill.get("notional_usdt"), 0.0))
    open_cost = max(0.0, _safe_float(fill.get("net_open_cost_usdt"), 0.0))
    fee_pct = max(0.0, _safe_float(fill.get("fee_pct"), 0.0))
    close_fee_usdt = round(notional * fee_pct / 100.0, 6)
    move_pct = _effective_move_pct(fill, policy, runner)
    side = str(fill.get("side") or "BUY").upper()
    signed_move_pct = move_pct if side == "BUY" else -move_pct
    gross_pnl = round(notional * signed_move_pct / 100.0, 6)
    net_pnl = round(gross_pnl - open_cost - close_fee_usdt, 6)
    roi_pct = round((net_pnl / notional * 100.0), 6) if notional > 0 else 0.0
    breakeven_pct = round(((open_cost + close_fee_usdt) / notional * 100.0) + policy["breakeven_buffer_pct"], 6) if notional > 0 else 0.0
    return {
        "symbol": fill.get("symbol"),
        "lane": fill.get("lane"),
        "side": side,
        "notional_usdt": round(notional, 4),
        "paper_fill_price": fill.get("paper_fill_price"),
        "paper_quantity": fill.get("paper_quantity"),
        "assumed_exit_move_pct": round(move_pct, 6),
        "gross_pnl_usdt": gross_pnl,
        "open_cost_usdt": round(open_cost, 6),
        "estimated_close_fee_usdt": close_fee_usdt,
        "net_pnl_usdt": net_pnl,
        "roi_pct": roi_pct,
        "breakeven_move_pct": breakeven_pct,
        "profitable_after_costs": net_pnl > 0,
    }


def _quality_score(runner: dict, result: dict, blockers: list[str], warnings: list[str]) -> float:
    runner_score = _safe_float(runner.get("paper_execution_score"), 0.0)
    score = runner_score * 0.60
    if result.get("profitable_after_costs"):
        score += 22.0
    else:
        warnings.append("paper_result_not_profitable_after_costs")
        score -= 10.0
    if _safe_float(result.get("roi_pct"), 0.0) >= _safe_float(result.get("breakeven_move_pct"), 0.0):
        score += 8.0
    else:
        warnings.append("paper_roi_below_breakeven_buffer")
    if _safe_float(result.get("net_pnl_usdt"), 0.0) >= 0:
        score += 6.0
    if blockers:
        score -= min(45.0, len(set(blockers)) * 11.0)
    if warnings:
        score -= min(16.0, len(set(warnings)) * 3.0)
    return round(_clamp(score), 2)


def _next_action(score: float, result: dict, blockers: list[str]) -> str:
    if blockers:
        return "BLOCK_PAPER_LEARNING_CHAIN"
    if score >= 78 and result.get("profitable_after_costs"):
        return "PROMOTE_SIGNAL_FOR_PAPER_REPEAT"
    if score >= 62:
        return "KEEP_IN_PAPER_REVIEW"
    return "TIGHTEN_SIGNAL_AND_COST_FILTERS"


def build_autonomous_paper_result_evaluator(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev83 read-only paper result evaluator.

    Evaluates a Rev82 paper fill after estimated fee/spread/slippage impact and
    exposes whether the signal is worth repeating in paper. It does not place
    orders, call an exchange, write runtime state, or auto-apply tuning.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    runner = _runner(data, settings, auth_store, username)
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("paper_result_evaluator_disabled")
    if runner.get("execution_state") != "PAPER_EXECUTED":
        blockers.append("paper_execution_not_available")
    if _safe_float(runner.get("paper_execution_score"), 0.0) < policy["min_runner_score"]:
        blockers.append("paper_runner_score_below_evaluator_floor")

    fill = runner.get("paper_fill") if isinstance(runner.get("paper_fill"), dict) else {}
    if not fill.get("paper_filled"):
        blockers.append("paper_fill_missing_or_not_filled")

    generated_at = now_iso()
    result = _pnl(fill, policy, runner) if fill else {}
    quality_score = _quality_score(runner, result, blockers, warnings) if result else 0.0

    if blockers:
        evaluation_state = "BLOCKED"
    elif quality_score >= policy["min_quality_score"] and result.get("profitable_after_costs"):
        evaluation_state = "PASSED"
    else:
        evaluation_state = "REVIEW"

    next_action = _next_action(quality_score, result, blockers)

    return {
        "status": "ok" if evaluation_state == "PASSED" else ("blocked" if evaluation_state == "BLOCKED" else "review"),
        "revision": 83,
        "engine": "autonomous_paper_result_evaluator",
        "generated_at": generated_at,
        "read_only": True,
        "auto_apply": False,
        "paper_only": True,
        "evaluation_state": evaluation_state,
        "next_action": next_action,
        "paper_result_quality_score": quality_score,
        "paper_result": result,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "inputs": {
            "runner_revision": runner.get("revision"),
            "runner_state": runner.get("execution_state"),
            "paper_execution_score": runner.get("paper_execution_score"),
            "paper_execution_id": fill.get("paper_execution_id"),
            "symbol": fill.get("symbol"),
            "lane": fill.get("lane"),
        },
        "policy": policy,
        "command_preview": {
            "type": "paper_result_evaluator_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "paper_only": True,
            "source_revision": 83,
            "evaluation_state": evaluation_state,
            "next_action": next_action,
            "symbol": fill.get("symbol"),
            "lane": fill.get("lane"),
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    result = payload.get("paper_result") if isinstance(payload.get("paper_result"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 83,
        "engine": "autonomous_paper_result_evaluator_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "evaluation_state": payload.get("evaluation_state"),
        "next_action": payload.get("next_action"),
        "paper_result_quality_score": payload.get("paper_result_quality_score"),
        "symbol": result.get("symbol") or (payload.get("inputs") or {}).get("symbol"),
        "lane": result.get("lane") or (payload.get("inputs") or {}).get("lane"),
        "net_pnl_usdt": result.get("net_pnl_usdt"),
        "roi_pct": result.get("roi_pct"),
        "profitable_after_costs": result.get("profitable_after_costs") is True,
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_paper_result_evaluator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_paper_result_evaluator(data, settings, auth_store, username))


def build_autonomous_paper_result_evaluator_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_paper_result_evaluator(data, settings, auth_store, username)
    summary = _summary_from_payload(payload)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    result = payload.get("paper_result") if isinstance(payload.get("paper_result"), dict) else {}
    checks = {
        "revision_is_83": payload.get("revision") == 83,
        "runner_chain_present": (payload.get("inputs") or {}).get("runner_revision") == 82,
        "paper_only": payload.get("paper_only") is True and command.get("paper_only") is True,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": command.get("places_order") is False,
        "no_exchange_request": command.get("sends_exchange_request") is False,
        "no_runtime_write": command.get("writes_runtime_state") is False,
        "pnl_contract_present": all(key in result for key in ("net_pnl_usdt", "roi_pct", "profitable_after_costs")) if result else payload.get("status") == "blocked",
        "summary_revision_is_83": summary.get("revision") == 83,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 83,
        "engine": "autonomous_paper_result_evaluator_quality",
        "generated_at": now_iso(),
        "quality_status": "PAPER_RESULT_EVALUATOR_OK" if passed else "PAPER_RESULT_EVALUATOR_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("evaluation_state"),
        "sample_action": payload.get("next_action"),
    }
