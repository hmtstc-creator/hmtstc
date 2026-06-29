from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import BASE_DIR, DEFAULT_USER
from services.real_trade_state_service import ensure_real_trade_state, lock_real_trading

REVISION = 34
ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = BASE_DIR
RUNTIME_BACKUP_DIR = BACKEND_DIR / "runtime_backups"
ROLLBACK_DIR = ROOT_DIR / "deploy" / "rollback"

RUNTIME_FILES = [
    BACKEND_DIR / "settings_store.json",
    BACKEND_DIR / "shadow_store.json",
    BACKEND_DIR / "auth_store.json",
    BACKEND_DIR / "rule_store.json",
    BACKEND_DIR / "audit_store.json",
]

RUNTIME_GLOBS = [
    "backend/.env",
    "backend/*.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
    "backend/runtime_backups/*",
    "backend/*_backup_*.json",
    "*.log",
]

REQUIRED_DEPLOY_FILES = [
    ROOT_DIR / "deploy" / "deploy.sh",
    ROOT_DIR / "deploy" / "hmtstc-backend.service",
    ROOT_DIR / "deploy" / "nginx.conf",
    ROOT_DIR / "scripts" / "pre_deploy_backup.py",
    ROOT_DIR / "scripts" / "post_deploy_check.py",
    ROOT_DIR / "scripts" / "build_release_zip.py",
    ROOT_DIR / "scripts" / "revision_34_quality_check.py",
]

REQUIRED_HEALTH_ENDPOINTS = [
    "/health",
    "/health/ops",
    "/api/real/readiness",
    "/api/quality/revision-34",
    "/api/quality/revision-34/deploy-safety",
    "/api/quality/revision-34/rollback-safety",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _status_from_blockers(blockers: list[str]) -> str:
    if not blockers:
        return "ok"
    if len(blockers) <= 2:
        return "review"
    return "blocked"


def read_env_contract() -> dict:
    return {
        "real_trading_enabled": str(os.getenv("REAL_TRADING_ENABLED", "false")).strip().lower() == "true",
        "real_trading_dry_run": str(os.getenv("REAL_TRADING_DRY_RUN", "true")).strip().lower() != "false",
        "binance_mode": str(os.getenv("BINANCE_MODE", "testnet") or "testnet").strip().lower(),
        "pilot_enabled": str(os.getenv("REAL_PILOT_ENABLED", "false")).strip().lower() == "true",
        "max_order_usdt": os.getenv("REAL_MAX_ORDER_USDT", "5"),
        "daily_loss_limit_usdt": os.getenv("REAL_DAILY_LOSS_LIMIT_USDT", "2"),
    }


def build_real_lock_report(data: dict | None = None) -> dict:
    data = data if isinstance(data, dict) else {}
    state = ensure_real_trade_state(data)
    env = read_env_contract()
    blockers = []
    warnings = []

    if env["real_trading_enabled"]:
        blockers.append("env_real_trading_enabled_true")
    if not env["real_trading_dry_run"]:
        blockers.append("env_real_trading_dry_run_false")
    if state.get("owner_unlocked"):
        blockers.append("owner_unlocked_after_deploy")
    if state.get("pilot", {}).get("active"):
        blockers.append("pilot_active_after_deploy")
    if state.get("enabled"):
        warnings.append("runtime_real_state_enabled_flag_true")

    return {
        "status": _status_from_blockers(blockers),
        "revision": REVISION,
        "real_trading_locked": not blockers,
        "env": env,
        "runtime": {
            "enabled": bool(state.get("enabled")),
            "dry_run": bool(state.get("dry_run", True)),
            "owner_unlocked": bool(state.get("owner_unlocked")),
            "emergency_lock": bool(state.get("emergency_lock")),
            "pilot_active": bool(state.get("pilot", {}).get("active")),
            "manual_attention_required": bool(state.get("manual_attention_required")),
        },
        "blockers": blockers,
        "warnings": warnings,
        "policy": "real trading must remain locked after deploy, restart, and rollback",
    }


def enforce_post_deploy_lock(data: dict, reason: str = "rev34_deploy_safety_lock") -> dict:
    state = ensure_real_trade_state(data)
    lock_real_trading(state, reason=reason)
    state["enabled"] = False
    state["dry_run"] = True
    state.setdefault("pilot", {})["active"] = False
    state["last_deploy_lock_at"] = now_iso()
    state["last_deploy_lock_reason"] = reason
    return state


def build_backup_plan() -> dict:
    files = []
    for path in RUNTIME_FILES:
        item = {
            "path": str(path.relative_to(ROOT_DIR)),
            "exists": path.exists(),
            "required_for_runtime": path.name in {"settings_store.json", "shadow_store.json", "auth_store.json", "rule_store.json"},
        }
        if path.exists():
            item["size_bytes"] = path.stat().st_size
            item["sha256"] = sha256_file(path)
        files.append(item)
    return {
        "status": "ok",
        "revision": REVISION,
        "backup_dir": str(RUNTIME_BACKUP_DIR.relative_to(ROOT_DIR)),
        "runtime_files": files,
        "backup_before_deploy_required": True,
        "restore_must_lock_real_trading": True,
    }


def create_runtime_backup(label: str = "manual", include_missing_manifest: bool = True) -> dict:
    RUNTIME_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_id = f"rev34_{label}_{timestamp}"
    target_dir = RUNTIME_BACKUP_DIR / backup_id
    target_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for source in RUNTIME_FILES:
        entry = {
            "source": str(source.relative_to(ROOT_DIR)),
            "exists": source.exists(),
        }
        if source.exists():
            dest = target_dir / source.name
            shutil.copy2(source, dest)
            entry.update({
                "backup": str(dest.relative_to(ROOT_DIR)),
                "size_bytes": dest.stat().st_size,
                "sha256": sha256_file(dest),
            })
        entries.append(entry)

    manifest = {
        "status": "ok",
        "revision": REVISION,
        "backup_id": backup_id,
        "created_at": now_iso(),
        "label": label,
        "entries": entries,
        "restore_policy": {
            "real_trading_locked_after_restore": True,
            "owner_unlock_reset_after_restore": True,
            "reconciliation_required_after_restore": True,
        },
    }
    if include_missing_manifest:
        (target_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def build_rollback_plan() -> dict:
    ROLLBACK_DIR.mkdir(parents=True, exist_ok=True)
    manifests = []
    for manifest in sorted(RUNTIME_BACKUP_DIR.glob("rev34_*/manifest.json"))[-10:]:
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            manifests.append({
                "backup_id": payload.get("backup_id"),
                "created_at": payload.get("created_at"),
                "path": str(manifest.relative_to(ROOT_DIR)),
                "entries": len(payload.get("entries") or []),
            })
        except Exception:
            continue
    return {
        "status": "ok" if (ROOT_DIR / "scripts" / "pre_deploy_backup.py").exists() else "review",
        "revision": REVISION,
        "rollback_dir": str(ROLLBACK_DIR.relative_to(ROOT_DIR)),
        "recent_backups": manifests,
        "policy": {
            "rollback_dry_run_required": True,
            "real_trading_locked_after_rollback": True,
            "owner_unlock_reset_after_rollback": True,
            "manual_reconciliation_required": True,
        },
    }


def build_deploy_file_report() -> dict:
    files = []
    missing = []
    for path in REQUIRED_DEPLOY_FILES:
        exists = path.exists()
        files.append({"path": str(path.relative_to(ROOT_DIR)), "exists": exists})
        if not exists:
            missing.append(str(path.relative_to(ROOT_DIR)))
    return {
        "status": "ok" if not missing else "blocked",
        "revision": REVISION,
        "files": files,
        "missing": missing,
    }


def build_runtime_leak_report() -> dict:
    leaked = []
    for pattern in RUNTIME_GLOBS:
        for path in ROOT_DIR.glob(pattern):
            if not path.exists() or path.is_dir():
                continue
            # Example stores are intentional and safe.
            if ".example" in path.name:
                continue
            leaked.append(str(path.relative_to(ROOT_DIR)))
    return {
        "status": "ok" if not leaked else "review",
        "revision": REVISION,
        "checked_patterns": RUNTIME_GLOBS,
        "runtime_files_present_in_worktree": sorted(set(leaked)),
        "release_zip_must_exclude": True,
    }


def build_release_manifest(zip_path: Path | None = None) -> dict:
    release_name = zip_path.name if zip_path else "hmtstc_revizyon_58_button_ui_productization_full_project.zip"
    import re
    match = re.search(r"(?:revizyon|rev|revision)[_-]?(\d+)", release_name, re.IGNORECASE)
    release_revision = int(match.group(1)) if match else REVISION
    required_checks = [
        "python_compile",
        "frontend_js_syntax",
        "fastapi_import",
        "revision_33_quality_check",
        "revision_34_quality_check",
        "revision_35_quality_check",
        "post_deploy_smoke_dry_run",
    ]
    if release_revision >= 36:
        required_checks.append("revision_36_quality_check")
    if release_revision >= 37:
        required_checks.append("revision_37_quality_check")
    if release_revision >= 58:
        required_checks.extend([
            "level1_58_button_inventory",
            "level1_58_button_smoke_quality",
            "level1_58_service_page_restructure",
            "level1_58_summary_read_only",
            "level1_58_runtime_leak_commit_safe",
        ])
    manifest = {
        "status": "ok",
        "revision": release_revision,
        "created_at": now_iso(),
        "release_name": release_name,
        "runtime_exclusion_policy": RUNTIME_GLOBS,
        "required_checks": required_checks,
    }
    if zip_path and zip_path.exists():
        manifest["zip"] = {
            "path": str(zip_path),
            "size_bytes": zip_path.stat().st_size,
            "sha256": sha256_file(zip_path),
        }
    return manifest


def build_deploy_safety_report(data: dict | None = None, settings: dict | None = None) -> dict:
    data = data if isinstance(data, dict) else {}
    file_report = build_deploy_file_report()
    backup = build_backup_plan()
    lock = build_real_lock_report(data)
    leaks = build_runtime_leak_report()
    rollback = build_rollback_plan()

    blockers = []
    warnings = []
    for name, report in {
        "deploy_files": file_report,
        "real_lock": lock,
        "runtime_leaks": leaks,
        "rollback": rollback,
    }.items():
        if report.get("status") == "blocked":
            blockers.append(name)
        elif report.get("status") == "review":
            warnings.append(name)

    readiness = 100 - (len(blockers) * 30) - (len(warnings) * 10)
    readiness = max(readiness, 0)
    return {
        "status": "ok" if readiness >= 90 and not blockers else ("review" if readiness >= 60 else "blocked"),
        "revision": REVISION,
        "readiness_score": readiness,
        "generated_at": now_iso(),
        "deploy_files": file_report,
        "backup_plan": backup,
        "real_lock": lock,
        "runtime_leaks": leaks,
        "rollback_plan": rollback,
        "health_endpoints": REQUIRED_HEALTH_ENDPOINTS,
        "blockers": blockers,
        "warnings": warnings,
    }


def build_revision_34_quality_report(data: dict | None = None, settings: dict | None = None) -> dict:
    data = data if isinstance(data, dict) else {}
    deploy = build_deploy_safety_report(data, settings or {})
    gates = [
        {"name": "pre_deploy_backup", "status": "ok" if (ROOT_DIR / "scripts" / "pre_deploy_backup.py").exists() else "blocked", "detail": "Runtime store backup script exists."},
        {"name": "post_deploy_smoke", "status": "ok" if (ROOT_DIR / "scripts" / "post_deploy_check.py").exists() else "blocked", "detail": "Health/readiness/quality smoke script exists."},
        {"name": "release_zip_builder", "status": "ok" if (ROOT_DIR / "scripts" / "build_release_zip.py").exists() else "blocked", "detail": "Runtime-safe release zip builder exists."},
        {"name": "real_trading_locked", "status": build_real_lock_report(data).get("status"), "detail": "Real trading remains locked after deploy/restart."},
        {"name": "rollback_policy", "status": build_rollback_plan().get("status"), "detail": "Rollback requires dry-run, lock reset, and reconciliation."},
        {"name": "runtime_leak_policy", "status": build_runtime_leak_report().get("status"), "detail": "Release pack excludes env, credentials, runtime stores and backups."},
        {"name": "ops_health_endpoint", "status": "ok", "detail": "/health/ops exposes deploy safety and runtime lock status."},
    ]
    ok_count = sum(1 for gate in gates if gate.get("status") == "ok")
    readiness = round(ok_count / len(gates) * 100, 2)
    return {
        "revision": REVISION,
        "status": "ok" if readiness >= 85 and deploy.get("status") != "blocked" else "review",
        "readiness_score": readiness,
        "gates": gates,
        "deploy_safety": deploy,
        "policy": {
            "no_real_trading_auto_enable": True,
            "backup_before_deploy": True,
            "post_deploy_smoke_required": True,
            "rollback_must_lock_real": True,
            "release_zip_excludes_runtime": True,
        },
    }


def create_release_zip(output_path: Path, root: Path | None = None) -> dict:
    root = root or ROOT_DIR
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    excluded_parts = {"__pycache__", ".pytest_cache", ".git", "node_modules", "runtime_backups"}
    excluded_names = {".env", "settings_store.json", "shadow_store.json", "auth_store.json", "rule_store.json", "audit_store.json", "real_trade_store.json"}

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path == output_path or path.is_dir():
                continue
            rel = path.relative_to(root)
            if any(part in excluded_parts for part in rel.parts):
                continue
            if path.name in excluded_names:
                continue
            if path.suffix in {".pyc", ".pyo", ".log", ".tmp"}:
                continue
            zf.write(path, rel.as_posix())
    manifest = build_release_manifest(output_path)
    return manifest
