#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("HMTSTC_OFFLINE_QUALITY_CHECK", "1")


def main() -> int:
    from services.revision_21_service import build_revision_21_quality_report

    data = {
        "positions": [],
        "paper_lab": {"models": []},
        "real_trade": {
            "positions": [],
            "orders": [],
            "owner_unlocked": False,
            "dry_run": True,
            "enabled": False,
        },
    }
    settings = {"capital_usdt": 1000, "slot_count": 20, "slot_size_usdt": 50}
    payload = build_revision_21_quality_report(data, settings)
    required = ["wallet_integrity", "balance_reconciliation", "money_separation", "mismatch_lock", "ui_contract"]
    missing = [k for k in required if k not in payload.get("checks", {})]
    if missing:
        print("REV21_FAIL missing checks", missing)
        return 1
    if payload.get("revision") != 21:
        print("REV21_FAIL wrong revision")
        return 1
    print("REV21_OK", payload.get("status"), payload.get("readiness_score"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
