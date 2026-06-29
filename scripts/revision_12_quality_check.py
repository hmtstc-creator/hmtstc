#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.config import DEFAULT_USER  # noqa: E402
from core.storage import load_shadow, load_settings  # noqa: E402
from services.revision_12_service import build_revision_12_quality_report  # noqa: E402


def main() -> int:
    data = load_shadow(DEFAULT_USER)
    data["username"] = DEFAULT_USER
    settings = load_settings(DEFAULT_USER)
    report = build_revision_12_quality_report(data, settings, username=DEFAULT_USER, run_live_scan=False)
    output = {
        "status": report.get("status"),
        "revision": report.get("revision"),
        "score": report.get("score"),
        "state": report.get("state"),
        "blockers": report.get("blockers"),
        "reviews": report.get("reviews"),
        "block_count": len(report.get("blocks") or {}),
        "next_gate": report.get("next_gate"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if report.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
