from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_control_loop_service import build_autonomous_control_loop


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


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    policy = settings.get("autonomous_safety_supervisor") if isinstance(settings.get("autonomous_safety_supervisor"), dict) else {}
    return {
        "enabled": _safe_bool(policy.get("enabled"), True),
        "max_daily_loss_usdt": max(0.0, _safe_float(policy.get("max_daily_loss_usdt"), 25.0)),
        "max_loss_streak": max(1, _safe_int(policy.get("max_loss_streak"), 3)),
        "min_quality_score": max(0.0, min(100.0, _safe_float(policy.get("min_quality_score"), 55.0))),
        "min_confidence": max(0.0, min(100.0, _safe_float(policy.get("min_confidence"), 40.0))),
        "max_blockers": max(0, _safe_int(policy.get("max_blockers"), 0)),
        "require_api_ready_for_real": _safe_bool(policy.get("require_api_ready_for_real"), True),
        "kill_switch_on_emergency": _safe_bool(policy.get("kill_switch_on_emergency"), True),
    }


def _loss_streak(trades: list[dict]) -> int:
    streak = 0
    for trade in reversed(trades):
        pnl = _safe_float(trade.get("pnl_usdt", trade.get("pnl", 0.0)))
        if pnl < 0:
            streak += 1
        elif pnl > 0:
            break
    return streak


def _daily_pnl(data: dict, control: dict) -> float:
    candidates = [
        data.get("today_pnl_usdt"),
        data.get("daily_pnl_usdt"),
        (data.get("daily") or {}).get("pnl_usdt") if isinstance(data.get("daily"), dict) else None,
        (data.get("performance") or {}).get("today_pnl_usdt") if isinstance(data.get("performance"), dict) else None,
    ]
    for value in candidates:
        if value is not None:
            return _safe_float(value)
    trades = data.get("closed_trades") if isinstance(data.get("closed_trades"), list) else []
    if trades:
        return sum(_safe_float(trade.get("pnl_usdt", trade.get("pnl", 0.0))) for trade in trades[-50:])
    return _safe_float((control.get("signals") or {}).get("today_pnl_usdt") if isinstance(control.get("signals"), dict) else 0.0)


def _api_ready(auth_store: dict, username: str) -> bool:
    users = auth_store.get("users") if isinstance(auth_store.get("users"), dict) else {}
    user = users.get(username) if isinstance(users.get(username), dict) else {}
    connection = user.get("api_connection") if isinstance(user.get("api_connection"), dict) else {}
    return bool(connection.get("masked_api_key") and connection.get("api_secret_digest"))


def _evaluate(data: dict, control: dict, auth_store: dict, username: str, policy: dict) -> tuple[str, list[str], list[str]]:
    hard: list[str] = []
    warnings: list[str] = []
    blockers = _as_list(control.get("blockers"))
    signals = control.get("signals") if isinstance(control.get("signals"), dict) else {}
    command = control.get("command_preview") if isinstance(control.get("command_preview"), dict) else {}
    quality_score = _safe_float(signals.get("quality_score"), 0.0)
    confidence = _safe_float(signals.get("confidence"), 0.0)
    lane = str(command.get("lane") or control.get("execution_lane") or "none").lower()
    state = str(control.get("autopilot_state") or "OBSERVE").upper()
    trades = data.get("closed_trades") if isinstance(data.get("closed_trades"), list) else []
    loss_streak = _loss_streak([trade for trade in trades if isinstance(trade, dict)])
    today_pnl = _daily_pnl(data, control)

    if not policy["enabled"]:
        hard.append("safety_supervisor_disabled")
    if policy["kill_switch_on_emergency"] and state in {"EMERGENCY_STOP", "PROTECT", "BLOCKED"}:
        hard.append("autopilot_protection_state")
    if today_pnl <= -policy["max_daily_loss_usdt"]:
        hard.append("daily_loss_limit_reached")
    if loss_streak >= policy["max_loss_streak"]:
        hard.append("loss_streak_limit_reached")
    if len(blockers) > policy["max_blockers"]:
        hard.append("autopilot_blockers_present")
    if lane in {"real", "micro_real", "micro-real"} and policy["require_api_ready_for_real"] and not _api_ready(auth_store, username):
        hard.append("api_connection_not_ready_for_real_lane")
    if quality_score and quality_score < policy["min_quality_score"]:
        warnings.append("quality_score_below_safety_target")
    if confidence and confidence < policy["min_confidence"]:
        warnings.append("confidence_below_safety_target")

    if hard:
        return "KILL_SWITCH", sorted(set(hard)), sorted(set(warnings))
    if warnings:
        return "SAFE_MODE", [], sorted(set(warnings))
    if control.get("can_execute"):
        return "ARMED", [], []
    return "MONITOR", [], []


def _action_for_state(state: str) -> tuple[str, str]:
    mapping = {
        "KILL_SWITCH": ("force_pause_all_new_entries", "Güvenlik kesicisi aktif; yeni işlem girişi durdurulmalı."),
        "SAFE_MODE": ("reduce_to_watch_or_paper", "Sistem güvenli moda alınmalı; gerçek işlem hattı beklemeli."),
        "ARMED": ("allow_guarded_execution", "Execution guard izin verirse düşük riskli işlem hattı çalışabilir."),
        "MONITOR": ("monitor_only", "Sistem izleme modunda kalmalı; emir açma izni yok."),
    }
    return mapping.get(state, ("monitor_only", "Varsayılan izleme modu."))


def build_autonomous_safety_supervisor(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev71 final safety supervisor for the autonomous chain.

    This is a read-only hard safety layer. It never places an order and never mutates
    settings. It converts control-loop output into a simple safety state: ARMED,
    MONITOR, SAFE_MODE, or KILL_SWITCH.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    control = build_autonomous_control_loop(data, settings, auth_store, username)
    state, hard_blockers, warnings = _evaluate(data, control, auth_store, username, policy)
    action, action_text = _action_for_state(state)
    can_continue_autopilot = state in {"ARMED", "MONITOR"}
    can_execute = state == "ARMED" and bool(control.get("can_execute"))

    return {
        "status": "ok" if state in {"ARMED", "MONITOR"} else "blocked" if state == "KILL_SWITCH" else "review",
        "revision": 71,
        "engine": "autonomous_safety_supervisor",
        "generated_at": now_iso(),
        "read_only": True,
        "safety_state": state,
        "safety_action": action,
        "safety_action_text": action_text,
        "can_continue_autopilot": can_continue_autopilot,
        "can_execute": can_execute,
        "hard_blockers": hard_blockers,
        "warnings": warnings,
        "kill_switch_active": state == "KILL_SWITCH",
        "safe_mode_required": state in {"KILL_SWITCH", "SAFE_MODE"},
        "policy": policy,
        "control_loop": {
            "revision": control.get("revision"),
            "autopilot_state": control.get("autopilot_state"),
            "next_action": control.get("next_action"),
            "execution_lane": control.get("execution_lane"),
            "can_execute": control.get("can_execute"),
            "blocker_count": len(control.get("blockers") or []),
        },
        "command_preview": {
            "type": action,
            "read_only": True,
            "requires_execution_guard": True,
            "override": "pause" if state == "KILL_SWITCH" else "safe_mode" if state == "SAFE_MODE" else "none",
            "source_revision": 71,
        },
    }


def build_summary_autonomous_safety_supervisor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_safety_supervisor(data, settings, auth_store, username)
    return {
        "status": payload.get("status"),
        "revision": 71,
        "engine": "autonomous_safety_supervisor_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "safety_state": payload.get("safety_state"),
        "safety_action": payload.get("safety_action"),
        "safety_action_text": payload.get("safety_action_text"),
        "can_continue_autopilot": payload.get("can_continue_autopilot"),
        "can_execute": payload.get("can_execute"),
        "kill_switch_active": payload.get("kill_switch_active"),
        "safe_mode_required": payload.get("safe_mode_required"),
        "hard_blocker_count": len(payload.get("hard_blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_autonomous_safety_supervisor_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_safety_supervisor(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_71": payload.get("revision") == 71,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "safety_state_available": payload.get("safety_state") in {"ARMED", "MONITOR", "SAFE_MODE", "KILL_SWITCH"},
        "kill_switch_contract": isinstance(payload.get("kill_switch_active"), bool) and isinstance(payload.get("hard_blockers"), list),
        "no_direct_order_placement": not any(key in payload for key in ("place_order", "market_order", "exchange_request", "signed_payload")),
        "execution_guard_required": command.get("requires_execution_guard") is True,
        "control_loop_source_visible": isinstance(payload.get("control_loop"), dict) and payload["control_loop"].get("revision") == 70,
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 71,
        "engine": "autonomous_safety_supervisor_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "safety_state": payload.get("safety_state"),
        "safety_action": payload.get("safety_action"),
        "kill_switch_active": payload.get("kill_switch_active"),
    }
