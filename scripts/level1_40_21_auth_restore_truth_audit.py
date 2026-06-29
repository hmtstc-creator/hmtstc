#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_JS = ROOT / "frontend" / "js" / "app" / "state.js"
INIT_JS = ROOT / "frontend" / "js" / "app" / "init.js"
AUTH_JS = ROOT / "frontend" / "js" / "app" / "auth.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.md"


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
    init_js = _load_text(INIT_JS)
    auth_js = _load_text(AUTH_JS)
    api_js = _load_text(API_JS)
    audit_20 = _load_json(AUDIT_20)

    restore_fn = _section(auth_js, "restoreAuth: async function", "login: async function")
    login_fn = _section(auth_js, "login: async function", "changeOwnPassword: async function")
    logout_fn = _section(auth_js, "logout: async function", "renderPasswordChange: function")
    sync_fn = _section(api_js, "syncApiData: async function", "syncHeavyApiData: async function")
    heavy_fn = _section(api_js, "syncHeavyApiData: async function", "\n  }\n};")

    state_auth_not_localstorage_truth = (
        "auth: false" in state_js
        and "auth: Boolean(localStorage.getItem(\"hmtstc_token\"))" not in state_js
    )
    state_auth_restore_fields_present = _contains_all(state_js, [
        "authRestorePending",
        "authRestoreChecked",
        "authRestoreError",
        "authDiagnostics",
        "tokenExists",
        "lastBlockReason",
        "token: localStorage.getItem(\"hmtstc_token\") || null",
    ])
    init_restore_gate_present = _contains_all(init_js, [
        "HMTSTC_APP.restoreAuth()",
        "authRestorePending",
        "setInterval(function",
        "30000",
        "HMTSTC_APP.isUserEditing()",
        "HMTSTC_APP.state.syncInProgress",
    ]) and "if (HMTSTC_APP.state.auth) {\n      HMTSTC_APP.syncApiData();" not in init_js
    restore_auth_function_present = _contains_all(restore_fn, [
        "restoreAuth: async function",
        "localStorage.getItem(\"hmtstc_token\")",
        '"/api/auth/me"',
        'requestKind: "auth_restore"',
        "preventGlobalAbort: true",
        "timeoutMs: 10000",
        "skipHeavySync: true",
    ])
    restore_auth_401_clears_token = _contains_all(restore_fn, [
        'type === "http_401"',
        'type === "http_403"',
        "localStorage.removeItem(\"hmtstc_token\")",
        "Oturum süresi doldu, tekrar giriş yap.",
        "auth_401",
    ])
    restore_auth_network_keeps_token = _contains_all(restore_fn, [
        "auth_restore_network_error",
        "HMTSTC_APP.state.token = token",
        "tokenExists: true",
    ])
    login_success_sets_restore_truth = _contains_all(login_fn, [
        "if (!result.authenticated || !result.token)",
        "localStorage.setItem(\"hmtstc_token\", result.token)",
        "HMTSTC_APP.state.token = result.token",
        "HMTSTC_APP.state.auth = true",
        "HMTSTC_APP.state.authRestorePending = false",
        "HMTSTC_APP.state.authRestoreChecked = true",
        "skipHeavySync: true",
    ])
    logout_clears_restore_truth = _contains_all(logout_fn, [
        "localStorage.removeItem(\"hmtstc_token\")",
        "app.state.auth = false",
        "app.state.token = null",
        "app.state.user = null",
        "app.state.authRestorePending = false",
        "app.state.authRestoreChecked = true",
        "no_token",
    ])
    api_sync_auth_restore_guard_present = _contains_all(sync_fn, [
        "authRestorePending",
        "auth_restore_pending",
        "lastSyncBlockReason",
        "no_token",
        "auth_not_verified",
    ])
    api_auth_restore_request_kind_present = _contains_all(api_js, [
        'AUTH_RESTORE: "auth_restore"',
        "isAuthRestore",
        "requestKind === \"auth_restore\"",
    ])
    heavy_10_5_guards_preserved = _contains_all(heavy_fn, [
        "heavySyncAllowedAtMs",
        "nowMs + 120000",
        "300000",
        "heavySyncInProgress",
    ])
    token_value_not_logged = (
        "console.log(token" not in auth_js
        and "console.warn(token" not in auth_js
        and "console.error(token" not in auth_js
        and "pushOperationLine(token" not in auth_js
    )
    prior_40_20_status = audit_20.get("status")

    checks = {
        "state_auth_not_localstorage_truth": state_auth_not_localstorage_truth,
        "state_auth_restore_fields_present": state_auth_restore_fields_present,
        "init_restore_gate_present": init_restore_gate_present,
        "restore_auth_function_present": restore_auth_function_present,
        "restore_auth_401_clears_token": restore_auth_401_clears_token,
        "restore_auth_network_keeps_token": restore_auth_network_keeps_token,
        "login_success_sets_restore_truth": login_success_sets_restore_truth,
        "logout_clears_restore_truth": logout_clears_restore_truth,
        "api_sync_auth_restore_guard_present": api_sync_auth_restore_guard_present,
        "api_auth_restore_request_kind_present": api_auth_restore_request_kind_present,
        "heavy_10_5_guards_preserved": heavy_10_5_guards_preserved,
        "token_value_not_logged": token_value_not_logged,
        "prior_40_20_ok": prior_40_20_status == "ok",
    }
    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    status = "blocker" if blockers else "ok"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_40_20_status": prior_40_20_status,
        "blockers": blockers,
        "recommended_next_actions": [
            "Keep localStorage token as a restore candidate only, not auth truth.",
            "Keep /api/auth/me as the startup auth source of truth.",
            "Keep sync blocked while authRestorePending is true.",
            "Run 40.21 before opening Paket 11.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.21 Auth Restore Truth Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- State localStorage auth truth degil: `{_yn(report['state_auth_not_localstorage_truth'])}`")
    lines.append(f"- Restore alanlari mevcut: `{_yn(report['state_auth_restore_fields_present'])}`")
    lines.append(f"- Init restore gate: `{_yn(report['init_restore_gate_present'])}`")
    lines.append(f"- RestoreAuth fonksiyonu: `{_yn(report['restore_auth_function_present'])}`")
    lines.append("")
    lines.append("## Auth Restore")
    lines.append("")
    lines.append(f"- 401/403 token temizler: `{_yn(report['restore_auth_401_clears_token'])}`")
    lines.append(f"- Network hatasi tokeni hemen silmez: `{_yn(report['restore_auth_network_keeps_token'])}`")
    lines.append(f"- Login restore truth set eder: `{_yn(report['login_success_sets_restore_truth'])}`")
    lines.append(f"- Logout restore truth temizler: `{_yn(report['logout_clears_restore_truth'])}`")
    lines.append(f"- Token degeri loglanmaz: `{_yn(report['token_value_not_logged'])}`")
    lines.append("")
    lines.append("## Sync Guard")
    lines.append("")
    lines.append(f"- syncApiData auth restore guard: `{_yn(report['api_sync_auth_restore_guard_present'])}`")
    lines.append(f"- auth_restore request kind: `{_yn(report['api_auth_restore_request_kind_present'])}`")
    lines.append(f"- Paket 10.5 heavy guardlari: `{_yn(report['heavy_10_5_guards_preserved'])}`")
    lines.append(f"- 40.20: `{report['prior_40_20_status']}`")
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
        lines.append("Auth restore truth, token validation ve startup sync gate kontrolleri temiz.")
    else:
        lines.append("Auth restore truth blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT_OK",
        "blocker": "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"state_auth_not_localstorage_truth={str(report['state_auth_not_localstorage_truth']).lower()}")
    print(f"init_restore_gate_present={str(report['init_restore_gate_present']).lower()}")
    print(f"restore_auth_function_present={str(report['restore_auth_function_present']).lower()}")
    print(f"api_sync_auth_restore_guard_present={str(report['api_sync_auth_restore_guard_present']).lower()}")
    print(f"prior_40_20_status={report['prior_40_20_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
