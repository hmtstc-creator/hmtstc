#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAPER_LAB_STORE = ROOT / "backend" / "services" / "paper_lab_store.py"
RULE_ENGINE = ROOT / "backend" / "services" / "rule_engine.py"
RULE_ROUTES = ROOT / "backend" / "routes" / "rule_routes.py"
DASHBOARD_ROUTES = ROOT / "backend" / "routes" / "dashboard_routes.py"
API_JS = ROOT / "frontend" / "js" / "app" / "api.js"
RULES_JS = ROOT / "frontend" / "js" / "app" / "rules.js"
STRATEGIES_JS = ROOT / "frontend" / "js" / "pages" / "strategies.js"
GITIGNORE = ROOT / ".gitignore"
STORE_EXAMPLE = ROOT / "backend" / "paper_lab_store.example.json"
AUDIT_20 = ROOT / "docs" / "LEVEL1_40_20_LIVE_STARTUP_RULES_HYDRATION_AUDIT.json"
AUDIT_21 = ROOT / "docs" / "LEVEL1_40_21_AUTH_RESTORE_TRUTH_AUDIT.json"
AUDIT_22 = ROOT / "docs" / "LEVEL1_40_22_COINFILTER_RULES_PAPERLAB_AUDIT.json"
AUDIT_23 = ROOT / "docs" / "LEVEL1_40_23_RULES_PAPERLAB_INDEPENDENCE_AUDIT.json"
AUDIT_24 = ROOT / "docs" / "LEVEL1_40_24_PAPERLAB_AUTONOMOUS_ENGINE_AUDIT.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT.md"


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


def _deploy_text() -> str:
    chunks: list[str] = []
    for base in [ROOT / "deploy", ROOT / "scripts"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".sh", ".ps1", ".py", ".bat", ".cmd", ".md"}:
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
    return "\n".join(chunks)


def build_report() -> dict[str, Any]:
    paper_lab_store = _load_text(PAPER_LAB_STORE)
    rule_engine = _load_text(RULE_ENGINE)
    rule_routes = _load_text(RULE_ROUTES)
    dashboard_routes = _load_text(DASHBOARD_ROUTES)
    api_js = _load_text(API_JS)
    rules_js = _load_text(RULES_JS)
    strategies_js = _load_text(STRATEGIES_JS)
    gitignore = _load_text(GITIGNORE)
    deploy_text = _deploy_text()
    audit_20 = _load_json(AUDIT_20)
    audit_21 = _load_json(AUDIT_21)
    audit_22 = _load_json(AUDIT_22)
    audit_23 = _load_json(AUDIT_23)
    audit_24 = _load_json(AUDIT_24)

    activate_fn = _section(rule_engine, "def activate_paper_lab_rules", "def export_rules")
    api_sync_fn = _section(api_js, "syncApiData: async function", "syncHeavyApiData: async function")
    apply_status_fn = _section(api_js, "applyPaperLabStatusPayload: function", "syncUsersData: async function")
    frontend_activate_fn = _section(rules_js, "activatePaperLabRules: async function", "exportRulesDebugFile: async function")

    paper_lab_store_service_present = _contains_all(paper_lab_store, [
        "def load_paper_lab_store",
        "def save_paper_lab_store",
        "def record_paper_lab_run",
        "def get_last_paper_lab_run",
        "def list_paper_lab_runs",
        "def normalize_paper_lab_store",
        'PAPER_LAB_STORE_FILE = BASE_DIR / "paper_lab_store.json"',
    ])
    paper_lab_store_atomic_write_present = _contains_all(paper_lab_store, [
        "threading.RLock",
        "uuid4",
        ".tmp",
        "os.replace",
        "with _STORE_LOCK",
    ]) and "with_suffix(path.suffix + \".tmp\")" not in paper_lab_store
    paper_lab_store_runtime_gitignored = (
        "backend/paper_lab_store.json" in gitignore
        and "backend/paper_lab_store.json.*" in gitignore
    )
    paper_lab_store_example_present = STORE_EXAMPLE.exists()
    paper_lab_store_normalize_present = _contains_all(paper_lab_store, [
        "normalize_paper_lab_run",
        "normalize_paper_lab_store",
        "MAX_RUNS_PER_USER = 20",
        "_backup_corrupt_store",
    ])

    paper_lab_run_recorded_on_success = _contains_all(activate_fn, [
        "record_paper_lab_run(username",
        '"status": "completed"',
        '"filter_ids": final_filter_ids',
        '"strategy_ids": final_strategy_ids',
        '"accepted_combinations": accepted_count',
        '"rejected_combinations": rejected_count',
    ])
    paper_lab_run_recorded_on_failure = _contains_all(activate_fn, [
        "except Exception as error",
        '"status": "failed"',
        '"error_message": error_message',
        "record_paper_lab_run(username",
        "raise",
    ])
    paper_lab_run_id_present = _contains_all(activate_fn, [
        "run_id = str(uuid4())",
        '"run_id": run_id',
        '"last_run": persistent_run',
    ])
    paper_lab_rules_fingerprint_present = _contains_all(paper_lab_store + rule_engine, [
        "paper_lab_rules_fingerprint",
        "hashlib.sha256",
        '"rules_fingerprint"',
    ])
    paper_lab_last_run_endpoint_present = (
        '@router.get("/paper-lab/status")' in rule_routes
        and "build_persistent_paper_lab_status" in rule_routes
        and '"paper_lab_status": build_persistent_paper_lab_status(user)' in dashboard_routes
    )

    frontend_hydrates_paperlab_from_backend = _contains_all(apply_status_fn + api_sync_fn, [
        "applyPaperLabStatusPayload",
        "last_run",
        "HMTSTC_APP.state.lastPaperLabResult",
        "HMTSTC_APP.state.paperLabRun",
        "HMTSTC_DATA.paperLabStatus",
        '"/api/rules/paper-lab/status"',
        "bundled.paper_lab_status",
    ])
    strategies_page_uses_persistent_last_run = _contains_all(strategies_js, [
        "persistentLastRun",
        "last_run_matches_current_rules",
        "Rules fingerprint match",
        "Run id",
        "Son run zamanı",
        "Bu Paper Lab sonucu mevcut filtre/strateji setinden önce oluşturuldu.",
    ])
    frontend_not_only_using_ram_state = _contains_all(frontend_activate_fn + api_sync_fn, [
        "applyPaperLabStatusPayload(result.paper_lab_status || result",
        "paper_lab_persistent_store",
        "api_rules_paper_lab_status",
    ])

    unconditional_copy_tokens = [
        "cp backend/paper_lab_store.example.json backend/paper_lab_store.json",
        "copy backend\\paper_lab_store.example.json backend\\paper_lab_store.json",
        "Copy-Item backend\\paper_lab_store.example.json backend\\paper_lab_store.json",
    ]
    guarded_copy_present = "paper_lab_store.example.json" in deploy_text and ("if [ ! -f backend/paper_lab_store.json ]" in deploy_text or "Test-Path" in deploy_text)
    deploy_does_not_overwrite_paper_lab_store = not any(token in deploy_text for token in unconditional_copy_tokens) or guarded_copy_present

    prior_40_20_status = audit_20.get("status")
    prior_40_21_status = audit_21.get("status")
    prior_40_22_status = audit_22.get("status")
    prior_40_23_status = audit_23.get("status")
    prior_40_24_status = audit_24.get("status")

    checks = {
        "paper_lab_store_service_present": paper_lab_store_service_present,
        "paper_lab_store_atomic_write_present": paper_lab_store_atomic_write_present,
        "paper_lab_store_runtime_gitignored": paper_lab_store_runtime_gitignored,
        "paper_lab_store_example_present": paper_lab_store_example_present,
        "paper_lab_store_normalize_present": paper_lab_store_normalize_present,
        "paper_lab_run_recorded_on_success": paper_lab_run_recorded_on_success,
        "paper_lab_run_recorded_on_failure": paper_lab_run_recorded_on_failure,
        "paper_lab_run_id_present": paper_lab_run_id_present,
        "paper_lab_rules_fingerprint_present": paper_lab_rules_fingerprint_present,
        "paper_lab_last_run_endpoint_present": paper_lab_last_run_endpoint_present,
        "frontend_hydrates_paperlab_from_backend": frontend_hydrates_paperlab_from_backend,
        "strategies_page_uses_persistent_last_run": strategies_page_uses_persistent_last_run,
        "frontend_not_only_using_ram_state": frontend_not_only_using_ram_state,
        "deploy_does_not_overwrite_paper_lab_store": deploy_does_not_overwrite_paper_lab_store,
        "prior_40_20_ok": prior_40_20_status == "ok",
        "prior_40_21_ok": prior_40_21_status == "ok",
        "prior_40_22_ok": prior_40_22_status == "ok",
        "prior_40_23_ok": prior_40_23_status == "ok",
        "prior_40_24_ok": prior_40_24_status == "ok",
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
        "blockers": blockers,
        "recommended_next_actions": [
            "Keep backend/paper_lab_store.json out of Git.",
            "Use /api/rules/paper-lab/status or dashboard bundle for frontend hydration.",
            "Treat fingerprint mismatch as stale research result, not a UI cache miss.",
            "Run 40.25 before opening Paket 11.",
        ],
    }


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.25 PaperLab Persistence Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Store service: `{_yn(report['paper_lab_store_service_present'])}`")
    lines.append(f"- Atomic write: `{_yn(report['paper_lab_store_atomic_write_present'])}`")
    lines.append(f"- Runtime gitignored: `{_yn(report['paper_lab_store_runtime_gitignored'])}`")
    lines.append(f"- Frontend backend hydration: `{_yn(report['frontend_hydrates_paperlab_from_backend'])}`")
    lines.append("")
    lines.append("## Store")
    lines.append("")
    for key in [
        "paper_lab_store_example_present",
        "paper_lab_store_normalize_present",
        "paper_lab_run_recorded_on_success",
        "paper_lab_run_recorded_on_failure",
        "paper_lab_rules_fingerprint_present",
        "paper_lab_last_run_endpoint_present",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Frontend")
    lines.append("")
    for key in [
        "strategies_page_uses_persistent_last_run",
        "frontend_not_only_using_ram_state",
        "deploy_does_not_overwrite_paper_lab_store",
    ]:
        lines.append(f"- {key}: `{_yn(report[key])}`")
    lines.append("")
    lines.append("## Onceki Auditler")
    lines.append("")
    for number in ["20", "21", "22", "23", "24"]:
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
        lines.append("Paper Lab kalici store, hydration ve deploy overwrite korumasi temiz.")
    else:
        lines.append("Paper Lab persistence blocker durumunda.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT_OK",
        "blocker": "LEVEL1_40_25_PAPERLAB_PERSISTENCE_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"paper_lab_store_atomic_write_present={str(report['paper_lab_store_atomic_write_present']).lower()}")
    print(f"paper_lab_run_recorded_on_success={str(report['paper_lab_run_recorded_on_success']).lower()}")
    print(f"paper_lab_run_recorded_on_failure={str(report['paper_lab_run_recorded_on_failure']).lower()}")
    print(f"frontend_hydrates_paperlab_from_backend={str(report['frontend_hydrates_paperlab_from_backend']).lower()}")
    print(f"strategies_page_uses_persistent_last_run={str(report['strategies_page_uses_persistent_last_run']).lower()}")
    print(f"prior_40_24_status={report['prior_40_24_status']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
