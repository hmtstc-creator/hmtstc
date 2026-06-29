#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HMTSTC_OFFLINE_QUALITY_CHECK", "1")
sys.path.insert(0, str(ROOT / "backend"))

REQUIRED = [
    ROOT / "backend/services/live_micro_pilot_procedure_service.py",
    ROOT / "backend/services/real_pilot_service.py",
    ROOT / "backend/routes/real_routes.py",
    ROOT / "backend/routes/quality_routes.py",
    ROOT / "frontend/js/app/api.js",
    ROOT / "frontend/js/pages/intelligence.js",
    ROOT / "docs/REV36_LIVE_MICRO_PILOT_PROCEDURE.md",
]
for path in REQUIRED:
    if not path.exists():
        raise SystemExit(f"MISSING: {path.relative_to(ROOT)}")
for path in (ROOT / "backend").rglob("*.py"):
    py_compile.compile(str(path), doraise=True)
for path in (ROOT / "scripts").glob("*.py"):
    py_compile.compile(str(path), doraise=True)

from services.live_micro_pilot_procedure_service import (  # noqa: E402
    REV36_STEPS,
    build_live_micro_pilot_runbook,
    build_pilot_rehearsal_checklist,
    build_revision_36_quality_report,
    build_tiny_order_plan,
    finalize_pilot_procedure,
    record_pilot_rehearsal,
)
from services.real_trade_state_service import ensure_real_trade_state, unlock_real_trading  # noqa: E402

sample_data = {"real_trade": {"enabled": False, "dry_run": True, "owner_unlocked": False, "pilot": {"active": False}}}
sample_settings = {"bot": {"allocated_usdt": 1000, "usdt_per_position": 5}, "risk": {}}
state = ensure_real_trade_state(sample_data)
unlock_real_trading(state, "qc", minutes=5)
runbook = build_live_micro_pilot_runbook(sample_data, sample_settings)
if len(runbook.get("procedure") or []) != 8:
    raise SystemExit("FAILED: runbook must contain 8 procedure steps")
if [s["id"] for s in REV36_STEPS] != ["readonly_precheck", "dry_run_rehearsal", "confirmation_token_preview", "tiny_real_order_window", "tracking", "reconciliation", "auto_lock", "final_report"]:
    raise SystemExit("FAILED: Rev36 procedure order changed")
checklist = build_pilot_rehearsal_checklist(sample_data, sample_settings)
if checklist.get("total_count") != 8:
    raise SystemExit("FAILED: rehearsal checklist count must be 8")
plan = build_tiny_order_plan(sample_data, sample_settings, {"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 5})
sequence = plan.get("sequence") or []
required_sequence = [
    "GET /api/real/readiness",
    "POST /api/real/orders/dry-run",
    "POST /api/real/orders/preview",
    "POST /api/real/unlock",
    "POST /api/real/orders/place",
    "GET /api/real/positions/lifecycle",
    "POST /api/real/positions/reconcile",
    "POST /api/real/pilot/finalize",
    "GET /api/real/pilot/report",
]
if sequence != required_sequence:
    raise SystemExit("FAILED: tiny order sequence mismatch")
if plan.get("real_order_executed_by_this_endpoint") is not False:
    raise SystemExit("FAILED: tiny order plan endpoint must not execute real order")
recorded = record_pilot_rehearsal(sample_data, sample_settings, user="qc", payload={"note": "quality"})
if recorded.get("rehearsal", {}).get("paper_only") is not True:
    raise SystemExit("FAILED: rehearsal must be paper-only")
final = finalize_pilot_procedure(sample_data, sample_settings, user="qc", reason="quality_finalize")
if final.get("owner_unlocked") is not False or "auto_lock" not in str(final.get("real_lock_reason", "")) and final.get("real_lock_reason") != "quality_finalize":
    raise SystemExit("FAILED: finalize must lock real trading")
quality = build_revision_36_quality_report(sample_data, sample_settings)
if quality.get("status") != "ok":
    raise SystemExit("FAILED: revision 36 quality not ok")

quality_routes = (ROOT / "backend/routes/quality_routes.py").read_text(encoding="utf-8")
real_routes = (ROOT / "backend/routes/real_routes.py").read_text(encoding="utf-8")
api = (ROOT / "frontend/js/app/api.js").read_text(encoding="utf-8")
intel = (ROOT / "frontend/js/pages/intelligence.js").read_text(encoding="utf-8")
service = (ROOT / "backend/services/live_micro_pilot_procedure_service.py").read_text(encoding="utf-8")
checks = {
    "revision_36_quality_routes": "/revision-36" in quality_routes and "revision-36/runbook" in quality_routes and "revision-36/final-report" in quality_routes,
    "pilot_procedure_routes": "/pilot/procedure" in real_routes and "/pilot/finalize" in real_routes and "/pilot/tiny-order-plan" in real_routes,
    "api_sync_rev36": "revision36Quality" in api and "realPilotProcedure" in api and "revision36TinyOrder" in api,
    "ui_rev36_cards": "Rev36 Live Micro Pilot" in intel and "Tiny Order Plan" in intel and "Auto-lock" in intel,
    "runbook_has_required_chain": "readonly_precheck" in service and "dry_run_rehearsal" in service and "confirmation_token_preview" in service and "final_report" in service,
    "no_direct_order_execution": "place_real_order(" not in service and "dry_run_order(" not in service,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))
print("REVISION_36_QUALITY_OK")
