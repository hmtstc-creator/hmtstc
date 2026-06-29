from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_capital_allocator_service import build_autonomous_capital_allocator
from services.autonomous_safety_supervisor_service import build_autonomous_safety_supervisor
from services.trade_quality_feedback_service import build_trade_quality_feedback


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
    raw = settings.get("autonomous_position_manager") if isinstance(settings.get("autonomous_position_manager"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "hard_stop_loss_pct": _clamp(_safe_float(raw.get("hard_stop_loss_pct"), 1.2), 0.1, 8.0),
        "soft_take_profit_pct": _clamp(_safe_float(raw.get("soft_take_profit_pct"), 0.55), 0.05, 6.0),
        "trailing_start_pct": _clamp(_safe_float(raw.get("trailing_start_pct"), 0.35), 0.05, 6.0),
        "max_position_age_minutes": max(1, _safe_int(raw.get("max_position_age_minutes"), 180)),
        "max_managed_positions": max(1, min(20, _safe_int(raw.get("max_managed_positions"), 6))),
        "min_quality_score": _clamp(_safe_float(raw.get("min_quality_score"), 55.0), 0.0, 100.0),
        "read_only": True,
        "auto_apply": False,
    }


def _positions(data: dict) -> list[dict]:
    buckets = []
    for key in ("real_positions", "open_real_positions", "positions", "paper_positions", "open_positions"):
        value = data.get(key)
        if isinstance(value, list):
            buckets.extend(item for item in value if isinstance(item, dict))
    seen: set[str] = set()
    result: list[dict] = []
    for index, item in enumerate(buckets):
        symbol = str(item.get("symbol") or item.get("pair") or f"POSITION_{index}").upper()
        position_id = str(item.get("id") or item.get("position_id") or item.get("order_id") or f"{symbol}_{index}")
        fingerprint = f"{symbol}:{position_id}"
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        entry = _safe_float(item.get("entry_price", item.get("avg_entry", item.get("price", 0.0))))
        mark = _safe_float(item.get("mark_price", item.get("current_price", item.get("last_price", entry))))
        qty = _safe_float(item.get("qty", item.get("quantity", item.get("amount", 0.0))))
        pnl_pct = _safe_float(item.get("pnl_pct", item.get("unrealized_pnl_pct", 0.0)))
        if pnl_pct == 0 and entry > 0 and mark > 0:
            side = str(item.get("side", "LONG")).upper()
            direction = -1.0 if side == "SHORT" else 1.0
            pnl_pct = ((mark - entry) / entry) * 100.0 * direction
        result.append({
            "id": position_id,
            "symbol": symbol,
            "side": str(item.get("side", "LONG")).upper(),
            "entry_price": round(entry, 8),
            "mark_price": round(mark, 8),
            "quantity": round(max(0.0, qty), 8),
            "notional_usdt": round(abs(_safe_float(item.get("notional_usdt"), mark * qty if mark and qty else item.get("value_usdt", 0.0))), 6),
            "pnl_pct": round(pnl_pct, 4),
            "pnl_usdt": round(_safe_float(item.get("pnl_usdt", item.get("unrealized_pnl_usdt", 0.0))), 6),
            "age_minutes": _safe_int(item.get("age_minutes", item.get("holding_minutes", 0))),
            "strategy": str(item.get("strategy", item.get("strategy_id", "unknown"))),
            "source": str(item.get("source", "runtime")),
        })
    return result


def _position_action(position: dict, policy: dict, safety: dict, capital: dict, quality: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    pnl_pct = _safe_float(position.get("pnl_pct"))
    age = _safe_int(position.get("age_minutes"))
    quality_score = _safe_float(quality.get("quality_score", quality.get("last_trade_quality", 0.0)))
    if not policy["enabled"]:
        return "HOLD", ["position_manager_disabled"]
    if safety.get("kill_switch_active") or safety.get("safe_mode_required"):
        return "EXIT_PREVIEW", ["safety_supervisor_requires_protection"]
    if capital.get("allocation_state") == "BLOCKED":
        reasons.append("capital_allocator_blocked")
    if pnl_pct <= -abs(policy["hard_stop_loss_pct"]):
        reasons.append("hard_stop_loss_reached")
        return "EXIT_PREVIEW", reasons
    if pnl_pct >= policy["soft_take_profit_pct"]:
        reasons.append("soft_take_profit_reached")
        return "TAKE_PROFIT_PREVIEW", reasons
    if pnl_pct >= policy["trailing_start_pct"]:
        reasons.append("trailing_start_reached")
        return "TRAILING_PROTECT_PREVIEW", reasons
    if age >= policy["max_position_age_minutes"]:
        reasons.append("position_age_limit_reached")
        return "REDUCE_OR_EXIT_PREVIEW", reasons
    if quality_score and quality_score < policy["min_quality_score"]:
        reasons.append("quality_below_position_threshold")
        return "TIGHTEN_STOP_PREVIEW", reasons
    if reasons:
        return "TIGHTEN_STOP_PREVIEW", reasons
    return "HOLD", ["no_exit_condition"]


def build_autonomous_position_manager(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev74 read-only position lifecycle manager.

    Produces autonomous hold/take-profit/trailing-stop/exit-preview decisions for open
    positions by combining safety, capital allocation, and trade-quality signals. It does
    not place orders and does not persist state; execution stays behind the governor.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    positions = _positions(data)[: policy["max_managed_positions"]]
    safety = build_autonomous_safety_supervisor(data, settings, auth_store, username)
    capital = build_autonomous_capital_allocator(data, settings, auth_store, username)
    quality = build_trade_quality_feedback(data, settings)
    managed: list[dict] = []
    action_counts: dict[str, int] = {}
    blockers: list[str] = []
    for position in positions:
        action, reasons = _position_action(position, policy, safety, capital, quality)
        action_counts[action] = action_counts.get(action, 0) + 1
        if action != "HOLD":
            blockers.extend(reason for reason in reasons if reason not in blockers and reason.endswith(("blocked", "protection")))
        managed.append({
            "id": position.get("id"),
            "symbol": position.get("symbol"),
            "side": position.get("side"),
            "pnl_pct": position.get("pnl_pct"),
            "pnl_usdt": position.get("pnl_usdt"),
            "age_minutes": position.get("age_minutes"),
            "notional_usdt": position.get("notional_usdt"),
            "strategy": position.get("strategy"),
            "recommended_action": action,
            "reasons": reasons,
            "command_preview": {
                "type": "position_lifecycle_preview",
                "symbol": position.get("symbol"),
                "position_id": position.get("id"),
                "action": action,
                "read_only": True,
                "auto_apply": False,
                "places_order": False,
                "source_revision": 74,
            },
        })
    protective_actions = sum(count for action, count in action_counts.items() if action != "HOLD")
    if not policy["enabled"]:
        status = "review"
        lifecycle_state = "DISABLED"
    elif not positions:
        status = "ok"
        lifecycle_state = "NO_OPEN_POSITIONS"
    elif safety.get("kill_switch_active"):
        status = "blocked"
        lifecycle_state = "FORCE_PROTECTION"
    elif protective_actions:
        status = "review"
        lifecycle_state = "MANAGE_PROTECTION"
    else:
        status = "ok"
        lifecycle_state = "HOLD_STABLE"
    return {
        "status": status,
        "revision": 74,
        "engine": "autonomous_position_manager",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "lifecycle_state": lifecycle_state,
        "open_position_count": len(positions),
        "protective_action_count": protective_actions,
        "action_counts": action_counts,
        "managed_positions": managed,
        "blockers": sorted(set(blockers)),
        "inputs": {
            "safety_state": safety.get("safety_state"),
            "kill_switch_active": safety.get("kill_switch_active"),
            "allocation_state": capital.get("allocation_state"),
            "capital_action": capital.get("capital_action"),
            "quality_score": quality.get("quality_score"),
        },
        "policy": policy,
        "command_preview": {
            "type": "position_manager_preview",
            "read_only": True,
            "auto_apply": False,
            "places_order": False,
            "writes_runtime_state": False,
            "source_revision": 74,
        },
    }


def build_summary_autonomous_position_manager(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_position_manager(data, settings, auth_store, username)
    return {
        "status": payload.get("status"),
        "revision": 74,
        "engine": "autonomous_position_manager_summary",
        "generated_at": payload.get("generated_at"),
        "read_only": True,
        "lifecycle_state": payload.get("lifecycle_state"),
        "open_position_count": payload.get("open_position_count", 0),
        "protective_action_count": payload.get("protective_action_count", 0),
        "action_counts": payload.get("action_counts", {}),
        "attention_required": payload.get("status") in {"review", "blocked"},
        "primary_action": next((item.get("recommended_action") for item in payload.get("managed_positions", []) if item.get("recommended_action") != "HOLD"), "HOLD"),
        "blocker_count": len(payload.get("blockers") or []),
    }


def build_autonomous_position_manager_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_autonomous_position_manager(data, settings, auth_store, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    managed = payload.get("managed_positions") if isinstance(payload.get("managed_positions"), list) else []
    checks = {
        "revision_74": payload.get("revision") == 74,
        "read_only": payload.get("read_only") is True and command.get("read_only") is True,
        "auto_apply_disabled": payload.get("auto_apply") is False and command.get("auto_apply") is False,
        "no_direct_order": command.get("places_order") is False and all((item.get("command_preview") or {}).get("places_order") is False for item in managed if isinstance(item, dict)),
        "no_runtime_persistence": command.get("writes_runtime_state") is False,
        "policy_visible": "hard_stop_loss_pct" in (payload.get("policy") or {}),
        "bounded_position_count": len(managed) <= _safe_int((payload.get("policy") or {}).get("max_managed_positions"), 6),
        "source_chain_visible": isinstance(payload.get("inputs"), dict) and "safety_state" in payload.get("inputs", {}),
        "no_secret_leak": "api_secret" not in str(payload).lower() and "signed_payload" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 74,
        "engine": "autonomous_position_manager_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "lifecycle_state": payload.get("lifecycle_state"),
        "protective_action_count": payload.get("protective_action_count"),
        "status_source": payload.get("status"),
    }
