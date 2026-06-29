#!/usr/bin/env python3
from __future__ import annotations

import importlib
import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "backend/services/model_scoring_service.py",
    ROOT / "backend/services/recommendation_engine_service.py",
    ROOT / "backend/services/revision_25_service.py",
    ROOT / "backend/routes/model_routes.py",
    ROOT / "backend/routes/quality_routes.py",
]

for file in FILES:
    py_compile.compile(str(file), doraise=True)

import sys
sys.path.insert(0, str(ROOT / "backend"))
app = importlib.import_module("main").app
routes = {getattr(route, "path", "") for route in app.routes}
required = {
    "/api/quality/revision-25",
    "/api/quality/revision-25/model-scoring",
    "/api/quality/revision-25/recommendation",
    "/api/quality/revision-25/score-history",
    "/api/quality/revision-25/switch-gate",
    "/api/models/score-final",
    "/api/models/recommendation-final",
}
missing = sorted(required - routes)
if missing:
    raise SystemExit(f"MISSING_ROUTES: {missing}")

from services.model_scoring_service import build_model_score_report
from services.recommendation_engine_service import build_recommendation_final
from services.revision_25_service import build_revision_25_quality_report

sample = {"paper_lab": {"models": {}, "active_real_model_id": None}, "bot_running": False}
settings = {}
score = build_model_score_report(sample, settings)
rec = build_recommendation_final(sample, settings)
quality = build_revision_25_quality_report(sample, settings)
if score.get("formula_version") != "final_score_v1_rev25":
    raise SystemExit("BAD_SCORE_FORMULA")
if rec.get("auto_apply") is not False:
    raise SystemExit("AUTO_APPLY_NOT_FALSE")
if quality.get("revision") != 25:
    raise SystemExit("BAD_REVISION")
print("REVISION_25_QUALITY_CHECK_OK")
