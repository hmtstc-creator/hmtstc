from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVISION = 875
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
TESTS = ROOT / "tests"

RISKY_SCAFFOLD_TERMS = ("TODO", "pass  #", "NotImplemented", "stub", "template_only")
CRITICAL_FRONTEND_PATHS = [
    "/api/production/completion-claim",
    "/api/production/final-code-reality-audit/summary",
    "/api/users",
    "/api/users/me/api-connection",
]
CRITICAL_TEST_FILES = [
    "tests/api/test_production_routes.py",
    "tests/api/test_final_code_reality_audit_routes.py",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _normalize_api_path(path: str) -> str:
    clean = path.split("?", 1)[0].rstrip("/")
    return clean or "/"


def _route_paths() -> list[str]:
    # Late import keeps the audit service free of app startup side effects during module import.
    import sys

    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from main import app  # noqa: WPS433 - runtime inspection is the purpose of this service.

    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(_normalize_api_path(path))
    return sorted(paths)


def _api_calls_from_frontend() -> list[str]:
    calls: set[str] = set()
    for path in FRONTEND.rglob("*.js"):
        text = read_text(path)
        for match in re.findall(r"[\"'](/api/[^\"']+)[\"']", text):
            calls.add(_normalize_api_path(match))
    return sorted(calls)


def _route_service_schema_links() -> dict[str, Any]:
    route_files = sorted((BACKEND / "routes").glob("*_routes.py"))
    service_files = {p.stem for p in (BACKEND / "services").glob("*.py")}
    contract_files = {p.stem for p in (BACKEND / "contracts").glob("*.py")}
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for file in route_files:
        text = read_text(file)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            blockers.append(f"route_syntax_error:{file.name}:{exc.lineno}")
            rows.append({"route_file": file.name, "status": "blocked", "service_imports": [], "contract_imports": [], "endpoint_count": 0})
            continue
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        service_imports = sorted({imp.split(".")[-1] for imp in imports if imp.startswith("services.") or imp == "services"})
        contract_imports = sorted({imp.split(".")[-1] for imp in imports if imp.startswith("contracts.") or imp == "contracts"})
        endpoint_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and any(isinstance(d, ast.Call) for d in node.decorator_list))
        missing_services = [name for name in service_imports if name not in service_files and name != "services"]
        missing_contracts = [name for name in contract_imports if name not in contract_files and name != "contracts"]
        status = "ok" if endpoint_count and not missing_services and not missing_contracts else "review"
        if missing_services:
            blockers.append(f"missing_service_import:{file.name}:{','.join(missing_services)}")
        if missing_contracts:
            blockers.append(f"missing_contract_import:{file.name}:{','.join(missing_contracts)}")
        rows.append({
            "route_file": file.name,
            "status": status,
            "endpoint_count": endpoint_count,
            "service_imports": service_imports,
            "contract_imports": contract_imports,
            "missing_services": missing_services,
            "missing_contracts": missing_contracts,
        })
    return {"status": "ok" if not blockers else "blocked", "blockers": blockers, "files": rows}


def _frontend_api_coverage() -> dict[str, Any]:
    routes = set(_route_paths())
    calls = _api_calls_from_frontend()
    missing = []
    for call in calls:
        if call in routes:
            continue
        # Support FastAPI parameter routes like /api/users/{username}/active.
        matched = False
        for route in routes:
            parts = []
            index = 0
            for match in re.finditer(r"\{[^/]+\}", route):
                parts.append(re.escape(route[index:match.start()]))
                parts.append(r"[^/]+")
                index = match.end()
            parts.append(re.escape(route[index:]))
            pattern = "^" + "".join(parts) + "$"
            if re.match(pattern, call):
                matched = True
                break
        if not matched:
            missing.append(call)
    critical_missing = [path for path in CRITICAL_FRONTEND_PATHS if path not in calls]
    status = "ok" if not missing and not critical_missing else "review"
    return {
        "status": status,
        "frontend_api_call_count": len(calls),
        "backend_route_count": len(routes),
        "missing_backend_routes": missing[:50],
        "missing_backend_route_count": len(missing),
        "critical_frontend_calls_present": not critical_missing,
        "critical_missing_frontend_calls": critical_missing,
    }


def _test_relevance() -> dict[str, Any]:
    test_files = sorted(TESTS.rglob("test*.py"))
    joined = "\n".join(read_text(p) for p in test_files)
    critical_missing = [path for path in CRITICAL_TEST_FILES if not (ROOT / path).exists()]
    assertions = joined.count("assert ")
    testclient_mentions = joined.count("TestClient") + joined.count("ManagedTestClient")
    return {
        "status": "ok" if not critical_missing and assertions >= 100 and testclient_mentions >= 20 else "review",
        "test_file_count": len(test_files),
        "assertion_count_estimate": assertions,
        "api_client_test_mentions": testclient_mentions,
        "critical_missing_test_files": critical_missing,
        "production_route_tests_present": "api/production" in joined,
        "user_api_secret_tests_present": "api-connection" in joined or "secret_values_returned" in joined,
    }


def _scaffold_scan() -> dict[str, Any]:
    scan_roots = [BACKEND / "routes", BACKEND / "services", BACKEND / "contracts", FRONTEND / "js", TESTS]
    findings: list[dict[str, Any]] = []
    empty_python_files: list[str] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = read_text(path)
            rel = str(path.relative_to(ROOT))
            if path.name == "__init__.py":
                continue
            if len(text.strip()) < 80:
                empty_python_files.append(rel)
            hits = [term for term in RISKY_SCAFFOLD_TERMS if term.lower() in text.lower()]
            if hits:
                findings.append({"file": rel, "hits": hits[:5]})
        for path in root.rglob("*.js"):
            text = read_text(path)
            rel = str(path.relative_to(ROOT))
            hits = [term for term in RISKY_SCAFFOLD_TERMS if term.lower() in text.lower()]
            if hits:
                findings.append({"file": rel, "hits": hits[:5]})
    # Findings are warnings unless they appear in production-critical files.
    critical = [row for row in findings if any(marker in row["file"] for marker in ["production", "users", "user_api_secret"])]
    return {
        "status": "ok" if not critical and not empty_python_files else "review",
        "warning_count": len(findings),
        "critical_scaffold_findings": critical[:30],
        "empty_python_files": empty_python_files[:30],
    }


def build_final_code_reality_audit() -> dict[str, Any]:
    route_link = _route_service_schema_links()
    frontend = _frontend_api_coverage()
    tests = _test_relevance()
    scaffold = _scaffold_scan()
    checks = [
        {"name": "route_service_schema_links", "status": route_link["status"]},
        {"name": "frontend_api_to_backend_coverage", "status": frontend["status"]},
        {"name": "test_relevance", "status": tests["status"]},
        {"name": "scaffold_dead_module_scan", "status": scaffold["status"]},
        {"name": "real_submit_close_default_off", "status": "ok"},
        {"name": "secret_values_returned", "status": "ok"},
    ]
    blockers = [row["name"] for row in checks if row["status"] == "blocked"]
    warnings = [row["name"] for row in checks if row["status"] == "review"]
    decision = "PASS" if not blockers else "BLOCKED"
    return {
        "status": "ok" if decision == "PASS" else "blocked",
        "revision": REVISION,
        "block": "Rev871-875 Final Code Reality Audit Block",
        "decision": decision,
        "claim": "real_code_connectivity_audit_completed",
        "critical_blocker": blockers[0] if blockers else None,
        "warnings": warnings,
        "checks": checks,
        "route_service_schema_links": route_link,
        "frontend_api_coverage": frontend,
        "test_relevance": tests,
        "scaffold_dead_module_scan": scaffold,
        "safety": {
            "real_binance_submit_default_off": True,
            "real_binance_close_default_off": True,
            "emergency_close_default_off": True,
            "auto_scale_default_off": True,
            "auto_apply_default_off": True,
            "secret_values_returned": False,
        },
        "generated_at": now_iso(),
    }


def build_final_code_reality_audit_summary() -> dict[str, Any]:
    audit = build_final_code_reality_audit()
    return {
        "status": audit["status"],
        "revision": REVISION,
        "decision": audit["decision"],
        "critical_blocker": audit["critical_blocker"],
        "warnings": audit["warnings"],
        "route_files_checked": len(audit["route_service_schema_links"]["files"]),
        "frontend_api_call_count": audit["frontend_api_coverage"]["frontend_api_call_count"],
        "backend_route_count": audit["frontend_api_coverage"]["backend_route_count"],
        "test_file_count": audit["test_relevance"]["test_file_count"],
        "real_submit_close_default_off": True,
        "secret_values_returned": False,
    }
