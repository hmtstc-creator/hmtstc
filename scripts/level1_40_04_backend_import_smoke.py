#!/usr/bin/env python3
"""Level1 40.04 Backend import smoke check.

Validates that the FastAPI application can be imported from the packaged
backend without starting a server, that routes are registered, and that the
critical read-only endpoints added in recent revisions are present.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DOCS_DIR = ROOT / "docs"
REPORT_PATH = DOCS_DIR / "LEVEL1_40_04_BACKEND_IMPORT_SMOKE_REPORT.json"

REQUIRED_ROUTES = {
    "/health",
    "/health/ops",
    "/api/summary",
    "/api/real/readiness",
    "/api/quality/revision-37",
}

MIN_ROUTE_COUNT = 300
GENERATED_RUNTIME_FILES = {
    BACKEND_DIR / "settings_store.json",
    BACKEND_DIR / "shadow_store.json",
    BACKEND_DIR / "auth_store.json",
    BACKEND_DIR / "rule_store.json",
    BACKEND_DIR / "audit_store.json",
    BACKEND_DIR / "real_trade_store.json",
}



def _ensure_import_path() -> None:
    backend_path = str(BACKEND_DIR)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def _route_snapshot(routes: Iterable[object]) -> list[dict[str, object]]:
    snapshot: list[dict[str, object]] = []
    for route in routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        name = getattr(route, "name", None)
        if not path:
            continue
        method_list = sorted(m for m in (methods or []) if m not in {"HEAD"})
        snapshot.append({"path": path, "methods": method_list, "name": name})
    return sorted(snapshot, key=lambda item: (str(item["path"]), str(item["methods"])))



def _cleanup_generated_runtime_files(preexisting: set[Path]) -> list[str]:
    cleaned: list[str] = []
    for path in GENERATED_RUNTIME_FILES:
        if path in preexisting:
            continue
        if path.exists() and path.is_file():
            path.unlink()
            cleaned.append(str(path.relative_to(ROOT)))
    return sorted(cleaned)


def run_check() -> dict[str, object]:
    _ensure_import_path()
    preexisting_runtime = {path for path in GENERATED_RUNTIME_FILES if path.exists()}
    result: dict[str, object] = {
        "status": "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "backend_dir": str(BACKEND_DIR),
        "min_route_count": MIN_ROUTE_COUNT,
        "required_routes": sorted(REQUIRED_ROUTES),
        "errors": [],
    }

    try:
        main_module = importlib.import_module("main")
    except Exception as exc:  # pragma: no cover - script-level diagnostic
        result["errors"].append(f"main_import_failed: {type(exc).__name__}: {exc}")
        result["cleaned_generated_runtime_files"] = _cleanup_generated_runtime_files(preexisting_runtime)
        return result

    app = getattr(main_module, "app", None)
    if app is None:
        result["errors"].append("main.app missing")
        result["cleaned_generated_runtime_files"] = _cleanup_generated_runtime_files(preexisting_runtime)
        return result

    routes = _route_snapshot(getattr(app, "routes", []))
    route_paths = {str(item["path"]) for item in routes}
    missing_routes = sorted(REQUIRED_ROUTES - route_paths)
    route_count = len(routes)

    result.update(
        {
            "app_type": type(app).__name__,
            "route_count": route_count,
            "missing_routes": missing_routes,
            "routes_sample": routes[:25],
        }
    )

    if route_count < MIN_ROUTE_COUNT:
        result["errors"].append(f"route_count_below_minimum: {route_count} < {MIN_ROUTE_COUNT}")
    if missing_routes:
        result["errors"].append(f"missing_required_routes: {', '.join(missing_routes)}")

    result["cleaned_generated_runtime_files"] = _cleanup_generated_runtime_files(preexisting_runtime)

    if not result["errors"]:
        result["status"] = "ok"
    return result


def main() -> int:
    result = run_check()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if result["status"] != "ok":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    print("LEVEL1_40_04_BACKEND_IMPORT_SMOKE_OK")
    print(f"route_count={result['route_count']}")
    print(f"report={REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
