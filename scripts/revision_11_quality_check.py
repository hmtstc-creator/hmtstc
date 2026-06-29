#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import py_compile
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

RUNTIME_FORBIDDEN = [
    "backend/.env",
    "backend/auth_store.json",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/rule_store.json",
]


def compile_python() -> list[str]:
    errors = []
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return errors


def runtime_leaks() -> list[str]:
    # Compile/import kontrolleri __pycache__ üretebilir; paketleme öncesi temizlenir.
    for cache_dir in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    leaks = []
    for item in RUNTIME_FORBIDDEN:
        if (ROOT / item).exists():
            leaks.append(item)
    for path in ROOT.rglob("*.log"):
        leaks.append(str(path.relative_to(ROOT)))
    for path in ROOT.rglob("*.pyc"):
        leaks.append(str(path.relative_to(ROOT)))
    return leaks


def smoke_imports() -> list[str]:
    errors = []
    for mod in [
        "main",
        "services.revision_11_service",
        "services.execution_simulator",
        "services.paper_lab_service",
        "services.real_trade_safety_service",
        "services.intelligence_service",
    ]:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            errors.append(f"{mod}: {exc}")
    return errors


def quality_payload() -> dict:
    from services.revision_11_service import build_revision_11_quality_report
    return build_revision_11_quality_report({}, {}, username="ahmet", run_live_scan=False)


def main() -> int:
    result = {
        "revision": "revizyon_11",
        "python_compile_errors": compile_python(),
        "runtime_leaks": runtime_leaks(),
        "import_errors": smoke_imports(),
    }
    try:
        payload = quality_payload()
        result["quality_status"] = payload.get("status")
        result["quality_score"] = payload.get("score")
        result["quality_blocks"] = list((payload.get("blocks") or {}).keys())
    except Exception as exc:
        result.setdefault("import_errors", []).append(f"quality_payload: {exc}")

    ok = not result["python_compile_errors"] and not result["runtime_leaks"] and not result["import_errors"]
    result["status"] = "ok" if ok else "failed"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
