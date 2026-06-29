from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
REVISION_RANGE = "976-980"
PACKAGE_NAME = "Local-to-GitHub-to-VPS Sync Block"

REQUIRED_ROOT_ITEMS = [
    "README.md",
    "package.json",
    "pytest.ini",
    ".gitignore",
    "backend/main.py",
    "backend/.env.example",
    "frontend/index.html",
    "deploy/deploy.sh",
    "deploy/hmtstc-backend.service",
    "deploy/nginx.conf",
    "scripts/build_release_zip.py",
    "scripts/level1_49_commit_safe_scan.py",
]

REQUIRED_DIRECTORIES = ["backend", "backend/routes", "backend/services", "frontend", "frontend/js", "scripts", "tests", "docs", "deploy"]

FORBIDDEN_COMMIT_EXACT = {
    "backend/.env",
    "backend/auth_store.json",
    "backend/settings_store.json",
    "backend/shadow_store.json",
    "backend/rule_store.json",
    "backend/audit_store.json",
    "backend/real_trade_store.json",
}
FORBIDDEN_PREFIXES = {".git/", "node_modules/", ".pytest_cache/", "__pycache__/", "backend/runtime_backups/"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".sqlite", ".db", ".log", ".tmp"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?secret|secret[_-]?key|private[_-]?key)\s*[:=]\s*['\"][A-Za-z0-9_./+=-]{24,}['\"]"),
    re.compile(r"(?i)binance[_-]?api[_-]?secret\s*[:=]\s*['\"][A-Za-z0-9_./+=-]{24,}['\"]"),
]
TEXT_SUFFIXES = {".py", ".js", ".html", ".css", ".md", ".json", ".yml", ".yaml", ".txt", ".sh", ".ini", ".toml", ".example"}

GITHUB_ALLOWED_TOP_LEVEL = {"backend", "frontend", "scripts", "tests", "docs", "deploy", "ops"}
GITHUB_ALLOWED_FILES = {"README.md", "LIVE_SHADOW_CHECKLIST.md", "package.json", "pytest.ini", "jest.config.cjs", "playwright.config.ts", "webhook_server.py", "hmtstc-developer.agent.md", ".gitignore"}

VPS_REQUIRED_DEPLOY_FILES = ["deploy/deploy.sh", "deploy/hmtstc-backend.service", "deploy/nginx.conf", "backend/.env.example", "backend/requirements.txt"]
VPS_RUNTIME_ONLY_FILES = sorted(FORBIDDEN_COMMIT_EXACT | {"backend/runtime_backups/"})


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_source_files(root: Path = ROOT_DIR) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_norm = norm(rel)
        parts = set(rel.parts)
        if parts & {".git", "node_modules", ".pytest_cache", "__pycache__", "venv", ".venv"}:
            continue
        if rel_norm in FORBIDDEN_COMMIT_EXACT or rel_norm.startswith("backend/runtime_backups/"):
            continue
        files.append(path)
    return files


def path_is_forbidden(rel: str) -> bool:
    rel = norm(rel).rstrip("/")
    if rel in FORBIDDEN_COMMIT_EXACT:
        return True
    if any(rel.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
        return True
    return any(rel.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES)


def scan_secret_literals(root: Path = ROOT_DIR) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in iter_source_files(root):
        rel = norm(path.relative_to(root))
        if path.suffix.lower() not in TEXT_SUFFIXES and ".env.example" not in rel:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line_no, line in enumerate(content.splitlines(), 1):
            if "os.getenv" in line or "process.env" in line or rel.endswith(".env.example"):
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append({"file": rel, "line": line_no, "pattern": pattern.pattern})
    return findings


def build_rev976_local_structure_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    missing = [item for item in REQUIRED_ROOT_ITEMS if not (root / item).exists()]
    missing_dirs = [item for item in REQUIRED_DIRECTORIES if not (root / item).is_dir()]
    nested_roots = [norm(p.relative_to(root)) for p in root.rglob("hmtstc_revizyon_*.zip")]
    return {
        "revision": 976,
        "status": "ok" if not missing and not missing_dirs and not nested_roots else "blocked",
        "purpose": "final_zip_to_local_vscode_structure_control",
        "required_items": REQUIRED_ROOT_ITEMS,
        "missing_items": missing,
        "missing_directories": missing_dirs,
        "nested_release_artifacts_in_source": nested_roots,
        "local_copy_rule": "Unzip contents directly into the project root; do not keep zip files inside the repo tree.",
    }


def parse_gitignore(root: Path = ROOT_DIR) -> dict[str, Any]:
    path = root / ".gitignore"
    content = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    required_patterns = [
        "backend/.env",
        "backend/auth_store.json",
        "backend/settings_store.json",
        "backend/shadow_store.json",
        "backend/real_trade_store.json",
        "backend/runtime_backups/",
        "node_modules/",
        ".pytest_cache/",
        "*.log",
        "*.sqlite",
        "*.db",
        "*.pem",
        "*.key",
    ]
    missing = [pattern for pattern in required_patterns if pattern not in content]
    return {"exists": path.exists(), "required_patterns": required_patterns, "missing_patterns": missing}


def build_rev977_gitignore_secret_runtime_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    gitignore = parse_gitignore(root)
    files = [norm(path.relative_to(root)) for path in iter_source_files(root)]
    forbidden_hits = sorted({rel for rel in files if path_is_forbidden(rel)})
    secret_hits = scan_secret_literals(root)
    blockers = []
    if not gitignore["exists"]:
        blockers.append("missing_gitignore")
    if gitignore["missing_patterns"]:
        blockers.append("gitignore_missing_runtime_or_secret_patterns")
    if forbidden_hits:
        blockers.append("forbidden_runtime_or_secret_files_present")
    if secret_hits:
        blockers.append("literal_secret_findings")
    return {
        "revision": 977,
        "status": "ok" if not blockers else "blocked",
        "purpose": "gitignore_secret_runtime_cache_control",
        "gitignore": gitignore,
        "forbidden_hits": forbidden_hits,
        "secret_findings": secret_hits,
        "blockers": blockers,
        "policy": {
            "runtime_files_are_vps_only": True,
            "env_example_allowed": True,
            "api_key_secret_must_never_be_committed": True,
            "frontend_and_logs_must_not_echo_secret_values": True,
        },
    }


def build_rev978_github_commit_push_safe_list(root: Path = ROOT_DIR) -> dict[str, Any]:
    source_files = [norm(path.relative_to(root)) for path in iter_source_files(root)]
    allowed: list[str] = []
    blocked: list[str] = []
    review: list[str] = []
    for rel in source_files:
        top = rel.split("/", 1)[0]
        if path_is_forbidden(rel):
            blocked.append(rel)
        elif rel in GITHUB_ALLOWED_FILES or top in GITHUB_ALLOWED_TOP_LEVEL:
            allowed.append(rel)
        else:
            review.append(rel)
    return {
        "revision": 978,
        "status": "ok" if not blocked else "blocked",
        "purpose": "github_commit_push_safe_file_list",
        "allowed_count": len(allowed),
        "blocked_count": len(blocked),
        "review_count": len(review),
        "allowed_prefixes": sorted(GITHUB_ALLOWED_TOP_LEVEL),
        "allowed_root_files": sorted(GITHUB_ALLOWED_FILES),
        "blocked_files": sorted(blocked),
        "review_files": sorted(review),
        "recommended_commands": [
            "git status --short",
            "git add .",
            "git status --short",
            "git commit -m \"Rev980 local github vps sync block\"",
            "git push origin main",
        ],
        "pre_push_gate": "Run python3 scripts/rev976_980_local_github_vps_sync_check.py before commit/push.",
    }


def build_rev979_vps_pull_deploy_match_check(root: Path = ROOT_DIR) -> dict[str, Any]:
    missing = [item for item in VPS_REQUIRED_DEPLOY_FILES if not (root / item).exists()]
    checksum_manifest = []
    for rel in VPS_REQUIRED_DEPLOY_FILES:
        path = root / rel
        entry = {"path": rel, "exists": path.exists()}
        if path.exists() and path.is_file():
            entry["sha256"] = sha256_file(path)
            entry["size_bytes"] = path.stat().st_size
        checksum_manifest.append(entry)
    return {
        "revision": 979,
        "status": "ok" if not missing else "blocked",
        "purpose": "vps_pull_deploy_file_match_control",
        "required_deploy_files": VPS_REQUIRED_DEPLOY_FILES,
        "missing_deploy_files": missing,
        "checksum_manifest": checksum_manifest,
        "vps_runtime_only_files": VPS_RUNTIME_ONLY_FILES,
        "safe_vps_sequence": [
            "git pull origin main",
            "python3 scripts/rev976_980_local_github_vps_sync_check.py",
            "python3 scripts/level1_40_05_runtime_leak_guard.py",
            "python3 scripts/level1_55_post_deploy_smoke_final.py --offline",
            "systemctl restart hmtstc-backend",
            "systemctl status hmtstc-backend --no-pager",
        ],
        "rule": "VPS runtime stores stay on VPS; GitHub carries code/templates only.",
    }


def build_local_github_vps_sync_report(root: Path = ROOT_DIR) -> dict[str, Any]:
    blocks = {
        "rev976_local_structure": build_rev976_local_structure_check(root),
        "rev977_gitignore_secret_runtime": build_rev977_gitignore_secret_runtime_check(root),
        "rev978_github_commit_push": build_rev978_github_commit_push_safe_list(root),
        "rev979_vps_pull_deploy_match": build_rev979_vps_pull_deploy_match_check(root),
    }
    blockers = [name for name, payload in blocks.items() if payload.get("status") == "blocked"]
    return {
        "revision": 980,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "status": "ok" if not blockers else "blocked",
        "generated_at": now_iso(),
        "blocks": blocks,
        "blockers": blockers,
        "final_decision": "SYNC_READY" if not blockers else "SYNC_BLOCKED",
        "non_goals": [
            "No live Binance order submission.",
            "No secret or runtime store export.",
            "No automatic VPS mutation from this report.",
        ],
    }


def write_sync_reports(root: Path = ROOT_DIR) -> dict[str, Path]:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    report = build_local_github_vps_sync_report(root)
    json_path = docs / "HMTSTC_Rev976_980_Local_GitHub_VPS_Sync_Report.json"
    md_path = docs / "HMTSTC_Rev976_980_Local_GitHub_VPS_Sync_Report.md"
    completion_path = docs / "HMTSTC_Rev976_980_Completion_Report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    completion_path.write_text(json.dumps({"status": report["status"], "revision": 980, "final_decision": report["final_decision"], "blockers": report["blockers"], "generated_at": report["generated_at"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# HMTSTC Rev976-980 Local-to-GitHub-to-VPS Sync Report",
        "",
        f"- Status: **{report['status']}**",
        f"- Final decision: **{report['final_decision']}**",
        f"- Generated at: `{report['generated_at']}`",
        "",
        "## Revision Results",
    ]
    for key, block in report["blocks"].items():
        lines.extend([f"- **{block['revision']} / {key}**: `{block['status']}`"])
    lines.extend([
        "",
        "## Commit/Deploy Guardrails",
        "- Commit code, docs, tests and deploy templates only.",
        "- Keep `.env`, runtime stores, backups, DB files and logs outside Git.",
        "- VPS must keep runtime data local; GitHub must remain source-only.",
        "- Real Binance submit/close remains default OFF.",
    ])
    if report["blockers"]:
        lines.extend(["", "## Blockers", *[f"- {item}" for item in report["blockers"]]])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "md": md_path, "completion": completion_path}
