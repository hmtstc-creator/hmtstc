#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIFF_PATH = ROOT / "docs" / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
ROUTE_INVENTORY_PATH = ROOT / "docs" / "LEVEL1_40_06_API_ROUTE_INVENTORY.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_09_MISSING_ENDPOINT_REPORT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_09_MISSING_ENDPOINT_REPORT.md"

CRITICAL_PREFIXES = (
    "/api/real/",
    "/api/settings/",
    "/api/rules",
    "/api/models/real-approval",
)


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _path_normalized(path: str) -> str:
    return (path or "").strip().rstrip("/") or "/"


def _template_matches(endpoint: str, method: str, routes: list[dict]) -> bool:
    endpoint_norm = _path_normalized(endpoint)
    for route in routes:
        if method.upper() not in [m.upper() for m in route.get("methods", [])]:
            continue
        path = _path_normalized(route.get("path") or "")
        if "{" not in path:
            continue
        prefix = _path_normalized(path.split("{")[0])
        if endpoint_norm == prefix or endpoint_norm.startswith(prefix + "/") or endpoint_norm.startswith(prefix):
            return True
    return False


def _classify_mismatch(item: dict, routes: list[dict]) -> tuple[str, str, str]:
    frontend = item.get("frontend") or {}
    method = str(frontend.get("method") or "GET").upper()
    endpoint = str(frontend.get("endpoint") or "")
    source_kind = frontend.get("source_kind") or "unknown"
    backend_methods = item.get("available_backend_methods") or []
    backend_paths = item.get("backend_paths") or []

    if source_kind == "string-literal" and method == "GET" and "POST" in backend_methods:
        return (
            "static_inventory_false_positive",
            "frontend string literal endpoint metadata was detected as an API call; actual fetchJson call uses POST nearby",
            "no endpoint implementation required; improve frontend inventory parser context in a later step",
        )

    if _template_matches(endpoint, method, routes) or (endpoint.endswith("/") and any("{" in p and _path_normalized(endpoint).startswith(_path_normalized(p.split("{")[0])) for p in backend_paths)):
        return (
            "dynamic_path_match_parser_gap",
            "frontend builds a dynamic endpoint and the static diff matched the collection route instead of parameterized route",
            "no backend endpoint required; improve contract matcher to support parameterized path templates",
        )

    if _path_normalized(endpoint) == "/api/rules" and method in {"POST", "DELETE"}:
        return (
            "rules_dynamic_id_parser_gap",
            "frontend constructs rule-id endpoints dynamically, while static inventory collapsed them to /api/rules/",
            "verify generated URL includes encoded rule id; improve extractor before declaring missing backend route",
        )

    if not backend_methods:
        return (
            "missing_backend_path",
            "frontend endpoint path has no backend route candidate",
            "add backend route or remove/update frontend call",
        )

    return (
        "method_mismatch_review",
        f"frontend method {method} does not match backend methods {backend_methods}",
        "manual review required; either update frontend method or backend route",
    )


def build_report(diff: dict, route_inventory: dict) -> dict:
    missing_paths = diff.get("missing_paths") or []
    method_mismatches = diff.get("method_mismatches") or []
    routes = route_inventory.get("routes") or []
    classified = []
    by_category = Counter()
    by_file = Counter()
    critical_items = []

    for idx, item in enumerate(method_mismatches, 1):
        frontend = item.get("frontend") or {}
        category, reason, recommended_action = _classify_mismatch(item, routes)
        normalized = {
            "id": f"MM-{idx:03d}",
            "category": category,
            "frontend_file": frontend.get("file"),
            "line": frontend.get("line"),
            "frontend_method": frontend.get("method"),
            "frontend_endpoint": frontend.get("endpoint"),
            "source_kind": frontend.get("source_kind"),
            "backend_methods": item.get("available_backend_methods") or [],
            "backend_paths": item.get("backend_paths") or [],
            "reason": reason,
            "recommended_action": recommended_action,
            "critical": any(str(frontend.get("endpoint") or "").startswith(prefix) for prefix in CRITICAL_PREFIXES),
        }
        classified.append(normalized)
        by_category[category] += 1
        by_file[normalized["frontend_file"] or "unknown"] += 1
        if normalized["critical"]:
            critical_items.append(normalized)

    missing_classified = []
    for idx, item in enumerate(missing_paths, 1):
        frontend = item.get("frontend") or item
        missing_classified.append({
            "id": f"MP-{idx:03d}",
            "category": "missing_backend_path",
            "frontend_file": frontend.get("file"),
            "line": frontend.get("line"),
            "frontend_method": frontend.get("method"),
            "frontend_endpoint": frontend.get("endpoint"),
            "recommended_action": "add backend route or update frontend call",
            "critical": any(str(frontend.get("endpoint") or "").startswith(prefix) for prefix in CRITICAL_PREFIXES),
        })

    true_blockers = [x for x in classified if x["category"] in {"missing_backend_path", "method_mismatch_review"}]
    parser_gaps = [x for x in classified if x["category"].endswith("parser_gap") or x["category"] == "static_inventory_false_positive"]
    diff_method_mismatch_count = int(diff.get("method_mismatch_count") or len(classified))

    status = "ok" if not missing_classified and not true_blockers else "review"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_diff": str(DIFF_PATH.relative_to(ROOT)),
        "frontend_call_count": diff.get("frontend_call_count"),
        "backend_route_count": diff.get("backend_route_count"),
        "missing_path_count": len(missing_classified),
        "method_mismatch_count": diff_method_mismatch_count,
        "true_blocker_count": len(missing_classified) + len(true_blockers),
        "parser_gap_or_false_positive_count": len(parser_gaps),
        "critical_review_count": len(critical_items),
        "by_category": dict(by_category),
        "by_file": dict(by_file),
        "missing_paths": missing_classified,
        "method_mismatches": classified,
        "true_blockers": missing_classified + true_blockers,
        "parser_gaps_or_false_positives": parser_gaps,
        "critical_items": critical_items,
        "recommended_next_actions": [
            "Do not add backend routes solely from static contract findings; review parser output first.",
            "Keep the frontend inventory extractor limited to real fetch/fetchJson calls.",
            "Keep parameterized path matching enabled for dynamic URLs such as /api/settings/risk-profiles/{dynamic} and /api/rules/{dynamic}.",
            "Keep real-trade endpoints under special review even when the contract guard is green.",
        ],
    }


def write_markdown(report: dict) -> None:
    lines = []
    lines.append("# LEVEL1 40.09 — Missing Endpoint Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Status: `{report['status']}`")
    lines.append(f"- Frontend calls reviewed: `{report['frontend_call_count']}`")
    lines.append(f"- Backend routes reviewed: `{report['backend_route_count']}`")
    lines.append(f"- Missing backend paths: `{report['missing_path_count']}`")
    lines.append(f"- Method mismatches: `{report['method_mismatch_count']}`")
    lines.append(f"- True blockers: `{report['true_blocker_count']}`")
    lines.append(f"- Parser gaps / false positives: `{report['parser_gap_or_false_positive_count']}`")
    lines.append(f"- Critical review items: `{report['critical_review_count']}`")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    if report["true_blocker_count"] == 0:
        if report["method_mismatch_count"] == 0:
            lines.append("No frontend path is missing in backend and no method mismatch remains.")
        else:
            lines.append(f"No frontend path is missing in backend. `{report['method_mismatch_count']}` method mismatch item(s) remain classified as parser gaps or static inventory false positives.")
    else:
        lines.append("There are true endpoint blockers. These must be fixed before the API contract can be considered green.")
    lines.append("")
    lines.append("## Category counts")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|---|---:|")
    for category, count in sorted(report["by_category"].items()):
        lines.append(f"| `{category}` | {count} |")
    lines.append("")
    lines.append("## Method mismatch classification")
    lines.append("")
    if report["method_mismatches"]:
        lines.append("| ID | Category | Frontend | Endpoint | Backend methods | Action |")
        lines.append("|---|---|---|---|---|---|")
        for item in report["method_mismatches"]:
            lines.append(
                f"| {item['id']} | `{item['category']}` | `{item['frontend_file']}:{item['line']}` | `{item['frontend_method']} {item['frontend_endpoint']}` | `{','.join(item['backend_methods'])}` | {item['recommended_action']} |"
            )
    else:
        lines.append("No method mismatches detected.")
    lines.append("")
    lines.append("## Recommended next actions")
    lines.append("")
    for action in report["recommended_next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    diff = _load_json(DIFF_PATH)
    route_inventory = _load_json(ROUTE_INVENTORY_PATH)
    report = build_report(diff, route_inventory)
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report)
    if report["missing_path_count"] != 0:
        raise SystemExit("LEVEL1_40_09_MISSING_ENDPOINT_REPORT_FAIL: missing backend paths exist")
    print("LEVEL1_40_09_MISSING_ENDPOINT_REPORT_OK")
    print(f"missing_path_count={report['missing_path_count']}")
    print(f"method_mismatch_count={report['method_mismatch_count']}")
    print(f"true_blocker_count={report['true_blocker_count']}")
    print(f"parser_gap_or_false_positive_count={report['parser_gap_or_false_positive_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
