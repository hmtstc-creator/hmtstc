#!/usr/bin/env python3
"""Local static/smoke quality check for HMTSTC Revizyon 10.

This script intentionally avoids live Binance calls and runtime secrets. It checks
backend imports, app route registration, the API contract matrix, and the quality
report builder with a synthetic scan state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from core.storage import normalize_settings  # noqa: E402
from main import app  # noqa: E402
from services.system_audit_service import build_api_contract_matrix, build_revision10_quality_report  # noqa: E402


def main() -> int:
    routes = {getattr(route, "path", "") for route in app.routes}
    required = {
        "/health",
        "/health/ops",
        "/api/bot/status",
        "/api/bot/scan",
        "/api/models/recommendation",
        "/api/intelligence/overview",
        "/api/quality/api-contract",
        "/api/quality/revision-10",
    }
    missing = sorted(required - routes)
    if missing:
        print(json.dumps({"status": "failed", "missing_routes": missing}, ensure_ascii=False, indent=2))
        return 1

    settings = normalize_settings({})
    data = {
        "bot_running": False,
        "last_scan": {
            "status": "ok",
            "live": True,
            "scanned": 120,
            "candidates_count": 1,
            "scan_diagnostics": {"mode": "synthetic"},
            "scan_rows": [
                {"symbol": "BTCUSDT", "price": 100, "score": 72, "quality_score": 82, "volatility": 2.1, "quote_volume": 25_000_000},
                {"symbol": "TESTUSDT", "price": 1, "score": 25, "quality_score": 25, "volatility": 0.2, "quote_volume": 100_000, "rejection_reasons": ["low_quality_score"]},
            ],
            "candidates": [{"symbol": "BTCUSDT", "price": 100, "score": 72, "quality_score": 82, "volatility": 2.1, "quote_volume": 25_000_000}],
            "rejection_breakdown": {"low_quality_score": 1},
        },
    }
    contract = build_api_contract_matrix()
    report = build_revision10_quality_report(data, settings)
    payload = {
        "status": "ok",
        "route_count": len(routes),
        "contract_count": contract.get("count"),
        "quality_score": report.get("product_readiness", {}).get("score"),
        "revision": report.get("revision"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
