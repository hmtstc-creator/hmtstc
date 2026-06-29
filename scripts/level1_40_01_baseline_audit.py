#!/usr/bin/env python3
"""Level1 40.01 baseline audit for HMTSTC.

Read-only inventory script. It validates the current package baseline before
quality-foundation work begins. It does not mutate runtime stores and it does
not call trading/write endpoints.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FORBIDDEN = {
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
}
RUNTIME_FORBIDDEN_DIRS = {"backend/runtime_backups"}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(pattern: str) -> list[str]:
    return sorted(rel(p) for p in ROOT.glob(pattern) if p.is_file())


def route_inventory() -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for path in sorted((ROOT / "backend" / "routes").glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as exc:
            routes.append({"file": rel(path), "error": f"syntax: {exc}"})
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    method = dec.func.attr.upper()
                    if method in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                        route_path = None
                        if dec.args and isinstance(dec.args[0], ast.Constant):
                            route_path = dec.args[0].value
                        routes.append({
                            "file": rel(path),
                            "function": node.name,
                            "method": method,
                            "path": route_path,
                        })
    return routes


def runtime_leaks() -> list[str]:
    leaks: list[str] = []
    for item in RUNTIME_FORBIDDEN:
        if (ROOT / item).exists():
            leaks.append(item)
    for item in RUNTIME_FORBIDDEN_DIRS:
        if (ROOT / item).exists():
            leaks.append(item)
    return leaks


def main() -> int:
    all_files = sorted(p for p in ROOT.rglob("*") if p.is_file())
    py_files = [p for p in all_files if p.suffix == ".py"]
    js_files = [p for p in all_files if p.suffix == ".js"]
    routes = route_inventory()
    leaks = runtime_leaks()

    inventory = {
        "audit_id": "level1_40_01_baseline_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "counts": {
            "total_files": len(all_files),
            "python_files": len(py_files),
            "javascript_files": len(js_files),
            "backend_route_files": len(list_files("backend/routes/*.py")),
            "backend_service_files": len(list_files("backend/services/*.py")),
            "frontend_page_modules": len(list_files("frontend/js/pages/*.js")),
            "frontend_app_modules": len(list_files("frontend/js/app/*.js")),
            "quality_scripts": len(list_files("scripts/*quality_check.py")),
            "backend_test_files": len(list_files("tests/**/*.py")),
            "frontend_test_files": len(list_files("frontend/tests/**/*")),
            "declared_backend_routes": len([r for r in routes if "error" not in r]),
        },
        "required_assets": {
            "summary_page": (ROOT / "frontend/js/pages/summary.js").exists(),
            "summary_service": (ROOT / "backend/services/summary_service.py").exists(),
            "summary_routes": (ROOT / "backend/routes/summary_routes.py").exists(),
            "summary_quality_script": (ROOT / "scripts/revision_38_summary_quality_check.py").exists(),
            "readme": (ROOT / "README.md").exists(),
        },
        "runtime_leaks": leaks,
        "routes_sample": routes[:40],
        "critical_file_hashes": {
            item: file_sha256(ROOT / item)
            for item in [
                "backend/main.py",
                "backend/services/summary_service.py",
                "backend/routes/summary_routes.py",
                "frontend/js/pages/summary.js",
                "scripts/revision_38_summary_quality_check.py",
            ]
            if (ROOT / item).exists()
        },
    }

    out_dir = ROOT / "docs"
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "LEVEL1_40_01_BASELINE_INVENTORY.json"
    json_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")

    status = "OK" if not leaks and all(inventory["required_assets"].values()) else "REVIEW"
    print(f"LEVEL1_40_01_BASELINE_{status}")
    print(json.dumps({"counts": inventory["counts"], "runtime_leaks": leaks}, indent=2))
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
