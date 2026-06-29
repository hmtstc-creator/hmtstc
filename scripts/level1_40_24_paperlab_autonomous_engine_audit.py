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
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
AUDIT_21 = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
AUDIT_22 = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json"
AUDIT_23 = ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.md"


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
    rules_js = _load_text(RULES_JS)
    audit_20 = _load_json(AUDIT_20)
    audit_21 = _load_json(AUDIT_21)
    audit_22 = _load_json(AUDIT_22)
    audit_23 = _load_json(AUDIT_23)

    activate_fn = _section(rules_js, "activatePaperLabRules: async function", "exportRulesDebugFile: async function")
    save_selection_fn = _section(rules_js, "saveDashboardRuleSelection: async function", "activatePaperLabRules: async function")
    engine_activate_fn = _section(rule_engine, "def activate_paper_lab_rules", "def export_rules")
    engine_build_models_fn = _section(rule_engine, "def build_custom_models", "def activate_paper_lab_rules")
    route_activate_fn = _section(rule_routes, '@router.post("/activate-paper-lab")', '@router.post("/auto-paper-lab")')

    paper_lab_not_using_selected_filter_ids = (
        "selected_filter_ids" not in activate_fn
        and "selected_filter_ids" not in route_activate_fn
        and "selected_filter_ids" not in engine_activate_fn
    )
    paper_lab_not_using_selected_strategy_ids = (
        "selected_strategy_ids" not in activate_fn
        and "selected_strategy_ids" not in route_activate_fn
        and "selected_strategy_ids" not in engine_activate_fn
    )
    dashboard_selection_not_modified_by_paper_lab = (
        "lastKnownRulesSelection" not in activate_fn
        and "HMTSTC_DATA.rules = Object.assign" not in activate_fn
        and '"/api/rules/selection"' in save_selection_fn
        and "selected_filter_ids: selectionSnapshot.filter" in save_selection_fn
        and "selected_strategy_ids: selectionSnapshot.strategy" in save_selection_fn
    )
    paper_lab_uses_all_enabled_filters = (
        "get_enabled_rules(username)" in engine_build_models_fn
        and "use_active_selection: bool = False" in engine_build_models_fn
        and "build_custom_models(username)" in engine_activate_fn
        and "paper_lab_filter_ids" in engine_activate_fn
    )
    paper_lab_uses_all_enabled_strategies = (
        "get_enabled_rules(username)" in engine_build_models_fn
        and "build_custom_models(username)" in engine_activate_fn
        and "paper_lab_strategy_ids" in engine_activate_fn
        and "paper_lab_candidate_count" in engine_activate_fn
    )
    paper_lab_running_finally_reset = _contains_all(activate_fn, [
        "this.state.paperLabRunning = true",
        "} finally {",
        "this.state.paperLabRunning = false",
    ])
    paper_lab_repeatable_runs_supported = _contains_all(activate_fn, [
        "if (this.state.paperLabRunning)",
        "return;",
        "this.state.paperLabRunning = false",
        "run_id",
    ]) and "if (this.state.paperLabEngineStatus === \"completed\")" not in activate_fn and "already completed" not in activate_fn
    paper_lab_state_isolated = _contains_all(state_js, [
        "paperLabEngineStatus",
        "paperLabRunId",
        "paperLabCandidateCount",
        "paperLabModelCount",
        "paperLabAccepted",
        "paperLabRejected",
        "paperLabStartedAt",
        "paperLabCompletedAt",
    ]) and _contains_all(activate_fn, [
        'this.state.paperLabEngineStatus = "running"',
        'this.state.paperLabEngineStatus = "completed"',
        'this.state.paperLabEngineStatus = "failed"',
        "this.state.paperLabRunId",
        "this.state.paperLabCandidateCount",
        "this.state.paperLabModelCount",
        "this.state.paperLabAccepted",
        "this.state.paperLabRejected",
    ])
    paper_lab_status_lifecycle_present = _contains_all(activate_fn, [
        'status: "running"',
        'status: "completed"',
        'status: "failed"',
        "started_at",
        "completed_at",
    ])
    paper_lab_result_pool_separate = _contains_all(activate_fn, [
        "this.state.paperLabRun",
        "this.state.lastPaperLabResult",
        "HMTSTC_DATA.paperLabStatus",
        "paper_lab_candidate_count",
        "accepted_combinations",
        "rejected_combinations",
    ]) and "HMTSTC_DATA.rules = Object.assign" not in activate_fn

    prior_40_20_status = audit_20.get("status")
    prior_40_21_status = audit_21.get("status")
    prior_40_22_status = audit_22.get("status")
    prior_40_23_status = audit_23.get("status")

    checks = {
        "paper_lab_not_using_selected_filter_ids": paper_lab_not_using_selected_filter_ids,
        "paper_lab_not_using_selected_strategy_ids": paper_lab_not_using_selected_strategy_ids,
        "dashboard_selection_not_modified_by_paper_lab": dashboard_selection_not_modified_by_paper_lab,
        "paper_lab_uses_all_enabled_filters": paper_lab_uses_all_enabled_filters,
        "paper_lab_uses_all_enabled_strategies": paper_lab_uses_all_enabled_strategies,
        "paper_lab_running_finally_reset": paper_lab_running_finally_reset,
        "paper_lab_repeatable_runs_supported": paper_lab_repeatable_runs_supported,
        "paper_lab_state_isolated": paper_lab_state_isolated,
        "paper_lab_status_lifecycle_present": paper_lab_status_lifecycle_present,
        "paper_lab_result_pool_separate": paper_lab_result_pool_separate,
        "prior_40_20_ok": prior_40_20_status == "ok",
        "prior_40_21_ok": prior_40_21_status == "ok",
        "prior_40_22_ok": prior_40_22_status == "ok",
        "prior_40_23_ok": prior_40_23_status == "ok",
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
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.24 PaperLab Autonomous Engine Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Selected filter ids kullanmiyor: `{_yn(report['paper_lab_not_using_selected_filter_ids'])}`")
    lines.append(f"- Selected strategy ids kullanmiyor: `{_yn(report['paper_lab_not_using_selected_strategy_ids'])}`")
    lines.append(f"- Dashboard selection degismiyor: `{_yn(report['dashboard_selection_not_modified_by_paper_lab'])}`")
    lines.append(f"- Repeatable run: `{_yn(report['paper_lab_repeatable_runs_supported'])}`")
    lines.append("")
    lines.append("## Bagimsizlik")
    lines.append("")
    for key in [
        "paper_lab_uses_all_enabled_filters",
        "paper_lab_uses_all_enabled_strategies",
        "paper_lab_result_pool_separate",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Sureklilik")
    lines.append("")
    for key in [
        "paper_lab_running_finally_reset",
        "paper_lab_state_isolated",
        "paper_lab_status_lifecycle_present",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Onceki Auditler")
    lines.append("")
    lines.append(f"- 40.20: `{report['prior_40_20_status']}`")
    lines.append(f"- 40.21: `{report['prior_40_21_status']}`")
    lines.append(f"- 40.22: `{report['prior_40_22_status']}`")
    lines.append(f"- 40.23: `{report['prior_40_23_status']}`")
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
        lines.append("Paper Lab autonomous research engine kontrolleri temiz.")
    else:
        lines.append("Paper Lab autonomous research engine blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT_OK",
        "blocker": "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"paper_lab_not_using_selected_filter_ids={str(report['paper_lab_not_using_selected_filter_ids']).lower()}")
    print(f"paper_lab_not_using_selected_strategy_ids={str(report['paper_lab_not_using_selected_strategy_ids']).lower()}")
    print(f"paper_lab_running_finally_reset={str(report['paper_lab_running_finally_reset']).lower()}")
    print(f"paper_lab_repeatable_runs_supported={str(report['paper_lab_repeatable_runs_supported']).lower()}")
    print(f"prior_40_23_status={report['prior_40_23_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
