from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
REVISION_RANGE = "981-985"
PACKAGE_NAME = "Production Environment Activation Block"
FINAL_DECISION_READY = "PRODUCTION_ENV_READY"

REQUIRED_ENV_KEYS = [
    "HMTSTC_ENV",
    "HMTSTC_SECRET_KEY",
    "HMTSTC_OWNER_USERNAME",
    "HMTSTC_OWNER_PASSWORD",
    "HMTSTC_BINANCE_API_KEY",
    "HMTSTC_BINANCE_API_SECRET",
    "HMTSTC_REAL_TRADING_ENABLED",
    "HMTSTC_REAL_TRADE_ENABLED",
    "HMTSTC_ENABLE_REAL_SUBMIT",
    "HMTSTC_ENABLE_REAL_CLOSE",
    "HMTSTC_ENABLE_EMERGENCY_CLOSE",
    "HMTSTC_AUTO_SCALE_ENABLED",
    "HMTSTC_AUTO_APPLY_ENABLED",
    "HMTSTC_AUTO_CLOSE_ENABLED",
]

SAFE_FALSE_FLAGS = [
    "HMTSTC_REAL_TRADING_ENABLED",
    "HMTSTC_REAL_TRADE_ENABLED",
    "HMTSTC_ENABLE_REAL_SUBMIT",
    "HMTSTC_ENABLE_REAL_CLOSE",
    "HMTSTC_ENABLE_EMERGENCY_CLOSE",
    "HMTSTC_AUTO_SCALE_ENABLED",
    "HMTSTC_AUTO_APPLY_ENABLED",
    "HMTSTC_AUTO_CLOSE_ENABLED",
]

REQUIRED_FRONTEND_FILES = [
    "frontend/index.html",
    "frontend/js/app.js",
    "frontend/js/config.example.js",
    "frontend/js/config.js",
]

QUALITY_SCRIPTS = ["quality:frontend", "quality:post-deploy", "quality:sync"]

REQUIRED_BACKEND_FILES = [
    "backend/main.py",
    "backend/requirements.txt",
    "backend/routes/production_routes.py",
]

REQUIRED_DEPLOY_FILES = [
    "deploy/hmtstc-backend.service",
    "deploy/nginx.conf",
    "deploy/deploy.sh",
]

RUNTIME_ONLY_FILES = [
    "backend/.env",
    "backend/auth_store.json",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
    "backend/runtime_backups/",
]

REQUIRED_PYTHON_DEPENDENCIES = ["fastapi", "uvicorn", "pydantic"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _rel_exists(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def _parse_assignment_keys(text: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r"^\s*([A-Z0-9_]+)\s*=", text, re.MULTILINE)}


def _read_env_template_metadata(root: Path) -> dict[str, Any]:
    path = root / "backend" / ".env.example"
    text = _read(path)
    keys = sorted(_parse_assignment_keys(text))
    missing = [key for key in REQUIRED_ENV_KEYS if key not in keys]
    unsafe_defaults: list[dict[str, str]] = []
    safe_defaults: list[dict[str, str]] = []
    for key in SAFE_FALSE_FLAGS:
        match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([^\n#]+)", text, re.MULTILINE)
        value = str(match.group(1)).strip().strip('"\'').lower() if match else "missing"
        row = {"key": key, "expected": "false", "actual_template_value": value}
        if value == "false":
            safe_defaults.append(row)
        else:
            unsafe_defaults.append(row)
    placeholder_secret_keys = [
        key
        for key in ("HMTSTC_SECRET_KEY", "HMTSTC_BINANCE_API_KEY", "HMTSTC_BINANCE_API_SECRET")
        if re.search(rf"^\s*{re.escape(key)}\s*=\s*(replace|change|example|dummy|test|your|local)", text, re.IGNORECASE | re.MULTILINE)
    ]
    return {
        "file": "backend/.env.example",
        "exists": path.exists(),
        "declared_key_count": len(keys),
        "declared_keys": keys,
        "missing_required_keys": missing,
        "safe_false_defaults": safe_defaults,
        "unsafe_defaults": unsafe_defaults,
        "placeholder_secret_keys": sorted(placeholder_secret_keys),
        "secret_values_returned": False,
    }


def build_rev981_backend_env_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    template = _read_env_template_metadata(root)
    runtime_env = root / "backend" / ".env"
    runtime_status = "vps_only_present" if runtime_env.exists() else "vps_only_not_in_package"
    blockers = []
    if not template["exists"]:
        blockers.append("missing_backend_env_example")
    if template["missing_required_keys"]:
        blockers.append("missing_required_env_keys")
    if template["unsafe_defaults"]:
        blockers.append("unsafe_real_trading_or_auto_default")
    return {
        "revision": 981,
        "name": "backend_env_checklist",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "env_template": template,
        "runtime_env_file_status": runtime_status,
        "runtime_env_value_policy": "Do not read, print, zip, log, or return backend/.env values; only VPS operator validates real values.",
        "runtime_only_files": RUNTIME_ONLY_FILES,
        "secret_values_returned": False,
    }


def _load_package_json(root: Path) -> dict[str, Any]:
    try:
        return json.loads(_read(root / "package.json") or "{}")
    except Exception:
        return {}


def build_rev982_frontend_build_config_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    package = _load_package_json(root)
    scripts = package.get("scripts") or {}
    missing_files = [rel for rel in REQUIRED_FRONTEND_FILES if not _rel_exists(root, rel)]
    missing_quality_scripts = [name for name in QUALITY_SCRIPTS if name not in scripts]
    index = _read(root / "frontend" / "index.html")
    config_js = _read(root / "frontend" / "js" / "config.js")
    app_js = _read(root / "frontend" / "js" / "app.js")
    script_refs = {
        "js/config.js": "js/config.js" in index,
        "js/app.js": "js/app.js" in index,
    }
    api_base_present = "apiBase" in config_js or "API_BASE" in config_js or "api" in config_js.lower()
    app_root_present = "HMTSTC_APP" in app_js
    build_script_present = "build" in scripts
    blockers = []
    if missing_files:
        blockers.append("missing_frontend_static_files")
    if missing_quality_scripts:
        blockers.append("missing_required_quality_scripts")
    if not all(script_refs.values()):
        blockers.append("frontend_index_missing_required_script_refs")
    if not app_root_present:
        blockers.append("frontend_app_root_not_detected")
    return {
        "revision": 982,
        "name": "frontend_build_config_control",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "asset_mode": "static_frontend",
        "build_script_present": build_script_present,
        "build_script_required": False,
        "build_script_note": "No build script is acceptable for this package because production is static/smoke-test based.",
        "missing_files": missing_files,
        "script_refs": script_refs,
        "api_base_config_detected": api_base_present,
        "app_root_present": app_root_present,
        "quality_scripts": {name: scripts.get(name) for name in QUALITY_SCRIPTS},
    }


def _service_exec_is_expected(service_text: str) -> bool:
    compact = " ".join(service_text.split())
    return "/var/www/hmtstc/backend/venv/bin/uvicorn" in compact and "main:app" in compact and "--host 127.0.0.1" in compact and "--port 8000" in compact


def build_rev983_service_nginx_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    missing = [rel for rel in REQUIRED_DEPLOY_FILES if not _rel_exists(root, rel)]
    service = _read(root / "deploy" / "hmtstc-backend.service")
    nginx = _read(root / "deploy" / "nginx.conf")
    deploy = _read(root / "deploy" / "deploy.sh")
    checks = [
        {"name": "systemd_service_name", "status": "ok" if "HMTSTC Backend API" in service else "blocked"},
        {"name": "systemd_working_directory", "status": "ok" if "WorkingDirectory=/var/www/hmtstc/backend" in service else "blocked"},
        {"name": "systemd_environment_file", "status": "ok" if "EnvironmentFile=-/var/www/hmtstc/backend/.env" in service else "blocked"},
        {"name": "systemd_execstart_backend_venv", "status": "ok" if _service_exec_is_expected(service) else "blocked"},
        {"name": "systemd_restart_policy", "status": "ok" if "Restart=always" in service else "review"},
        {"name": "nginx_frontend_root", "status": "ok" if "root /var/www/hmtstc/frontend" in nginx else "blocked"},
        {"name": "nginx_api_proxy", "status": "ok" if "proxy_pass http://127.0.0.1:8000/api/" in nginx else "blocked"},
        {"name": "nginx_health_proxy", "status": "ok" if "proxy_pass http://127.0.0.1:8000/health" in nginx else "blocked"},
        {"name": "deploy_restart_backend", "status": "ok" if "systemctl restart hmtstc-backend" in deploy else "blocked"},
        {"name": "deploy_nginx_test", "status": "ok" if "nginx -t" in deploy else "blocked"},
    ]
    blockers = [row["name"] for row in checks if row["status"] == "blocked"]
    reviews = [row["name"] for row in checks if row["status"] == "review"]
    return {
        "revision": 983,
        "name": "systemd_docker_nginx_production_service_control",
        "status": "ok" if not missing and not blockers else "blocked",
        "blockers": (["missing_deploy_files"] if missing else []) + blockers,
        "reviews": reviews,
        "docker_required": False,
        "systemd_service": "hmtstc-backend",
        "expected_execstart": "/var/www/hmtstc/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000",
        "missing_files": missing,
        "checks": checks,
    }


def _parse_requirements(root: Path) -> dict[str, Any]:
    path = root / "backend" / "requirements.txt"
    text = _read(path)
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            entries.append(line)
    lower = "\n".join(entries).lower()
    missing = [dep for dep in REQUIRED_PYTHON_DEPENDENCIES if dep not in lower]
    return {"file": "backend/requirements.txt", "exists": path.exists(), "entries_count": len(entries), "missing_core_dependencies": missing}


def _mode_string(path: Path) -> str | None:
    try:
        return oct(stat.S_IMODE(path.stat().st_mode))
    except Exception:
        return None


def build_rev984_vps_dependency_permission_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    missing_backend = [rel for rel in REQUIRED_BACKEND_FILES if not _rel_exists(root, rel)]
    requirements = _parse_requirements(root)
    deploy_sh = root / "deploy" / "deploy.sh"
    gitignore = _read(root / ".gitignore")
    runtime_patterns = [pattern for pattern in RUNTIME_ONLY_FILES if pattern.rstrip("/") in gitignore or pattern in gitignore]
    missing_gitignore_runtime_patterns = [pattern for pattern in RUNTIME_ONLY_FILES if pattern not in runtime_patterns]
    deploy_text = _read(deploy_sh)
    permission_checks = [
        {"name": "backend_dir_owner_policy", "status": "ok" if "chown -R hmtstc:www-data" in deploy_text else "blocked"},
        {"name": "backend_dir_mode_policy", "status": "ok" if "chmod 750" in deploy_text else "blocked"},
        {"name": "env_mode_policy", "status": "ok" if "chmod 640" in deploy_text and ".env" in deploy_text else "blocked"},
        {"name": "runtime_store_mode_policy", "status": "ok" if "chmod 660" in deploy_text else "blocked"},
        {"name": "runtime_backup_repo_externalized", "status": "ok" if "backend/runtime_backups/" in gitignore else "blocked"},
    ]
    blockers = []
    if missing_backend:
        blockers.append("missing_backend_files")
    if not requirements["exists"] or requirements["missing_core_dependencies"]:
        blockers.append("missing_core_python_dependencies")
    if missing_gitignore_runtime_patterns:
        blockers.append("gitignore_missing_runtime_only_patterns")
    blockers.extend([row["name"] for row in permission_checks if row["status"] == "blocked"])
    return {
        "revision": 984,
        "name": "vps_dependency_permission_control",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "missing_backend_files": missing_backend,
        "python_requirements": requirements,
        "permission_policy_checks": permission_checks,
        "deploy_script_mode": _mode_string(deploy_sh),
        "runtime_only_gitignore_patterns_present": runtime_patterns,
        "missing_runtime_only_gitignore_patterns": missing_gitignore_runtime_patterns,
        "vps_runtime_backups_target": "/var/backups/hmtstc/runtime_backups_YYYYMMDD_HHMMSS",
    }


def build_production_environment_activation_report(root: Path = ROOT_DIR) -> dict[str, Any]:
    checks = {
        "rev981_backend_env": build_rev981_backend_env_check(root),
        "rev982_frontend_build_config": build_rev982_frontend_build_config_check(root),
        "rev983_service_nginx": build_rev983_service_nginx_check(root),
        "rev984_dependency_permission": build_rev984_vps_dependency_permission_check(root),
    }
    blockers = [name for name, payload in checks.items() if payload.get("status") == "blocked"]
    reviews = [
        f"{name}:{item}"
        for name, payload in checks.items()
        for item in payload.get("reviews", [])
    ]
    final_decision = FINAL_DECISION_READY if not blockers else "BLOCKED"
    return {
        "status": "ok" if final_decision == FINAL_DECISION_READY else "blocked",
        "revision": 985,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "generated_at": _now_iso(),
        "final_decision": final_decision,
        "blockers": blockers,
        "reviews": reviews,
        "checks": checks,
        "production_scope": {
            "environment_activation_only": True,
            "real_order_submit_triggered": False,
            "real_order_close_triggered": False,
            "binance_secret_values_returned": False,
            "owner_approval_required_for_live": True,
        },
        "operator_next_steps": [
            "Keep backend/.env only on VPS and never commit it.",
            "Run npm run quality:rev985-production-env before production activation handoff.",
            "Validate systemctl status hmtstc-backend and nginx -t directly on VPS.",
        ],
        "secret_values_returned": False,
    }


def build_production_environment_activation_summary(root: Path = ROOT_DIR) -> dict[str, Any]:
    report = build_production_environment_activation_report(root)
    return {
        "status": report["status"],
        "revision": report["revision"],
        "revision_range": report["revision_range"],
        "final_decision": report["final_decision"],
        "blocker_count": len(report["blockers"]),
        "review_count": len(report["reviews"]),
        "secret_values_returned": False,
        "real_order_submit_triggered": False,
        "real_order_close_triggered": False,
    }


if __name__ == "__main__":
    print(json.dumps(build_production_environment_activation_report(), indent=2, ensure_ascii=False))
