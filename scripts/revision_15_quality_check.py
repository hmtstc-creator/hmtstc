from __future__ import annotations

import compileall
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def assert_file(path: str, needle: str | None = None) -> None:
    full = ROOT / path
    if not full.exists():
        raise AssertionError(f"missing file: {path}")
    if needle and needle not in full.read_text(encoding="utf-8"):
        raise AssertionError(f"missing marker in {path}: {needle}")


def main() -> int:
    if not compileall.compile_dir(str(ROOT / "backend"), quiet=1):
        raise AssertionError("python compile failed")
    checks = [
        ("frontend/js/app/api.js", "/api/quality/revision-15"),
        ("frontend/js/app/realTrade.js", "previewRealOrder"),
        ("frontend/js/pages/dashboard.js", "real-trade-panel-v15"),
        ("frontend/js/pages/positions.js", "positions-v15"),
        ("backend/routes/quality_routes.py", "/revision-15"),
        ("backend/services/revision_15_service.py", "build_revision_15_quality_report"),
    ]
    for path, marker in checks:
        assert_file(path, marker)
    forbidden = [
        "backend/.env",
        "backend/settings_store.json",
        "backend/shadow_store.json",
        "backend/auth_store.json",
        "backend/rule_store.json",
    ]
    leaked = [p for p in forbidden if (ROOT / p).exists()]
    if leaked:
        raise AssertionError(f"runtime files leaked: {leaked}")
    print("REVISION_15_REAL_REMEDIATION_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
