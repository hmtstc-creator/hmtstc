from __future__ import annotations

from collections import Counter
from typing import Any

from services.settings_unit_service import normalize_settings_units, validate_normalized_settings
from services.rule_engine import validate_rule, list_rules
from services.revision_12_service import build_revision_12_quality_report
from services.system_audit_service import build_api_contract_matrix
from services.analysis_service import scan_market


def _status(ok: bool, review: bool = False) -> str:
    if ok and not review:
        return "ok"
    if ok and review:
        return "review"
    return "blocked"


def build_settings_units_report(settings: dict) -> dict:
    validation = validate_normalized_settings(settings)
    normalized = validation.get("normalized") or normalize_settings_units(settings)
    return {
        "status": _status(validation.get("valid", False), bool(validation.get("warnings"))),
        "valid": validation.get("valid", False),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
        "unit_schema": normalized.get("unit_schema", {}),
        "risk_calculation": normalized.get("risk_calculation", {}),
        "notes": [
            "Yüzdelik alanlarda 0,75 veya 0.75 girişi 0.75% olarak yorumlanır.",
            "Para alanlarında çıplak sayı USDT olarak yorumlanır.",
        ],
    }


def build_audit_log_report(data: dict) -> dict:
    items = data.get("audit", []) if isinstance(data, dict) else []
    categories = Counter(str(item.get("category") or "unknown") for item in items if isinstance(item, dict))
    severities = Counter(str(item.get("severity") or "info") for item in items if isinstance(item, dict))
    critical = [item for item in items if str(item.get("severity")) in {"critical", "blocked"}]
    missing_context = [item for item in items if isinstance(item, dict) and not item.get("request_id")]
    return {
        "status": "ok" if not missing_context or len(items) == 0 else "review",
        "total": len(items),
        "categories": dict(categories),
        "severities": dict(severities),
        "critical_count": len(critical),
        "missing_request_id_count": len(missing_context),
        "schema": {
            "required": ["time", "user", "role", "action", "category", "severity", "result", "request_id"],
            "categories": ["security", "settings", "rule", "strategy", "filter", "risk", "trading", "paper_lab", "recommendation", "approval", "backup", "restore", "system", "user", "package"],
            "severities": ["info", "notice", "warning", "critical", "blocked"],
        },
    }


def build_rule_schema_report(username: str = "ahmet") -> dict:
    payload = list_rules(username)
    rules = payload.get("rules", []) or []
    results = []
    for rule in rules:
        validation = validate_rule(rule)
        results.append({"id": rule.get("id"), "type": rule.get("type"), "valid": validation.get("valid"), "errors": validation.get("errors", []), "warnings": validation.get("warnings", [])})
    invalid = [item for item in results if not item.get("valid")]
    return {"status": "ok" if not invalid else "blocked", "count": len(rules), "invalid_count": len(invalid), "rules": results[-50:]}


def build_scan_trace_report(data: dict, settings: dict) -> dict:
    scan = (data or {}).get("last_scan") or {}
    trace = scan.get("scan_trace") or {}
    diagnostics = scan.get("scan_diagnostics") or {}
    issues = []
    if not scan:
        issues.append("no_scan_yet")
    if scan and not trace:
        issues.append("missing_scan_trace")
    return {
        "status": "ok" if not issues else "review",
        "scan_id": scan.get("scan_id"),
        "scanned": scan.get("scanned", 0),
        "eligible_universe_count": scan.get("eligible_universe_count", 0),
        "candidates_count": scan.get("candidates_count", 0),
        "trace": trace,
        "diagnostics": diagnostics,
        "issues": issues,
    }


def build_bot_loop_trace_report(data: dict) -> dict:
    traces = (data or {}).get("bot_loop_traces") or []
    last = traces[-1] if traces else {}
    issues = []
    if not traces:
        issues.append("no_bot_loop_trace_yet")
    return {"status": "ok" if not issues else "review", "count": len(traces), "last": last, "issues": issues}


def build_revision_13_quality_report(data: dict, settings: dict, username: str = "ahmet") -> dict:
    settings_units = build_settings_units_report(settings)
    audit_log = build_audit_log_report(data)
    rule_schema = build_rule_schema_report(username)
    scan_trace = build_scan_trace_report(data, settings)
    bot_loop_trace = build_bot_loop_trace_report(data)
    previous = build_revision_12_quality_report(data, settings, username=username)
    blocks = {
        "settings_units": settings_units,
        "audit_log": audit_log,
        "rule_schema": rule_schema,
        "scan_trace": scan_trace,
        "bot_loop_trace": bot_loop_trace,
        "api_contract": build_api_contract_matrix(),
        "previous_revision_gate": previous.get("readiness", {}),
    }
    statuses = [block.get("status") for block in blocks.values() if isinstance(block, dict)]
    blockers = sum(1 for status in statuses if status == "blocked")
    reviews = sum(1 for status in statuses if status == "review")
    score = max(0, 100 - blockers * 25 - reviews * 8)
    return {
        "status": "blocked" if blockers else ("review" if reviews else "ok"),
        "revision": 13,
        "readiness": {"score": score, "blockers": blockers, "reviews": reviews, "state": "blocked" if blockers else ("review" if reviews else "ready")},
        "checks": blocks,
        "next_gate": "revizyon_14_trade_decision_depth",
    }
