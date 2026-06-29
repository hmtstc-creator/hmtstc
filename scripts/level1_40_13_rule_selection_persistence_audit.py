#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
FRONTEND_INVENTORY_PATH = ROOT / "docs" / "LEVEL1_40_07_FRONTEND_API_INVENTORY.json"
CONTRACT_DIFF_PATH = ROOT / "docs" / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
OWNER_CONTRACT_PATH = ROOT / "docs" / "LEVEL1_40_12_OWNER_APPROVAL_CONTRACT_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_policy(diff: dict[str, Any]) -> dict[str, list[Any]]:
    policy = diff.get("runtime_policy") if isinstance(diff.get("runtime_policy"), dict) else {}
    return {
        "runtime_leaks": diff.get("runtime_leaks") if isinstance(diff.get("runtime_leaks"), list) else [],
        "tracked_runtime_stores": policy.get("tracked_runtime_stores") if isinstance(policy.get("tracked_runtime_stores"), list) else [],
        "unignored_runtime_stores": policy.get("unignored_runtime_stores") if isinstance(policy.get("unignored_runtime_stores"), list) else [],
    }


def build_report(dashboard_js: str, rules_js: str, frontend: dict[str, Any], diff: dict[str, Any], owner: dict[str, Any]) -> dict[str, Any]:
    dashboard_explicit_selection_guard = (
        "function selectionState" in dashboard_js
        and "explicit: true" in dashboard_js
        and "explicit: false" in dashboard_js
        and "state.explicit" in dashboard_js
    )
    all_active_fallback_guarded = (
        "!selected.length" not in dashboard_js
        and "active_fallback" in dashboard_js
        and "item.enabled !== false && item.active !== false" in dashboard_js
    )
    selection_saving_state_present = "dashboardRuleSelectionSaving" in rules_js and "dashboardRuleSelectionSaving" in dashboard_js
    response_filter_selection_verified = "result.selected_filter_ids" in rules_js and "filterSelectionMatches" in rules_js and "sameIdSet(selectionSnapshot.filter" in rules_js
    response_strategy_selection_verified = "result.selected_strategy_ids" in rules_js and "strategySelectionMatches" in rules_js and "sameIdSet(selectionSnapshot.strategy" in rules_js
    draft_cleared_after_verified_success = "this.state.dashboardRuleSelectionDraft = null" in rules_js and "filterSelectionMatches" in rules_js and "strategySelectionMatches" in rules_js
    draft_preserved_on_error = "selectionSnapshot.filter.slice()" in rules_js and "selectionSnapshot.strategy.slice()" in rules_js and "Seçim ekranda korunuyor" in rules_js
    double_submit_guard_present = "if (this.state.dashboardRuleSelectionSaving)" in rules_js and "zaten devam ediyor" in rules_js
    activate_paper_lab_call_present = '"/api/rules/activate-paper-lab"' in rules_js or "'/api/rules/activate-paper-lab'" in rules_js

    runtime = _runtime_policy(diff)
    contract_missing_path_count = int(diff.get("missing_path_count") or 0)
    contract_method_mismatch_count = int(diff.get("method_mismatch_count") or 0)
    owner_status = str(owner.get("status") or "unknown")
    runtime_leak_count = len(runtime["runtime_leaks"])
    tracked_runtime_store_count = len(runtime["tracked_runtime_stores"])
    unignored_runtime_store_count = len(runtime["unignored_runtime_stores"])

    blockers: list[str] = []
    if not activate_paper_lab_call_present:
        blockers.append("activate-paper-lab frontend call is missing")
    if contract_missing_path_count:
        blockers.append(f"Contract diff has missing_path_count={contract_missing_path_count}")
    if contract_method_mismatch_count:
        blockers.append(f"Contract diff has method_mismatch_count={contract_method_mismatch_count}")
    if owner_status != "ok":
        blockers.append(f"40.12 owner approval contract status is {owner_status}")
    if runtime_leak_count:
        blockers.append(f"Runtime leak count is {runtime_leak_count}")
    if tracked_runtime_store_count:
        blockers.append(f"Tracked runtime store count is {tracked_runtime_store_count}")
    if unignored_runtime_store_count:
        blockers.append(f"Unignored runtime store count is {unignored_runtime_store_count}")
    if not response_filter_selection_verified:
        blockers.append("Backend response selected_filter_ids verification is missing")
    if not response_strategy_selection_verified:
        blockers.append("Backend response selected_strategy_ids verification is missing")
    if not draft_preserved_on_error:
        blockers.append("Dashboard rule selection draft is not clearly preserved on error")

    review_items: list[str] = []
    if not dashboard_explicit_selection_guard:
        review_items.append("Dashboard explicit selection guard not detected")
    if not all_active_fallback_guarded:
        review_items.append("All-active fallback is not clearly guarded")
    if not selection_saving_state_present:
        review_items.append("Saving state not detected")
    if not double_submit_guard_present:
        review_items.append("Double submit guard not detected")
    if not draft_cleared_after_verified_success:
        review_items.append("Draft clear after verified success not detected")

    status = "blocker" if blockers else ("review" if review_items else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dashboard_js": str(DASHBOARD_JS.relative_to(ROOT)),
        "source_rules_js": str(RULES_JS.relative_to(ROOT)),
        "source_frontend_inventory": str(FRONTEND_INVENTORY_PATH.relative_to(ROOT)),
        "source_contract_diff": str(CONTRACT_DIFF_PATH.relative_to(ROOT)),
        "source_owner_approval_contract": str(OWNER_CONTRACT_PATH.relative_to(ROOT)),
        "frontend_call_count": int(frontend.get("call_count") or 0),
        "dashboard_explicit_selection_guard": dashboard_explicit_selection_guard,
        "all_active_fallback_guarded": all_active_fallback_guarded,
        "selection_saving_state_present": selection_saving_state_present,
        "response_filter_selection_verified": response_filter_selection_verified,
        "response_strategy_selection_verified": response_strategy_selection_verified,
        "draft_cleared_after_verified_success": draft_cleared_after_verified_success,
        "draft_preserved_on_error": draft_preserved_on_error,
        "double_submit_guard_present": double_submit_guard_present,
        "activate_paper_lab_call_present": activate_paper_lab_call_present,
        "contract_missing_path_count": contract_missing_path_count,
        "contract_method_mismatch_count": contract_method_mismatch_count,
        "owner_approval_contract_status": owner_status,
        "runtime_leak_count": runtime_leak_count,
        "tracked_runtime_store_count": tracked_runtime_store_count,
        "unignored_runtime_store_count": unignored_runtime_store_count,
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Run this audit after 40.12 before changing Dashboard rule selection behavior.",
            "Keep backend response selection mismatch visible to the user and preserve the draft.",
            "Do not clear dashboardRuleSelectionDraft before selected_filter_ids and selected_strategy_ids are verified.",
            "Keep live-trade, Binance, order executor, Futures and strategy/filter decision logic out of this package.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.13 Rule Selection Persistence Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Frontend API call count: `{report['frontend_call_count']}`")
    lines.append(f"- Dashboard explicit selection guard: `{_yn(report['dashboard_explicit_selection_guard'])}`")
    lines.append(f"- Response filter verified: `{_yn(report['response_filter_selection_verified'])}`")
    lines.append(f"- Response strategy verified: `{_yn(report['response_strategy_selection_verified'])}`")
    lines.append(f"- Draft preserved on error: `{_yn(report['draft_preserved_on_error'])}`")
    lines.append("")
    lines.append("## Dashboard Selection Guard")
    lines.append("")
    lines.append(f"- Explicit selection modeli: `{_yn(report['dashboard_explicit_selection_guard'])}`")
    lines.append(f"- All-active fallback guard: `{_yn(report['all_active_fallback_guarded'])}`")
    lines.append("")
    lines.append("## Paper Lab Save Guard")
    lines.append("")
    lines.append(f"- Saving state: `{_yn(report['selection_saving_state_present'])}`")
    lines.append(f"- Double submit guard: `{_yn(report['double_submit_guard_present'])}`")
    lines.append(f"- Backend filter secimi dogrulama: `{_yn(report['response_filter_selection_verified'])}`")
    lines.append(f"- Backend strategy secimi dogrulama: `{_yn(report['response_strategy_selection_verified'])}`")
    lines.append(f"- Dogrulanmis basaridan sonra draft temizleme: `{_yn(report['draft_cleared_after_verified_success'])}`")
    lines.append(f"- Hata durumunda draft koruma: `{_yn(report['draft_preserved_on_error'])}`")
    lines.append("")
    lines.append("## Backend / Contract Guard")
    lines.append("")
    lines.append(f"- Missing path: `{report['contract_missing_path_count']}`")
    lines.append(f"- Method mismatch: `{report['contract_method_mismatch_count']}`")
    lines.append(f"- 40.12 owner approval contract: `{report['owner_approval_contract_status']}`")
    lines.append(f"- Runtime leak: `{report['runtime_leak_count']}`")
    lines.append(f"- Tracked runtime store: `{report['tracked_runtime_store_count']}`")
    lines.append(f"- Unignored runtime store: `{report['unignored_runtime_store_count']}`")
    lines.append("")
    lines.append("## Blocker / Review Listesi")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- BLOCKER: {blocker}")
    if report["review_items"]:
        for item in report["review_items"]:
            lines.append(f"- REVIEW: {item}")
    if not report["blockers"] and not report["review_items"]:
        lines.append("Blocker veya review item yok.")
    lines.append("")
    lines.append("## Sonuc")
    lines.append("")
    if report["status"] == "ok":
        lines.append("Dashboard rule selection persistence guard ve Paper Lab save dogrulamasi temiz.")
    elif report["status"] == "review":
        lines.append("Rule selection persistence icin manuel inceleme gerektiren statik bulgular var.")
    else:
        lines.append("Rule selection persistence veya contract guard blocker durumunda.")
    lines.append("")
    lines.append("## Paket 9 Icin Onerilen Devam")
    lines.append("")
    for action in report["recommended_next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        dashboard_js = _load_text(DASHBOARD_JS)
        rules_js = _load_text(RULES_JS)
        frontend = _load_json(FRONTEND_INVENTORY_PATH)
        diff = _load_json(CONTRACT_DIFF_PATH)
        owner = _load_json(OWNER_CONTRACT_PATH)
        report = build_report(dashboard_js, rules_js, frontend, diff, owner)
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT_OK",
        "review": "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT_REVIEW",
        "blocker": "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"dashboard_explicit_selection_guard={str(report['dashboard_explicit_selection_guard']).lower()}")
    print(f"response_filter_selection_verified={str(report['response_filter_selection_verified']).lower()}")
    print(f"response_strategy_selection_verified={str(report['response_strategy_selection_verified']).lower()}")
    print(f"draft_preserved_on_error={str(report['draft_preserved_on_error']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
