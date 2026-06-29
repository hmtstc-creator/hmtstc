from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_daily_operation_service import build_summary_daily_operation


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


def _status_from(mode: str, risk_status: str, attention: bool, blockers: list[str]) -> str:
    mode = str(mode or "WATCH").upper()
    risk = str(risk_status or "review").upper()
    if blockers or mode in {"EMERGENCY_STOP", "SAFE_MODE", "OFF"} or risk in {"DANGER", "BLOCKED"}:
        return "blocked"
    if attention or mode in {"WATCH", "PAPER"} or risk in {"CAUTION", "WAIT", "REVIEW"}:
        return "review"
    return "ok"


def _plain_action(action: str, mode: str) -> str:
    action = str(action or "watch_market")
    mode = str(mode or "WATCH").upper()
    if action == "allow_micro_entries" or mode == "MICRO_REAL":
        return "Mikro gerçek işlem izni var."
    if action == "paper_validate" or mode == "PAPER":
        return "Paper modda doğrulama yapılıyor."
    if action == "pause_new_entries" or mode in {"SAFE_MODE", "EMERGENCY_STOP", "OFF"}:
        return "Yeni işlem durduruldu."
    return "Piyasa izleniyor."


def _headline(status: str, mode: str, market: str, pnl: float, attention: bool) -> str:
    if status == "blocked":
        return "Sistem koruma modunda; yeni işlem açılmamalı."
    if attention:
        return "Sistem izliyor; manuel dikkat öneriliyor."
    if mode == "MICRO_REAL":
        return "Sistem mikro gerçek işlem için uygun ortam görüyor."
    if mode == "PAPER":
        return "Sistem paper doğrulama ile fırsatları test ediyor."
    if pnl > 0:
        return "Gün pozitif; sistem kontrollü modda kalıyor."
    return f"Sistem {market or 'piyasayı'} izliyor; acele işlem yok."


def _attention_items(summary: dict, daily: dict, status: str) -> list[str]:
    items: list[str] = []
    quality = summary.get("quality") if isinstance(summary.get("quality"), dict) else {}
    reconciliation = summary.get("reconciliation") if isinstance(summary.get("reconciliation"), dict) else {}
    system = summary.get("system") if isinstance(summary.get("system"), dict) else {}
    positions = summary.get("positions") if isinstance(summary.get("positions"), dict) else {}
    tuner = summary.get("adaptive_parameter_tuner") if isinstance(summary.get("adaptive_parameter_tuner"), dict) else {}
    control = summary.get("autonomous_control_loop") if isinstance(summary.get("autonomous_control_loop"), dict) else {}
    safety = summary.get("autonomous_safety_supervisor") if isinstance(summary.get("autonomous_safety_supervisor"), dict) else {}
    position_manager = summary.get("autonomous_position_manager") if isinstance(summary.get("autonomous_position_manager"), dict) else {}
    if safety.get("kill_switch_active"):
        items.append("kill_switch_active")
    if safety.get("safe_mode_required"):
        items.append("safety_supervisor_safe_mode")
    if status == "blocked":
        items.append("bot_or_risk_blocked")
    if reconciliation.get("manual_attention_required") or quality.get("reconciliation_required"):
        items.append("reconciliation_attention")
    if positions.get("manual_attention_required"):
        items.append("position_attention")
    if system.get("emergency"):
        items.append("emergency_active")
    if tuner.get("apply_mode") in {"manual_review", "auto_apply_ready"} and tuner.get("proposal_count", 0):
        items.append("adaptive_tuning_review")
    if control.get("autopilot_state") in {"BLOCKED", "PROTECT", "REVIEW"}:
        items.append("autopilot_attention")
    position_manager = summary.get("autonomous_position_manager") if isinstance(summary.get("autonomous_position_manager"), dict) else {}
    if position_manager.get("attention_required") or position_manager.get("protective_action_count", 0):
        items.append("position_manager_attention")
    paper_result = summary.get("autonomous_paper_result_evaluator") if isinstance(summary.get("autonomous_paper_result_evaluator"), dict) else {}
    paper_promotion = summary.get("autonomous_paper_promotion_gate") if isinstance(summary.get("autonomous_paper_promotion_gate"), dict) else {}
    micro_readiness = summary.get("autonomous_micro_real_readiness_gate") if isinstance(summary.get("autonomous_micro_real_readiness_gate"), dict) else {}
    micro_sandbox = summary.get("autonomous_micro_real_execution_sandbox") if isinstance(summary.get("autonomous_micro_real_execution_sandbox"), dict) else {}
    paper_promotion = summary.get("autonomous_paper_promotion_gate") if isinstance(summary.get("autonomous_paper_promotion_gate"), dict) else {}
    if paper_result.get("attention_required") or paper_result.get("status") in {"review", "blocked"}:
        items.append("paper_result_evaluator_attention")
    paper_promotion = summary.get("autonomous_paper_promotion_gate") if isinstance(summary.get("autonomous_paper_promotion_gate"), dict) else {}
    if paper_promotion.get("attention_required") or paper_promotion.get("status") in {"review", "blocked"}:
        items.append("paper_promotion_gate_attention")
    micro_readiness = summary.get("autonomous_micro_real_readiness_gate") if isinstance(summary.get("autonomous_micro_real_readiness_gate"), dict) else {}
    micro_sandbox = summary.get("autonomous_micro_real_execution_sandbox") if isinstance(summary.get("autonomous_micro_real_execution_sandbox"), dict) else {}
    if micro_readiness.get("attention_required") or micro_readiness.get("status") in {"review", "blocked"}:
        items.append("micro_real_readiness_attention")
    micro_sandbox = summary.get("autonomous_micro_real_execution_sandbox") if isinstance(summary.get("autonomous_micro_real_execution_sandbox"), dict) else {}
    if micro_sandbox.get("status") in {"review", "blocked"}:
        items.append("micro_real_execution_sandbox_attention")
    micro_adapter = summary.get("autonomous_micro_real_exchange_adapter_hardening") if isinstance(summary.get("autonomous_micro_real_exchange_adapter_hardening"), dict) else {}
    micro_first_execution = summary.get("autonomous_first_micro_real_controlled_execution") if isinstance(summary.get("autonomous_first_micro_real_controlled_execution"), dict) else {}
    micro_position_tracker = summary.get("autonomous_micro_real_position_tracker") if isinstance(summary.get("autonomous_micro_real_position_tracker"), dict) else {}
    micro_position_tracker = summary.get("autonomous_micro_real_position_tracker") if isinstance(summary.get("autonomous_micro_real_position_tracker"), dict) else {}
    if micro_adapter.get("status") in {"review", "blocked"}:
        items.append("micro_real_exchange_adapter_attention")
    micro_position_tracker = summary.get("autonomous_micro_real_position_tracker") if isinstance(summary.get("autonomous_micro_real_position_tracker"), dict) else {}
    if micro_position_tracker.get("manual_attention_required") or micro_position_tracker.get("status") == "blocked":
        items.append("micro_real_position_tracker_attention")
    micro_scale_controller = summary.get("autonomous_micro_real_promotion_demotion_controller") if isinstance(summary.get("autonomous_micro_real_promotion_demotion_controller"), dict) else {}
    if micro_scale_controller.get("decision") in {"reduce", "stop"} or micro_scale_controller.get("status") == "blocked":
        items.append("micro_real_promotion_demotion_attention")
    small_capital_mode = summary.get("autonomous_fully_autonomous_small_capital_mode") if isinstance(summary.get("autonomous_fully_autonomous_small_capital_mode"), dict) else {}
    if small_capital_mode.get("decision") in {"hold", "stop"} or small_capital_mode.get("status") in {"review", "blocked"}:
        items.append("fully_autonomous_small_capital_attention")
    for blocker in daily.get("blockers") or []:
        if blocker not in items:
            items.append(str(blocker))
    return items[:5]


def build_minimal_summary_dashboard(summary: dict | None, data: dict | None = None, settings: dict | None = None) -> dict:
    """Build the Rev66 executive surface from existing read-only engines.

    The payload deliberately exposes only the few values the owner needs to see:
    bot mode, market condition, PnL, risk status, action, and attention flag.
    It has no command fields and does not mutate runtime state.
    """
    summary = deepcopy(summary or {})
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    daily = summary.get("daily_operation") if isinstance(summary.get("daily_operation"), dict) else {}
    if not daily:
        daily = build_summary_daily_operation(data, settings)

    system = summary.get("system") if isinstance(summary.get("system"), dict) else {}
    money = summary.get("money") if isinstance(summary.get("money"), dict) else {}
    market_payload = summary.get("market") if isinstance(summary.get("market"), dict) else {}
    risk = summary.get("risk_brain") if isinstance(summary.get("risk_brain"), dict) else {}
    quality = summary.get("trade_quality_feedback") if isinstance(summary.get("trade_quality_feedback"), dict) else {}
    tuner = summary.get("adaptive_parameter_tuner") if isinstance(summary.get("adaptive_parameter_tuner"), dict) else {}
    control = summary.get("autonomous_control_loop") if isinstance(summary.get("autonomous_control_loop"), dict) else {}
    safety = summary.get("autonomous_safety_supervisor") if isinstance(summary.get("autonomous_safety_supervisor"), dict) else {}
    position_manager = summary.get("autonomous_position_manager") if isinstance(summary.get("autonomous_position_manager"), dict) else {}
    paper_result = summary.get("autonomous_paper_result_evaluator") if isinstance(summary.get("autonomous_paper_result_evaluator"), dict) else {}
    paper_promotion = summary.get("autonomous_paper_promotion_gate") if isinstance(summary.get("autonomous_paper_promotion_gate"), dict) else {}
    micro_readiness = summary.get("autonomous_micro_real_readiness_gate") if isinstance(summary.get("autonomous_micro_real_readiness_gate"), dict) else {}
    micro_sandbox = summary.get("autonomous_micro_real_execution_sandbox") if isinstance(summary.get("autonomous_micro_real_execution_sandbox"), dict) else {}
    micro_adapter = summary.get("autonomous_micro_real_exchange_adapter_hardening") if isinstance(summary.get("autonomous_micro_real_exchange_adapter_hardening"), dict) else {}
    micro_first_execution = summary.get("autonomous_first_micro_real_controlled_execution") if isinstance(summary.get("autonomous_first_micro_real_controlled_execution"), dict) else {}
    micro_position_tracker = summary.get("autonomous_micro_real_position_tracker") if isinstance(summary.get("autonomous_micro_real_position_tracker"), dict) else {}
    micro_result_evaluator = summary.get("autonomous_micro_real_result_evaluator") if isinstance(summary.get("autonomous_micro_real_result_evaluator"), dict) else {}
    micro_scale_controller = summary.get("autonomous_micro_real_promotion_demotion_controller") if isinstance(summary.get("autonomous_micro_real_promotion_demotion_controller"), dict) else {}
    small_capital_mode = summary.get("autonomous_fully_autonomous_small_capital_mode") if isinstance(summary.get("autonomous_fully_autonomous_small_capital_mode"), dict) else {}

    mode = str(daily.get("bot_mode") or system.get("autonomous_daily_mode") or risk.get("bot_mode") or "WATCH").upper()
    market = str(daily.get("market") or market_payload.get("autonomous_market_mode") or market_payload.get("regime") or "WAIT").upper()
    today_pnl = _safe_float(daily.get("today_pnl_usdt"), _safe_float(money.get("autonomous_today_pnl_usdt"), _safe_float(money.get("real_today_pnl"), 0.0)))
    risk_status = str(daily.get("risk_status") or risk.get("risk_status") or market_payload.get("autonomous_risk_status") or "review").upper()
    position_action = str(position_manager.get("primary_action") or "")
    action = str(safety.get("safety_action") or (position_action if position_action and position_action != "HOLD" else "") or control.get("next_action") or daily.get("action") or system.get("autonomous_daily_action") or "watch_market")
    quality_score = _safe_float(daily.get("quality_score"), _safe_float(quality.get("quality_score"), 0.0))
    confidence = _safe_float(risk.get("confidence"), _safe_float((summary.get("autonomous_decision") or {}).get("confidence") if isinstance(summary.get("autonomous_decision"), dict) else 0.0, 0.0))
    trade_count = _safe_int(daily.get("trade_count"), 0)
    blockers = list(daily.get("blockers") or risk.get("blockers") or []) if isinstance(daily.get("blockers") or risk.get("blockers") or [], list) else []
    if safety.get("kill_switch_active") or safety.get("safe_mode_required"):
        blockers = list(blockers) + [str(safety.get("safety_state") or "safety_supervisor_attention")]
    preliminary_status = _status_from(mode, risk_status, False, blockers)
    attention_items = _attention_items(summary, daily, preliminary_status)
    attention_required = bool(attention_items)
    status = _status_from(mode, risk_status, attention_required, blockers)

    tiles = [
        {"key": "bot_mode", "label": "Bot", "value": mode, "tone": status},
        {"key": "market", "label": "Market", "value": market, "tone": "ok" if market in {"TRADE", "BULL", "TREND"} else "review"},
        {"key": "today_pnl", "label": "Today", "value": round(today_pnl, 4), "unit": "USDT", "tone": "ok" if today_pnl >= 0 else "blocked"},
        {"key": "risk", "label": "Risk", "value": risk_status, "tone": "ok" if risk_status in {"NORMAL", "OK"} else ("blocked" if risk_status in {"DANGER", "BLOCKED"} else "review")},
        {"key": "action", "label": "Action", "value": _plain_action(action, mode), "tone": status},
    ]
    if attention_required:
        tiles.append({"key": "attention", "label": "Attention", "value": "Required", "tone": "blocked"})
    else:
        tiles.append({"key": "attention", "label": "Attention", "value": "None", "tone": "ok"})

    return {
        "status": status,
        "revision": 66,
        "engine": "minimal_summary_dashboard",
        "generated_at": now_iso(),
        "read_only": True,
        "minimal": True,
        "headline": _headline(status, mode, market, today_pnl, attention_required),
        "bot_mode": mode,
        "market_condition": market,
        "today_pnl_usdt": round(today_pnl, 4),
        "risk_status": risk_status,
        "action": action,
        "autopilot_state": control.get("autopilot_state"),
        "safety_state": safety.get("safety_state"),
        "position_lifecycle_state": position_manager.get("lifecycle_state"),
        "position_primary_action": position_manager.get("primary_action"),
        "paper_result_state": paper_result.get("evaluation_state"),
        "paper_result_quality_score": paper_result.get("paper_result_quality_score"),
        "paper_result_net_pnl_usdt": paper_result.get("net_pnl_usdt"),
        "paper_promotion_state": paper_promotion.get("promotion_state"),
        "paper_promotion_score": paper_promotion.get("promotion_score"),
        "paper_promotion_target_lane": paper_promotion.get("target_lane"),
        "micro_real_readiness_state": micro_readiness.get("readiness_state"),
        "micro_real_readiness_score": micro_readiness.get("readiness_score"),
        "micro_real_probe_notional_usdt": micro_readiness.get("probe_notional_usdt"),
        "micro_real_result_evaluator_state": micro_result_evaluator.get("evaluator_state"),
        "micro_real_result_quality_score": micro_result_evaluator.get("result_quality_score"),
        "micro_real_scale_controller_state": micro_scale_controller.get("controller_state"),
        "micro_real_scale_decision": micro_scale_controller.get("decision"),
        "micro_real_scale_target_notional_usdt": micro_scale_controller.get("target_notional_usdt"),
        "fully_autonomous_small_capital_state": small_capital_mode.get("mode_state"),
        "fully_autonomous_small_capital_decision": small_capital_mode.get("decision"),
        "fully_autonomous_small_capital_score": small_capital_mode.get("autonomy_score"),
        "kill_switch_active": bool(safety.get("kill_switch_active")),
        "action_text": _plain_action(action, mode),
        "attention_required": attention_required,
        "attention_items": attention_items,
        "confidence": round(confidence, 2),
        "trade_count": trade_count,
        "quality_score": round(quality_score, 2),
        "primary_symbol": daily.get("primary_symbol") or risk.get("primary_symbol"),
        "primary_strategy": daily.get("primary_strategy") or risk.get("primary_strategy"),
        "tiles": tiles,
        "source": {
            "summary_revision": summary.get("revision"),
            "daily_operation_revision": daily.get("revision"),
            "risk_brain_revision": risk.get("revision"),
            "trade_quality_revision": quality.get("revision"),
            "adaptive_tuner_revision": tuner.get("revision"),
            "autonomous_control_loop_revision": control.get("revision"),
            "autonomous_safety_supervisor_revision": safety.get("revision"),
            "autonomous_position_manager_revision": position_manager.get("revision"),
            "autonomous_paper_result_evaluator_revision": paper_result.get("revision"),
            "autonomous_paper_promotion_gate_revision": paper_promotion.get("revision"),
            "autonomous_micro_real_readiness_gate_revision": micro_readiness.get("revision"),
            "autonomous_micro_real_execution_sandbox_revision": micro_sandbox.get("revision"),
            "autonomous_micro_real_exchange_adapter_hardening_revision": micro_adapter.get("revision"),
            "autonomous_first_micro_real_controlled_execution_revision": micro_first_execution.get("revision"),
            "autonomous_micro_real_position_tracker_revision": micro_position_tracker.get("revision"),
            "autonomous_micro_real_result_evaluator_revision": micro_result_evaluator.get("revision"),
            "autonomous_micro_real_promotion_demotion_controller_revision": micro_scale_controller.get("revision"),
            "autonomous_semi_autonomous_real_trading_lane_revision": (summary.get("autonomous_semi_autonomous_real_trading_lane") or {}).get("revision") if isinstance(summary.get("autonomous_semi_autonomous_real_trading_lane"), dict) else None,
            "autonomous_fully_autonomous_small_capital_mode_revision": (summary.get("autonomous_fully_autonomous_small_capital_mode") or {}).get("revision") if isinstance(summary.get("autonomous_fully_autonomous_small_capital_mode"), dict) else None,
        },
    }


def build_minimal_summary_dashboard_quality(summary: dict | None, data: dict | None = None, settings: dict | None = None) -> dict:
    payload = build_minimal_summary_dashboard(summary, data, settings)
    tiles = payload.get("tiles") if isinstance(payload.get("tiles"), list) else []
    checks = {
        "revision_66": payload.get("revision") == 66,
        "read_only": payload.get("read_only") is True,
        "minimal_contract": payload.get("minimal") is True and 5 <= len(tiles) <= 6,
        "required_tiles": {"bot_mode", "market", "today_pnl", "risk", "action"}.issubset({str(item.get("key")) for item in tiles if isinstance(item, dict)}),
        "no_command_payload": not any(key in payload for key in ("place_order", "start_bot", "stop_bot", "execute", "confirm")),
        "source_chain_visible": isinstance(payload.get("source"), dict) and payload["source"].get("daily_operation_revision") in {None, 65},
        "safety_surface_visible": "kill_switch_active" in payload and "safety_state" in payload,
        "position_lifecycle_visible": "position_lifecycle_state" in payload and "position_primary_action" in payload,
        "paper_result_visible": "paper_result_state" in payload and "paper_result_quality_score" in payload,
        "paper_promotion_visible": "paper_promotion_state" in payload and "paper_promotion_score" in payload,
        "micro_real_readiness_visible": "micro_real_readiness_state" in payload and "micro_real_readiness_score" in payload,
        "micro_real_execution_sandbox_visible": payload.get("source", {}).get("autonomous_micro_real_execution_sandbox_revision") in {None, 88},
        "micro_real_exchange_adapter_visible": payload.get("source", {}).get("autonomous_micro_real_exchange_adapter_hardening_revision") in {None, 89},
        "first_micro_real_controlled_execution_visible": payload.get("source", {}).get("autonomous_first_micro_real_controlled_execution_revision") in {None, 91},
        "micro_real_position_tracker_visible": payload.get("source", {}).get("autonomous_micro_real_position_tracker_revision") in {None, 92},
        "micro_real_result_evaluator_visible": payload.get("source", {}).get("autonomous_micro_real_result_evaluator_revision") in {None, 94},
        "micro_real_promotion_demotion_controller_visible": payload.get("source", {}).get("autonomous_micro_real_promotion_demotion_controller_revision") in {None, 95},
        "semi_autonomous_real_trading_lane_visible": payload.get("source", {}).get("autonomous_semi_autonomous_real_trading_lane_revision") in {None, 96},
        "fully_autonomous_small_capital_mode_visible": payload.get("source", {}).get("autonomous_fully_autonomous_small_capital_mode_revision") in {None, 97},
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 66,
        "engine": "minimal_summary_dashboard_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "dashboard_status": payload.get("status"),
        "tile_count": len(tiles),
    }
