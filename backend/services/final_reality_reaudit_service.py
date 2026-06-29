"""Rev971-975 Final Reality Re-Audit service.

Local-only production reality audit. It validates file tree, backend route-service
binding, frontend API coverage and test command integrity without opening any
exchange/network path or returning secret values.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RealityCheck:
    name: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _list_files(root: Path) -> list[Path]:
    ignored = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def _extract_routes(root: Path) -> list[dict[str, str]]:
    routes: list[dict[str, str]] = []
    for path in sorted((root / "backend" / "routes").glob("*.py")):
        text = _read(path)
        prefix = ""
        router_match = re.search(r"APIRouter\((.*?)\)", text, re.S)
        if router_match:
            prefix_match = re.search(r"prefix\s*=\s*[\"']([^\"']+)", router_match.group(1))
            if prefix_match:
                prefix = prefix_match.group(1)
        for match in re.finditer(r"@router\.(get|post|put|delete|patch)\(\s*[\"']([^\"']*)", text):
            routes.append({"file": path.relative_to(root).as_posix(), "method": match.group(1).upper(), "path": prefix + match.group(2)})
    return routes


def _route_regex(route_path: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\{[^/]+\}", r"[^/]+", route_path.rstrip("/")) + "$")


def _extract_frontend_endpoints(root: Path) -> list[dict[str, str]]:
    endpoints: list[dict[str, str]] = []
    for path in sorted((root / "frontend").rglob("*.js")):
        text = _read(path)
        for match in re.finditer(r"fetchJson\(\s*[\"']([^\"']+)", text):
            endpoint = match.group(1).split("?")[0].rstrip("/") or "/"
            endpoints.append({"file": path.relative_to(root).as_posix(), "endpoint": endpoint})
    return endpoints


def _file_tree_check(root: Path) -> RealityCheck:
    required = [
        "backend/main.py",
        "backend/routes/production_routes.py",
        "backend/services/hmtstc_final_commercial_rc_service.py",
        "frontend/index.html",
        "frontend/js/app/api.js",
        "frontend/tests/unit/page_smoke_runner.cjs",
        "deploy/hmtstc-backend.service",
        "deploy/nginx.conf",
        "docs/HMTSTC_Rev966_970_Tamamlandi_Not.md",
    ]
    missing = [item for item in required if not (root / item).exists()]
    if missing:
        return RealityCheck("rev971_file_tree", "BLOCKED", "missing=" + ",".join(missing))
    runtime_hits = []
    for path in _list_files(root):
        rel = path.relative_to(root).as_posix()
        if path.name == ".env":
            runtime_hits.append(rel)
        if path.suffix in {".pyc", ".log", ".sqlite", ".db"}:
            runtime_hits.append(rel)
    if runtime_hits:
        return RealityCheck("rev971_file_tree", "BLOCKED", "runtime_or_cache_artifacts=" + ",".join(runtime_hits[:20]))
    return RealityCheck("rev971_file_tree", "PASS", "required production/backend/frontend/deploy/docs files present; runtime artifacts absent")


def _backend_binding_check(root: Path) -> RealityCheck:
    main_text = _read(root / "backend" / "main.py")
    route_files = sorted((root / "backend" / "routes").glob("*.py"))
    unmounted = []
    for path in route_files:
        if path.name == "__init__.py":
            continue
        stem = path.stem.replace("_routes", "")
        if path.stem not in main_text and stem not in main_text:
            unmounted.append(path.name)
    route_count = len(_extract_routes(root))
    if unmounted:
        return RealityCheck("rev972_backend_route_service_schema", "REVIEW", "unmounted_route_files=" + ",".join(unmounted[:20]))
    # Verify routes import at least one service module where expected.
    route_without_service = []
    for path in route_files:
        if path.name in {"__init__.py", "auth_routes.py"}:
            continue
        text = _read(path)
        if "from services." not in text and "import services" not in text:
            route_without_service.append(path.name)
    if route_without_service:
        return RealityCheck("rev972_backend_route_service_schema", "REVIEW", "routes_without_service_binding=" + ",".join(route_without_service[:20]))
    return RealityCheck("rev972_backend_route_service_schema", "PASS", f"{len(route_files)-1} route modules mounted; {route_count} route contracts detected")


def _frontend_api_check(root: Path) -> RealityCheck:
    routes = _extract_routes(root)
    route_patterns = [(_route_regex(item["path"]), item) for item in routes]
    endpoints = _extract_frontend_endpoints(root)
    missing = []
    for endpoint in endpoints:
        path = endpoint["endpoint"].rstrip("/") or "/"
        if not any(pattern.match(path) for pattern, _item in route_patterns):
            missing.append(endpoint)
    if missing:
        detail = ",".join(f"{item['endpoint']}@{item['file']}" for item in missing[:20])
        return RealityCheck("rev973_frontend_api_route_binding", "BLOCKED", "missing_backend_routes=" + detail)
    return RealityCheck("rev973_frontend_api_route_binding", "PASS", f"{len(endpoints)} frontend fetchJson contracts matched to backend route inventory")


def _test_integrity_check(root: Path) -> RealityCheck:
    package_path = root / "package.json"
    package = json.loads(_read(package_path)) if package_path.exists() else {"scripts": {}}
    missing_targets = []
    for name, command in (package.get("scripts") or {}).items():
        for token in re.findall(r"(?:python3?|node)\s+([^\s&|]+)", command):
            if not (root / token).exists():
                missing_targets.append(f"{name}:{token}")
    backend_smoke = root / "tests" / "api" / "test_backend_import_smoke.py"
    production_tests = sorted((root / "tests" / "api").glob("test_*production*_routes.py"))
    if missing_targets:
        return RealityCheck("rev974_test_integrity", "BLOCKED", "missing_script_targets=" + ",".join(missing_targets[:20]))
    if not backend_smoke.exists() or not production_tests:
        return RealityCheck("rev974_test_integrity", "BLOCKED", "missing_backend_or_production_tests")
    return RealityCheck("rev974_test_integrity", "PASS", f"npm script targets exist; backend smoke present; production_route_test_files={len(production_tests)}")


def _scaffold_density_check(root: Path) -> RealityCheck:
    suspicious: list[str] = []
    for path in _list_files(root):
        if path.suffix not in {".py", ".js", ".ts"}:
            continue
        rel = path.relative_to(root).as_posix()
        if rel.endswith(("final_code_reality_audit_service.py", "final_reality_reaudit_service.py")):
            continue
        text = _read(path).strip().lower()
        if not text:
            continue
        if any(marker in text for marker in ("todo: implement", "pass  #", "notimplementederror", "placeholder only")):
            suspicious.append(rel)
    if suspicious:
        return RealityCheck("rev975_scaffold_dead_code_scan", "REVIEW", "scaffold_markers=" + ",".join(suspicious[:20]))
    return RealityCheck("rev975_scaffold_dead_code_scan", "PASS", "no obvious todo/pass/notimplemented scaffold markers detected in source files")


def build_final_reality_reaudit(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    root = _project_root()
    checks = [
        _file_tree_check(root),
        _backend_binding_check(root),
        _frontend_api_check(root),
        _test_integrity_check(root),
        _scaffold_density_check(root),
    ]
    statuses = [check.status for check in checks]
    if "BLOCKED" in statuses:
        decision = "REALITY_REAUDIT_BLOCKED"
        operator_action = "Resolve blocked code, route, frontend or test target before VPS sync."
    elif "REVIEW" in statuses:
        decision = "REALITY_REAUDIT_REVIEW"
        operator_action = "Review non-blocking inventory warnings before production activation."
    else:
        decision = "REALITY_REAUDIT_PASS"
        operator_action = "Proceed to Local-to-GitHub-to-VPS Sync Block."
    return {
        "status": "ok",
        "revision": 975,
        "block": "Rev971-975 Final Reality Re-Audit Block",
        "decision": decision,
        "critical_blocker": next((check.name for check in checks if check.status == "BLOCKED"), None) or next((check.name for check in checks if check.status == "REVIEW"), "none"),
        "checks": [check.as_dict() for check in checks],
        "checks_passed": sum(1 for check in checks if check.status == "PASS"),
        "checks_total": len(checks),
        "route_contracts_total": len(_extract_routes(root)),
        "frontend_api_contracts_total": len(_extract_frontend_endpoints(root)),
        "real_network_call_performed": False,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "emergency_close_default_off": True,
        "secret_values_returned": False,
        "activation_token_value_returned": False,
        "owner_approval_required": True,
        "operator_action": operator_action,
    }


def build_final_reality_reaudit_summary() -> dict[str, Any]:
    result = build_final_reality_reaudit()
    return {
        "status": result["status"],
        "revision": result["revision"],
        "decision": result["decision"],
        "critical_blocker": result["critical_blocker"],
        "checks_passed": result["checks_passed"],
        "checks_total": result["checks_total"],
        "route_contracts_total": result["route_contracts_total"],
        "frontend_api_contracts_total": result["frontend_api_contracts_total"],
        "real_network_call_performed": False,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "emergency_close_default_off": True,
        "secret_values_returned": False,
        "operator_action": result["operator_action"],
    }
