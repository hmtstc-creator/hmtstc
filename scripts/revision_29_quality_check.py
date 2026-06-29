from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "backend/services/observability_service.py",
    "backend/services/revision_29_service.py",
    "backend/routes/observability_routes.py",
    "backend/routes/quality_routes.py",
    "frontend/js/pages/dashboard.js",
    "frontend/js/pages/intelligence.js",
    "frontend/js/app/api.js",
]

RUNTIME_FORBIDDEN = [
    "backend/.env",
    "backend/auth_store.json",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/runtime_backups",
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def main() -> None:
    for rel in REQUIRED:
        if not (ROOT / rel).exists():
            fail(f"missing {rel}")
        ok(f"exists {rel}")

    for py in (ROOT / "backend").rglob("*.py"):
        if "__pycache__" not in str(py):
            py_compile.compile(str(py), doraise=True)
    ok("python compile")

    for js in (ROOT / "frontend" / "js").rglob("*.js"):
        subprocess.run(["node", "--check", str(js)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ok("frontend js syntax")

    sys.path.insert(0, str(ROOT / "backend"))
    from main import app  # noqa: F401
    ok("backend app import")

    route_paths = {getattr(route, "path", "") for route in app.routes}
    for endpoint in [
        "/api/observability/summary",
        "/api/observability/latency",
        "/api/observability/endpoint-errors",
        "/api/observability/stale",
        "/api/observability/deploy",
        "/api/quality/revision-29",
        "/api/quality/revision-29/latency",
        "/api/quality/revision-29/endpoint-errors",
        "/api/quality/revision-29/stale-data",
        "/api/quality/revision-29/deploy-health",
        "/api/quality/revision-29/ui",
    ]:
        if endpoint not in route_paths:
            fail(f"route missing {endpoint}")
    ok("revision 29 routes")

    from services.revision_29_service import build_revision_29_quality_report
    sample = {
        "last_scan": {"time": "2026-05-20T10:00:00+00:00", "latency_ms": 280},
        "last_tick": "2026-05-20T10:00:00+00:00",
        "health_history": [{"problems": [], "duration_ms": 120}],
        "bot_loop_traces": [{"duration_ms": 150}],
        "audit": [{"endpoint": "/api/test", "result": "ok", "severity": "info"}],
    }
    report = build_revision_29_quality_report(sample, {})
    if report.get("revision") != 29 or not report.get("summary"):
        fail("revision 29 report invalid")
    ok("revision 29 service")

    for rel in RUNTIME_FORBIDDEN:
        if (ROOT / rel).exists():
            fail(f"runtime file leaked: {rel}")
    ok("runtime leakage")

    print(json.dumps({"status": "ok", "revision": 29}, ensure_ascii=False))


if __name__ == "__main__":
    main()
