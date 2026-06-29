#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTH_JS = ROOT / "frontend" / "js" / "app" / "auth.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
DASHBOARD_JS = ROOT / "frontend" / "js" / "pages" / "dashboard.js"
AUDIT_13 = ROOT / "docs" / "LEVEL1_40_13_RULE_SELECTION_PERSISTENCE_AUDIT.json"
AUDIT_14 = ROOT / "docs" / "LEVEL1_40_14_RULE_BACKEND_STABILITY_AUDIT.json"
AUDIT_15 = ROOT / "docs" / "LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_report() -> dict[str, Any]:
    auth_js = _load_text(AUTH_JS)
    api_js = _load_text(API_JS)
    rules_js = _load_text(RULES_JS)
    dashboard_js = _load_text(DASHBOARD_JS)
    audit_13 = _load_json(AUDIT_13)
    audit_14 = _load_json(AUDIT_14)
    audit_15 = _load_json(AUDIT_15)

    auth_typo_hmtststc_absent = "HMTSTSTC_APP" not in auth_js + api_js + rules_js + dashboard_js
    auth_logout_safe_app_guard_present = (
        "const app = window.HMTSTC_APP || null" in auth_js
        and "const state = app && app.state ? app.state : {}" in auth_js
        and "if (state.token && app && app.fetchJson)" in auth_js
        and "if (app && app.clearRestrictedData)" in auth_js
    )
    auth_logout_401_ignored_present = (
        "error.status !== 401" in auth_js
        and "Logout hatası (ignore)" in auth_js
        and "localStorage.removeItem(\"hmtstc_token\")" in auth_js
    )
    api_get_auth_headers_safe_app_guard_present = (
        "const app = window.HMTSTC_APP || {}" in api_js
        and "const state = app.state || {}" in api_js
        and "state.token || localStorage.getItem(\"hmtstc_token\")" in api_js
    )
    api_401_not_backend_offline = (
        "if (response.status === 401) return \"http_401\"" in api_js
        and "throw this.decorateApiError(authError, \"http_401\"" in api_js
        and "backend_api: \"online\"" in api_js
        and "auth_status: \"auth_expired\"" in api_js
    )
    api_401_preserve_rules_present = (
        "clearRestrictedData: function (options)" in api_js
        and "preserveRules" in api_js
        and "this.clearRestrictedData({ preserveRules: true })" in api_js
        and "expired_preserved" in api_js
    )
    api_handle_unauthorized_stops_sync_present = (
        "state.syncInProgress = false" in api_js
        and "state.heavySyncInProgress = false" in api_js
        and "state.apiReady = false" in api_js
        and "state.apiSyncReady = false" in api_js
        and "Oturum süresi doldu, tekrar giriş yap." in api_js
    )
    rules_401_preserve_last_good_present = (
        "error && error.status === 401" in rules_js
        and "son başarılı filtre/strateji listesi korunuyor" in rules_js
        and "this.state.dashboardRuleSelectionSaving = false" in rules_js
        and "Filtre/strateji listesi korunuyor" in rules_js
    )
    dashboard_auth_expired_status_present = (
        "system.auth_status === \"auth_expired\"" in dashboard_js
        and ("system.last_api_error_type === \"http_401\"" in dashboard_js or "lastApiErrorType === \"http_401\"" in dashboard_js)
        and "systemStatusItem(\"Oturum\"" in dashboard_js
        and "Süresi Doldu" in dashboard_js
    )

    blockers: list[str] = []
    for name, value in [
        ("auth_typo_hmtststc_absent", auth_typo_hmtststc_absent),
        ("auth_logout_safe_app_guard_present", auth_logout_safe_app_guard_present),
        ("api_get_auth_headers_safe_app_guard_present", api_get_auth_headers_safe_app_guard_present),
        ("api_401_not_backend_offline", api_401_not_backend_offline),
        ("api_401_preserve_rules_present", api_401_preserve_rules_present),
    ]:
        if not value:
            blockers.append(f"{name}=false")

    review_items: list[str] = []
    for name, value in [
        ("auth_logout_401_ignored_present", auth_logout_401_ignored_present),
        ("api_handle_unauthorized_stops_sync_present", api_handle_unauthorized_stops_sync_present),
        ("rules_401_preserve_last_good_present", rules_401_preserve_last_good_present),
        ("dashboard_auth_expired_status_present", dashboard_auth_expired_status_present),
    ]:
        if not value:
            review_items.append(f"{name}=false")

    for name, audit in [
        ("40.13", audit_13),
        ("40.14", audit_14),
        ("40.15", audit_15),
    ]:
        if audit.get("status") != "ok":
            blockers.append(f"{name} status is {audit.get('status')}")

    status = "blocker" if blockers else ("review" if review_items else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auth_typo_hmtststc_absent": auth_typo_hmtststc_absent,
        "auth_logout_safe_app_guard_present": auth_logout_safe_app_guard_present,
        "auth_logout_401_ignored_present": auth_logout_401_ignored_present,
        "api_get_auth_headers_safe_app_guard_present": api_get_auth_headers_safe_app_guard_present,
        "api_401_not_backend_offline": api_401_not_backend_offline,
        "api_401_preserve_rules_present": api_401_preserve_rules_present,
        "api_handle_unauthorized_stops_sync_present": api_handle_unauthorized_stops_sync_present,
        "rules_401_preserve_last_good_present": rules_401_preserve_last_good_present,
        "dashboard_auth_expired_status_present": dashboard_auth_expired_status_present,
        "rule_selection_persistence_status": audit_13.get("status"),
        "rule_backend_stability_status": audit_14.get("status"),
        "system_status_runtime_store_status": audit_15.get("status"),
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Keep 401/auth-expired separate from backend_offline in user-facing status.",
            "Preserve last successful rules payload when auth expires.",
            "Keep logout tolerant of /api/auth/logout returning 401.",
            "Run 40.16 after 40.13, 40.14 and 40.15 before Paket 11.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.16 Auth 401 State Guard Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- HMTSTSTC typo yok: `{_yn(report['auth_typo_hmtststc_absent'])}`")
    lines.append(f"- Logout safe app guard: `{_yn(report['auth_logout_safe_app_guard_present'])}`")
    lines.append(f"- 401 backend offline degil: `{_yn(report['api_401_not_backend_offline'])}`")
    lines.append(f"- 401 rules preserve: `{_yn(report['api_401_preserve_rules_present'])}`")
    lines.append("")
    lines.append("## Auth / Logout")
    lines.append("")
    lines.append(f"- Safe app guard: `{_yn(report['auth_logout_safe_app_guard_present'])}`")
    lines.append(f"- 401 ignored during logout: `{_yn(report['auth_logout_401_ignored_present'])}`")
    lines.append("")
    lines.append("## API 401 Guard")
    lines.append("")
    lines.append(f"- Safe auth header app guard: `{_yn(report['api_get_auth_headers_safe_app_guard_present'])}`")
    lines.append(f"- 401 not backend_offline: `{_yn(report['api_401_not_backend_offline'])}`")
    lines.append(f"- 401 preserve rules: `{_yn(report['api_401_preserve_rules_present'])}`")
    lines.append(f"- handleUnauthorized stops sync: `{_yn(report['api_handle_unauthorized_stops_sync_present'])}`")
    lines.append("")
    lines.append("## Frontend State")
    lines.append("")
    lines.append(f"- Rules 401 last-good preserve: `{_yn(report['rules_401_preserve_last_good_present'])}`")
    lines.append(f"- Dashboard auth expired status: `{_yn(report['dashboard_auth_expired_status_present'])}`")
    lines.append("")
    lines.append("## Prior Audits")
    lines.append("")
    lines.append(f"- 40.13: `{report['rule_selection_persistence_status']}`")
    lines.append(f"- 40.14: `{report['rule_backend_stability_status']}`")
    lines.append(f"- 40.15: `{report['system_status_runtime_store_status']}`")
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
        lines.append("Auth 401, logout ve frontend state guard kontrolleri temiz.")
    elif report["status"] == "review":
        lines.append("Auth 401 state guard icin manuel inceleme gerektiren statik bulgular var.")
    else:
        lines.append("Auth 401 state guard blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT_OK",
        "review": "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT_REVIEW",
        "blocker": "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"auth_typo_hmtststc_absent={str(report['auth_typo_hmtststc_absent']).lower()}")
    print(f"auth_logout_safe_app_guard_present={str(report['auth_logout_safe_app_guard_present']).lower()}")
    print(f"api_get_auth_headers_safe_app_guard_present={str(report['api_get_auth_headers_safe_app_guard_present']).lower()}")
    print(f"api_401_not_backend_offline={str(report['api_401_not_backend_offline']).lower()}")
    print(f"api_401_preserve_rules_present={str(report['api_401_preserve_rules_present']).lower()}")
    print(f"rules_401_preserve_last_good_present={str(report['rules_401_preserve_last_good_present']).lower()}")
    print(f"dashboard_auth_expired_status_present={str(report['dashboard_auth_expired_status_present']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
