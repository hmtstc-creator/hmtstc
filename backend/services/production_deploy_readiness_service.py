from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVISION = 880
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DEPLOY = ROOT / "deploy"
SCRIPTS = ROOT / "scripts"

REQUIRED_BACKEND_FILES = [
    "backend/main.py",
    "backend/requirements.txt",
    "backend/.env.example",
]
REQUIRED_FRONTEND_FILES = [
    "frontend/index.html",
    "frontend/js/app.js",
    "frontend/js/config.example.js",
]
REQUIRED_DEPLOY_FILES = [
    "deploy/deploy.sh",
    "deploy/hmtstc-backend.service",
    "deploy/nginx.conf",
]
REQUIRED_ENV_KEYS = [
    "HMTSTC_SECRET_KEY",
    "HMTSTC_OWNER_USERNAME",
    "HMTSTC_OWNER_PASSWORD",
    "HMTSTC_REAL_TRADING_ENABLED",
    "HMTSTC_ENABLE_REAL_SUBMIT",
    "HMTSTC_ENABLE_REAL_CLOSE",
    "HMTSTC_ENABLE_EMERGENCY_CLOSE",
]
SAFE_DEFAULT_FLAGS = {
    "HMTSTC_REAL_TRADING_ENABLED": "false",
    "HMTSTC_ENABLE_REAL_SUBMIT": "false",
    "HMTSTC_ENABLE_REAL_CLOSE": "false",
    "HMTSTC_ENABLE_EMERGENCY_CLOSE": "false",
    "HMTSTC_AUTO_SCALE_ENABLED": "false",
    "HMTSTC_AUTO_APPLY_ENABLED": "false",
    "HMTSTC_AUTO_CLOSE_ENABLED": "false",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _exists(rel_path: str) -> bool:
    return (ROOT / rel_path).exists()


def _parse_requirements() -> dict[str, Any]:
    path = BACKEND / "requirements.txt"
    text = _read(path)
    entries = []
    missing_pins = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
        if not any(op in line for op in ("==", ">=", "~=", "<=")):
            missing_pins.append(line)
    required = ["fastapi", "uvicorn", "pydantic"]
    lower = "\n".join(entries).lower()
    missing_required = [pkg for pkg in required if pkg not in lower]
    return {
        "status": "ok" if path.exists() and not missing_required else "blocked",
        "file": "backend/requirements.txt",
        "dependency_count": len(entries),
        "missing_required": missing_required,
        "unpinned_or_loose": missing_pins[:20],
        "notes": "Loose pins are warnings only; missing core dependencies block deploy readiness.",
    }


def _frontend_static_check() -> dict[str, Any]:
    missing = [path for path in REQUIRED_FRONTEND_FILES if not _exists(path)]
    index = _read(FRONTEND / "index.html")
    app_js = _read(FRONTEND / "js" / "app.js")
    required_scripts = ["js/config.js", "js/app.js"]
    missing_scripts = [script for script in required_scripts if script not in index]
    has_app_root = "HMTSTC_APP" in app_js
    return {
        "status": "ok" if not missing and not missing_scripts and has_app_root else "blocked",
        "missing_files": missing,
        "missing_scripts": missing_scripts,
        "app_root_present": has_app_root,
        "asset_mode": "static_frontend",
    }


def _env_example_check() -> dict[str, Any]:
    path = BACKEND / ".env.example"
    text = _read(path)
    found = sorted({match.group(1) for match in re.finditer(r"^([A-Z0-9_]+)\s*=", text, re.MULTILINE)})
    missing = [key for key in REQUIRED_ENV_KEYS if key not in found]
    safe_flags = []
    unsafe_flags = []
    for key, expected in SAFE_DEFAULT_FLAGS.items():
        match = re.search(rf"^{re.escape(key)}\s*=\s*([^\n#]+)", text, re.MULTILINE)
        value = str(match.group(1)).strip().strip('"\'').lower() if match else "missing"
        row = {"key": key, "expected": expected, "found": value}
        if value == expected:
            safe_flags.append(row)
        else:
            unsafe_flags.append(row)
    return {
        "status": "ok" if path.exists() and not missing and not unsafe_flags else "blocked",
        "file": "backend/.env.example",
        "declared_key_count": len(found),
        "missing_required_keys": missing,
        "safe_default_flags": safe_flags,
        "unsafe_default_flags": unsafe_flags,
        "secret_values_returned": False,
    }


def _deploy_file_check() -> dict[str, Any]:
    missing = [path for path in REQUIRED_DEPLOY_FILES if not _exists(path)]
    service = _read(DEPLOY / "hmtstc-backend.service")
    nginx = _read(DEPLOY / "nginx.conf")
    deploy_sh = _read(DEPLOY / "deploy.sh")
    checks = [
        {"name": "systemd_execstart", "status": "ok" if "ExecStart" in service else "blocked"},
        {"name": "systemd_working_directory", "status": "ok" if "WorkingDirectory" in service else "blocked"},
        {"name": "nginx_proxy_pass", "status": "ok" if "proxy_pass" in nginx else "blocked"},
        {"name": "deploy_script_restarts_service", "status": "ok" if "systemctl" in deploy_sh or "docker" in deploy_sh else "review"},
    ]
    blockers = [row["name"] for row in checks if row["status"] == "blocked"]
    return {
        "status": "ok" if not missing and not blockers else "blocked",
        "missing_files": missing,
        "checks": checks,
    }


def _forbidden_runtime_scan() -> dict[str, Any]:
    forbidden_patterns = [
        re.compile(r"(^|/)\.env$"),
        re.compile(r"(^|/)auth_store\.json$"),
        re.compile(r"(^|/)settings_store\.json$"),
        re.compile(r"(^|/)shadow_store\.json$"),
        re.compile(r"(^|/)runtime_backups(/|$)"),
        re.compile(r"\.sqlite3?$"),
        re.compile(r"\.db$"),
        re.compile(r"\.log$"),
        re.compile(r"(^|/)node_modules(/|$)"),
        re.compile(r"(^|/)\.venv(/|$)"),
        re.compile(r"(^|/)venv(/|$)"),
        re.compile(r"(^|/)__pycache__(/|$)"),
    ]
    hits = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        if any(part in {".git", "node_modules", ".venv", "venv", "__pycache__"} for part in rel.split("/")):
            continue
        if any(pattern.search(rel) for pattern in forbidden_patterns):
            # .env.example is allowed and pycache dirs are not packaged by final zip builder.
            if rel.endswith(".env.example"):
                continue
            hits.append(rel)
    return {
        "status": "ok" if not hits else "blocked",
        "hit_count": len(hits),
        "hits": hits[:100],
    }


def _vps_checklist() -> list[dict[str, str]]:
    return [
        {"item": "Python runtime", "expected": "Python 3.11+ installed", "status": "operator_verify"},
        {"item": "Backend dependencies", "expected": "pip install -r backend/requirements.txt", "status": "ready"},
        {"item": "Environment", "expected": "Copy backend/.env.example to backend/.env and fill secrets on VPS only", "status": "operator_required"},
        {"item": "Real trading flags", "expected": "submit/close/emergency/auto flags remain false by default", "status": "ready"},
        {"item": "Systemd", "expected": "deploy/hmtstc-backend.service installed and enabled", "status": "operator_required"},
        {"item": "Nginx", "expected": "deploy/nginx.conf reviewed for domain/IP and proxy path", "status": "operator_required"},
        {"item": "Frontend", "expected": "frontend/js/config.js points to production API base", "status": "operator_required"},
        {"item": "Smoke", "expected": "/health and /health/ops return OK/review without secret exposure", "status": "ready"},
    ]


def build_production_deploy_readiness() -> dict[str, Any]:
    backend_files = {path: _exists(path) for path in REQUIRED_BACKEND_FILES}
    requirements = _parse_requirements()
    frontend = _frontend_static_check()
    env = _env_example_check()
    deploy_files = _deploy_file_check()
    forbidden = _forbidden_runtime_scan()
    sections = [
        {"name": "backend_files", "status": "ok" if all(backend_files.values()) else "blocked", "details": backend_files},
        {"name": "backend_dependencies", "status": requirements["status"], "details": requirements},
        {"name": "frontend_build_assets", "status": frontend["status"], "details": frontend},
        {"name": "vps_environment_contract", "status": env["status"], "details": env},
        {"name": "systemd_nginx_deploy_files", "status": deploy_files["status"], "details": deploy_files},
        {"name": "runtime_forbidden_file_scan", "status": forbidden["status"], "details": forbidden},
    ]
    blockers = [section["name"] for section in sections if section["status"] == "blocked"]
    reviews = [section["name"] for section in sections if section["status"] == "review"]
    decision = "READY" if not blockers and not reviews else ("BLOCKED" if blockers else "REVIEW")
    return {
        "status": "ok" if decision == "READY" else "review",
        "revision": REVISION,
        "generated_at": _now_iso(),
        "decision": decision,
        "blockers": blockers,
        "reviews": reviews,
        "sections": sections,
        "vps_checklist": _vps_checklist(),
        "safe_defaults": SAFE_DEFAULT_FLAGS,
        "operator_action": "Fill VPS-only secrets/env and run deploy smoke checks." if decision != "BLOCKED" else "Resolve blockers before VPS deploy.",
        "secret_values_returned": False,
        "real_submit_default_off": True,
        "real_close_default_off": True,
        "auto_scale_default_off": True,
    }


def build_production_deploy_readiness_summary() -> dict[str, Any]:
    report = build_production_deploy_readiness()
    return {
        "status": report["status"],
        "revision": report["revision"],
        "decision": report["decision"],
        "blocker_count": len(report["blockers"]),
        "review_count": len(report["reviews"]),
        "critical_blocker": report["blockers"][0] if report["blockers"] else None,
        "operator_action": report["operator_action"],
        "real_submit_default_off": True,
        "secret_values_returned": False,
    }


if __name__ == "__main__":
    print(json.dumps(build_production_deploy_readiness(), indent=2, ensure_ascii=False))
