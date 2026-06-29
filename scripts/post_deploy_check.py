#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.deploy_safety_service import build_real_lock_report, build_revision_34_quality_report  # noqa: E402


def fetch_json(url: str, token: str | None = None, timeout: int = 5) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="HMTSTC Rev34 post-deploy smoke check")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--token", default=None, help="Optional bearer token for protected smoke endpoints")
    parser.add_argument("--retries", type=int, default=10)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--offline", action="store_true", help="Run local/offline safety checks only")
    args = parser.parse_args()

    if args.offline:
        payload = {
            "status": "ok",
            "mode": "offline",
            "real_lock": build_real_lock_report({}),
            "revision_34": build_revision_34_quality_report({}, {}),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["real_lock"].get("status") in {"ok", "review"} else 1

    endpoints = [
        ("health", "/health", False),
        ("ops", "/health/ops", False),
        ("real_readiness", "/api/real/readiness", True),
        ("summary", "/api/summary", True),
        ("revision_34", "/api/quality/revision-34", True),
    ]
    results = {}
    last_error = None
    for attempt in range(1, args.retries + 1):
        try:
            for name, path, protected in endpoints:
                results[name] = fetch_json(args.base_url.rstrip("/") + path, token=args.token if protected else None)
            break
        except Exception as exc:
            last_error = str(exc)
            time.sleep(args.sleep)
    else:
        print(json.dumps({"status": "blocked", "error": last_error, "results": results}, ensure_ascii=False, indent=2))
        return 1

    blockers = []
    if results.get("health", {}).get("status") not in {"healthy", "ok"}:
        blockers.append("health_not_ok")
    ops_deploy = results.get("ops", {}).get("deploy_safety", {})
    real_lock = ops_deploy.get("real_lock", {})
    if real_lock.get("status") == "blocked" or real_lock.get("real_trading_locked") is False:
        blockers.append("real_trading_not_locked")
    if results.get("summary", {}).get("status") not in {"ok", "partial"}:
        blockers.append("summary_not_available")
    if results.get("revision_34", {}).get("status") == "blocked":
        blockers.append("revision_34_quality_blocked")

    payload = {"status": "ok" if not blockers else "blocked", "blockers": blockers, "results": results}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
