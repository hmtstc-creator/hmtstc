from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "backend/services/audit_forensics_service.py",
    "backend/services/revision_28_service.py",
    "backend/routes/audit_routes.py",
    "backend/routes/quality_routes.py",
    "frontend/js/pages/logs.js",
    "frontend/js/pages/intelligence.js",
    "frontend/js/app/audit.js",
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
        path = ROOT / rel
        if not path.exists():
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
        "/api/audit/forensics",
        "/api/audit/timeline",
        "/api/quality/revision-28",
        "/api/quality/revision-28/audit-forensics",
        "/api/quality/revision-28/audit-search",
        "/api/quality/revision-28/audit-export",
        "/api/quality/revision-28/audit-immutability",
        "/api/quality/revision-28/audit-timeline",
    ]:
        if endpoint not in route_paths:
            fail(f"route missing {endpoint}")
    ok("revision 28 routes")

    from services.revision_28_service import build_revision_28_quality_report
    sample = {
        "audit": [
            {
                "time": "2026-05-20T10:00:00",
                "user": "ahmet",
                "role": "owner",
                "action": "real_order.attempt",
                "category": "trading",
                "severity": "critical",
                "result": "blocked",
                "endpoint": "/api/real/orders/place",
                "request_id": "req_demo",
                "correlation_id": "corr_demo",
                "before": {"locked": True},
                "after": {"locked": True},
            }
        ]
    }
    report = build_revision_28_quality_report(sample)
    if report.get("revision") != 28 or not report.get("audit_forensics"):
        fail("revision 28 report invalid")
    ok("revision 28 service")

    for rel in RUNTIME_FORBIDDEN:
        if (ROOT / rel).exists():
            fail(f"runtime file leaked: {rel}")
    ok("runtime leakage")

    print(json.dumps({"status": "ok", "revision": 28}, ensure_ascii=False))


if __name__ == "__main__":
    main()
