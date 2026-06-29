#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "backend/services/real_pilot_service.py",
    "backend/routes/real_routes.py",
    "backend/services/summary_service.py",
    "frontend/js/pages/summary.js",
    "tests/unit/test_micro_pilot_controller.py",
    "tests/api/test_micro_pilot_routes.py",
]
MARKERS = {
    "backend/services/real_pilot_service.py": ["build_pilot_visibility", "validate_pilot_order_guard", "finalize_pilot_controller", "evidence_chain", "final_report"],
    "backend/routes/real_routes.py": ["/pilot/visibility", "/pilot/order-guard", "/pilot/final-report"],
    "backend/services/summary_service.py": ["attach_pilot_summary", "micro_pilot_controller"],
    "frontend/js/pages/summary.js": ["Micro Pilot", "Pilot status", "Auto lock"],
}
RUNTIME_FORBIDDEN = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
]


def fail(message: str):
    print(f"LEVEL1_45_MICRO_PILOT_CONTROLLER_QUALITY_FAIL: {message}")
    raise SystemExit(1)


def run(cmd: list[str], env: dict | None = None):
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        fail("command failed: " + " ".join(cmd))
    return result


def main():
    for rel in REQUIRED:
        if not (ROOT / rel).exists():
            fail(f"missing required file: {rel}")
    for rel, markers in MARKERS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                fail(f"missing marker {marker!r} in {rel}")
    leaks = [rel for rel in RUNTIME_FORBIDDEN if (ROOT / rel).exists()]
    if (ROOT / "backend/runtime_backups").exists():
        leaks.append("backend/runtime_backups")
    if leaks:
        fail("runtime leak: " + ", ".join(leaks))
    run([sys.executable, "-m", "compileall", "-q", "backend", "scripts", "tests"])
    if Path("frontend/js/pages/summary.js").exists():
        run(["node", "--check", "frontend/js/pages/summary.js"])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    env["HMTSTC_OFFLINE_QUALITY_CHECK"] = "1"
    run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_micro_pilot_controller.py", "tests/api/test_micro_pilot_routes.py"], env=env)
    report = {
        "status": "ok",
        "package": "level1_45_micro_pilot_controller",
        "required_files": REQUIRED,
        "runtime_leaks": [],
        "checks": ["compile", "summary_js_syntax", "pilot_unit_api_tests", "marker_contract"],
    }
    out = ROOT / "docs/LEVEL1_45_MICRO_PILOT_CONTROLLER_REPORT.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("LEVEL1_45_MICRO_PILOT_CONTROLLER_QUALITY_OK")


if __name__ == "__main__":
    main()
