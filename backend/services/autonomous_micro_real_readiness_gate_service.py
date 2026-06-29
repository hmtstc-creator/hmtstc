from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_paper_promotion_gate_service import build_autonomous_paper_promotion_gate
from services.user_api_secret_layer_service import build_user_api_secret_summary


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
    raw = settings.get("autonomous_micro_real_readiness_gate") if isinstance(settings.get("autonomous_micro_real_readiness_gate"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "min_promotion_score": _clamp(_safe_float(raw.get("min_promotion_score"), 78.0), 1.0, 100.0),
        "max_probe_notional_usdt": max(5.0, _safe_float(raw.get("max_probe_notional_usdt"), 25.0)),
        "min_api_readiness": str(raw.get("min_api_readiness") or "ready_for_trade_guarded"),
        "require_trade_permission": _safe_bool(raw.get("require_trade_permission"), True),
        "require_live_environment_for_real": _safe_bool(raw.get("require_live_environment_for_real"), False),
        "max_blocker_count": max(0, _safe_int(raw.get("max_blocker_count"), 0)),
        "read_only": True,
        "auto_apply": False,
        "target_lane": "MICRO_REAL_PREVIEW",
    }


def _promotion(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_paper_promotion_gate") if isinstance(data.get("autonomous_paper_promotion_gate"), dict) else None
    return raw or build_autonomous_paper_promotion_gate(data, settings, auth_store, username)


def _safety_state(data: dict) -> dict:
    safety = data.get("autonomous_safety_supervisor") if isinstance(data.get("autonomous_safety_supervisor"), dict) else {}
    control = data.get("autonomous_control_loop") if isinstance(data.get("autonomous_control_loop"), dict) else {}
    daily = data.get("daily_operation") if isinstance(data.get("daily_operation"), dict) else {}
    return {
        "kill_switch_active": _safe_bool(safety.get("kill_switch_active"), False),
        "safe_mode_required": _safe_bool(safety.get("safe_mode_required"), False),
        "safety_state": safety.get("safety_state") or safety.get("status") or "unknown",
        "autopilot_state": control.get("autopilot_state") or "unknown",
        "daily_mode": daily.get("bot_mode") or daily.get("mode") or "unknown",
    }


def _readiness_score(promotion: dict, api: dict, safety: dict, policy: dict, blockers: list[str], warnings: list[str]) -> float:
    score = _safe_float(promotion.get("promotion_score"), 0.0) * 0.65
    if promotion.get("promotion_state") == "ELIGIBLE_FOR_MICRO_REAL_REVIEW":
        score += 15.0
    if api.get("can_execute_real_trade"):
        score += 12.0
    elif api.get("configured"):
        score += 5.0
        warnings.append("api_configured_without_trade_permission")
    if not safety.get("kill_switch_active") and not safety.get("safe_mode_required"):
        score += 8.0
    if blockers:
        score -= min(45.0, len(set(blockers)) * 12.0)
    if warnings:
        score -= min(10.0, len(set(warnings)) * 2.5)
    return round(_clamp(score), 2)


def _next_action(state: str) -> str:
    if state == "READY_FOR_MICRO_REAL_PROBATION":
        return "BUILD_MICRO_REAL_PROBATION_ORDER_PREVIEW"
    if state == "MICRO_REAL_REVIEW_REQUIRED":
        return "REVIEW_API_SAFETY_OR_PAPER_PROMOTION"
    return "KEEP_IN_PAPER_AND_BLOCK_MICRO_REAL"


def build_autonomous_micro_real_readiness_gate(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev85 read-only gate for paper-to-micro-real probation readiness.

    This service is deliberately not an execution service. It checks whether a
    paper-approved signal is safe enough to move into a tiny micro-real preview
    lane, using API readiness, safety state, paper promotion quality and probe
    notional caps. It never places an order, calls the exchange or writes runtime
    state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    promotion = _promotion(data, settings, auth_store, username)
    api = build_user_api_secret_summary(auth_store, username)
    safety = _safety_state(data)
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("micro_real_readiness_gate_disabled")
    if promotion.get("revision") != 84:
        blockers.append("paper_promotion_revision_mismatch")
    if promotion.get("promotion_state") != "ELIGIBLE_FOR_MICRO_REAL_REVIEW":
        blockers.append("paper_promotion_not_ready")
    if _safe_float(promotion.get("promotion_score"), 0.0) < policy["min_promotion_score"]:
        blockers.append("promotion_score_below_micro_real_floor")
    if str(promotion.get("target_lane") or "").upper() != "MICRO_REAL_PREVIEW":
        blockers.append("target_lane_not_micro_real_preview")
    if policy["require_trade_permission"] and not api.get("can_execute_real_trade"):
        blockers.append("api_trade_permission_not_ready")
    if policy["require_live_environment_for_real"] and str(api.get("environment") or "").lower() != "live":
        blockers.append("live_environment_required_for_micro_real")
    if safety.get("kill_switch_active"):
        blockers.append("kill_switch_active")
    if safety.get("safe_mode_required"):
        blockers.append("safe_mode_required")
    if len(set(blockers)) > policy["max_blocker_count"]:
        warnings.append("blocker_count_above_policy")

    readiness_score = _readiness_score(promotion, api, safety, policy, blockers, warnings)
    if blockers:
        readiness_state = "BLOCKED"
    elif readiness_score >= policy["min_promotion_score"]:
        readiness_state = "READY_FOR_MICRO_REAL_PROBATION"
    else:
        readiness_state = "MICRO_REAL_REVIEW_REQUIRED"
    status = "ok" if readiness_state == "READY_FOR_MICRO_REAL_PROBATION" else ("blocked" if readiness_state == "BLOCKED" else "review")
    next_action = _next_action(readiness_state)
    probe_notional = min(policy["max_probe_notional_usdt"], _safe_float((promotion.get("command_preview") or {}).get("micro_real_probe_notional_usdt"), policy["max_probe_notional_usdt"]))

    return {
        "status": status,
        "revision": 85,
        "engine": "autonomous_micro_real_readiness_gate",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "readiness_state": readiness_state,
        "readiness_score": readiness_score,
        "next_action": next_action,
        "source_lane": promotion.get("source_lane") or "PAPER",
        "target_lane": "MICRO_REAL_PREVIEW" if readiness_state != "BLOCKED" else "PAPER",
        "symbol": promotion.get("symbol"),
        "probe_notional_usdt": round(probe_notional, 4),
        "api_readiness": api.get("readiness"),
        "api_configured": api.get("configured"),
        "api_trade_enabled": api.get("trade_enabled"),
        "api_can_execute_real_trade": api.get("can_execute_real_trade"),
        "exchange": api.get("exchange"),
        "environment": api.get("environment"),
        "promotion_state": promotion.get("promotion_state"),
        "promotion_score": promotion.get("promotion_score"),
        "safety": safety,
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy": policy,
        "inputs": {
            "paper_promotion_revision": promotion.get("revision"),
            "paper_promotion_state": promotion.get("promotion_state"),
            "paper_promotion_target_lane": promotion.get("target_lane"),
            "user_api_revision": api.get("revision"),
            "user_api_readiness": api.get("readiness"),
        },
        "command_preview": {
            "type": "micro_real_readiness_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "source_revision": 85,
            "readiness_state": readiness_state,
            "next_action": next_action,
            "target_lane": "MICRO_REAL_PREVIEW" if readiness_state != "BLOCKED" else "PAPER",
            "probe_notional_usdt": round(probe_notional, 4),
            "requires_final_execution_approval": True,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status"),
        "revision": 85,
        "engine": "autonomous_micro_real_readiness_gate_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "readiness_state": payload.get("readiness_state"),
        "readiness_score": payload.get("readiness_score"),
        "next_action": payload.get("next_action"),
        "symbol": payload.get("symbol"),
        "target_lane": payload.get("target_lane"),
        "probe_notional_usdt": payload.get("probe_notional_usdt"),
        "api_readiness": payload.get("api_readiness"),
        "api_configured": payload.get("api_configured"),
        "api_trade_enabled": payload.get("api_trade_enabled"),
        "promotion_state": payload.get("promotion_state"),
        "promotion_score": payload.get("promotion_score"),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_summary_autonomous_micro_real_readiness_gate(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_readiness_gate(data, settings, auth_store, username))


def build_autonomous_micro_real_readiness_gate_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_readiness_gate(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    summary = _summary_from_payload(payload)
    checks = {
        "revision_is_85": payload.get("revision") == 85,
        "paper_promotion_chain_present": (payload.get("inputs") or {}).get("paper_promotion_revision") == 84,
        "api_secret_chain_present": (payload.get("inputs") or {}).get("user_api_revision") == 67,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order_placement": command.get("places_order") is False,
        "no_exchange_request": command.get("sends_exchange_request") is False,
        "no_runtime_write": command.get("writes_runtime_state") is False,
        "readiness_contract_present": all(key in payload for key in ("readiness_state", "readiness_score", "target_lane", "next_action")),
        "summary_revision_is_85": summary.get("revision") == 85,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 85,
        "engine": "autonomous_micro_real_readiness_gate_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_READINESS_GATE_OK" if passed else "MICRO_REAL_READINESS_GATE_REVIEW",
        "checks": checks,
        "summary": summary,
        "sample_state": payload.get("readiness_state"),
        "sample_action": payload.get("next_action"),
    }
