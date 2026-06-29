#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from services.execution_calibration_service import build_execution_calibration_report, build_simulator_drift_report
from services.revision_24_service import build_revision_24_quality_report


def main() -> int:
    sample_data = {
        "open_positions": [
            {
                "id": "paper_sample_1",
                "symbol": "BTCUSDT",
                "model_id": "model_a",
                "strategy_id": "strategy_a",
                "entry": 100,
                "quantity": 1,
                "execution_entry": {
                    "execution_quality_score": 78,
                    "spread_percent": 0.04,
                    "slippage_percent": 0.05,
                    "commission_usdt": 0.01,
                    "source_price": 100,
                    "executed_price": 100.05,
                },
            }
        ],
        "real_trade": {
            "orders": [
                {"order_id": "dry_1", "dry_run": True, "symbol": "BTCUSDT", "execution_quality_score": 74, "status": "dry_run_ready"}
            ],
            "positions": [],
        },
    }
    settings = {"risk": {"max_spread_percent": 0.35, "max_slippage_percent": 0.35}}
    report = build_revision_24_quality_report(sample_data, settings)
    calibration = build_execution_calibration_report(sample_data, settings)
    drift = build_simulator_drift_report(sample_data, settings)
    assert report["revision"] == 24
    assert calibration["sample_count"] >= 2
    assert "paper" in calibration["source_summary"]
    assert "dry_run" in calibration["source_summary"]
    assert "drift" in drift
    print("REVISION_24_QUALITY_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
