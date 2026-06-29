#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INIT_JS = ROOT / "frontend" / "js" / "app" / "init.js"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
AUTH_JS = ROOT / "frontend" / "js" / "app" / "auth.js"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
COIN_FILTER_JS = ROOT / "frontend" / "js" / "pages" / "coinFilter.js"
AUDIT_19 = ROOT / "docs" / "LEVEL1_40_19_MUTATION_ABORT_ISOLATION_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.md"


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
    init_js = _load_text(INIT_JS)
    api_js = _load_text(API_JS)
    auth_js = _load_text(AUTH_JS)
    rules_js = _load_text(RULES_JS)
    coin_filter_js = _load_text(COIN_FILTER_JS)
    audit_19 = _load_json(AUDIT_19)

    sync_fn = _section(api_js, "syncApiData: async function", "syncHeavyApiData: async function")
    heavy_fn = _section(api_js, "syncHeavyApiData: async function", "\n  }\n};")
    login_fn = _section(auth_js, "login: async function", "changeOwnPassword: async function")
    logout_fn = _section(auth_js, "logout: async function", "renderPasswordChange: function")
    coin_save_fn = _section(coin_filter_js, "save: async function", "refreshScan: async function")

    polling_30000_present = "setInterval(function" in init_js and "}, 30000)" in init_js
    polling_5000_absent = "5000" not in init_js
    polling_guards_present = _contains_all(init_js, [
        "!HMTSTC_APP.state.auth",
        "HMTSTC_APP.isUserEditing()",
        "HMTSTC_APP.state.syncInProgress",
    ]) and (
        "HMTSTC_APP.syncApiData()" in init_js
        or "HMTSTC_APP.syncApiData({ skipHeavySync: false })" in init_js
    )
    heavy_startup_delay_present = _contains_all(heavy_fn, [
        "heavySyncAllowedAtMs",
        "nowMs + 120000",
        "nowMs < HMTSTC_APP.state.heavySyncAllowedAtMs",
        "return",
    ])
    heavy_interval_300000_present = "nowMs - HMTSTC_APP.state.lastHeavySyncMs < 300000" in heavy_fn
    heavy_sync_does_not_toggle_core_ready_false = (
        "apiReady = false" not in heavy_fn
        and "apiSyncReady = false" not in heavy_fn
    )
    heavy_endpoints_deferred_guarded = _contains_all(heavy_fn, [
        "/api/models/reports?period=7d",
        "/api/intelligence/overview",
        "/api/intelligence/auto-bot-mode-decision",
        "/api/intelligence/tradeability-decision",
        "heavySyncAllowedAtMs",
        "lastHeavySyncMs",
        "300000",
    ])
    bundle_timeout_fallback_present = _contains_all(sync_fn, [
        "bundleError",
        "Promise.allSettled",
        'this.fetchJson("/api/rules"',
        'this.fetchJson("/api/settings"',
        "fallbackCoreReady",
        "bundle_status",
        '"degraded"',
    ])
    rules_hydration_preserve_present = _contains_all(api_js, [
        "preserveOrApplyRulesPayload",
        "rules_payload_preserved",
        "preserved_after_empty_payload",
    ])
    coinfilter_save_no_immediate_heavy_sync = (
        "await HMTSTC_APP.syncHeavyApiData()" not in coin_save_fn
        and "skipHeavySync: true" in coin_save_fn
    )
    auth_login_logout_protected_mutation = (
        _contains_all(login_fn, [
            '"/api/auth/login"',
            'requestKind: "mutation"',
            "preventGlobalAbort: true",
            "timeoutMs: 15000",
            "skipHeavySync: true",
            "heavySyncAllowedAtMs",
        ])
        and _contains_all(logout_fn, [
            '"/api/auth/logout"',
            'requestKind: "mutation"',
            "preventGlobalAbort: true",
            "timeoutMs: 15000",
        ])
    )
    login_no_immediate_heavy_sync = "syncHeavyApiData" not in login_fn and "skipHeavySync: true" in login_fn
    rules_save_no_immediate_heavy_sync = (
        "skipHeavySync: true" in rules_js
        and "Paper Lab başarılı kaydedildi; ancak son refresh tamamlanamadı." in rules_js
        and "preserveOrApplyRulesPayload" in rules_js
    )
    prior_40_19_status = audit_19.get("status")

    checks = {
        "polling_30000_present": polling_30000_present,
        "polling_5000_absent": polling_5000_absent,
        "polling_guards_present": polling_guards_present,
        "heavy_startup_delay_present": heavy_startup_delay_present,
        "heavy_interval_300000_present": heavy_interval_300000_present,
        "heavy_sync_does_not_toggle_core_ready_false": heavy_sync_does_not_toggle_core_ready_false,
        "heavy_endpoints_deferred_guarded": heavy_endpoints_deferred_guarded,
        "bundle_timeout_fallback_present": bundle_timeout_fallback_present,
        "rules_hydration_preserve_present": rules_hydration_preserve_present,
        "coinfilter_save_no_immediate_heavy_sync": coinfilter_save_no_immediate_heavy_sync,
        "auth_login_logout_protected_mutation": auth_login_logout_protected_mutation,
        "login_no_immediate_heavy_sync": login_no_immediate_heavy_sync,
        "rules_save_no_immediate_heavy_sync": rules_save_no_immediate_heavy_sync,
        "prior_40_19_ok": prior_40_19_status == "ok",
    }

    blockers = [f"{name}=false" for name, value in checks.items() if not value]
    status = "blocker" if blockers else "ok"

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "prior_40_19_status": prior_40_19_status,
        "blockers": blockers,
        "recommended_next_actions": [
            "Keep startup polling at 30 seconds or slower.",
            "Keep heavy sync delayed for the first two minutes after login/startup.",
            "Keep /api/rules and /api/settings independent from dashboard bundle success.",
            "Run 40.20 before Paket 11 live acceptance.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.20 Live Startup Rules Hydration Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Polling 30000 ms: `{_yn(report['polling_30000_present'])}`")
    lines.append(f"- 5000 ms polling yok: `{_yn(report['polling_5000_absent'])}`")
    lines.append(f"- Heavy startup delay: `{_yn(report['heavy_startup_delay_present'])}`")
    lines.append(f"- Heavy interval 300000 ms: `{_yn(report['heavy_interval_300000_present'])}`")
    lines.append(f"- Bundle fallback hydration: `{_yn(report['bundle_timeout_fallback_present'])}`")
    lines.append("")
    lines.append("## Frontend Guards")
    lines.append("")
    lines.append(f"- Polling guards: `{_yn(report['polling_guards_present'])}`")
    lines.append(f"- Heavy core ready false yapmaz: `{_yn(report['heavy_sync_does_not_toggle_core_ready_false'])}`")
    lines.append(f"- Heavy endpointler deferred/guarded: `{_yn(report['heavy_endpoints_deferred_guarded'])}`")
    lines.append(f"- Rules hydrate preserve: `{_yn(report['rules_hydration_preserve_present'])}`")
    lines.append(f"- CoinFilter save immediate heavy yok: `{_yn(report['coinfilter_save_no_immediate_heavy_sync'])}`")
    lines.append(f"- Auth login/logout protected mutation: `{_yn(report['auth_login_logout_protected_mutation'])}`")
    lines.append(f"- Login immediate heavy yok: `{_yn(report['login_no_immediate_heavy_sync'])}`")
    lines.append(f"- Rules save immediate heavy yok: `{_yn(report['rules_save_no_immediate_heavy_sync'])}`")
    lines.append("")
    lines.append("## Prior Audit")
    lines.append("")
    lines.append(f"- 40.19: `{report['prior_40_19_status']}`")
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
        lines.append("Live startup, rules hydration ve heavy sync guard kontrolleri temiz.")
    else:
        lines.append("Live startup veya rules hydration blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT_OK",
        "blocker": "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"polling_30000_present={str(report['polling_30000_present']).lower()}")
    print(f"heavy_startup_delay_present={str(report['heavy_startup_delay_present']).lower()}")
    print(f"heavy_interval_300000_present={str(report['heavy_interval_300000_present']).lower()}")
    print(f"bundle_timeout_fallback_present={str(report['bundle_timeout_fallback_present']).lower()}")
    print(f"coinfilter_save_no_immediate_heavy_sync={str(report['coinfilter_save_no_immediate_heavy_sync']).lower()}")
    print(f"auth_login_logout_protected_mutation={str(report['auth_login_logout_protected_mutation']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
