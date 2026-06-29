#!/usr/bin/env python3
from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "backend/services/replay_explainability_service.py",
    "backend/services/reports_service.py",
    "backend/services/execution_calibration_service.py",
    "backend/routes/model_routes.py",
    "backend/routes/quality_routes.py",
    "tests/unit/test_reports_replay_explainability.py",
    "tests/api/test_reports_replay_routes.py",
]
REQUIRED_MARKERS = {
    "backend/services/replay_explainability_service.py": [
        "build_report_archive_schema",
        "build_model_ranking_delta",
        "build_reports_replay_final",
        "why_profit_loss",
        "build_execution_calibration_report",
    ],
    "backend/services/reports_service.py": [
        "archive_standard_report_set",
        "execution_calibration_score",
        "paper_vs_dry_run_quality_delta",
    ],
    "backend/routes/model_routes.py": [
        "/reports/archive/schema",
        "/reports/archive/daily",
        "/reports/archive/weekly-monthly",
        "/reports/execution-calibration",
        "/reports/why-open",
        "/reports/why-close",
        "/reports/why-profit-loss",
        "/reports/export-snapshot",
    ],
    "backend/routes/quality_routes.py": ["/level1-46/reports-replay-explainability"],
}
RUNTIME_LEAKS = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
]


def fail(message: str) -> None:
    print(f"LEVEL1_46_REPORTS_REPLAY_QUALITY_FAIL: {message}")
    raise SystemExit(1)


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
    if result.returncode != 0:
        fail(f"command failed {' '.join(cmd)}\n{result.stdout}")
    return result.stdout


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        fail(f"missing files: {missing}")
    for rel in REQUIRED_FILES:
        if rel.endswith(".py"):
            py_compile.compile(str(ROOT / rel), doraise=True)
    for rel, markers in REQUIRED_MARKERS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        absent = [m for m in markers if m not in text]
        if absent:
            fail(f"{rel} missing markers {absent}")
    leaks = [rel for rel in RUNTIME_LEAKS if (ROOT / rel).exists()]
    if leaks:
        fail(f"runtime leaks present: {leaks}")
    run([sys.executable, "-m", "compileall", "-q", "backend", "scripts", "tests"])
    run(["bash", "-lc", "find frontend/js -name '*.js' -print0 | xargs -0 -I{} node --check '{}' "])
    run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_reports_replay_explainability.py", "tests/api/test_reports_replay_routes.py"])
    route_count = run([sys.executable, "-c", "import sys; sys.path.insert(0,'backend'); from main import app; print(len(app.routes))"]).strip().splitlines()[-1]
    report = {
        "status": "ok",
        "route_count": int(route_count),
        "required_files": REQUIRED_FILES,
        "runtime_leaks": [],
        "checks": [
            "archive_schema",
            "daily_weekly_monthly_archives",
            "period_compare",
            "model_ranking_delta",
            "replay_index",
            "why_open_close_profit_loss",
            "execution_calibration",
            "paper_dry_run_real_drift",
            "export_snapshot",
        ],
    }
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "LEVEL1_46_REPORTS_REPLAY_QUALITY_REPORT.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("LEVEL1_46_REPORTS_REPLAY_QUALITY_OK")
    print(f"route_count={route_count}")


if __name__ == "__main__":
    main()
