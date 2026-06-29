#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
ANALYSIS = BACKEND / "services" / "analysis_service.py"
PAPER_LAB = BACKEND / "services" / "paper_lab_service.py"
WORKER = BACKEND / "infrastructure" / "runtime" / "bot_scan_worker.py"
LOOP_CONTROL = BACKEND / "infrastructure" / "runtime" / "bot_loop_control.py"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
BINANCE_ROUTES = BACKEND / "routes" / "binance_routes.py"
DASHBOARD_ROUTES = BACKEND / "routes" / "dashboard_routes.py"
MAIN = BACKEND / "main.py"
CONFIG = BACKEND / "core" / "config.py"
BOT_JS = ROOT / "frontend" / "js" / "app" / "bot.js"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
PRIOR = {
    "40.36.3": ROOT / "docs" / "LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT.json",
    "40.36.4": ROOT / "docs" / "LEVEL1_40_36_4_BOT_START_FIRST_TICK_TIMEOUT_AUDIT.json",
}
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT.md"


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


def _generation_guard_probe() -> dict[str, bool]:
    source = _function(WORKER, "_worker_write_allowed")
    tree = ast.parse(source)
    node = tree.body[0]
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {"threading": threading}
    exec(compile(module, str(WORKER), "exec"), namespace)
    allowed = namespace["_worker_write_allowed"]
    event = threading.Event()
    base = {
        "scan_worker_generation": 7,
        "requested_running": True,
        "engine_status": "running",
        "scan_cancel_requested": False,
    }
    return {
        "matching_generation_allowed": bool(allowed(dict(base), 7, event)),
        "stale_generation_blocked": not allowed(dict(base), 6, event),
        "stopped_request_blocked": not allowed({**base, "requested_running": False}, 7, event),
        "failed_engine_blocked": not allowed({**base, "engine_status": "failed"}, 7, event),
        "cancel_state_blocked": not allowed({**base, "scan_cancel_requested": True}, 7, event),
    }


def build_report() -> dict[str, Any]:
    bot_service = _text(BOT_SERVICE)
    analysis = _text(ANALYSIS)
    paper_lab = _text(PAPER_LAB)
    worker = _text(WORKER)
    loop_control = _text(LOOP_CONTROL)
    bot_routes = _text(BOT_ROUTES)
    binance_routes = _text(BINANCE_ROUTES)
    dashboard_routes = _text(DASHBOARD_ROUTES)
    main = _text(MAIN)
    config = _text(CONFIG)
    bot_js = _text(BOT_JS)
    coin_filter_js = _text(COIN_FILTER_JS)
    first_tick = _function(BOT_SERVICE, "run_bot_first_tick_guarded")
    start_route = _function(BOT_ROUTES, "bot_start")
    last_scan_route = _function(BOT_ROUTES, "bot_last_scan")
    bundle_route = _function(DASHBOARD_ROUTES, "dashboard_bundle")
    probe = _generation_guard_probe()
    prior_statuses = {name: json.loads(_text(path)).get("status") for name, path in PRIOR.items()}

    state_fields = [
        "active_scan_worker",
        "scan_worker_started_at",
        "scan_worker_deadline_at",
        "scan_cancel_requested",
        "scan_worker_generation",
    ]
    checks = {
        "first_tick_lightweight_mode_present": "def run_bot_first_tick_guarded" in bot_service and '"mode": "heartbeat_first_tick"' in first_tick,
        "first_tick_does_not_use_deep_analysis": "scan_market" not in first_tick and "deep_analysis" not in first_tick and "run_paper_lab_tick" not in first_tick,
        "start_endpoint_is_non_blocking": "scan_market" not in start_route and "run_bot_tick" not in start_route and "run_bot_first_tick" not in start_route,
        "scan_worker_state_fields_present": all(f'"{field}"' in config for field in state_fields),
        "scan_worker_runs_in_separate_thread": "threading.Thread(" in worker and "daemon=True" in worker and "run_bot_tick_guarded(" in worker,
        "scan_worker_generation_guard_present": "_worker_write_allowed" in worker and all(probe.values()),
        "timeout_cancels_scan_worker": "cancel_scan_worker(username, reason=\"first_tick_timeout\")" in loop_control,
        "stop_and_emergency_cancel_worker": bot_routes.count("cancel_scan_worker(") >= 3,
        "failed_state_cpu_guard_present": all(value in loop_control for value in [
            'data["active_scan_worker"] = False',
            'data["scan_cancel_requested"] = True',
            'data["tick_in_progress"] = False',
            'data["requested_running"] = False',
        ]),
        "scan_loop_cancel_deadline_guard_present": "cancel_requested" in analysis and analysis.count("_cancelled(cancel_requested") >= 4,
        "deep_analysis_cancel_deadline_guard_present": "analyze_symbol(symbol, settings, deadline=deep_deadline, cancel_requested=cancel_requested)" in analysis,
        "strategy_filter_cancel_guard_present": "cancel_requested" in paper_lab and "evaluate_rule" in paper_lab and "evaluate_filter" in paper_lab,
        "deep_network_timeout_uses_remaining_deadline": "_remaining_timeout(deadline" in analysis and "deadline=deadline" in bot_service,
        "public_market_timeout_at_most_three_seconds": "timeout=3 if not strict else 10" in binance_routes,
        "last_scan_endpoint_is_cached_read": "load_shadow" in last_scan_route and "scan_market" not in last_scan_route and "get_market_symbols" not in last_scan_route,
        "dashboard_bundle_does_not_start_scan": "scan_market" not in bundle_route and "run_bot_tick" not in bundle_route and "start_scan_worker" not in bundle_route,
        "frontend_start_success_message_present": "Bot başlatıldı. İlk piyasa taraması hazırlanıyor." in bot_js and "if ((result || {}).ok === false)" in bot_js,
        "coinfilter_cached_empty_message_present": "Henüz canlı tarama yok" in coin_filter_js and "coinFilterScanLoading" in coin_filter_js,
        "scheduler_uses_light_first_tick_and_background_worker": "run_bot_first_tick_guarded(" in main and "start_scan_worker(" in main,
        "prior_40_36_3_and_40_36_4_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "generation_guard_probe": probe,
        "prior_audit_statuses": prior_statuses,
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36.5 Hard Cancel Bot Scan Worker Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- Lightweight first tick: `{_yn(report['first_tick_lightweight_mode_present'])}`",
        f"- Separate scan worker: `{_yn(report['scan_worker_runs_in_separate_thread'])}`",
        f"- Generation guard: `{_yn(report['scan_worker_generation_guard_present'])}`",
        f"- Timeout cancel: `{_yn(report['timeout_cancels_scan_worker'])}`",
        f"- CoinFilter cached view: `{_yn(report['coinfilter_cached_empty_message_present'])}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    if report["blockers"]:
        lines.extend(f"- BLOCKER: {item}" for item in report["blockers"])
    else:
        lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Lightweight first tick, generation guard ve scan worker cancel kalite kapisi temiz." if report["status"] == "ok" else "Hard cancel scan worker kalite kapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"first_tick_lightweight_mode_present={str(report['first_tick_lightweight_mode_present']).lower()}")
    print(f"scan_worker_generation_guard_present={str(report['scan_worker_generation_guard_present']).lower()}")
    print(f"timeout_cancels_scan_worker={str(report['timeout_cancels_scan_worker']).lower()}")
    print(f"coinfilter_cached_empty_message_present={str(report['coinfilter_cached_empty_message_present']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
