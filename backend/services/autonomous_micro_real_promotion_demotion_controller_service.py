from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_micro_real_result_evaluator_service import build_autonomous_micro_real_result_evaluator


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


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_micro_real_promotion_demotion_controller") if isinstance(settings.get("autonomous_micro_real_promotion_demotion_controller"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 94,
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "direct_order_enabled": _safe_bool(raw.get("direct_order_enabled"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "auto_apply_enabled": _safe_bool(raw.get("auto_apply_enabled"), False),
        "min_probe_sample_size": max(1, _safe_int(raw.get("min_probe_sample_size"), 5)),
        "min_win_rate_for_increase": max(0.0, min(100.0, _safe_float(raw.get("min_win_rate_for_increase"), 65.0))),
        "min_profit_factor_for_increase": max(0.0, _safe_float(raw.get("min_profit_factor_for_increase"), 1.35)),
        "max_drawdown_pct_for_increase": max(0.0, _safe_float(raw.get("max_drawdown_pct_for_increase"), 2.0)),
        "max_drawdown_pct_before_stop": max(0.0, _safe_float(raw.get("max_drawdown_pct_before_stop"), 4.0)),
        "max_loss_streak_before_reduce": max(1, _safe_int(raw.get("max_loss_streak_before_reduce"), 2)),
        "max_loss_streak_before_stop": max(1, _safe_int(raw.get("max_loss_streak_before_stop"), 3)),
        "min_quality_score_for_increase": max(1.0, min(100.0, _safe_float(raw.get("min_quality_score_for_increase"), 78.0))),
        "reduce_notional_factor": max(0.05, min(1.0, _safe_float(raw.get("reduce_notional_factor"), 0.5))),
        "increase_notional_factor": max(1.0, min(2.0, _safe_float(raw.get("increase_notional_factor"), 1.25))),
        "absolute_micro_notional_cap_usdt": max(1.0, _safe_float(raw.get("absolute_micro_notional_cap_usdt"), 25.0)),
        "cooldown_minutes_after_reduce": max(0, _safe_int(raw.get("cooldown_minutes_after_reduce"), 60)),
        "cooldown_minutes_after_stop": max(0, _safe_int(raw.get("cooldown_minutes_after_stop"), 240)),
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_micro_real_result_evaluator") if isinstance(data.get("autonomous_micro_real_result_evaluator"), dict) else None
    if raw and raw.get("revision") == 94 and "command_preview" in raw:
        return raw
    return build_autonomous_micro_real_result_evaluator(data, settings, auth_store, username)


def _completed_results(data: dict, source: dict) -> list[dict]:
    candidates: list[dict] = []
    for key in ("micro_real_result_history", "micro_real_results", "micro_real_evaluations"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    if not candidates:
        candidates.append(source)
    return candidates[-50:]


def _result_metrics(item: dict) -> dict:
    realized = item.get("realized_result") if isinstance(item.get("realized_result"), dict) else item
    roi = _safe_float(realized.get("realized_roi_pct"), _safe_float(item.get("realized_roi_pct"), 0.0))
    net = _safe_float(realized.get("net_pnl_usdt"), _safe_float(item.get("net_pnl_usdt"), 0.0))
    notional = abs(_safe_float(realized.get("notional_usdt"), _safe_float(item.get("notional_usdt"), 0.0)))
    quality = _safe_float(item.get("result_quality_score"), _safe_float(item.get("quality_score"), 0.0))
    return {"roi": roi, "net": net, "notional": notional, "quality": quality, "win": net > 0}


def _portfolio_stats(results: list[dict], source: dict) -> dict:
    rows = [_result_metrics(item) for item in results]
    sample_size = len(rows)
    wins = [row for row in rows if row["win"]]
    losses = [row for row in rows if not row["win"]]
    gross_profit = sum(max(0.0, row["net"]) for row in rows)
    gross_loss = abs(sum(min(0.0, row["net"]) for row in rows))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    win_rate = (len(wins) / sample_size * 100.0) if sample_size else 0.0
    total_net = sum(row["net"] for row in rows)
    total_notional = sum(row["notional"] for row in rows) or abs(_safe_float((source.get("realized_result") or {}).get("notional_usdt"), 0.0))
    roi_avg = sum(row["roi"] for row in rows) / sample_size if sample_size else 0.0
    quality_avg = sum(row["quality"] for row in rows) / sample_size if sample_size else 0.0
    loss_streak = 0
    for row in reversed(rows):
        if row["win"]:
            break
        loss_streak += 1
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for row in rows:
        equity += row["net"]
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    drawdown_pct = (max_drawdown / total_notional * 100.0) if total_notional > 0 else 0.0
    return {
        "sample_size": sample_size,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 4),
        "total_net_pnl_usdt": round(total_net, 6),
        "average_roi_pct": round(roi_avg, 4),
        "average_quality_score": round(quality_avg, 2),
        "loss_streak": loss_streak,
        "max_drawdown_pct": round(drawdown_pct, 4),
        "total_notional_usdt": round(total_notional, 6),
    }


def _current_notional(data: dict, source: dict) -> float:
    for key in ("current_micro_notional_usdt", "micro_real_probe_notional_usdt", "last_micro_real_notional_usdt"):
        if key in data:
            value = _safe_float(data.get(key), 0.0)
            if value > 0:
                return value
    realized = source.get("realized_result") if isinstance(source.get("realized_result"), dict) else {}
    return max(0.0, _safe_float(realized.get("notional_usdt"), 0.0)) or 10.0


def build_autonomous_micro_real_promotion_demotion_controller(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev95 micro-real promotion/demotion controller.

    Converts Rev94 micro-real results into a controlled size/risk decision:
    increase, hold, reduce or stop. It is preview-only, never places orders,
    never calls an exchange and never writes runtime state by default.
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
        blockers.append("micro_real_promotion_demotion_controller_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_result_evaluator_revision_mismatch")
    if command.get("approved_for_micro_real_promotion_demotion_controller") is not True:
        warnings.append("result_evaluator_not_ready_for_controller")
    if policy["network_calls_allowed"]:
        blockers.append("network_calls_must_remain_disabled_for_rev95")
    if policy["direct_order_enabled"]:
        blockers.append("direct_order_must_remain_disabled_for_rev95")
    if policy["runtime_write_enabled"]:
        blockers.append("runtime_write_must_remain_disabled_for_rev95")
    if policy["auto_apply_enabled"]:
        blockers.append("auto_apply_must_remain_disabled_for_rev95")

    results = _completed_results(data, source)
    stats = _portfolio_stats(results, source)
    sample_guard_passed = stats["sample_size"] >= policy["min_probe_sample_size"]
    if not sample_guard_passed:
        warnings.append("collect_more_micro_real_samples")

    source_status = str(source.get("status") or "review")
    source_recommendation = str(((source.get("promotion_signal") or {}) if isinstance(source.get("promotion_signal"), dict) else {}).get("recommendation") or command.get("next_action") or "").upper()
    if source_status == "blocked":
        blockers.append("source_result_evaluator_blocked")

    current_notional = _current_notional(data, source)
    increase_target = min(policy["absolute_micro_notional_cap_usdt"], current_notional * policy["increase_notional_factor"])
    reduce_target = max(1.0, current_notional * policy["reduce_notional_factor"])

    stop_condition = (
        bool(blockers)
        or stats["loss_streak"] >= policy["max_loss_streak_before_stop"]
        or stats["max_drawdown_pct"] >= policy["max_drawdown_pct_before_stop"]
        or source_recommendation in {"BLOCK_RESULT_REVIEW"}
    )
    reduce_condition = (
        not stop_condition
        and (
            stats["loss_streak"] >= policy["max_loss_streak_before_reduce"]
            or source_recommendation in {"TIGHTEN_OR_COOLDOWN"}
            or stats["average_roi_pct"] < 0
        )
    )
    increase_condition = (
        not stop_condition
        and not reduce_condition
        and sample_guard_passed
        and stats["win_rate_pct"] >= policy["min_win_rate_for_increase"]
        and stats["profit_factor"] >= policy["min_profit_factor_for_increase"]
        and stats["max_drawdown_pct"] <= policy["max_drawdown_pct_for_increase"]
        and stats["average_quality_score"] >= policy["min_quality_score_for_increase"]
        and source_recommendation in {"ALLOW_PROMOTION_REVIEW"}
    )

    if stop_condition:
        decision = "stop"
        controller_state = "MICRO_REAL_SCALE_STOP"
        next_action = "STOP_MICRO_REAL_AND_REVIEW"
        target_notional = 0.0
        cooldown_minutes = policy["cooldown_minutes_after_stop"]
        status = "blocked" if blockers else "review"
    elif reduce_condition:
        decision = "reduce"
        controller_state = "MICRO_REAL_SCALE_REDUCE"
        next_action = "REDUCE_PROBE_SIZE_AND_COOLDOWN"
        target_notional = reduce_target
        cooldown_minutes = policy["cooldown_minutes_after_reduce"]
        status = "review"
    elif increase_condition:
        decision = "increase"
        controller_state = "MICRO_REAL_SCALE_INCREASE_REVIEW"
        next_action = "ALLOW_SMALL_SIZE_INCREASE_PREVIEW"
        target_notional = increase_target
        cooldown_minutes = 0
        status = "ok"
    else:
        decision = "hold"
        controller_state = "MICRO_REAL_SCALE_HOLD"
        next_action = "HOLD_CURRENT_MICRO_SIZE"
        target_notional = current_notional
        cooldown_minutes = 0
        status = "review" if warnings else "ok"

    score = 50.0
    score += min(20.0, max(0.0, stats["win_rate_pct"] - 50.0) * 0.5)
    score += min(15.0, max(0.0, stats["profit_factor"] - 1.0) * 10.0)
    score += min(10.0, max(0.0, stats["average_roi_pct"]) * 2.0)
    score += min(10.0, max(0.0, stats["average_quality_score"] - 70.0) * 0.35)
    score -= min(20.0, stats["max_drawdown_pct"] * 4.0)
    score -= stats["loss_streak"] * 7.0
    score -= len(set(blockers)) * 20.0 + len(set(warnings)) * 4.0
    controller_score = max(0.0, min(100.0, score))

    controller_id = "mrpdc_" + sha256(f"rev95:{username}:{source.get('evaluator_id')}:{decision}:{target_notional}".encode("utf-8")).hexdigest()[:24]
    evidence = {
        "sample_guard_passed": sample_guard_passed,
        "increase_criteria": {
            "win_rate_ok": stats["win_rate_pct"] >= policy["min_win_rate_for_increase"],
            "profit_factor_ok": stats["profit_factor"] >= policy["min_profit_factor_for_increase"],
            "drawdown_ok": stats["max_drawdown_pct"] <= policy["max_drawdown_pct_for_increase"],
            "quality_ok": stats["average_quality_score"] >= policy["min_quality_score_for_increase"],
            "source_allows_promotion_review": source_recommendation == "ALLOW_PROMOTION_REVIEW",
        },
        "reduce_criteria": {
            "loss_streak_reduce": stats["loss_streak"] >= policy["max_loss_streak_before_reduce"],
            "negative_average_roi": stats["average_roi_pct"] < 0,
            "source_tighten": source_recommendation == "TIGHTEN_OR_COOLDOWN",
        },
        "stop_criteria": {
            "loss_streak_stop": stats["loss_streak"] >= policy["max_loss_streak_before_stop"],
            "drawdown_stop": stats["max_drawdown_pct"] >= policy["max_drawdown_pct_before_stop"],
            "source_blocked": source_status == "blocked",
        },
    }

    return {
        "status": status,
        "revision": 95,
        "engine": "autonomous_micro_real_promotion_demotion_controller",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "dry_run": True,
        "places_order": False,
        "sends_exchange_request": False,
        "writes_runtime_state": False,
        "controller_state": controller_state,
        "controller_id": controller_id,
        "controller_score": round(controller_score, 2),
        "source_revision": source.get("revision"),
        "source_evaluator_id": source.get("evaluator_id"),
        "source_recommendation": source_recommendation,
        "decision": decision,
        "next_action": next_action,
        "micro_real_scale_decision": {
            "decision": decision,
            "current_notional_usdt": round(current_notional, 6),
            "target_notional_usdt": round(target_notional, 6),
            "increase_allowed_preview": decision == "increase",
            "reduce_required_preview": decision == "reduce",
            "stop_required_preview": decision == "stop",
            "hold_required_preview": decision == "hold",
            "cooldown_minutes": cooldown_minutes,
            "auto_apply": False,
        },
        "performance_window": stats,
        "controller_evidence": evidence,
        "safety_contract": {
            "network_calls_allowed": policy["network_calls_allowed"],
            "direct_order_enabled": policy["direct_order_enabled"],
            "runtime_write_enabled": policy["runtime_write_enabled"],
            "auto_apply_enabled": policy["auto_apply_enabled"],
            "contains_secret": False,
        },
        "blockers": sorted(set(str(item) for item in blockers if item)),
        "warnings": sorted(set(str(item) for item in warnings if item)),
        "policy_public": policy,
        "command_preview": {
            "type": "micro_real_promotion_demotion_controller_preview",
            "source_revision": 95,
            "controller_state": controller_state,
            "next_action": next_action,
            "decision": decision,
            "target_notional_usdt": round(target_notional, 6),
            "lane": "MICRO_REAL_PROMOTION_DEMOTION_CONTROLLER",
            "read_only": True,
            "auto_apply": False,
            "dry_run": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "approved_for_semi_autonomous_real_lane_review": decision == "increase" and status == "ok" and not blockers,
        },
    }


def _summary_from_payload(payload: dict) -> dict:
    scale = payload.get("micro_real_scale_decision") if isinstance(payload.get("micro_real_scale_decision"), dict) else {}
    stats = payload.get("performance_window") if isinstance(payload.get("performance_window"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 95,
        "engine": "autonomous_micro_real_promotion_demotion_controller_summary",
        "generated_at": payload.get("generated_at"),
        "controller_state": payload.get("controller_state"),
        "controller_score": payload.get("controller_score"),
        "decision": payload.get("decision"),
        "next_action": payload.get("next_action"),
        "current_notional_usdt": scale.get("current_notional_usdt"),
        "target_notional_usdt": scale.get("target_notional_usdt"),
        "cooldown_minutes": scale.get("cooldown_minutes"),
        "sample_size": stats.get("sample_size"),
        "win_rate_pct": stats.get("win_rate_pct"),
        "profit_factor": stats.get("profit_factor"),
        "max_drawdown_pct": stats.get("max_drawdown_pct"),
        "loss_streak": stats.get("loss_streak"),
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "read_only": True,
        "auto_apply": False,
    }


def build_summary_autonomous_micro_real_promotion_demotion_controller(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_micro_real_promotion_demotion_controller(data, settings, auth_store, username))


def build_autonomous_micro_real_promotion_demotion_controller_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_micro_real_promotion_demotion_controller(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    scale = payload.get("micro_real_scale_decision") if isinstance(payload.get("micro_real_scale_decision"), dict) else {}
    checks = {
        "revision_is_95": payload.get("revision") == 95,
        "source_result_evaluator_chain_present": payload.get("source_revision") == 94,
        "decision_is_limited_to_four_states": payload.get("decision") in {"increase", "hold", "reduce", "stop"},
        "performance_window_present": isinstance(payload.get("performance_window"), dict) and "win_rate_pct" in payload.get("performance_window", {}),
        "scale_decision_present": isinstance(scale, dict) and "target_notional_usdt" in scale,
        "service_does_not_place_order": payload.get("places_order") is False and command.get("places_order") is False,
        "service_does_not_execute_network_call": payload.get("sends_exchange_request") is False and command.get("sends_exchange_request") is False,
        "service_does_not_write_runtime": payload.get("writes_runtime_state") is False and command.get("writes_runtime_state") is False,
        "auto_apply_off": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "secret_safe": payload.get("safety_contract", {}).get("contains_secret") is False,
        "summary_revision_is_95": _summary_from_payload(payload).get("revision") == 95,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 95,
        "engine": "autonomous_micro_real_promotion_demotion_controller_quality",
        "generated_at": now_iso(),
        "quality_status": "MICRO_REAL_PROMOTION_DEMOTION_CONTROLLER_OK" if passed else "MICRO_REAL_PROMOTION_DEMOTION_CONTROLLER_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_state": payload.get("controller_state"),
        "sample_action": command.get("next_action"),
    }
