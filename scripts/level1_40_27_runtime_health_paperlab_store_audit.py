#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REAL_TRADE_SAFETY = ROOT / "backend" / "services" / "real_trade_safety_service.py"
PAPER_LAB_STORE = ROOT / "backend" / "services" / "paper_lab_store.py"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
AUDIT_21 = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
AUDIT_22 = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json"
AUDIT_23 = ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json"
AUDIT_24 = ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json"
AUDIT_25 = ROOT / "docs" / "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.json"
AUDIT_26 = ROOT / "docs" / "LEVEL1_40_26_PAPERLAB_HYDRATION_STABILITY_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.md"


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
    safety = _load_text(REAL_TRADE_SAFETY)
    paper_lab_store = _load_text(PAPER_LAB_STORE)
    audit_20 = _load_json(AUDIT_20)
    audit_21 = _load_json(AUDIT_21)
    audit_22 = _load_json(AUDIT_22)
    audit_23 = _load_json(AUDIT_23)
    audit_24 = _load_json(AUDIT_24)
    audit_25 = _load_json(AUDIT_25)
    audit_26 = _load_json(AUDIT_26)

    runtime_fn = _section(safety, "def build_runtime_health", "def build_real_trade_safety_status")
    store_health_fn = _section(safety, "def _paper_lab_store_runtime_health", "def _legacy_paper_lab_runtime_health")
    store_payload_fn = _section(safety, "def _paper_lab_store_payload", "def _paper_lab_store_runtime_health")
    legacy_fn = _section(safety, "def _legacy_paper_lab_runtime_health", "def build_runtime_health")
    username_fn = _section(safety, "def _runtime_username", "def _paper_lab_store_runtime_health")

    real_trade_safety_service_imports_get_last_paper_lab_run = (
        "from services.paper_lab_store import get_last_paper_lab_run" in safety
        and "def get_last_paper_lab_run" in paper_lab_store
    )
    build_runtime_health_uses_paper_lab_store = _contains_all(runtime_fn + store_health_fn, [
        "_paper_lab_store_runtime_health(runtime_username)",
        "get_last_paper_lab_run(username)",
        '"source": "paper_lab_store"',
    ])
    paper_lab_store_read_is_try_except_protected = _contains_all(store_health_fn, [
        "try:",
        "last_run = get_last_paper_lab_run(username)",
        "except Exception as exc:",
        '"error": str(exc)[:240]',
    ])
    health_failure_does_not_break_endpoint = _contains_all(store_health_fn, [
        '"state": "missing"',
        '"seconds": None',
        '"fresh": False',
        '"source": "paper_lab_store"',
    ])
    last_paper_lab_includes_source_paper_lab_store = _contains_all(store_health_fn + store_payload_fn, [
        '"state": "ok"',
        '"started_at": started_at',
        '"completed_at": completed_at',
        '"run_id": last_run.get("run_id")',
        '"status": last_run.get("status")',
        '"source": "paper_lab_store"',
    ])
    fallback_to_old_fields_preserved = _contains_all(legacy_fn + runtime_fn, [
        "data.get(\"last_paper_lab_tick\")",
        "data.get(\"last_model_evaluation_at\")",
        "lab.get(\"last_run_at\")",
        '"source"] = "legacy_runtime_fields"',
        "_paper_lab_store_runtime_health(runtime_username) or _legacy_paper_lab_runtime_health(data, lab)",
    ])
    runtime_health_username_priority_present = _contains_all(username_fn, [
        "for source in [settings, data]",
        "for key in [\"username\", \"user\"]",
        "return \"admin\"",
    ])

    prior_40_20_status = audit_20.get("status")
    prior_40_21_status = audit_21.get("status")
    prior_40_22_status = audit_22.get("status")
    prior_40_23_status = audit_23.get("status")
    prior_40_24_status = audit_24.get("status")
    prior_40_25_status = audit_25.get("status")
    prior_40_26_status = audit_26.get("status")

    checks = {
        "real_trade_safety_service_imports_get_last_paper_lab_run": real_trade_safety_service_imports_get_last_paper_lab_run,
        "build_runtime_health_uses_paper_lab_store": build_runtime_health_uses_paper_lab_store,
        "paper_lab_store_read_is_try_except_protected": paper_lab_store_read_is_try_except_protected,
        "health_failure_does_not_break_endpoint": health_failure_does_not_break_endpoint,
        "last_paper_lab_includes_source_paper_lab_store": last_paper_lab_includes_source_paper_lab_store,
        "fallback_to_old_fields_preserved": fallback_to_old_fields_preserved,
        "runtime_health_username_priority_present": runtime_health_username_priority_present,
        "prior_40_20_ok": prior_40_20_status == "ok",
        "prior_40_21_ok": prior_40_21_status == "ok",
        "prior_40_22_ok": prior_40_22_status == "ok",
        "prior_40_23_ok": prior_40_23_status == "ok",
        "prior_40_24_ok": prior_40_24_status == "ok",
        "prior_40_25_ok": prior_40_25_status == "ok",
        "prior_40_26_ok": prior_40_26_status == "ok",
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
        "blockers": blockers,
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.27 Runtime Health PaperLab Store Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Store import: `{_yn(report['real_trade_safety_service_imports_get_last_paper_lab_run'])}`")
    lines.append(f"- Runtime health store kullanimi: `{_yn(report['build_runtime_health_uses_paper_lab_store'])}`")
    lines.append(f"- Try/except korumasi: `{_yn(report['paper_lab_store_read_is_try_except_protected'])}`")
    lines.append(f"- Legacy fallback: `{_yn(report['fallback_to_old_fields_preserved'])}`")
    lines.append("")
    lines.append("## Kontroller")
    lines.append("")
    for key in [
        "health_failure_does_not_break_endpoint",
        "last_paper_lab_includes_source_paper_lab_store",
        "runtime_health_username_priority_present",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Onceki Auditler")
    lines.append("")
    for number in ["20", "21", "22", "23", "24", "25", "26"]:
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
        lines.append("Runtime health last_paper_lab kaynagi Paper Lab persistent store ile baglandi.")
    else:
        lines.append("Runtime health Paper Lab store link blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT_OK",
        "blocker": "LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"build_runtime_health_uses_paper_lab_store={str(report['build_runtime_health_uses_paper_lab_store']).lower()}")
    print(f"paper_lab_store_read_is_try_except_protected={str(report['paper_lab_store_read_is_try_except_protected']).lower()}")
    print(f"last_paper_lab_includes_source_paper_lab_store={str(report['last_paper_lab_includes_source_paper_lab_store']).lower()}")
    print(f"fallback_to_old_fields_preserved={str(report['fallback_to_old_fields_preserved']).lower()}")
    print(f"prior_40_26_status={report['prior_40_26_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
