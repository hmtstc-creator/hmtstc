#!/usr/bin/env python3
"""Level1 40.03 pytest configuration quality check.

Verifies that pytest is standardized for the HMTSTC quality foundation without
requiring live credentials, runtime store files or network access.
"""
from __future__ import annotations

import configparser
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTEST_INI = ROOT / "pytest.ini"
TEST_ROOT = ROOT / "tests"
REQUIRED_DIRS = [
    TEST_ROOT,
    TEST_ROOT / "unit",
    TEST_ROOT / "api",
    TEST_ROOT / "integration",
    TEST_ROOT / "fixtures",
    TEST_ROOT / "helpers",
]
REQUIRED_MARKERS = {"unit", "api", "integration", "smoke"}
RUNTIME_FORBIDDEN = {
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
}


def fail(message: str) -> None:
    print(f"LEVEL1_40_03_PYTEST_CONFIG_FAIL: {message}")
    raise SystemExit(1)


def read_pytest_config() -> configparser.ConfigParser:
    if not PYTEST_INI.exists():
        fail("pytest.ini is missing")
    parser = configparser.ConfigParser()
    parser.read(PYTEST_INI)
    if "pytest" not in parser:
        fail("pytest.ini must contain a [pytest] section")
    return parser


def main() -> int:
    for directory in REQUIRED_DIRS:
        if not directory.exists() or not directory.is_dir():
            fail(f"required test directory missing: {directory.relative_to(ROOT)}")

    parser = read_pytest_config()
    cfg = parser["pytest"]

    expected_pairs = {
        "testpaths": "tests",
        "python_files": "test_*.py",
        "python_classes": "Test*",
        "python_functions": "test_*",
        "pythonpath": "backend",
    }
    for key, expected in expected_pairs.items():
        value = cfg.get(key, "").strip()
        if value != expected:
            fail(f"{key} must be {expected!r}, got {value!r}")

    addopts = cfg.get("addopts", "")
    for required_opt in ["-ra", "--strict-markers", "--strict-config"]:
        if required_opt not in addopts.split():
            fail(f"addopts must include {required_opt}")

    marker_text = cfg.get("markers", "")
    found_markers = {line.split(":", 1)[0].strip() for line in marker_text.splitlines() if line.strip()}
    missing_markers = sorted(REQUIRED_MARKERS - found_markers)
    if missing_markers:
        fail(f"missing pytest markers: {missing_markers}")

    leaked = [path for path in sorted(RUNTIME_FORBIDDEN) if (ROOT / path).exists()]
    if leaked:
        fail(f"runtime files must not be packaged: {leaked}")

    print("LEVEL1_40_03_PYTEST_CONFIG_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
