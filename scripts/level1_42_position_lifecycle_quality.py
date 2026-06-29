#!/usr/bin/env python3
from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "backend/services/real_position_lifecycle_service.py",
    "backend/services/real_trade_service.py",
    "backend/routes/real_routes.py",
    "tests/unit/test_real_position_lifecycle.py",
    "docs/LEVEL1_42_POSITION_LIFECYCLE_FSM.md",
]
REQUIRED_MARKERS = {
    "backend/services/real_position_lifecycle_service.py": [
        "REAL_POSITION_STATUSES",
        "VALID_TRANSITIONS",
        "create_preview_position",
        "create_position_from_order_record",
        "detect_orphan_orders",
        "build_position_timeline",
        "archive_closed_position",
    ],
    "backend/routes/real_routes.py": [
        "/positions/lifecycle",
        "/positions/{position_id}/timeline",
        "/positions/orphans",
    ],
    "backend/services/real_trade_service.py": [
        "create_position_from_order_record",
        "create_preview_position",
        "build_real_position_timeline",
    ],
}
RUNTIME_FORBIDDEN = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
    "backend/runtime_backups",
]


def fail(message: str) -> None:
    print(f"LEVEL1_42_POSITION_LIFECYCLE_QUALITY_FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_files() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        fail(f"missing required files: {missing}")
    for rel, markers in REQUIRED_MARKERS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        absent = [marker for marker in markers if marker not in text]
        if absent:
            fail(f"{rel} missing markers {absent}")


def check_compile() -> None:
    for rel in ["backend/services/real_position_lifecycle_service.py", "backend/services/real_trade_service.py", "backend/routes/real_routes.py", "scripts/level1_42_position_lifecycle_quality.py"]:
        py_compile.compile(str(ROOT / rel), doraise=True)


def run_tests() -> None:
    cmd = [sys.executable, "-m", "pytest", "-q", "tests/unit/test_real_position_lifecycle.py"]
    result = subprocess.run(cmd, cwd=ROOT, env={**__import__('os').environ, "PYTHONPATH": "backend"}, text=True, capture_output=True, timeout=60)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        fail("position lifecycle tests failed")


def check_runtime_leaks() -> None:
    leaked = [rel for rel in RUNTIME_FORBIDDEN if (ROOT / rel).exists()]
    if leaked:
        fail(f"runtime leaks found: {leaked}")


def write_report() -> None:
    report = {
        "status": "ok",
        "level": "42",
        "package": "Real Position Lifecycle FSM",
        "completed_items": [
            "Position FSM schema",
            "Position state storage standard",
            "Planned to previewed transition",
            "Previewed to submitted transition",
            "Submitted to filled/open transition",
            "Partial fill state",
            "Cancel/reject states",
            "Closing state",
            "Closed state and history archive",
            "Orphan order detection",
            "Manual attention flag",
            "Position timeline API/UI payload",
            "Lifecycle audit completeness",
            "Lifecycle regression and quality gate",
        ],
        "required_statuses": "REAL_POSITION_STATUSES",
        "transition_contract": "VALID_TRANSITIONS",
        "tests": "tests/unit/test_real_position_lifecycle.py",
    }
    out = ROOT / "docs" / "LEVEL1_42_POSITION_LIFECYCLE_REPORT.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    check_files()
    check_compile()
    check_runtime_leaks()
    run_tests()
    write_report()
    print("LEVEL1_42_POSITION_LIFECYCLE_QUALITY_OK")


if __name__ == "__main__":
    main()
