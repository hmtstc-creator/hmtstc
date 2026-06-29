#!/usr/bin/env python3
"""Level1 40.06 API route inventory.

Builds a deterministic inventory of all FastAPI routes registered by backend/main.py.
The inventory is read-only and is intended to feed later API contract checks.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DOCS_DIR = ROOT / "docs"
REPORT_PATH = DOCS_DIR / "LEVEL1_40_06_API_ROUTE_INVENTORY.json"
MARKDOWN_PATH = DOCS_DIR / "LEVEL1_40_06_API_ROUTE_INVENTORY.md"

GENERATED_RUNTIME_FILES = [
    BACKEND_DIR / "settings_store.json",
    BACKEND_DIR / "shadow_store.json",
    BACKEND_DIR / "auth_store.json",
    BACKEND_DIR / "rule_store.json",
    BACKEND_DIR / "audit_store.json",
    BACKEND_DIR / "real_trade_store.json",
]

REQUIRED_PATHS = {
    "/health",
    "/health/ops",
    "/api/summary",
    "/api/real/readiness",
    "/api/quality/revision-37",
}


def _cleanup_generated_runtime_files(preexisting: set[Path]) -> None:
    for path in GENERATED_RUNTIME_FILES:
        if path in preexisting:
            continue
        if path.exists() and path.is_file():
            path.unlink()


def _ensure_backend_import_path() -> None:
    backend = str(BACKEND_DIR)
    if backend not in sys.path:
        sys.path.insert(0, backend)


def _route_module(route: Any) -> str:
    endpoint = getattr(route, "endpoint", None)
    return getattr(endpoint, "__module__", "") if endpoint else ""


def _route_name(route: Any) -> str:
    return str(getattr(route, "name", "") or "")


def _route_methods(route: Any) -> list[str]:
    methods = getattr(route, "methods", None) or []
    return sorted(method for method in methods if method not in {"HEAD", "OPTIONS"})


def _route_tags(route: Any) -> list[str]:
    tags = getattr(route, "tags", None) or []
    return [str(tag) for tag in tags]


def _route_entry(route: Any) -> dict[str, Any] | None:
    path = getattr(route, "path", None)
    if not path:
        return None
    methods = _route_methods(route)
    if not methods:
        return None
    module = _route_module(route)
    return {
        "path": str(path),
        "methods": methods,
        "name": _route_name(route),
        "endpoint_module": module,
        "tags": _route_tags(route),
    }


def build_inventory() -> dict[str, Any]:
    preexisting = {path for path in GENERATED_RUNTIME_FILES if path.exists()}
    _ensure_backend_import_path()
    try:
        from main import app  # type: ignore

        entries = [_route_entry(route) for route in app.routes]
        routes = sorted([entry for entry in entries if entry], key=lambda item: (item["path"], ",".join(item["methods"]), item["name"]))
    finally:
        _cleanup_generated_runtime_files(preexisting)

    method_counter: Counter[str] = Counter()
    prefix_counter: Counter[str] = Counter()
    module_counter: Counter[str] = Counter()
    duplicate_keys: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for route in routes:
        for method in route["methods"]:
            method_counter[method] += 1
            duplicate_keys[f"{method} {route['path']}"].append(route)
        parts = [part for part in route["path"].split("/") if part]
        prefix = f"/{parts[0]}" if parts else "/"
        if prefix == "/api" and len(parts) > 1:
            prefix = f"/api/{parts[1]}"
        prefix_counter[prefix] += 1
        module_counter[route["endpoint_module"] or "unknown"] += 1

    duplicate_routes = {
        key: value for key, value in sorted(duplicate_keys.items()) if len(value) > 1
    }
    route_paths = {route["path"] for route in routes}
    missing_required_paths = sorted(REQUIRED_PATHS - route_paths)

    inventory: dict[str, Any] = {
        "status": "ok" if not missing_required_paths and not duplicate_routes else "review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "route_count": len(routes),
        "method_count": dict(sorted(method_counter.items())),
        "prefix_count": dict(sorted(prefix_counter.items())),
        "module_count": dict(sorted(module_counter.items())),
        "required_paths": sorted(REQUIRED_PATHS),
        "missing_required_paths": missing_required_paths,
        "duplicate_routes": duplicate_routes,
        "routes": routes,
    }
    return inventory


def write_markdown(inventory: dict[str, Any], path: Path = MARKDOWN_PATH) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.06 API Route Inventory")
    lines.append("")
    lines.append("Bu rapor, FastAPI uygulamasında kayıtlı route listesini read-only şekilde çıkarır.")
    lines.append("")
    lines.append(f"- Status: `{inventory['status']}`")
    lines.append(f"- Route count: `{inventory['route_count']}`")
    lines.append(f"- Generated at: `{inventory['generated_at']}`")
    lines.append("")
    lines.append("## Method count")
    lines.append("")
    for method, count in inventory["method_count"].items():
        lines.append(f"- `{method}`: {count}")
    lines.append("")
    lines.append("## Prefix count")
    lines.append("")
    for prefix, count in inventory["prefix_count"].items():
        lines.append(f"- `{prefix}`: {count}")
    lines.append("")
    lines.append("## Required paths")
    lines.append("")
    for required in inventory["required_paths"]:
        marker = "OK" if required not in inventory["missing_required_paths"] else "MISSING"
        lines.append(f"- `{required}` — {marker}")
    lines.append("")
    lines.append("## Route list")
    lines.append("")
    lines.append("| Method | Path | Name | Module |")
    lines.append("|---|---|---|---|")
    for route in inventory["routes"]:
        methods = ", ".join(route["methods"])
        lines.append(f"| {methods} | `{route['path']}` | `{route['name']}` | `{route['endpoint_module']}` |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build FastAPI route inventory for HMTSTC.")
    parser.add_argument("--json", dest="json_path", default=str(REPORT_PATH), help="JSON output path.")
    parser.add_argument("--markdown", dest="markdown_path", default=str(MARKDOWN_PATH), help="Markdown output path.")
    args = parser.parse_args(argv)

    inventory = build_inventory()
    json_path = Path(args.json_path)
    if not json_path.is_absolute():
        json_path = ROOT / json_path
    markdown_path = Path(args.markdown_path)
    if not markdown_path.is_absolute():
        markdown_path = ROOT / markdown_path

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(inventory, markdown_path)

    if inventory["status"] != "ok":
        print(json.dumps({
            "status": inventory["status"],
            "missing_required_paths": inventory["missing_required_paths"],
            "duplicate_routes": list(inventory["duplicate_routes"].keys()),
        }, indent=2, ensure_ascii=False))
        return 1

    print("LEVEL1_40_06_API_ROUTE_INVENTORY_OK")
    print(f"route_count={inventory['route_count']}")
    print(f"json={json_path.relative_to(ROOT) if json_path.is_relative_to(ROOT) else json_path}")
    print(f"markdown={markdown_path.relative_to(ROOT) if markdown_path.is_relative_to(ROOT) else markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
