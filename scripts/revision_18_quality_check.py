#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def check_python_compile() -> None:
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        py_compile.compile(str(path), doraise=True)


def check_runtime_leakage() -> None:
    forbidden = [
        BACKEND / ".env",
        BACKEND / "auth_store.json",
        BACKEND / "settings_store.json",
        BACKEND / "shadow_store.json",
        BACKEND / "rule_store.json",
        BACKEND / "runtime_backups",
    ]
    leaked = [str(p.relative_to(ROOT)) for p in forbidden if p.exists()]
    if leaked:
        raise AssertionError("Runtime dosyası sızıntısı: " + ", ".join(leaked))


def check_js_syntax() -> None:
    import subprocess
    for path in (FRONTEND / "js").rglob("*.js"):
        subprocess.run(["node", "--check", str(path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def check_rule_schema() -> None:
    import sys
    sys.path.insert(0, str(BACKEND))
    service = importlib.import_module("services.rule_schema_service")
    contract = service.build_rule_schema_contract()
    assert contract["schema_version"].startswith("rev18"), contract
    sample_filter = {
        "type": "filter",
        "id": "USER_FILTER_TEST",
        "name": "Test Filter",
        "version": 1,
        "enabled": True,
        "risk_level": "medium",
        "conditions": [{"metric": "quote_volume", "operator": ">=", "value": 1000000}],
    }
    valid = service.validate_rule_schema(sample_filter)
    assert valid["valid"], valid
    bad_strategy = {"type": "strategy", "id": "BAD", "name": "Bad", "version": 1, "enabled": True, "min_score": 90}
    invalid = service.validate_rule_schema(bad_strategy)
    assert not invalid["valid"], invalid
    diff = service.diff_rules({"a": 1}, {"a": 2, "b": 3})
    assert len(diff) == 2, diff


def check_routes() -> None:
    import sys
    sys.path.insert(0, str(BACKEND))
    app_module = importlib.import_module("main")
    routes = {getattr(route, "path", "") for route in app_module.app.routes}
    required = {
        "/api/rules/schema",
        "/api/rules/schema/validate",
        "/api/rules/governance",
        "/api/rules/diff",
        "/api/quality/revision-18",
        "/api/quality/revision-18/rule-schema",
        "/api/quality/revision-18/rule-governance",
        "/api/quality/revision-18/rule-editor",
        "/api/quality/revision-18/import-export",
    }
    missing = sorted(required - routes)
    if missing:
        raise AssertionError("Eksik route: " + json.dumps(missing, ensure_ascii=False))


def main() -> None:
    check_runtime_leakage()
    check_python_compile()
    check_js_syntax()
    check_rule_schema()
    check_routes()
    print("REVISION_18_QUALITY_CHECK_OK")


if __name__ == "__main__":
    main()
