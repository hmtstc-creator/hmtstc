#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HMTSTC_OFFLINE_QUALITY_CHECK", "1")
sys.path.insert(0, str(ROOT / "backend"))

REQUIRED = [
    ROOT / "backend/services/revision_37_service.py",
    ROOT / "backend/routes/quality_routes.py",
    ROOT / "frontend/js/app/api.js",
    ROOT / "frontend/js/pages/intelligence.js",
    ROOT / "scripts/revision_37_quality_check.py",
    ROOT / "docs/REV37_FINAL_VERIFICATION.md",
]
for path in REQUIRED:
    if not path.exists():
        raise SystemExit(f"MISSING: {path.relative_to(ROOT)}")

for path in (ROOT / "backend").rglob("*.py"):
    py_compile.compile(str(path), doraise=True)
for path in (ROOT / "scripts").glob("*.py"):
    py_compile.compile(str(path), doraise=True)

# JS syntax check when node is available.
js_files = sorted((ROOT / "frontend" / "js").rglob("*.js"))
for js_file in js_files:
    result = subprocess.run(["node", "--check", str(js_file)], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"JS_SYNTAX_FAILED: {js_file.relative_to(ROOT)}\n{result.stderr}")

from services.revision_37_service import (  # noqa: E402
    EXPECTED_FINAL_ENDPOINTS,
    FINAL_REQUIRED_FILES,
    build_autonomous_policy_report,
    build_endpoint_contract_report,
    build_file_manifest,
    build_gate_report,
    build_quality_script_chain_report,
    build_revision_37_quality_report,
    build_runtime_leak_report,
)

manifest = build_file_manifest()
if manifest.get("status") != "ok":
    raise SystemExit("FAILED: missing final required files " + json.dumps(manifest.get("missing")))
if manifest.get("required_count", 0) < 20:
    raise SystemExit("FAILED: final manifest too small")

gates = build_gate_report({}, {})
if gates.get("status") != "ok" or gates.get("passed_count") != gates.get("gate_count"):
    raise SystemExit("FAILED: Rev37 gates not fully passed")

endpoints = build_endpoint_contract_report()
if endpoints.get("status") != "ok":
    raise SystemExit("FAILED: endpoint contract incomplete " + json.dumps(endpoints))
if len(EXPECTED_FINAL_ENDPOINTS) < 10:
    raise SystemExit("FAILED: endpoint contract coverage is too small")

scripts = build_quality_script_chain_report()
if scripts.get("status") != "ok":
    raise SystemExit("FAILED: missing quality script chain")

leaks = build_runtime_leak_report()
if leaks.get("status") != "ok":
    raise SystemExit("FAILED: runtime leak found " + json.dumps(leaks.get("leaked_files")))

policy = build_autonomous_policy_report()
for forbidden in ["AI placing real orders", "AI unlocking real trading", "Deploy that enables REAL_TRADING_ENABLED"]:
    if forbidden not in policy.get("forbidden_actions", []):
        raise SystemExit("FAILED: autonomous policy missing " + forbidden)

quality = build_revision_37_quality_report({}, {})
if quality.get("status") != "ok":
    raise SystemExit("FAILED: revision 37 quality not ok " + json.dumps(quality.get("blockers")))

quality_routes = (ROOT / "backend/routes/quality_routes.py").read_text(encoding="utf-8")
api = (ROOT / "frontend/js/app/api.js").read_text(encoding="utf-8")
intel = (ROOT / "frontend/js/pages/intelligence.js").read_text(encoding="utf-8")
checks = {
    "revision_37_routes": "/revision-37" in quality_routes and "/revision-37/gates" in quality_routes and "/revision-37/checksum" in quality_routes,
    "api_sync_rev37": "revision37Quality" in api and "revision37Gates" in api and "revision37PackageManifest" in api,
    "ui_rev37_cards": "Rev37 Final Verification" in intel and "Gates → manifest → checksum → release" in intel,
    "docs_rev37": "Final Verification + Packaging" in (ROOT / "docs/REV37_FINAL_VERIFICATION.md").read_text(encoding="utf-8"),
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))

print("REVISION_37_QUALITY_OK")
