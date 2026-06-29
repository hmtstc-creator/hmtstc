#!/usr/bin/env python3
"""Level1 40.08 API contract diff.

Compares the frontend API inventory generated in 40.07 with the backend
FastAPI route inventory generated in 40.06. The script is deliberately
read-only: it does not change application state, and it produces JSON/Markdown
reports that feed the next step, `missing endpoint report`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
BACKEND_INVENTORY = DOCS_DIR / "LEVEL1_40_06_API_ROUTE_INVENTORY.json"
FRONTEND_INVENTORY = DOCS_DIR / "LEVEL1_40_07_FRONTEND_API_INVENTORY.json"
REPORT_PATH = DOCS_DIR / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
MARKDOWN_PATH = DOCS_DIR / "LEVEL1_40_08_API_CONTRACT_DIFF.md"

RUNTIME_FORBIDDEN = [
    ROOT / "backend" / ".env",
    ROOT / "backend" / "binance_credentials_store.json",
    ROOT / "backend" / "settings_store.json",
    ROOT / "backend" / "shadow_store.json",
    ROOT / "backend" / "auth_store.json",
    ROOT / "backend" / "rule_store.json",
    ROOT / "backend" / "audit_store.json",
    ROOT / "backend" / "real_trade_store.json",
    ROOT / "backend" / "runtime_backups",
]

CRITICAL_FRONTEND_PATHS = {
    "/api/real/readiness",
    "/health",
    "/health/ops",
    "/api/quality/revision-37",
}

IGNORED_FRONTEND_BASE_PATHS = {
    # Browser-only static/UI placeholders can be added here if future scans need
    # known false-positive suppression. Keep empty by default for transparency.
}


@dataclass(frozen=True)
class BackendRoute:
    method: str
    path: str
    name: str
    module: str
    regex: re.Pattern[str]
    normalized: str


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/") if path.is_relative_to(ROOT) else str(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing inventory: {_relative(path)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _is_git_tracked(path: Path) -> bool:
    result = _run_git(["ls-files", "--", _relative(path)])
    return bool(result.stdout.strip())


def _is_git_ignored(path: Path) -> bool:
    result = _run_git(["check-ignore", "-q", "--", _relative(path)])
    return result.returncode == 0


def _runtime_policy() -> dict[str, list[str]]:
    tracked: list[str] = []
    unignored: list[str] = []
    allowed: list[str] = []

    for path in RUNTIME_FORBIDDEN:
        if not path.exists():
            continue
        rel = _relative(path)
        is_tracked = _is_git_tracked(path)
        is_ignored = _is_git_ignored(path)
        if is_tracked:
            tracked.append(rel)
        elif not is_ignored:
            unignored.append(rel)
        else:
            allowed.append(rel)

    return {
        "tracked_runtime_stores": sorted(tracked),
        "unignored_runtime_stores": sorted(unignored),
        "allowed_ignored_runtime_stores": sorted(allowed),
    }


def _normalize_endpoint(path: str) -> str:
    endpoint = str(path or "").strip()
    endpoint = endpoint.split("?", 1)[0]
    endpoint = endpoint.replace("&amp;", "&")
    endpoint = re.sub(r"/+$", "", endpoint) if endpoint != "/" else endpoint
    if endpoint == "":
        endpoint = "/"
    return endpoint


def _route_to_regex(path: str) -> re.Pattern[str]:
    normalized = _normalize_endpoint(path)
    parts = normalized.split("/")
    regex_parts: list[str] = []
    for part in parts:
        if not part:
            regex_parts.append("")
            continue
        if re.fullmatch(r"\{[^/{}]+\}", part):
            regex_parts.append(r"[^/]+")
        else:
            regex_parts.append(re.escape(part))
    pattern = "^" + "/".join(regex_parts) + "/?$"
    return re.compile(pattern)


def _frontend_to_regex(path: str) -> re.Pattern[str]:
    normalized = _normalize_endpoint(path)
    parts = normalized.split("/")
    regex_parts: list[str] = []
    for part in parts:
        if not part:
            regex_parts.append("")
            continue
        if part in {"{dynamic}", "{id}", "{symbol}", "{user}"} or "{dynamic}" in part:
            regex_parts.append(r"[^/]+")
        else:
            regex_parts.append(re.escape(part))
    pattern = "^" + "/".join(regex_parts) + "/?$"
    return re.compile(pattern)


def _backend_routes(backend_inventory: dict[str, Any]) -> list[BackendRoute]:
    routes: list[BackendRoute] = []
    for route in backend_inventory.get("routes", []):
        path = _normalize_endpoint(route.get("path", ""))
        if not path:
            continue
        for method in route.get("methods", []):
            method_upper = str(method).upper()
            routes.append(BackendRoute(
                method=method_upper,
                path=path,
                name=str(route.get("name", "")),
                module=str(route.get("endpoint_module", "")),
                regex=_route_to_regex(path),
                normalized=path,
            ))
    return sorted(routes, key=lambda item: (item.method, item.path, item.name))


def _matches_backend(frontend_path: str, method: str, backend_routes: list[BackendRoute]) -> tuple[list[BackendRoute], list[BackendRoute]]:
    normalized = _normalize_endpoint(frontend_path)
    method = method.upper()
    path_matches: list[BackendRoute] = []
    method_matches: list[BackendRoute] = []

    for route in backend_routes:
        # First try backend template route matching against frontend literal/dynamic path.
        backend_pattern_matches = bool(route.regex.match(normalized))
        # Also try a frontend dynamic pattern against backend route templates. This helps
        # when frontend calls `/foo/{dynamic}` and backend has `/foo/{item_id}`.
        frontend_pattern_matches = bool(_frontend_to_regex(normalized).match(route.path))
        if backend_pattern_matches or frontend_pattern_matches:
            path_matches.append(route)
            if route.method == method:
                method_matches.append(route)
    return path_matches, method_matches


def build_contract_diff(
    backend_inventory_path: Path = BACKEND_INVENTORY,
    frontend_inventory_path: Path = FRONTEND_INVENTORY,
) -> dict[str, Any]:
    backend_inventory = _load_json(backend_inventory_path)
    frontend_inventory = _load_json(frontend_inventory_path)
    backend_routes = _backend_routes(backend_inventory)
    frontend_calls = frontend_inventory.get("calls", [])

    matched: list[dict[str, Any]] = []
    missing_paths: list[dict[str, Any]] = []
    method_mismatches: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []

    for call in sorted(frontend_calls, key=lambda item: (item.get("file", ""), item.get("line", 0), item.get("endpoint", ""))):
        endpoint = _normalize_endpoint(call.get("base_path") or call.get("endpoint", ""))
        method = str(call.get("method", "GET")).upper()
        if endpoint in IGNORED_FRONTEND_BASE_PATHS:
            ignored.append({**call, "reason": "allowlisted_false_positive"})
            continue
        path_matches, method_matches = _matches_backend(endpoint, method, backend_routes)
        if method_matches:
            matched.append({
                "frontend": call,
                "backend": [{"method": route.method, "path": route.path, "name": route.name, "module": route.module} for route in method_matches],
                "match_type": "method_and_path",
            })
        elif path_matches:
            method_mismatches.append({
                "frontend": call,
                "available_backend_methods": sorted({route.method for route in path_matches}),
                "backend_paths": sorted({route.path for route in path_matches}),
            })
        else:
            missing_paths.append({"frontend": call})

    backend_keys = {(route.method, route.path) for route in backend_routes}
    frontend_keys = {(_normalize_endpoint(call.get("base_path") or call.get("endpoint", "")), str(call.get("method", "GET")).upper()) for call in frontend_calls}
    unused_backend_routes = [
        {"method": route.method, "path": route.path, "name": route.name, "module": route.module}
        for route in backend_routes
        if (route.method, route.path) not in {(method, path) for path, method in frontend_keys}
        and route.path.startswith(("/api", "/health"))
    ]

    critical_missing = [
        item for item in missing_paths
        if _normalize_endpoint(item["frontend"].get("base_path") or item["frontend"].get("endpoint", "")) in CRITICAL_FRONTEND_PATHS
    ]
    runtime_policy = _runtime_policy()
    runtime_leaks = runtime_policy["tracked_runtime_stores"]
    missing_by_path: Counter[str] = Counter(_normalize_endpoint(item["frontend"].get("base_path") or item["frontend"].get("endpoint", "")) for item in missing_paths)
    mismatch_by_path: Counter[str] = Counter(_normalize_endpoint(item["frontend"].get("base_path") or item["frontend"].get("endpoint", "")) for item in method_mismatches)
    missing_by_file: Counter[str] = Counter(item["frontend"].get("file", "unknown") for item in missing_paths)
    mismatch_by_file: Counter[str] = Counter(item["frontend"].get("file", "unknown") for item in method_mismatches)

    review_required = bool(missing_paths or method_mismatches)
    fatal = bool(critical_missing or runtime_policy["tracked_runtime_stores"] or runtime_policy["unignored_runtime_stores"])
    report: dict[str, Any] = {
        "status": "fail" if fatal else ("review" if review_required else "ok"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend_inventory": _relative(backend_inventory_path),
        "frontend_inventory": _relative(frontend_inventory_path),
        "backend_route_count": backend_inventory.get("route_count", len(backend_routes)),
        "frontend_call_count": frontend_inventory.get("call_count", len(frontend_calls)),
        "matched_call_count": len(matched),
        "missing_path_count": len(missing_paths),
        "method_mismatch_count": len(method_mismatches),
        "ignored_call_count": len(ignored),
        "unused_backend_api_route_count": len(unused_backend_routes),
        "critical_frontend_paths": sorted(CRITICAL_FRONTEND_PATHS),
        "critical_missing": critical_missing,
        "runtime_policy": runtime_policy,
        "runtime_leaks": runtime_leaks,
        "top_missing_paths": dict(missing_by_path.most_common(50)),
        "top_method_mismatches": dict(mismatch_by_path.most_common(50)),
        "missing_by_file": dict(missing_by_file.most_common()),
        "method_mismatch_by_file": dict(mismatch_by_file.most_common()),
        "missing_paths": missing_paths,
        "method_mismatches": method_mismatches,
        "matched_samples": matched[:100],
        "unused_backend_api_routes": unused_backend_routes,
        "ignored_calls": ignored,
        "notes": [
            "This script performs static contract review only; it does not fix endpoints.",
            "A review status is expected until the following missing endpoint report step classifies and resolves gaps.",
            "Critical frontend paths must not be missing when called: /api/real/readiness, /health, /health/ops, /api/quality/revision-37.",
            "/api/summary is a backend critical route, but it is not a required frontend call.",
        ],
    }
    return report


def write_markdown(report: dict[str, Any], path: Path = MARKDOWN_PATH) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.08 API Contract Diff")
    lines.append("")
    lines.append("Bu rapor, frontend API çağrıları ile backend FastAPI route envanterini karşılaştırır.")
    lines.append("Sonraki adım olan `Eksik endpoint raporu` için sınıflandırılmış fark üretir.")
    lines.append("")
    lines.append(f"- Status: `{report.get('status')}`")
    lines.append(f"- Generated at: `{report.get('generated_at')}`")
    lines.append(f"- Backend route count: `{report.get('backend_route_count')}`")
    lines.append(f"- Frontend call count: `{report.get('frontend_call_count')}`")
    lines.append(f"- Matched call count: `{report.get('matched_call_count')}`")
    lines.append(f"- Missing path count: `{report.get('missing_path_count')}`")
    lines.append(f"- Method mismatch count: `{report.get('method_mismatch_count')}`")
    lines.append(f"- Critical missing count: `{len(report.get('critical_missing', []))}`")
    lines.append(f"- Runtime leaks: `{len(report.get('runtime_leaks', []))}`")
    runtime_policy = report.get("runtime_policy", {})
    lines.append(f"- Tracked runtime stores: `{len(runtime_policy.get('tracked_runtime_stores', []))}`")
    lines.append(f"- Unignored runtime stores: `{len(runtime_policy.get('unignored_runtime_stores', []))}`")
    lines.append(f"- Allowed ignored runtime stores: `{len(runtime_policy.get('allowed_ignored_runtime_stores', []))}`")
    lines.append("")

    lines.append("## Critical frontend paths")
    lines.append("")
    critical_missing_paths = {_normalize_endpoint(item.get("frontend", {}).get("base_path") or item.get("frontend", {}).get("endpoint", "")) for item in report.get("critical_missing", [])}
    for critical in report.get("critical_frontend_paths", []):
        marker = "MISSING" if critical in critical_missing_paths else "OK"
        lines.append(f"- `{critical}` — {marker}")
    lines.append("")

    lines.append("## Top missing paths")
    lines.append("")
    if report.get("top_missing_paths"):
        lines.append("| Path | Count |")
        lines.append("|---|---:|")
        for item, count in report.get("top_missing_paths", {}).items():
            lines.append(f"| `{item}` | {count} |")
    else:
        lines.append("No missing frontend paths detected.")
    lines.append("")

    lines.append("## Top method mismatches")
    lines.append("")
    if report.get("top_method_mismatches"):
        lines.append("| Path | Count |")
        lines.append("|---|---:|")
        for item, count in report.get("top_method_mismatches", {}).items():
            lines.append(f"| `{item}` | {count} |")
    else:
        lines.append("No method mismatches detected.")
    lines.append("")

    lines.append("## Missing by file")
    lines.append("")
    if report.get("missing_by_file"):
        lines.append("| File | Count |")
        lines.append("|---|---:|")
        for item, count in report.get("missing_by_file", {}).items():
            lines.append(f"| `{item}` | {count} |")
    else:
        lines.append("No missing-path source files.")
    lines.append("")

    lines.append("## Contract notes")
    lines.append("")
    for note in report.get("notes", []):
        lines.append(f"- {note}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare frontend API calls with backend FastAPI routes.")
    parser.add_argument("--backend", default=str(BACKEND_INVENTORY), help="Backend route inventory JSON path.")
    parser.add_argument("--frontend", default=str(FRONTEND_INVENTORY), help="Frontend API inventory JSON path.")
    parser.add_argument("--json", dest="json_path", default=str(REPORT_PATH), help="JSON output path.")
    parser.add_argument("--markdown", dest="markdown_path", default=str(MARKDOWN_PATH), help="Markdown output path.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero for review-level mismatches, not only fatal critical misses.")
    args = parser.parse_args(argv)

    try:
        report = build_contract_diff(Path(args.backend), Path(args.frontend))
    except Exception as exc:  # keep the CLI useful for CI logs
        print(json.dumps({"status": "fail", "error": str(exc)}, indent=2, ensure_ascii=False))
        return 1

    json_path = Path(args.json_path)
    if not json_path.is_absolute():
        json_path = ROOT / json_path
    markdown_path = Path(args.markdown_path)
    if not markdown_path.is_absolute():
        markdown_path = ROOT / markdown_path

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report, markdown_path)

    print("LEVEL1_40_08_API_CONTRACT_DIFF_OK")
    print(f"status={report['status']}")
    print(f"matched_call_count={report['matched_call_count']}")
    print(f"missing_path_count={report['missing_path_count']}")
    print(f"method_mismatch_count={report['method_mismatch_count']}")
    print(f"json={_relative(json_path)}")
    print(f"markdown={_relative(markdown_path)}")

    if report["status"] == "fail" or (args.strict and report["status"] != "ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
