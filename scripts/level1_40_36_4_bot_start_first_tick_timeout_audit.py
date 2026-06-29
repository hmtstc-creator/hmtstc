#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
MAIN = BACKEND / "main.py"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
LOOP_CONTROL = BACKEND / "infrastructure" / "runtime" / "bot_loop_control.py"
ANALYSIS = BACKEND / "services" / "analysis_service.py"
MARKET = BACKEND / "services" / "market_service.py"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
DASHBOARD_ROUTES = BACKEND / "routes" / "dashboard_routes.py"
BINANCE_ROUTES = BACKEND / "routes" / "binance_routes.py"
BOT_JS = ROOT / "frontend" / "js" / "app" / "bot.js"
PRIOR = ROOT / "docs" / "LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT.md"


def _text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _function(path: Path, name: str) -> str:
    text = _text(path)
    tree = ast.parse(text, filename=str(path))
    node = next((item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name), None)
    if node is None:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def _guard_runtime_probe() -> dict[str, Any]:
    text = _text(BOT_SERVICE)
    tree = ast.parse(text, filename=str(BOT_SERVICE))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "run_bot_tick_guarded")
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "run_bot_tick": lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("scan_timeout")),
        "now_iso": lambda: "finished",
    }
    exec(compile(module, str(BOT_SERVICE), "exec"), namespace)
    state = {"tick_in_progress": True}
    raised = False
    try:
        namespace["run_bot_tick_guarded"](state, {}, limit=100)
    except TimeoutError:
        raised = True
    return {"raised": raised, "tick_in_progress": state.get("tick_in_progress"), "last_tick_finished_at": state.get("last_tick_finished_at")}


def build_report() -> dict[str, Any]:
    main = _text(MAIN)
    bot_service = _text(BOT_SERVICE)
    loop_control = _text(LOOP_CONTROL)
    analysis = _text(ANALYSIS)
    market = _text(MARKET)
    bot_routes = _text(BOT_ROUTES)
    dashboard = _text(DASHBOARD_ROUTES)
    binance_routes = _text(BINANCE_ROUTES)
    bot_js = _text(BOT_JS)
    start_route = _function(BOT_ROUTES, "bot_start")
    last_scan_route = _function(BOT_ROUTES, "bot_last_scan")
    bundle_route = _function(DASHBOARD_ROUTES, "dashboard_bundle")
    probe = _guard_runtime_probe()
    prior_status = json.loads(_text(PRIOR)).get("status")

    checks = {
        "first_tick_timeout_seconds_at_most_25": "RESTORE_FIRST_TICK_TIMEOUT_SECONDS = 25" in loop_control,
        "tick_in_progress_finally_reset": "def run_bot_tick_guarded" in bot_service and "finally:" in _function(BOT_SERVICE, "run_bot_tick_guarded") and probe["raised"] and probe["tick_in_progress"] is False,
        "failed_bot_clears_requested_running": 'data["requested_running"] = False' in main and '"mode": "heartbeat_only"' in start_route and 'ensure_bot_loop_running' not in start_route,
        "failed_bot_clears_tick_lock": 'data["tick_in_progress"] = False' in main and 'data["tick_in_progress"] = False' in loop_control,
        "start_endpoint_does_not_wait_for_first_tick": "run_bot_tick" not in start_route and "scan_market" not in start_route and "RESTORE_FIRST_TICK_WAIT_SECONDS = 0.25" in loop_control,
        "bot_loop_scan_timeout_present": "timeout_seconds=20" in bot_service and "scan_deadline" in analysis,
        "deep_analysis_timeout_present": "deep_analysis_timeout_seconds=15" in bot_service and "deep_deadline" in analysis,
        "network_calls_use_remaining_timeout": "timeout=_remaining_timeout" in analysis or "_fetch_klines_with_timeout" in analysis and "timeout=max(0.1" in market,
        "cpu_throttle_40_36_3_preserved": prior_status == "ok" and "MIN_TICK_INTERVAL_SECONDS = 30" in main and "BOT_LOOP_ERROR_BACKOFF_SECONDS = 60" in main,
        "last_scan_endpoint_is_cached_store_read": "load_shadow" in last_scan_route and "scan_market" not in last_scan_route and "get_market_symbols" not in last_scan_route,
        "dashboard_bundle_does_not_trigger_scan": "scan_market" not in bundle_route and "run_bot_tick" not in bundle_route,
        "public_market_read_has_short_timeout": "timeout=3 if not strict else 10" in binance_routes,
        "frontend_start_200_not_generic_error": "if ((result || {}).ok === false)" in bot_js and "this.checkFirstTickResult();" in bot_js,
        "frontend_first_tick_timeout_message_present": "Bot ilk taramada zaman aşımına düştü. CPU kilidi önlendi." in bot_js,
    }
    blockers = [f"{key}=false" for key, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "guard_runtime_probe": probe,
        "prior_40_36_3_status": prior_status,
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36.4 Bot Start First Tick Timeout Audit", "", "## Ozet", "",
        f"- Durum: `{report['status']}`",
        f"- First tick timeout: `{_yn(report['first_tick_timeout_seconds_at_most_25'])}`",
        f"- Finally unlock: `{_yn(report['tick_in_progress_finally_reset'])}`",
        f"- Non-blocking start: `{_yn(report['start_endpoint_does_not_wait_for_first_tick'])}`",
        f"- Scan timeout: `{_yn(report['bot_loop_scan_timeout_present'])}`",
        f"- Frontend timeout mesaji: `{_yn(report['frontend_first_tick_timeout_message_present'])}`",
        "", "## Kontroller", "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    lines.extend(f"- BLOCKER: {item}" for item in report["blockers"]) if report["blockers"] else lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Bot start first tick timeout kalite kapisi temiz." if report["status"] == "ok" else "Bot start first tick timeout blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"first_tick_timeout_seconds_at_most_25={str(report['first_tick_timeout_seconds_at_most_25']).lower()}")
    print(f"tick_in_progress_finally_reset={str(report['tick_in_progress_finally_reset']).lower()}")
    print(f"start_endpoint_does_not_wait_for_first_tick={str(report['start_endpoint_does_not_wait_for_first_tick']).lower()}")
    print(f"bot_loop_scan_timeout_present={str(report['bot_loop_scan_timeout_present']).lower()}")
    print(f"frontend_first_tick_timeout_message_present={str(report['frontend_first_tick_timeout_message_present']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
