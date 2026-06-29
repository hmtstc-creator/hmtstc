#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import py_compile
import subprocess
import sys
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def compile_python() -> list[str]:
    errors = []
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            errors.append(f"python:{path.relative_to(ROOT)}:{exc}")
    return errors


def check_js() -> list[str]:
    errors = []
    for path in (FRONTEND / "js").rglob("*.js"):
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            errors.append(f"js:{path.relative_to(ROOT)}:{result.stderr.strip()}")
    return errors


def clean_pycache():
    for path in ROOT.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)


def check_runtime_leakage() -> list[str]:
    clean_pycache()
    forbidden = [
        "backend/.env",
        "backend/auth_store.json",
        "backend/settings_store.json",
        "backend/shadow_store.json",
        "backend/rule_store.json",
    ]
    errors = []
    for rel in forbidden:
        if (ROOT / rel).exists():
            errors.append(f"runtime_leak:{rel}")
    for path in ROOT.rglob("*.pyc"):
        errors.append(f"runtime_leak:{path.relative_to(ROOT)}")
    return errors


def functional_checks() -> dict:
    sys.path.insert(0, str(BACKEND))
    from services.settings_unit_service import normalize_percent, normalize_money, validate_normalized_settings
    from services.revision_13_service import build_revision_13_quality_report

    percent = normalize_percent("0,75")
    money = normalize_money("1000")
    validation = validate_normalized_settings({
        "bot": {"allocated_usdt": "1000", "usdt_per_position": "50", "max_open_positions": "20"},
        "risk": {"stop_loss": "0,75", "take_profit": "2", "daily_loss_limit": "30", "weekly_loss_limit": "90"},
    })
    quality = build_revision_13_quality_report({"audit": [], "last_scan": {}, "bot_loop_traces": []}, validation["normalized"], username="ahmet")
    return {
        "percent_0_75": percent,
        "money_1000": money,
        "settings_valid": validation["valid"],
        "quality_revision": quality["revision"],
    }


def main() -> int:
    errors = []
    errors.extend(compile_python())
    errors.extend(check_js())
    errors.extend(check_runtime_leakage())
    checks = {}
    try:
        checks = functional_checks()
        if checks.get("percent_0_75", {}).get("value") != 0.75:
            errors.append("percent_normalization_failed")
        if checks.get("money_1000", {}).get("value") != 1000:
            errors.append("money_normalization_failed")
        if not checks.get("settings_valid"):
            errors.append("settings_validation_failed")
    except Exception as exc:
        errors.append(f"functional:{exc}")
    print(json.dumps({"ok": not errors, "revision": 13, "errors": errors, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
