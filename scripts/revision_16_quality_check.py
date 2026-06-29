from __future__ import annotations

import compileall
import pathlib

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
        ("backend/services/revision_16_service.py", "build_revision_16_quality_report"),
        ("backend/routes/quality_routes.py", "/revision-16"),
        ("backend/routes/settings_routes.py", "/risk-preview"),
        ("backend/services/settings_unit_service.py", "worst_case_open_loss_usdt"),
        ("frontend/js/app/settings.js", "previewSettings"),
        ("frontend/js/pages/settings.js", "Risk Önizleme"),
        ("frontend/js/pages/intelligence.js", "Rev16 Unit Contract"),
        ("scripts/revision_16_quality_check.py", "REVISION_16_SETTINGS_RISK_OK"),
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
    print("REVISION_16_SETTINGS_RISK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
