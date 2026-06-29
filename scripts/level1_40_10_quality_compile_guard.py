#!/usr/bin/env python3
"""Level1 40.10 quality compile guard.

This guard verifies that quality scripts are real executable checks rather than
static marker files. It compiles all quality/check scripts, performs a light AST
inspection for active assertions/fail paths, runs the recent critical quality
scripts, and writes a machine-readable report.
"""
from __future__ import annotations

import ast
import json
import py_compile
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPORT = DOCS / "LEVEL1_40_10_QUALITY_COMPILE_GUARD_REPORT.json"
MD = DOCS / "LEVEL1_40_10_QUALITY_COMPILE_GUARD.md"

QUALITY_PATTERNS = (
    "revision_*quality_check.py",
    "revision_*_quality_check.py",
    "level1_*_check.py",
    "level1_*_guard.py",
    "level1_*_smoke.py",
    "level1_*_audit.py",
    "level1_*_inventory.py",
    "level1_*_diff.py",
    "level1_*_report.py",
)

RECENT_SCRIPTS_TO_RUN = [
    "scripts/revision_38_summary_quality_check.py",
    "scripts/level1_40_05_runtime_leak_guard.py",
    "scripts/level1_40_11_recent_gates_audit.py",
    "scripts/level1_40_12_summary_regression_check.py",
]


def _discover_scripts() -> list[Path]:
    scripts: set[Path] = set()
    for pattern in QUALITY_PATTERNS:
        scripts.update((ROOT / "scripts").glob(pattern))
    return sorted(path for path in scripts if path.is_file())


def _compile(path: Path) -> dict[str, object]:
    try:
        py_compile.compile(str(path), doraise=True)
        return {"status": "ok"}
    except Exception as exc:  # pragma: no cover - diagnostic path
        return {"status": "failed", "error": str(exc)}


def _ast_profile(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return {"status": "failed", "error": str(exc)}

    node_types = {type(node).__name__ for node in ast.walk(tree)}
    call_names: list[str] = []
    constants: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                call_names.append(func.id)
            elif isinstance(func, ast.Attribute):
                call_names.append(func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            constants.append(node.value)

    has_active_checks = any(name in node_types for name in ["If", "For", "Assert", "Compare", "Raise", "Try"])
    has_failure_path = any(name in call_names for name in ["exit", "fail", "SystemExit"]) or "Raise" in node_types
    has_file_or_contract_checks = any(token in text for token in ["exists()", "py_compile", "node", "subprocess", "rglob", "glob", "REQUIRED", "FORBIDDEN", "checks ="])
    has_ok_marker = any("OK" in c for c in constants)
    print_only = "print(" in text and not (has_active_checks and has_failure_path)
    score = sum([has_active_checks, has_failure_path, has_file_or_contract_checks, has_ok_marker])

    status = "ok" if score >= 3 and not print_only else "review"
    return {
        "status": status,
        "score": score,
        "has_active_checks": has_active_checks,
        "has_failure_path": has_failure_path,
        "has_file_or_contract_checks": has_file_or_contract_checks,
        "has_ok_marker": has_ok_marker,
        "print_only_suspected": print_only,
    }


def _run_script(rel: str) -> dict[str, object]:
    path = ROOT / rel
    if not path.exists():
        return {"script": rel, "status": "missing", "returncode": None, "stdout_tail": "", "stderr_tail": ""}
    result = subprocess.run([sys.executable, str(path)], cwd=str(ROOT), capture_output=True, text=True, timeout=30)
    return {
        "script": rel,
        "status": "ok" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-1200:],
        "stderr_tail": result.stderr[-1200:],
    }


def build_report() -> dict[str, object]:
    scripts = _discover_scripts()
    items: list[dict[str, object]] = []
    compile_failed: list[str] = []
    static_review: list[str] = []

    for script in scripts:
        rel = str(script.relative_to(ROOT))
        compile_result = _compile(script)
        profile = _ast_profile(script)
        item = {
            "script": rel,
            "compile": compile_result,
            "profile": profile,
        }
        items.append(item)
        if compile_result.get("status") != "ok":
            compile_failed.append(rel)
        if profile.get("status") != "ok":
            static_review.append(rel)

    executed = [_run_script(rel) for rel in RECENT_SCRIPTS_TO_RUN]
    execution_failed = [item["script"] for item in executed if item.get("status") != "ok"]

    status = "ok" if not compile_failed and not execution_failed else "failed"
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality_script_count": len(scripts),
        "compiled_ok_count": len(scripts) - len(compile_failed),
        "compile_failed": compile_failed,
        "static_review_count": len(static_review),
        "static_review": static_review,
        "executed_count": len(executed),
        "execution_failed": execution_failed,
        "executed": executed,
        "items": items,
        "interpretation": "Compile and execution failures are blocking. Static review findings are advisory signals for scripts that may need stronger assertions.",
    }


def write_markdown(report: dict[str, object]) -> None:
    lines = [
        "# Level1 40.10 Quality Compile Guard",
        "",
        f"Generated: {report['generated_at']}",
        f"Status: **{report['status']}**",
        "",
        "## Summary",
        "",
        f"- Quality/check scripts discovered: {report['quality_script_count']}",
        f"- Compile OK: {report['compiled_ok_count']}",
        f"- Compile failed: {len(report['compile_failed'])}",
        f"- Recent scripts executed: {report['executed_count']}",
        f"- Execution failed: {len(report['execution_failed'])}",
        f"- Static review advisories: {report['static_review_count']}",
        "",
        "## Policy",
        "",
        "Quality scripts must compile, have active checks, and contain a failure path. Scripts that only print an OK marker without checking files, contracts, syntax, or endpoint state are flagged for review.",
        "",
    ]
    if report["compile_failed"]:
        lines.append("## Compile failures")
        lines.extend(f"- {item}" for item in report["compile_failed"])
        lines.append("")
    if report["execution_failed"]:
        lines.append("## Execution failures")
        lines.extend(f"- {item}" for item in report["execution_failed"])
        lines.append("")
    if report["static_review"]:
        lines.append("## Static review advisories")
        lines.extend(f"- {item}" for item in report["static_review"])
        lines.append("")
    MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    report = build_report()
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report)
    if report["status"] != "ok":
        print(json.dumps({
            "status": report["status"],
            "compile_failed": report["compile_failed"],
            "execution_failed": report["execution_failed"],
        }, indent=2, ensure_ascii=False))
        return 1
    print("LEVEL1_40_10_QUALITY_COMPILE_GUARD_OK")
    print(f"quality_script_count={report['quality_script_count']}")
    print(f"compiled_ok_count={report['compiled_ok_count']}")
    print(f"executed_count={report['executed_count']}")
    print(f"static_review_count={report['static_review_count']}")
    print("report=docs/LEVEL1_40_10_QUALITY_COMPILE_GUARD_REPORT.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
