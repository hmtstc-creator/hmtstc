#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
STORAGE = BACKEND / "core" / "storage.py"
BOT_SERVICE = BACKEND / "services" / "bot_service.py"
BOT_ROUTES = BACKEND / "routes" / "bot_routes.py"
DASHBOARD_ROUTES = BACKEND / "routes" / "dashboard_routes.py"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
PRIOR_40_36 = ROOT / "docs" / "LEVEL1_40_36_BOT_START_AND_COINFILTER_SAVE_STABILITY_AUDIT.json"
PRIOR_40_36_1 = ROOT / "docs" / "LEVEL1_40_36_1_BOT_LOOP_NONE_NUMERIC_HOTFIX_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_36_2_STATUS_FIELD_SYNC_HOTFIX_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_36_2_STATUS_FIELD_SYNC_HOTFIX_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_probe() -> dict[str, Any]:
    storage_tree = ast.parse(_load_text(STORAGE), filename=str(STORAGE))
    helper_node = next(
        node for node in storage_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "sync_last_scan_state"
    )
    helper_module = ast.Module(body=[helper_node], type_ignores=[])
    ast.fix_missing_locations(helper_module)
    namespace: dict[str, Any] = {}
    exec(compile(helper_module, str(STORAGE), "exec"), namespace)
    scan_time = "2026-06-13T10:11:12+00:00"
    scan = {"time": scan_time, "scanned": 89, "error": None, "live": True}
    state = {"last_scan_time": None}
    namespace["sync_last_scan_state"](state, scan)

    return {
        "synced_last_scan_time": state.get("last_scan_time"),
        "nested_last_scan_time": state.get("last_scan", {}).get("time"),
    }


def build_report() -> dict[str, Any]:
    storage_text = _load_text(STORAGE)
    bot_service_text = _load_text(BOT_SERVICE)
    bot_routes_text = _load_text(BOT_ROUTES)
    dashboard_text = _load_text(DASHBOARD_ROUTES)
    api_text = _load_text(API_JS)
    prior_40_36_status = _load_json(PRIOR_40_36).get("status")
    prior_40_36_1_status = _load_json(PRIOR_40_36_1).get("status")
    probe = _runtime_probe()
    scan_write_count = bot_service_text.count("sync_last_scan_state(data, scan)") + bot_routes_text.count("sync_last_scan_state(data, scan)")

    checks = {
        "last_scan_write_sync_helper_present": 'data["last_scan_time"] = safe_scan.get("time")' in storage_text,
        "all_known_scan_writes_use_sync_helper": scan_write_count >= 4 and 'data["last_scan"] = scan' not in bot_service_text + bot_routes_text,
        "last_scan_time_runtime_sync_present": probe["synced_last_scan_time"] == probe["nested_last_scan_time"],
        "normalized_state_repairs_last_scan_time": 'normalized["last_scan_time"] = normalized.get("last_scan_time") or normalized["last_scan"].get("time")' in storage_text,
        "bot_status_last_scan_time_fallback_present": 'data.get("last_scan_time") or last_scan.get("time")' in bot_routes_text,
        "dashboard_last_scan_time_fallback_present": 'data.get("last_scan_time") or last_scan.get("time")' in dashboard_text,
        "dashboard_backend_api_online_when_running_scan_clean": 'runtime_truth.get("bot_running") and not scan_error' in dashboard_text and '"backend_api_status": backend_api_status' in dashboard_text,
        "frontend_bundle_success_clears_backend_error": all(value in api_text for value in [
            'backend_api: "online"', 'last_api_error_type: ""', 'last_api_error_message: ""', 'core_failure_count: 0',
        ]),
        "runtime_truth_fields_preserved": all(value in dashboard_text for value in [
            '"requested_running": runtime_truth.get("requested_running")',
            '"bot_running": runtime_truth.get("bot_running")',
            '"engine_status": runtime_truth.get("engine_status")',
        ]),
        "prior_40_36_status_ok": prior_40_36_status == "ok",
        "prior_40_36_1_status_ok": prior_40_36_1_status == "ok",
    }
    blockers = [f"{key}=false" for key, value in checks.items() if not value]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "runtime_probe": probe,
        "prior_40_36_status": prior_40_36_status,
        "prior_40_36_1_status": prior_40_36_1_status,
        "blockers": blockers,
        "recommended_next_actions": [
            "Deploy sonrasi last_scan.time ile last_scan_time alanlarinin birebir esitligini kontrol et.",
            "Bot running ve scan error bosken Dashboard Backend API durumunun online kaldigini dogrula.",
            "requested_running, bot_running ve engine_status alanlarini canli scheduler sonucu ile kabul et.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.36.2 Status Field Sync Hotfix Audit", "", "## Ozet", "",
        f"- Durum: `{report['status']}`",
        f"- Scan time sync: `{_yn(report['last_scan_time_runtime_sync_present'])}`",
        f"- Bot status fallback: `{_yn(report['bot_status_last_scan_time_fallback_present'])}`",
        f"- Dashboard backend online guard: `{_yn(report['dashboard_backend_api_online_when_running_scan_clean'])}`",
        f"- Runtime truth alanlari korunuyor: `{_yn(report['runtime_truth_fields_preserved'])}`",
        "", "## Kontroller", "",
    ]
    for key, value in report.items():
        if isinstance(value, bool):
            lines.append(f"- {key}: `{_yn(value)}`")
    lines.extend(["", "## Blocker Listesi", ""])
    lines.extend((f"- BLOCKER: {item}" for item in report["blockers"])) if report["blockers"] else lines.append("Blocker yok.")
    lines.extend(["", "## Sonuc", ""])
    lines.append("Status field sync hotfix kalite kapisi temiz." if report["status"] == "ok" else "Status field sync hotfix blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_36_2_STATUS_FIELD_SYNC_HOTFIX_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_36_2_STATUS_FIELD_SYNC_HOTFIX_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_36_2_STATUS_FIELD_SYNC_HOTFIX_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"last_scan_time_runtime_sync_present={str(report['last_scan_time_runtime_sync_present']).lower()}")
    print(f"bot_status_last_scan_time_fallback_present={str(report['bot_status_last_scan_time_fallback_present']).lower()}")
    print(f"dashboard_backend_api_online_when_running_scan_clean={str(report['dashboard_backend_api_online_when_running_scan_clean']).lower()}")
    print(f"runtime_truth_fields_preserved={str(report['runtime_truth_fields_preserved']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
