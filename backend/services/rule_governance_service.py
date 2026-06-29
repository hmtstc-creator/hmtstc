from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.storage import load_shadow, now_iso
from services.rule_engine import get_rule_versions, list_rules, validate_rule
from services.rule_schema_service import validate_rule_schema, build_rule_diff, RULE_SCHEMA_VERSION

RULE_GOVERNANCE_VERSION = "rev26.rule-governance.v1"


def _status(blocked: int = 0, review: int = 0) -> str:
    if blocked > 0:
        return "blocked"
    if review > 0:
        return "review"
    return "ok"


def _rule_score(rule: dict) -> dict:
    schema = validate_rule_schema(rule)
    base = validate_rule(rule)
    errors = list(schema.get("errors") or []) + list(base.get("errors") or [])
    warnings = list(schema.get("warnings") or []) + list(base.get("warnings") or [])
    score = 100
    score -= min(80, len(errors) * 25)
    score -= min(35, len(warnings) * 7)
    if rule.get("enabled") is False:
        score -= 5
    if rule.get("type") == "strategy" and not rule.get("exit_rules"):
        score -= 8
    if rule.get("type") == "filter" and float(rule.get("min_score") or 0) < 50:
        score -= 10
    return {
        "rule_id": rule.get("id"),
        "type": rule.get("type"),
        "name": rule.get("name"),
        "version": rule.get("version"),
        "enabled": rule.get("enabled", True),
        "score": max(0, min(100, int(score))),
        "status": _status(len(errors), len(warnings)),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors[:12],
        "warnings": warnings[:12],
    }


def build_rule_lineage_report(username: str, rule_id: str | None = None) -> dict:
    payload = list_rules(username)
    rules = payload.get("rules", []) or []
    if rule_id:
        rules = [item for item in rules if item.get("id") == rule_id]
    rows = []
    total_versions = 0
    for rule in rules:
        versions_payload = get_rule_versions(username, rule.get("id"))
        versions = versions_payload.get("versions", []) or []
        total_versions += len(versions)
        rows.append({
            "rule_id": rule.get("id"),
            "type": rule.get("type"),
            "name": rule.get("name"),
            "current_version": rule.get("version"),
            "archived_versions": len(versions),
            "last_archived_at": (versions[-1] or {}).get("archived_at") if versions else None,
            "lineage_status": "versioned" if versions else "single_version",
            "restore_policy": "restore_creates_new_version",
            "snapshot_policy": "paper_positions_keep_entry_snapshot",
        })
    review = sum(1 for row in rows if row.get("archived_versions", 0) == 0)
    return {
        "status": _status(review=review if rows else 0),
        "governance_version": RULE_GOVERNANCE_VERSION,
        "rule_id": rule_id,
        "rules_count": len(rows),
        "archived_versions_count": total_versions,
        "versioned_rules_count": len([r for r in rows if r.get("archived_versions", 0) > 0]),
        "rows": rows,
        "notes": [
            "Restore işlemi geçmişe dönük performansı değiştirmez; yeni versiyon oluşturur.",
            "Paper Lab pozisyonları açılış anındaki rule snapshot/version bilgisini taşımaya devam etmelidir.",
        ],
    }


def _extract_rule_refs(position: dict) -> tuple[str | None, str | None]:
    filter_id = position.get("filter_id") or position.get("filter_rule_id")
    strategy_id = position.get("strategy_id") or position.get("strategy_rule_id")
    snapshot = position.get("settings_snapshot") or position.get("rule_snapshot") or {}
    if isinstance(snapshot, dict):
        filter_id = filter_id or snapshot.get("filter_id") or snapshot.get("filter_rule_id")
        strategy_id = strategy_id or snapshot.get("strategy_id") or snapshot.get("strategy_rule_id")
    signal = position.get("entry_signal") or {}
    if isinstance(signal, dict):
        filter_id = filter_id or signal.get("filter_id")
        strategy_id = strategy_id or signal.get("strategy_id")
    return filter_id, strategy_id


def _pnl(position: dict) -> float:
    for key in ("pnl", "realized_pnl", "total_pnl", "pnl_usdt"):
        try:
            return float(position.get(key) or 0)
        except Exception:
            pass
    return 0.0


def build_rule_impact_report(username: str, rule_id: str | None = None) -> dict:
    data = load_shadow(username)
    rules_payload = list_rules(username)
    rules = rules_payload.get("rules", []) or []
    rule_ids = {item.get("id") for item in rules}
    positions = []
    for key in ("positions", "closed_positions", "history", "paper_positions"):
        value = data.get(key, [])
        if isinstance(value, list):
            positions.extend([item for item in value if isinstance(item, dict)])
    impact: dict[str, dict[str, Any]] = {}
    for rid in rule_ids:
        impact[rid] = {"rule_id": rid, "trades": 0, "pnl": 0.0, "wins": 0, "losses": 0, "snapshot_coverage": 0}
    for pos in positions:
        filter_id, strategy_id = _extract_rule_refs(pos)
        refs = [item for item in [filter_id, strategy_id] if item]
        for rid in refs:
            if rule_id and rid != rule_id:
                continue
            row = impact.setdefault(rid, {"rule_id": rid, "trades": 0, "pnl": 0.0, "wins": 0, "losses": 0, "snapshot_coverage": 0})
            pnl = _pnl(pos)
            row["trades"] += 1
            row["pnl"] += pnl
            if pnl > 0:
                row["wins"] += 1
            elif pnl < 0:
                row["losses"] += 1
            if pos.get("rule_snapshot") or pos.get("settings_snapshot") or pos.get("entry_signal"):
                row["snapshot_coverage"] += 1
    rows = []
    for rid, row in impact.items():
        if rule_id and rid != rule_id:
            continue
        trades = int(row.get("trades") or 0)
        wins = int(row.get("wins") or 0)
        row["pnl"] = round(float(row.get("pnl") or 0), 6)
        row["win_rate"] = round((wins / trades) * 100, 2) if trades else 0
        row["snapshot_coverage_pct"] = round((int(row.get("snapshot_coverage") or 0) / trades) * 100, 2) if trades else 0
        row["impact_status"] = "no_data" if trades == 0 else ("review" if row["snapshot_coverage_pct"] < 70 else "ok")
        rows.append(row)
    rows = sorted(rows, key=lambda x: (x.get("trades", 0), x.get("pnl", 0)), reverse=True)
    no_data = len([r for r in rows if r.get("trades", 0) == 0])
    review = len([r for r in rows if r.get("impact_status") == "review"])
    return {
        "status": _status(review=review + (1 if no_data and not rule_id else 0)),
        "governance_version": RULE_GOVERNANCE_VERSION,
        "rule_id": rule_id,
        "positions_scanned": len(positions),
        "rows": rows[:100],
        "summary": {
            "rules_count": len(rows),
            "rules_with_trades": len([r for r in rows if r.get("trades", 0) > 0]),
            "rules_without_trades": no_data,
            "snapshot_review_count": review,
        },
    }


def build_rule_rollback_preview(username: str, rule_id: str, archived_at: str | None = None, version: int | None = None) -> dict:
    versions_payload = get_rule_versions(username, rule_id)
    versions = versions_payload.get("versions", []) or []
    current = versions_payload.get("current")
    selected = None
    if archived_at:
        selected = next((item for item in versions if item.get("archived_at") == archived_at), None)
    if selected is None and version is not None:
        selected = next((item for item in reversed(versions) if int(item.get("version") or 0) == int(version)), None)
    if selected is None and versions:
        selected = versions[-1]
    diff = build_rule_diff(username, rule_id, selected or {}) if selected else {"diff": [], "change_count": 0}
    blockers = []
    if not current:
        blockers.append("current_rule_not_found")
    if not selected:
        blockers.append("version_not_found")
    validation = validate_rule_schema(selected or {}) if selected else {"valid": False, "errors": []}
    if selected and not validation.get("valid"):
        blockers.append("selected_version_schema_invalid")
    return {
        "status": "blocked" if blockers else "ok",
        "rule_id": rule_id,
        "current_version": (current or {}).get("version"),
        "target_version": (selected or {}).get("version"),
        "target_archived_at": (selected or {}).get("archived_at"),
        "restore_policy": "restore_creates_new_version",
        "will_create_version": int((current or {}).get("version") or 0) + 1 if current else None,
        "change_count": diff.get("change_count", len(diff.get("diff", []))),
        "diff": (diff.get("diff") or [])[:80],
        "validation": validation,
        "blockers": blockers,
        "requires_owner": True,
        "requires_audit": True,
    }


def build_rule_final_governance_report(username: str) -> dict:
    payload = list_rules(username)
    rules = payload.get("rules", []) or []
    scores = [_rule_score(item) for item in rules]
    lineage = build_rule_lineage_report(username)
    impact = build_rule_impact_report(username)
    blocked = len([s for s in scores if s.get("status") == "blocked"])
    review = len([s for s in scores if s.get("status") == "review"])
    avg_score = round(sum(s.get("score", 0) for s in scores) / len(scores), 2) if scores else 0
    readiness = max(0, min(100, int(avg_score) - blocked * 20 - review * 5))
    return {
        "status": _status(blocked, review),
        "governance_version": RULE_GOVERNANCE_VERSION,
        "schema_version": RULE_SCHEMA_VERSION,
        "rules_count": len(rules),
        "filters_count": len(payload.get("filters", []) or []),
        "strategies_count": len(payload.get("strategies", []) or []),
        "avg_rule_score": avg_score,
        "readiness_score": readiness,
        "blocked_rules": blocked,
        "review_rules": review,
        "rule_scores": scores[:100],
        "lineage_summary": {
            "status": lineage.get("status"),
            "versioned_rules_count": lineage.get("versioned_rules_count"),
            "archived_versions_count": lineage.get("archived_versions_count"),
        },
        "impact_summary": impact.get("summary", {}),
        "policies": {
            "schema_validation_required": True,
            "restore_creates_new_version": True,
            "import_requires_validation": True,
            "duplicate_id_protection": True,
            "paper_lab_activation_is_not_real_trade": True,
            "owner_only_rule_editor": True,
        },
        "generated_at": now_iso(),
    }
