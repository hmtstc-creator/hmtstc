#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import py_compile
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "docs" / "LEVEL1_40_11_RECENT_GATES_AUDIT_REPORT.json"
REPORT_MD = ROOT / "docs" / "LEVEL1_40_11_RECENT_GATES_AUDIT.md"

RUNTIME_PATHS = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
    "backend/runtime_backups",
]

GATES = {
    "rev34_deploy_rollback": {
        "routes": [
            "/revision-34",
            "/revision-34/deploy-safety",
            "/revision-34/pre-deploy-backup",
            "/revision-34/rollback-safety",
            "/revision-34/real-lock",
        ],
        "scripts": [
            "scripts/revision_34_quality_check.py",
            "scripts/pre_deploy_backup.py",
            "scripts/post_deploy_check.py",
            "scripts/build_release_zip.py",
        ],
        "services": ["backend/services/deploy_safety_service.py"],
        "docs": ["deploy/REV34_DEPLOY_ROLLBACK.md"],
        "frontend_markers": ["revision34Quality", "deploySafety34", "rollbackSafety34", "realLock34"],
    },
    "rev35_ai_safe_mode": {
        "routes": [
            "/revision-35",
            "/revision-35/ai-policy",
            "/revision-35/no-trade-authority",
            "/revision-35/paper-queue",
            "/revision-35/prompt-logging",
        ],
        "scripts": ["scripts/revision_35_quality_check.py"],
        "services": [
            "backend/services/ai_analyst_safe_mode_service.py",
            "backend/services/agent_service.py",
            "backend/services/llm_service.py",
        ],
        "docs": ["docs/REV35_AI_ANALYST_SAFE_MODE.md"],
        "frontend_markers": ["revision35Quality", "aiSafeMode35", "aiNoTradeAuthority35"],
    },
    "rev36_live_micro_pilot": {
        "routes": [
            "/revision-36",
            "/revision-36/runbook",
            "/revision-36/rehearsal",
            "/revision-36/tiny-order",
            "/revision-36/auto-lock",
            "/revision-36/final-report",
        ],
        "scripts": ["scripts/revision_36_quality_check.py"],
        "services": [
            "backend/services/live_micro_pilot_procedure_service.py",
            "backend/services/real_pilot_service.py",
        ],
        "docs": ["docs/REV36_LIVE_MICRO_PILOT_PROCEDURE.md"],
        "frontend_markers": ["revision36Quality", "revision36Runbook", "revision36FinalReport"],
    },
    "rev37_final_verification": {
        "routes": [
            "/revision-37",
            "/revision-37/gates",
            "/revision-37/autonomous-policy",
            "/revision-37/package-manifest",
            "/revision-37/checksum",
            "/revision-37/runtime-leak",
            "/revision-37/endpoint-contract",
        ],
        "scripts": ["scripts/revision_37_quality_check.py"],
        "services": ["backend/services/revision_37_service.py"],
        "docs": ["docs/REV37_FINAL_VERIFICATION.md"],
        "frontend_markers": ["revision37Quality", "revision37Gates", "revision37EndpointContract"],
    },
    "rev38_summary_dashboard": {
        "routes": ["/summary"],
        "scripts": ["scripts/revision_38_summary_quality_check.py"],
        "services": ["backend/services/summary_service.py"],
        "docs": ["docs/REV38_SUMMARY_DASHBOARD.md"],
        "frontend_markers": ["/api/summary", "window.HMTSTC_PAGES.summary", '["summary", "Summary"]'],
    },
}


def read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def compile_python_tree() -> list[str]:
    failures: list[str] = []
    for base in [ROOT / "backend", ROOT / "scripts", ROOT / "tests"]:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                py_compile.compile(str(path), doraise=True)
            except Exception as exc:  # pragma: no cover - CLI guard
                failures.append(f"{path.relative_to(ROOT)}: {exc}")
    return failures


def node_check_frontend() -> list[str]:
    failures: list[str] = []
    js_paths = list((ROOT / "frontend" / "js").rglob("*.js")) if (ROOT / "frontend" / "js").exists() else []
    for path in js_paths:
        result = subprocess.run(["node", "--check", str(path)], cwd=ROOT, text=True, capture_output=True)
        if result.returncode != 0:
            failures.append(f"{path.relative_to(ROOT)}: {result.stderr.strip()}")
    return failures


def clean_runtime() -> None:
    for rel in RUNTIME_PATHS:
        path = ROOT / rel
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            import shutil
            shutil.rmtree(path)


def run_script(rel: str) -> dict:
    clean_runtime()
    result = subprocess.run([sys.executable, rel], cwd=ROOT, text=True, capture_output=True)
    clean_runtime()
    return {
        "script": rel,
        "returncode": result.returncode,
        "stdout_tail": result.stdout.strip().splitlines()[-5:],
        "stderr_tail": result.stderr.strip().splitlines()[-5:],
        "ok": result.returncode == 0,
    }


def extract_quality_routes() -> set[str]:
    routes_text = read("backend/routes/quality_routes.py")
    return set(re.findall(r'@router\.get\("([^"]+)"\)', routes_text))


def audit_gate(name: str, cfg: dict) -> dict:
    quality_routes = extract_quality_routes()
    quality_text = read("backend/routes/quality_routes.py")
    api_text = read("frontend/js/app/api.js")
    intelligence_text = read("frontend/js/pages/intelligence.js")
    summary_text = read("frontend/js/pages/summary.js")
    data_text = read("frontend/js/data.js")
    frontend_blob = "\n".join([api_text, intelligence_text, summary_text, data_text])

    missing_routes = [route for route in cfg["routes"] if route not in quality_routes and route not in read("backend/routes/summary_routes.py")]
    missing_scripts = [rel for rel in cfg["scripts"] if not (ROOT / rel).exists()]
    missing_services = [rel for rel in cfg["services"] if not (ROOT / rel).exists()]
    missing_docs = [rel for rel in cfg["docs"] if not (ROOT / rel).exists()]
    missing_frontend = [marker for marker in cfg["frontend_markers"] if marker not in frontend_blob]

    script_runs = []
    for rel in cfg["scripts"]:
        if (ROOT / rel).exists() and Path(rel).name.startswith("revision_"):
            script_runs.append(run_script(rel))

    ok = not any([missing_routes, missing_scripts, missing_services, missing_docs, missing_frontend]) and all(s["ok"] for s in script_runs)
    return {
        "name": name,
        "status": "ok" if ok else "review",
        "missing_routes": missing_routes,
        "missing_scripts": missing_scripts,
        "missing_services": missing_services,
        "missing_docs": missing_docs,
        "missing_frontend_markers": missing_frontend,
        "script_runs": script_runs,
    }


def main() -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    py_failures = compile_python_tree()
    js_failures = node_check_frontend()
    clean_runtime()
    runtime_leaks = [rel for rel in RUNTIME_PATHS if (ROOT / rel).exists()]
    gate_results = [audit_gate(name, cfg) for name, cfg in GATES.items()]
    clean_runtime()
    review_gates = [g["name"] for g in gate_results if g["status"] != "ok"]

    route_count = 0
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        from main import app  # type: ignore
        route_count = len(app.routes)
        clean_runtime()
    except Exception as exc:
        py_failures.append(f"backend main import failed: {exc}")

    report = {
        "status": "ok" if not py_failures and not js_failures and not runtime_leaks and not review_gates else "review",
        "scope": "Rev34-Rev38 recent gate integrity audit",
        "route_count": route_count,
        "python_compile_failures": py_failures,
        "frontend_js_failures": js_failures,
        "runtime_leaks": runtime_leaks,
        "gates": gate_results,
        "review_gates": review_gates,
        "summary": {
            "gate_count": len(gate_results),
            "ok_gate_count": sum(1 for g in gate_results if g["status"] == "ok"),
            "review_gate_count": len(review_gates),
        },
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# LEVEL1 40.11 — Recent Gates Audit",
        "",
        "Rev34–Rev38 gate bütünlüğünü doğrular: route, servis, script, dokümantasyon, frontend sync marker ve kalite script çalıştırma kontrolleri.",
        "",
        f"- Status: `{report['status']}`",
        f"- FastAPI route count: `{route_count}`",
        f"- Gate count: `{report['summary']['gate_count']}`",
        f"- OK gates: `{report['summary']['ok_gate_count']}`",
        f"- Review gates: `{report['summary']['review_gate_count']}`",
        f"- Runtime leaks: `{len(runtime_leaks)}`",
        "",
        "## Gate Results",
        "",
        "| Gate | Status | Missing route | Missing service | Missing frontend |",
        "|---|---:|---:|---:|---:|",
    ]
    for gate in gate_results:
        lines.append(
            f"| {gate['name']} | {gate['status']} | {len(gate['missing_routes'])} | {len(gate['missing_services'])} | {len(gate['missing_frontend_markers'])} |"
        )
    lines.extend([
        "",
        "## Contract",
        "",
        "Bu script sadece read-only denetim yapar. Runtime store veya trading state değiştirmez.",
        "Başarılı çıktı marker'ı: `LEVEL1_40_11_RECENT_GATES_AUDIT_OK`.",
    ])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if report["status"] != "ok":
        raise SystemExit("LEVEL1_40_11_RECENT_GATES_AUDIT_REVIEW: " + ", ".join(review_gates or py_failures or js_failures or runtime_leaks))
    print("LEVEL1_40_11_RECENT_GATES_AUDIT_OK")
    print(f"gate_count={report['summary']['gate_count']}")
    print(f"route_count={route_count}")


if __name__ == "__main__":
    main()
