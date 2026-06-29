#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.model_scoring_service import evaluate_strategy_candidates  # noqa: E402


STRATEGY = {
    "id": "STRATEGY_A", "type": "strategy", "name": "A", "enabled": True, "version": 1,
    "strategy_type": "momentum", "risk_level": "medium", "required_metrics": ["ema_signal"],
    "conditions": [{"metric": "ema_signal", "operator": "==", "value": True}],
    "avoid_conditions": [], "entry_rules": [], "exit_rules": [],
}


def main() -> int:
    handoff = {
        "scan_id": "scan-27", "time": "2026-06-15T12:00:00",
        "candidates": [
            {"symbol": "BUYUSDT", "passed": True, "ema_signal": True, "score": 82},
            {"symbol": "WAITUSDT", "passed": True, "ema_signal": False, "score": 75},
            {"symbol": "REJECTUSDT", "passed": False, "ema_signal": True, "score": 90},
        ],
    }
    with patch("services.model_scoring_service.get_active_rules", return_value=([], [STRATEGY])):
        result = evaluate_strategy_candidates("audit", handoff)
    with patch("services.model_scoring_service.get_active_rules", return_value=([], [])):
        empty = evaluate_strategy_candidates("audit", handoff)

    routes = (ROOT / "backend" / "routes" / "rule_routes.py").read_text(encoding="utf-8")
    bot = (ROOT / "backend" / "services" / "bot_service.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "js" / "app" / "rules.js").read_text(encoding="utf-8")
    output = result["outputs"][0]
    checks = {
        "active_strategy_contract": result["active_strategy_ids"] == ["STRATEGY_A"] and result["paper_lab_isolated"] is True,
        "output_schema_complete": set(output) == {"strategy_id", "symbol", "signal", "confidence", "entry_reason", "invalid_reasons"},
        "buy_only_when_conditions_pass": result["passed"] == 1 and result["approved_candidates"][0]["symbol"] == "BUYUSDT",
        "rejected_coin_never_evaluated": all(row["symbol"] != "REJECTUSDT" for row in result["outputs"]),
        "invalid_reasons_are_explicit": any(row["symbol"] == "WAITUSDT" and row["invalid_reasons"] for row in result["outputs"]),
        "no_strategy_blocks_runtime": empty["status"] == "blocked" and empty["reason"] == "no_active_strategy" and empty["passed"] == 0,
        "bot_logs_no_strategy": '"no_active_strategy"' in bot and "approved_candidates" in bot,
        "runtime_endpoints_exist": '"/runtime-contract"' in routes and '"/runtime-evaluate"' in routes,
        "frontend_exposes_runtime_summary": "strategyRuntimeSummary" in frontend and "paper_lab_isolated" in frontend,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("LEVEL1_40_47_PACKAGE_27_STRATEGY_ENGINE_RUNTIME_CONTRACT_AUDIT_FAIL")
        print("failed=" + ",".join(failed))
        return 1
    print("LEVEL1_40_47_PACKAGE_27_STRATEGY_ENGINE_RUNTIME_CONTRACT_AUDIT_OK")
    print("status=ok")
    print(f"checks={len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
