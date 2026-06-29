from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "backend/services/summary_service.py",
    "backend/routes/summary_routes.py",
    "frontend/js/pages/summary.js",
    "scripts/revision_38_summary_quality_check.py",
]
FORBIDDEN_PATTERNS = [
    r"onclick=",
    r"<button",
    r"<select",
    r"<input",
    r"<textarea",
    r"POST\s+/api",
    r"approve",
    r"reject",
    r"unlock",
    r"place",
    r"start",
    r"stop",
    r"reset",
    r"emergencyStop",
    r"confirm",
]
RUNTIME_PATTERNS = [
    "backend/.env",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/auth_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
]


def read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def fail(message: str) -> None:
    print(f"SUMMARY_QUALITY_FAIL: {message}")
    sys.exit(1)


def main() -> None:
    missing = [rel for rel in REQUIRED_FILES if not (ROOT / rel).exists()]
    if missing:
        fail("missing files: " + ", ".join(missing))

    summary_js = read("frontend/js/pages/summary.js")
    index_html = read("frontend/index.html")
    data_js = read("frontend/js/data.js")
    render_js = read("frontend/js/app/render.js")
    api_js = read("frontend/js/app/api.js")
    main_py = read("backend/main.py")
    route_py = read("backend/routes/summary_routes.py")

    if "window.HMTSTC_PAGES.summary" not in summary_js:
        fail("summary page registration missing")
    if "./js/pages/summary.js" not in index_html:
        fail("summary script missing in index.html")
    if '["summary", "Summary"]' not in data_js:
        fail("summary menu item missing")
    if '"summary", "dashboard"' not in render_js:
        fail("summary missing from main page group before dashboard")
    if "/api/summary" not in api_js:
        fail("api sync missing /api/summary")
    if "summary_router" not in main_py:
        fail("summary router missing in main.py")
    if '@router.get("/summary")' not in route_py:
        fail("/api/summary must be GET-only")

    lowered = summary_js.lower()
    violations = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern.lower(), lowered):
            violations.append(pattern)
    if violations:
        fail("summary page contains action patterns: " + ", ".join(violations))

    try:
        ast.parse(read("backend/services/summary_service.py"))
        ast.parse(route_py)
    except SyntaxError as error:
        fail(f"python syntax error: {error}")

    leaks = [rel for rel in RUNTIME_PATTERNS if (ROOT / rel).exists()]
    if leaks:
        fail("runtime files present in package: " + ", ".join(leaks))

    print("SUMMARY_QUALITY_OK")


if __name__ == "__main__":
    main()
