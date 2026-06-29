#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_JS = ROOT / "frontend" / "js" / "app" / "state.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
SETTINGS_ROUTES = ROOT / "backend" / "routes" / "settings_routes.py"
BOT_ROUTES = ROOT / "backend" / "routes" / "bot_routes.py"
REPORTS_ROUTES = ROOT / "backend" / "routes" / "reports_routes.py"
REPORT_SERVICE = ROOT / "backend" / "services" / "eight_hour_report_service.py"
MAIN_PY = ROOT / "backend" / "main.py"
GITIGNORE = ROOT / ".gitignore"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT.md"
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
    state_js = _load_text(STATE_JS)
    api_js = _load_text(API_JS)
    coin_filter_js = _load_text(COIN_FILTER_JS)
    settings_routes = _load_text(SETTINGS_ROUTES)
    bot_routes = _load_text(BOT_ROUTES)
    reports_routes = _load_text(REPORTS_ROUTES)
    report_service = _load_text(REPORT_SERVICE)
    main_py = _load_text(MAIN_PY)
    gitignore = _load_text(GITIGNORE)
    combined_runtime_text = "\n".join([api_js, coin_filter_js, settings_routes, bot_routes, reports_routes, report_service, main_py])

    prior_statuses = {
        path.stem.replace("LEVEL1_", "").replace("_AUDIT", ""): _load_json(path).get("status")
        for path in PRIOR_AUDITS
    }

    checks = {
        "coinfilter_save_proof_present": _contains_all(state_js + coin_filter_js, [
            "coinFilterSaveProof",
            "changedAt",
            "mismatchReason",
            "persisted",
        ]),
        "coinfilter_payload_response_refresh_chain_present": _contains_all(coin_filter_js, [
            "payloadCoinFilter",
            "proof.response",
            "proof.storeEcho",
            "proof.refreshEcho",
            "backend_response_coin_filter_mismatch",
            "settings_store_echo_mismatch",
            "settings_refresh_echo_mismatch",
        ]),
        "coinfilter_partial_payload_does_not_clear_saved_values": _contains_all(api_js, [
            "applySettingsPayload",
            "partial_settings_payload",
            "coin_filter_partial_payload_preserved",
            "currentCoinFilter",
        ]),
        "coinfilter_bundle_overwrite_guard_present": _contains_all(api_js, [
            "coinFilterBundleOverwriteGuarded",
            "bundleOverwriteGuarded",
            "coin_filter_bundle_overwrite_guarded",
            "dashboard_bundle",
        ]),
        "coinfilter_backend_store_echo_present": _contains_all(settings_routes, [
            "_settings_store_echo_response",
            '"source": "settings_store"',
            '"store_echo"',
            '"refresh_echo"',
            '"persisted"',
        ]),
        "bot_no_trade_reason_funnel_present": _contains_all(bot_routes + report_service, [
            "scan_total",
            "coinfilter_passed",
            "coinfilter_rejected",
            "strategy_signal_count",
            "karabasan_passed",
            "risk_passed",
            "final_trade_candidate_count",
            "trade_opened",
            "primary_no_trade_reason",
            "top_blockers",
        ]),
        "eight_hour_report_periods_present": _contains_all(report_service, [
            "EIGHT_HOUR_REPORT_PERIODS",
            "00:00-08:00",
            "08:00-16:00",
            "16:00-00:00",
        ]),
        "eight_hour_report_timezone_europe_bucharest_present": "Europe/Bucharest" in report_service,
        "eight_hour_report_store_gitignored": _contains_all(gitignore, [
            "backend/eight_hour_report_store.json",
            "backend/eight_hour_report_store.json.*",
        ]),
        "eight_hour_report_latest_endpoint_present": _contains_all(reports_routes + main_py, [
            '"/eight-hour/latest"',
            "latest_eight_hour_report",
            "reports_router",
        ]),
        "eight_hour_report_generate_endpoint_present": _contains_all(reports_routes + report_service, [
            '"/eight-hour/generate"',
            "generate_eight_hour_report",
            "force",
        ]),
        "paper_lab_live_monitor_not_added": not any(
            marker in combined_runtime_text
            for marker in ["EventSource", "WebSocket", "paper_lab_live_monitor", "livePaperLabMonitor"]
        ),
        "previous_40_20_to_40_28_status_ok": all(status == "ok" for status in prior_statuses.values()),
    }

    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    status = "blocker" if blockers else "ok"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_statuses": prior_statuses,
        "blockers": blockers,
        "recommended_next_actions": [
            "Canli ortamda CoinFilter save -> Ctrl+F5 kabul testini ayni degerle dogrula.",
            "Canli ortamda /api/reports/eight-hour/latest ciktisini son tamamlanmis 8 saatlik blok icin kontrol et.",
            "Paper Lab icin live monitor, WebSocket veya SSE eklemeden Paket 11'e gec.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.29 CoinFilter Persistence and 8H Report Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- CoinFilter save proof: `{_yn(report['coinfilter_save_proof_present'])}`")
    lines.append(f"- Payload/response/refresh zinciri: `{_yn(report['coinfilter_payload_response_refresh_chain_present'])}`")
    lines.append(f"- Bundle overwrite guard: `{_yn(report['coinfilter_bundle_overwrite_guard_present'])}`")
    lines.append(f"- 8 saatlik rapor endpointleri: `{_yn(report['eight_hour_report_latest_endpoint_present'] and report['eight_hour_report_generate_endpoint_present'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key, value in report.items():
        if key.endswith("_present") or key.endswith("_preserved") or key.endswith("_gitignored") or key.endswith("_ok") or key in {"paper_lab_live_monitor_not_added", "previous_40_20_to_40_28_status_ok"}:
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
        lines.append("CoinFilter persistence proof ve 8 saatlik rapor altyapisi statik kontrolleri temiz.")
    else:
        lines.append("CoinFilter persistence veya 8 saatlik rapor altyapisi blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT_OK",
        "blocker": "LEVEL1_40_29_COINFILTER_PERSISTENCE_AND_8H_REPORT_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"coinfilter_save_proof_present={str(report['coinfilter_save_proof_present']).lower()}")
    print(f"coinfilter_bundle_overwrite_guard_present={str(report['coinfilter_bundle_overwrite_guard_present']).lower()}")
    print(f"eight_hour_report_latest_endpoint_present={str(report['eight_hour_report_latest_endpoint_present']).lower()}")
    print(f"eight_hour_report_generate_endpoint_present={str(report['eight_hour_report_generate_endpoint_present']).lower()}")
    print(f"previous_40_20_to_40_28_status_ok={str(report['previous_40_20_to_40_28_status_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
