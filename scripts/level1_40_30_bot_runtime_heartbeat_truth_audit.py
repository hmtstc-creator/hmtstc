#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BOT_ROUTES = ROOT / "backend" / "routes" / "bot_routes.py"
BOT_SERVICE = ROOT / "backend" / "services" / "bot_service.py"
BOT_TRUTH_SERVICE = ROOT / "backend" / "services" / "bot_runtime_truth_service.py"
REAL_TRADE_SAFETY = ROOT / "backend" / "services" / "real_trade_safety_service.py"
RUNTIME_REGISTRY = ROOT / "backend" / "infrastructure" / "runtime" / "bot_runtime_registry.py"
SCHEDULER = ROOT / "backend" / "infrastructure" / "runtime" / "scheduler.py"
MAIN_PY = ROOT / "backend" / "main.py"
REPORT_SERVICE = ROOT / "backend" / "services" / "eight_hour_report_service.py"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT.md"
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
    bot_routes = _load_text(BOT_ROUTES)
    bot_service = _load_text(BOT_SERVICE)
    bot_truth = _load_text(BOT_TRUTH_SERVICE)
    real_safety = _load_text(REAL_TRADE_SAFETY)
    registry = _load_text(RUNTIME_REGISTRY)
    scheduler = _load_text(SCHEDULER)
    main_py = _load_text(MAIN_PY)
    report_service = _load_text(REPORT_SERVICE)
    prior_statuses = {
        path.stem.replace("LEVEL1_", "").replace("_AUDIT", ""): _load_json(path).get("status")
        for path in PRIOR_AUDITS
    }

    checks = {
        "bot_status_has_requested_running": '"requested_running"' in bot_routes and "requested_running" in bot_truth,
        "bot_status_has_loop_alive": '"loop_alive"' in bot_routes and "loop_alive" in bot_truth,
        "bot_status_has_engine_status_stale": '"stale"' in bot_truth and '"engine_status"' in bot_routes,
        "heartbeat_freshness_threshold_present": _contains_all(registry + bot_truth, [
            "TICK_STALE_THRESHOLD_SECONDS = 180",
            "SCAN_STALE_THRESHOLD_SECONDS = 300",
            "tick_stale_threshold_seconds",
            "scan_stale_threshold_seconds",
        ]),
        "startup_restore_requested_running_present": _contains_all(main_py, [
            "restore_requested_bot_loops",
            "requested_running",
            "emergency_lock",
            "startup_restore_skipped_emergency_lock",
        ]),
        "bot_task_registry_present": _contains_all(registry + scheduler + main_py, [
            "bot_task_running",
            "bot_task_started_at",
            "bot_task_last_heartbeat_at",
            "bot_task_exception",
            "mark_bot_task_heartbeat",
        ]),
        "bot_start_verifies_task_alive": _contains_all(bot_routes, [
            "ensure_bot_loop_running",
            "bot_loop_task_failed_to_start",
            '"started": False',
            "runtime_truth",
        ]) and "requested_running" in bot_service,
        "bot_stop_cancels_task": _contains_all(bot_routes + bot_service, [
            "mark_user_bot_requested(user, False)",
            '"stopped": True',
            '"requested_running": False',
            "data[\"requested_running\"] = False",
        ]),
        "eight_hour_report_includes_loop_alive": _contains_all(report_service, [
            '"loop_alive"',
            '"engine_status"',
            "build_bot_runtime_truth",
        ]),
        "stale_bot_primary_no_trade_reason_present": _contains_all(report_service, [
            "bot_loop_stale",
            "primary_no_trade_reason",
            "not runtime_truth.get(\"loop_alive\")",
        ]),
        "runtime_health_uses_runtime_truth": _contains_all(real_safety, [
            "build_bot_runtime_truth",
            '"requested_running"',
            '"loop_alive"',
            '"primary_runtime_problem"',
        ]),
        "previous_40_20_to_40_29_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Deploy sonrasi /api/bot/status ciktisinda requested_running ve loop_alive ayrimini kontrol et.",
            "Backend restart sonrasi requested_running=true ise tick/scan 3 dakika icinde yenilenmeli.",
            "Bot stale ise kullaniciya bot_running=true tek basina guven sinyali verilmemeli.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.30 Bot Runtime Heartbeat Truth Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Requested running: `{_yn(report['bot_status_has_requested_running'])}`")
    lines.append(f"- Loop alive: `{_yn(report['bot_status_has_loop_alive'])}`")
    lines.append(f"- Stale engine status: `{_yn(report['bot_status_has_engine_status_stale'])}`")
    lines.append(f"- Task registry: `{_yn(report['bot_task_registry_present'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key, value in report.items():
        if key.endswith("_present") or key.endswith("_alive") or key.endswith("_ok") or key in {"bot_start_verifies_task_alive", "bot_stop_cancels_task", "runtime_health_uses_runtime_truth", "eight_hour_report_includes_loop_alive", "stale_bot_primary_no_trade_reason_present"}:
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
    if report["status"] == "ok":
        lines.append("Bot runtime heartbeat truth, startup restore ve stale raporlama kontrolleri temiz.")
    else:
        lines.append("Bot runtime heartbeat truth blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT_OK",
        "blocker": "LEVEL1_40_30_BOT_RUNTIME_HEARTBEAT_TRUTH_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"bot_status_has_requested_running={str(report['bot_status_has_requested_running']).lower()}")
    print(f"bot_status_has_loop_alive={str(report['bot_status_has_loop_alive']).lower()}")
    print(f"bot_task_registry_present={str(report['bot_task_registry_present']).lower()}")
    print(f"bot_start_verifies_task_alive={str(report['bot_start_verifies_task_alive']).lower()}")
    print(f"previous_40_20_to_40_29_status_ok={str(report['previous_40_20_to_40_29_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
