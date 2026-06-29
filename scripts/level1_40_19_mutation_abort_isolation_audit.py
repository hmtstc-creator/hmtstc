#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
AUDIT_JS = ROOT / "frontend" / "js" / "app" / "audit.js"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
AUDIT_16 = ROOT / "docs" / "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT.json"
AUDIT_17 = ROOT / "docs" / "LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT.json"
AUDIT_18 = ROOT / "docs" / "LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _contains_all(text: str, items: list[str]) -> bool:
    return all(item in text for item in items)


def build_report() -> dict[str, Any]:
    api_js = _load_text(API_JS)
    audit_js = _load_text(AUDIT_JS)
    rules_js = _load_text(RULES_JS)
    coin_filter_js = _load_text(COIN_FILTER_JS)
    dashboard_js = _load_text(DASHBOARD_JS)
    audit_16 = _load_json(AUDIT_16)
    audit_17 = _load_json(AUDIT_17)
    audit_18 = _load_json(AUDIT_18)

    request_aborted_classification_present = _contains_all(api_js, [
        'error.name === "AbortError"',
        '"request_aborted"',
        "apiUserMessage",
    ])
    mutation_prevent_global_abort = _contains_all(api_js, [
        'MUTATION: "mutation"',
        "preventGlobalAbort",
        "requestKind",
        "timeoutMs",
    ])
    mutation_no_global_abort_signal = (
        "globalAbort" not in api_js
        and "globalAbortController" not in api_js
        and "delete request.preventGlobalAbort" in api_js
    )
    sync_overlap_guard_present = _contains_all(api_js, [
        "HMTSTC_APP.state.syncInProgress",
        "return false",
        "HMTSTC_APP.state.heavySyncInProgress",
    ])
    heavy_endpoints_isolated = _contains_all(api_js, [
        "/api/models/reports?period=7d",
        "/api/intelligence/overview",
        "/api/intelligence/auto-bot-mode-decision",
        "/api/intelligence/tradeability-decision",
        "HEAVY_READ",
        "AUDIT_BEST_EFFORT",
        "heavy_status",
    ])
    audit_best_effort_abort = _contains_all(audit_js, [
        '"/api/audit"',
        'requestKind: "audit_best_effort"',
        "preventGlobalAbort: true",
        'error.apiErrorType === "request_aborted"',
    ])
    coinfilter_save_protected = _contains_all(coin_filter_js, [
        '"/api/settings"',
        'requestKind: "mutation"',
        "preventGlobalAbort: true",
        "coinFilterSaving",
        'error.apiErrorType === "request_aborted"',
    ])
    rules_save_protected = _contains_all(rules_js, [
        '"/api/rules/save"',
        '"/api/rules/activate-paper-lab"',
        '"/api/rules/auto-paper-lab"',
        'requestKind: "mutation"',
        "preventGlobalAbort: true",
        "İstek iptal edildi; tekrar dene",
    ])
    dashboard_backend_core_status_present = _contains_all(dashboard_js, [
        "last_api_request_kind",
        "core_read",
        "request_aborted",
        "coreError",
        "Backend API",
        "Ağır Analiz",
        "Audit",
        "Rules",
    ])
    request_aborted_not_backend_offline = _contains_all(api_js, [
        'type === "request_aborted"',
        "backendApiStatus = previousSystem.backend_api || \"online\"",
    ]) and _contains_all(dashboard_js, [
        'lastApiErrorType === "request_aborted"',
        'system.backend_api || "online"',
    ])

    prior_40_16_status = audit_16.get("status")
    prior_40_17_status = audit_17.get("status")
    prior_40_18_status = audit_18.get("status")
    prior_audits_ok = prior_40_16_status == "ok" and prior_40_17_status == "ok" and prior_40_18_status == "ok"

    blockers: list[str] = []
    for name, value in [
        ("request_aborted_classification_present", request_aborted_classification_present),
        ("mutation_prevent_global_abort", mutation_prevent_global_abort),
        ("mutation_no_global_abort_signal", mutation_no_global_abort_signal),
        ("sync_overlap_guard_present", sync_overlap_guard_present),
        ("heavy_endpoints_isolated", heavy_endpoints_isolated),
        ("audit_best_effort_abort", audit_best_effort_abort),
        ("coinfilter_save_protected", coinfilter_save_protected),
        ("rules_save_protected", rules_save_protected),
        ("dashboard_backend_core_status_present", dashboard_backend_core_status_present),
        ("request_aborted_not_backend_offline", request_aborted_not_backend_offline),
        ("prior_audits_ok", prior_audits_ok),
    ]:
        if not value:
            blockers.append(f"{name}=false")

    status = "blocker" if blockers else "ok"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request_aborted_classification_present": request_aborted_classification_present,
        "mutation_prevent_global_abort": mutation_prevent_global_abort,
        "mutation_no_global_abort_signal": mutation_no_global_abort_signal,
        "sync_overlap_guard_present": sync_overlap_guard_present,
        "heavy_endpoints_isolated": heavy_endpoints_isolated,
        "audit_best_effort_abort": audit_best_effort_abort,
        "coinfilter_save_protected": coinfilter_save_protected,
        "rules_save_protected": rules_save_protected,
        "dashboard_backend_core_status_present": dashboard_backend_core_status_present,
        "request_aborted_not_backend_offline": request_aborted_not_backend_offline,
        "prior_40_16_status": prior_40_16_status,
        "prior_40_17_status": prior_40_17_status,
        "prior_40_18_status": prior_40_18_status,
        "prior_audits_ok": prior_audits_ok,
        "blockers": blockers,
        "recommended_next_actions": [
            "Keep CoinFilter, Rules and Paper Lab save flows as protected mutation requests.",
            "Keep audit writes best-effort and isolated from Backend API global status.",
            "Keep heavy intelligence/model endpoints out of core backend health decisions.",
            "Run 40.19 before Paket 11 live validation.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.19 Mutation Abort Isolation Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Request aborted siniflandirma: `{_yn(report['request_aborted_classification_present'])}`")
    lines.append(f"- Mutation preventGlobalAbort: `{_yn(report['mutation_prevent_global_abort'])}`")
    lines.append(f"- CoinFilter save protected: `{_yn(report['coinfilter_save_protected'])}`")
    lines.append(f"- Rules save protected: `{_yn(report['rules_save_protected'])}`")
    lines.append(f"- Audit best-effort abort: `{_yn(report['audit_best_effort_abort'])}`")
    lines.append(f"- Heavy endpoint izolasyonu: `{_yn(report['heavy_endpoints_isolated'])}`")
    lines.append("")
    lines.append("## Backend Status Truth")
    lines.append("")
    lines.append(f"- Sync overlap guard: `{_yn(report['sync_overlap_guard_present'])}`")
    lines.append(f"- Dashboard core status: `{_yn(report['dashboard_backend_core_status_present'])}`")
    lines.append(f"- request_aborted backend offline degil: `{_yn(report['request_aborted_not_backend_offline'])}`")
    lines.append(f"- Mutation global abort signal yok: `{_yn(report['mutation_no_global_abort_signal'])}`")
    lines.append("")
    lines.append("## Onceki Auditler")
    lines.append("")
    lines.append(f"- 40.16: `{report['prior_40_16_status']}`")
    lines.append(f"- 40.17: `{report['prior_40_17_status']}`")
    lines.append(f"- 40.18: `{report['prior_40_18_status']}`")
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
        lines.append("Mutation abort izolasyonu, agir endpoint ayrimi ve Backend API status guard kontrolleri temiz.")
    else:
        lines.append("Mutation abort izolasyonu blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT_OK",
        "blocker": "LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"mutation_prevent_global_abort={str(report['mutation_prevent_global_abort']).lower()}")
    print(f"coinfilter_save_protected={str(report['coinfilter_save_protected']).lower()}")
    print(f"rules_save_protected={str(report['rules_save_protected']).lower()}")
    print(f"audit_best_effort_abort={str(report['audit_best_effort_abort']).lower()}")
    print(f"heavy_endpoints_isolated={str(report['heavy_endpoints_isolated']).lower()}")
    print(f"request_aborted_not_backend_offline={str(report['request_aborted_not_backend_offline']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
