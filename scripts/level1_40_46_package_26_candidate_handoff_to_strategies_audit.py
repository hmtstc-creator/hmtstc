#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.analysis_service import build_candidate_handoff  # noqa: E402


def main() -> int:
    scan = {
        "scan_id": "scan-26", "time": "2026-06-15T12:00:00", "settings_used": {"min_quote_volume": 1000},
        "candidates": [
            {"symbol": "PASSUSDT", "passed": True, "first_rejection_reason": None},
            {"symbol": "REJECTUSDT", "passed": False, "first_rejection_reason": "low_volatility"},
        ],
        "scan_rows": [
            {"symbol": "PASSUSDT", "passed": True, "first_rejection_reason": None},
            {"symbol": "REJECTUSDT", "passed": False, "first_rejection_reason": "low_volatility"},
        ],
    }
    handoff = build_candidate_handoff(scan)
    analysis = (ROOT / "backend" / "services" / "analysis_service.py").read_text(encoding="utf-8")
    bot = (ROOT / "backend" / "services" / "bot_service.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "frontend" / "js" / "pages" / "dashboard.js").read_text(encoding="utf-8")
    network = (ROOT / "frontend" / "js" / "components" / "liveTradeNetwork.js").read_text(encoding="utf-8")
    storage = (ROOT / "backend" / "core" / "storage.py").read_text(encoding="utf-8")
    dashboard_routes = (ROOT / "backend" / "routes" / "dashboard_routes.py").read_text(encoding="utf-8")
    checks = {
        "handoff_contract_complete": set(handoff).issuperset({"scan_id", "time", "settings_used", "candidates", "scan_rows", "passed"}),
        "only_explicit_passed_candidates": handoff["passed"] == 1 and [row["symbol"] for row in handoff["candidates"]] == ["PASSUSDT"],
        "rejected_row_kept_for_diagnostics": handoff["scan_rows"][1]["first_rejection_reason"] == "low_volatility",
        "scan_payload_builds_handoff": 'payload["candidate_handoff"] = build_candidate_handoff(payload)' in analysis,
        "bot_consumes_handoff_only": "evaluate_strategy_candidates(username, handoff)" in bot and 'strategy_runtime.get("approved_candidates", [])' in bot,
        "dashboard_reads_handoff": "scan.candidate_handoff.candidates" in dashboard and "const networkRows = candidateRows" in dashboard,
        "network_rejects_non_passed": "item && item.passed === true" in network,
        "handoff_persists_in_last_scan": '"candidate_handoff": last_scan.get("candidate_handoff"' in storage,
        "dashboard_api_exposes_handoff": '"candidate_handoff": last_scan.get("candidate_handoff"' in dashboard_routes,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("LEVEL1_40_46_PACKAGE_26_CANDIDATE_HANDOFF_TO_STRATEGIES_AUDIT_FAIL")
        print("failed=" + ",".join(failed))
        return 1
    print("LEVEL1_40_46_PACKAGE_26_CANDIDATE_HANDOFF_TO_STRATEGIES_AUDIT_OK")
    print("status=ok")
    print(f"checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
