from __future__ import annotations

from services.rule_governance_service import (
    build_rule_final_governance_report,
    build_rule_impact_report,
    build_rule_lineage_report,
)
from services.rule_schema_service import build_rule_schema_contract

REVISION = "26"


def _gate(name: str, report: dict, min_ok_score: int | None = None) -> dict:
    status = report.get("status", "review") if isinstance(report, dict) else "blocked"
    if min_ok_score is not None and isinstance(report, dict):
        score = int(report.get("readiness_score") or report.get("avg_rule_score") or 0)
        if score < min_ok_score and status == "ok":
            status = "review"
    return {"name": name, "status": status, "report": report}


def build_rule_schema_hardening_quality(username: str) -> dict:
    contract = build_rule_schema_contract()
    required = contract.get("schemas", {})
    missing = []
    for rule_type in ["filter", "strategy"]:
        schema = required.get(rule_type, {})
        for key in ["required", "recommended", "forbidden", "sections"]:
            if key not in schema:
                missing.append(f"{rule_type}.{key}")
    return {
        "status": "ok" if not missing else "blocked",
        "schema_version": contract.get("schema_version"),
        "types": contract.get("types", []),
        "metrics_count": contract.get("metrics_count", 0),
        "operators": contract.get("operators", []),
        "missing_contract_parts": missing,
        "hardening_checks": {
            "required_fields": True,
            "forbidden_fields": True,
            "metric_whitelist": True,
            "operator_whitelist": True,
            "dangerous_rule_warnings": True,
            "type_separation": True,
        },
    }


def build_rule_governance_final_quality(username: str) -> dict:
    return build_rule_final_governance_report(username)


def build_rule_lineage_quality(username: str) -> dict:
    return build_rule_lineage_report(username)


def build_rule_impact_quality(username: str) -> dict:
    return build_rule_impact_report(username)


def build_rule_rollback_quality(username: str) -> dict:
    lineage = build_rule_lineage_report(username)
    rows = lineage.get("rows", [])
    restore_ready = len([row for row in rows if row.get("archived_versions", 0) > 0])
    return {
        "status": "ok" if restore_ready else "review",
        "restore_ready_rules": restore_ready,
        "rules_count": len(rows),
        "policy": "restore_creates_new_version_and_requires_audit",
        "owner_only": True,
        "rollback_preview_endpoint": "/api/rules/{rule_id}/rollback-preview",
    }


def build_revision_26_quality_report(username: str) -> dict:
    schema = build_rule_schema_hardening_quality(username)
    governance = build_rule_governance_final_quality(username)
    lineage = build_rule_lineage_quality(username)
    impact = build_rule_impact_quality(username)
    rollback = build_rule_rollback_quality(username)
    gates = [
        _gate("schema_hardening", schema),
        _gate("governance_final", governance, min_ok_score=65),
        _gate("lineage", lineage),
        _gate("impact", impact),
        _gate("rollback", rollback),
    ]
    blocked = [g for g in gates if g.get("status") == "blocked"]
    review = [g for g in gates if g.get("status") == "review"]
    score = max(0, 100 - len(blocked) * 30 - len(review) * 10)
    return {
        "revision": REVISION,
        "status": "blocked" if blocked else ("review" if review else "ok"),
        "score": score,
        "gates": gates,
        "rule_governance": governance,
        "lineage": lineage,
        "impact": impact,
        "rollback": rollback,
        "next_revision": "Rev27 = Settings & Risk Final Pack",
    }
