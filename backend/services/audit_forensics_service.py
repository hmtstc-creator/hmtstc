from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any

AUDIT_CATEGORIES = [
    "security", "settings", "rule", "strategy", "filter", "risk", "trading", "paper_lab",
    "recommendation", "approval", "backup", "restore", "system", "user", "package", "audit",
]
AUDIT_SEVERITIES = ["info", "notice", "warning", "critical", "blocked"]
CRITICAL_ACTION_HINTS = ["real", "order", "emergency", "unlock", "restore", "delete", "clear", "approval", "backup"]


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _stable_payload(item: dict) -> str:
    payload = {k: item.get(k) for k in sorted(item.keys()) if k not in {"hash", "prev_hash", "chain_index"}}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def audit_hash(item: dict, prev_hash: str = "") -> str:
    return hashlib.sha256((prev_hash + "|" + _stable_payload(item)).encode("utf-8")).hexdigest()


def enrich_audit_chain(items: list[dict]) -> list[dict]:
    enriched = []
    prev = "GENESIS"
    for idx, raw in enumerate(_safe_list(items)):
        item = dict(raw or {})
        item["chain_index"] = idx
        item["prev_hash"] = prev
        item["hash"] = audit_hash(item, prev)
        prev = item["hash"]
        enriched.append(item)
    return enriched


def audit_taxonomy_report(items: list[dict]) -> dict:
    items = _safe_list(items)
    categories = Counter(str(x.get("category") or "system") for x in items)
    severities = Counter(str(x.get("severity") or "info") for x in items)
    results = Counter(str(x.get("result") or "ok") for x in items)
    unknown_categories = sorted([k for k in categories if k not in AUDIT_CATEGORIES])
    unknown_severities = sorted([k for k in severities if k not in AUDIT_SEVERITIES])
    return {
        "status": "ok" if not unknown_categories and not unknown_severities else "review",
        "categories": dict(categories),
        "severities": dict(severities),
        "results": dict(results),
        "allowed_categories": AUDIT_CATEGORIES,
        "allowed_severities": AUDIT_SEVERITIES,
        "unknown_categories": unknown_categories,
        "unknown_severities": unknown_severities,
    }


def audit_completeness_report(items: list[dict]) -> dict:
    items = _safe_list(items)
    total = len(items)
    def pct(count: int) -> float:
        return round((count / total) * 100, 2) if total else 0.0
    fields = ["request_id", "correlation_id", "endpoint", "page", "role", "category", "severity"]
    coverage = {field + "_coverage_pct": pct(len([x for x in items if x.get(field)])) for field in fields}
    before_after = len([x for x in items if x.get("before") is not None or x.get("after") is not None])
    coverage["before_after_coverage_pct"] = pct(before_after)
    critical = [x for x in items if str(x.get("severity") or "").lower() in {"critical", "blocked"}]
    critical_before_after = len([x for x in critical if x.get("before") is not None or x.get("after") is not None])
    coverage["critical_before_after_coverage_pct"] = round((critical_before_after / len(critical)) * 100, 2) if critical else 100.0
    score = round(sum(coverage.values()) / max(len(coverage), 1), 2)
    return {"status": "ok" if score >= 70 else "review", "total": total, "critical": len(critical), "score": score, **coverage}


def audit_immutability_report(data: dict) -> dict:
    items = _safe_list(data.get("audit"))
    chain = enrich_audit_chain(items)
    clear_ledger = _safe_list(data.get("audit_clear_ledger"))
    policy = {
        "append_only_policy": True,
        "clear_requires_owner": True,
        "clear_keeps_ledger": True,
        "exports_include_manifest": True,
        "hash_chain_available": True,
        "runtime_json_not_tamper_proof": True,
    }
    warnings = []
    if not chain:
        warnings.append("Audit listesi boş; zincir canlı aksiyonlardan sonra oluşacak.")
    if len(clear_ledger) == 0:
        warnings.append("Audit clear ledger boş; clear aksiyonu yapılmadıysa normal.")
    return {
        "status": "ok" if policy["hash_chain_available"] else "review",
        "items": len(items),
        "last_hash": chain[-1]["hash"] if chain else None,
        "clear_ledger_count": len(clear_ledger),
        "policy": policy,
        "warnings": warnings,
    }


def audit_search_index(items: list[dict]) -> dict:
    items = _safe_list(items)
    endpoints = Counter(str(x.get("endpoint") or "-") for x in items)
    actions = Counter(str(x.get("action") or "-") for x in items)
    users = Counter(str(x.get("user") or "-") for x in items)
    critical = [x for x in items if str(x.get("severity") or "").lower() in {"critical", "blocked"}]
    recent = list(reversed(items[-20:]))
    return {
        "status": "ok",
        "total": len(items),
        "top_endpoints": endpoints.most_common(15),
        "top_actions": actions.most_common(15),
        "top_users": users.most_common(15),
        "critical_count": len(critical),
        "recent": recent,
    }


def security_trading_timeline(items: list[dict]) -> dict:
    filtered = []
    for item in _safe_list(items):
        category = str(item.get("category") or "").lower()
        severity = str(item.get("severity") or "").lower()
        action = str(item.get("action") or "").lower()
        if category in {"security", "trading", "approval", "restore", "backup"} or severity in {"critical", "blocked"} or any(h in action for h in CRITICAL_ACTION_HINTS):
            filtered.append(item)
    return {"status": "ok", "count": len(filtered), "items": list(reversed(filtered[-200:]))}


def audit_export_manifest(items: list[dict], fmt: str, filters: dict | None = None) -> dict:
    chain = enrich_audit_chain(items)
    exported_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    content_hash = hashlib.sha256(json.dumps(chain, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {
        "format": fmt,
        "count": len(items),
        "exported_at": exported_at,
        "content_hash": content_hash,
        "first_hash": chain[0]["hash"] if chain else None,
        "last_hash": chain[-1]["hash"] if chain else None,
        "filters": filters or {},
        "immutable_policy": "runtime-json-hash-chain-ledger",
    }


def build_audit_forensics_final_report(data: dict) -> dict:
    items = _safe_list((data or {}).get("audit"))
    taxonomy = audit_taxonomy_report(items)
    completeness = audit_completeness_report(items)
    immutability = audit_immutability_report(data or {})
    search = audit_search_index(items)
    timeline = security_trading_timeline(items)
    score = round((completeness.get("score", 0) + (100 if taxonomy.get("status") == "ok" else 70) + (100 if immutability.get("status") == "ok" else 70)) / 3, 2)
    return {
        "status": "ok" if score >= 80 else "review",
        "revision": 28,
        "score": score,
        "taxonomy": taxonomy,
        "completeness": completeness,
        "immutability": immutability,
        "search_index": search,
        "security_trading_timeline": timeline,
    }
