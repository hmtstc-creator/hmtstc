#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
MAIN = BACKEND / "main.py"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
ANALYSIS_SERVICE = BACKEND / "services" / "analysis_service.py"
LOOP_CONTROL = BACKEND / "infrastructure" / "runtime" / "bot_loop_control.py"
SCHEDULER = BACKEND / "infrastructure" / "runtime" / "scheduler.py"
ROUTE_FILES = {
    "dashboard_bundle": BACKEND / "routes" / "dashboard_routes.py",
    "positions": BACKEND / "routes" / "dashboard_routes.py",
    "bot_status": BACKEND / "routes" / "bot_routes.py",
    "get_settings": BACKEND / "routes" / "settings_routes.py",
    "get_rules": BACKEND / "routes" / "rule_routes.py",
    "my_api_connection": BACKEND / "routes" / "users_routes.py",
    "market": BACKEND / "routes" / "binance_routes.py",
}
PRIOR_AUDITS = {
    "40.36": ROOT / "docs" / "LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.json",
    "40.36.1": ROOT / "docs" / "LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT.json",
    "40.36.2": ROOT / "docs" / "LEVEL1_40_36_2_STATUS_FIELD_SYNC_HOTFIX_AUDIT.json",
}
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(_load_text(path))


def _function_source(path: Path, name: str) -> str:
    text = _load_text(path)
    tree = ast.parse(text, filename=str(path))
    node = next((item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name), None)
    if node is None:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def _isolated_function(path: Path, name: str, namespace: dict[str, Any]):
    text = _load_text(path)
    tree = ast.parse(text, filename=str(path))
    node = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


def _stopped_runtime_probe() -> dict[str, Any]:
    calls = {"ensure": 0, "tick": 0, "save": 0}

    def ensure_spy(*args, **kwargs):
        calls["ensure"] += 1
        return {}

    def tick_spy(*args, **kwargs):
        calls["tick"] += 1
        return {"status": "ok"}

    def save_spy(*args, **kwargs):
        calls["save"] += 1

    base = {
        "ENABLE_BACKGROUND_SCAN_WORKER": False,
        "get_shadow_users": lambda: ["ahmet"],
        "load_shadow": lambda user: {"requested_running": False, "bot_running": False, "engine_status": "stopped"},
        "save_shadow": save_spy,
        "ensure_bot_loop_running": ensure_spy,
        "run_bot_tick": tick_spy,
        "append_log": lambda *args, **kwargs: None,
        "load_settings": lambda user: {},
        "mark_user_bot_requested": lambda *args, **kwargs: None,
        "mark_bot_task_heartbeat": lambda *args, **kwargs: None,
        "mark_bot_task_exception": lambda *args, **kwargs: None,
        "time": __import__("time"),
        "traceback": __import__("traceback"),
    }
    restore_fn = _isolated_function(MAIN, "restore_requested_bot_loops", dict(base))
    restored_any = restore_fn()
    loop_fn = _isolated_function(MAIN, "bot_loop", dict(base))
    loop_result = loop_fn()
    return {**calls, "restored_any": restored_any, "loop_result": loop_result}


def build_report() -> dict[str, Any]:
    main_text = _load_text(MAIN)
    restore_text = _function_source(MAIN, "restore_requested_bot_loops")
    loop_text = _function_source(MAIN, "bot_loop")
    bot_service_text = _load_text(BOT_SERVICE)
    analysis_text = _load_text(ANALYSIS_SERVICE)
    loop_control_text = _load_text(LOOP_CONTROL)
    scheduler_text = _load_text(SCHEDULER)
    scheduler_start_text = scheduler_text[scheduler_text.find("    def start"):scheduler_text.find("    def _run")]
    prior_statuses = {name: _load_json(path).get("status") for name, path in PRIOR_AUDITS.items()}
    stopped_probe = _stopped_runtime_probe()

    endpoint_sources = {name: _function_source(path, name) for name, path in ROUTE_FILES.items()}
    endpoint_scan_free = all("scan_market(" not in source and "run_bot_tick(" not in source and "ensure_bot_loop_running(" not in source for source in endpoint_sources.values())
    deep_match = re.search(r'deep_limit\s*=\s*max\(0,\s*min\(_safe_int\(bot_settings\.get\("scan_deep_analysis_limit"\),\s*(\d+)\),\s*(\d+)\)\)', analysis_text)
    deep_cap = max(map(int, deep_match.groups())) if deep_match else None

    checks = {
        "stopped_restore_skips_ensure_bot_loop_running": "if not requested_running:" in restore_text and "continue" in restore_text and restore_text.find("if not requested_running:") < restore_text.find("ensure_bot_loop_running("),
        "stopped_scheduler_skips_scan_and_tick": (
            "if not requested_running:" in loop_text
            and "continue" in loop_text
            and loop_text.find("if not requested_running:") < loop_text.find("start_scan_worker(")
            and loop_text.find("if not requested_running:") < loop_text.find("run_bot_first_tick_guarded(")
        ),
        "stopped_runtime_probe_has_zero_background_work": stopped_probe["ensure"] == 0 and stopped_probe["tick"] == 0 and stopped_probe["save"] == 0 and stopped_probe["restored_any"] is False,
        "scheduler_stops_when_no_requested_users": "if not requested_user_seen:" in loop_text and "return" in loop_text and "restore_started" in main_text,
        "requested_running_default_true_absent": 'data.get("requested_running", True)' not in main_text and 'data.get("requested_running", data.get("bot_running", False))' in main_text,
        "ensure_loop_rejects_stopped_user": 'reason": "bot_not_requested"' in loop_control_text and "if not bool(data.get(\"requested_running\"" in loop_control_text,
        "tick_in_progress_guard_present": 'if data.get("tick_in_progress"):' in loop_text and 'data["tick_in_progress"] = True' in loop_text and 'data["tick_in_progress"] = False' in loop_text,
        "min_tick_interval_seconds_at_least_30": "MIN_TICK_INTERVAL_SECONDS = 30" in main_text and "_runtime_iso_after(tick_delay)" in loop_text,
        "error_backoff_at_least_60": "BOT_LOOP_ERROR_BACKOFF_SECONDS = 60" in main_text and 'data["next_tick_not_before"] = _runtime_iso_after' in loop_text,
        "deep_analysis_cap_at_most_8": deep_cap is not None and deep_cap <= 8,
        "api_read_endpoints_do_not_trigger_scan": endpoint_scan_free,
        "stop_clears_loop_throttle_state": all(value in _function_source(BOT_SERVICE, "stop_bot") for value in [
            'data["requested_running"] = False', 'data["bot_running"] = False', 'data["engine_status"] = "stopped"',
            'data["tick_in_progress"] = False', 'data["next_tick_not_before"] = None',
        ]),
        "inflight_tick_respects_persisted_stop": "def _apply_persisted_stop_guard" in main_text and loop_text.count("_apply_persisted_stop_guard(user, data)") >= 2,
        "scheduler_can_restart_after_clean_exit": "finally:" in scheduler_text and "self._started = False" in scheduler_text and "register_bot_task_thread(None)" in scheduler_text,
        "scheduler_start_race_guard_present": scheduler_start_text.find("self._started = True") < scheduler_start_text.find("self._thread.start()"),
        "prior_40_36_audits_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "deep_analysis_cap": deep_cap,
        "endpoint_scan_free": {name: "scan_market(" not in source and "run_bot_tick(" not in source and "ensure_bot_loop_running(" not in source for name, source in endpoint_sources.items()},
        "prior_audit_statuses": prior_statuses,
        "stopped_runtime_probe": stopped_probe,
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36.3 Bot Loop CPU Throttle Audit", "", "## Ozet", "",
        f"- Durum: `{report['status']}`",
        f"- Stopped scheduler skip: `{_yn(report['stopped_scheduler_skips_scan_and_tick'])}`",
        f"- Tick in-progress guard: `{_yn(report['tick_in_progress_guard_present'])}`",
        f"- Error backoff: `{_yn(report['error_backoff_at_least_60'])}`",
        f"- Deep analysis cap: `{report['deep_analysis_cap']}`",
        f"- API isolation: `{_yn(report['api_read_endpoints_do_not_trigger_scan'])}`",
        "", "## Kontroller", "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    lines.extend(f"- BLOCKER: {item}" for item in report["blockers"]) if report["blockers"] else lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Bot loop CPU throttle kalite kapisi temiz." if report["status"] == "ok" else "Bot loop CPU throttle blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_36_3_BOT_LOOP_CPU_THROTTLE_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"stopped_scheduler_skips_scan_and_tick={str(report['stopped_scheduler_skips_scan_and_tick']).lower()}")
    print(f"tick_in_progress_guard_present={str(report['tick_in_progress_guard_present']).lower()}")
    print(f"error_backoff_at_least_60={str(report['error_backoff_at_least_60']).lower()}")
    print(f"deep_analysis_cap={report['deep_analysis_cap']}")
    print(f"api_read_endpoints_do_not_trigger_scan={str(report['api_read_endpoints_do_not_trigger_scan']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
