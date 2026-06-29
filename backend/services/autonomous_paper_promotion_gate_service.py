from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_paper_result_evaluator_service import build_autonomous_paper_result_evaluator


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
    raw = settings.get("autonomous_paper_promotion_gate") if isinstance(settings.get("autonomous_paper_promotion_gate"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_result_quality_score": _clamp(_safe_float(raw.get("min_result_quality_score"), 76.0), 1.0, 100.0),
        "min_roi_pct": _safe_float(raw.get("min_roi_pct"), 0.05),
        "max_warning_count": max(0, _safe_int(raw.get("max_warning_count"), 2)),
        "min_required_paper_samples": max(1, _safe_int(raw.get("min_required_paper_samples"), 1)),
        "micro_real_probe_notional_usdt": max(5.0, _safe_float(raw.get("micro_real_probe_notional_usdt"), 25.0)),
        "read_only": True,
        "auto_apply": False,
        "paper_to_micro_real_only": True,
    }


def _evaluator(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_paper_result_evaluator") if isinstance(data.get("autonomous_paper_result_evaluator"), dict) else None
    return raw or build_autonomous_paper_result_evaluator(data, settings, auth_store, username)


def _paper_sample_count(data: dict, evaluator: dict) -> int:
    explicit = _safe_int(data.get("paper_passed_sample_count"), 0)
    if explicit > 0:
        return explicit
    memory = data.get("autonomous_evidence_learning_memory") if isinstance(data.get("autonomous_evidence_learning_memory"), dict) else {}
    learned = _safe_int(memory.get("passed_paper_sample_count"), 0)
    if learned > 0:
        return learned
    return 1 if evaluator.get("evaluation_state") == "PASSED" else 0


def _promotion_score(evaluator: dict, result: dict, sample_count: int, policy: dict, blockers: list[str], warnings: list[str]) -> float:
    base = _safe_float(evaluator.get("paper_result_quality_score"), 0.0) * 0.72
    roi = _safe_float(result.get("roi_pct"), 0.0)
    net = _safe_float(result.get("net_pnl_usdt"), 0.0)
    if result.get("profitable_after_costs"):
        base += 12.0
    if roi >= policy["min_roi_pct"]:
        base += 8.0
    else:
        warnings.append("paper_roi_below_promotion_floor")
    if net > 0:
        base += 5.0
    if sample_count >= policy["min_required_paper_samples"]:
        base += 5.0
    else:
        blockers.append("insufficient_paper_sample_count")
    if blockers:
        base -= min(45.0, len(set(blockers)) * 10.0)
    if warnings:
        base -= min(12.0, len(set(warnings)) * 3.0)
    return round(_clamp(base), 2)


def _next_action(state: str) -> str:
    if state == "ELIGIBLE_FOR_MICRO_REAL_REVIEW":
        return "PREPARE_MICRO_REAL_PROBATION_PREVIEW"
    if state == "PAPER_REPEAT_REQUIRED":
        return "RUN_ADDITIONAL_PAPER_SAMPLE"
    if state == "BLOCKED":
        return "KEEP_SIGNAL_IN_PAPER_OR_BLOCK"
    return "REVIEW_PAPER_PROMOTION_INPUTS"


def build_autonomous_paper_promotion_gate(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev84 read-only paper-to-micro-real promotion gate.

    This gate converts Rev83 paper result quality into a controlled promotion
    decision. It does not place orders, call exchanges, write runtime state, or
    auto-promote the bot. It only says whether the signal is ready for a
    micro-real probation preview.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    evaluator = _evaluator(data, settings, auth_store, username)
    result = evaluator.get("paper_result") if isinstance(evaluator.get("paper_result"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = list(evaluator.get("warnings") or []) if isinstance(evaluator.get("warnings"), list) else []

    if not policy["enabled"]:
        blockers.append("paper_promotion_gate_disabled")
    if evaluator.get("revision") != 83:
        blockers.append("paper_result_evaluator_revision_mismatch")
    if evaluator.get("evaluation_state") != "PASSED":
        blockers.append("paper_result_not_passed")
    if _safe_float(evaluator.get("paper_result_quality_score"), 0.0) < policy["min_result_quality_score"]:
        blockers.append("paper_result_quality_below_promotion_floor")
    if result.get("profitable_after_costs") is not True:
        blockers.append("paper_result_not_profitable_after_costs")
    if str(result.get("lane") or "PAPER").upper() != "PAPER":
        blockers.append("promotion_source_lane_not_paper")
    if len(set(warnings)) > policy["max_warning_count"]:
        blockers.append("too_many_paper_warnings_for_promotion")

    sample_count = _paper_sample_count(data, evaluator)
    promotion_score = _promotion_score(evaluator, result, sample_count, policy, blockers, warnings)

    if blockers:
        promotion_state = "BLOCKED"
    elif promotion_score >= policy["min_result_quality_score"]:
        promotion_state = "ELIGIBLE_FOR_MICRO_REAL_REVIEW"
    else:
        promotion_state = "PAPER_REPEAT_REQUIRED"

    status = "ok" if promotion_state == "ELIGIBLE_FOR_MICRO_REAL_REVIEW" else ("blocked" if promotion_state == "BLOCKED" else "review")
    next_action = _next_action(promotion_state)

    return {
        "status": status,
        "revision": 84,
        "engine": "autonomous_paper_promotion_gate",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "promotion_state": promotion_state,
        "next_action": next_action,
        "promotion_score": promotion_score,
        "source_lane": result.get("lane") or "PAPER",
        "target_lane": "MICRO_REAL_PREVIEW" if promotion_state == "ELIGIBLE_FOR_MICRO_REAL_REVIEW" else "PAPER",
        "symbol": result.get("symbol") or (evaluator.get("inputs") or {}).get("symbol"),
        "paper_samples": sample_count,
        "paper_result_quality_score": evaluator.get("paper_result_quality_score"),
        "paper_roi_pct": result.get("roi_pct"),
        "paper_net_pnl_usdt": result.get("net_pnl_usdt"),
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy": policy,
        "inputs": {
            "paper_result_evaluator_revision": evaluator.get("revision"),
            "paper_evaluation_state": evaluator.get("evaluation_state"),
            "paper_next_action": evaluator.get("next_action"),
            "paper_profitable_after_costs": result.get("profitable_after_costs"),
        },
        "command_preview": {
            "type": "paper_promotion_gate_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "source_revision": 84,
            "promotion_state": promotion_state,
            "next_action": next_action,
            "target_lane": "MICRO_REAL_PREVIEW" if promotion_state == "ELIGIBLE_FOR_MICRO_REAL_REVIEW" else "PAPER",
            "micro_real_probe_notional_usdt": policy["micro_real_probe_notional_usdt"],
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 84,
        "engine": "autonomous_paper_promotion_gate_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "promotion_state": payload.get("promotion_state"),
        "next_action": payload.get("next_action"),
        "promotion_score": payload.get("promotion_score"),
        "symbol": payload.get("symbol"),
        "source_lane": payload.get("source_lane"),
        "target_lane": payload.get("target_lane"),
        "paper_samples": payload.get("paper_samples"),
        "paper_roi_pct": payload.get("paper_roi_pct"),
        "paper_net_pnl_usdt": payload.get("paper_net_pnl_usdt"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_paper_promotion_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_paper_promotion_gate(data, settings, auth_store, username))


def build_autonomous_paper_promotion_gate_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_paper_promotion_gate(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_84": payload.get("revision") == 84,
        "paper_result_chain_present": (payload.get("inputs") or {}).get("paper_result_evaluator_revision") == 83,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": command.get("places_order") is False,
        "no_exchange_request": command.get("sends_exchange_request") is False,
        "no_runtime_write": command.get("writes_runtime_state") is False,
        "promotion_contract_present": all(key in payload for key in ("promotion_state", "promotion_score", "target_lane", "next_action")),
        "summary_revision_is_84": summary.get("revision") == 84,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 84,
        "engine": "autonomous_paper_promotion_gate_quality",
        "generated_at": now_iso(),
        "quality_status": "PAPER_PROMOTION_GATE_OK" if passed else "PAPER_PROMOTION_GATE_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("promotion_state"),
        "sample_action": payload.get("next_action"),
    }
