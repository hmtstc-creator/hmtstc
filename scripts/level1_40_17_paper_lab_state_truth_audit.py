#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
AUDIT_13 = ROOT / "docs" / "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.json"
AUDIT_14 = ROOT / "docs" / "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT.json"
AUDIT_15 = ROOT / "docs" / "LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT.json"
AUDIT_16 = ROOT / "docs" / "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT.md"


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
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        return text[start_index:]
    return text[start_index:end_index]


def build_report() -> dict[str, Any]:
    rules_js = _load_text(RULES_JS)
    api_js = _load_text(API_JS)
    dashboard_js = _load_text(DASHBOARD_JS)
    auto_fn = _section(rules_js, "autoBuildPaperLabModels: async function ()", "pushRuleLog: function")
    bundle_section = _section(api_js, "if (bundled && bundled.status === \"ok\")", "if (bundleError")
    audits = {
        "40.13": _load_json(AUDIT_13),
        "40.14": _load_json(AUDIT_14),
        "40.15": _load_json(AUDIT_15),
        "40.16": _load_json(AUDIT_16),
    }

    auto_paper_lab_no_api_ready_hard_block = not (
        "!HMTSTC_APP.state.apiReady && !HMTSTC_APP.state.apiSyncReady" in auto_fn
        and "Backend erişilemiyor. Auto Paper Lab başlatılmadı" in auto_fn
    )
    auto_paper_lab_fetches_rules_first = (
        'this.fetchJson("/api/rules"' in auto_fn
        and 'this.fetchJson("/api/rules"' in auto_fn
        and auto_fn.find('this.fetchJson("/api/rules"') < auto_fn.find('this.fetchJson("/api/rules/auto-paper-lab"')
    )
    auto_paper_lab_auth_expired_precheck_present = (
        "authExpired" in auto_fn
        and "auth_expired" in auto_fn
        and "Oturum süresi doldu. Auto Paper Lab başlatılmadı" in auto_fn
    )
    auto_paper_lab_401_not_backend_offline = (
        'type === "http_401"' in auto_fn
        and "Oturum süresi doldu. Filtre/strateji listesi korunuyor" in auto_fn
    )
    auto_paper_lab_403_role_message_present = (
        'type === "http_403"' in auto_fn
        and "Yetki yetersiz. Paper Lab için rol/izin kontrol edilmeli." in auto_fn
    )
    auto_paper_lab_success_preserved_after_refresh_error = (
        "Paper Lab başarılı kaydedildi; ancak son refresh tamamlanamadı." in auto_fn
        and "try {" in auto_fn
        and "await this.syncApiData()" in auto_fn
        and "catch (syncError)" in auto_fn
    )
    api_bundle_preserve_existing_rules_present = (
        "isSafeRulesPayload" in api_js
        and "preserveOrApplyRulesPayload" in api_js
        and "this.preserveOrApplyRulesPayload(bundled.rules, \"dashboard_bundle\")" in bundle_section
        and "rules_payload_preserved" in api_js
    )
    api_http_401_backend_online_present = (
        'type === "http_401"' in api_js
        and 'backend_api: "online"' in api_js
        and 'auth_status: "auth_expired"' in api_js
    )
    api_http_403_backend_online_present = (
        'type === "http_403"' in api_js
        and 'backend_api: backendApiStatus' in api_js
        and 'type === "http_403" ? "forbidden"' in api_js
    )
    dashboard_backend_status_truth_present = (
        '["http_401", "http_403", "http_404"]' in dashboard_js
        and (
            '["backend_offline", "timeout", "cors_error"]' in dashboard_js
            or '["backend_offline", "timeout", "cors_error", "http_500"]' in dashboard_js
        )
        and "lastApiErrorType" in dashboard_js
        and ("lastApiRequestKind" in dashboard_js or "last_api_request_kind" in dashboard_js)
        and ("coreError" in dashboard_js or "coreSensitiveError" in dashboard_js)
        and "HMTSTC_APP.state.apiReady || HMTSTC_APP.state.apiSyncReady" in dashboard_js
    )
    dashboard_auth_status_item_present = (
        'systemStatusItem("Oturum"' in dashboard_js
        and "Süresi Doldu" in dashboard_js
        and "Yetki Yok" in dashboard_js
    )
    rules_refresh_error_preserves_rules_present = (
        "error && error.status === 401" in rules_js
        and "son başarılı filtre/strateji listesi korunuyor" in rules_js
        and "return false" in _section(rules_js, "refreshRulesData: async function", "updateLocalRulesCache")
    )

    blockers: list[str] = []
    for name, value in [
        ("auto_paper_lab_no_api_ready_hard_block", auto_paper_lab_no_api_ready_hard_block),
        ("auto_paper_lab_fetches_rules_first", auto_paper_lab_fetches_rules_first),
        ("auto_paper_lab_auth_expired_precheck_present", auto_paper_lab_auth_expired_precheck_present),
        ("auto_paper_lab_401_not_backend_offline", auto_paper_lab_401_not_backend_offline),
        ("auto_paper_lab_403_role_message_present", auto_paper_lab_403_role_message_present),
        ("auto_paper_lab_success_preserved_after_refresh_error", auto_paper_lab_success_preserved_after_refresh_error),
        ("api_bundle_preserve_existing_rules_present", api_bundle_preserve_existing_rules_present),
        ("api_http_401_backend_online_present", api_http_401_backend_online_present),
        ("api_http_403_backend_online_present", api_http_403_backend_online_present),
        ("dashboard_backend_status_truth_present", dashboard_backend_status_truth_present),
        ("dashboard_auth_status_item_present", dashboard_auth_status_item_present),
        ("rules_refresh_error_preserves_rules_present", rules_refresh_error_preserves_rules_present),
    ]:
        if not value:
            blockers.append(f"{name}=false")

    prior_statuses = {name: audit.get("status") for name, audit in audits.items()}
    for name, status in prior_statuses.items():
        if status != "ok":
            blockers.append(f"{name} status is {status}")

    status = "blocker" if blockers else "ok"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auto_paper_lab_no_api_ready_hard_block": auto_paper_lab_no_api_ready_hard_block,
        "auto_paper_lab_fetches_rules_first": auto_paper_lab_fetches_rules_first,
        "auto_paper_lab_auth_expired_precheck_present": auto_paper_lab_auth_expired_precheck_present,
        "auto_paper_lab_401_not_backend_offline": auto_paper_lab_401_not_backend_offline,
        "auto_paper_lab_403_role_message_present": auto_paper_lab_403_role_message_present,
        "auto_paper_lab_success_preserved_after_refresh_error": auto_paper_lab_success_preserved_after_refresh_error,
        "api_bundle_preserve_existing_rules_present": api_bundle_preserve_existing_rules_present,
        "api_http_401_backend_online_present": api_http_401_backend_online_present,
        "api_http_403_backend_online_present": api_http_403_backend_online_present,
        "dashboard_backend_status_truth_present": dashboard_backend_status_truth_present,
        "dashboard_auth_status_item_present": dashboard_auth_status_item_present,
        "rules_refresh_error_preserves_rules_present": rules_refresh_error_preserves_rules_present,
        "prior_40_13_status": prior_statuses["40.13"],
        "prior_40_14_status": prior_statuses["40.14"],
        "prior_40_15_status": prior_statuses["40.15"],
        "prior_40_16_status": prior_statuses["40.16"],
        "blockers": blockers,
        "review_items": [],
        "recommended_next_actions": [
            "Keep Auto Paper Lab tied to fresh /api/rules response before local cache decisions.",
            "Preserve successful Paper Lab status after refresh failures.",
            "Keep bundled rules guarded with preserveOrApplyRulesPayload.",
            "Do not treat HTTP 401/403/404 as backend offline.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.17 Paper Lab State Truth Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Auto Paper Lab apiReady hard-block yok: `{_yn(report['auto_paper_lab_no_api_ready_hard_block'])}`")
    lines.append(f"- Auto Paper Lab once /api/rules okur: `{_yn(report['auto_paper_lab_fetches_rules_first'])}`")
    lines.append(f"- Bundle rules preserve guard: `{_yn(report['api_bundle_preserve_existing_rules_present'])}`")
    lines.append(f"- Dashboard backend status truth: `{_yn(report['dashboard_backend_status_truth_present'])}`")
    lines.append("")
    lines.append("## Auto Paper Lab")
    lines.append("")
    lines.append(f"- Auth expired precheck: `{_yn(report['auto_paper_lab_auth_expired_precheck_present'])}`")
    lines.append(f"- 401 backend offline degil: `{_yn(report['auto_paper_lab_401_not_backend_offline'])}`")
    lines.append(f"- 403 role message: `{_yn(report['auto_paper_lab_403_role_message_present'])}`")
    lines.append(f"- Refresh error success preserve: `{_yn(report['auto_paper_lab_success_preserved_after_refresh_error'])}`")
    lines.append("")
    lines.append("## API / Dashboard")
    lines.append("")
    lines.append(f"- API 401 backend online: `{_yn(report['api_http_401_backend_online_present'])}`")
    lines.append(f"- API 403 backend online: `{_yn(report['api_http_403_backend_online_present'])}`")
    lines.append(f"- Dashboard auth status item: `{_yn(report['dashboard_auth_status_item_present'])}`")
    lines.append(f"- Rules refresh preserves rules: `{_yn(report['rules_refresh_error_preserves_rules_present'])}`")
    lines.append("")
    lines.append("## Prior Audits")
    lines.append("")
    lines.append(f"- 40.13: `{report['prior_40_13_status']}`")
    lines.append(f"- 40.14: `{report['prior_40_14_status']}`")
    lines.append(f"- 40.15: `{report['prior_40_15_status']}`")
    lines.append(f"- 40.16: `{report['prior_40_16_status']}`")
    lines.append("")
    lines.append("## Blocker / Review")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- BLOCKER: {blocker}")
    else:
        lines.append("Blocker veya review item yok.")
    lines.append("")
    lines.append("## Sonuc")
    lines.append("")
    if report["status"] == "ok":
        lines.append("Paper Lab state truth, backend status truth ve rule cache preserve kontrolleri temiz.")
    else:
        lines.append("Paper Lab state truth blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT_OK",
        "blocker": "LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"auto_paper_lab_no_api_ready_hard_block={str(report['auto_paper_lab_no_api_ready_hard_block']).lower()}")
    print(f"auto_paper_lab_fetches_rules_first={str(report['auto_paper_lab_fetches_rules_first']).lower()}")
    print(f"auto_paper_lab_401_not_backend_offline={str(report['auto_paper_lab_401_not_backend_offline']).lower()}")
    print(f"auto_paper_lab_403_role_message_present={str(report['auto_paper_lab_403_role_message_present']).lower()}")
    print(f"api_bundle_preserve_existing_rules_present={str(report['api_bundle_preserve_existing_rules_present']).lower()}")
    print(f"dashboard_backend_status_truth_present={str(report['dashboard_backend_status_truth_present']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
