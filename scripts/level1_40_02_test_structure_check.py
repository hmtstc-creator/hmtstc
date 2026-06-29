#!/usr/bin/env python3
"""Validate the standardized test directory structure for Level1 40.02."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRS = [
    "tests",
    "tests/unit",
    "tests/api",
    "tests/integration",
    "tests/fixtures",
    "tests/helpers",
]
REQUIRED_FILES = [
    "tests/README.md",
    "tests/__init__.py",
    "tests/unit/__init__.py",
    "tests/api/__init__.py",
    "tests/integration/__init__.py",
    "tests/helpers/__init__.py",
    "tests/helpers/fakes.py",
    "tests/unit/test_summary_service.py",
    "tests/api/test_summary_routes.py",
]
FORBIDDEN_RUNTIME_NAMES = {
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
}


def fail(message: str) -> None:
    print(f"LEVEL1_40_02_FAIL: {message}")
    sys.exit(1)


def main() -> None:
    missing_dirs = [path for path in REQUIRED_DIRS if not (ROOT / path).is_dir()]
    if missing_dirs:
        fail(f"missing directories: {missing_dirs}")

    missing_files = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing_files:
        fail(f"missing files: {missing_files}")

    runtime_leaks = [path for path in FORBIDDEN_RUNTIME_NAMES if (ROOT / path).exists()]
    if runtime_leaks:
        fail(f"runtime files included: {runtime_leaks}")

    readme = (ROOT / "tests/README.md").read_text(encoding="utf-8")
    for marker in ["tests/unit", "tests/api", "tests/integration", "live Binance", "runtime store"]:
        if marker not in readme:
            fail(f"tests/README.md missing marker: {marker}")

    print("LEVEL1_40_02_TEST_STRUCTURE_OK")


if __name__ == "__main__":
    main()
