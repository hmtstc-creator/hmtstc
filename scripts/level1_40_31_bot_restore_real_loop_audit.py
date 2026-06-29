#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = ROOT / "backend" / "main.py"
BOT_ROUTES = ROOT / "backend" / "routes" / "bot_routes.py"
BOT_TRUTH = ROOT / "backend" / "services" / "bot_runtime_truth_service.py"
REPORT_SERVICE = ROOT / "backend" / "services" / "eight_hour_report_service.py"
REGISTRY = ROOT / "backend" / "infrastructure" / "runtime" / "bot_runtime_registry.py"
SCHEDULER = ROOT / "backend" / "infrastructure" / "runtime" / "scheduler.py"
LOOP_CONTROL = ROOT / "backend" / "infrastructure" / "runtime" / "bot_loop_control.py"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT.md"
PRIOR_AUDITS = [
    ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT.json",
    ROOT / "docs" / "LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT.json",
]


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _section(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        return ""
    if not end:
        return text[start_index:]
    end_index = text.find(end, start_index + len(start))
    return text[start_index:] if end_index < 0 else text[start_index:end_index]


def _contains_all(text: str, values: list[str]) -> bool:
    return all(value in text for value in values)


def build_report() -> dict[str, Any]:
    main_py = _load_text(MAIN_PY)
    bot_routes = _load_text(BOT_ROUTES)
    bot_truth = _load_text(BOT_TRUTH)
    report_service = _load_text(REPORT_SERVICE)
    registry = _load_text(REGISTRY)
    scheduler = _load_text(SCHEDULER)
    loop_control = _load_text(LOOP_CONTROL)
    restore_fn = _section(main_py, "def restore_requested_bot_loops", "def bot_loop")
    bot_loop_fn = _section(main_py, "def bot_loop", "")
    prior_statuses = {
        path.stem.replace("LEVEL1_", "").replace("_AUDIT", ""): _load_json(path).get("status")
        for path in PRIOR_AUDITS
    }

    checks = {
        "restore_does_not_fake_heartbeat": "mark_bot_task_heartbeat" not in restore_fn,
        "heartbeat_only_from_real_loop": "mark_bot_task_heartbeat(user)" in bot_loop_fn and "_REGISTRY[\"bot_task_running\"] = True" not in _section(registry, "def mark_bot_task_heartbeat", "def mark_bot_task_exception"),
        "ensure_bot_loop_running_present": _contains_all(loop_control, [
            "def ensure_bot_loop_running",
            "_RUNTIME_SCHEDULER.start()",
            "is_bot_task_alive(username)",
        ]),
        "start_and_restore_share_loop_starter": "ensure_bot_loop_running" in bot_routes and "ensure_bot_loop_running" in restore_fn,
        "restore_logs_present": _contains_all(main_py, [
            "BOT_RESTORE_CHECK",
            "BOT_RESTORE_START",
            "BOT_RESTORE_TASK_STARTED",
            "BOT_RESTORE_FIRST_TICK_OK",
            "BOT_RESTORE_FAILED",
        ]),
        "is_bot_task_alive_checks_real_task_reference": _contains_all(registry + scheduler, [
            "_TASK_THREAD",
            "register_bot_task_thread",
            "_TASK_THREAD.is_alive()",
            "BOT_TASK_HEARTBEAT_STALE_SECONDS",
        ]),
        "restore_first_tick_guard_present": _contains_all(bot_truth + main_py, [
            "restore_no_first_tick",
            "last_runtime_restore_at",
            "restore_age_seconds",
            "last_runtime_restore_first_tick_ok_at",
        ]),
        "eight_hour_report_restore_failure_reason_present": _contains_all(report_service, [
            "bot_restore_failed",
            "restore_no_first_tick",
            "primary_runtime_problem",
        ]),
        "previous_40_20_to_40_30_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Canli restart sonrasi BOT_RESTORE_* log zincirini journalctl ile dogrula.",
            "Requested bot icin 3 dakika icinde last_tick ve last_scan yenilenmesini kontrol et.",
            "Restore fail olursa /api/bot/status engine_status=failed ve primary_runtime_problem=restore_no_first_tick gostermeli.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.31 Bot Restore Real Loop Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Restore sahte heartbeat yok: `{_yn(report['restore_does_not_fake_heartbeat'])}`")
    lines.append(f"- Ortak loop starter: `{_yn(report['start_and_restore_share_loop_starter'])}`")
    lines.append(f"- Gercek task referansi: `{_yn(report['is_bot_task_alive_checks_real_task_reference'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key, value in report.items():
        if key.endswith("_present") or key.endswith("_starter") or key.endswith("_heartbeat") or key.endswith("_reference") or key.endswith("_ok") or key in {"restore_does_not_fake_heartbeat", "start_and_restore_share_loop_starter", "heartbeat_only_from_real_loop"}:
            lines.append(f"- {key}: `{_yn(bool(value))}`")
    lines.append("")
    lines.append("## Blocker Listesi")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- BLOCKER: {blocker}")
    else:
        lines.append("Blocker yok.")
    lines.append("")
    lines.append("## Sonuc")
    lines.append("")
    lines.append("Bot restore real loop kontrolleri temiz." if report["status"] == "ok" else "Bot restore real loop blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT_OK",
        "blocker": "LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"restore_does_not_fake_heartbeat={str(report['restore_does_not_fake_heartbeat']).lower()}")
    print(f"ensure_bot_loop_running_present={str(report['ensure_bot_loop_running_present']).lower()}")
    print(f"start_and_restore_share_loop_starter={str(report['start_and_restore_share_loop_starter']).lower()}")
    print(f"is_bot_task_alive_checks_real_task_reference={str(report['is_bot_task_alive_checks_real_task_reference']).lower()}")
    print(f"previous_40_20_to_40_30_status_ok={str(report['previous_40_20_to_40_30_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
