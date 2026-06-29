#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "LEVEL1_41_REAL_ORDER_SAFETY_FINAL_REPORT.json"
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
REQUIRED = [
    "backend/services/real_trade_state_service.py",
    "backend/services/real_trade_service.py",
    "backend/services/binance_service.py",
    "backend/services/real_order_safety_final_service.py",
    "tests/unit/test_real_order_safety_final.py",
]
REQUIRED_MARKERS = {
    "backend/services/real_trade_state_service.py": ["payload_hash", "confirmation_token_user_mismatch", "confirmation_token_payload_hash_mismatch", "confirmation_token_used"],
    "backend/services/real_trade_service.py": ["payload_snapshot", "blocker_matrix", "_audit_meta_for_order", "dry_run_active_real_place_blocked"],
    "backend/services/binance_service.py": ["MARKET_LOT_SIZE", "PRICE_FILTER", "map_binance_error", "filter_checks"],
    "backend/services/real_order_safety_final_service.py": ["REAL_SAFETY_BLOCKER_GROUPS", "preview_required_before_place", "immutable_audit_required"],
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"cmd": cmd, "returncode": proc.returncode, "output_tail": proc.stdout[-4000:]}


def py_compile(paths: list[str]) -> list[str]:
    errors = []
    for item in paths:
        p = ROOT / item
        try:
            ast.parse(p.read_text())
        except Exception as exc:
            errors.append(f"{item}: {exc}")
    return errors


def main() -> int:
    failures = []
    checks = []
    for item in REQUIRED:
        exists = (ROOT / item).exists()
        checks.append({"name": f"exists:{item}", "ok": exists})
        if not exists:
            failures.append(f"missing_required:{item}")
    for item, markers in REQUIRED_MARKERS.items():
        text = (ROOT / item).read_text() if (ROOT / item).exists() else ""
        for marker in markers:
            ok = marker in text
            checks.append({"name": f"marker:{item}:{marker}", "ok": ok})
            if not ok:
                failures.append(f"marker_missing:{item}:{marker}")
    compile_errors = py_compile(REQUIRED + ["scripts/level1_41_real_order_safety_final_quality.py"])
    if compile_errors:
        failures.extend(compile_errors)
    checks.append({"name": "python_ast_compile", "ok": not compile_errors, "errors": compile_errors})
    runtime_leaks = [item for item in RUNTIME_FORBIDDEN if (ROOT / item).exists()]
    if runtime_leaks:
        failures.append(f"runtime_leaks:{runtime_leaks}")
    checks.append({"name": "runtime_leak_guard", "ok": not runtime_leaks, "leaks": runtime_leaks})
    pytest_result = run([sys.executable, "-m", "pytest", "-q", "tests/unit/test_real_order_safety_final.py"])
    checks.append({"name": "real_order_safety_pytest", "ok": pytest_result["returncode"] == 0, "result": pytest_result})
    if pytest_result["returncode"] != 0:
        failures.append("real_order_safety_pytest_failed")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps({"status": "ok" if not failures else "failed", "checks": checks, "failures": failures}, indent=2, ensure_ascii=False))
    if failures:
        print("LEVEL1_41_REAL_ORDER_SAFETY_FINAL_FAILED")
        for f in failures:
            print(f" - {f}")
        return 1
    print("LEVEL1_41_REAL_ORDER_SAFETY_FINAL_OK")
    print(f"report={rel(REPORT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
