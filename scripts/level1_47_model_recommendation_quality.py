#!/usr/bin/env python3
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "backend/services/paper_model_recommendation_quality_service.py",
    "tests/unit/test_model_recommendation_quality.py",
    "tests/api/test_model_recommendation_quality_routes.py",
]
REQUIRED_ROUTE_MARKERS = [
    "/paper-lab/wallet-integrity",
    "/paper-lab/position-integrity",
    "/score-regression",
    "/score-components",
    "/score-history",
    "/recommendation/decision-table",
    "/recommendation/history-final",
    "/recommendation/replay-linkage",
    "/real-paper-divergence-penalty",
    "/quality/model-recommendation",
]
RUNTIME_LEAKS = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
    "backend/runtime_backups",
]


def fail(message: str) -> None:
    print(f"LEVEL1_47_MODEL_RECOMMENDATION_QUALITY_FAIL: {message}")
    raise SystemExit(1)


def main() -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            fail(f"missing required file {rel}")
    for rel in [
        "backend/services/paper_model_recommendation_quality_service.py",
        "backend/routes/model_routes.py",
        "backend/routes/quality_routes.py",
        "tests/unit/test_model_recommendation_quality.py",
        "tests/api/test_model_recommendation_quality_routes.py",
    ]:
        py_compile.compile(str(ROOT / rel), doraise=True)
    model_routes = (ROOT / "backend/routes/model_routes.py").read_text(encoding="utf-8")
    for marker in REQUIRED_ROUTE_MARKERS:
        if marker not in model_routes:
            fail(f"missing model route marker {marker}")
    quality_routes = (ROOT / "backend/routes/quality_routes.py").read_text(encoding="utf-8")
    if "/level1-47/model-recommendation-quality" not in quality_routes:
        fail("missing quality route marker")
    service_text = (ROOT / "backend/services/paper_model_recommendation_quality_service.py").read_text(encoding="utf-8")
    required_funcs = [
        "build_paper_wallet_integrity_report",
        "build_paper_position_integrity_report",
        "build_model_scoring_regression_report",
        "build_model_score_component_explanation",
        "build_recommendation_decision_table",
        "build_recommendation_history_report",
        "build_real_paper_divergence_penalty_report",
        "build_model_score_history_report",
        "build_recommendation_replay_linkage",
        "build_paper_model_recommendation_quality_report",
    ]
    for func in required_funcs:
        if f"def {func}" not in service_text:
            fail(f"missing function {func}")
    if '"auto_apply": False' not in service_text or '"read_only": True' not in service_text:
        fail("missing read-only/auto-apply safety markers")
    for rel in RUNTIME_LEAKS:
        if (ROOT / rel).exists():
            fail(f"runtime leak exists: {rel}")
    print("LEVEL1_47_MODEL_RECOMMENDATION_QUALITY_OK")


if __name__ == "__main__":
    main()
