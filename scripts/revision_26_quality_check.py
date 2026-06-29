#!/usr/bin/env python3
from __future__ import annotations

import importlib
import py_compile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "backend/services/rule_schema_service.py",
    ROOT / "backend/services/rule_governance_service.py",
    ROOT / "backend/services/revision_26_service.py",
    ROOT / "backend/routes/rule_routes.py",
    ROOT / "backend/routes/quality_routes.py",
]
for file in FILES:
    py_compile.compile(str(file), doraise=True)

sys.path.insert(0, str(ROOT / "backend"))
app = importlib.import_module("main").app
routes = {getattr(route, "path", "") for route in app.routes}
required = {
    "/api/quality/revision-26",
    "/api/quality/revision-26/rule-schema-hardening",
    "/api/quality/revision-26/rule-governance-final",
    "/api/quality/revision-26/rule-lineage",
    "/api/quality/revision-26/rule-impact",
    "/api/quality/revision-26/rule-rollback",
    "/api/rules/governance/final",
    "/api/rules/lineage",
    "/api/rules/impact",
    "/api/rules/{rule_id}/rollback-preview",
}
missing = sorted(required - routes)
if missing:
    raise SystemExit(f"MISSING_ROUTES: {missing}")

from services.rule_schema_service import validate_rule_schema, RULE_SCHEMA_VERSION
from services.revision_26_service import build_revision_26_quality_report

valid_rule = {
    "type": "filter",
    "id": "USER_FILTER_TEST",
    "name": "Test Filter",
    "version": 1,
    "enabled": True,
    "conditions": [{"metric": "quote_volume", "operator": ">=", "value": 1000000}],
    "avoid_conditions": [{"metric": "spread_percent", "operator": ">", "value": 0.35}],
    "min_score": 65,
}
validation = validate_rule_schema(valid_rule)
if not validation.get("valid"):
    raise SystemExit(f"SCHEMA_VALIDATION_FAILED: {validation}")
if not str(RULE_SCHEMA_VERSION).startswith("rev26"):
    raise SystemExit("BAD_SCHEMA_VERSION")
quality = build_revision_26_quality_report("ahmet")
if str(quality.get("revision")) != "26":
    raise SystemExit("BAD_REVISION")
print("REVISION_26_QUALITY_CHECK_OK")
