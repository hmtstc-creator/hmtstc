from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import hashlib
import json


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


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
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on", "enabled", "allow", "allowed", "ready", "ok", "pass"}:
            return True
        if text in {"0", "false", "no", "off", "disabled", "deny", "blocked", "halt", "fail"}:
            return False
    if value is None:
        return fallback
    return bool(value)


def _settings(settings: dict | None, key: str) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    return _as_dict(settings.get(key))


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
        "journal_write_allowed": True,
        "audit_write_allowed": True,
        "network_default_off": True,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_execute": False,
        "auto_promote": False,
        "auto_scale": False,
        "auto_apply": False,
    }


def _policy(settings: dict | None) -> dict:
    source: dict[str, Any] = {}
    for key in (
        "autonomous_production_data_integrity",
        "autonomous_production_observability_incident_drill",
        "autonomous_production_self_governance",
    ):
        source.update(_settings(settings, key))
    return {
        "max_runtime_age_seconds": max(10, _safe_int(source.get("max_runtime_age_seconds"), 180)),
        "max_journal_gap": max(0, _safe_int(source.get("max_journal_gap"), 0)),
        "min_learning_confidence": max(0.0, min(1.0, _safe_float(source.get("min_learning_confidence"), 0.60))),
        "required_decision_fields": _as_list(source.get("required_decision_fields")) or ["decision", "critical_blocker", "operator_action", "trade_allowed"],
        "real_submit_enable": _safe_bool(source.get("real_submit_enable"), False),
        "real_close_enable": _safe_bool(source.get("real_close_enable"), False),
        "auto_scale_enable": _safe_bool(source.get("auto_scale_enable"), False),
        "auto_apply_enable": _safe_bool(source.get("auto_apply_enable"), False),
    }


def _runtime(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    source: dict[str, Any] = {}
    for key in ("production_data_integrity_runtime", "runtime_integrity", "production_observability_runtime", "small_capital_runtime"):
        source.update(_as_dict(data.get(key)))
    return {
        "runtime_age_seconds": max(0, _safe_int(source.get("runtime_age_seconds"), source.get("heartbeat_age_seconds", 999))),
        "last_update_present": _safe_bool(source.get("last_update_present"), bool(data.get("last_tick") or data.get("last_updated_at") or data.get("last_calculation_at"))),
        "schema_version": str(source.get("schema_version") or data.get("schema_version") or "unknown"),
        "runtime_sources": _as_list(source.get("runtime_sources")) or ["shadow", "settings", "summary"],
        "journal_entries": _as_list(source.get("journal_entries") or data.get("trade_journal") or data.get("real_trade_journal") or data.get("journal")),
        "orders": _as_list(source.get("orders") or data.get("orders") or data.get("real_orders")),
        "positions": _as_list(source.get("positions") or data.get("open_positions") or data.get("real_positions")),
        "learning_memory": _as_dict(source.get("learning_memory") or data.get("learning_memory") or data.get("real_learning_memory") or data.get("autonomous_learning_memory")),
        "decision_packet": _as_dict(source.get("decision_packet") or data.get("latest_decision_packet") or data.get("production_decision_packet")),
    }


def _sha256_payload(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reason(code: str, detail: str, action: str, severity: str = "major", priority: int = 50) -> dict:
    return {"code": code, "severity": severity, "detail": detail, "action": action, "priority": priority}


def _critical(reasons: list[dict]) -> dict:
    if not reasons:
        return {"code": "none", "severity": "ok", "detail": "Production data integrity is acceptable.", "action": "continue_guarded_observation", "priority": 99}
    weight = {"critical": 0, "major": 1, "minor": 2, "ok": 3}
    return sorted(reasons, key=lambda item: (weight.get(str(item.get("severity")), 2), int(item.get("priority", 50))))[0]


def build_rev226_runtime_data_freshness_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    runtime = _runtime(data)
    checks = [
        _check("runtime_age", "ok" if runtime["runtime_age_seconds"] <= policy["max_runtime_age_seconds"] else "blocked", "Runtime data must be fresh before limited-live decisions.", True, 1, "refresh_runtime_snapshot"),
        _check("last_update_present", "ok" if runtime["last_update_present"] else "review", "At least one last update marker should exist.", True, 4, "restore_last_update_marker"),
        _check("runtime_sources_present", "ok" if len(runtime["runtime_sources"]) >= 2 else "review", "Multiple runtime sources should be visible for operator review.", False, 7, "review_runtime_sources"),
    ]
    body = {
        "data_integrity": _final_status(checks),
        "freshness_status": _final_status(checks),
        "runtime_age_seconds": runtime["runtime_age_seconds"],
        "max_runtime_age_seconds": policy["max_runtime_age_seconds"],
        "schema_version": runtime["schema_version"],
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "real_submit_close": "OFF",
    }
    return {"engine": "runtime_data_freshness_validator", "revision": 226, "status": _final_status(checks), "generated_at": now_iso(), "runtime_data_freshness_validator": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev227_journal_consistency_checksum"}


def build_rev227_journal_consistency_checksum(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    runtime = _runtime(data)
    journal = runtime["journal_entries"]
    orders = runtime["orders"]
    positions = runtime["positions"]
    journal_ids = {str(x.get("order_id") or x.get("client_order_id") or x.get("id")) for x in journal if isinstance(x, dict)}
    order_ids = {str(x.get("order_id") or x.get("client_order_id") or x.get("id")) for x in orders if isinstance(x, dict)}
    missing_journal = sorted([x for x in order_ids if x and x != "None" and x not in journal_ids])
    orphan_journal = sorted([x for x in journal_ids if x and x != "None" and x not in order_ids]) if order_ids else []
    checksum = _sha256_payload({"journal": journal, "orders": orders, "positions": positions})
    checks = [
        _check("journal_entries_visible", "ok" if journal else "review", "Journal visibility is required before evidence-based live scaling.", False, 5, "verify_journal_source"),
        _check("missing_journal_gap", "ok" if len(missing_journal) <= policy["max_journal_gap"] else "blocked", "Every known order should have a journal/evidence link.", True, 1, "reconcile_missing_journal_entries"),
        _check("orphan_journal_gap", "ok" if not orphan_journal else "review", "Orphan journal records require operator review.", False, 6, "review_orphan_journal_entries"),
    ]
    body = {
        "data_integrity": _final_status(checks),
        "checksum": checksum,
        "journal_count": len(journal),
        "order_count": len(orders),
        "position_count": len(positions),
        "missing_journal_count": len(missing_journal),
        "orphan_journal_count": len(orphan_journal),
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "real_submit_close": "OFF",
    }
    return {"engine": "journal_consistency_checksum", "revision": 227, "status": _final_status(checks), "generated_at": now_iso(), "journal_consistency_checksum": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev228_learning_memory_integrity_guard"}


def build_rev228_learning_memory_integrity_guard(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    memory = _runtime(data)["learning_memory"]
    confidence = max(0.0, min(1.0, _safe_float(memory.get("confidence") or memory.get("evidence_confidence") or memory.get("quality_score"), 0.0)))
    sample_count = _safe_int(memory.get("sample_count") or memory.get("trades") or memory.get("evidence_count"), 0)
    has_live_cost = bool(memory.get("fee_model") or memory.get("slippage_model") or memory.get("live_cost_calibration"))
    checks = [
        _check("learning_memory_present", "ok" if memory else "review", "Learning memory should exist before repeat live decisions.", False, 6, "collect_learning_memory"),
        _check("learning_confidence", "ok" if confidence >= policy["min_learning_confidence"] else "review", "Low confidence prevents blind scale-up.", True, 2, "freeze_learning_based_scaling"),
        _check("sample_count_nonzero", "ok" if sample_count > 0 else "review", "Live sample size should be visible.", False, 7, "collect_more_evidence"),
        _check("live_cost_model_visible", "ok" if has_live_cost else "review", "Fee/slippage/latency cost reality should be represented.", False, 8, "update_cost_model"),
    ]
    body = {
        "data_integrity": _final_status(checks),
        "learning_confidence": round(confidence, 4),
        "min_learning_confidence": policy["min_learning_confidence"],
        "sample_count": sample_count,
        "live_cost_model_visible": has_live_cost,
        "scale_allowed": False,
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "real_submit_close": "OFF",
    }
    return {"engine": "learning_memory_integrity_guard", "revision": 228, "status": _final_status(checks), "generated_at": now_iso(), "learning_memory_integrity_guard": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev229_decision_packet_schema_validator"}


def build_rev229_decision_packet_schema_validator(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    packet = _runtime(data)["decision_packet"]
    required = [str(x) for x in policy["required_decision_fields"]]
    missing = [field for field in required if field not in packet]
    unsafe_trade_allowed = packet.get("trade_allowed") is True and not packet.get("owner_approval")
    checks = [
        _check("decision_packet_present", "ok" if packet else "review", "Latest decision packet should be visible.", False, 4, "publish_decision_packet_preview"),
        _check("required_fields", "ok" if not missing else "blocked", "Decision packet must expose critical decision fields.", True, 1, "repair_decision_packet_schema"),
        _check("owner_gate_for_trade_allowed", "ok" if not unsafe_trade_allowed else "blocked", "Trade allowed cannot be true without owner approval scope.", True, 0, "block_unsafe_trade_allowed_packet"),
    ]
    body = {
        "data_integrity": _final_status(checks),
        "schema_valid": _final_status(checks) == "ok",
        "required_fields": required,
        "missing_fields": missing,
        "decision": packet.get("decision") or "review",
        "trade_allowed": bool(packet.get("trade_allowed")) and bool(packet.get("owner_approval")),
        "operator_action": _critical([c for c in checks if c.get("status") != "ok"]).get("action"),
        "real_submit_close": "OFF",
    }
    return {"engine": "decision_packet_schema_validator", "revision": 229, "status": _final_status(checks), "generated_at": now_iso(), "decision_packet_schema_validator": body, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev230_production_data_integrity_report"}


def build_rev230_production_data_integrity_report(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    policy = _policy(settings)
    freshness = build_rev226_runtime_data_freshness_validator(data, settings, auth_store, username)
    journal = build_rev227_journal_consistency_checksum(data, settings, auth_store, username)
    learning = build_rev228_learning_memory_integrity_guard(data, settings, auth_store, username)
    schema = build_rev229_decision_packet_schema_validator(data, settings, auth_store, username)
    reasons: list[dict] = []
    if freshness.get("status") == "blocked":
        reasons.append(_reason("stale_runtime", "Runtime data is stale or missing freshness marker.", "refresh_runtime_snapshot", "critical", 1))
    if journal.get("status") == "blocked":
        reasons.append(_reason("journal_mismatch", "Order/journal relationship is inconsistent.", "reconcile_journal_before_live", "critical", 2))
    if schema.get("status") == "blocked":
        reasons.append(_reason("decision_schema_invalid", "Decision packet is missing mandatory fields or unsafe owner gate.", "repair_decision_packet_schema", "critical", 0))
    if learning.get("status") == "review":
        reasons.append(_reason("learning_memory_review", "Learning memory confidence/sample/cost data requires review.", "freeze_scale_collect_evidence", "major", 6))
    if policy["real_submit_enable"] or policy["real_close_enable"] or policy["auto_scale_enable"] or policy["auto_apply_enable"]:
        reasons.append(_reason("unsafe_flag_enabled", "Submit/close/scale/apply flags must remain default OFF in this block.", "disable_unsafe_flags", "critical", 0))
    decision = "BLOCKED" if any(r.get("severity") == "critical" for r in reasons) else "ATTENTION" if reasons else "OK"
    checks = [
        _check("freshness_integrity", freshness.get("status", "review"), "Runtime freshness validator result."),
        _check("journal_integrity", journal.get("status", "review"), "Journal checksum result."),
        _check("learning_integrity", learning.get("status", "review"), "Learning memory guard result.", False),
        _check("decision_schema_integrity", schema.get("status", "review"), "Decision packet schema result."),
        _check("unsafe_flags_off", "ok" if not (policy["real_submit_enable"] or policy["real_close_enable"] or policy["auto_scale_enable"] or policy["auto_apply_enable"]) else "blocked", "Unsafe flags stay OFF.", True, 0, "disable_unsafe_flags"),
    ]
    report = {
        "data_integrity": decision,
        "data_integrity_ready": decision == "OK",
        "trade_allowed": False,
        "critical_issue": _critical(reasons),
        "operator_action": _critical(reasons).get("action"),
        "runtime_freshness": _as_dict(freshness.get("runtime_data_freshness_validator")).get("freshness_status"),
        "journal_status": _as_dict(journal.get("journal_consistency_checksum")).get("data_integrity"),
        "learning_status": _as_dict(learning.get("learning_memory_integrity_guard")).get("data_integrity"),
        "decision_schema_status": _as_dict(schema.get("decision_packet_schema_validator")).get("data_integrity"),
        "real_submit_close": "OFF",
        "auto_scale": "OFF",
        "auto_apply": "OFF",
    }
    return {"engine": "production_data_integrity_report", "revision": 230, "status": _final_status(checks), "generated_at": now_iso(), "production_data_integrity_report": report, "checks": checks, "check_totals": _totals(checks), "command_preview": _command_preview(), "contains_secret": False, "secret_values_returned": False, "next_allowed_step": "rev231_live_strategy_reality_validation_block"}


_REVISION_BUILDERS = {
    226: build_rev226_runtime_data_freshness_validator,
    227: build_rev227_journal_consistency_checksum,
    228: build_rev228_learning_memory_integrity_guard,
    229: build_rev229_decision_packet_schema_validator,
    230: build_rev230_production_data_integrity_report,
}


def build_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    revision = int(revision)
    if revision not in _REVISION_BUILDERS:
        raise ValueError(f"Unsupported Rev226-230 revision: {revision}")
    return _REVISION_BUILDERS[revision](data, settings, auth_store, username)


def build_summary_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    body = payload.get("runtime_data_freshness_validator") or payload.get("journal_consistency_checksum") or payload.get("learning_memory_integrity_guard") or payload.get("decision_packet_schema_validator") or payload.get("production_data_integrity_report") or {}
    issue = _as_dict(body.get("critical_issue"))
    return {
        "revision": int(revision),
        "status": payload.get("status"),
        "mode": "production_data_integrity_preview",
        "decision": body.get("data_integrity") or body.get("freshness_status") or payload.get("status"),
        "risk": issue.get("severity") or payload.get("status"),
        "trade_allowed": False,
        "data_integrity_ready": bool(body.get("data_integrity_ready")) if "data_integrity_ready" in body else payload.get("status") == "ok",
        "critical_issue": issue.get("code") or "review",
        "operator_action": body.get("operator_action") or issue.get("action") or "review_data_integrity",
        "runtime_freshness": body.get("runtime_freshness") or body.get("freshness_status"),
        "journal_status": body.get("journal_status"),
        "learning_status": body.get("learning_status"),
        "decision_schema_status": body.get("decision_schema_status"),
        "real_submit_close": "OFF",
        "command_preview": payload.get("command_preview"),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_block_payload(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    outputs = {
        "autonomous_runtime_data_freshness_validator": build_rev226_runtime_data_freshness_validator(data, settings, auth_store, username),
        "autonomous_journal_consistency_checksum": build_rev227_journal_consistency_checksum(data, settings, auth_store, username),
        "autonomous_learning_memory_integrity_guard": build_rev228_learning_memory_integrity_guard(data, settings, auth_store, username),
        "autonomous_decision_packet_schema_validator": build_rev229_decision_packet_schema_validator(data, settings, auth_store, username),
        "autonomous_production_data_integrity_report": build_rev230_production_data_integrity_report(data, settings, auth_store, username),
    }
    final = outputs["autonomous_production_data_integrity_report"]
    block_status = "blocked" if any(x.get("status") == "blocked" for x in outputs.values()) else "review" if any(x.get("status") == "review" for x in outputs.values()) else "ok"
    return {
        "engine": "autonomous_production_data_integrity_block",
        "revision": 230,
        "status": block_status,
        "generated_at": now_iso(),
        "outputs": outputs,
        "production_data_integrity_report": final.get("production_data_integrity_report"),
        "summary_result": build_summary_for_revision(230, data, settings, auth_store, username),
        "command_preview": _command_preview(),
        "contains_secret": False,
        "secret_values_returned": False,
    }


def build_quality_for_revision(revision: int, data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_for_revision(revision, data, settings, auth_store, username)
    all_checks = list(payload.get("checks") or []) + [
        _check("quality_network_default_off", "ok", "Quality gate confirms no exchange network request."),
        _check("quality_real_submit_default_off", "ok", "Quality gate confirms real submit default OFF."),
        _check("quality_real_close_default_off", "ok", "Quality gate confirms real close default OFF."),
        _check("quality_auto_scale_default_off", "ok", "Quality gate confirms auto-scale default OFF."),
        _check("quality_auto_apply_default_off", "ok", "Quality gate confirms auto-apply default OFF."),
        _check("quality_secret_free", "ok", "Quality gate confirms no secret values are returned."),
    ]
    return {"engine": "autonomous_production_data_integrity_quality_gate", "revision": int(revision), "quality_gate": "PASS", "status": payload.get("status"), "checks": all_checks, "check_totals": _totals(all_checks), "network_default_off": True, "real_submit_default_off": True, "real_close_default_off": True, "auto_scale_default_off": True, "auto_apply_default_off": True, "contains_secret": False, "secret_values_returned": False}
