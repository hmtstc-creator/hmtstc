#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

checks = []

def check(name, ok, detail=""):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})

try:
    importlib.import_module("services.coin_universe_final_service")
    importlib.import_module("services.revision_30_service")
    check("rev30_services_import", True)
except Exception as exc:
    check("rev30_services_import", False, str(exc))

try:
    from services.revision_30_service import build_revision_30_quality_report
    sample = {
        "last_scan": {
            "status": "ok",
            "scan_id": "sample",
            "scanned": 2,
            "eligible_universe_count": 2,
            "universe_total_seen": 4,
            "candidates_count": 1,
            "rejected_count": 1,
            "scan_rows": [
                {"symbol": "BTCUSDT", "status": "PASSED", "score": 75, "quality_score": 82, "analysis_depth": "technical"},
                {"symbol": "ABCUSDT", "status": "REJECT", "reason": "low_quote_volume", "rejection_reasons": ["low_quote_volume"], "score": 12, "quality_score": 25},
            ],
            "candidates": [{"symbol": "BTCUSDT", "score": 75, "quality_score": 82}],
            "rejection_breakdown": {"low_quote_volume": 1},
            "scan_diagnostics": {"deep_analyzed_count": 1},
        }
    }
    report = build_revision_30_quality_report(sample, {})
    check("rev30_quality_report", report.get("status") in {"ok", "review", "blocked"}, report.get("status", ""))
    check("rev30_universe_summary", ((report.get("summary") or {}).get("coin_universe") or {}).get("summary", {}).get("eligible_spot_universe") == 2)
except Exception as exc:
    check("rev30_quality_report", False, str(exc))

try:
    from main import app
    routes = {route.path for route in app.routes}
    required = {
        "/api/quality/revision-30",
        "/api/quality/revision-30/coin-universe",
        "/api/quality/revision-30/reject-distribution",
        "/api/quality/revision-30/scan-history",
        "/api/quality/revision-30/scan-replay",
        "/api/quality/revision-30/scan-explanation",
        "/api/bot/scan-history",
        "/api/bot/scan-replay",
    }
    missing = sorted(required - routes)
    check("rev30_routes_registered", not missing, ", ".join(missing))
except Exception as exc:
    check("rev30_routes_registered", False, str(exc))

for path in [
    ROOT / "frontend" / "js" / "pages" / "coinFilter.js",
    ROOT / "frontend" / "js" / "pages" / "intelligence.js",
    ROOT / "frontend" / "js" / "app" / "api.js",
]:
    check(f"frontend_file_exists:{path.name}", path.exists())
    if path.exists():
        text = path.read_text(encoding="utf-8")
        check(f"frontend_rev30_marker:{path.name}", "Rev30" in text or "revision30" in text)

runtime_forbidden = [
    BACKEND / ".env",
    BACKEND / "auth_store.json",
    BACKEND / "settings_store.json",
    BACKEND / "shadow_store.json",
    BACKEND / "runtime_backups",
]
leaks = [str(p.relative_to(ROOT)) for p in runtime_forbidden if p.exists()]
check("runtime_file_leakage", not leaks, ", ".join(leaks))

ok = all(item["ok"] for item in checks)
print(json.dumps({"status": "ok" if ok else "failed", "revision": 30, "checks": checks}, indent=2, ensure_ascii=False))
sys.exit(0 if ok else 1)
