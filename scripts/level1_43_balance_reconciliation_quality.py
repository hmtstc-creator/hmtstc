#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "backend/services/real_balance_service.py",
    "backend/services/real_trade_service.py",
    "backend/routes/real_routes.py",
    "tests/unit/test_balance_reconciliation.py",
    "docs/LEVEL1_43_BALANCE_RECONCILIATION.md",
]
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
MARKERS = {
    "backend/services/real_balance_service.py": [
        "capture_balance_snapshot",
        "compare_bot_exchange_state",
        "apply_mismatch_lock",
        "calculate_realized_pnl",
        "calculate_unrealized_pnl",
        "build_daily_weekly_pnl",
        "build_balance_reconciliation_full_report",
    ],
    "backend/routes/real_routes.py": [
        '"/reconciliation/report"',
        '"/reconciliation/pnl"',
        '"/reconciliation/snapshot"',
    ],
    "frontend/js/pages/summary.js": ["Balance / PnL / Reconciliation", "Mismatch lock"],
}


def run(cmd):
    result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        print(result.stdout)
        raise SystemExit(result.returncode)
    return result.stdout.strip()


def main():
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    if missing:
        raise SystemExit(f"missing files: {missing}")
    marker_errors = []
    for path, markers in MARKERS.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                marker_errors.append(f"{path}:{marker}")
    if marker_errors:
        raise SystemExit("missing markers: " + ", ".join(marker_errors))
    leaks = [p for p in RUNTIME_FORBIDDEN if (ROOT / p).exists()]
    if leaks:
        raise SystemExit(f"runtime leaks: {leaks}")
    run([sys.executable, "-m", "compileall", "-q", "backend", "scripts", "tests"])
    if subprocess.run(["bash", "-lc", "find frontend/js -name '*.js' -print0 | xargs -0 -I{} node --check {}"], cwd=ROOT).returncode != 0:
        raise SystemExit("frontend js syntax failed")
    run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_balance_reconciliation.py", "tests/api/test_balance_reconciliation_routes.py"])
    report = {
        "status": "ok",
        "checks": ["snapshots", "state_compare", "mismatch_lock", "realized_pnl", "unrealized_pnl", "fees", "daily_weekly_pnl", "summary_ui"],
    }
    out = ROOT / "docs" / "LEVEL1_43_BALANCE_RECONCILIATION_REPORT.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LEVEL1_43_BALANCE_RECONCILIATION_QUALITY_OK")


if __name__ == "__main__":
    main()
