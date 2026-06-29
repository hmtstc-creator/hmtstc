#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULE_ENGINE = ROOT / "backend" / "services" / "rule_engine.py"
RULE_ROUTES = ROOT / "backend" / "routes" / "rule_routes.py"
STATE_JS = ROOT / "frontend" / "js" / "app" / "state.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
AUDIT_21 = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
AUDIT_22 = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.md"


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
    rule_engine = _load_text(RULE_ENGINE)
    rule_routes = _load_text(RULE_ROUTES)
    state_js = _load_text(STATE_JS)
    api_js = _load_text(API_JS)
    rules_js = _load_text(RULES_JS)
    dashboard_js = _load_text(DASHBOARD_JS)
    audit_20 = _load_json(AUDIT_20)
    audit_21 = _load_json(AUDIT_21)
    audit_22 = _load_json(AUDIT_22)

    selection_state_fn = _section(dashboard_js, "function selectionState", "function normalizeIdList")
    checklist_fn = _section(dashboard_js, "function checkList", "window.HMTSTC_PAGES.dashboard")
    save_selection_fn = _section(rules_js, "saveDashboardRuleSelection: async function", "activatePaperLabRules: async function")
    activate_fn = _section(rules_js, "activatePaperLabRules: async function", "exportRulesDebugFile: async function")
    engine_activate_fn = _section(rule_engine, "def activate_paper_lab_rules", "def export_rules")
    engine_build_models_fn = _section(rule_engine, "def build_custom_models", "def activate_paper_lab_rules")
    route_activate_fn = _section(rule_routes, '@router.post("/activate-paper-lab")', '@router.post("/auto-paper-lab")')

    dashboard_active_selection_source_present = _contains_all(rule_engine, [
        "def save_rule_selection",
        'user_state["selected_filter_ids"]',
        'user_state["selected_strategy_ids"]',
    ]) and _contains_all(rule_routes, [
        '@router.post("/selection")',
        "save_rule_selection(",
    ]) and _contains_all(save_selection_fn, [
        '"/api/rules/selection"',
        "selected_filter_ids: selectionSnapshot.filter",
        "selected_strategy_ids: selectionSnapshot.strategy",
    ])
    empty_selected_list_not_default_all = (
        "active_fallback" not in selection_state_fn
        and "activeRuleIds(fallbackAll)" not in selection_state_fn
        and 'const checked = selectedIds.indexOf(id) !== -1 ? " checked" : "";' in checklist_fn
    )
    missing_selected_field_not_default_all = (
        '"no_backend_selection"' in selection_state_fn
        and "lastKnownRulesSelection" in dashboard_js
        and "active_fallback" not in dashboard_js
    )
    last_known_not_overwritten_by_paper_lab = (
        "lastKnownRulesSelection" not in activate_fn
        and "selected_filter_ids" not in route_activate_fn
        and "selected_strategy_ids" not in route_activate_fn
    )
    rules_save_proof_state_present = _contains_all(state_js, [
        "rulesSelectionProof",
        "rulesSelectionProofHistory",
        "dashboardRenderedRuleSelection",
    ]) and _contains_all(rules_js, [
        "beforeSaveFilterIds",
        "payloadFilterIds",
        "responseFilterIds",
        "refreshFilterIds",
    ]) and _contains_all(save_selection_fn, [
        'this.setRulesSelectionProof("save_payload"',
        'this.setRulesSelectionProof("backend_response"',
        'this.setRulesSelectionProof("core_refresh"',
    ])
    save_response_refresh_render_comparison_present = _contains_all(save_selection_fn, [
        "filterSelectionMatches",
        "strategySelectionMatches",
        "refreshMatches",
        "mismatchStage",
        "core_refresh",
    ])
    dashboard_render_selected_ids_only = _contains_all(dashboard_js, [
        "recordDashboardRuleSelectionProof",
        "render_filter_ids",
        "render_strategy_ids",
    ]) and "item.enabled !== false && item.active !== false ? \" checked\"" not in checklist_fn

    paper_lab_payload_independent = _contains_all(activate_fn, [
        "paper_lab_scope",
        "all_eligible",
        '"/api/rules/activate-paper-lab"',
    ]) and "selected_filter_ids:" not in activate_fn and "selected_strategy_ids:" not in activate_fn
    paper_lab_response_not_applied_to_dashboard_selection = (
        "HMTSTC_DATA.rules = Object.assign" not in activate_fn
        and "lastKnownRulesSelection" not in activate_fn
        and "result.selected_filter_ids" not in activate_fn
        and "result.selected_strategy_ids" not in activate_fn
    )
    paper_lab_state_separate_present = _contains_all(state_js, [
        "paperLabRunning",
        "paperLabRun",
        "lastPaperLabResult",
    ]) and _contains_all(activate_fn, [
        "HMTSTC_DATA.paperLabStatus",
        "this.state.lastPaperLabResult",
        "this.state.paperLabRun",
    ])
    paper_lab_after_dashboard_selection_preserved = _contains_all(activate_fn, [
        "activeSelectionBefore",
        "activeSelectionAfter",
        "afterPaperLabFilterIds",
        "afterPaperLabStrategyIds",
        "paper_lab_after_refresh",
    ])
    paper_lab_running_finally_reset = _contains_all(activate_fn, [
        "this.state.paperLabRunning = true",
        "} finally {",
        "this.state.paperLabRunning = false",
    ])
    paper_lab_rerun_state_guard_present = _contains_all(activate_fn, [
        "if (this.state.paperLabRunning)",
        "Paper Lab çalışması zaten devam ediyor",
    ])
    backend_paper_lab_does_not_persist_selection = (
        'user_state["selected_filter_ids"] = final_filter_ids' not in engine_activate_fn
        and 'user_state["selected_strategy_ids"] = final_strategy_ids' not in engine_activate_fn
        and "paper_lab_filter_ids" in engine_activate_fn
        and "paper_lab_strategy_ids" in engine_activate_fn
    )
    backend_paper_lab_uses_all_enabled_rules = (
        "use_active_selection: bool = False" in engine_build_models_fn
        and "get_enabled_rules(username)" in engine_build_models_fn
        and "build_custom_models(username)" in engine_activate_fn
    )

    prior_40_20_status = audit_20.get("status")
    prior_40_21_status = audit_21.get("status")
    prior_40_22_status = audit_22.get("status")

    checks = {
        "dashboard_active_selection_source_present": dashboard_active_selection_source_present,
        "empty_selected_list_not_default_all": empty_selected_list_not_default_all,
        "missing_selected_field_not_default_all": missing_selected_field_not_default_all,
        "last_known_not_overwritten_by_paper_lab": last_known_not_overwritten_by_paper_lab,
        "rules_save_proof_state_present": rules_save_proof_state_present,
        "save_response_refresh_render_comparison_present": save_response_refresh_render_comparison_present,
        "dashboard_render_selected_ids_only": dashboard_render_selected_ids_only,
        "paper_lab_payload_independent": paper_lab_payload_independent,
        "paper_lab_response_not_applied_to_dashboard_selection": paper_lab_response_not_applied_to_dashboard_selection,
        "paper_lab_state_separate_present": paper_lab_state_separate_present,
        "paper_lab_after_dashboard_selection_preserved": paper_lab_after_dashboard_selection_preserved,
        "paper_lab_running_finally_reset": paper_lab_running_finally_reset,
        "paper_lab_rerun_state_guard_present": paper_lab_rerun_state_guard_present,
        "backend_paper_lab_does_not_persist_selection": backend_paper_lab_does_not_persist_selection,
        "backend_paper_lab_uses_all_enabled_rules": backend_paper_lab_uses_all_enabled_rules,
        "prior_40_20_ok": prior_40_20_status == "ok",
        "prior_40_21_ok": prior_40_21_status == "ok",
        "prior_40_22_ok": prior_40_22_status == "ok",
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
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.23 Rules PaperLab Independence Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Dashboard active selection source: `{_yn(report['dashboard_active_selection_source_present'])}`")
    lines.append(f"- Default-all yok: `{_yn(report['empty_selected_list_not_default_all'])}`")
    lines.append(f"- Paper Lab payload independent: `{_yn(report['paper_lab_payload_independent'])}`")
    lines.append(f"- Paper Lab rerun guard: `{_yn(report['paper_lab_rerun_state_guard_present'])}`")
    lines.append("")
    lines.append("## Rules Selection Persistence")
    lines.append("")
    for key in [
        "missing_selected_field_not_default_all",
        "last_known_not_overwritten_by_paper_lab",
        "rules_save_proof_state_present",
        "save_response_refresh_render_comparison_present",
        "dashboard_render_selected_ids_only",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Paper Lab Independence")
    lines.append("")
    for key in [
        "paper_lab_response_not_applied_to_dashboard_selection",
        "paper_lab_state_separate_present",
        "paper_lab_after_dashboard_selection_preserved",
        "paper_lab_running_finally_reset",
        "backend_paper_lab_does_not_persist_selection",
        "backend_paper_lab_uses_all_enabled_rules",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Onceki Auditler")
    lines.append("")
    lines.append(f"- 40.20: `{report['prior_40_20_status']}`")
    lines.append(f"- 40.21: `{report['prior_40_21_status']}`")
    lines.append(f"- 40.22: `{report['prior_40_22_status']}`")
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
        lines.append("Dashboard active selection persistence ve Paper Lab independence kontrolleri temiz.")
    else:
        lines.append("Rules selection veya Paper Lab independence blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT_OK",
        "blocker": "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"dashboard_active_selection_source_present={str(report['dashboard_active_selection_source_present']).lower()}")
    print(f"paper_lab_payload_independent={str(report['paper_lab_payload_independent']).lower()}")
    print(f"paper_lab_running_finally_reset={str(report['paper_lab_running_finally_reset']).lower()}")
    print(f"prior_40_20_status={report['prior_40_20_status']}")
    print(f"prior_40_21_status={report['prior_40_21_status']}")
    print(f"prior_40_22_status={report['prior_40_22_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
