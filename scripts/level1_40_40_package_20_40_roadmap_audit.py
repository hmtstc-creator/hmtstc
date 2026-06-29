#!/usr/bin/env python3
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "d4f06c7"
HEAD_COMMIT = "3bd86ec"

EXPECTED_BLACKBOX_DIFF = {
    "blackbox2.md",
    "blackbox2_full.txt",
    "docs/LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT.json",
    "docs/LEVEL1_40_33_COINFILTER_FINAL_PIPELINE_AUDIT.md",
    "docs/LEVEL1_40_39_1_PERSIST_COINFILTER_COUNTERS_AUDIT.json",
    "docs/LEVEL1_40_39_2_COINFILTER_SINGLE_SOURCE_HYDRATION_AUDIT.json",
    "docs/LEVEL1_40_39_SAFE_COINFILTER_SCAN_AND_COUNTERS_AUDIT.json",
    "frontend/js/pages/dashboard.js",
}

MISSING_BLACKBOX_54_ARTIFACTS = {
    "scripts/level1_40_39_4_coinfilter_final_pipeline_contract_audit.py",
    "docs/LEVEL1_40_39_4_COINFILTER_FINAL_PIPELINE_CONTRACT_AUDIT.json",
    "docs/LEVEL1_40_39_4_COINFILTER_FINAL_PIPELINE_CONTRACT_AUDIT.md",
}

PYTHON_SYNTAX_FILES = (
    "backend/core/config.py",
    "backend/core/storage.py",
    "backend/routes/bot_routes.py",
    "backend/routes/dashboard_routes.py",
    "backend/services/analysis_service.py",
    "backend/services/coin_universe_service.py",
)

JAVASCRIPT_SYNTAX_FILES = (
    "frontend/js/pages/coinFilter.js",
    "frontend/js/pages/dashboard.js",
    "frontend/js/app/api.js",
)

AUDIT_SCRIPTS = (
    "scripts/level1_40_39_1_persist_coinfilter_counters_audit.py",
    "scripts/level1_40_39_2_coinfilter_single_source_hydration_audit.py",
    "scripts/level1_40_39_3_coinfilter_settings_contract_audit.py",
    "scripts/level1_40_39_safe_coinfilter_scan_and_counters_audit.py",
)

PACKAGE_SCOPE = {
    ".gitignore",
    "docs/HMTSTC10_CODE_INSPECTION_REPORT.md",
    "scripts/level1_40_40_package_20_40_roadmap_audit.py",
}

SENSITIVE_EXACT_NAMES = {
    ".env",
    "auth_store.json",
    "settings_store.json",
    "shadow_store.json",
    "rule_store.json",
    "paper_lab_store.json",
    "eight_hour_report_store.json",
    "audit_store.json",
    "real_trade_store.json",
    "binance_credentials_store.json",
}


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def git_lines(*args: str) -> list[str]:
    result = run(["git", *args])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_sensitive(path_text: str) -> bool:
    path = Path(path_text.replace("\\", "/"))
    name = path.name.lower()
    if name.endswith(".example.json") or name == ".env.example":
        return False
    return (
        name in SENSITIVE_EXACT_NAMES
        or name.endswith("_store.runtime.json")
        or (name.startswith(".env.") and name != ".env.example")
        or "runtime_backups" in {part.lower() for part in path.parts}
        or ("_backup_" in name and name.endswith(".json"))
    )


def check_git_baseline() -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    head = run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
    if not head.startswith(HEAD_COMMIT):
        failures.append(f"unexpected HEAD: {head}, expected {HEAD_COMMIT}")

    diff_files = set(git_lines("diff", "--name-only", BASE_COMMIT, HEAD_COMMIT))
    if diff_files != EXPECTED_BLACKBOX_DIFF:
        missing = sorted(EXPECTED_BLACKBOX_DIFF - diff_files)
        extra = sorted(diff_files - EXPECTED_BLACKBOX_DIFF)
        failures.append(f"unexpected {BASE_COMMIT}..{HEAD_COMMIT} diff: missing={missing}, extra={extra}")

    present_54 = sorted(path for path in MISSING_BLACKBOX_54_ARTIFACTS if (ROOT / path).exists())
    if present_54:
        failures.append(f"untrusted Blackbox 5.4 artifacts unexpectedly present: {present_54}")
    else:
        notes.append("Blackbox 5.4 script/report artifacts are absent and remain untrusted")
    return failures, notes


def check_repository_safety() -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    tracked = git_lines("ls-files")
    staged = git_lines("diff", "--cached", "--name-only")
    tracked_leaks = sorted(path for path in tracked if is_sensitive(path))
    staged_leaks = sorted(path for path in staged if is_sensitive(path))
    if tracked_leaks:
        failures.append(f"tracked runtime/secret files: {tracked_leaks}")
    if staged_leaks:
        failures.append(f"staged runtime/secret files: {staged_leaks}")

    ignore_probes = (
        "backend/.env",
        "backend/auth_store.json",
        "backend/paper_lab_store.json.temporary",
        "backend/runtime_backups/probe.json",
        "backend/state_backup_20260615.json",
    )
    ignored = set(git_lines("check-ignore", "--no-index", *ignore_probes))
    missing_ignores = sorted(set(ignore_probes) - ignored)
    if missing_ignores:
        failures.append(f"runtime ignore probes not covered: {missing_ignores}")

    status_paths = []
    status_output = run(["git", "status", "--porcelain"]).stdout
    for line in status_output.splitlines():
        if len(line) < 4:
            continue
        raw_path = line[3:].strip()
        status_paths.append(raw_path.split(" -> ")[-1])
    unrelated = sorted(path for path in status_paths if path not in PACKAGE_SCOPE)
    if unrelated:
        notes.append(f"pre-existing out-of-scope working tree changes preserved: {unrelated}")
    if staged:
        notes.append(f"staged files present: {staged}")
    return failures, notes


def check_syntax() -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    for relative in PYTHON_SYNTAX_FILES:
        path = ROOT / relative
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        except (OSError, SyntaxError, UnicodeError) as exc:
            failures.append(f"python syntax failed for {relative}: {exc}")

    node = shutil.which("node")
    if not node:
        notes.append("node executable not found; JS files are unchanged from the recorded syntax-clean baseline")
        return failures, notes
    for relative in JAVASCRIPT_SYNTAX_FILES:
        result = run([node, "--check", relative], check=False)
        if result.returncode:
            failures.append(f"javascript syntax failed for {relative}: {result.stderr.strip()}")
    return failures, notes


def check_existing_audits() -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    wrapper = (
        "import runpy,sys; "
        "from pathlib import Path; "
        "Path.write_text=lambda self,*args,**kwargs: len(args[0]) if args else 0; "
        "sys.argv=[sys.argv[1]]; "
        "runpy.run_path(sys.argv[0],run_name='__main__')"
    )
    for relative in AUDIT_SCRIPTS:
        result = run([sys.executable, "-c", wrapper, relative], check=False)
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.returncode:
            failures.append(f"{relative} failed:\n{output}")
        else:
            marker = next((line for line in result.stdout.splitlines() if line.endswith("_OK")), "OK")
            notes.append(f"{relative}: {marker}")
    return failures, notes


def main() -> int:
    failures: list[str] = []
    notes: list[str] = []

    for checker in (check_git_baseline, check_repository_safety):
        check_failures, check_notes = checker()
        failures.extend(check_failures)
        notes.extend(check_notes)
    syntax_failures, syntax_notes = check_syntax()
    failures.extend(syntax_failures)
    notes.extend(syntax_notes)
    audit_failures, audit_notes = check_existing_audits()
    failures.extend(audit_failures)
    notes.extend(audit_notes)

    if failures:
        print("LEVEL1_40_40_PACKAGE_20_BASELINE_FREEZE_AUDIT_FAIL")
        for failure in failures:
            print(f"FAIL: {failure}")
        for note in notes:
            print(f"NOTE: {note}")
        return 1

    print("LEVEL1_40_40_PACKAGE_20_BASELINE_FREEZE_AUDIT_OK")
    print("status=ok")
    print(f"head={HEAD_COMMIT}")
    print(f"base={BASE_COMMIT}")
    print("tracked_runtime_leaks=0")
    print("staged_runtime_leaks=0")
    print(f"python_syntax_files={len(PYTHON_SYNTAX_FILES)}")
    print(f"javascript_syntax_files={len(JAVASCRIPT_SYNTAX_FILES)}")
    print(f"existing_39x_audits={len(AUDIT_SCRIPTS)}")
    for note in notes:
        print(f"NOTE: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
