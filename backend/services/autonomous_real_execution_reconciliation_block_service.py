from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "confirmed", "ok", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "emergency", "fail"}:
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


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    value = settings.get(key)
    return value if isinstance(value, dict) else {}


def _check(name: str, status: str, detail: str, required: bool = True, priority: int = 50, action: str = "review") -> dict:
    return {"name": name, "status": status, "required": required, "priority": priority, "detail": detail, "action": action}


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


def _command_preview() -> dict:
    return {
        "places_order": False,
        "submits_close_order": False,
        "sends_exchange_request": False,
        "writes_runtime_file": False,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "owner_approval_required": True,
        "approval_gated": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
    }


def _policy(settings: dict | None) -> dict:
    source = {
        **_settings(settings, "autonomous_limited_live_activation_rehearsal"),
        **_settings(settings, "autonomous_real_execution_reconciliation"),
    }
    return {
        "real_network_enable": _safe_bool(source.get("real_network_enable"), False),
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_repair_enable": _safe_bool(source.get("auto_repair_enable"), False),
        "auto_close_enable": _safe_bool(source.get("auto_close_enable"), False),
        "partial_fill_attention_threshold": max(0.0, min(1.0, _safe_float(source.get("partial_fill_attention_threshold"), 0.98))),
        "stale_order_minutes": max(1, _safe_int(source.get("stale_order_minutes"), 30)),
        "max_pending_orders": max(0, _safe_int(source.get("max_pending_orders"), 2)),
        "max_residual_notional_usdt": max(0.0, _safe_float(source.get("max_residual_notional_usdt"), 2.0)),
        "allowed_symbols": [str(x).upper().strip() for x in source.get("allowed_symbols", ["BTCUSDT", "ETHUSDT"]) if str(x).strip()],
    }


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def _first_dict(*values: Any) -> dict:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _orders(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    real_trade = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    candidates = []
    for source in (data, real_trade, data.get("exchange") if isinstance(data.get("exchange"), dict) else {}, data.get("order_state") if isinstance(data.get("order_state"), dict) else {}):
        candidates.extend(_as_list(source.get("orders")))
        candidates.extend(_as_list(source.get("exchange_orders")))
        candidates.extend(_as_list(source.get("order_statuses")))
    return candidates


def _positions(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    real_trade = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    candidates = []
    for source in (data, real_trade, data.get("position_state") if isinstance(data.get("position_state"), dict) else {}):
        candidates.extend(_as_list(source.get("positions")))
        candidates.extend(_as_list(source.get("open_positions")))
        candidates.extend(_as_list(source.get("real_positions")))
    return candidates


def _journal(data: dict | None) -> list[dict]:
    data = data if isinstance(data, dict) else {}
    real_trade = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    candidates = []
    for source in (data, real_trade, data.get("journal_state") if isinstance(data.get("journal_state"), dict) else {}):
        candidates.extend(_as_list(source.get("journal")))
        candidates.extend(_as_list(source.get("trade_journal")))
        candidates.extend(_as_list(source.get("executions")))
    return candidates


def _status_text(order: dict) -> str:
    for key in ("canonical_status", "status", "order_status", "state", "exchange_status", "fill_status"):
        value = order.get(key)
        if value is not None:
            return str(value).strip().upper()
    return "UNKNOWN"


def _canonical_status(raw_status: str) -> str:
    text = str(raw_status or "").strip().upper().replace(" ", "_").replace("-", "_")
    mapping = {
        "NEW": "open",
        "OPEN": "open",
        "PENDING": "open",
        "PARTIALLY_FILLED": "partial",
        "PARTIAL": "partial",
        "PARTIAL_FILL": "partial",
        "FILLED": "filled",
        "DONE": "filled",
        "CLOSED": "filled",
        "CANCELED": "canceled",
        "CANCELLED": "canceled",
        "EXPIRED": "expired",
        "REJECTED": "rejected",
        "FAILED": "rejected",
        "UNKNOWN": "unknown",
    }
    return mapping.get(text, "unknown")


def _order_id(item: dict) -> str:
    for key in ("client_order_id", "clientOrderId", "order_id", "orderId", "id", "intent_id"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "missing-order-id"


def _symbol(item: dict) -> str:
    return str(item.get("symbol") or item.get("pair") or "UNKNOWN").upper()


def _age_minutes(order: dict) -> int:
    for key in ("age_minutes", "preview_age_minutes", "elapsed_minutes", "minutes_open"):
        if key in order:
            return max(0, _safe_int(order.get(key), 0))
    return 0


def _quantity(item: dict) -> float:
    for key in ("qty", "quantity", "executed_qty", "executedQty", "position_qty", "size"):
        if key in item:
            return abs(_safe_float(item.get(key), 0.0))
    return 0.0


def _notional(item: dict) -> float:
    for key in ("notional_usdt", "notional", "quote_qty", "quoteQty", "position_notional_usdt", "reserved_usdt"):
        if key in item:
            return abs(_safe_float(item.get(key), 0.0))
    price = _safe_float(item.get("price") or item.get("avg_price") or item.get("avgPrice"), 0.0)
    qty = _quantity(item)
    return abs(price * qty)


def _fill_ratio(order: dict) -> float:
    if "fill_ratio" in order:
        return max(0.0, min(1.0, _safe_float(order.get("fill_ratio"), 0.0)))
    executed = _safe_float(order.get("executed_qty") or order.get("executedQty"), 0.0)
    original = _safe_float(order.get("orig_qty") or order.get("origQty") or order.get("quantity") or order.get("qty"), 0.0)
    if original > 0:
        return max(0.0, min(1.0, executed / original))
    return 1.0 if _canonical_status(_status_text(order)) == "filled" else 0.0


def _issue(code: str, severity: str, detail: str, action: str, priority: int = 50, order_id: str | None = None, symbol: str | None = None) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority, "order_id": order_id, "symbol": symbol}


def _critical_issue(issues: list[dict]) -> dict:
    if not issues:
        return {"code": "none", "severity": "ok", "detail": "Execution state is consistent.", "action": "continue_preview_or_manual_review"}
    return sorted(issues, key=lambda x: ({"critical": 0, "major": 1, "minor": 2, "ok": 3}.get(x.get("severity"), 2), int(x.get("priority", 50))))[0]


def build_rev186_exchange_order_state_canonicalizer(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    orders = _orders(data)
    canonical = []
    unknown_count = 0
    for order in orders:
        raw = _status_text(order)
        state = _canonical_status(raw)
        unknown_count += 1 if state == "unknown" else 0
        canonical.append({"order_id": _order_id(order), "symbol": _symbol(order), "raw_status": raw, "canonical_state": state, "fill_ratio": round(_fill_ratio(order), 6), "notional_usdt": round(_notional(order), 6), "age_minutes": _age_minutes(order)})
    checks = [
        _check("orders_readable", "ok" if isinstance(orders, list) else "blocked", "Order fixtures/mock state is readable."),
        _check("unknown_statuses", "review" if unknown_count else "ok", "Unknown exchange statuses require manual attention.", required=False, action="map_unknown_exchange_status"),
        _check("network_default_off", "ok" if not policy["real_network_enable"] else "blocked", "Canonicalizer must not call exchange network."),
        _check("real_submit_close_default_off", "ok" if not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "Canonicalizer cannot enable submit/close."),
    ]
    state = "attention" if unknown_count else "canonicalized"
    return {"engine": "autonomous_exchange_order_state_canonicalizer", "revision": 186, "status": _final_status(checks), "generated_at": now_iso(), "canonical_order_state": {"decision": state, "orders_seen": len(orders), "unknown_count": unknown_count, "states": canonical, "network": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev187_position_journal_order_reconciliation"}


def build_rev187_position_journal_order_reconciliation_v2(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    orders = build_rev186_exchange_order_state_canonicalizer(data, settings, auth_store, username)["canonical_order_state"]["states"]
    positions = _positions(data)
    journal = _journal(data)
    issues: list[dict] = []
    order_ids = {_order_id(o) for o in orders}
    journal_order_ids = {_order_id(j) for j in journal}
    pos_order_ids = {_order_id(p) for p in positions if _order_id(p) != "missing-order-id"}
    for pos in positions:
        oid = _order_id(pos)
        sym = _symbol(pos)
        if _notional(pos) > 0 and oid != "missing-order-id" and oid not in order_ids:
            issues.append(_issue("position_without_exchange_order", "major", "Position references no matching exchange order.", "manual_attention_safe_mode", 10, oid, sym))
        if _notional(pos) > 0 and oid != "missing-order-id" and oid not in journal_order_ids:
            issues.append(_issue("position_without_journal", "major", "Position is not represented in journal.", "manual_attention_reconcile_journal", 11, oid, sym))
    for order in orders:
        state = order.get("canonical_state")
        oid = _order_id(order)
        sym = _symbol(order)
        if state == "filled" and oid not in journal_order_ids:
            issues.append(_issue("filled_order_without_journal", "major", "Filled order lacks journal evidence.", "safe_mode_reconcile_journal", 12, oid, sym))
        if state == "filled" and oid not in pos_order_ids and order.get("notional_usdt", 0) > 0:
            issues.append(_issue("filled_order_without_position", "major", "Filled order has no matching position snapshot.", "manual_attention_reconcile_position", 13, oid, sym))
        if state in {"rejected", "expired", "canceled", "unknown"}:
            issues.append(_issue(f"order_{state}", "minor" if state in {"canceled", "expired"} else "major", f"Order state is {state}.", "review_order_lifecycle", 20, oid, sym))
    checks = [
        _check("reconciliation_inputs_available", "ok", "Order/position/journal fixtures were evaluated."),
        _check("consistency_issues", "blocked" if any(i["severity"] in {"critical", "major"} for i in issues) else ("review" if issues else "ok"), "Major reconciliation issues block live progression.", action="manual_attention_or_safe_mode"),
        _check("auto_repair_default_off", "ok" if not policy["auto_repair_enable"] else "blocked", "Auto repair remains OFF."),
        _check("network_submit_close_off", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "No real network/submit/close action."),
    ]
    action = "safe_mode" if any(i["severity"] in {"critical", "major"} for i in issues) else ("manual_attention" if issues else "continue_preview")
    return {"engine": "autonomous_position_journal_order_reconciliation_v2", "revision": 187, "status": _final_status(checks), "generated_at": now_iso(), "reconciliation": {"decision": "inconsistent" if issues else "consistent", "recommended_action": action, "orders": len(orders), "positions": len(positions), "journal_entries": len(journal), "issues": issues, "critical_issue": _critical_issue(issues), "network": "OFF", "auto_repair": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev188_partial_fill_residual_risk_handler"}


def build_rev188_partial_fill_residual_risk_handler(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    canonical = build_rev186_exchange_order_state_canonicalizer(data, settings, auth_store, username)["canonical_order_state"]["states"]
    issues: list[dict] = []
    residuals = []
    for order in canonical:
        fill_ratio = _safe_float(order.get("fill_ratio"), 0.0)
        if order.get("canonical_state") == "partial" or 0 < fill_ratio < 1:
            residual_notional = max(0.0, _safe_float(order.get("notional_usdt"), 0.0) * (1.0 - fill_ratio))
            residual = {"order_id": order.get("order_id"), "symbol": order.get("symbol"), "fill_ratio": round(fill_ratio, 6), "residual_notional_usdt": round(residual_notional, 6), "exit_plan_required": True, "auto_close": "OFF"}
            residuals.append(residual)
            severity = "major" if fill_ratio < policy["partial_fill_attention_threshold"] or residual_notional > policy["max_residual_notional_usdt"] else "minor"
            issues.append(_issue("partial_fill_residual_exposure", severity, "Partial fill leaves residual exposure/risk to manage.", "manual_attention_prepare_exit_plan", 10, str(order.get("order_id")), str(order.get("symbol"))))
    checks = [
        _check("partial_fill_scan", "ok", "Partial fill states scanned from canonical order fixture."),
        _check("residual_risk", "blocked" if any(i["severity"] == "major" for i in issues) else ("review" if issues else "ok"), "Residual exposure above threshold blocks progression.", action="manual_attention_exit_plan"),
        _check("auto_close_default_off", "ok" if not policy["auto_close_enable"] and not policy["real_close_enable"] else "blocked", "Auto close remains OFF/approval-gated."),
        _check("network_submit_default_off", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] else "blocked", "No real network/submit action."),
    ]
    return {"engine": "autonomous_partial_fill_residual_risk_handler", "revision": 188, "status": _final_status(checks), "generated_at": now_iso(), "partial_fill_residual_risk": {"decision": "attention" if issues else "clear", "residuals": residuals, "issues": issues, "critical_issue": _critical_issue(issues), "exit_plan_required": bool(residuals), "auto_close": "OFF", "real_close_submit": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev189_duplicate_stale_order_protection"}


def build_rev189_duplicate_stale_order_protection(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    policy = _policy(settings)
    canonical = build_rev186_exchange_order_state_canonicalizer(data, settings, auth_store, username)["canonical_order_state"]["states"]
    issues: list[dict] = []
    seen: dict[str, int] = {}
    open_pending = 0
    for order in canonical:
        oid = str(order.get("order_id") or "missing-order-id")
        seen[oid] = seen.get(oid, 0) + 1
        state = str(order.get("canonical_state"))
        if state in {"open", "partial"}:
            open_pending += 1
        if state in {"open", "partial"} and _safe_int(order.get("age_minutes"), 0) > policy["stale_order_minutes"]:
            issues.append(_issue("stale_order_preview", "major", "Open/partial order preview is older than stale-order threshold.", "block_submit_refresh_preview", 10, oid, str(order.get("symbol"))))
    for oid, count in seen.items():
        if oid != "missing-order-id" and count > 1:
            issues.append(_issue("duplicate_client_order_id", "critical", "Duplicate client/order ID detected.", "block_submit_regenerate_idempotency_key", 1, oid, None))
    if open_pending > policy["max_pending_orders"]:
        issues.append(_issue("too_many_pending_orders", "major", "Pending order count exceeds policy limit.", "cooldown_or_halt_new_submits", 5, None, None))
    checks = [
        _check("idempotency_scan", "ok", "Order IDs checked for duplicates."),
        _check("stale_order_scan", "blocked" if any(i["severity"] in {"critical", "major"} for i in issues) else "ok", "Duplicate/stale orders block new submit preview.", action="block_duplicate_or_stale_submit"),
        _check("network_submit_close_off", "ok" if not policy["real_network_enable"] and not policy["real_submit_enable"] and not policy["real_close_enable"] else "blocked", "Protection layer cannot place/close orders."),
    ]
    return {"engine": "autonomous_duplicate_stale_order_protection", "revision": 189, "status": _final_status(checks), "generated_at": now_iso(), "duplicate_stale_order_protection": {"decision": "block_new_submit" if issues else "clear", "open_pending_orders": open_pending, "issues": issues, "critical_issue": _critical_issue(issues), "idempotency_layer": "enforced_preview_only", "network": "OFF"}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev190_execution_reconciliation_report"}


def build_rev190_execution_reconciliation_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings = deepcopy(data or {}), deepcopy(settings or {})
    canonicalizer = build_rev186_exchange_order_state_canonicalizer(data, settings, auth_store, username)
    reconciliation = build_rev187_position_journal_order_reconciliation_v2(data, settings, auth_store, username)
    residual = build_rev188_partial_fill_residual_risk_handler(data, settings, auth_store, username)
    stale = build_rev189_duplicate_stale_order_protection(data, settings, auth_store, username)
    issue_pool = []
    for payload, key in ((reconciliation, "reconciliation"), (residual, "partial_fill_residual_risk"), (stale, "duplicate_stale_order_protection")):
        body = payload.get(key) if isinstance(payload.get(key), dict) else {}
        issue_pool.extend(body.get("issues") or [])
    critical = _critical_issue(issue_pool)
    major_count = len([i for i in issue_pool if i.get("severity") in {"critical", "major"}])
    minor_count = len([i for i in issue_pool if i.get("severity") == "minor"])
    score = max(0, 100 - major_count * 25 - minor_count * 10)
    if major_count:
        decision = "inconsistent"
        action = "manual_attention_safe_mode_or_halt"
    elif minor_count:
        decision = "attention"
        action = "review_before_next_submit"
    else:
        decision = "consistent"
        action = "continue_preview_or_approval_gated_review"
    checks = [
        _check("canonicalizer_available", canonicalizer.get("status", "blocked"), "Rev186 canonical state available."),
        _check("position_journal_order_reconciliation", reconciliation.get("status", "blocked"), "Rev187 reconciliation available."),
        _check("partial_fill_handler", residual.get("status", "blocked"), "Rev188 residual risk available."),
        _check("duplicate_stale_order_protection", stale.get("status", "blocked"), "Rev189 duplicate/stale protection available."),
        _check("real_submit_close_still_off", "ok", "Report cannot enable real submit/close."),
        _check("network_still_off", "ok", "Report cannot send exchange requests."),
    ]
    report = {"decision": decision, "execution_consistency": decision, "consistency_score": score, "critical_issue": critical, "recommended_action": action, "summary_visible": {"execution": decision, "issue": critical.get("code"), "action": action, "real_submit_close": "OFF", "network": "OFF"}, "orders_seen": canonicalizer.get("canonical_order_state", {}).get("orders_seen", 0), "issue_count": len(issue_pool), "major_issue_count": major_count, "minor_issue_count": minor_count, "real_submit_close": "OFF", "network": "OFF"}
    return {"engine": "autonomous_execution_reconciliation_report", "revision": 190, "status": _final_status(checks), "generated_at": now_iso(), "execution_reconciliation_report": report, "summary_result": report["summary_visible"], "outputs": {"canonicalizer": canonicalizer, "reconciliation": reconciliation, "partial_fill_residual_risk": residual, "duplicate_stale_order_protection": stale}, "checks": checks, "check_totals": _totals(checks), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev191_live_risk_firewall_block"}


REV_BUILDERS = {186: build_rev186_exchange_order_state_canonicalizer, 187: build_rev187_position_journal_order_reconciliation_v2, 188: build_rev188_partial_fill_residual_risk_handler, 189: build_rev189_duplicate_stale_order_protection, 190: build_rev190_execution_reconciliation_report}
REV_KEYS = {186: "autonomous_exchange_order_state_canonicalizer", 187: "autonomous_position_journal_order_reconciliation_v2", 188: "autonomous_partial_fill_residual_risk_handler", 189: "autonomous_duplicate_stale_order_protection", 190: "autonomous_execution_reconciliation_report"}


def build_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builder = REV_BUILDERS.get(int(revision))
    if not builder:
        return {"engine": "autonomous_real_execution_reconciliation_block", "revision": revision, "status": "blocked", "message": "Unsupported Rev186-190 revision.", "contains_secret": False}
    return builder(data or {}, settings or {}, auth_store or {}, username)


def build_summary_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    if int(revision) == 190:
        return {"revision": 190, **payload.get("summary_result", {}), "status": payload.get("status", "review"), "check_totals": payload.get("check_totals", {})}
    for key in ("canonical_order_state", "reconciliation", "partial_fill_residual_risk", "duplicate_stale_order_protection"):
        if isinstance(payload.get(key), dict):
            return {"revision": int(revision), "status": payload.get("status", "review"), "summary": payload.get(key), "check_totals": payload.get("check_totals", {})}
    return {"revision": int(revision), "status": payload.get("status", "review"), "summary": {}, "check_totals": payload.get("check_totals", {})}


def build_block_payload(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    data, settings, auth_store = deepcopy(data or {}), deepcopy(settings or {}), deepcopy(auth_store or {})
    outputs = {REV_KEYS[rev]: build_for_revision(rev, data, settings, auth_store, username) for rev in range(186, 191)}
    statuses = [payload.get("status") for payload in outputs.values()]
    block_status = "blocked" if "blocked" in statuses else ("review" if "review" in statuses else "ok")
    final = outputs["autonomous_execution_reconciliation_report"]
    return {"engine": "autonomous_real_execution_reconciliation_block", "revision": 190, "status": block_status, "generated_at": now_iso(), "username": username, "outputs": outputs, "summary_result": final.get("summary_result", {}), "execution_reconciliation_report": final.get("execution_reconciliation_report", {}), "auto_apply_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev191_live_risk_firewall_block"}


def build_quality_for_revision(revision: int, data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    preview = payload.get("command_preview", {})
    checks = [
        _check("route_payload_available", "ok" if payload.get("revision") == int(revision) else "blocked", "Revision payload is available."),
        _check("no_secret_exposure", "ok" if payload.get("contains_secret") is False and payload.get("secret_values_returned") is False else "blocked", "Payload does not expose secrets."),
        _check("network_default_off", "ok" if preview.get("network_default_off") is True and preview.get("sends_exchange_request") is False else "blocked", "No exchange network request."),
        _check("real_submit_default_off", "ok" if preview.get("real_submit_default_off") is True and preview.get("places_order") is False else "blocked", "Real submit is disabled."),
        _check("real_close_default_off", "ok" if preview.get("real_close_default_off") is True and preview.get("submits_close_order") is False else "blocked", "Real close is disabled."),
        _check("auto_apply_default_off", "ok" if payload.get("auto_apply_default_off") is True else "blocked", "All decisions remain advisory/approval-gated."),
    ]
    return {"engine": "autonomous_real_execution_reconciliation_quality_gate", "revision": int(revision), "quality_gate": "PASS" if _final_status(checks) == "ok" else "FAIL", "status": _final_status(checks), "checks": checks, "check_totals": _totals(checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "contains_secret": False, "secret_values_returned": False}
