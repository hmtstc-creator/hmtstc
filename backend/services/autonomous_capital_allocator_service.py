from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_evidence_learning_memory_service import build_autonomous_evidence_learning_memory
from services.autonomous_execution_governor_service import build_autonomous_execution_governor
from services.risk_brain_service import build_risk_brain


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_capital_allocator") if isinstance(settings.get("autonomous_capital_allocator"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "target_usdt_reserve_pct": _clamp(_safe_float(raw.get("target_usdt_reserve_pct"), 82.0), 50.0, 99.0),
        "max_trade_capital_pct": _clamp(_safe_float(raw.get("max_trade_capital_pct"), 8.0), 0.1, 25.0),
        "max_symbol_capital_pct": _clamp(_safe_float(raw.get("max_symbol_capital_pct"), 3.0), 0.1, 15.0),
        "profit_lock_pct": _clamp(_safe_float(raw.get("profit_lock_pct"), 60.0), 0.0, 100.0),
        "min_learning_score": _clamp(_safe_float(raw.get("min_learning_score"), 60.0), 0.0, 100.0),
        "min_cash_buffer_usdt": max(0.0, _safe_float(raw.get("min_cash_buffer_usdt"), 20.0)),
        "max_active_symbols": max(1, min(12, _safe_int(raw.get("max_active_symbols"), 4))),
        "read_only": True,
        "auto_apply": False,
    }


def _wallet(data: dict) -> dict:
    candidates = [
        data.get("wallet"),
        data.get("paper_wallet"),
        data.get("account"),
        data.get("balance"),
        data.get("balances"),
    ]
    wallet = next((item for item in candidates if isinstance(item, dict)), {})
    total = _safe_float(wallet.get("total_usdt", wallet.get("equity_usdt", wallet.get("total", 0.0))))
    usdt = _safe_float(wallet.get("usdt", wallet.get("free_usdt", wallet.get("cash_usdt", 0.0))))
    pnl_today = _safe_float(data.get("today_pnl_usdt", data.get("daily_pnl_usdt", wallet.get("today_pnl_usdt", 0.0))))
    if total <= 0 and usdt > 0:
        total = usdt
    if usdt <= 0 and total > 0:
        usdt = total
    return {
        "total_usdt": round(max(0.0, total), 6),
        "free_usdt": round(max(0.0, usdt), 6),
        "today_pnl_usdt": round(pnl_today, 6),
        "usdt_reserve_pct": round((usdt / total * 100.0), 2) if total > 0 else 100.0,
    }


def _allocation_state(wallet: dict, policy: dict, execution: dict, risk: dict, learning: dict) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not policy["enabled"]:
        blockers.append("capital_allocator_disabled")
    if execution.get("can_execute") is False:
        blockers.append("execution_governor_blocked")
    if learning.get("learning_score", 0) < policy["min_learning_score"]:
        blockers.append("learning_score_below_capital_threshold")
    if wallet["free_usdt"] < policy["min_cash_buffer_usdt"]:
        blockers.append("cash_buffer_below_minimum")
    if wallet["usdt_reserve_pct"] < policy["target_usdt_reserve_pct"]:
        warnings.append("usdt_reserve_below_target")
    if risk.get("risk_status") in {"blocked", "danger", "critical"}:
        blockers.append("risk_brain_blocked")
    if blockers:
        return "BLOCKED", sorted(set(blockers)), sorted(set(warnings))
    if warnings:
        return "DEFENSIVE", sorted(set(blockers)), sorted(set(warnings))
    return "ALLOCATE", sorted(set(blockers)), sorted(set(warnings))


def _suggestion(wallet: dict, policy: dict, state: str, risk: dict, learning: dict) -> dict:
    total = wallet["total_usdt"]
    free = wallet["free_usdt"]
    trade_pool = total * policy["max_trade_capital_pct"] / 100.0
    reserve_required = total * policy["target_usdt_reserve_pct"] / 100.0
    reserve_gap = max(0.0, reserve_required - free)
    available_after_buffer = max(0.0, free - policy["min_cash_buffer_usdt"] - reserve_gap)
    risk_order = _safe_float(risk.get("suggested_order_usdt", risk.get("order_size_usdt", trade_pool)))
    max_symbol = total * policy["max_symbol_capital_pct"] / 100.0
    if state == "BLOCKED":
        suggested_order = 0.0
        capital_action = "hold_cash"
    elif state == "DEFENSIVE":
        suggested_order = min(risk_order, max_symbol, trade_pool, available_after_buffer) * 0.5
        capital_action = "defensive_micro_allocation"
    else:
        quality_boost = 1.0 if _safe_float(learning.get("learning_score")) >= 75 else 0.75
        suggested_order = min(risk_order, max_symbol, trade_pool, available_after_buffer) * quality_boost
        capital_action = "allow_bounded_allocation" if suggested_order > 0 else "hold_cash"
    locked_profit = max(0.0, wallet["today_pnl_usdt"]) * policy["profit_lock_pct"] / 100.0
    return {
        "capital_action": capital_action,
        "suggested_order_usdt": round(max(0.0, suggested_order), 6),
        "max_trade_pool_usdt": round(trade_pool, 6),
        "max_symbol_usdt": round(max_symbol, 6),
        "reserved_usdt_target": round(reserve_required, 6),
        "reserve_gap_usdt": round(reserve_gap, 6),
        "profit_lock_usdt": round(locked_profit, 6),
        "max_active_symbols": policy["max_active_symbols"],
    }


def build_autonomous_capital_allocator(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev73 read-only autonomous capital allocation governor.

    Converts the scanner/mode/strategy/risk/quality/safety/evidence chain into a compact
    capital-use decision: how much cash stays in USDT, whether allocation is blocked,
    and what the maximum bounded next order size should be. It never places orders,
    never stores secrets, and never mutates runtime state.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    wallet = _wallet(data)
    execution = build_autonomous_execution_governor(data, settings, auth_store, username)
    risk = build_risk_brain(data, settings)
    learning = build_autonomous_evidence_learning_memory(data, settings, auth_store, username)
    state, blockers, warnings = _allocation_state(wallet, policy, execution, risk, learning)
    suggestion = _suggestion(wallet, policy, state, risk, learning)
    status = "blocked" if state == "BLOCKED" else ("review" if state == "DEFENSIVE" else "ok")
    return {
        "status": status,
        "revision": 73,
        "engine": "autonomous_capital_allocator",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "allocation_state": state,
        "capital_action": suggestion["capital_action"],
        "wallet": wallet,
        "suggestion": suggestion,
        "blockers": blockers,
        "warnings": warnings,
        "inputs": {
            "execution_state": execution.get("execution_state"),
            "can_execute": execution.get("can_execute"),
            "risk_status": risk.get("risk_status"),
            "risk_suggested_order_usdt": risk.get("suggested_order_usdt"),
            "learning_score": learning.get("learning_score"),
            "learning_status": learning.get("status"),
        },
        "policy": policy,
        "command_preview": {
            "type": "capital_allocation_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "writes_runtime_state": False,
            "source_revision": 73,
        },
    }


def build_summary_autonomous_capital_allocator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_capital_allocator(data, settings, auth_store, username)
    suggestion = payload.get("suggestion") if isinstance(payload.get("suggestion"), dict) else {}
    wallet = payload.get("wallet") if isinstance(payload.get("wallet"), dict) else {}
    return {
        "status": payload.get("status"),
        "revision": 73,
        "engine": "autonomous_capital_allocator_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "allocation_state": payload.get("allocation_state"),
        "capital_action": payload.get("capital_action"),
        "suggested_order_usdt": suggestion.get("suggested_order_usdt", 0.0),
        "usdt_reserve_pct": wallet.get("usdt_reserve_pct", 100.0),
        "profit_lock_usdt": suggestion.get("profit_lock_usdt", 0.0),
        "reserve_gap_usdt": suggestion.get("reserve_gap_usdt", 0.0),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
    }


def build_autonomous_capital_allocator_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_capital_allocator(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    suggestion = payload.get("suggestion") if isinstance(payload.get("suggestion"), dict) else {}
    wallet = payload.get("wallet") if isinstance(payload.get("wallet"), dict) else {}
    checks = {
        "revision_73": payload.get("revision") == 73,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "no_direct_order": command.get("places_order") is False,
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "wallet_visible": isinstance(wallet.get("total_usdt"), (int, float)) and isinstance(wallet.get("free_usdt"), (int, float)),
        "bounded_order_size": _safe_float(suggestion.get("suggested_order_usdt")) <= _safe_float(suggestion.get("max_symbol_usdt", 0.0)) + 0.000001,
        "reserve_policy_visible": "target_usdt_reserve_pct" in (payload.get("policy") or {}),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "signed_payload" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 73,
        "engine": "autonomous_capital_allocator_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "allocation_state": payload.get("allocation_state"),
        "suggested_order_usdt": suggestion.get("suggested_order_usdt"),
        "status_source": payload.get("status"),
    }
