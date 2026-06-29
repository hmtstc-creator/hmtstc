#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAPER_LAB_STORE = ROOT / "backend" / "services" / "paper_lab_store.py"
REAL_TRADE_SAFETY = ROOT / "backend" / "services" / "real_trade_safety_service.py"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
AUDIT_21 = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
AUDIT_22 = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json"
AUDIT_23 = ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json"
AUDIT_24 = ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json"
AUDIT_25 = ROOT / "docs" / "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.json"
AUDIT_26 = ROOT / "docs" / "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.json"
AUDIT_27 = ROOT / "docs" / "LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.md"


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
    paper_lab_store = _load_text(PAPER_LAB_STORE)
    safety = _load_text(REAL_TRADE_SAFETY)
    audit_20 = _load_json(AUDIT_20)
    audit_21 = _load_json(AUDIT_21)
    audit_22 = _load_json(AUDIT_22)
    audit_23 = _load_json(AUDIT_23)
    audit_24 = _load_json(AUDIT_24)
    audit_25 = _load_json(AUDIT_25)
    audit_26 = _load_json(AUDIT_26)
    audit_27 = _load_json(AUDIT_27)

    latest_any_fn = _section(paper_lab_store, "def get_latest_paper_lab_run_any_user", "def build_paper_lab_status")
    store_health_fn = _section(safety, "def _paper_lab_store_runtime_health", "def _legacy_paper_lab_runtime_health")
    payload_fn = _section(safety, "def _paper_lab_store_payload", "def _paper_lab_store_runtime_health")
    runtime_fn = _section(safety, "def build_runtime_health", "def build_real_trade_safety_status")
    legacy_fn = _section(safety, "def _legacy_paper_lab_runtime_health", "def build_runtime_health")

    paper_lab_store_has_get_latest_any_user = "def get_latest_paper_lab_run_any_user" in paper_lab_store
    latest_any_user_scans_users_dict = _contains_all(latest_any_fn, [
        "store = load_paper_lab_store()",
        'users = store.get("users")',
        "for username, state in users.items()",
        "for raw_run in runs",
        "completed_at",
        "started_at",
    ])
    latest_any_user_returns_username = _contains_all(latest_any_fn, [
        'latest_run["username"] = str(username)',
        "return latest_run",
    ])
    build_runtime_health_uses_exact_username_first = _contains_all(store_health_fn + runtime_fn, [
        "runtime_username = _runtime_username(data, settings)",
        "last_run = get_last_paper_lab_run(username)",
        "last_run.setdefault(\"username\", username)",
    ])
    build_runtime_health_falls_back_to_any_user = _contains_all(store_health_fn, [
        "latest_run = get_latest_paper_lab_run_any_user()",
        "return _paper_lab_store_payload(latest_run, stale_after_seconds)",
    ])
    last_paper_lab_includes_username = '"username": last_run.get("username")' in payload_fn
    source_paper_lab_store_preserved = '"source": "paper_lab_store"' in payload_fn and '"source": "paper_lab_store"' in store_health_fn
    legacy_fallback_preserved = _contains_all(legacy_fn + runtime_fn, [
        "legacy_runtime_fields",
        "data.get(\"last_paper_lab_tick\")",
        "data.get(\"last_model_evaluation_at\")",
        "lab.get(\"last_run_at\")",
        "_paper_lab_store_runtime_health(runtime_username) or _legacy_paper_lab_runtime_health(data, lab)",
    ])
    health_exception_safe = _contains_all(store_health_fn, [
        "try:",
        "except Exception as exc:",
        '"state": "missing"',
        '"source": "paper_lab_store"',
        '"error": str(exc)[:240]',
    ])

    prior_40_20_status = audit_20.get("status")
    prior_40_21_status = audit_21.get("status")
    prior_40_22_status = audit_22.get("status")
    prior_40_23_status = audit_23.get("status")
    prior_40_24_status = audit_24.get("status")
    prior_40_25_status = audit_25.get("status")
    prior_40_26_status = audit_26.get("status")
    prior_40_27_status = audit_27.get("status")

    checks = {
        "paper_lab_store_has_get_latest_any_user": paper_lab_store_has_get_latest_any_user,
        "latest_any_user_scans_users_dict": latest_any_user_scans_users_dict,
        "latest_any_user_returns_username": latest_any_user_returns_username,
        "build_runtime_health_uses_exact_username_first": build_runtime_health_uses_exact_username_first,
        "build_runtime_health_falls_back_to_any_user": build_runtime_health_falls_back_to_any_user,
        "last_paper_lab_includes_username": last_paper_lab_includes_username,
        "source_paper_lab_store_preserved": source_paper_lab_store_preserved,
        "legacy_fallback_preserved": legacy_fallback_preserved,
        "health_exception_safe": health_exception_safe,
        "prior_40_20_ok": prior_40_20_status == "ok",
        "prior_40_21_ok": prior_40_21_status == "ok",
        "prior_40_22_ok": prior_40_22_status == "ok",
        "prior_40_23_ok": prior_40_23_status == "ok",
        "prior_40_24_ok": prior_40_24_status == "ok",
        "prior_40_25_ok": prior_40_25_status == "ok",
        "prior_40_26_ok": prior_40_26_status == "ok",
        "prior_40_27_ok": prior_40_27_status == "ok",
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
        "prior_40_26_status": prior_40_26_status,
        "prior_40_27_status": prior_40_27_status,
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.28 Runtime Health PaperLab User Resolution Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Any-user latest reader: `{_yn(report['paper_lab_store_has_get_latest_any_user'])}`")
    lines.append(f"- Users dict taraniyor: `{_yn(report['latest_any_user_scans_users_dict'])}`")
    lines.append(f"- Exact username first: `{_yn(report['build_runtime_health_uses_exact_username_first'])}`")
    lines.append(f"- Any-user fallback: `{_yn(report['build_runtime_health_falls_back_to_any_user'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key in [
        "latest_any_user_returns_username",
        "last_paper_lab_includes_username",
        "source_paper_lab_store_preserved",
        "legacy_fallback_preserved",
        "health_exception_safe",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Onceki Auditler")
    lines.append("")
    for number in ["20", "21", "22", "23", "24", "25", "26", "27"]:
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
        lines.append("Runtime health Paper Lab user resolution store genelinde temiz.")
    else:
        lines.append("Runtime health Paper Lab user resolution blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT_OK",
        "blocker": "LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"paper_lab_store_has_get_latest_any_user={str(report['paper_lab_store_has_get_latest_any_user']).lower()}")
    print(f"build_runtime_health_falls_back_to_any_user={str(report['build_runtime_health_falls_back_to_any_user']).lower()}")
    print(f"last_paper_lab_includes_username={str(report['last_paper_lab_includes_username']).lower()}")
    print(f"legacy_fallback_preserved={str(report['legacy_fallback_preserved']).lower()}")
    print(f"prior_40_27_status={report['prior_40_27_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
