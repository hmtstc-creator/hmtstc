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
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
STRATEGIES_JS = ROOT / "frontend" / "js" / "pages" / "strategies.js"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
AUDIT_21 = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.md"


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
    coin_filter_js = _load_text(COIN_FILTER_JS)
    dashboard_js = _load_text(DASHBOARD_JS)
    strategies_js = _load_text(STRATEGIES_JS)
    audit_20 = _load_json(AUDIT_20)
    audit_21 = _load_json(AUDIT_21)

    coin_save = _section(coin_filter_js, "save: async function", "refreshScan: async function")
    update_draft = _section(coin_filter_js, "updateDraft: function", "collectSettings: function")
    selection_fn = _section(dashboard_js, "function selectionState", "function checkList")
    checklist_fn = _section(dashboard_js, "function checkList", "window.HMTSTC_PAGES.dashboard")
    save_selection_fn = _section(rules_js, "saveDashboardRuleSelection: async function", "activatePaperLabRules: async function")
    activate_fn = _section(rules_js, "activatePaperLabRules: async function", "exportRulesDebugFile: async function")
    auto_fn = _section(rules_js, "autoBuildPaperLabModels: async function", "pushRuleLog: function")

    coinfilter_draft_state_present = _contains_all(state_js, [
        "coinFilterDraft",
        "coinFilterDirty",
        "coinFilterDraftSource",
        "coinFilterLastSavedAt",
    ]) and _contains_all(coin_filter_js, [
        "initDraft: function",
        "updateDraft: function",
        "HMTSTC_APP.state.coinFilterDraft",
        "HMTSTC_APP.state.coinFilterDirty = true",
        "oninput='HMTSTC_COIN_FILTER_ACTIONS.updateDraft",
    ])
    coinfilter_prevent_submit_present = _contains_all(coin_filter_js, [
        "event.preventDefault",
        "type='button'",
        "HMTSTC_COIN_FILTER_ACTIONS.save(event)",
        "window.scrollTo(0, scrollY)",
    ])
    coinfilter_no_immediate_heavy_sync = "await HMTSTC_APP.syncHeavyApiData()" not in coin_save and "skipHeavySync: true" in coin_save
    coinfilter_save_core_refresh_present = _contains_all(coin_save, [
        '"/api/settings"',
        'method: "POST"',
        'requestKind: "mutation"',
        "preventGlobalAbort: true",
        "timeoutMs: 15000",
        "requestKind: \"core_read\"",
        "HMTSTC_APP.syncApiData({ skipHeavySync: true })",
    ])
    coinfilter_numeric_conversion_present = _contains_all(coin_filter_js, [
        "toNumber: function",
        "data-cf-type",
        'type === "number"',
    ])
    coinfilter_draft_preserved_on_error = _contains_all(coin_save, [
        "form değerleri korunuyor",
        "HMTSTC_APP.state.coinFilterSaving = false",
    ]) and "HMTSTC_APP.state.coinFilterDirty = false" not in _section(coin_save, "} catch (error)", "} finally")

    rules_last_known_selection_present = _contains_all(state_js, [
        "lastKnownRulesSelection",
        "filter: null",
        "strategy: null",
    ]) and _contains_all(api_js, [
        "lastKnownRulesSelection",
        "selected_filter_ids",
        "selected_strategy_ids",
        "previousRules.selected_filter_ids",
        "previousRules.selected_strategy_ids",
    ])
    dashboard_no_default_all_selected = (
        "active_fallback" not in selection_fn
        and "activeRuleIds(fallbackAll)" not in selection_fn
        and '"no_backend_selection"' in selection_fn
        and 'const checked = selectedIds.indexOf(id) !== -1 ? " checked" : "";' in checklist_fn
    )
    rules_update_draft_no_active_fallback = (
        "this.activeRuleIds(source)" not in _section(rules_js, "updateDashboardRuleDraft: function", "newRuleDraft: function")
        and "lastKnownRulesSelection" in _section(rules_js, "updateDashboardRuleDraft: function", "newRuleDraft: function")
    )
    paper_lab_selection_preserved = _contains_all(activate_fn, [
        "activeSelectionBefore",
        "activeSelectionAfter",
        "paper_lab_after_refresh",
        "afterPaperLabFilterIds",
        "afterPaperLabStrategyIds",
    ])
    paper_lab_success_state_present = _contains_all(state_js, ["lastPaperLabResult"]) and _contains_all(activate_fn, [
        "this.state.lastPaperLabResult",
        "accepted_combinations",
        "rejected_combinations",
        "model_count",
        "HMTSTC_DATA.paperLabStatus",
    ]) and _contains_all(auto_fn, [
        "this.state.lastPaperLabResult",
        "selected_filter_count",
        "selected_strategy_count",
    ])
    strategies_paper_lab_visibility_present = _contains_all(strategies_js, [
        "lastPaperLabResult",
        "paperLabStatus",
        "Son Paper Lab Çalışması",
        "accepted_combinations",
        "rejected_combinations",
        "lastRunPanel",
    ])
    paper_lab_refresh_error_preserves_success = "Paper Lab başarılı kaydedildi; ancak son refresh tamamlanamadı." in rules_js
    rules_selection_proof_state_present = _contains_all(state_js, [
        "dashboardRenderedRuleSelection",
        "rulesSelectionProof",
        "rulesSelectionProofHistory",
    ])
    paper_lab_activate_independent_payload = _contains_all(activate_fn, [
        "paper_lab_scope",
        "all_eligible",
    ]) and "selected_filter_ids: selectedFilters" not in activate_fn and "selected_strategy_ids: selectedStrategies" not in activate_fn
    rules_save_payload_proof_present = paper_lab_activate_independent_payload and _contains_all(save_selection_fn, [
        'this.setRulesSelectionProof("save_payload"',
        "save_payload_filter_ids",
        "save_payload_strategy_ids",
        "selected_filter_ids: selectionSnapshot.filter",
        "selected_strategy_ids: selectionSnapshot.strategy",
    ])
    rules_backend_response_proof_present = _contains_all(save_selection_fn, [
        'this.setRulesSelectionProof("backend_response"',
        "result.selected_filter_ids",
        "result.selected_strategy_ids",
        "response_filter_matches_payload",
        "response_strategy_matches_payload",
    ])
    dashboard_render_selection_proof_present = _contains_all(dashboard_js, [
        "recordDashboardRuleSelectionProof",
        "dashboardRenderedRuleSelection",
        "render_filter_ids",
        "render_strategy_ids",
        "render_filter_matches_payload",
        "render_strategy_matches_payload",
    ])
    paper_lab_post_render_proof_present = _contains_all(activate_fn, [
        'this.setRulesSelectionProof("paper_lab_after_refresh"',
        "afterPaperLabFilterIds",
        "afterPaperLabStrategyIds",
        "this.render();",
    ])
    rules_save_end_to_end_selection_proof_present = (
        rules_selection_proof_state_present
        and rules_save_payload_proof_present
        and rules_backend_response_proof_present
        and dashboard_render_selection_proof_present
        and paper_lab_post_render_proof_present
    )
    prior_40_20_status = audit_20.get("status")
    prior_40_21_status = audit_21.get("status")

    checks = {
        "coinfilter_draft_state_present": coinfilter_draft_state_present,
        "coinfilter_prevent_submit_present": coinfilter_prevent_submit_present,
        "coinfilter_no_immediate_heavy_sync": coinfilter_no_immediate_heavy_sync,
        "coinfilter_save_core_refresh_present": coinfilter_save_core_refresh_present,
        "coinfilter_numeric_conversion_present": coinfilter_numeric_conversion_present,
        "coinfilter_draft_preserved_on_error": coinfilter_draft_preserved_on_error,
        "rules_last_known_selection_present": rules_last_known_selection_present,
        "dashboard_no_default_all_selected": dashboard_no_default_all_selected,
        "rules_update_draft_no_active_fallback": rules_update_draft_no_active_fallback,
        "paper_lab_selection_preserved": paper_lab_selection_preserved,
        "paper_lab_success_state_present": paper_lab_success_state_present,
        "strategies_paper_lab_visibility_present": strategies_paper_lab_visibility_present,
        "paper_lab_refresh_error_preserves_success": paper_lab_refresh_error_preserves_success,
        "rules_selection_proof_state_present": rules_selection_proof_state_present,
        "rules_save_payload_proof_present": rules_save_payload_proof_present,
        "rules_backend_response_proof_present": rules_backend_response_proof_present,
        "dashboard_render_selection_proof_present": dashboard_render_selection_proof_present,
        "paper_lab_post_render_proof_present": paper_lab_post_render_proof_present,
        "rules_save_end_to_end_selection_proof_present": rules_save_end_to_end_selection_proof_present,
        "prior_40_20_ok": prior_40_20_status == "ok",
        "prior_40_21_ok": prior_40_21_status == "ok",
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    status = "blocker" if blockers else "ok"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_40_20_status": prior_40_20_status,
        "prior_40_21_status": prior_40_21_status,
        "blockers": blockers,
        "recommended_next_actions": [
            "Keep CoinFilter edits in local draft until save succeeds.",
            "Never treat an empty selected id list as all selected.",
            "Keep Paper Lab success state visible outside heavy reports.",
            "Run 40.22 before opening Paket 11.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.22 CoinFilter Rules PaperLab Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- CoinFilter draft state: `{_yn(report['coinfilter_draft_state_present'])}`")
    lines.append(f"- CoinFilter submit engeli: `{_yn(report['coinfilter_prevent_submit_present'])}`")
    lines.append(f"- Rules default-all yok: `{_yn(report['dashboard_no_default_all_selected'])}`")
    lines.append(f"- Rules save E2E proof: `{_yn(report['rules_save_end_to_end_selection_proof_present'])}`")
    lines.append(f"- Paper Lab visibility: `{_yn(report['strategies_paper_lab_visibility_present'])}`")
    lines.append("")
    lines.append("## CoinFilter")
    lines.append("")
    lines.append(f"- Immediate heavy sync yok: `{_yn(report['coinfilter_no_immediate_heavy_sync'])}`")
    lines.append(f"- Save core refresh: `{_yn(report['coinfilter_save_core_refresh_present'])}`")
    lines.append(f"- Numeric conversion: `{_yn(report['coinfilter_numeric_conversion_present'])}`")
    lines.append(f"- Error durumunda draft korunur: `{_yn(report['coinfilter_draft_preserved_on_error'])}`")
    lines.append("")
    lines.append("## Rules Selection")
    lines.append("")
    lines.append(f"- Last known selection: `{_yn(report['rules_last_known_selection_present'])}`")
    lines.append(f"- Draft active fallback yok: `{_yn(report['rules_update_draft_no_active_fallback'])}`")
    lines.append(f"- Paper Lab selection korunur: `{_yn(report['paper_lab_selection_preserved'])}`")
    lines.append(f"- Proof state: `{_yn(report['rules_selection_proof_state_present'])}`")
    lines.append(f"- Save payload proof: `{_yn(report['rules_save_payload_proof_present'])}`")
    lines.append(f"- Backend response proof: `{_yn(report['rules_backend_response_proof_present'])}`")
    lines.append(f"- Dashboard render checked proof: `{_yn(report['dashboard_render_selection_proof_present'])}`")
    lines.append(f"- Paper Lab sonrasi render proof: `{_yn(report['paper_lab_post_render_proof_present'])}`")
    lines.append("")
    lines.append("## Paper Lab")
    lines.append("")
    lines.append(f"- Success state: `{_yn(report['paper_lab_success_state_present'])}`")
    lines.append(f"- Refresh error success silmez: `{_yn(report['paper_lab_refresh_error_preserves_success'])}`")
    lines.append(f"- 40.20: `{report['prior_40_20_status']}`")
    lines.append(f"- 40.21: `{report['prior_40_21_status']}`")
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
        lines.append("CoinFilter draft, rules selection integrity ve Paper Lab visibility kontrolleri temiz.")
    else:
        lines.append("CoinFilter / rules / Paper Lab blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT_OK",
        "blocker": "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"coinfilter_draft_state_present={str(report['coinfilter_draft_state_present']).lower()}")
    print(f"dashboard_no_default_all_selected={str(report['dashboard_no_default_all_selected']).lower()}")
    print(f"paper_lab_success_state_present={str(report['paper_lab_success_state_present']).lower()}")
    print(f"strategies_paper_lab_visibility_present={str(report['strategies_paper_lab_visibility_present']).lower()}")
    print(f"rules_save_end_to_end_selection_proof_present={str(report['rules_save_end_to_end_selection_proof_present']).lower()}")
    print(f"prior_40_20_status={report['prior_40_20_status']}")
    print(f"prior_40_21_status={report['prior_40_21_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
