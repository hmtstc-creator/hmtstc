#!/usr/bin/env python3
from __future__ import annotations

import importlib
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "backend/services/settings_unit_service.py",
    ROOT / "backend/services/settings_risk_service.py",
    ROOT / "backend/services/revision_27_service.py",
    ROOT / "backend/routes/settings_routes.py",
    ROOT / "backend/routes/quality_routes.py",
]
for file in FILES:
    py_compile.compile(str(file), doraise=True)

sys.path.insert(0, str(ROOT / "backend"))
app = importlib.import_module("main").app
routes = {getattr(route, "path", "") for route in app.routes}
required = {
    "/api/settings/risk-impact",
    "/api/settings/risk-impact/current",
    "/api/settings/rollback-preview",
    "/api/settings/rollback",
    "/api/quality/revision-27",
    "/api/quality/revision-27/settings-final",
    "/api/quality/revision-27/risk-final",
    "/api/quality/revision-27/settings-rollback",
    "/api/quality/revision-27/settings-ui",
}
missing = sorted(required - routes)
if missing:
    raise SystemExit(f"MISSING_ROUTES: {missing}")

from services.settings_unit_service import normalize_settings_units
from services.settings_risk_service import build_real_readiness_impact, build_worst_case_risk_matrix
from services.revision_27_service import build_revision_27_quality_report

sample = {
    "bot": {"allocated_usdt": "1000", "usdt_per_position": "50", "max_open_positions": "5"},
    "risk": {"stop_loss": "0,75", "take_profit": "2", "daily_loss_limit": "30", "weekly_loss_limit": "90"},
}
normalized = normalize_settings_units(sample)
if abs(float(normalized["risk"]["stop_loss"]) - 0.75) > 1e-9:
    raise SystemExit("PERCENT_NORMALIZATION_FAILED")
if float(normalized["bot"]["allocated_usdt"]) != 1000:
    raise SystemExit("MONEY_NORMALIZATION_FAILED")
matrix = build_worst_case_risk_matrix(normalized)
if not matrix.get("scenarios"):
    raise SystemExit("RISK_MATRIX_EMPTY")
impact = build_real_readiness_impact(normalized)
if "real_trade_policy" not in impact:
    raise SystemExit("READINESS_IMPACT_MISSING_POLICY")
quality = build_revision_27_quality_report(normalized, {"settings_history": []})
if str(quality.get("revision")) != "27":
    raise SystemExit("BAD_REVISION")
print("REVISION_27_QUALITY_CHECK_OK")
