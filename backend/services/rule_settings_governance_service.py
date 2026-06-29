from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.storage import load_shadow, load_settings, now_iso
from services.rule_engine import get_rule_versions, list_rules, restore_rule_version, validate_rule
from services.rule_governance_service import (
    build_rule_final_governance_report,
    build_rule_impact_report,
    build_rule_lineage_report,
    build_rule_rollback_preview,
)
from services.rule_schema_service import build_rule_diff, validate_rule_schema
from services.settings_risk_service import (
    build_real_readiness_impact,
    build_settings_change_diff,
    build_settings_rollback_preview,
    build_worst_case_risk_matrix,
)
from services.settings_unit_service import calculate_risk_summary, normalize_settings_units, validate_normalized_settings

LEVEL1_48_VERSION = "level1-48.rule-settings-governance.v1"


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _status(blockers: list | None = None, warnings: list | None = None) -> str:
    if blockers:
        return "blocked"
    if warnings:
        return "review"
    return "ok"


def _rule_danger_codes(rule: dict) -> list[dict]:
    warnings: list[dict] = []
    if not isinstance(rule, dict):
        return [{"code": "RULE_NOT_OBJECT", "severity": "blocked", "message": "Rule dict olmalı."}]
    rule_type = rule.get("type")
    if rule.get("enabled") is False:
        warnings.append({"code": "RULE_DISABLED", "severity": "notice", "message": "Rule pasif; Paper Lab çıktılarında beklenen etki görülmeyebilir."})
    risk_level = str(rule.get("risk_level") or "").lower()
    if risk_level == "high":
        warnings.append({"code": "HIGH_RISK_RULE", "severity": "warning", "message": "High risk rule sadece test/paper ve owner onaylı akışlarda kullanılmalı."})
    if rule_type == "filter":
        try:
            if float(rule.get("min_score") or 0) < 50:
                warnings.append({"code": "LOW_FILTER_MIN_SCORE", "severity": "warning", "message": "min_score 50 altı; düşük kaliteli coinleri sisteme alabilir."})
        except Exception:
            warnings.append({"code": "MIN_SCORE_NOT_NUMERIC", "severity": "blocked", "message": "min_score sayısal değil."})
        if not _safe_list(rule.get("avoid_conditions")):
            warnings.append({"code": "FILTER_WITHOUT_AVOID_CONDITIONS", "severity": "warning", "message": "Spread/volatilite/pump riskleri için avoid_conditions önerilir."})
    if rule_type == "strategy":
        if not _safe_list(rule.get("entry_rules")) and not _safe_list(rule.get("conditions")):
            warnings.append({"code": "STRATEGY_WITHOUT_ENTRY", "severity": "blocked", "message": "Strategy giriş koşulu olmadan aşırı geniş çalışabilir."})
        if not _safe_list(rule.get("exit_rules")):
            warnings.append({"code": "STRATEGY_WITHOUT_EXIT", "severity": "warning", "message": "exit_rules yok; Paper Lab çıkış davranışı belirsizleşir."})
    return warnings


def build_rule_governance_schema() -> dict:
    return {
        "status": "ok",
        "version": LEVEL1_48_VERSION,
        "contracts": {
            "version_list": "GET /api/rules/{rule_id}/versions",
            "diff_preview": "POST /api/rules/diff",
            "restore_as_new_version": "POST /api/rules/{rule_id}/restore-version",
            "impact_report": "GET /api/rules/{rule_id}/impact",
            "danger_warnings": "GET /api/rules/danger-warnings",
            "settings_rollback_preview": "POST /api/settings/rollback-preview",
            "settings_rollback_apply": "POST /api/settings/rollback",
            "settings_impact_preview": "POST /api/settings/impact-preview",
            "governance_evidence": "GET /api/rules/governance/evidence and GET /api/settings/governance/evidence",
        },
        "policies": {
            "restore_creates_new_version": True,
            "settings_rollback_creates_new_settings_record": True,
            "rule_settings_changes_are_audited": True,
            "dangerous_changes_are_warning_only_until_user_action": True,
            "governance_does_not_unlock_real_trading": True,
            "governance_does_not_place_orders": True,
        },
    }


def build_rule_danger_warnings(username: str, rule_id: str | None = None, candidate: dict | None = None) -> dict:
    rules = list_rules(username).get("rules", []) or []
    if candidate is not None:
        rules = [candidate]
    elif rule_id:
        rules = [rule for rule in rules if rule.get("id") == rule_id]
    rows = []
    blockers = []
    warnings = []
    for rule in rules:
        schema = validate_rule_schema(rule)
        base = validate_rule(rule)
        danger = _rule_danger_codes(rule)
        row_warnings = list(schema.get("warnings") or []) + list(base.get("warnings") or []) + danger
        row_errors = list(schema.get("errors") or []) + list(base.get("errors") or [])
        severity_blockers = [item for item in danger if item.get("severity") == "blocked"]
        row_status = _status(row_errors + severity_blockers, row_warnings)
        if row_status == "blocked":
            blockers.append(rule.get("id") or "candidate")
        elif row_status == "review":
            warnings.append(rule.get("id") or "candidate")
        rows.append({
            "rule_id": rule.get("id"),
            "name": rule.get("name"),
            "type": rule.get("type"),
            "version": rule.get("version"),
            "status": row_status,
            "errors": row_errors[:20],
            "warnings": row_warnings[:30],
            "danger_codes": danger,
        })
    return {
        "status": _status(blockers, warnings),
        "version": LEVEL1_48_VERSION,
        "rule_id": rule_id,
        "count": len(rows),
        "blocked_count": len(blockers),
        "review_count": len(warnings),
        "rows": rows,
        "generated_at": now_iso(),
    }


def build_settings_impact_preview(current_settings: dict | None, candidate_settings: dict | None) -> dict:
    current = normalize_settings_units(deepcopy(current_settings or {}))
    candidate = deepcopy(candidate_settings or current)
    validation = validate_normalized_settings(candidate)
    normalized = validation.get("normalized") or candidate
    changes = build_settings_change_diff(current, normalized)
    readiness = build_real_readiness_impact(normalized)
    matrix = build_worst_case_risk_matrix(normalized)
    warnings = list(validation.get("warnings") or []) + list(readiness.get("warnings") or [])
    blockers = [err.get("message") if isinstance(err, dict) else str(err) for err in (validation.get("errors") or [])] + list(readiness.get("blockers") or [])
    return {
        "status": _status(blockers, warnings),
        "version": LEVEL1_48_VERSION,
        "valid": validation.get("valid"),
        "changes": changes,
        "change_count": len(changes),
        "target_settings": normalized,
        "risk_calculation": normalized.get("risk_calculation") or calculate_risk_summary(normalized),
        "real_readiness_impact": readiness,
        "worst_case_matrix": matrix,
        "blockers": blockers,
        "warnings": warnings,
        "policy": "Impact preview read-only çalışır; kaydetme, rollback, real unlock veya emir oluşturmaz.",
        "generated_at": now_iso(),
    }


def build_risk_profile_audit(username: str) -> dict:
    data = load_shadow(username)
    history = _safe_list(data.get("settings_history"))
    rows = []
    for item in history:
        source = str(item.get("source") or "")
        changes = _safe_list(item.get("changes"))
        if "risk_profile" in source or any(str(ch.get("field") or "").startswith("risk.profile") for ch in changes):
            rows.append({
                "time": item.get("time"),
                "source": source,
                "user": item.get("user") or username,
                "profile": item.get("profile"),
                "changes": changes,
                "risk_calculation": item.get("risk_calculation"),
                "real_readiness_impact": item.get("real_readiness_impact"),
            })
    return {
        "status": "ok" if rows else "waiting_for_data",
        "version": LEVEL1_48_VERSION,
        "user": username,
        "count": len(rows),
        "rows": rows[-100:],
        "policy": "Risk profile değişiklikleri settings_history ve audit üzerinden izlenir.",
    }


def _audit_events(username: str, categories: set[str]) -> list[dict]:
    data = load_shadow(username)
    audit = _safe_list(data.get("audit")) + _safe_list(data.get("audit_log"))
    rows = []
    for item in audit:
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        category = str(meta.get("category") or item.get("category") or "")
        event = str(item.get("event") or item.get("action") or "")
        if category in categories or any(token in event for token in categories):
            rows.append({
                "time": item.get("time") or item.get("at"),
                "event": event,
                "result": item.get("result") or item.get("status"),
                "message": item.get("message"),
                "category": category,
                "severity": meta.get("severity") or item.get("severity"),
                "meta": meta,
            })
    return rows[-250:]


def build_rule_governance_evidence(username: str) -> dict:
    rules = list_rules(username).get("rules", []) or []
    lineage = build_rule_lineage_report(username)
    impact = build_rule_impact_report(username)
    evidence = _audit_events(username, {"rule", "rule.save", "rule.restore", "rule.delete"})
    versioned = 0
    for rule in rules:
        versioned += len(get_rule_versions(username, rule.get("id")).get("versions", []) or [])
    warnings = []
    if not evidence:
        warnings.append("rule_audit_evidence_not_found")
    if rules and versioned == 0:
        warnings.append("rule_versions_not_created_yet")
    return {
        "status": "review" if warnings else "ok",
        "version": LEVEL1_48_VERSION,
        "rules_count": len(rules),
        "archived_versions_count": versioned,
        "evidence_count": len(evidence),
        "lineage_summary": {"status": lineage.get("status"), "versioned_rules_count": lineage.get("versioned_rules_count")},
        "impact_summary": impact.get("summary", {}),
        "warnings": warnings,
        "evidence": evidence,
        "generated_at": now_iso(),
    }


def build_settings_governance_evidence(username: str) -> dict:
    data = load_shadow(username)
    settings = load_settings(username)
    history = _safe_list(data.get("settings_history"))
    evidence = _audit_events(username, {"settings", "settings.update", "risk_profile"})
    impact = build_real_readiness_impact(settings)
    warnings = []
    if not history:
        warnings.append("settings_history_empty")
    if not evidence:
        warnings.append("settings_audit_evidence_not_found")
    return {
        "status": "review" if warnings else "ok",
        "version": LEVEL1_48_VERSION,
        "settings_history_count": len(history),
        "evidence_count": len(evidence),
        "risk_profile_audit": build_risk_profile_audit(username),
        "current_impact": impact,
        "warnings": warnings,
        "evidence": evidence,
        "generated_at": now_iso(),
    }


def build_rule_settings_governance_quality(username: str) -> dict:
    settings = load_settings(username)
    rule_final = build_rule_final_governance_report(username)
    rule_evidence = build_rule_governance_evidence(username)
    settings_evidence = build_settings_governance_evidence(username)
    settings_impact = build_settings_impact_preview(settings, settings)
    danger = build_rule_danger_warnings(username)
    checks = [
        {"name": "rule_version_policy", "status": "ok", "detail": "restore_creates_new_version"},
        {"name": "rule_diff_available", "status": "ok", "detail": "POST /api/rules/diff"},
        {"name": "rule_impact_available", "status": "ok", "detail": "GET /api/rules/{id}/impact"},
        {"name": "dangerous_rule_warnings", "status": danger.get("status", "ok"), "detail": f"{danger.get('count', 0)} rules scanned"},
        {"name": "settings_rollback_available", "status": "ok", "detail": "rollback preview/apply endpoints"},
        {"name": "settings_impact_preview", "status": settings_impact.get("status", "ok"), "detail": f"{settings_impact.get('change_count', 0)} changes"},
        {"name": "risk_profile_audit", "status": build_risk_profile_audit(username).get("status", "ok"), "detail": "history based"},
        {"name": "governance_evidence_chain", "status": "review" if rule_evidence.get("status") == "review" or settings_evidence.get("status") == "review" else "ok", "detail": "rule/settings evidence"},
    ]
    blocked = [c for c in checks if c.get("status") == "blocked"]
    review = [c for c in checks if c.get("status") in {"review", "waiting_for_data"}]
    return {
        "status": _status(blocked, review),
        "version": LEVEL1_48_VERSION,
        "user": username,
        "checks": checks,
        "summary": {
            "check_count": len(checks),
            "blocked_count": len(blocked),
            "review_count": len(review),
            "rule_readiness_score": rule_final.get("readiness_score"),
        },
        "rule_governance": rule_final,
        "rule_evidence": rule_evidence,
        "settings_evidence": settings_evidence,
        "settings_impact": settings_impact,
        "policies": build_rule_governance_schema().get("policies", {}),
        "generated_at": now_iso(),
    }
