#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.deploy_safety_service import create_runtime_backup, build_backup_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="HMTSTC Rev34 pre-deploy runtime backup")
    parser.add_argument("--label", default="pre_deploy", help="Backup label")
    parser.add_argument("--plan-only", action="store_true", help="Only print backup plan")
    args = parser.parse_args()

    payload = build_backup_plan() if args.plan_only else create_runtime_backup(label=args.label)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload.get("status") not in {"ok", "review"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
