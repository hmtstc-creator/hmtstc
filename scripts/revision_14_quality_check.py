#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import py_compile
import shutil
import subprocess
import sys

os.environ.setdefault("HMTSTC_OFFLINE_QUALITY_CHECK", "true")
os.environ.setdefault("BINANCE_TIMEOUT_SECONDS", "1")
ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def compile_python() -> list[str]:
    errors = []
    for path in BACKEND.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            errors.append(f"python:{path.relative_to(ROOT)}:{exc}")
    return errors


def check_js() -> list[str]:
    errors = []
    for path in (FRONTEND / "js").rglob("*.js"):
        result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            errors.append(f"js:{path.relative_to(ROOT)}:{result.stderr.strip()}")
    return errors


def clean_pycache():
    for path in ROOT.rglob("__pycache__"):
        shutil.rmtree(path, ignore_errors=True)


def check_runtime_leakage() -> list[str]:
    clean_pycache()
    forbidden = [
        "backend/.env",
        "backend/auth_store.json",
        "backend/settings_store.json",
        "backend/shadow_store.json",
        "backend/rule_store.json",
        "backend/real_trade_store.json",
        "backend/audit_store.json",
    ]
    errors = []
    for rel in forbidden:
        if (ROOT / rel).exists():
            errors.append(f"runtime_leak:{rel}")
    for path in ROOT.rglob("*.pyc"):
        errors.append(f"runtime_leak:{path.relative_to(ROOT)}")
    return errors


def functional_checks() -> dict:
    sys.path.insert(0, str(BACKEND))
    from services.binance_service import load_binance_runtime_config, BinanceService
    from services.real_trade_state_service import ensure_real_trade_state, is_unlock_valid
    from services.real_trade_service import build_order_safety_report, build_real_readiness
    from services.revision_14_service import build_revision_14_quality_report

    data = {"bot_running": False, "last_scan": {}, "audit": [], "real_trade": {}}
    state = ensure_real_trade_state(data)
    settings = {"api": {"mode": "shadow"}, "bot": {"allocated_usdt": 1000, "usdt_per_position": 50, "max_open_positions": 1}, "risk": {"daily_loss_limit": 2, "weekly_loss_limit": 5}}
    runtime = load_binance_runtime_config()
    service = BinanceService()
    readiness = build_real_readiness(data, settings)
    safety = build_order_safety_report(data, settings, {"symbol": "BTCUSDT", "side": "BUY", "quote_order_qty": 5})
    quality = build_revision_14_quality_report(data, settings)
    return {
        "revision": quality.get("revision"),
        "dry_run_default": runtime.real_trading_dry_run,
        "real_enabled_default": runtime.real_trading_enabled,
        "owner_unlock_default": is_unlock_valid(state),
        "readiness_status": readiness.get("status"),
        "safety_status": safety.get("status"),
        "quality_status": quality.get("status"),
        "client_has_spot_methods": all(hasattr(service, name) for name in ["ping", "account", "balances", "symbol_filters", "place_market_order"]),
    }


def main() -> int:
    errors = []
    errors.extend(compile_python())
    errors.extend(check_js())
    errors.extend(check_runtime_leakage())
    checks = {}
    try:
        checks = functional_checks()
        if checks.get("revision") != 14:
            errors.append("revision_14_report_failed")
        if checks.get("real_enabled_default") is not False:
            errors.append("real_trading_default_not_locked")
        if checks.get("dry_run_default") is not True:
            errors.append("dry_run_default_not_active")
        if checks.get("owner_unlock_default") is not False:
            errors.append("owner_unlock_default_not_locked")
        if not checks.get("client_has_spot_methods"):
            errors.append("binance_client_methods_missing")
    except Exception as exc:
        errors.append(f"functional:{exc}")
    print(json.dumps({"ok": not errors, "revision": 14, "errors": errors, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
