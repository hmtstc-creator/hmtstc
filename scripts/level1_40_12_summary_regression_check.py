from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "backend/services/summary_service.py",
    "backend/routes/summary_routes.py",
    "frontend/js/pages/summary.js",
    "tests/unit/test_summary_service.py",
    "tests/api/test_summary_routes.py",
]


def fail(message: str) -> None:
    print(f"LEVEL1_40_12_SUMMARY_REGRESSION_FAIL: {message}")
    sys.exit(1)


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        fail(f"command failed: {' '.join(cmd)}\n{proc.stdout}")


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).exists()]
    if missing:
        fail("missing required files: " + ", ".join(missing))

    service = (ROOT / "backend/services/summary_service.py").read_text(encoding="utf-8", errors="ignore")
    if "deepcopy(source_data)" not in service or "deepcopy(source_settings)" not in service:
        fail("summary service must protect source data/settings with deepcopy")

    tests = (ROOT / "tests/unit/test_summary_service.py").read_text(encoding="utf-8", errors="ignore")
    for marker in [
        "test_summary_does_not_mutate_input_payloads",
        "test_summary_normalizes_full_snapshot_values",
        "test_summary_handles_missing_sources_without_crashing",
    ]:
        if marker not in tests:
            fail(f"missing unit regression: {marker}")

    api_tests = (ROOT / "tests/api/test_summary_routes.py").read_text(encoding="utf-8", errors="ignore")
    if "test_summary_endpoint_is_get_only" not in api_tests:
        fail("missing get-only API regression")

    run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_summary_service.py", "tests/api/test_summary_routes.py"])
    print("LEVEL1_40_12_SUMMARY_REGRESSION_OK")


if __name__ == "__main__":
    main()
