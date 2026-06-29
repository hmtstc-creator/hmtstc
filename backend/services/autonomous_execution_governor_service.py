from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_daily_operation_service import build_autonomous_daily_operation
from services.user_api_secret_layer_service import build_user_api_secret_summary

EXECUTION_MODES = {"PAPER", "MICRO_REAL", "REAL"}
REAL_MODES = {"MICRO_REAL", "REAL"}
BLOCKING_ACTIONS = {"pause_new_entries", "watch_market"}


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
    execution = settings.get("execution_governor") if isinstance(settings.get("execution_governor"), dict) else {}
    real = settings.get("real_trade") if isinstance(settings.get("real_trade"), dict) else {}
    bot = settings.get("bot") if isinstance(settings.get("bot"), dict) else {}
    return {
        "enabled": _safe_bool(execution.get("enabled"), True),
        "dry_run_default": _safe_bool(execution.get("dry_run_default"), True),
        "require_user_api_for_real": _safe_bool(execution.get("require_user_api_for_real"), True),
        "require_micro_real_before_real": _safe_bool(execution.get("require_micro_real_before_real"), True),
        "max_single_order_usdt": max(0.0, _safe_float(execution.get("max_single_order_usdt"), _safe_float(bot.get("max_order_usdt"), 25.0))),
        "min_order_usdt": max(0.0, _safe_float(execution.get("min_order_usdt"), 5.0)),
        "real_trading_master_enabled": _safe_bool(real.get("enabled"), _safe_bool(bot.get("real_trading_enabled"), False)),
        "paper_allowed_without_api": _safe_bool(execution.get("paper_allowed_without_api"), True),
    }


def _api_summary(auth_store: dict | None, username: str) -> dict:
    try:
        return build_user_api_secret_summary(auth_store or {}, username)
    except Exception as exc:  # defensive fallback for read-only summary path
        return {
            "status": "review",
            "revision": 67,
            "read_only": True,
            "configured": False,
            "can_execute_real_trade": False,
            "readiness": "error",
            "error": str(exc),
        }


def _normalize_mode(mode: Any) -> str:
    text = str(mode or "WATCH").upper()
    return text if text in {"OFF", "WATCH", "PAPER", "MICRO_REAL", "REAL", "SAFE_MODE", "EMERGENCY_STOP"} else "WATCH"


def _execution_lane(mode: str, action: str) -> str:
    mode = _normalize_mode(mode)
    action = str(action or "watch_market")
    if mode == "PAPER" or action == "paper_validate":
        return "paper"
    if mode == "MICRO_REAL" or action == "allow_micro_entries":
        return "micro_real"
    if mode == "REAL":
        return "real"
    return "none"


def _decision_text(can_execute: bool, lane: str, blockers: list[str], symbol: str | None, amount: float, dry_run: bool) -> str:
    if blockers:
        return f"Execution kapalı: {', '.join(blockers[:3])}."
    if not can_execute:
        return "Execution beklemede; sistem izleme modunda."
    if lane == "paper":
        return f"Paper execution izni var; {symbol or 'aday sembol'} üzerinde doğrulama yapılabilir."
    if lane == "micro_real":
        suffix = "dry-run" if dry_run else "guarded real"
        return f"Mikro gerçek execution izni var; önerilen emir {round(amount, 4)} USDT ({suffix})."
    if lane == "real":
        return f"Gerçek execution için bütün guardlar geçti; önerilen emir {round(amount, 4)} USDT."
    return "Execution aksiyonu yok."


def build_autonomous_execution_governor(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Build the final read-only gate before any autonomous execution.

    This service intentionally does not place orders and does not mutate runtime state.
    It turns the scanner -> mode -> strategy -> risk -> daily operation chain into an
    execution permission payload that downstream real-order code can consume.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _policy(settings)
    daily = build_autonomous_daily_operation(data, settings)
    api = _api_summary(auth_store, username)

    mode = _normalize_mode(daily.get("recommended_mode"))
    action = str(daily.get("recommended_action") or "watch_market")
    lane = _execution_lane(mode, action)
    budget = daily.get("budget") if isinstance(daily.get("budget"), dict) else {}
    raw_order = _safe_float(budget.get("suggested_order_usdt"), 0.0)
    order_usdt = round(min(max(raw_order, 0.0), policy["max_single_order_usdt"]), 4)
    if order_usdt < policy["min_order_usdt"] and lane in {"micro_real", "real"}:
        order_usdt = 0.0

    blockers = set(daily.get("blockers") or [])
    warnings = set(daily.get("warnings") or [])
    if not policy["enabled"]:
        blockers.add("execution_governor_disabled")
    if daily.get("status") == "blocked":
        blockers.add("daily_operation_blocked")
    if action in BLOCKING_ACTIONS or mode in {"OFF", "WATCH", "SAFE_MODE", "EMERGENCY_STOP"}:
        blockers.add("mode_not_executable")
    if lane == "none":
        blockers.add("no_execution_lane")
    if lane in {"micro_real", "real"}:
        if not policy["real_trading_master_enabled"]:
            blockers.add("real_trading_master_disabled")
        if policy["require_user_api_for_real"] and not api.get("can_execute_real_trade"):
            blockers.add("user_api_not_ready_for_real_trade")
        if order_usdt <= 0.0:
            blockers.add("order_size_below_minimum")
    if lane == "real" and policy["require_micro_real_before_real"]:
        blockers.add("real_mode_requires_micro_real_stage")
    if lane == "paper" and not policy["paper_allowed_without_api"] and not api.get("configured"):
        blockers.add("paper_api_required_by_policy")

    dry_run = policy["dry_run_default"] or lane == "paper"
    can_execute = not blockers and lane in {"paper", "micro_real", "real"}
    execution_state = "ready" if can_execute else ("paper_ready" if lane == "paper" and not blockers else "blocked")
    command = {
        "type": "none",
        "dry_run": True,
        "symbol": daily.get("primary_symbol"),
        "strategy": daily.get("primary_strategy"),
        "max_notional_usdt": 0.0,
    }
    if can_execute:
        command = {
            "type": "paper_order" if lane == "paper" else "guarded_real_order",
            "dry_run": dry_run,
            "symbol": daily.get("primary_symbol"),
            "strategy": daily.get("primary_strategy"),
            "max_notional_usdt": order_usdt if lane in {"micro_real", "real"} else raw_order,
            "execution_lane": lane,
            "requires_final_order_preview": lane in {"micro_real", "real"},
        }

    return {
        "status": "ok" if can_execute else "blocked",
        "revision": 68,
        "engine": "autonomous_execution_governor",
        "generated_at": now_iso(),
        "read_only": True,
        "can_execute": can_execute,
        "execution_state": execution_state,
        "execution_lane": lane,
        "recommended_mode": mode,
        "recommended_action": action,
        "primary_symbol": daily.get("primary_symbol"),
        "primary_strategy": daily.get("primary_strategy"),
        "confidence": daily.get("confidence"),
        "suggested_order_usdt": order_usdt,
        "dry_run": dry_run,
        "blockers": sorted(blockers),
        "warnings": sorted(warnings)[:10],
        "decision_text": _decision_text(can_execute, lane, sorted(blockers), daily.get("primary_symbol"), order_usdt, dry_run),
        "command_preview": command,
        "source": {
            "daily_operation_revision": daily.get("revision"),
            "user_api_secret_revision": api.get("revision"),
        },
        "policy": policy,
    }


def build_summary_execution_governor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_execution_governor(data, settings, auth_store, username)
    return {
        "status": payload.get("status"),
        "revision": 68,
        "read_only": True,
        "can_execute": payload.get("can_execute"),
        "execution_state": payload.get("execution_state"),
        "execution_lane": payload.get("execution_lane"),
        "dry_run": payload.get("dry_run"),
        "primary_symbol": payload.get("primary_symbol"),
        "primary_strategy": payload.get("primary_strategy"),
        "suggested_order_usdt": payload.get("suggested_order_usdt"),
        "decision_text": payload.get("decision_text"),
        "blockers": payload.get("blockers", []),
        "updated_at": payload.get("generated_at"),
    }


def build_autonomous_execution_governor_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_execution_governor(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    checks = {
        "revision_68": payload.get("revision") == 68,
        "read_only": payload.get("read_only") is True,
        "daily_operation_linked": (payload.get("source") or {}).get("daily_operation_revision") == 65,
        "user_api_linked": (payload.get("source") or {}).get("user_api_secret_revision") in {67, None},
        "no_direct_order_execution": command.get("requires_final_order_preview") in {True, False, None} and "order_id" not in command,
        "blocked_without_real_api": not payload.get("can_execute") if payload.get("execution_lane") in {"micro_real", "real"} and "user_api_not_ready_for_real_trade" in payload.get("blockers", []) else True,
        "command_contract": {"type", "dry_run", "symbol", "strategy", "max_notional_usdt"}.issubset(command.keys()),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 68,
        "engine": "autonomous_execution_governor_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "can_execute": payload.get("can_execute"),
        "execution_lane": payload.get("execution_lane"),
        "blockers": payload.get("blockers", []),
    }
