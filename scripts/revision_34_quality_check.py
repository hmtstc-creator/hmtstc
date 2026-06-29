#!/usr/bin/env python3
from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / "backend/services/deploy_safety_service.py",
    ROOT / "backend/routes/quality_routes.py",
    ROOT / "backend/main.py",
    ROOT / "scripts/pre_deploy_backup.py",
    ROOT / "scripts/post_deploy_check.py",
    ROOT / "scripts/build_release_zip.py",
    ROOT / "deploy/deploy.sh",
    ROOT / "deploy/REV34_DEPLOY_ROLLBACK.md",
]

for path in REQUIRED:
    if not path.exists():
        raise SystemExit(f"MISSING: {path.relative_to(ROOT)}")

for path in (ROOT / "backend").rglob("*.py"):
    py_compile.compile(str(path), doraise=True)
for path in (ROOT / "scripts").glob("*.py"):
    py_compile.compile(str(path), doraise=True)

quality = (ROOT / "backend/routes/quality_routes.py").read_text(encoding="utf-8")
main = (ROOT / "backend/main.py").read_text(encoding="utf-8")
service = (ROOT / "backend/services/deploy_safety_service.py").read_text(encoding="utf-8")
deploy = (ROOT / "deploy/deploy.sh").read_text(encoding="utf-8")
api = (ROOT / "frontend/js/app/api.js").read_text(encoding="utf-8")
checks = {
    "revision_34_quality_routes": "/revision-34" in quality and "revision-34/deploy-safety" in quality and "revision-34/rollback-safety" in quality,
    "ops_health_deploy_safety": "/health/ops" in main and "build_deploy_safety_report" in main,
    "startup_real_lock": "apply_startup_real_trade_lock" in main and "enforce_post_deploy_lock" in main,
    "backup_script_contract": "create_runtime_backup" in (ROOT / "scripts/pre_deploy_backup.py").read_text(encoding="utf-8"),
    "post_deploy_smoke_contract": "/api/real/readiness" in (ROOT / "scripts/post_deploy_check.py").read_text(encoding="utf-8"),
    "release_zip_excludes_runtime": "runtime_backups" in service and "settings_store.json" in service and "create_release_zip" in service,
    "deploy_script_uses_rev34": "pre_deploy_backup.py" in deploy and "post_deploy_check.py" in deploy,
    "api_sync_rev34": "revision34Quality" in api and "deploySafety34" in api,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))
print("REVISION_34_QUALITY_OK")
