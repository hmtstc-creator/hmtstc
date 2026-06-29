#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FORBIDDEN = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
]
REQUIRED_FILES = [
    "backend/services/emergency_recovery_service.py",
    "backend/routes/real_routes.py",
    "backend/services/summary_service.py",
    "frontend/js/pages/summary.js",
    "tests/unit/test_emergency_close_recovery.py",
    "tests/api/test_emergency_close_routes.py",
]
REQUIRED_MARKERS = {
    "backend/services/emergency_recovery_service.py": [
        "build_emergency_close_preview_final",
        "execute_emergency_close",
        "build_emergency_visibility",
        "payload_bound_token",
        "no_auto_start_after_recovery",
    ],
    "backend/routes/real_routes.py": [
        '/emergency/close-preview',
        '/emergency/close',
        '/emergency/visibility',
    ],
    "frontend/js/pages/summary.js": [
        "Emergency Close & Recovery",
        "Last close",
        "No auto-start",
    ],
}


def fail(msg: str) -> None:
    print(f"LEVEL1_44_EMERGENCY_CLOSE_QUALITY_FAIL: {msg}")
    raise SystemExit(1)


def main() -> int:
    missing = [p for p in REQUIRED_FILES if not (ROOT / p).exists()]
    if missing:
        fail(f"missing_files={missing}")
    runtime = [p for p in RUNTIME_FORBIDDEN if (ROOT / p).exists()]
    runtime += ["backend/runtime_backups"] if (ROOT / "backend/runtime_backups").exists() else []
    if runtime:
        fail(f"runtime_leaks={runtime}")
    marker_issues = []
    for rel, markers in REQUIRED_MARKERS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                marker_issues.append({"file": rel, "marker": marker})
    if marker_issues:
        fail(f"marker_issues={marker_issues}")
    sys.path.insert(0, str(ROOT / "backend"))
    from main import app  # type: ignore
    paths = {getattr(route, "path", "") for route in app.routes}
    required_paths = {
        "/api/real/emergency/close-preview",
        "/api/real/emergency/close",
        "/api/real/emergency/visibility",
        "/api/real/emergency/recovery",
        "/api/real/emergency/checklist",
    }
    missing_paths = sorted(required_paths - paths)
    if missing_paths:
        fail(f"missing_paths={missing_paths}")
    report = {
        "status": "ok",
        "required_files": REQUIRED_FILES,
        "required_paths": sorted(required_paths),
        "route_count": len(app.routes),
        "runtime_leaks": [],
    }
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "LEVEL1_44_EMERGENCY_CLOSE_REPORT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("LEVEL1_44_EMERGENCY_CLOSE_QUALITY_OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
