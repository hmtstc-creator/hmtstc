#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE_AUTH = ROOT / "backend" / "core" / "auth.py"
AUTH_ROUTES = ROOT / "backend" / "routes" / "auth_routes.py"
AUTH_JS = ROOT / "frontend" / "js" / "app" / "auth.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
AUDIT_16 = ROOT / "docs" / "LEVEL1_40_16_AUTH_401_STATE_GUARD_AUDIT.json"
AUDIT_17 = ROOT / "docs" / "LEVEL1_40_17_PAPER_LAB_STATE_TRUTH_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT.md"


def _load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_report() -> dict[str, Any]:
    core_auth = _load_text(CORE_AUTH)
    auth_routes = _load_text(AUTH_ROUTES)
    auth_js = _load_text(AUTH_JS)
    api_js = _load_text(API_JS)
    audit_16 = _load_json(AUDIT_16)
    audit_17 = _load_json(AUDIT_17)

    backend_auth_surface = core_auth + "\n" + auth_routes
    auth_store_static_tmp_absent = "auth_store.json.tmp" not in backend_auth_surface and 'AUTH_FILE.suffix + ".tmp"' not in core_auth
    auth_store_unique_tmp_present = (
        "uuid.uuid4().hex" in core_auth
        and "threading.get_ident()" in core_auth
        and "os.getpid()" in core_auth
        and "AUTH_FILE.with_name" in core_auth
    )
    auth_store_lock_present = (
        "_AUTH_STORE_LOCK = threading.RLock()" in core_auth
        and "def auth_store_lock" in core_auth
        and "with _AUTH_STORE_LOCK" in core_auth
        and "with auth_store_lock()" in auth_routes
    )
    auth_store_atomic_replace_present = "os.replace(temp_file, AUTH_FILE)" in core_auth
    auth_store_write_error_handled = (
        "class AuthStoreWriteError" in core_auth
        and "raise AuthStoreWriteError" in core_auth
        and "except AuthStoreWriteError" in auth_routes
        and '"status": "auth_store_error"' in auth_routes
        and "status_code=503" in auth_routes
    )
    frontend_login_double_submit_guard_present = (
        "loginInProgress" in auth_js
        and "if (HMTSTC_APP.state.loginInProgress)" in auth_js
        and "HMTSTC_APP.state.loginInProgress = true" in auth_js
        and "HMTSTC_APP.state.loginInProgress = false" in auth_js
    )
    frontend_login_button_disabled_present = (
        "const loginInProgress = Boolean(HMTSTC_APP.state.loginInProgress)" in auth_js
        and "disabled" in auth_js
        and "Giriş yapılıyor..." in auth_js
        and "!HMTSTC_APP.state.loginInProgress" in auth_js
    )
    frontend_login_500_clears_token_present = (
        "response.status >= 500" in auth_js
        and "localStorage.removeItem(\"hmtstc_token\")" in auth_js
        and "token: null" in auth_js
    )
    api_401_403_not_backend_offline = (
        'type === "http_401"' in api_js
        and 'type === "http_403"' in api_js
        and "backend_offline" in api_js
        and "backendApiStatus" in api_js
    )
    api_login_in_progress_blocks_sync = "HMTSTC_APP.state.loginInProgress" in api_js and "syncApiData" in api_js

    blockers: list[str] = []
    for name, value in [
        ("auth_store_static_tmp_absent", auth_store_static_tmp_absent),
        ("auth_store_unique_tmp_present", auth_store_unique_tmp_present),
        ("auth_store_lock_present", auth_store_lock_present),
        ("auth_store_atomic_replace_present", auth_store_atomic_replace_present),
        ("auth_store_write_error_handled", auth_store_write_error_handled),
        ("frontend_login_double_submit_guard_present", frontend_login_double_submit_guard_present),
        ("frontend_login_button_disabled_present", frontend_login_button_disabled_present),
        ("api_401_403_not_backend_offline", api_401_403_not_backend_offline),
    ]:
        if not value:
            blockers.append(f"{name}=false")

    review_items: list[str] = []
    for name, value in [
        ("frontend_login_500_clears_token_present", frontend_login_500_clears_token_present),
        ("api_login_in_progress_blocks_sync", api_login_in_progress_blocks_sync),
    ]:
        if not value:
            review_items.append(f"{name}=false")

    prior_40_16_status = audit_16.get("status")
    prior_40_17_status = audit_17.get("status")
    if prior_40_16_status != "ok":
        blockers.append(f"40.16 status is {prior_40_16_status}")
    if prior_40_17_status != "ok":
        blockers.append(f"40.17 status is {prior_40_17_status}")

    status = "blocker" if blockers else ("review" if review_items else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auth_store_static_tmp_absent": auth_store_static_tmp_absent,
        "auth_store_unique_tmp_present": auth_store_unique_tmp_present,
        "auth_store_lock_present": auth_store_lock_present,
        "auth_store_atomic_replace_present": auth_store_atomic_replace_present,
        "auth_store_write_error_handled": auth_store_write_error_handled,
        "frontend_login_double_submit_guard_present": frontend_login_double_submit_guard_present,
        "frontend_login_button_disabled_present": frontend_login_button_disabled_present,
        "frontend_login_500_clears_token_present": frontend_login_500_clears_token_present,
        "api_401_403_not_backend_offline": api_401_403_not_backend_offline,
        "api_login_in_progress_blocks_sync": api_login_in_progress_blocks_sync,
        "prior_40_16_status": prior_40_16_status,
        "prior_40_17_status": prior_40_17_status,
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Keep auth_store writes on unique tmp files under RLock.",
            "Keep login double-submit guard active until sync completes.",
            "Do not stage runtime auth_store or tmp files.",
            "Run 40.18 before Paket 11.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.18 Auth Store Atomic Write Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Static tmp absent: `{_yn(report['auth_store_static_tmp_absent'])}`")
    lines.append(f"- Unique tmp present: `{_yn(report['auth_store_unique_tmp_present'])}`")
    lines.append(f"- Lock present: `{_yn(report['auth_store_lock_present'])}`")
    lines.append(f"- Atomic replace: `{_yn(report['auth_store_atomic_replace_present'])}`")
    lines.append("")
    lines.append("## Backend Auth Store")
    lines.append("")
    lines.append(f"- Write error handled: `{_yn(report['auth_store_write_error_handled'])}`")
    lines.append(f"- Prior 40.16: `{report['prior_40_16_status']}`")
    lines.append(f"- Prior 40.17: `{report['prior_40_17_status']}`")
    lines.append("")
    lines.append("## Frontend Login")
    lines.append("")
    lines.append(f"- Double submit guard: `{_yn(report['frontend_login_double_submit_guard_present'])}`")
    lines.append(f"- Button disabled/loading: `{_yn(report['frontend_login_button_disabled_present'])}`")
    lines.append(f"- Login 500 clears token: `{_yn(report['frontend_login_500_clears_token_present'])}`")
    lines.append(f"- Login in progress blocks sync: `{_yn(report['api_login_in_progress_blocks_sync'])}`")
    lines.append(f"- 401/403 not backend offline: `{_yn(report['api_401_403_not_backend_offline'])}`")
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
        lines.append("Auth store atomic write ve login double-submit guard kontrolleri temiz.")
    elif report["status"] == "review":
        lines.append("Auth store atomic write icin manuel inceleme gerektiren statik bulgular var.")
    else:
        lines.append("Auth store atomic write blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT_OK",
        "review": "LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT_REVIEW",
        "blocker": "LEVEL1_40_18_AUTH_STORE_ATOMIC_WRITE_AUDIT_BLOCKER",
    }[report["status"]]
    print(marker)
    print(f"status={report['status']}")
    print(f"auth_store_static_tmp_absent={str(report['auth_store_static_tmp_absent']).lower()}")
    print(f"auth_store_unique_tmp_present={str(report['auth_store_unique_tmp_present']).lower()}")
    print(f"auth_store_lock_present={str(report['auth_store_lock_present']).lower()}")
    print(f"auth_store_atomic_replace_present={str(report['auth_store_atomic_replace_present']).lower()}")
    print(f"auth_store_write_error_handled={str(report['auth_store_write_error_handled']).lower()}")
    print(f"frontend_login_double_submit_guard_present={str(report['frontend_login_double_submit_guard_present']).lower()}")
    print(f"frontend_login_button_disabled_present={str(report['frontend_login_button_disabled_present']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
