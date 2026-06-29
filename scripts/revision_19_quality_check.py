#!/usr/bin/env python3
import importlib
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

FILES = [
    "backend/services/reports_service.py",
    "backend/services/revision_19_service.py",
    "backend/routes/quality_routes.py",
]


def main():
    for rel in FILES:
        py_compile.compile(str(ROOT / rel), doraise=True)
    main_mod = importlib.import_module("main")
    assert getattr(main_mod, "app", None) is not None, "FastAPI app import edilemedi"
    service = importlib.import_module("services.revision_19_service")
    report = service.build_revision_19_quality_report({}, {})
    assert report.get("revision") == 19, "Rev19 kalite raporu yanlış revision dönüyor"
    assert "checks" in report, "Rev19 checks eksik"
    print("REVISION_19_QUALITY_CHECK_OK")


if __name__ == "__main__":
    main()
