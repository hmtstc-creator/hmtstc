#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.deploy_safety_service import create_release_zip  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build runtime-safe HMTSTC release zip")
    parser.add_argument("--output", default=str(ROOT.parent / "hmtstc_revizyon_37_full_project.zip"))
    args = parser.parse_args()
    manifest = create_release_zip(Path(args.output), ROOT)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
