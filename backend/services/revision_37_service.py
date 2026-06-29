from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
SCRIPTS_DIR = ROOT_DIR / "scripts"
DOCS_DIR = ROOT_DIR / "docs"
DEPLOY_DIR = ROOT_DIR / "deploy"
REVISION = 37

FINAL_REQUIRED_FILES = [
    "README.md",
    "backend/main.py",
    "backend/routes/quality_routes.py",
    "backend/routes/real_routes.py",
    "backend/routes/agent_routes.py",
    "backend/services/deploy_safety_service.py",
    "backend/services/ai_analyst_safe_mode_service.py",
    "backend/services/live_micro_pilot_procedure_service.py",
    "backend/services/revision_37_service.py",
    "frontend/js/app/api.js",
    "frontend/js/pages/intelligence.js",
    "scripts/pre_deploy_backup.py",
    "scripts/post_deploy_check.py",
    "scripts/build_release_zip.py",
    "scripts/revision_34_quality_check.py",
    "scripts/revision_35_quality_check.py",
    "scripts/revision_36_quality_check.py",
    "scripts/revision_37_quality_check.py",
    "deploy/REV34_DEPLOY_ROLLBACK.md",
    "docs/REV35_AI_ANALYST_SAFE_MODE.md",
    "docs/REV36_LIVE_MICRO_PILOT_PROCEDURE.md",
    "docs/REV37_FINAL_VERIFICATION.md",
]

EXPECTED_FINAL_ENDPOINTS = [
    "/health",
    "/health/ops",
    "/api/real/readiness",
    "/api/quality/revision-34",
    "/api/quality/revision-35",
    "/api/quality/revision-36",
    "/api/quality/revision-37",
    "/api/quality/revision-37/gates",
    "/api/quality/revision-37/autonomous-policy",
    "/api/quality/revision-37/package-manifest",
    "/api/quality/revision-37/checksum",
]

QUALITY_SCRIPT_CHAIN = [
    "scripts/revision_33_quality_check.py",
    "scripts/revision_34_quality_check.py",
    "scripts/revision_35_quality_check.py",
    "scripts/revision_36_quality_check.py",
    "scripts/revision_37_quality_check.py",
]

RUNTIME_LEAK_PATTERNS = [
    "backend/.env",
    "backend/*.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
    "backend/runtime_backups/*",
    "*.log",
]

FINAL_GATES = [
    {
        "id": "rev34_deploy_rollback_safety",
        "title": "Deploy & Rollback Safety",
        "required_files": ["scripts/pre_deploy_backup.py", "scripts/post_deploy_check.py", "deploy/REV34_DEPLOY_ROLLBACK.md"],
        "required_endpoints": ["/health/ops", "/api/quality/revision-34", "/api/real/readiness"],
    },
    {
        "id": "rev35_ai_analyst_safe_mode",
        "title": "AI Analyst Safe Mode",
        "required_files": ["backend/services/ai_analyst_safe_mode_service.py", "backend/routes/agent_routes.py", "docs/REV35_AI_ANALYST_SAFE_MODE.md"],
        "required_endpoints": ["/api/agent/safe-mode", "/api/agent/suggestions", "/api/agent/paper-queue", "/api/agent/prompt-log"],
    },
    {
        "id": "rev36_live_micro_pilot_procedure",
        "title": "Live Micro Pilot Procedure",
        "required_files": ["backend/services/live_micro_pilot_procedure_service.py", "backend/services/real_pilot_service.py", "docs/REV36_LIVE_MICRO_PILOT_PROCEDURE.md"],
        "required_endpoints": ["/api/real/pilot/procedure", "/api/real/pilot/rehearsal", "/api/real/pilot/tiny-order-plan", "/api/real/pilot/finalize"],
    },
    {
        "id": "rev37_final_verification_packaging",
        "title": "Final Verification + Packaging",
        "required_files": ["backend/services/revision_37_service.py", "scripts/revision_37_quality_check.py", "docs/REV37_FINAL_VERIFICATION.md"],
        "required_endpoints": ["/api/quality/revision-37", "/api/quality/revision-37/gates", "/api/quality/revision-37/package-manifest"],
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_exists(rel_path: str) -> bool:
    return (ROOT_DIR / rel_path).exists()


def read_text(rel_path: str) -> str:
    path = ROOT_DIR / rel_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def endpoint_present(endpoint: str, route_text: str) -> bool:
    if endpoint in route_text:
        return True
    prefixes = ["/api/quality", "/api/real", "/api/agent", "/api/observability"]
    for prefix in prefixes:
        if endpoint.startswith(prefix):
            suffix = endpoint[len(prefix):] or "/"
            if suffix in route_text:
                return True
    return False


def build_file_manifest() -> dict[str, Any]:
    files = []
    missing = []
    for rel in FINAL_REQUIRED_FILES:
        path = ROOT_DIR / rel
        item: dict[str, Any] = {"path": rel, "exists": path.exists()}
        if path.exists() and path.is_file():
            item["size_bytes"] = path.stat().st_size
            item["sha256"] = sha256_file(path)
        else:
            missing.append(rel)
        files.append(item)
    return {
        "status": "ok" if not missing else "blocked",
        "revision": REVISION,
        "generated_at": now_iso(),
        "required_count": len(FINAL_REQUIRED_FILES),
        "present_count": len(FINAL_REQUIRED_FILES) - len(missing),
        "missing": missing,
        "files": files,
    }


def build_runtime_leak_report() -> dict[str, Any]:
    leaked = []
    for pattern in RUNTIME_LEAK_PATTERNS:
        for path in ROOT_DIR.glob(pattern):
            if not path.exists() or path.is_dir():
                continue
            rel = str(path.relative_to(ROOT_DIR))
            if path.name.endswith(".example") or ".example." in path.name:
                continue
            leaked.append(rel)
    return {
        "status": "ok" if not leaked else "blocked",
        "revision": REVISION,
        "runtime_leak_found": bool(leaked),
        "leaked_files": sorted(set(leaked)),
        "policy": "release zip must not contain live credentials, runtime stores, backups or logs",
    }


def build_endpoint_contract_report() -> dict[str, Any]:
    route_text = read_text("backend/routes/quality_routes.py") + "\n" + read_text("backend/routes/real_routes.py") + "\n" + read_text("backend/routes/agent_routes.py") + "\n" + read_text("backend/main.py")
    api_text = read_text("frontend/js/app/api.js")
    found = []
    missing = []
    ui_missing = []
    for endpoint in EXPECTED_FINAL_ENDPOINTS:
        if endpoint_present(endpoint, route_text):
            found.append(endpoint)
        else:
            missing.append(endpoint)
        if endpoint.startswith("/api/quality/revision-37") and endpoint not in api_text:
            ui_missing.append(endpoint)
    return {
        "status": "ok" if not missing and not ui_missing else "blocked",
        "revision": REVISION,
        "expected_count": len(EXPECTED_FINAL_ENDPOINTS),
        "found_count": len(found),
        "missing": missing,
        "ui_missing": ui_missing,
        "found": found,
    }


def build_quality_script_chain_report() -> dict[str, Any]:
    scripts = []
    missing = []
    for rel in QUALITY_SCRIPT_CHAIN:
        path = ROOT_DIR / rel
        exists = path.exists()
        scripts.append({"path": rel, "exists": exists, "executable_command": f"python3 {rel}"})
        if not exists:
            missing.append(rel)
    return {
        "status": "ok" if not missing else "blocked",
        "revision": REVISION,
        "scripts": scripts,
        "missing": missing,
        "required_command_sequence": [f"python3 {rel}" for rel in QUALITY_SCRIPT_CHAIN],
    }


def build_autonomous_policy_report() -> dict[str, Any]:
    return {
        "status": "ok",
        "revision": REVISION,
        "policy": "human-controlled deployment and real-trading authority",
        "rules": [
            {"id": "no_background_autonomy", "state": "enforced", "detail": "No unattended background development claim is allowed by the package."},
            {"id": "ai_no_trade_authority", "state": "enforced", "detail": "AI analyst output is suggestions-only and paper-queue only."},
            {"id": "real_trade_locked_on_deploy", "state": "enforced", "detail": "Deploy/restart/rollback must leave real trading locked."},
            {"id": "pilot_requires_human_runbook", "state": "enforced", "detail": "Live micro pilot requires readonly, dry-run, token, tiny order, tracking, reconcile, auto-lock, report."},
            {"id": "release_requires_quality_chain", "state": "enforced", "detail": "Rev33-Rev37 quality scripts and syntax checks are required before release."},
        ],
        "forbidden_actions": [
            "AI placing real orders",
            "AI unlocking real trading",
            "AI starting pilot without owner-controlled flow",
            "Deploy that enables REAL_TRADING_ENABLED",
            "Release zip containing runtime credentials or live stores",
        ],
    }


def build_gate_report(data: dict | None = None, settings: dict | None = None) -> dict[str, Any]:
    route_text = read_text("backend/routes/quality_routes.py") + "\n" + read_text("backend/routes/real_routes.py") + "\n" + read_text("backend/routes/agent_routes.py") + "\n" + read_text("backend/main.py")
    gates = []
    blockers = []
    for gate in FINAL_GATES:
        missing_files = [rel for rel in gate["required_files"] if not file_exists(rel)]
        missing_endpoints = [endpoint for endpoint in gate["required_endpoints"] if not endpoint_present(endpoint, route_text)]
        status = "ok" if not missing_files and not missing_endpoints else "blocked"
        if status != "ok":
            blockers.append(gate["id"])
        gates.append({
            "id": gate["id"],
            "title": gate["title"],
            "status": status,
            "missing_files": missing_files,
            "missing_endpoints": missing_endpoints,
            "required_files": gate["required_files"],
            "required_endpoints": gate["required_endpoints"],
        })
    return {
        "status": "ok" if not blockers else "blocked",
        "revision": REVISION,
        "gate_count": len(gates),
        "passed_count": len([g for g in gates if g["status"] == "ok"]),
        "blockers": blockers,
        "gates": gates,
    }


def build_release_checksum_manifest(output_zip: str | None = None) -> dict[str, Any]:
    candidates = []
    if output_zip:
        candidates.append(Path(output_zip))
    candidates.extend([
        ROOT_DIR.parent / "hmtstc_revizyon_37_full_project.zip",
        ROOT_DIR / "hmtstc_revizyon_37_full_project.zip",
    ])
    seen = set()
    files = []
    for path in candidates:
        if str(path) in seen:
            continue
        seen.add(str(path))
        item: dict[str, Any] = {"path": str(path), "exists": path.exists()}
        if path.exists() and path.is_file():
            item["size_bytes"] = path.stat().st_size
            item["sha256"] = sha256_file(path)
        files.append(item)
    return {
        "status": "ok" if any(f.get("exists") for f in files) else "pending",
        "revision": REVISION,
        "generated_at": now_iso(),
        "release_files": files,
    }


def build_revision_37_quality_report(data: dict | None = None, settings: dict | None = None) -> dict[str, Any]:
    manifest = build_file_manifest()
    gates = build_gate_report(data, settings)
    endpoints = build_endpoint_contract_report()
    scripts = build_quality_script_chain_report()
    leaks = build_runtime_leak_report()
    policy = build_autonomous_policy_report()
    sections = {
        "package_manifest": manifest,
        "final_gates": gates,
        "endpoint_contract": endpoints,
        "quality_script_chain": scripts,
        "runtime_leak_check": leaks,
        "autonomous_policy": policy,
    }
    blockers = [name for name, section in sections.items() if section.get("status") == "blocked"]
    warnings = [name for name, section in sections.items() if section.get("status") == "review"]
    return {
        "status": "ok" if not blockers else "blocked",
        "revision": REVISION,
        "generated_at": now_iso(),
        "release_state": "final_verification_passed" if not blockers else "blocked_before_release",
        "blockers": blockers,
        "warnings": warnings,
        "sections": sections,
        "next_action": "Use hmtstc_revizyon_37_full_project.zip as final release root after external deployment smoke." if not blockers else "Close blockers before release packaging.",
    }
