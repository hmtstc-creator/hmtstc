from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.adaptive_parameter_tuner_service import build_adaptive_parameter_tuner
from services.autonomous_daily_operation_service import build_summary_daily_operation
from services.autonomous_execution_governor_service import build_autonomous_execution_governor
from services.risk_brain_service import build_risk_brain
from services.strategy_selection_engine_service import build_summary_strategy_selection
from services.trade_quality_feedback_service import build_summary_trade_quality_feedback


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
    control = settings.get("autonomous_control_loop") if isinstance(settings.get("autonomous_control_loop"), dict) else {}
    return {
        "enabled": _safe_bool(control.get("enabled"), True),
        "allow_real_lane": _safe_bool(control.get("allow_real_lane"), False),
        "allow_micro_real_lane": _safe_bool(control.get("allow_micro_real_lane"), True),
        "min_quality_score": max(0.0, min(100.0, _safe_float(control.get("min_quality_score"), 60.0))),
        "min_confidence": max(0.0, min(100.0, _safe_float(control.get("min_confidence"), 55.0))),
        "max_attention_items": max(0, _safe_int(control.get("max_attention_items"), 0)),
        "max_tuning_proposals_for_autopilot": max(0, _safe_int(control.get("max_tuning_proposals_for_autopilot"), 2)),
    }


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _mode_rank(mode: str) -> int:
    order = {
        "EMERGENCY_STOP": 0,
        "SAFE_MODE": 1,
        "OFF": 2,
        "WATCH": 3,
        "PAPER": 4,
        "MICRO_REAL": 5,
        "REAL": 6,
    }
    return order.get(str(mode or "WATCH").upper(), 3)


def _choose_state(daily: dict, execution: dict, risk: dict, quality: dict, tuner: dict, policy: dict) -> tuple[str, list[str]]:
    blockers: list[str] = []
    blockers.extend(_as_list(daily.get("blockers")))
    blockers.extend(_as_list(execution.get("blockers")))
    blockers.extend(_as_list(risk.get("blockers")))
    blockers = sorted(set(blockers))

    mode = str(daily.get("bot_mode") or risk.get("bot_mode") or "WATCH").upper()
    lane = str(execution.get("execution_lane") or "none").lower()
    quality_score = _safe_float(quality.get("quality_score"), _safe_float(tuner.get("quality_score"), 0.0))
    confidence = _safe_float(risk.get("confidence"), _safe_float(daily.get("confidence"), 0.0))
    attention_items = _as_list(daily.get("attention_items")) + _as_list(quality.get("warnings"))
    proposal_count = _safe_int(tuner.get("proposal_count"), 0)

    if not policy["enabled"]:
        blockers.append("autonomous_control_loop_disabled")
        return "PAUSED", sorted(set(blockers))
    if blockers:
        return "BLOCKED", sorted(set(blockers))
    if mode in {"EMERGENCY_STOP", "SAFE_MODE", "OFF"} or str(risk.get("risk_status") or "").upper() in {"DANGER", "BLOCKED"}:
        return "PROTECT", sorted(set(blockers))
    if len(attention_items) > policy["max_attention_items"]:
        return "REVIEW", sorted(set(blockers + ["attention_required"]))
    if quality_score and quality_score < policy["min_quality_score"]:
        return "PAPER_ONLY", sorted(set(blockers + ["quality_below_autopilot_threshold"]))
    if confidence and confidence < policy["min_confidence"]:
        return "OBSERVE", sorted(set(blockers + ["confidence_below_autopilot_threshold"]))
    if proposal_count > policy["max_tuning_proposals_for_autopilot"]:
        return "REVIEW", sorted(set(blockers + ["too_many_tuning_proposals"]))
    if lane == "real" and not policy["allow_real_lane"]:
        return "MICRO_REAL_READY" if policy["allow_micro_real_lane"] else "PAPER_ONLY", sorted(set(blockers + ["real_lane_requires_owner_opt_in"]))
    if lane in {"micro_real", "micro-real"} and policy["allow_micro_real_lane"] and _mode_rank(mode) >= _mode_rank("MICRO_REAL"):
        return "MICRO_REAL_READY", blockers
    if mode == "REAL" and policy["allow_real_lane"]:
        return "REAL_READY", blockers
    if mode == "PAPER":
        return "PAPER_ONLY", blockers
    return "OBSERVE", blockers


def _next_action(state: str) -> tuple[str, str]:
    mapping = {
        "REAL_READY": ("allow_real_execution", "Gerçek işlem hattı hazır; yine de exchange emri ayrı execution guard’dan geçmeli."),
        "MICRO_REAL_READY": ("allow_micro_real_execution", "Mikro gerçek işlem hattı hazır; düşük notional ve koruma limitleri korunmalı."),
        "PAPER_ONLY": ("paper_validate", "Sinyaller paper modda doğrulanmalı; gerçek işlem açılmamalı."),
        "OBSERVE": ("watch_market", "Piyasa izlenmeli; yeni emir için yeterli güven yok."),
        "REVIEW": ("manual_review", "Sistem karar verebilir ama parametre/kalite dikkat sinyali var."),
        "PROTECT": ("pause_new_entries", "Koruma modu aktif; yeni girişler durdurulmalı."),
        "BLOCKED": ("block_execution", "Execution bloklandı; risk veya bağlantı problemi çözülmeli."),
        "PAUSED": ("autopilot_paused", "Otonom kontrol döngüsü ayarlardan kapalı."),
    }
    return mapping.get(state, ("watch_market", "Varsayılan güvenli izleme modu."))


def build_autonomous_control_loop(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Orchestrate the autonomous decision chain without placing orders.

    Rev70 is the closed-loop supervisor: it reads scanner/mode/strategy/risk/quality/
    execution/tuning outputs and produces one simple autopilot state. It deliberately
    does not call an exchange or mutate settings; it creates a safe command preview for
    the runtime/execution layer.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)

    daily = build_summary_daily_operation(data, settings)
    strategy = build_summary_strategy_selection(data, settings)
    risk = build_risk_brain(data, settings)
    quality = build_summary_trade_quality_feedback(data, settings)
    execution = build_autonomous_execution_governor(data, settings, auth_store, username)
    tuner = build_adaptive_parameter_tuner(data, settings, auth_store, username)

    state, blockers = _choose_state(daily, execution, risk, quality, tuner, policy)
    action, action_text = _next_action(state)
    can_autopilot = state in {"MICRO_REAL_READY", "REAL_READY", "PAPER_ONLY", "OBSERVE"} and not blockers
    can_execute = bool(execution.get("can_execute")) and state in {"MICRO_REAL_READY", "REAL_READY"}
    lane = str(execution.get("execution_lane") or "none")

    command_preview = {
        "type": action,
        "state": state,
        "lane": lane,
        "symbol": daily.get("primary_symbol") or risk.get("primary_symbol"),
        "strategy": daily.get("primary_strategy") or strategy.get("strategy"),
        "max_order_usdt": execution.get("suggested_order_usdt") or risk.get("suggested_order_usdt"),
        "read_only": True,
        "requires_execution_guard": True,
    }

    return {
        "status": "ok" if can_autopilot or state in {"PAPER_ONLY", "OBSERVE"} else "review",
        "revision": 70,
        "engine": "autonomous_control_loop",
        "generated_at": now_iso(),
        "read_only": True,
        "autopilot_state": state,
        "next_action": action,
        "next_action_text": action_text,
        "can_autopilot": can_autopilot,
        "can_execute": can_execute,
        "execution_lane": lane,
        "blockers": blockers,
        "warnings": sorted(set(_as_list(tuner.get("warnings")) + _as_list(quality.get("warnings")))),
        "command_preview": command_preview,
        "policy": policy,
        "source_chain": {
            "daily_operation_revision": daily.get("revision"),
            "strategy_selection_revision": strategy.get("revision"),
            "risk_brain_revision": risk.get("revision"),
            "trade_quality_revision": quality.get("revision"),
            "execution_governor_revision": execution.get("revision"),
            "adaptive_tuner_revision": tuner.get("revision"),
        },
        "signals": {
            "bot_mode": daily.get("bot_mode"),
            "market": daily.get("market"),
            "risk_status": risk.get("risk_status"),
            "quality_score": quality.get("quality_score"),
            "tuning_apply_mode": tuner.get("apply_mode"),
            "proposal_count": tuner.get("proposal_count"),
        },
    }


def build_summary_autonomous_control_loop(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_control_loop(data, settings, auth_store, username)
    return {
        "status": payload.get("status"),
        "revision": 70,
        "engine": "autonomous_control_loop_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "autopilot_state": payload.get("autopilot_state"),
        "next_action": payload.get("next_action"),
        "next_action_text": payload.get("next_action_text"),
        "can_autopilot": payload.get("can_autopilot"),
        "can_execute": payload.get("can_execute"),
        "execution_lane": payload.get("execution_lane"),
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "primary_symbol": payload.get("command_preview", {}).get("symbol") if isinstance(payload.get("command_preview"), dict) else None,
        "primary_strategy": payload.get("command_preview", {}).get("strategy") if isinstance(payload.get("command_preview"), dict) else None,
    }


def build_autonomous_control_loop_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_control_loop(data, settings, auth_store, username)
    source_chain = payload.get("source_chain") if isinstance(payload.get("source_chain"), dict) else {}
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_70": payload.get("revision") == 70,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "closed_loop_sources": {"daily_operation_revision", "strategy_selection_revision", "risk_brain_revision", "trade_quality_revision", "execution_governor_revision", "adaptive_tuner_revision"}.issubset(source_chain.keys()),
        "no_direct_order_placement": not any(key in payload for key in ("place_order", "market_order", "exchange_request", "signed_payload")),
        "command_preview_guarded": command.get("requires_execution_guard") is True,
        "summary_state_available": bool(payload.get("autopilot_state") and payload.get("next_action")),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 70,
        "engine": "autonomous_control_loop_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "autopilot_state": payload.get("autopilot_state"),
        "next_action": payload.get("next_action"),
        "can_execute": payload.get("can_execute"),
        "source_chain": source_chain,
    }
