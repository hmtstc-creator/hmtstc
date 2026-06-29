from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATTERNS = {
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
}
RUNTIME_DIRS = {"backend/runtime_backups"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def iter_project_files() -> list[Path]:
    ignored_parts = {".git", "__pycache__", ".pytest_cache", "node_modules"}
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(ROOT).parts)
        if parts & ignored_parts:
            continue
        files.append(path)
    return sorted(files, key=lambda p: rel(p))


def build_runtime_cleanup_report(clean: bool = False) -> dict[str, Any]:
    removed: list[str] = []
    found: list[str] = []
    for item in sorted(RUNTIME_PATTERNS):
        path = ROOT / item
        if path.exists():
            found.append(item)
            if clean:
                path.unlink(missing_ok=True)
                removed.append(item)
    for item in sorted(RUNTIME_DIRS):
        path = ROOT / item
        if path.exists():
            found.append(item)
            if clean:
                import shutil
                shutil.rmtree(path, ignore_errors=True)
                removed.append(item)
    return {
        "status": "ok" if not found or clean else "review",
        "clean_requested": clean,
        "found_runtime_items": found,
        "removed_runtime_items": removed,
        "policy": "runtime files are environment-owned and excluded from release packages",
    }


def build_runtime_leak_report() -> dict[str, Any]:
    leaks: list[str] = []
    for path in iter_project_files():
        relative = rel(path)
        if relative in RUNTIME_PATTERNS:
            leaks.append(relative)
        if any(relative.startswith(f"{directory}/") for directory in RUNTIME_DIRS):
            leaks.append(relative)
        if path.suffix.lower() in SECRET_SUFFIXES:
            leaks.append(relative)
    return {
        "status": "ok" if not leaks else "blocked",
        "leaks": sorted(set(leaks)),
        "checked_at": utc_now(),
    }


def build_route_inventory_snapshot() -> dict[str, Any]:
    try:
        import sys
        backend = str(ROOT / "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from main import app  # type: ignore
        routes = []
        for route in app.routes:
            path = getattr(route, "path", "")
            methods = sorted(getattr(route, "methods", []) or [])
            name = getattr(route, "name", "")
            if path:
                routes.append({"path": path, "methods": methods, "name": name})
        return {"status": "ok", "route_count": len(routes), "routes": routes, "checked_at": utc_now()}
    except Exception as exc:
        return {"status": "blocked", "route_count": 0, "routes": [], "error": str(exc), "checked_at": utc_now()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release_manifest(zip_path: str | None = None) -> dict[str, Any]:
    files = iter_project_files()
    suffix_counts: dict[str, int] = {}
    for path in files:
        suffix = path.suffix.lower() or "[no_ext]"
        suffix_counts[suffix] = suffix_counts.get(suffix, 0) + 1
    payload: dict[str, Any] = {
        "status": "ok",
        "revision": 55,
        "generated_at": utc_now(),
        "file_count": len(files),
        "suffix_counts": dict(sorted(suffix_counts.items())),
        "required_artifacts": {
            "gitignore": (ROOT / ".gitignore").exists(),
            "test_all": (ROOT / "scripts/test_all.sh").exists(),
            "package_json": (ROOT / "package.json").exists(),
            "pytest_ini": (ROOT / "pytest.ini").exists(),
            "commit_safe_scan": (ROOT / "scripts/level1_49_commit_safe_scan.py").exists(),
        },
        "runtime_leak": build_runtime_leak_report(),
        "route_inventory": {k: v for k, v in build_route_inventory_snapshot().items() if k != "routes"},
    }
    if zip_path:
        zp = Path(zip_path)
        if zp.exists():
            payload["zip"] = {"path": str(zp), "sha256": _sha256(zp), "size_bytes": zp.stat().st_size}
    if not all(payload["required_artifacts"].values()):
        payload["status"] = "review"
    if payload["runtime_leak"].get("status") != "ok":
        payload["status"] = "blocked"
    return payload


def build_rollback_metadata() -> dict[str, Any]:
    return {
        "status": "ok",
        "revision": 55,
        "rollback_policy": {
            "real_trading_locked_after_rollback": True,
            "owner_unlock_reset_after_rollback": True,
            "reconciliation_required_after_rollback": True,
            "emergency_state_preserved_after_rollback": True,
            "runtime_files_restored_from_backup_only": True,
        },
        "runtime_files_to_preserve": sorted(RUNTIME_PATTERNS) + sorted(RUNTIME_DIRS),
        "post_rollback_smoke_endpoints": [
            "/health",
            "/health/ops",
            "/api/summary",
            "/api/real/readiness",
            "/api/quality/level1-55/final-release",
        ],
    }


def build_api_contract_snapshot() -> dict[str, Any]:
    docs_dir = ROOT / "docs"
    candidates = [
        docs_dir / "LEVEL1_40_08_API_CONTRACT_DIFF.json",
        docs_dir / "LEVEL1_40_09_MISSING_ENDPOINT_REPORT.json",
        docs_dir / "LEVEL1_53_FRONTEND_API_INVENTORY_HARDENED.json",
    ]
    found = [rel(p) for p in candidates if p.exists()]
    return {
        "status": "ok" if found else "review",
        "source_reports": found,
        "contract_policy": {
            "frontend_backend_diff_required": True,
            "missing_endpoint_blocker_allowed": False,
            "false_positive_classification_required": True,
        },
    }


def build_final_quality_review() -> dict[str, Any]:
    docs = ROOT / "docs"
    required = [
        "LEVEL1_54_UIUX_PRODUCTIZATION_QUALITY_REPORT.json",
        "LEVEL1_53_FRONTEND_SMOKE_QUALITY_REPORT.json",
        "LEVEL1_49_COMMIT_SAFE_QUALITY_REPORT.json",
        "LEVEL1_40_23_FINAL_QUALITY_REPORT.json",
    ]
    artifact_status = {name: (docs / name).exists() for name in required}
    blockers: list[str] = []
    if not all(artifact_status.values()):
        blockers.append("some_historical_quality_artifacts_missing")
    if build_runtime_leak_report().get("status") != "ok":
        blockers.append("runtime_leak_detected")
    return {
        "status": "ok" if not blockers else "review",
        "revision": 55,
        "artifact_status": artifact_status,
        "api_contract": build_api_contract_snapshot(),
        "rollback_metadata": build_rollback_metadata(),
        "runtime_leak": build_runtime_leak_report(),
        "blockers": blockers,
        "checked_at": utc_now(),
    }


def build_level1_55_final_release_quality() -> dict[str, Any]:
    review = build_final_quality_review()
    manifest = build_release_manifest()
    route_snapshot = build_route_inventory_snapshot()
    blockers: list[str] = []
    if review.get("status") == "blocked":
        blockers.append("final_quality_review_blocked")
    if manifest.get("runtime_leak", {}).get("status") != "ok":
        blockers.append("runtime_leak")
    if route_snapshot.get("status") != "ok":
        blockers.append("route_inventory_failed")
    return {
        "status": "ok" if not blockers else "blocked",
        "revision": 55,
        "title": "CI / Deploy Final Quality + Release Hardening",
        "checked_at": utc_now(),
        "blockers": blockers,
        "manifest": manifest,
        "route_inventory": {k: v for k, v in route_snapshot.items() if k != "routes"},
        "final_quality_review": review,
        "rollback_metadata": build_rollback_metadata(),
        "release_policy": {
            "runtime_safe_zip_required": True,
            "commit_safe_scan_required": True,
            "post_deploy_smoke_required": True,
            "real_trading_locked_by_default": True,
        },
    }


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
