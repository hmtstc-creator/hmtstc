#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = ROOT / "backend" / "main.py"
LOOP_CONTROL = ROOT / "backend" / "infrastructure" / "runtime" / "bot_loop_control.py"
BOT_TRUTH = ROOT / "backend" / "services" / "bot_runtime_truth_service.py"
REPORT_SERVICE = ROOT / "backend" / "services" / "eight_hour_report_service.py"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT.md"
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
    ROOT / "docs" / "LEVEL1_40_31_BOT_RESTORE_REAL_LOOP_AUDIT.json",
]


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_all(text: str, values: list[str]) -> bool:
    return all(value in text for value in values)


def build_report() -> dict[str, Any]:
    main_py = _load_text(MAIN_PY)
    loop_control = _load_text(LOOP_CONTROL)
    bot_truth = _load_text(BOT_TRUTH)
    report_service = _load_text(REPORT_SERVICE)
    prior_statuses = {
        path.stem.replace("LEVEL1_", "").replace("_AUDIT", ""): _load_json(path).get("status")
        for path in PRIOR_AUDITS
    }

    checks = {
        "ensure_bot_loop_running_does_not_accept_thread_only": _contains_all(loop_control, [
            '"thread_alive"',
            '"first_tick_ok"',
            '"loop_alive": bool(thread_alive and first_tick_ok)',
            'reason = "waiting_first_tick"',
        ]),
        "restore_first_tick_required": _contains_all(loop_control + bot_truth, [
            "restore_first_tick_ok",
            "last_runtime_restore_first_tick_ok_at",
            "last_tick",
            "_after",
        ]),
        "restore_monitor_or_watchdog_present": _contains_all(loop_control, [
            "_monitor_restore_first_tick",
            "threading.Thread",
            "RESTORE_FIRST_TICK_TIMEOUT_SECONDS = 25",
            "RESTORE_FIRST_TICK_WAIT_SECONDS = 0.25",
        ]),
        "restoring_status_has_timeout": _contains_all(bot_truth, [
            "waiting_first_tick",
            "restore_no_first_tick",
            "engine_status = \"restoring\"",
            "engine_status = \"failed\"",
        ]),
        "restore_failure_sets_engine_failed": _contains_all(loop_control + bot_truth, [
            "data[\"engine_status\"] = \"failed\"",
            "data[\"primary_runtime_problem\"] = \"first_tick_timeout\"",
            "data[\"bot_running\"] = False",
        ]),
        "bot_loop_user_diagnostics_present": _contains_all(main_py, [
            "BOT_LOOP_USER_CHECK",
            "requested_running",
            "bot_loop_user_check",
        ]),
        "bot_loop_tick_start_ok_failed_logs_present": _contains_all(main_py, [
            "BOT_LOOP_TICK_START",
            "BOT_LOOP_TICK_OK",
            "BOT_LOOP_TICK_FAILED",
            "first_tick_timeout",
        ]),
        "restore_result_contains_first_tick_ok": _contains_all(loop_control, [
            '"thread_alive"',
            '"first_tick_ok"',
            '"restore_started_at"',
            '"checked_at"',
        ]),
        "eight_hour_report_restore_failure_reason_present": _contains_all(report_service, [
            "bot_restore_failed",
            "restore_no_first_tick",
            "primary_runtime_problem",
        ]),
        "previous_40_20_to_40_31_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Canli restart sonrasi thread_alive=true tek basina basari sayilmadigini dogrula.",
            "last_runtime_restore_first_tick_ok_at dolmadan loop_alive=true donmemeli.",
            "180 saniye icinde tick/scan yoksa restore_no_first_tick fail durumunu kontrol et.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.32 Bot Restore First Tick Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Thread-only success yok: `{_yn(report['ensure_bot_loop_running_does_not_accept_thread_only'])}`")
    lines.append(f"- First tick zorunlu: `{_yn(report['restore_first_tick_required'])}`")
    lines.append(f"- Watchdog: `{_yn(report['restore_monitor_or_watchdog_present'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key, value in report.items():
        if key.endswith("_present") or key.endswith("_required") or key.endswith("_ok") or key in {"ensure_bot_loop_running_does_not_accept_thread_only", "restoring_status_has_timeout", "restore_failure_sets_engine_failed", "restore_result_contains_first_tick_ok"}:
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
    lines.append("Bot restore first tick kalite kapisi temiz." if report["status"] == "ok" else "Bot restore first tick kalite kapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT_OK",
        "blocker": "LEVEL1_40_32_BOT_RESTORE_FIRST_TICK_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"ensure_bot_loop_running_does_not_accept_thread_only={str(report['ensure_bot_loop_running_does_not_accept_thread_only']).lower()}")
    print(f"restore_first_tick_required={str(report['restore_first_tick_required']).lower()}")
    print(f"restore_monitor_or_watchdog_present={str(report['restore_monitor_or_watchdog_present']).lower()}")
    print(f"previous_40_20_to_40_31_status_ok={str(report['previous_40_20_to_40_31_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
