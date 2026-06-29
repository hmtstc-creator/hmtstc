from __future__ import annotations

import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "backend/services/revision_17_service.py",
    "backend/routes/audit_routes.py",
    "backend/routes/quality_routes.py",
    "frontend/js/pages/logs.js",
    "frontend/js/app/audit.js",
]
FORBIDDEN = [
    "backend/.env",
    "backend/auth_store.json",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/runtime_backups",
]
REQUIRED_SNIPPETS = {
    "backend/routes/quality_routes.py": ["/revision-17", "build_revision_17_quality_report"],
    "backend/routes/audit_routes.py": ["/summary", "/security-trading", "export_audit"],
    "frontend/js/pages/logs.js": ["Audit & Forensic Control Center", "audit-filter-grid", "Before / After / Meta"],
    "frontend/js/app/audit.js": ["exportAuditTrail: async function (format)", "URLSearchParams"],
}


def fail(message: str) -> None:
    print(f"ERR {message}")
    raise SystemExit(1)


def main() -> None:
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            fail(f"missing required file: {rel}")
    for rel in FORBIDDEN:
        if (ROOT / rel).exists():
            fail(f"runtime file leaked: {rel}")
    for py in (ROOT / "backend").rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        py_compile.compile(str(py), doraise=True)
    for rel, snippets in REQUIRED_SNIPPETS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in text:
                fail(f"missing snippet in {rel}: {snippet}")
    print("REVISION_17_QUALITY_OK")


if __name__ == "__main__":
    main()
