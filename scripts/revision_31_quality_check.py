from __future__ import annotations

import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REQUIRED_FILES = [
    "backend/services/market_intelligence_final_service.py",
    "backend/services/revision_31_service.py",
    "backend/routes/quality_routes.py",
    "backend/routes/intelligence_routes.py",
    "frontend/js/pages/intelligence.js",
    "frontend/js/pages/dashboard.js",
]

REQUIRED_ENDPOINTS = [
    "/api/quality/revision-31",
    "/api/quality/revision-31/market-regime",
    "/api/quality/revision-31/orderbook",
    "/api/quality/revision-31/no-trade-cooldown",
    "/api/quality/revision-31/ui",
    "/api/intelligence/market-intelligence-final",
    "/api/intelligence/regime-strategy-match",
    "/api/intelligence/orderbook-final",
    "/api/intelligence/no-trade-final",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            fail(f"Eksik dosya: {rel}")

    svc = importlib.import_module("services.market_intelligence_final_service")
    sample_data = {
        "last_scan": {
            "scan_rows": [
                {"symbol": "BTCUSDT", "score": 72, "quality_score": 74, "volatility": 1.2, "change_percent": 1.1, "status": "CANDIDATE"},
                {"symbol": "ETHUSDT", "score": 66, "quality_score": 67, "volatility": 1.5, "change_percent": 0.8, "status": "WATCH"},
            ],
            "candidates": [{"symbol": "BTCUSDT", "score": 72}],
        }
    }
    report = svc.build_market_intelligence_final_report(sample_data, {})
    if report.get("revision") != 31:
        fail("Market intelligence report revision 31 değil")
    for key in ["regime_strategy_match", "orderbook_intelligence", "no_trade_cooldown", "policy"]:
        if key not in report:
            fail(f"Market intelligence report alanı eksik: {key}")

    app_module = importlib.import_module("main")
    route_paths = {getattr(route, "path", "") for route in app_module.app.routes}
    for path in REQUIRED_ENDPOINTS:
        if path not in route_paths:
            fail(f"Endpoint kayıtlı değil: {path}")

    forbidden = [
        "backend/.env",
        "backend/auth_store.json",
        "backend/settings_store.json",
        "backend/shadow_store.json",
        "backend/runtime_backups",
    ]
    for rel in forbidden:
        if (ROOT / rel).exists():
            fail(f"Runtime dosyası pakete sızmış: {rel}")

    print("REVISION_31_QUALITY_CHECK_OK")


if __name__ == "__main__":
    main()
