from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_profit_protection_scaling_rules_service import (
    build_autonomous_profit_protection_scaling_rules,
)


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
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled", "allow", "auto"}
    if value is None:
        return fallback
    return bool(value)


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    raw = settings.get("autonomous_operator_free_dashboard") if isinstance(settings.get("autonomous_operator_free_dashboard"), dict) else {}
    return {
        "enabled": _safe_bool(raw.get("enabled"), True),
        "required_source_revision": 98,
        "network_calls_allowed": _safe_bool(raw.get("network_calls_allowed"), False),
        "direct_order_enabled": _safe_bool(raw.get("direct_order_enabled"), False),
        "runtime_write_enabled": _safe_bool(raw.get("runtime_write_enabled"), False),
        "real_submit_enabled": _safe_bool(raw.get("real_submit_enabled"), False),
        "hide_advanced_pages": _safe_bool(raw.get("hide_advanced_pages"), True),
        "attention_only_alerts": _safe_bool(raw.get("attention_only_alerts"), True),
        "max_attention_items": max(1, min(12, _safe_int(raw.get("max_attention_items"), 5))),
        "max_visible_tiles": 5,
        "critical_pnl_loss_usdt": min(-0.1, _safe_float(raw.get("critical_pnl_loss_usdt"), -5.0)),
        "risk_review_keywords": {"review", "blocked", "stop", "reduce", "halt", "lock"},
    }


def _source(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    raw = data.get("autonomous_profit_protection_scaling_rules") if isinstance(data.get("autonomous_profit_protection_scaling_rules"), dict) else None
    if raw and raw.get("revision") == 98 and "command_preview" in raw:
        return raw
    return build_autonomous_profit_protection_scaling_rules(data, settings, auth_store, username)


def _compact_state(value: Any, fallback: str = "review") -> str:
    text = str(value or fallback).strip().lower()
    if text in {"ok", "ready", "clear", "increase", "start_preview", "run_preview", "healthy"}:
        return "ok"
    if text in {"blocked", "stop", "halt", "error", "critical", "failed"}:
        return "blocked"
    if text in {"review", "reduce", "hold", "warning", "pending", "manual_attention"}:
        return "review"
    return text or fallback


def _attention_items(data: dict, source: dict, policy: dict) -> list[dict]:
    items: list[dict] = []
    for blocker in source.get("blockers") or []:
        items.append({"level": "blocked", "message": str(blocker), "source": "rev98"})
    for warning in source.get("warnings") or []:
        items.append({"level": "review", "message": str(warning), "source": "rev98"})
    today_pnl = _safe_float(source.get("today_pnl_usdt", data.get("today_real_pnl_usdt", data.get("today_pnl_usdt"))), 0.0)
    if today_pnl <= policy["critical_pnl_loss_usdt"]:
        items.append({"level": "blocked", "message": "daily_loss_attention_required", "source": "pnl"})
    if _safe_bool(data.get("kill_switch_active"), False) or _safe_bool(data.get("emergency_lock_active"), False):
        items.append({"level": "blocked", "message": "emergency_or_kill_switch_active", "source": "safety"})
    if _safe_bool(data.get("manual_attention_required"), False):
        items.append({"level": "review", "message": "manual_attention_required", "source": "runtime"})
    return items[: policy["max_attention_items"]]


def build_autonomous_operator_free_dashboard(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Rev99 operator-free dashboard controller.

    This layer compresses the autonomous stack into five owner-facing signals and
    action-control previews. It does not place orders, call exchanges, or write
    runtime state; emergency/safe-mode controls are exposed as explicit UI actions.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    auth_store = deepcopy(auth_store or {})
    policy = _policy(settings)
    source = _source(data, settings, auth_store, username)
    blockers: list[str] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("operator_free_dashboard_disabled")
    if source.get("revision") != policy["required_source_revision"]:
        blockers.append("source_profit_protection_revision_mismatch")
    if policy["network_calls_allowed"]:
        blockers.append("network_calls_must_remain_disabled_for_rev99")
    if policy["direct_order_enabled"]:
        blockers.append("direct_order_must_remain_disabled_for_rev99")
    if policy["runtime_write_enabled"]:
        blockers.append("runtime_write_must_remain_disabled_for_rev99")
    if policy["real_submit_enabled"]:
        blockers.append("real_submit_must_remain_disabled_for_rev99")

    source_decision = str(source.get("decision") or "hold").lower()
    source_status = _compact_state(source.get("status"))
    today_pnl = _safe_float(source.get("today_pnl_usdt", data.get("today_real_pnl_usdt", data.get("today_pnl_usdt"))), 0.0)
    risk_state = "normal"
    if source_decision in {"reduce", "hold"} or source_status == "review":
        risk_state = "review"
    if source_decision == "stop" or source_status == "blocked" or blockers:
        risk_state = "blocked"

    attention = _attention_items(data, source, policy)
    warning_levels = {item.get("level") for item in attention}
    if "blocked" in warning_levels:
        intervention = "required"
    elif "review" in warning_levels or warnings:
        intervention = "review"
    else:
        intervention = "none"

    market_tradeable = "yes" if source_decision in {"increase", "hold"} and risk_state == "normal" else "review"
    if risk_state == "blocked":
        market_tradeable = "no"
    bot_mode = "AUTONOMOUS_SMALL_CAPITAL"
    if source_decision == "stop" or risk_state == "blocked":
        bot_mode = "SAFE_MODE"
    elif source_decision == "reduce":
        bot_mode = "REDUCED_RISK"
    elif source_decision == "increase":
        bot_mode = "CONTROLLED_SCALE"

    action_taken = "continue_monitoring"
    if source_decision == "increase":
        action_taken = "protect_profit_and_allow_controlled_scale_preview"
    elif source_decision == "reduce":
        action_taken = "reduce_risk_preview"
    elif source_decision == "stop" or risk_state == "blocked":
        action_taken = "halt_new_risk_and_require_attention"
    elif source_decision == "hold":
        action_taken = "hold_current_limits"

    status = "blocked" if blockers or risk_state == "blocked" else ("review" if attention or warnings or risk_state == "review" else "ok")
    tiles = [
        {"key": "bot_mode", "label": "Bot Modu", "value": bot_mode, "tone": _compact_state(bot_mode)},
        {"key": "market_tradeable", "label": "Piyasa İşlem Durumu", "value": market_tradeable, "tone": market_tradeable},
        {"key": "today_pnl", "label": "Bugünkü PnL", "value": round(today_pnl, 4), "unit": "USDT", "tone": "ok" if today_pnl >= 0 else "blocked"},
        {"key": "risk", "label": "Risk", "value": risk_state, "tone": risk_state},
        {"key": "intervention", "label": "Müdahale", "value": intervention, "tone": intervention},
    ]
    control_actions = {
        "emergency_stop": {
            "label": "Emergency Stop",
            "endpoint": "/api/real/emergency/lock",
            "method": "POST",
            "requires_owner": True,
            "preview_only": True,
            "auto_execute": False,
        },
        "safe_mode": {
            "label": "Safe Mode",
            "endpoint": "/api/real/lock",
            "method": "POST",
            "requires_owner": True,
            "preview_only": True,
            "auto_execute": False,
        },
    }
    evidence_seed = f"rev99|{username}|{source.get('generated_at')}|{source_decision}|{status}|{today_pnl}"
    return {
        "status": status,
        "revision": 99,
        "engine": "autonomous_operator_free_dashboard",
        "generated_at": now_iso(),
        "source_revision": source.get("revision"),
        "source_decision": source_decision,
        "operator_mode": "operator_free_attention_only",
        "bot_mode": bot_mode,
        "market_tradeable": market_tradeable,
        "today_pnl_usdt": round(today_pnl, 4),
        "risk_state": risk_state,
        "intervention_required": intervention,
        "action_taken_or_recommended": action_taken,
        "visible_tiles": tiles[: policy["max_visible_tiles"]],
        "attention_items": attention,
        "hidden_advanced_pages": policy["hide_advanced_pages"],
        "attention_only_alerts": policy["attention_only_alerts"],
        "control_actions": control_actions,
        "day_end_report_preview": {
            "enabled": True,
            "format": "short_summary",
            "fields": ["bot_mode", "today_pnl_usdt", "risk_state", "action_taken_or_recommended", "attention_items"],
            "auto_send": False,
        },
        "command_preview": {
            "type": "operator_free_dashboard_preview",
            "read_only": True,
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "auto_execute_control": False,
            "direct_order_enabled": False,
            "real_submit_enabled": False,
            "advanced_pages_hidden_by_default": policy["hide_advanced_pages"],
        },
        "safety_contract": {
            "contains_secret": False,
            "direct_order_placement": False,
            "exchange_request": False,
            "runtime_write": False,
            "owner_controls_require_explicit_click": True,
            "approval_gated": True,
        },
        "audit_evidence": {
            "evidence_id": sha256(evidence_seed.encode("utf-8")).hexdigest()[:24],
            "source_engine": source.get("engine"),
            "source_status": source.get("status"),
            "source_decision": source_decision,
            "blocker_count": len(blockers),
            "attention_count": len(attention),
        },
        "blockers": blockers,
        "warnings": warnings,
        "read_only": True,
        "dry_run": True,
    }


def _summary_from_payload(payload: dict) -> dict:
    return {
        "status": payload.get("status", "review"),
        "revision": 99,
        "engine": "autonomous_operator_free_dashboard_summary",
        "generated_at": payload.get("generated_at"),
        "operator_mode": payload.get("operator_mode"),
        "bot_mode": payload.get("bot_mode"),
        "market_tradeable": payload.get("market_tradeable"),
        "today_pnl_usdt": payload.get("today_pnl_usdt"),
        "risk_state": payload.get("risk_state"),
        "intervention_required": payload.get("intervention_required"),
        "action_taken_or_recommended": payload.get("action_taken_or_recommended"),
        "visible_tiles": payload.get("visible_tiles") or [],
        "attention_items": payload.get("attention_items") or [],
        "control_actions": payload.get("control_actions") or {},
        "hidden_advanced_pages": payload.get("hidden_advanced_pages"),
        "attention_only_alerts": payload.get("attention_only_alerts"),
        "blocker_count": len(payload.get("blockers") or []),
        "warning_count": len(payload.get("warnings") or []),
        "read_only": True,
        "dry_run": True,
        "real_submit_enabled": False,
    }


def build_summary_autonomous_operator_free_dashboard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    return _summary_from_payload(build_autonomous_operator_free_dashboard(data, settings, auth_store, username))


def build_autonomous_operator_free_dashboard_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    sample = data or {
        "autonomous_profit_protection_scaling_rules": {
            "revision": 98,
            "status": "ok",
            "decision": "increase",
            "today_pnl_usdt": 3.5,
            "warnings": [],
            "blockers": [],
            "command_preview": {"read_only": True, "places_order": False, "sends_exchange_request": False, "writes_runtime_state": False},
            "generated_at": now_iso(),
        }
    }
    payload = build_autonomous_operator_free_dashboard(sample, settings or {"autonomous_operator_free_dashboard": {"enabled": True}}, auth_store or {}, username)
    command = payload.get("command_preview") if isinstance(payload.get("command_preview"), dict) else {}
    controls = payload.get("control_actions") if isinstance(payload.get("control_actions"), dict) else {}
    checks = {
        "revision_is_99": payload.get("revision") == 99,
        "source_profit_protection_chain_present": payload.get("source_revision") == 98,
        "five_visible_tiles": len(payload.get("visible_tiles") or []) == 5,
        "attention_only_alerts_present": payload.get("attention_only_alerts") is True,
        "emergency_stop_control_present": "emergency_stop" in controls,
        "safe_mode_control_present": "safe_mode" in controls,
        "controls_are_explicit_click_only": all((item or {}).get("auto_execute") is False for item in controls.values()),
        "service_does_not_place_order": command.get("places_order") is False,
        "service_does_not_execute_network_call": command.get("sends_exchange_request") is False,
        "service_does_not_write_runtime": command.get("writes_runtime_state") is False,
        "direct_order_off": command.get("direct_order_enabled") is False,
        "real_submit_off": command.get("real_submit_enabled") is False,
        "secret_safe": payload.get("safety_contract", {}).get("contains_secret") is False,
        "summary_revision_is_99": _summary_from_payload(payload).get("revision") == 99,
    }
    passed = all(checks.values())
    return {
        "status": "ok" if passed else "review",
        "revision": 99,
        "engine": "autonomous_operator_free_dashboard_quality",
        "generated_at": now_iso(),
        "quality_status": "OPERATOR_FREE_DASHBOARD_OK" if passed else "OPERATOR_FREE_DASHBOARD_REVIEW",
        "checks": checks,
        "summary": _summary_from_payload(payload),
        "sample_status": payload.get("status"),
        "sample_bot_mode": payload.get("bot_mode"),
    }
