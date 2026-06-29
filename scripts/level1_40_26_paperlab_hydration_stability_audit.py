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
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
STRATEGIES_JS = ROOT / "frontend" / "js" / "pages" / "strategies.js"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
AUDIT_21 = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
AUDIT_22 = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json"
AUDIT_23 = ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json"
AUDIT_24 = ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json"
AUDIT_25 = ROOT / "docs" / "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.md"


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


def _contains_all(text: str, values: list[str]) -> bool:
    return all(value in text for value in values)


def build_report() -> dict[str, Any]:
    state_js = _load_text(STATE_JS)
    api_js = _load_text(API_JS)
    rules_js = _load_text(RULES_JS)
    strategies_js = _load_text(STRATEGIES_JS)
    audit_20 = _load_json(AUDIT_20)
    audit_21 = _load_json(AUDIT_21)
    audit_22 = _load_json(AUDIT_22)
    audit_23 = _load_json(AUDIT_23)
    audit_24 = _load_json(AUDIT_24)
    audit_25 = _load_json(AUDIT_25)

    apply_status_fn = _section(api_js, "applyPaperLabStatusPayload: function", "fetchPaperLabStatus: async function")
    fetch_status_fn = _section(api_js, "fetchPaperLabStatus: async function", "syncUsersData: async function")
    should_fetch_fn = _section(api_js, "shouldFetchPaperLabStatus: function", "applyPaperLabStatusPayload: function")
    sync_fn = _section(api_js, "syncApiData: async function", "syncHeavyApiData: async function")
    fallback_requests = _section(sync_fn, "const results = await Promise.allSettled", "const keys = [")
    activate_fn = _section(rules_js, "activatePaperLabRules: async function", "exportRulesDebugFile: async function")

    paper_lab_status_throttle_present = _contains_all(state_js + should_fetch_fn, [
        "paperLabStatusLastFetchMs",
        "paperLabStatusMinIntervalMs: 60000",
        "Date.now() - lastFetchMs >= minIntervalMs",
    ])
    paper_lab_status_in_progress_guard_present = _contains_all(state_js + should_fetch_fn + fetch_status_fn, [
        "paperLabStatusFetchInProgress",
        "if (state.paperLabStatusFetchInProgress)",
        "HMTSTC_APP.state.paperLabStatusFetchInProgress = true",
        "HMTSTC_APP.state.paperLabStatusFetchInProgress = false",
    ])
    paper_lab_status_force_refresh_present = _contains_all(fetch_status_fn + activate_fn, [
        "force",
        "paper_lab_force_refresh",
        "this.fetchPaperLabStatus({ force: true",
        "skipPaperLabStatusFetch: true",
    ])
    bundle_paper_lab_status_preferred = _contains_all(sync_fn, [
        "const bundlePaperLabApplied = this.applyPaperLabStatusPayload(bundled.paper_lab_status, \"dashboard_bundle\")",
        "if (!bundlePaperLabApplied && !skipPaperLabStatusFetch)",
        "bundle_missing_throttled",
    ])
    paper_lab_status_does_not_clear_rules = (
        "HMTSTC_DATA.rules" not in apply_status_fn
        and "selected_filter_ids" not in apply_status_fn
        and "selected_strategy_ids" not in apply_status_fn
        and "lastKnownRulesSelection" not in apply_status_fn
        and "filters" not in apply_status_fn
        and "strategies" not in apply_status_fn
    )
    rules_render_preserve_on_partial_payload = _contains_all(api_js, [
        "isSafeRulesPayload",
        "preserved_after_empty_payload",
        "rules_payload_preserved: true",
        "this.preserveOrApplyRulesPayload(bundled.rules, \"dashboard_bundle\")",
        "HMTSTC_APP.preserveOrApplyRulesPayload(result.value, \"api_rules\")",
    ])
    strategies_panel_isolated_loading_present = _contains_all(strategies_js, [
        "paperLabStatusLoading",
        "isolatedPaperLabLoadingMessage",
        "Paper Lab sonucu yükleniyor...",
        "persistentLastRun",
    ])
    request_coalescing_present = (
        '"/api/rules/paper-lab/status"' not in fallback_requests
        and _contains_all(sync_fn, [
            "bundle_status",
            "fallback",
            "this.fetchPaperLabStatus({ force: false, render: true",
            "skipPaperLabStatusFetch",
        ])
    )

    prior_40_20_status = audit_20.get("status")
    prior_40_21_status = audit_21.get("status")
    prior_40_22_status = audit_22.get("status")
    prior_40_23_status = audit_23.get("status")
    prior_40_24_status = audit_24.get("status")
    prior_40_25_status = audit_25.get("status")

    checks = {
        "paper_lab_status_throttle_present": paper_lab_status_throttle_present,
        "paper_lab_status_in_progress_guard_present": paper_lab_status_in_progress_guard_present,
        "paper_lab_status_force_refresh_present": paper_lab_status_force_refresh_present,
        "bundle_paper_lab_status_preferred": bundle_paper_lab_status_preferred,
        "paper_lab_status_does_not_clear_rules": paper_lab_status_does_not_clear_rules,
        "rules_render_preserve_on_partial_payload": rules_render_preserve_on_partial_payload,
        "strategies_panel_isolated_loading_present": strategies_panel_isolated_loading_present,
        "request_coalescing_present": request_coalescing_present,
        "prior_40_20_ok": prior_40_20_status == "ok",
        "prior_40_21_ok": prior_40_21_status == "ok",
        "prior_40_22_ok": prior_40_22_status == "ok",
        "prior_40_23_ok": prior_40_23_status == "ok",
        "prior_40_24_ok": prior_40_24_status == "ok",
        "prior_40_25_ok": prior_40_25_status == "ok",
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    status = "blocker" if blockers else "ok"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_40_20_status": prior_40_20_status,
        "prior_40_21_status": prior_40_21_status,
        "prior_40_22_status": prior_40_22_status,
        "prior_40_23_status": prior_40_23_status,
        "prior_40_24_status": prior_40_24_status,
        "prior_40_25_status": prior_40_25_status,
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.26 PaperLab Hydration Stability Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Status throttle: `{_yn(report['paper_lab_status_throttle_present'])}`")
    lines.append(f"- In-progress guard: `{_yn(report['paper_lab_status_in_progress_guard_present'])}`")
    lines.append(f"- Bundle status onceligi: `{_yn(report['bundle_paper_lab_status_preferred'])}`")
    lines.append(f"- Request coalescing: `{_yn(report['request_coalescing_present'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key in [
        "paper_lab_status_force_refresh_present",
        "paper_lab_status_does_not_clear_rules",
        "rules_render_preserve_on_partial_payload",
        "strategies_panel_isolated_loading_present",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Onceki Auditler")
    lines.append("")
    for number in ["20", "21", "22", "23", "24", "25"]:
        lines.append(f"- 40.{number}: `{report[f'prior_40_{number}_status']}`")
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
        lines.append("Paper Lab hydration throttle ve rules render stability kontrolleri temiz.")
    else:
        lines.append("Paper Lab hydration stability blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT_OK",
        "blocker": "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"paper_lab_status_throttle_present={str(report['paper_lab_status_throttle_present']).lower()}")
    print(f"paper_lab_status_in_progress_guard_present={str(report['paper_lab_status_in_progress_guard_present']).lower()}")
    print(f"bundle_paper_lab_status_preferred={str(report['bundle_paper_lab_status_preferred']).lower()}")
    print(f"request_coalescing_present={str(report['request_coalescing_present']).lower()}")
    print(f"prior_40_25_status={report['prior_40_25_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
