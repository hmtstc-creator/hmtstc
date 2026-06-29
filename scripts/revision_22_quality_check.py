from __future__ import annotations

import os
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "backend/services/real_pilot_service.py",
    "backend/services/revision_22_service.py",
    "backend/routes/real_routes.py",
    "backend/routes/quality_routes.py",
    "frontend/js/app/realTrade.js",
    "frontend/js/pages/dashboard.js",
]
FORBIDDEN = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
]


def fail(msg: str):
    print(f"ERR {msg}")
    raise SystemExit(1)


def main():
    for rel in REQUIRED:
        if not (ROOT / rel).exists():
            fail(f"missing required file: {rel}")
    for rel in FORBIDDEN:
        if (ROOT / rel).exists():
            fail(f"runtime file leaked: {rel}")

    py_files = list((ROOT / "backend").rglob("*.py")) + list((ROOT / "scripts").glob("revision_22_quality_check.py"))
    for path in py_files:
        py_compile.compile(str(path), doraise=True)

    real_routes = (ROOT / "backend/routes/real_routes.py").read_text(encoding="utf-8")
    for token in ["/pilot/readiness", "/pilot/start", "/pilot/stop", "/pilot/report"]:
        if token not in real_routes:
            fail(f"real route missing {token}")

    quality_routes = (ROOT / "backend/routes/quality_routes.py").read_text(encoding="utf-8")
    for token in ["revision-22", "pilot-config", "pilot-lifecycle", "pilot-safety", "pilot-report", "pilot-ui"]:
        if token not in quality_routes:
            fail(f"quality route missing {token}")

    dashboard = (ROOT / "frontend/js/pages/dashboard.js").read_text(encoding="utf-8")
    for token in ["Mikro Pilot", "startRealPilot", "stopRealPilot", "refreshPilotReport"]:
        if token not in dashboard:
            fail(f"dashboard missing {token}")

    real_trade = (ROOT / "frontend/js/app/realTrade.js").read_text(encoding="utf-8")
    for token in ["startRealPilot", "stopRealPilot", "/api/real/pilot/start", "/api/real/pilot/report"]:
        if token not in real_trade:
            fail(f"realTrade.js missing {token}")

    print("REVISION_22_QUALITY_OK")


if __name__ == "__main__":
    main()
