#!/usr/bin/env python3
"""Level1 40.05 runtime leak guard.

Checks that release/source packages do not include live runtime files such as
.env, *_store.json state files, real trade state, or runtime backups.

Usage:
  python scripts/level1_40_05_runtime_leak_guard.py
  python scripts/level1_40_05_runtime_leak_guard.py --zip /path/release.zip
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
REPORT_PATH = DOCS_DIR / "LEVEL1_40_05_RUNTIME_LEAK_REPORT.json"

FORBIDDEN_EXACT = {
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
}
FORBIDDEN_DIR_PREFIXES = {
    "backend/runtime_backups/",
}
FORBIDDEN_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
}
ALLOWED_EXACT = {
    "backend/.env.example",
    "backend/settings_store.example.json",
    "backend/shadow_store.example.json",
    "backend/rule_store.example.json",
}
SKIP_DIR_PREFIXES = {
    ".git/",
    ".pytest_cache/",
    "__pycache__/",
}


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _source_entries(root: Path) -> list[str]:
    entries: list[str] = []
    for path in root.rglob("*"):
        rel = _normalize(str(path.relative_to(root)))
        if any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in SKIP_DIR_PREFIXES):
            continue
        if path.is_dir():
            rel = rel.rstrip("/") + "/"
        entries.append(rel)
    return sorted(entries)


def _zip_entries(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path, "r") as archive:
        return sorted(_normalize(info.filename) for info in archive.infolist())


def _find_leaks(entries: Iterable[str]) -> list[str]:
    leaks: list[str] = []
    for entry in entries:
        normalized = _normalize(entry)
        if normalized in ALLOWED_EXACT:
            continue
        if normalized in FORBIDDEN_EXACT:
            leaks.append(normalized)
            continue
        if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in FORBIDDEN_DIR_PREFIXES):
            leaks.append(normalized)
            continue
        if any(normalized.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            leaks.append(normalized)
    return sorted(set(leaks))


def run_check(zip_path: str | None = None) -> dict[str, object]:
    target_type = "source_tree"
    target = str(ROOT)
    if zip_path:
        target_type = "zip"
        target = str(Path(zip_path).resolve())
        entries = _zip_entries(Path(zip_path))
    else:
        entries = _source_entries(ROOT)

    leaks = _find_leaks(entries)
    result: dict[str, object] = {
        "status": "ok" if not leaks else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "target_type": target_type,
        "target": target,
        "entry_count": len(entries),
        "forbidden_exact": sorted(FORBIDDEN_EXACT),
        "forbidden_dir_prefixes": sorted(FORBIDDEN_DIR_PREFIXES),
        "allowed_examples": sorted(ALLOWED_EXACT),
        "leaks": leaks,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect runtime/secrets leaks in HMTSTC release packages.")
    parser.add_argument("--zip", dest="zip_path", default=None, help="Optional release zip to inspect.")
    parser.add_argument("--report", dest="report_path", default=str(REPORT_PATH), help="JSON report output path.")
    args = parser.parse_args(argv)

    result = run_check(args.zip_path)
    report_path = Path(args.report_path)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if result["status"] != "ok":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    print("LEVEL1_40_05_RUNTIME_LEAK_GUARD_OK")
    print(f"target_type={result['target_type']}")
    print(f"entry_count={result['entry_count']}")
    print(f"report={report_path.relative_to(ROOT) if report_path.is_relative_to(ROOT) else report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
