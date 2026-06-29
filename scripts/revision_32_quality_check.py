from __future__ import annotations

import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REQUIRED_FILES = [
    "backend/services/portfolio_allocation_final_service.py",
    "backend/services/revision_32_service.py",
    "backend/routes/quality_routes.py",
    "backend/routes/intelligence_routes.py",
    "frontend/js/pages/dashboard.js",
    "frontend/js/pages/intelligence.js",
]

REQUIRED_ENDPOINTS = [
    "/api/intelligence/portfolio-allocation-final",
    "/api/intelligence/usdt-reserve-policy",
    "/api/intelligence/cluster-exposure",
    "/api/intelligence/allocation-audit",
    "/api/quality/revision-32",
    "/api/quality/revision-32/portfolio-allocation",
    "/api/quality/revision-32/usdt-reserve",
    "/api/quality/revision-32/cluster-exposure",
    "/api/quality/revision-32/allocation-audit",
    "/api/quality/revision-32/ui",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            fail(f"Eksik dosya: {rel}")

    svc = importlib.import_module("services.portfolio_allocation_final_service")
    sample = {
        "last_scan": {"scan_rows": [
            {"symbol": "BTCUSDT", "quality_score": 78, "status": "CANDIDATE"},
            {"symbol": "DOGEUSDT", "quality_score": 54, "status": "WATCH"},
        ]},
        "paper_lab": {"models": {}},
    }
    settings = {"bot": {"allocated_usdt": 1000}}
    report = svc.build_portfolio_allocation_final(sample, settings)
    if report.get("revision") != 32:
        fail("Portfolio allocation report revision 32 değil")
    for key in ["reserve_policy", "cluster_exposure", "allocations", "audit_policy"]:
        if key not in report:
            fail(f"Allocation report alanı eksik: {key}")
    if report["reserve_policy"].get("target_reserve_percent", 0) < 70:
        fail("USDT reserve policy çok düşük")

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

    print("REVISION_32_QUALITY_CHECK_OK")


if __name__ == "__main__":
    main()
