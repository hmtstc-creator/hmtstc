from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "approved"}


def _reason(code: str, message: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "message": message, "action": action, "severity": severity, "priority": int(priority)}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return _reason("none", "No dry-proof blocker.", "no_action", "ok", 999)
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda r: (weight.get(str(r.get("severity")), 2), int(r.get("priority", 50))))[0]


def _check(name: str, status: str, message: str, detail: dict | None = None) -> dict:
    return {"name": name, "status": status, "message": message, "detail": detail or {}}


def _totals(checks: list[dict]) -> dict:
    return {
        "total": len(checks),
        "ok": sum(1 for c in checks if c.get("status") == "ok"),
        "review": sum(1 for c in checks if c.get("status") == "review"),
        "blocked": sum(1 for c in checks if c.get("status") == "blocked"),
    }


def _final_status(checks: list[dict]) -> str:
    if any(c.get("status") == "blocked" for c in checks):
        return "blocked"
    if any(c.get("status") == "review" for c in checks):
        return "review"
    return "ok"


def _command_preview() -> dict:
    return {
        "places_order": False,
        "sends_exchange_request": False,
        "submits_close_order": False,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_scale": False,
        "auto_apply": False,
        "read_only": True,
        "fixture_only": True,
        "approval_gated": True,
    }


def _policy(settings: dict | None) -> dict:
    settings = _as_dict(settings)
    live = _as_dict(settings.get("limited_live") or settings.get("live") or {})
    risk = _as_dict(settings.get("risk") or settings.get("risk_profile") or {})
    return {
        "real_submit_enable": _truthy(settings.get("real_submit_enable") or live.get("real_submit_enable")),
        "real_close_enable": _truthy(settings.get("real_close_enable") or live.get("real_close_enable")),
        "auto_scale": _truthy(settings.get("auto_scale") or live.get("auto_scale")),
        "auto_apply": _truthy(settings.get("auto_apply") or live.get("auto_apply")),
        "owner_approval": _truthy(live.get("owner_approval") or live.get("owner_approved") or settings.get("owner_approval")),
        "activation_token_preview": bool(str(live.get("activation_token_preview") or settings.get("activation_token_preview") or "").strip()),
        "max_notional": _safe_float(live.get("max_notional") or risk.get("max_notional") or settings.get("max_notional_usdt"), 25.0),
        "max_daily_loss": _safe_float(live.get("max_daily_loss") or risk.get("max_daily_loss") or settings.get("max_daily_loss_usdt"), 5.0),
        "allowed_symbols": _as_list(live.get("allowed_symbols")) or _as_list(settings.get("allowed_symbols")) or ["BTCUSDT", "ETHUSDT"],
        "session_id": str(live.get("session_id") or settings.get("session_id") or "dry-proof-session").strip(),
    }


def _fixtures(data: dict | None) -> dict:
    data = _as_dict(data)
    fixtures = _as_dict(data.get("exchange_fixtures") or data.get("micro_live_exchange_fixtures") or {})
    orders = _as_list(fixtures.get("orders")) or [
        {"order_id": "fixture-order-1", "client_order_id": "dry-proof-001", "status": "NEW", "symbol": "BTCUSDT", "executed_qty": 0, "orig_qty": 0.001},
        {"order_id": "fixture-order-2", "client_order_id": "dry-proof-002", "status": "FILLED", "symbol": "ETHUSDT", "executed_qty": 0.01, "orig_qty": 0.01},
        {"order_id": "fixture-order-3", "client_order_id": "dry-proof-003", "status": "PARTIALLY_FILLED", "symbol": "BTCUSDT", "executed_qty": 0.0004, "orig_qty": 0.001},
    ]
    positions = _as_list(fixtures.get("positions")) or [{"symbol": "ETHUSDT", "qty": 0.01, "entry_price": 3000, "source": "fixture"}]
    journal = _as_list(fixtures.get("journal")) or [{"client_order_id": "dry-proof-002", "symbol": "ETHUSDT", "status": "filled", "source": "fixture"}]
    return {"orders": orders, "positions": positions, "journal": journal, "fixture_source": "runtime_fixture_or_default"}


def _upstream(data: dict | None) -> dict:
    data = _as_dict(data)
    return {
        "operator_ux": _as_dict(data.get("autonomous_limited_live_operator_approval_ux_block") or data.get("limited_live_operator_ux_packet")),
        "risk_firewall": _as_dict(data.get("autonomous_live_risk_firewall_block") or data.get("live_risk_firewall_decision_packet")),
        "execution_reconciliation": _as_dict(data.get("autonomous_real_execution_reconciliation_block") or data.get("execution_reconciliation_report")),
        "data_integrity": _as_dict(data.get("autonomous_production_data_integrity_block") or data.get("production_data_integrity_report")),
    }


def _common_blockers(data: dict | None, settings: dict | None) -> list[dict]:
    p = _policy(settings)
    upstream = _upstream(data)
    reasons: list[dict] = []
    if p["real_submit_enable"] or p["real_close_enable"]:
        reasons.append(_reason("real_execution_flag_enabled", "Real submit/close flags must stay OFF during dry proof.", "turn_real_execution_flags_off", "critical", 0))
    if p["auto_scale"] or p["auto_apply"]:
        reasons.append(_reason("auto_scale_or_apply_enabled", "Auto-scale/auto-apply must stay OFF during dry proof.", "turn_auto_scale_apply_off", "critical", 1))
    if p["max_notional"] <= 0 or p["max_daily_loss"] <= 0:
        reasons.append(_reason("micro_limits_invalid", "Micro notional and daily loss limits must be explicit.", "set_micro_limits", "major", 10))
    if not p["session_id"]:
        reasons.append(_reason("session_boundary_missing", "Session boundary is required for dry proof.", "set_session_boundary", "major", 11))
    for key, payload in upstream.items():
        status = str(payload.get("status") or _as_dict(payload.get(key)).get("status") or payload.get("decision") or "review").lower()
        if status in {"blocked", "inconsistent", "emergency", "halt"}:
            reasons.append(_reason(f"{key}_blocked", f"{key} upstream status blocks execution dry proof.", "hold_until_upstream_ok", "major", 20))
    return reasons


def build_rev251_submit_path_dry_proof(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    p = _policy(settings)
    reasons = _common_blockers(data, settings)
    critical = _critical(reasons)
    proof = {
        "path": "submit",
        "dry_run_only": True,
        "would_submit_if_enabled": critical.get("severity") == "ok" and p["owner_approval"] and p["activation_token_preview"],
        "blocked_by_default": True,
        "required_gates": ["explicit_enable", "owner_approval", "activation_token_preview", "risk_firewall", "whitelist", "session_boundary", "idempotency"],
        "passed_gates_preview": {
            "owner_approval": p["owner_approval"],
            "activation_token_preview": p["activation_token_preview"],
            "session_boundary": bool(p["session_id"]),
            "micro_limits": p["max_notional"] > 0 and p["max_daily_loss"] > 0,
        },
        "critical_blocker": critical,
        "real_submit": "OFF",
    }
    checks = [
        _check("submit_real_network_off", "ok" if not p["real_submit_enable"] else "blocked", "Submit path never sends real network in dry proof."),
        _check("owner_approval_preview_checked", "ok" if p["owner_approval"] else "review", "Owner approval is evaluated but does not trigger submit."),
        _check("token_value_not_returned", "ok", "Activation token value is never returned."),
    ]
    return {"engine": "submit_path_dry_proof", "revision": 251, "status": _final_status(checks), "generated_at": now_iso(), "submit_path_dry_proof": proof, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev252_exit_path_dry_proof"}


def build_rev252_exit_path_dry_proof(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    p = _policy(settings)
    fixtures = _fixtures(data)
    open_positions = [x for x in fixtures["positions"] if _safe_float(x.get("qty"), 0) != 0]
    reasons = _common_blockers(data, settings)
    if open_positions and not p["owner_approval"]:
        reasons.append(_reason("exit_owner_approval_missing", "Exit/close dry path requires owner approval preview for controlled live scope.", "review_exit_scope", "major", 12))
    critical = _critical(reasons)
    proof = {
        "path": "exit",
        "dry_run_only": True,
        "open_position_fixture_count": len(open_positions),
        "exit_plan_required": bool(open_positions),
        "close_would_be_blocked": True,
        "exit_conditions_checked": ["sl", "tp", "trailing", "time_stop", "manual_attention", "emergency"],
        "critical_blocker": critical,
        "real_close": "OFF",
        "auto_close": "OFF",
    }
    checks = [
        _check("close_real_network_off", "ok" if not p["real_close_enable"] else "blocked", "Close path never sends real network in dry proof."),
        _check("exit_conditions_present", "ok", "Exit condition list is available before live scope."),
        _check("auto_close_default_off", "ok", "Auto-close remains OFF unless explicit approval path is active."),
    ]
    return {"engine": "exit_path_dry_proof", "revision": 252, "status": _final_status(checks), "generated_at": now_iso(), "exit_path_dry_proof": proof, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev253_exchange_response_fixture_validator"}


def build_rev253_exchange_response_fixture_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    fixtures = _fixtures(data)
    valid_status = {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"}
    invalid = [o for o in fixtures["orders"] if str(o.get("status") or "").upper() not in valid_status]
    partial = [o for o in fixtures["orders"] if str(o.get("status") or "").upper() == "PARTIALLY_FILLED"]
    validator = {
        "fixture_source": fixtures["fixture_source"],
        "order_fixture_count": len(fixtures["orders"]),
        "position_fixture_count": len(fixtures["positions"]),
        "journal_fixture_count": len(fixtures["journal"]),
        "invalid_status_count": len(invalid),
        "partial_fill_fixture_count": len(partial),
        "supported_statuses": sorted(valid_status),
        "fixture_valid": not invalid,
    }
    checks = [
        _check("fixtures_present", "ok" if fixtures["orders"] else "review", "Exchange response fixtures are available."),
        _check("statuses_canonical", "ok" if not invalid else "blocked", "Fixture statuses map to canonical states."),
        _check("partial_fill_covered", "ok" if partial else "review", "Partial fill fixture coverage is expected."),
    ]
    return {"engine": "exchange_response_fixture_validator", "revision": 253, "status": _final_status(checks), "generated_at": now_iso(), "exchange_response_fixture_validator": validator, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev254_reconciliation_dry_proof_runner"}


def build_rev254_reconciliation_dry_proof_runner(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    fixtures = _fixtures(data)
    order_ids = {str(o.get("client_order_id") or o.get("order_id")) for o in fixtures["orders"]}
    journal_ids = {str(j.get("client_order_id") or j.get("order_id")) for j in fixtures["journal"]}
    order_symbols = {str(o.get("symbol") or "").upper() for o in fixtures["orders"]}
    position_symbols = {str(p.get("symbol") or "").upper() for p in fixtures["positions"]}
    missing_journal = sorted(x for x in order_ids - journal_ids if x)
    position_without_order = sorted(x for x in position_symbols - order_symbols if x)
    partial_orders = [o for o in fixtures["orders"] if str(o.get("status") or "").upper() == "PARTIALLY_FILLED"]
    issues = []
    if missing_journal:
        issues.append(_reason("order_without_journal", "Order fixture exists without matching journal fixture.", "manual_attention_reconcile", "major", 20))
    if position_without_order:
        issues.append(_reason("position_without_order", "Position fixture exists without matching exchange order fixture.", "manual_attention_reconcile", "major", 21))
    if partial_orders:
        issues.append(_reason("partial_fill_residual_risk", "Partial fill fixture requires residual exposure plan.", "review_residual_exit_plan", "minor", 30))
    critical = _critical(issues)
    runner = {
        "dry_run_only": True,
        "consistent": not any(i.get("severity") in {"critical", "major"} for i in issues),
        "issue_count": len(issues),
        "critical_issue": critical,
        "missing_journal_count": len(missing_journal),
        "position_without_order_count": len(position_without_order),
        "partial_fill_count": len(partial_orders),
        "recommended_action": critical.get("action"),
    }
    checks = [
        _check("order_journal_link", "ok" if not missing_journal else "review", "Order and journal fixtures are linkable."),
        _check("position_order_link", "ok" if not position_without_order else "review", "Position and order fixtures are linkable."),
        _check("residual_risk_detected", "review" if partial_orders else "ok", "Partial fills are detected and surfaced."),
    ]
    return {"engine": "reconciliation_dry_proof_runner", "revision": 254, "status": _final_status(checks), "generated_at": now_iso(), "reconciliation_dry_proof_runner": runner, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev255_micro_live_execution_dry_proof_report"}


def build_rev255_micro_live_execution_dry_proof_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    submit = build_rev251_submit_path_dry_proof(data, settings, auth_store, username)
    exit_ = build_rev252_exit_path_dry_proof(data, settings, auth_store, username)
    fixtures = build_rev253_exchange_response_fixture_validator(data, settings, auth_store, username)
    reconciliation = build_rev254_reconciliation_dry_proof_runner(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (submit, exit_, fixtures, reconciliation):
        checks.extend(_as_list(payload.get("checks")))
    critical = _critical(_common_blockers(data, settings) + [_as_dict(reconciliation.get("reconciliation_dry_proof_runner", {}).get("critical_issue"))])
    status = _final_status(checks)
    if critical.get("severity") in {"critical", "major"}:
        decision = "HOLD"
    elif status == "review":
        decision = "DRY_PROOF_REVIEW"
    else:
        decision = "DRY_PROOF_READY"
    report = {
        "decision": decision,
        "execution_dry_proof": "ready" if decision == "DRY_PROOF_READY" else "attention",
        "critical_issue": critical,
        "submit_path": "dry_proof_only",
        "exit_path": "dry_proof_only",
        "fixture_validation": fixtures.get("status"),
        "reconciliation_status": reconciliation.get("status"),
        "recommended_action": critical.get("action") if critical.get("severity") != "ok" else "keep_real_submit_off_until_owner_go",
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    summary_result = {
        "revision": 255,
        "decision": report.get("decision", "HOLD"),
        "execution_dry_proof": report.get("execution_dry_proof", "attention"),
        "critical_issue": _as_dict(report.get("critical_issue")).get("code", "review"),
        "operator_action": report.get("recommended_action", "review"),
        "submit_path": report.get("submit_path", "dry_proof_only"),
        "exit_path": report.get("exit_path", "dry_proof_only"),
        "reconciliation_status": report.get("reconciliation_status", "review"),
        "trade_allowed": False,
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    return {"engine": "micro_live_execution_dry_proof_report", "revision": 255, "status": status, "generated_at": now_iso(), "micro_live_execution_dry_proof_report": report, "submit_path_dry_proof": submit.get("submit_path_dry_proof"), "exit_path_dry_proof": exit_.get("exit_path_dry_proof"), "exchange_response_fixture_validator": fixtures.get("exchange_response_fixture_validator"), "reconciliation_dry_proof_runner": reconciliation.get("reconciliation_dry_proof_runner"), "checks": checks, "check_totals": _totals(checks), "summary_result": summary_result, "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev256_small_capital_readiness_recheck"}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    builders = {
        251: build_rev251_submit_path_dry_proof,
        252: build_rev252_exit_path_dry_proof,
        253: build_rev253_exchange_response_fixture_validator,
        254: build_rev254_reconciliation_dry_proof_runner,
        255: build_rev255_micro_live_execution_dry_proof_report,
    }
    if int(revision) not in builders:
        raise ValueError(f"Unsupported Rev251-255 micro-live execution dry proof revision: {revision}")
    return builders[int(revision)](data, settings, auth_store, username)


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    rev251 = build_rev251_submit_path_dry_proof(data, settings, auth_store, username)
    rev252 = build_rev252_exit_path_dry_proof(data, settings, auth_store, username)
    rev253 = build_rev253_exchange_response_fixture_validator(data, settings, auth_store, username)
    rev254 = build_rev254_reconciliation_dry_proof_runner(data, settings, auth_store, username)
    rev255 = build_rev255_micro_live_execution_dry_proof_report(data, settings, auth_store, username)
    checks: list[dict] = []
    for payload in (rev251, rev252, rev253, rev254, rev255):
        checks.extend(_as_list(payload.get("checks")))
    return {
        "engine": "micro_live_execution_dry_proof_block",
        "revision": 255,
        "status": rev255.get("status", "review"),
        "generated_at": now_iso(),
        "rev251_submit_path_dry_proof": rev251,
        "rev252_exit_path_dry_proof": rev252,
        "rev253_exchange_response_fixture_validator": rev253,
        "rev254_reconciliation_dry_proof_runner": rev254,
        "rev255_micro_live_execution_dry_proof_report": rev255,
        "micro_live_execution_dry_proof_report": rev255.get("micro_live_execution_dry_proof_report", {}),
        "summary_result": build_summary_for_revision(255, data, settings, auth_store, username),
        "checks": checks,
        "check_totals": _totals(checks),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
        "next_allowed_step": "rev256_small_capital_readiness_recheck",
    }


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    if int(revision) == 255:
        p = build_rev255_micro_live_execution_dry_proof_report(data, settings, auth_store, username)
        report = _as_dict(p.get("micro_live_execution_dry_proof_report"))
        issue = _as_dict(report.get("critical_issue"))
        return {
            "revision": 255,
            "decision": report.get("decision", "HOLD"),
            "execution_dry_proof": report.get("execution_dry_proof", "attention"),
            "critical_issue": issue.get("code", "review"),
            "operator_action": report.get("recommended_action", "review"),
            "submit_path": report.get("submit_path", "dry_proof_only"),
            "exit_path": report.get("exit_path", "dry_proof_only"),
            "reconciliation_status": report.get("reconciliation_status", "review"),
            "trade_allowed": False,
            "real_submit_close": "OFF",
            "auto_scale": "OFF",
            "auto_apply": "OFF",
        }
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body_key = {
        251: "submit_path_dry_proof",
        252: "exit_path_dry_proof",
        253: "exchange_response_fixture_validator",
        254: "reconciliation_dry_proof_runner",
    }.get(int(revision), "summary")
    body = _as_dict(payload.get(body_key))
    issue = _as_dict(body.get("critical_blocker") or body.get("critical_issue"))
    return {
        "revision": int(revision),
        "decision": body.get("decision") or payload.get("status", "review"),
        "critical_issue": issue.get("code", "none"),
        "operator_action": body.get("recommended_action") or issue.get("action") or "review",
        "trade_allowed": False,
        "real_submit_close": "OFF",
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    command = payload.get("command_preview", {})
    failures = []
    if command.get("places_order") or command.get("sends_exchange_request") or command.get("submits_close_order"):
        failures.append("unexpected_execution_side_effect")
    if command.get("real_submit_default_off") is not True or command.get("real_close_default_off") is not True:
        failures.append("real_execution_not_default_off")
    if payload.get("contains_secret") or payload.get("secret_values_returned"):
        failures.append("secret_leak")
    if command.get("auto_scale") or command.get("auto_apply"):
        failures.append("auto_scale_or_apply_enabled")
    return {"quality_gate": "FAIL" if failures else "PASS", "revision": int(revision), "engine": payload.get("engine"), "status": payload.get("status"), "failures": failures, "command_preview": command, "checked_at": now_iso()}
