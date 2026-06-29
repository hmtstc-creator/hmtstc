#!/usr/bin/env python3
from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
REQUIRED = [
    ROOT / "backend/services/ai_analyst_safe_mode_service.py",
    ROOT / "backend/services/agent_service.py",
    ROOT / "backend/services/llm_service.py",
    ROOT / "backend/routes/agent_routes.py",
    ROOT / "backend/routes/quality_routes.py",
    ROOT / "frontend/js/app/api.js",
    ROOT / "frontend/js/pages/intelligence.js",
    ROOT / "docs/REV35_AI_ANALYST_SAFE_MODE.md",
]
for path in REQUIRED:
    if not path.exists():
        raise SystemExit(f"MISSING: {path.relative_to(ROOT)}")
for path in (ROOT / "backend").rglob("*.py"):
    py_compile.compile(str(path), doraise=True)
for path in (ROOT / "scripts").glob("*.py"):
    py_compile.compile(str(path), doraise=True)

from services.ai_analyst_safe_mode_service import (  # noqa: E402
    build_ai_safe_mode_policy,
    build_ai_suggestion,
    build_no_trade_authority_report,
    build_revision_35_quality_report,
    enqueue_paper_suggestion,
)

sample_data = {
    "last_scan": {
        "live": True,
        "candidates": [{"symbol": "BTCUSDT", "score": 82.5, "price": 65000, "reason": "fixture"}],
    }
}
sample_settings = {"bot": {"allocated_usdt": 1000, "usdt_per_position": 100}, "risk": {}}
policy = build_ai_safe_mode_policy()
if policy["authority"]["can_place_real_order"] is not False:
    raise SystemExit("FAILED: ai can_place_real_order must be false")
blocked = build_ai_suggestion(sample_data, sample_settings, "gerçek emir aç", user="qc", role="owner")
if blocked.get("status") != "blocked" or blocked.get("real_trade_authority") is not False:
    raise SystemExit("FAILED: real-order prompt must be blocked")
queued = enqueue_paper_suggestion(sample_data, sample_settings, "paper izleme önerisi üret", user="qc", role="owner")
if not queued.get("queued_item") or queued["queued_item"].get("paper_only") is not True:
    raise SystemExit("FAILED: paper queue item missing")
quality = build_revision_35_quality_report(sample_data, sample_settings)
if quality.get("status") != "ok":
    raise SystemExit("FAILED: revision 35 quality not ok")
no_trade = build_no_trade_authority_report()
if no_trade.get("real_trade_authority") is not False:
    raise SystemExit("FAILED: no_trade_authority false expected")

quality_routes = (ROOT / "backend/routes/quality_routes.py").read_text(encoding="utf-8")
agent_routes = (ROOT / "backend/routes/agent_routes.py").read_text(encoding="utf-8")
api = (ROOT / "frontend/js/app/api.js").read_text(encoding="utf-8")
intel = (ROOT / "frontend/js/pages/intelligence.js").read_text(encoding="utf-8")
service = (ROOT / "backend/services/ai_analyst_safe_mode_service.py").read_text(encoding="utf-8")
checks = {
    "revision_35_quality_routes": "/revision-35" in quality_routes and "revision-35/no-trade-authority" in quality_routes,
    "agent_suggestions_endpoint": "/suggestions" in agent_routes and "/paper-queue" in agent_routes and "/prompt-log" in agent_routes,
    "api_sync_rev35": "revision35Quality" in api and "aiPaperQueue35" in api and "aiPromptLog35" in api,
    "ui_rev35_cards": "Rev35 AI Safe Mode" in intel and "AI Paper Queue" in intel,
    "no_real_trade_import": "from services.real_trade_service" not in service and "import real_trade_service" not in service and "from routes.real_routes" not in service,
    "prompt_logging": "append_ai_prompt_log" in service and "prompt_hash" in service and "output_hash" in service,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))
print("REVISION_35_QUALITY_OK")
