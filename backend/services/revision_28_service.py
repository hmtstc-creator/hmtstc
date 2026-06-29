from __future__ import annotations

from services.audit_forensics_service import (
    audit_completeness_report,
    audit_immutability_report,
    audit_search_index,
    audit_taxonomy_report,
    build_audit_forensics_final_report,
    security_trading_timeline,
)


def _items(data: dict) -> list[dict]:
    return data.get("audit", []) if isinstance(data, dict) and isinstance(data.get("audit"), list) else []


def _gate(name: str, report: dict, min_score: float = 70) -> dict:
    status = report.get("status", "review")
    score = report.get("score")
    passed = status == "ok" and (score is None or float(score) >= min_score)
    return {"name": name, "status": "ok" if passed else "review", "passed": passed, "report": report}


def build_revision_28_quality_report(data: dict) -> dict:
    items = _items(data)
    forensics = build_audit_forensics_final_report(data)
    taxonomy = audit_taxonomy_report(items)
    completeness = audit_completeness_report(items)
    immutability = audit_immutability_report(data)
    search = audit_search_index(items)
    timeline = security_trading_timeline(items)
    gates = [
        _gate("audit_taxonomy", taxonomy),
        _gate("audit_completeness", completeness),
        _gate("audit_immutability", immutability),
        _gate("audit_search", search),
        _gate("security_trading_timeline", timeline),
    ]
    score = round(sum(100 if g["passed"] else 70 for g in gates) / len(gates), 2) if gates else 0
    return {
        "status": "ok" if all(g["passed"] for g in gates) else "review",
        "revision": 28,
        "score": score,
        "gates": gates,
        "audit_forensics": forensics,
        "taxonomy": taxonomy,
        "completeness": completeness,
        "immutability": immutability,
        "search": search,
        "security_trading_timeline": timeline,
        "policy": {
            "owner_only_clear": True,
            "export_manifest": True,
            "hash_chain": True,
            "critical_action_highlight": True,
            "runtime_json_limitation": "JSON runtime store is not cryptographically immutable; hash-chain detects exported sequence changes.",
        },
    }


def build_audit_forensics_quality(data: dict) -> dict:
    return build_audit_forensics_final_report(data)


def build_audit_search_quality(data: dict) -> dict:
    return audit_search_index(_items(data))


def build_audit_export_quality(data: dict) -> dict:
    items = _items(data)
    from services.audit_forensics_service import audit_export_manifest
    return {"status": "ok", "json": audit_export_manifest(items, "json"), "csv": audit_export_manifest(items, "csv")}


def build_audit_immutability_quality(data: dict) -> dict:
    return audit_immutability_report(data)


def build_audit_timeline_quality(data: dict) -> dict:
    return security_trading_timeline(_items(data))
