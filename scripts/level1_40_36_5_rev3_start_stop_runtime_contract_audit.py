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
FLAGS = BACKEND / "infrastructure" / "runtime" / "bot_runtime_flags.py"
MAIN = BACKEND / "main.py"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
DASHBOARD_ROUTES = BACKEND / "routes" / "dashboard_routes.py"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
RUNTIME_TRUTH = BACKEND / "services" / "bot_runtime_truth_service.py"
LOOP_CONTROL = BACKEND / "infrastructure" / "runtime" / "bot_loop_control.py"
SCAN_WORKER = BACKEND / "infrastructure" / "runtime" / "bot_scan_worker.py"
BOT_JS = ROOT / "frontend" / "js" / "app" / "bot.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
PRIOR = {
    "rev2": ROOT / "docs" / "LEVEL1_40_36_5_REV2_FIRST_TICK_HEARTBEAT_AUDIT.json",
    "hard_cancel": ROOT / "docs" / "LEVEL1_40_36_5_HARD_CANCEL_BOT_SCAN_WORKER_AUDIT.json",
}
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_5_REV3_START_STOP_RUNTIME_CONTRACT_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_5_REV3_START_STOP_RUNTIME_CONTRACT_AUDIT.md"


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


def _runtime_probe() -> dict[str, Any]:
    text = _text(BOT_SERVICE)
    tree = ast.parse(text, filename=str(BOT_SERVICE))
    names = {"_safe_int", "start_bot", "stop_bot"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    counter = {"value": 0}

    def now_iso() -> str:
        counter["value"] += 1
        return f"2026-06-14T15:00:0{counter['value']}+00:00"

    namespace: dict[str, Any] = {
        "now_iso": now_iso,
        "append_log": lambda *args, **kwargs: None,
        "record_performance_point": lambda *args, **kwargs: None,
    }
    exec(compile(module, str(BOT_SERVICE), "exec"), namespace)
    state = {
        "requested_running": False,
        "bot_running": False,
        "engine_status": "stopped",
        "primary_runtime_problem": "old_problem",
        "tick_in_progress": True,
        "active_scan_worker": True,
        "scan_cancel_requested": True,
    }
    namespace["start_bot"](state, mode="paper")
    started = dict(state)
    namespace["start_bot"](state, mode="paper")
    idempotent_started_at = state.get("bot_started_at") == started.get("bot_started_at")
    namespace["stop_bot"](state, reason="audit_stop")
    stopped = dict(state)
    return {"started": started, "stopped": stopped, "idempotent_started_at": idempotent_started_at}


def _call_locations() -> dict[str, list[str]]:
    paths = [MAIN, BOT_ROUTES, DASHBOARD_ROUTES, BOT_SERVICE, RUNTIME_TRUTH, LOOP_CONTROL, SCAN_WORKER]
    patterns = {
        "scan_market": [],
        "start_scan_worker": [],
        "active_scan_worker_true": [],
        "deep_analysis_true": [],
        "create_task": [],
        "thread_or_process": [],
    }
    for path in paths:
        text = _text(path)
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            location = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name == "scan_market":
                    patterns["scan_market"].append(location)
                if name == "start_scan_worker":
                    patterns["start_scan_worker"].append(location)
                if name == "create_task":
                    patterns["create_task"].append(location)
                if name in {"Thread", "Process"}:
                    patterns["thread_or_process"].append(location)
                if any(keyword.arg == "deep_analysis" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords):
                    patterns["deep_analysis_true"].append(location)
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                for target in targets:
                    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and target.slice.value == "active_scan_worker" and isinstance(value, ast.Constant) and value.value is True:
                        patterns["active_scan_worker_true"].append(location)
    return patterns


def build_report() -> dict[str, Any]:
    flags = _text(FLAGS)
    start_service = _function(BOT_SERVICE, "start_bot")
    stop_service = _function(BOT_SERVICE, "stop_bot")
    start_route = _function(BOT_ROUTES, "bot_start")
    status_route = _function(BOT_ROUTES, "bot_status")
    dashboard_bundle = _function(DASHBOARD_ROUTES, "dashboard_bundle")
    scan_worker_start = _function(SCAN_WORKER, "start_scan_worker")
    bot_js = _text(BOT_JS)
    dashboard_js = _text(DASHBOARD_JS)
    main = _text(MAIN)
    runtime_truth = _text(RUNTIME_TRUTH)
    probe = _runtime_probe()
    locations = _call_locations()
    prior_statuses = {name: json.loads(_text(path)).get("status") for name, path in PRIOR.items()}

    started = probe["started"]
    stopped = probe["stopped"]
    read_paths = status_route + "\n" + dashboard_bundle
    forbidden_start = ["scan_market", "start_scan_worker", "deep_analysis=True", "run_paper_lab_tick", "create_task", "Thread(", "Process("]
    forbidden_read = ["scan_market", "start_scan_worker", "deep_analysis=True", "run_paper_lab_tick", "create_task", "Thread(", "Process("]

    checks = {
        "auto_scan_on_bot_start_default_false": "AUTO_SCAN_ON_BOT_START = False" in flags,
        "auto_scan_on_status_read_default_false": "AUTO_SCAN_ON_STATUS_READ = False" in flags,
        "auto_scan_on_dashboard_read_default_false": "AUTO_SCAN_ON_DASHBOARD_READ = False" in flags,
        "background_scan_worker_default_false": "ENABLE_BACKGROUND_SCAN_WORKER = False" in flags,
        "start_path_has_no_heavy_work": not any(value in start_service + start_route for value in forbidden_start),
        "status_path_has_no_worker_start": not any(value in status_route for value in forbidden_read),
        "dashboard_bundle_has_no_worker_start": not any(value in dashboard_bundle for value in forbidden_read),
        "start_runtime_contract_ok": all([
            started.get("requested_running") is True,
            started.get("bot_running") is True,
            started.get("engine_status") == "running",
            started.get("primary_runtime_problem") is None,
            started.get("tick_in_progress") is False,
            started.get("active_scan_worker") is False,
            started.get("scan_cancel_requested") is False,
            bool(started.get("last_tick")),
        ]),
        "start_idempotent": probe["idempotent_started_at"] and "already_running" in start_route,
        "stop_runtime_contract_ok": all([
            stopped.get("requested_running") is False,
            stopped.get("bot_running") is False,
            stopped.get("engine_status") == "stopped",
            stopped.get("primary_runtime_problem") is None,
            stopped.get("tick_in_progress") is False,
            stopped.get("active_scan_worker") is False,
            stopped.get("scan_cancel_requested") is True,
            stopped.get("next_tick_not_before") is None,
        ]),
        "status_stale_cleanup_only": "reconcile_stale_scan_worker" in status_route and "start_scan_worker" not in status_route,
        "worker_start_feature_guarded": "if not ENABLE_BACKGROUND_SCAN_WORKER:" in scan_worker_start,
        "main_background_loop_disabled": "if not ENABLE_BACKGROUND_SCAN_WORKER:" in _function(MAIN, "bot_loop") and "ENABLE_BACKGROUND_SCAN_WORKER and restore_started" in main,
        "runtime_truth_heartbeat_mode_present": "runtime_mode\": \"heartbeat_only" in runtime_truth and "if not ENABLE_BACKGROUND_SCAN_WORKER:" in runtime_truth,
        "frontend_transient_status_nonfatal": "Bot start sonrası status geçici okunamadı; yeniden denenecek." in bot_js and "console.warn" in bot_js,
        "frontend_pending_guard_present": all(value in bot_js for value in ["botCommandPending", "beginBotCommand", "endBotCommand", "5000"]),
        "dashboard_pending_buttons_disabled": "commandDisabled" in dashboard_js and "botCommandPending" in dashboard_js,
        "prior_rev2_and_hard_cancel_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "runtime_probe": probe,
        "call_locations": locations,
        "call_graph_classification": {
            "bot_start": "COMMAND_START heartbeat-only",
            "bot_stop": "COMMAND_STOP cancel-and-clear",
            "bot_status": "READ_ONLY plus stale cleanup",
            "dashboard_bundle": "READ_ONLY",
            "bot_tick": "MANUAL_SCAN",
            "scan_debug_and_test_scan": "MANUAL_SCAN",
            "main_bot_loop": "LEGACY_AUTO_SCAN disabled by feature flag",
            "start_scan_worker": "SCHEDULED_SCAN disabled by feature flag",
        },
        "prior_audit_statuses": prior_statuses,
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36.5 Rev3 Start Stop Runtime Contract Audit",
        "",
        "## Ozet",
        "",
        f"- Durum: `{report['status']}`",
        f"- Start runtime contract: `{_yn(report['start_runtime_contract_ok'])}`",
        f"- Stop runtime contract: `{_yn(report['stop_runtime_contract_ok'])}`",
        f"- Background worker default kapali: `{_yn(report['background_scan_worker_default_false'])}`",
        f"- Read path worker baslatmiyor: `{_yn(report['status_path_has_no_worker_start'] and report['dashboard_bundle_has_no_worker_start'])}`",
        "",
        "## Kontroller",
        "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Call Graph", ""])
    for key, value in report["call_graph_classification"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Tetik Noktalari", ""])
    for key, values in report["call_locations"].items():
        lines.append(f"- `{key}`: {', '.join(values) if values else 'yok'}")
    lines.extend(["", "## Blocker Listesi", ""])
    lines.extend(f"- BLOCKER: {item}" for item in report["blockers"]) if report["blockers"] else lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Heartbeat-only start/stop runtime contract ve zero-background-worker kapisi temiz." if report["status"] == "ok" else "Revize 3 runtime contract blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_5_REV3_START_STOP_RUNTIME_CONTRACT_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_36_5_REV3_START_STOP_RUNTIME_CONTRACT_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_36_5_REV3_START_STOP_RUNTIME_CONTRACT_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"start_runtime_contract_ok={str(report['start_runtime_contract_ok']).lower()}")
    print(f"stop_runtime_contract_ok={str(report['stop_runtime_contract_ok']).lower()}")
    print(f"background_scan_worker_default_false={str(report['background_scan_worker_default_false']).lower()}")
    print(f"frontend_pending_guard_present={str(report['frontend_pending_guard_present']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
