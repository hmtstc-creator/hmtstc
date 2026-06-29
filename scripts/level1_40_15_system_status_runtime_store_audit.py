#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
BOT_JS = ROOT / "frontend" / "js" / "app" / "bot.js"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
RULE_ENGINE = ROOT / "backend" / "services" / "rule_engine.py"
DASHBOARD_ROUTES = ROOT / "backend" / "routes" / "dashboard_routes.py"
RULE_STORE = ROOT / "backend" / "rule_store.json"
RUNTIME_BACKUPS = ROOT / "backend" / "runtime_backups"
CONTRACT_DIFF = ROOT / "docs" / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
RULE_SELECTION_AUDIT = ROOT / "docs" / "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.json"
RULE_BACKEND_AUDIT = ROOT / "docs" / "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT.md"

RUNTIME_STORE_BLOCKLIST = {
    "backend/binance_credentials_store.json",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/rule_store.json",
}


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_policy(diff: dict[str, Any]) -> dict[str, list[Any]]:
    policy = diff.get("runtime_policy") if isinstance(diff.get("runtime_policy"), dict) else {}
    return {
        "runtime_leaks": diff.get("runtime_leaks") if isinstance(diff.get("runtime_leaks"), list) else [],
        "tracked_runtime_stores": policy.get("tracked_runtime_stores") if isinstance(policy.get("tracked_runtime_stores"), list) else [],
        "unignored_runtime_stores": policy.get("unignored_runtime_stores") if isinstance(policy.get("unignored_runtime_stores"), list) else [],
    }


def _count_rules(payload: Any) -> dict[str, int]:
    users = payload.get("users") if isinstance(payload, dict) else {}
    total = 0
    filters = 0
    strategies = 0
    if isinstance(users, dict):
        for state in users.values():
            rules = state.get("rules") if isinstance(state, dict) else []
            if not isinstance(rules, list):
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                total += 1
                if rule.get("type") == "filter":
                    filters += 1
                elif rule.get("type") == "strategy":
                    strategies += 1
    return {"total": total, "filters": filters, "strategies": strategies}


def _active_rule_store_counts() -> dict[str, int]:
    return _count_rules(_load_json(RULE_STORE, {"version": 1, "users": {}}))


def _backup_rule_store_counts() -> dict[str, Any]:
    best = {"path": None, "total": 0, "filters": 0, "strategies": 0}
    if not RUNTIME_BACKUPS.exists():
        return best
    for path in RUNTIME_BACKUPS.rglob("*.json"):
        if "rule_store" not in path.name:
            continue
        try:
            counts = _count_rules(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if counts["total"] > best["total"]:
            best = {
                "path": str(path.relative_to(ROOT)),
                "total": counts["total"],
                "filters": counts["filters"],
                "strategies": counts["strategies"],
            }
    return best


def _git_tracked_files() -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return set()
    if result.returncode != 0:
        return set()
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def build_report() -> dict[str, Any]:
    dashboard_js = _load_text(DASHBOARD_JS)
    api_js = _load_text(API_JS)
    bot_js = _load_text(BOT_JS)
    rules_js = _load_text(RULES_JS)
    rule_engine = _load_text(RULE_ENGINE)
    dashboard_routes = _load_text(DASHBOARD_ROUTES)
    diff = _load_json(CONTRACT_DIFF)
    rule_selection = _load_json(RULE_SELECTION_AUDIT)
    rule_backend = _load_json(RULE_BACKEND_AUDIT)
    runtime = _runtime_policy(diff)
    active_counts = _active_rule_store_counts()
    backup_counts = _backup_rule_store_counts()
    tracked = _git_tracked_files()
    tracked_runtime_stores = sorted(RUNTIME_STORE_BLOCKLIST.intersection(tracked))

    dashboard_status_panel_present = "dashboard-system-status-strip" in dashboard_js and "Backend API" in dashboard_js and "Karabasan" in dashboard_js
    backend_api_status_endpoint_present = '"/dashboard/bundle"' in dashboard_routes and "botStatus" in dashboard_routes and "rules" in dashboard_routes
    bot_status_frontend_read_present = '"/api/bot/status"' in bot_js or '"/api/bot/status"' in api_js
    bot_start_status_refresh_present = '"/api/bot/status"' in bot_js and "afterStatus" in bot_js and "bot_running" in bot_js
    karabasan_status_dashboard_present = "Karabasan" in dashboard_js and "karabasanScore" in dashboard_js
    paper_lab_auto_sync_call_present = '"/api/rules/auto-paper-lab"' in rules_js and "paperLabStatus" in rules_js
    api_error_classifier_present = "classifyApiError" in api_js and "backend_offline" in api_js and "invalid_json" in api_js
    rule_store_status_backend_present = "build_rule_store_status" in rule_engine and "rule_store_status" in rule_engine
    rule_store_status_dashboard_present = "rule_store_status" in dashboard_js and "Rule Store" in dashboard_js
    dashboard_rule_selection_reload_persistence_present = (
        "selectionState(dashboardRuleDraft.filter, rules.selected_filter_ids, filters)" in dashboard_js
        and "selectionState(dashboardRuleDraft.strategy, rules.selected_strategy_ids, strategies)" in dashboard_js
        and 'source: "backend"' in dashboard_js
    )
    dashboard_no_fallback_all_on_explicit_backend_selection = (
        "if (Array.isArray(backendIds))" in dashboard_js
        and "explicit: true" in dashboard_js
        and 'source: "backend"' in dashboard_js
        and 'source: "active_fallback"' in dashboard_js
        and "const checked = state.explicit" in dashboard_js
        and "selectedIds.indexOf(id) !== -1" in dashboard_js
        and "item.enabled !== false && item.active !== false" in dashboard_js
    )
    dashboard_selected_filter_ids_render_present = (
        "const selectedFilters = selectionState(dashboardRuleDraft.filter, rules.selected_filter_ids, filters)" in dashboard_js
        and 'checkList("Filtre", filters, selectedFilters, "data-rule-filter-select")' in dashboard_js
    )
    dashboard_selected_strategy_ids_render_present = (
        "const selectedStrategies = selectionState(dashboardRuleDraft.strategy, rules.selected_strategy_ids, strategies)" in dashboard_js
        and 'checkList("Strateji", strategies, selectedStrategies, "data-rule-strategy-select")' in dashboard_js
    )
    empty_active_backup_blocker = active_counts["total"] == 0 and backup_counts["total"] > 0

    contract_missing_path_count = int(diff.get("missing_path_count") or 0)
    contract_method_mismatch_count = int(diff.get("method_mismatch_count") or 0)
    runtime_leak_count = len(runtime["runtime_leaks"])
    unignored_runtime_store_count = len(runtime["unignored_runtime_stores"])

    blockers: list[str] = []
    for name, value in [
        ("dashboard_rule_selection_reload_persistence_present", dashboard_rule_selection_reload_persistence_present),
        ("dashboard_no_fallback_all_on_explicit_backend_selection", dashboard_no_fallback_all_on_explicit_backend_selection),
        ("dashboard_selected_filter_ids_render_present", dashboard_selected_filter_ids_render_present),
        ("dashboard_selected_strategy_ids_render_present", dashboard_selected_strategy_ids_render_present),
    ]:
        if not value:
            blockers.append(f"{name}=false")
    if empty_active_backup_blocker:
        blockers.append("Active rule_store has 0 rules while runtime backup has rules")
    if rule_selection.get("status") != "ok":
        blockers.append(f"40.13 status is {rule_selection.get('status')}")
    if rule_backend.get("status") != "ok":
        blockers.append(f"40.14 status is {rule_backend.get('status')}")
    if contract_missing_path_count:
        blockers.append(f"Contract diff missing_path_count={contract_missing_path_count}")
    if contract_method_mismatch_count:
        blockers.append(f"Contract diff method_mismatch_count={contract_method_mismatch_count}")
    if runtime_leak_count:
        blockers.append(f"Runtime leak count={runtime_leak_count}")
    if tracked_runtime_stores:
        blockers.append("Runtime store tracked by git: " + ", ".join(tracked_runtime_stores))
    if unignored_runtime_store_count:
        blockers.append(f"Unignored runtime store count={unignored_runtime_store_count}")

    review_items: list[str] = []
    for name, value in [
        ("dashboard_status_panel_present", dashboard_status_panel_present),
        ("backend_api_status_endpoint_present", backend_api_status_endpoint_present),
        ("bot_status_frontend_read_present", bot_status_frontend_read_present),
        ("bot_start_status_refresh_present", bot_start_status_refresh_present),
        ("karabasan_status_dashboard_present", karabasan_status_dashboard_present),
        ("paper_lab_auto_sync_call_present", paper_lab_auto_sync_call_present),
        ("api_error_classifier_present", api_error_classifier_present),
        ("rule_store_status_backend_present", rule_store_status_backend_present),
        ("rule_store_status_dashboard_present", rule_store_status_dashboard_present),
    ]:
        if not value:
            review_items.append(f"{name}=false")

    status = "blocker" if blockers else ("review" if review_items else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dashboard_status_panel_present": dashboard_status_panel_present,
        "backend_api_status_endpoint_present": backend_api_status_endpoint_present,
        "bot_status_frontend_read_present": bot_status_frontend_read_present,
        "bot_start_status_refresh_present": bot_start_status_refresh_present,
        "karabasan_status_dashboard_present": karabasan_status_dashboard_present,
        "paper_lab_auto_sync_call_present": paper_lab_auto_sync_call_present,
        "api_error_classifier_present": api_error_classifier_present,
        "rule_store_status_backend_present": rule_store_status_backend_present,
        "rule_store_status_dashboard_present": rule_store_status_dashboard_present,
        "dashboard_rule_selection_reload_persistence_present": dashboard_rule_selection_reload_persistence_present,
        "dashboard_no_fallback_all_on_explicit_backend_selection": dashboard_no_fallback_all_on_explicit_backend_selection,
        "dashboard_selected_filter_ids_render_present": dashboard_selected_filter_ids_render_present,
        "dashboard_selected_strategy_ids_render_present": dashboard_selected_strategy_ids_render_present,
        "active_rule_store_total_rules": active_counts["total"],
        "active_rule_store_filter_count": active_counts["filters"],
        "active_rule_store_strategy_count": active_counts["strategies"],
        "backup_max_rule_count": backup_counts["total"],
        "backup_max_filter_count": backup_counts["filters"],
        "backup_max_strategy_count": backup_counts["strategies"],
        "backup_candidate": backup_counts["path"],
        "empty_active_backup_blocker": empty_active_backup_blocker,
        "rule_selection_persistence_status": rule_selection.get("status"),
        "rule_backend_stability_status": rule_backend.get("status"),
        "contract_missing_path_count": contract_missing_path_count,
        "contract_method_mismatch_count": contract_method_mismatch_count,
        "runtime_leak_count": runtime_leak_count,
        "tracked_runtime_store_count": len(tracked_runtime_stores),
        "tracked_runtime_stores": tracked_runtime_stores,
        "unignored_runtime_store_count": unignored_runtime_store_count,
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Keep system status visible on Dashboard before adding new trading behavior.",
            "Do not auto-restore rule_store; require manual owner approval using the restore runbook.",
            "Keep bot active UI sourced from /api/bot/status after start commands.",
            "Keep API error classification in the shared fetchJson client.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.15 System Status Runtime Store Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Dashboard status panel: `{_yn(report['dashboard_status_panel_present'])}`")
    lines.append(f"- API error classifier: `{_yn(report['api_error_classifier_present'])}`")
    lines.append(f"- Bot start status refresh: `{_yn(report['bot_start_status_refresh_present'])}`")
    lines.append(f"- Dashboard rule reload persistence: `{_yn(report['dashboard_rule_selection_reload_persistence_present'])}`")
    lines.append(f"- Rule store: `{report['active_rule_store_filter_count']}` filtre / `{report['active_rule_store_strategy_count']}` strateji")
    lines.append("")
    lines.append("## System Status")
    lines.append("")
    lines.append(f"- Backend API status source: `{_yn(report['backend_api_status_endpoint_present'])}`")
    lines.append(f"- Bot status frontend read: `{_yn(report['bot_status_frontend_read_present'])}`")
    lines.append(f"- Karabasan dashboard status: `{_yn(report['karabasan_status_dashboard_present'])}`")
    lines.append(f"- Paper Lab auto sync status: `{_yn(report['paper_lab_auto_sync_call_present'])}`")
    lines.append("")
    lines.append("## Dashboard Rule Selection Persistence")
    lines.append("")
    lines.append(f"- Reload persistence source: `{_yn(report['dashboard_rule_selection_reload_persistence_present'])}`")
    lines.append(f"- Explicit backend selection fallback guard: `{_yn(report['dashboard_no_fallback_all_on_explicit_backend_selection'])}`")
    lines.append(f"- Filter selected ids render: `{_yn(report['dashboard_selected_filter_ids_render_present'])}`")
    lines.append(f"- Strategy selected ids render: `{_yn(report['dashboard_selected_strategy_ids_render_present'])}`")
    lines.append("")
    lines.append("## Rule Store")
    lines.append("")
    lines.append(f"- Aktif toplam rule: `{report['active_rule_store_total_rules']}`")
    lines.append(f"- Aktif filtre: `{report['active_rule_store_filter_count']}`")
    lines.append(f"- Aktif strateji: `{report['active_rule_store_strategy_count']}`")
    lines.append(f"- En yuksek backup rule: `{report['backup_max_rule_count']}`")
    lines.append(f"- Backup candidate: `{report['backup_candidate'] or '-'}`")
    lines.append(f"- Aktif bos / backup dolu blocker: `{_yn(report['empty_active_backup_blocker'])}`")
    lines.append("")
    lines.append("## Contract / Runtime")
    lines.append("")
    lines.append(f"- 40.13 status: `{report['rule_selection_persistence_status']}`")
    lines.append(f"- 40.14 status: `{report['rule_backend_stability_status']}`")
    lines.append(f"- Missing path: `{report['contract_missing_path_count']}`")
    lines.append(f"- Method mismatch: `{report['contract_method_mismatch_count']}`")
    lines.append(f"- Runtime leak: `{report['runtime_leak_count']}`")
    lines.append(f"- Tracked runtime store: `{report['tracked_runtime_store_count']}`")
    lines.append(f"- Unignored runtime store: `{report['unignored_runtime_store_count']}`")
    lines.append("")
    lines.append("## Blocker / Review")
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
        lines.append("System status, API error classifier ve runtime store gorunurluk kontrolleri temiz.")
    elif report["status"] == "review":
        lines.append("System status gorunurlugu icin manuel inceleme gerektiren statik bulgular var.")
    else:
        lines.append("Runtime store veya contract guard blocker durumunda.")
    lines.append("")
    lines.append("## Paket 11 Icin Onerilen Devam")
    lines.append("")
    for action in report["recommended_next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT_OK",
        "review": "LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT_REVIEW",
        "blocker": "LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"dashboard_status_panel_present={str(report['dashboard_status_panel_present']).lower()}")
    print(f"api_error_classifier_present={str(report['api_error_classifier_present']).lower()}")
    print(f"dashboard_rule_selection_reload_persistence_present={str(report['dashboard_rule_selection_reload_persistence_present']).lower()}")
    print(f"dashboard_no_fallback_all_on_explicit_backend_selection={str(report['dashboard_no_fallback_all_on_explicit_backend_selection']).lower()}")
    print(f"dashboard_selected_filter_ids_render_present={str(report['dashboard_selected_filter_ids_render_present']).lower()}")
    print(f"dashboard_selected_strategy_ids_render_present={str(report['dashboard_selected_strategy_ids_render_present']).lower()}")
    print(f"active_rule_store_total_rules={report['active_rule_store_total_rules']}")
    print(f"backup_max_rule_count={report['backup_max_rule_count']}")
    print(f"empty_active_backup_blocker={str(report['empty_active_backup_blocker']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
