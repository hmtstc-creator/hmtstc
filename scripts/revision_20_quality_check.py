from __future__ import annotations

import os
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HMTSTC_OFFLINE_QUALITY_CHECK", "1")
sys.path.insert(0, str(ROOT / "backend"))

REQUIRED_FILES = [
    "backend/services/real_position_lifecycle_service.py",
    "backend/services/revision_20_service.py",
    "backend/routes/real_routes.py",
    "frontend/js/pages/positions.js",
    "frontend/js/app/realTrade.js",
]


def assert_file(path: str) -> None:
    full = ROOT / path
    if not full.exists():
        raise AssertionError(f"missing file: {path}")


def compile_python() -> None:
    for file in (ROOT / "backend").rglob("*.py"):
        if "__pycache__" in file.parts:
            continue
        py_compile.compile(str(file), doraise=True)


def check_revision_20_report() -> None:
    from services.revision_20_service import build_revision_20_quality_report
    report = build_revision_20_quality_report({"positions": [], "real_trade": {}}, {})
    if report.get("revision") != 20:
        raise AssertionError("revision mismatch")
    checks = report.get("checks", {})
    for key in ["real_lifecycle", "reconciliation", "emergency_close_preview", "paper_real_separation", "ui_contract"]:
        if key not in checks:
            raise AssertionError(f"missing check: {key}")


def check_frontend_contract() -> None:
    positions = (ROOT / "frontend/js/pages/positions.js").read_text(encoding="utf-8")
    api = (ROOT / "frontend/js/app/api.js").read_text(encoding="utf-8")
    real_trade = (ROOT / "frontend/js/app/realTrade.js").read_text(encoding="utf-8")
    required_tokens = [
        "Real Lifecycle Status Matrix",
        "transitionRealPosition",
        "Emergency Close Preview",
        "Paper / Shadow Açık Pozisyonlar",
    ]
    for token in required_tokens:
        if token not in positions and token not in real_trade:
            raise AssertionError(f"missing frontend token: {token}")
    for token in ["/api/real/positions/lifecycle", "/api/quality/revision-20"]:
        if token not in api:
            raise AssertionError(f"missing api sync token: {token}")


def check_runtime_leakage() -> None:
    forbidden = [
        ROOT / "backend/.env",
        ROOT / "backend/auth_store.json",
        ROOT / "backend/settings_store.json",
        ROOT / "backend/shadow_store.json",
        ROOT / "backend/runtime_backups",
    ]
    leaked = [str(p.relative_to(ROOT)) for p in forbidden if p.exists()]
    if leaked:
        raise AssertionError("runtime leakage: " + ", ".join(leaked))


def main() -> None:
    for path in REQUIRED_FILES:
        assert_file(path)
    compile_python()
    check_revision_20_report()
    check_frontend_contract()
    check_runtime_leakage()
    print("REVISION_20_QUALITY_OK")


if __name__ == "__main__":
    main()
