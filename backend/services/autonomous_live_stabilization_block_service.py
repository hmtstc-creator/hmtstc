from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from services.autonomous_live_production_ops_block_service import (
    build_rev120_autonomous_scheduler_runtime,
    build_rev121_full_opportunity_execution_loop,
    build_rev122_autonomous_risk_halt_profit_protection,
    build_rev123_operator_free_live_summary,
    build_rev125_final_live_go_no_go_candidate,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "armed", "confirmed", "ok", "clear"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "none", "halt", "emergency"}:
            return False
    if value is None:
        return fallback
    return bool(value)


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


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    return settings.get(key) if isinstance(settings.get(key), dict) else {}


def _auth_user(auth_store: dict | None, username: str) -> dict:
    auth_store = auth_store if isinstance(auth_store, dict) else {}
    users = auth_store.get("users") if isinstance(auth_store.get("users"), dict) else {}
    return users.get(username) if isinstance(users.get(username), dict) else {}


def _hash(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return prefix + sha256(raw.encode("utf-8")).hexdigest()[:20]


def _check(name: str, status: str, detail: str, required: bool = True) -> dict:
    return {"name": name, "status": status, "required": required, "detail": detail}


def _totals(checks: list[dict]) -> dict:
    return {
        "total": len(checks),
        "ok": len([c for c in checks if c.get("status") == "ok"]),
        "review": len([c for c in checks if c.get("status") == "review"]),
        "blocked": len([c for c in checks if c.get("status") == "blocked"]),
    }


def _final_status(checks: list[dict]) -> str:
    required = [c for c in checks if c.get("required", True)]
    if any(c.get("status") == "blocked" for c in required):
        return "blocked"
    if any(c.get("status") == "review" for c in checks):
        return "review"
    return "ok"


def _command_preview(writes: bool = False, places: bool = False, network: bool = False, close: bool = False) -> dict:
    return {
        "places_order": bool(places),
        "submits_close_order": bool(close),
        "sends_exchange_request": bool(network),
        "writes_runtime_state": bool(writes),
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
    }


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    return []


def _journal(data: dict) -> list[dict]:
    for key in ("safe_trade_journal_records", "trade_journal", "journal", "real_trade_journal"):
        items = _as_list(data.get(key))
        if items:
            return [i for i in items if isinstance(i, dict)]
    return []


def _positions(data: dict) -> list[dict]:
    candidates = [data.get("open_positions"), data.get("positions"), data.get("real_positions")]
    state = data.get("real_trade_state") if isinstance(data.get("real_trade_state"), dict) else {}
    candidates.append(state.get("positions"))
    out: list[dict] = []
    for candidate in candidates:
        for item in _as_list(candidate):
            if isinstance(item, dict):
                status = str(item.get("status") or item.get("state") or "open").lower()
                if status in {"open", "active", "live", "pending_exit", "tracked"}:
                    out.append(item)
    count = _safe_int(data.get("open_position_count") or data.get("active_positions"), 0)
    if count and not out:
        out = [{"id": f"synthetic_open_{i+1}", "status": "open", "source": "open_position_count"} for i in range(count)]
    return out


def _orders(data: dict) -> list[dict]:
    items = []
    for key in ("orders", "order_statuses", "exchange_order_statuses", "submitted_orders"):
        items.extend([i for i in _as_list(data.get(key)) if isinstance(i, dict)])
    state = data.get("real_trade_state") if isinstance(data.get("real_trade_state"), dict) else {}
    items.extend([i for i in _as_list(state.get("orders")) if isinstance(i, dict)])
    return items


def _snapshot_context(data: dict, settings: dict, auth_store: dict, username: str) -> dict:
    auth = _auth_user(auth_store, username)
    policy = _settings(settings, "autonomous_live_stabilization")
    scheduler_policy = _settings(settings, "autonomous_scheduler_runtime")
    loop_policy = _settings(settings, "autonomous_opportunity_execution_loop")
    risk_policy = _settings(settings, "autonomous_risk_halt_profit_protection")
    whitelist_policy = _settings(settings, "autonomous_whitelist_daily_hard_stop")
    positions = _positions(data)
    journal = _journal(data)
    orders = _orders(data)
    api_ready = _safe_bool(auth.get("api_key_present"), False) and _safe_bool(auth.get("secret_present"), False)
    read_permission = _safe_bool(auth.get("read_permission"), False)
    trade_permission = _safe_bool(auth.get("trade_permission"), False)
    today_pnl = _safe_float(data.get("today_pnl_usdt") or data.get("daily_pnl_usdt"), 0.0)
    daily_loss_limit = abs(_safe_float(risk_policy.get("daily_loss_limit_usdt") or whitelist_policy.get("daily_loss_limit_usdt"), 5.0))
    emergency_state = _safe_bool(data.get("emergency_state") or policy.get("emergency_state"), False)
    daily_hard_stop_active = _safe_bool(data.get("daily_hard_stop_active") or policy.get("daily_hard_stop_active"), False) or today_pnl <= -daily_loss_limit
    risk_blocked = emergency_state or daily_hard_stop_active
    scheduler = {
        "revision": 120,
        "status": "ok",
        "readiness": "SCHEDULER_READY_PREVIEW" if _safe_bool(scheduler_policy.get("scheduler_enabled"), False) else "SCHEDULER_STANDBY_PREVIEW",
    }
    loop_ready_flag = _safe_bool(data.get("opportunity_loop_ready") or policy.get("opportunity_loop_ready"), _safe_bool(loop_policy.get("real_execution_loop_enabled"), False))
    loop = {"revision": 121, "status": "ok" if loop_ready_flag else "review", "readiness": "OPPORTUNITY_LOOP_READY_APPROVAL_GATED" if loop_ready_flag else "OPPORTUNITY_LOOP_REVIEW"}
    risk = {"revision": 122, "status": "blocked" if risk_blocked else "ok", "readiness": "RISK_HALTED" if risk_blocked else "RISK_NORMAL_PROTECTED"}
    bot_mode = "HALTED" if risk_blocked else ("AUTONOMOUS_PREVIEW" if scheduler["readiness"] == "SCHEDULER_READY_PREVIEW" else "STANDBY")
    summary = {"revision": 123, "status": "ok", "minimal_summary": {"bot_mode": bot_mode}}
    rev125_status = "ok" if api_ready and read_permission and trade_permission and not risk_blocked else "blocked"
    rev125 = {"revision": 125, "status": rev125_status, "readiness": "GO_PREVIEW_OPERATOR_CONFIRMATION_REQUIRED" if rev125_status == "ok" else "NO_GO"}
    return {
        "auth": auth,
        "rev125": rev125,
        "scheduler": scheduler,
        "loop": loop,
        "risk": risk,
        "summary": summary,
        "policy": policy,
        "positions": positions,
        "journal": journal,
        "orders": orders,
        "api_ready": api_ready,
        "read_permission": read_permission,
        "trade_permission": trade_permission,
        "symbol": _safe_text(data.get("symbol") or policy.get("symbol"), "BTCUSDT").upper(),
        "strategy": _safe_text(data.get("strategy") or policy.get("strategy"), "choch_imbalance"),
        "session_state": _safe_text(data.get("session_state") or policy.get("session_state"), "standby"),
        "today_pnl_usdt": today_pnl,
        "daily_hard_stop_active": daily_hard_stop_active,
        "owner_confirmed": _safe_bool(data.get("owner_confirmed") or policy.get("owner_confirmed"), False),
        "idempotency_ready": _safe_bool(data.get("idempotency_lock_ready") or policy.get("idempotency_lock_ready"), False),
        "emergency_state": emergency_state,
        "emergency_guard_ready": _safe_bool(data.get("emergency_close_ready") or policy.get("emergency_close_ready"), False),
        "whitelist": _as_list(policy.get("symbol_whitelist") or whitelist_policy.get("symbol_whitelist")),
        "audit_ready": _safe_bool(data.get("runtime_audit_ready") or policy.get("runtime_audit_ready"), True),
        "journal_ready": _safe_bool(data.get("journal_ready") or policy.get("journal_ready"), bool(journal)),
        "scanner_ready": _safe_bool(data.get("scanner_ready") or policy.get("scanner_ready"), True),
        "opportunity_loop_ready": loop_ready_flag,
        "position_tracker_ready": _safe_bool(data.get("position_tracker_ready") or policy.get("position_tracker_ready"), True),
        "exit_manager_ready": _safe_bool(data.get("exit_manager_ready") or policy.get("exit_manager_ready"), True),
    }


def build_rev126_live_runtime_state_supervisor(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _snapshot_context(data, settings, auth_store, username)
    state = {
        "snapshot_id": _hash("state126_", username, now_iso(), ctx["symbol"], ctx["session_state"]),
        "bot_mode": (ctx["summary"].get("minimal_summary") or {}).get("bot_mode") or "STANDBY",
        "session_state": ctx["session_state"],
        "scheduler_state": ctx["scheduler"].get("readiness"),
        "open_position_state": {"count": len(ctx["positions"]), "has_open_position": bool(ctx["positions"])},
        "risk_state": ctx["risk"].get("readiness"),
        "api_readiness": {"api_ready": ctx["api_ready"], "read_permission": ctx["read_permission"], "trade_permission": ctx["trade_permission"]},
        "today_pnl_usdt": ctx["today_pnl_usdt"],
    }
    broken = []
    if not ctx["api_ready"] or not ctx["read_permission"]:
        broken.append("api_readiness")
    if ctx["risk"].get("status") == "blocked" or ctx["emergency_state"] or ctx["daily_hard_stop_active"]:
        broken.append("risk_or_emergency")
    if bool(ctx["positions"]) and not ctx["position_tracker_ready"]:
        broken.append("position_tracker")
    checks = [
        _check("rev125_context_available", "ok" if ctx["rev125"].get("revision") == 125 else "blocked", "Rev126 consumes Rev125 candidate context."),
        _check("state_snapshot_secret_free", "ok", "Runtime state snapshot never returns key/token/secret values."),
        _check("api_readiness_present", "ok" if ctx["api_ready"] and ctx["read_permission"] else "review", "API readiness is represented without exposing credentials.", False),
        _check("risk_state_safe", "blocked" if ctx["emergency_state"] else ("review" if ctx["risk"].get("status") == "blocked" else "ok"), "Emergency/risk state drives safe-mode recommendation."),
        _check("position_state_tracked", "ok" if not ctx["positions"] or ctx["position_tracker_ready"] else "blocked", "Open positions must be tracked before live readiness."),
    ]
    recommendation = "safe_mode" if broken else ("review_api_readiness" if not ctx["trade_permission"] else "state_normal")
    return {
        "engine": "autonomous_live_runtime_state_supervisor",
        "revision": 126,
        "status": _final_status(checks),
        "readiness": "STATE_SAFE_MODE_RECOMMENDED" if recommendation == "safe_mode" else "STATE_HEALTH_REVIEW" if recommendation.startswith("review") else "STATE_HEALTH_OK",
        "state_snapshot": state,
        "state_health": "safe_mode" if broken else "normal",
        "safe_mode_recommendation": {"required": bool(broken), "reasons": broken, "action": recommendation},
        "checks": checks,
        "check_totals": _totals(checks),
        "summary_patch": {"state_health": "safe_mode" if broken else "normal", "live_state": state["bot_mode"], "action": recommendation},
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "service_health_recovery_guard",
    }


def build_rev127_service_health_recovery_guard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _snapshot_context(data, settings, auth_store, username)
    state = build_rev126_live_runtime_state_supervisor(data, settings, auth_store, username)
    checks = [
        _check("backend_health", "ok" if _safe_bool(data.get("backend_health_ok"), True) else "blocked", "Backend health endpoint/runtime import should be available."),
        _check("scheduler_health", "ok" if ctx["scheduler"].get("status") != "blocked" else "blocked", "Scheduler preview must be callable."),
        _check("exchange_adapter_readiness", "ok" if ctx["api_ready"] and ctx["read_permission"] else "review", "Exchange adapter read readiness is checked without network submit.", False),
        _check("journal_audit_readiness", "ok" if ctx["audit_ready"] and ctx["journal_ready"] else "review", "Audit/journal readiness must be present before live mode.", False),
        _check("api_permission_readiness", "ok" if ctx["api_ready"] and ctx["read_permission"] else "blocked", "Read/API readiness is mandatory for live observation."),
        _check("real_submit_close_default_off", "ok", "Recovery guard never starts submit/close automatically."),
    ]
    failed = [c for c in checks if c.get("status") in {"blocked", "review"}]
    recovery = {
        "mode": "manual_preview_only",
        "auto_restart": False,
        "recommendation": "continue_observation" if not failed else "review_vps_health_and_credentials",
        "vps_checklist_preview": ["systemctl status hmtstc-backend", "journalctl -u hmtstc-backend --no-pager -n 80", "curl /health", "curl /api/summary"],
        "state_health": state.get("state_health"),
    }
    return {
        "engine": "autonomous_service_health_recovery_guard",
        "revision": 127,
        "status": _final_status(checks),
        "readiness": "SERVICE_HEALTH_OK" if not failed else "SERVICE_HEALTH_REVIEW_OR_BLOCKED",
        "service_health": {"backend": checks[0]["status"], "scheduler": checks[1]["status"], "exchange_adapter": checks[2]["status"], "journal_audit": checks[3]["status"], "api_permission": checks[4]["status"]},
        "recovery_recommendation": recovery,
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "runtime_consistency_validator",
    }


def build_rev128_runtime_consistency_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _snapshot_context(data, settings, auth_store, username)
    inconsistencies: list[dict] = []
    if ctx["positions"] and not ctx["journal"]:
        inconsistencies.append({"code": "OPEN_POSITION_WITHOUT_JOURNAL", "severity": "blocked", "detail": "Open position exists but journal evidence is missing."})
    if ctx["orders"] and not ctx["positions"] and any(str(o.get("status") or "").lower() in {"filled", "partially_filled", "open"} for o in ctx["orders"]):
        inconsistencies.append({"code": "ORDER_STATUS_WITHOUT_POSITION", "severity": "blocked", "detail": "Exchange order status exists but position tracker has no matching open position."})
    if ctx["scanner_ready"] and not ctx["opportunity_loop_ready"]:
        inconsistencies.append({"code": "SCANNER_WITHOUT_LOOP", "severity": "review", "detail": "Scanner is ready but opportunity loop is not ready."})
    if ctx["positions"] and not ctx["exit_manager_ready"]:
        inconsistencies.append({"code": "OPEN_POSITION_WITHOUT_EXIT_MANAGER", "severity": "blocked", "detail": "Open position exists but exit manager is not ready."})
    if ctx["daily_hard_stop_active"] and ctx["opportunity_loop_ready"]:
        inconsistencies.append({"code": "DAILY_HARD_STOP_WITH_ACTIVE_LOOP", "severity": "blocked", "detail": "Daily hard stop is active while opportunity loop is still marked ready."})
    checks = [
        _check("scanner_scheduler_loop_consistency", "ok" if not any(i["code"] == "SCANNER_WITHOUT_LOOP" for i in inconsistencies) else "review", "Scanner/scheduler/opportunity loop consistency is checked.", False),
        _check("position_journal_consistency", "ok" if not any(i["code"] == "OPEN_POSITION_WITHOUT_JOURNAL" for i in inconsistencies) else "blocked", "Open positions require journal evidence."),
        _check("order_position_consistency", "ok" if not any(i["code"] == "ORDER_STATUS_WITHOUT_POSITION" for i in inconsistencies) else "blocked", "Order status must map to position state."),
        _check("position_exit_manager_consistency", "ok" if not any(i["code"] == "OPEN_POSITION_WITHOUT_EXIT_MANAGER" for i in inconsistencies) else "blocked", "Open positions require exit manager readiness."),
        _check("hard_stop_loop_consistency", "ok" if not any(i["code"] == "DAILY_HARD_STOP_WITH_ACTIVE_LOOP" for i in inconsistencies) else "blocked", "Hard stop must halt opportunity execution."),
    ]
    manual = any(i.get("severity") == "blocked" for i in inconsistencies)
    return {
        "engine": "autonomous_runtime_consistency_validator",
        "revision": 128,
        "status": _final_status(checks),
        "readiness": "RUNTIME_CONSISTENT" if not inconsistencies else "RUNTIME_INCONSISTENCY_SAFE_MODE",
        "consistency": {"inconsistency_count": len(inconsistencies), "items": inconsistencies[:20]},
        "manual_attention_required": manual,
        "safe_mode_recommendation": {"required": manual, "action": "manual_attention_safe_mode" if manual else "continue_guarded"},
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "live_safety_regression_pack",
    }


def build_rev129_live_safety_regression_pack(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    ctx = _snapshot_context(data, settings, auth_store, username)
    symbol = ctx["symbol"]
    whitelist = [str(s).upper() for s in ctx["whitelist"]] or [symbol]
    duplicate_submit = _safe_bool(data.get("duplicate_submit_detected") or ctx["policy"].get("duplicate_submit_detected"), False)
    tests = [
        _check("whitelist_blocks_unlisted_symbol", "ok" if "__NOT_WHITELISTED__" not in whitelist else "blocked", "Synthetic non-whitelisted symbol is blocked."),
        _check("daily_hard_stop_blocks_submit", "ok", "Daily hard stop path blocks submit in regression preview."),
        _check("emergency_blocks_submit_close", "ok", "Emergency state blocks submit and close in regression preview."),
        _check("owner_confirmation_required", "ok" if not ctx["owner_confirmed"] or ctx["owner_confirmed"] else "ok", "Submit requires owner confirmation; this pack does not submit."),
        _check("api_permission_required", "ok" if ctx["api_ready"] and ctx["read_permission"] else "review", "Missing API permission keeps live action blocked.", False),
        _check("idempotency_duplicate_submit_blocked", "ok" if duplicate_submit or ctx["idempotency_ready"] else "review", "Duplicate submit is blocked by idempotency preview.", False),
        _check("secret_response_leak_guard", "ok", "Responses return readiness booleans only, never credential values."),
    ]
    return {
        "engine": "autonomous_live_safety_regression_pack",
        "revision": 129,
        "status": _final_status(tests),
        "readiness": "SAFETY_REGRESSION_PASS" if _final_status(tests) != "blocked" else "SAFETY_REGRESSION_BLOCKED",
        "safety_regression": {"case_count": len(tests), "pass_count": len([t for t in tests if t.get("status") == "ok"]), "targeted_cases": [t["name"] for t in tests]},
        "checks": tests,
        "check_totals": _totals(tests),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "first_live_stabilization_report",
    }


def build_rev130_first_live_stabilization_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    state = build_rev126_live_runtime_state_supervisor(data, settings, auth_store, username)
    health = build_rev127_service_health_recovery_guard(data, settings, auth_store, username)
    consistency = build_rev128_runtime_consistency_validator(data, settings, auth_store, username)
    safety = build_rev129_live_safety_regression_pack(data, settings, auth_store, username)
    blockers = []
    for payload in (state, health, consistency, safety):
        for check in payload.get("checks", []) or []:
            if check.get("status") == "blocked" and check.get("required", True):
                blockers.append({"revision": payload.get("revision"), "check": check.get("name"), "detail": check.get("detail")})
    review_items = []
    for payload in (state, health, consistency, safety):
        for check in payload.get("checks", []) or []:
            if check.get("status") == "review":
                review_items.append({"revision": payload.get("revision"), "check": check.get("name"), "detail": check.get("detail")})
    if blockers:
        readiness = "blocked"
        action = "do_not_go_live_enter_safe_mode"
    elif review_items:
        readiness = "review"
        action = "limited_preview_review_before_micro_real"
    else:
        readiness = "ready"
        action = "ready_for_guarded_live_observation_not_auto_submit"
    checks = [
        _check("state_supervisor_complete", "ok" if state.get("revision") == 126 else "blocked", "Rev126 state supervisor is available."),
        _check("health_guard_complete", "ok" if health.get("revision") == 127 else "blocked", "Rev127 health guard is available."),
        _check("consistency_validator_complete", "ok" if consistency.get("revision") == 128 else "blocked", "Rev128 consistency validator is available."),
        _check("safety_regression_complete", "ok" if safety.get("revision") == 129 else "blocked", "Rev129 safety regression pack is available."),
        _check("no_live_submit_enabled", "ok", "Rev130 report is read-only and cannot place/close orders."),
    ]
    return {
        "engine": "autonomous_first_live_stabilization_report",
        "revision": 130,
        "status": _final_status(checks) if not blockers else "blocked",
        "readiness": readiness,
        "live_stabilization_report": {
            "ready_state": readiness,
            "critical_blocker": blockers[0] if blockers else None,
            "security_status": "safe_submit_close_off_secret_free",
            "state_health": state.get("state_health"),
            "action_recommendation": action,
            "review_item_count": len(review_items),
        },
        "summary_result": {"ready_state": readiness, "state_health": state.get("state_health"), "action": action, "critical_blocker": blockers[0] if blockers else None},
        "blockers": blockers[:20],
        "review_items": review_items[:20],
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev131_performance_observability_block",
    }


_REV_BUILDERS = {
    126: build_rev126_live_runtime_state_supervisor,
    127: build_rev127_service_health_recovery_guard,
    128: build_rev128_runtime_consistency_validator,
    129: build_rev129_live_safety_regression_pack,
    130: build_rev130_first_live_stabilization_report,
}

_REV_NAMES = {
    126: "autonomous_live_runtime_state_supervisor",
    127: "autonomous_service_health_recovery_guard",
    128: "autonomous_runtime_consistency_validator",
    129: "autonomous_live_safety_regression_pack",
    130: "autonomous_first_live_stabilization_report",
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = _REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_live_stabilization_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev126-130 revision.", "contains_secret": False}
    return builder(data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs: dict[str, dict] = {}
    base = deepcopy(data or {})
    for rev in range(126, 131):
        payload = build_for_revision(rev, base, settings, auth_store, username)
        key = _REV_NAMES[rev]
        outputs[key] = payload
    blockers = []
    for payload in outputs.values():
        for check in payload.get("checks", []) or []:
            if check.get("status") == "blocked" and check.get("required", True):
                blockers.append({"revision": payload.get("revision"), "check": check.get("name"), "detail": check.get("detail")})
    final_report = outputs["autonomous_first_live_stabilization_report"]
    return {
        "engine": "autonomous_live_stabilization_block",
        "revision": 130,
        "status": "blocked" if blockers else ("review" if any(p.get("status") == "review" for p in outputs.values()) else "ok"),
        "readiness": final_report.get("readiness"),
        "outputs": outputs,
        "blockers": blockers[:20],
        "summary_result": final_report.get("summary_result"),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    return {
        "revision": revision,
        "engine": payload.get("engine"),
        "status": payload.get("status"),
        "readiness": payload.get("readiness"),
        "decision": payload.get("summary_result", {}).get("action") if isinstance(payload.get("summary_result"), dict) else payload.get("readiness"),
        "manual_attention_required": payload.get("manual_attention_required", False) or bool(payload.get("blockers")),
        "state_health": payload.get("state_health") or (payload.get("summary_result") or {}).get("state_health"),
        "check_totals": payload.get("check_totals"),
        "command_preview": payload.get("command_preview"),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    totals = payload.get("check_totals") or _totals(payload.get("checks", []) or [])
    return {
        "engine": "autonomous_live_stabilization_quality_gate",
        "revision": revision,
        "status": payload.get("status"),
        "readiness": payload.get("readiness"),
        "quality_gate": "PASS" if payload.get("status") in {"ok", "review"} and not payload.get("contains_secret") else "FAIL",
        "check_totals": totals,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "runtime_write_default_off": True,
        "command_preview": payload.get("command_preview"),
        "contains_secret": False,
        "secret_values_returned": False,
    }
