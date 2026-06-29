#!/usr/bin/env python3
"""Level1 40.07 Frontend API endpoint inventory.

Scans frontend JavaScript modules for API references and writes a deterministic
inventory. The script is intentionally read-only and feeds the later API contract
comparison step.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_JS_DIR = ROOT / "frontend" / "js"
DOCS_DIR = ROOT / "docs"
REPORT_PATH = DOCS_DIR / "LEVEL1_40_07_FRONTEND_API_INVENTORY.json"
MARKDOWN_PATH = DOCS_DIR / "LEVEL1_40_07_FRONTEND_API_INVENTORY.md"

RUNTIME_FORBIDDEN = [
    ROOT / "backend" / ".env",
    ROOT / "backend" / "binance_credentials_store.json",
    ROOT / "backend" / "settings_store.json",
    ROOT / "backend" / "shadow_store.json",
    ROOT / "backend" / "auth_store.json",
    ROOT / "backend" / "rule_store.json",
    ROOT / "backend" / "audit_store.json",
    ROOT / "backend" / "real_trade_store.json",
    ROOT / "backend" / "runtime_backups",
]

CALL_START_RE = re.compile(r"\b(?P<name>fetchJson|fetch)\s*\(")
STRING_ENDPOINT_RE = re.compile(r"(?P<quote>[\"'`])(?P<path>/(?:api|health)[^\"'`]*?)(?P=quote)")
METHOD_RE = re.compile(r"method\s*:\s*[\"'](?P<method>[A-Z]+)[\"']")

# Very small false-positive allowlist for non-endpoint examples in docs embedded
# into JS strings, if they appear later.
IGNORED_PREFIXES = ("/api/placeholder",)


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _normalize_endpoint(raw: str) -> str:
    endpoint = raw.strip()
    # Convert simple template expressions into stable placeholders so later
    # contract diff can review them without losing the base route.
    endpoint = re.sub(r"\$\{[^}]+\}", "{dynamic}", endpoint)
    endpoint = endpoint.replace("&amp;", "&")
    endpoint = re.sub(r"/+\?", "?", endpoint)
    endpoint = re.sub(r"/+$", "", endpoint) if endpoint not in {"/", "/health"} else endpoint
    return endpoint


def _base_path(endpoint: str) -> str:
    return endpoint.split("?", 1)[0]


def _infer_method(context: str) -> str:
    match = METHOD_RE.search(context)
    return match.group("method") if match else "GET"


def _is_mutating(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _is_git_tracked(path: Path) -> bool:
    result = _run_git(["ls-files", "--", _relative(path)])
    return bool(result.stdout.strip())


def _is_git_ignored(path: Path) -> bool:
    result = _run_git(["check-ignore", "-q", "--", _relative(path)])
    return result.returncode == 0


def _runtime_policy() -> dict[str, list[str]]:
    tracked: list[str] = []
    unignored: list[str] = []
    allowed: list[str] = []

    for path in RUNTIME_FORBIDDEN:
        if not path.exists():
            continue
        rel = _relative(path)
        is_tracked = _is_git_tracked(path)
        is_ignored = _is_git_ignored(path)
        if is_tracked:
            tracked.append(rel)
        elif not is_ignored:
            unignored.append(rel)
        else:
            allowed.append(rel)

    return {
        "tracked_runtime_stores": sorted(tracked),
        "unignored_runtime_stores": sorted(unignored),
        "allowed_ignored_runtime_stores": sorted(allowed),
    }


def _find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _first_argument(call_text: str) -> str:
    open_index = call_text.find("(")
    if open_index < 0:
        return ""
    depth = 0
    quote: str | None = None
    escaped = False
    start = open_index + 1
    for index in range(start, len(call_text)):
        char = call_text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return call_text[start:index].strip()
            depth -= 1
        elif char == "," and depth == 0:
            return call_text[start:index].strip()
    return call_text[start:].strip()


def _string_literals(expression: str) -> list[tuple[int, int, str]]:
    literals: list[tuple[int, int, str]] = []
    index = 0
    while index < len(expression):
        quote = expression[index]
        if quote not in {"'", '"', "`"}:
            index += 1
            continue
        escaped = False
        value_chars: list[str] = []
        start = index
        index += 1
        while index < len(expression):
            char = expression[index]
            if escaped:
                value_chars.append(char)
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                literals.append((start, index + 1, "".join(value_chars)))
                index += 1
                break
            else:
                value_chars.append(char)
            index += 1
        else:
            break
    return literals


def _gap_has_dynamic(gap: str) -> bool:
    clean = gap.strip()
    if not clean:
        return False
    return "+" in clean or "encodeURIComponent" in clean or re.search(r"\b[A-Za-z_$][\w$]*\b", clean) is not None


def _endpoint_from_argument(expression: str) -> str | None:
    literals = _string_literals(expression)
    endpoint_parts: list[str] = []
    started = False
    last_end = 0

    for start, end, literal in literals:
        if not started:
            if not literal.startswith(("/api", "/health")):
                last_end = end
                continue
            endpoint_parts.append(literal)
            started = True
            last_end = end
            continue

        gap = expression[last_end:start]
        if _gap_has_dynamic(gap):
            endpoint_parts.append("{dynamic}")
        endpoint_parts.append(literal)
        last_end = end

    if not started:
        return None

    trailing = expression[last_end:]
    if _gap_has_dynamic(trailing):
        endpoint_parts.append("{dynamic}")

    endpoint = "".join(endpoint_parts)
    endpoint = re.sub(r"\{dynamic\}+", "{dynamic}", endpoint)
    endpoint = endpoint.replace("/{dynamic}/", "/{dynamic}/")
    return _normalize_endpoint(endpoint)


def _extract_endpoint_references(text: str, path: Path, call_spans: list[tuple[int, int]]) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    for match in STRING_ENDPOINT_RE.finditer(text):
        if any(start <= match.start() < end for start, end in call_spans):
            continue
        raw = match.group("path")
        if any(raw.startswith(prefix) for prefix in IGNORED_PREFIXES):
            continue
        references.append({
            "file": _relative(path),
            "line": _line_number(text, match.start()),
            "endpoint": _normalize_endpoint(raw),
            "base_path": _base_path(_normalize_endpoint(raw)),
            "source_kind": "reference_only",
        })
    return references


def _extract_calls(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str, str]] = set()

    for match in CALL_START_RE.finditer(text):
        open_index = text.find("(", match.start())
        close_index = _find_matching_paren(text, open_index)
        if close_index < 0:
            continue
        call_text = text[match.start():close_index + 1]
        arg = _first_argument(call_text)
        endpoint = _endpoint_from_argument(arg)
        if not endpoint or any(endpoint.startswith(prefix) for prefix in IGNORED_PREFIXES):
            continue
        start = match.start()
        line = _line_number(text, start)
        method = _infer_method(call_text)
        source_kind = match.group("name")
        key = (endpoint, line, _relative(path), method, source_kind)
        if key in seen:
            continue
        seen.add(key)
        entries.append({
            "file": _relative(path),
            "line": line,
            "method": method,
            "endpoint": endpoint,
            "base_path": _base_path(endpoint),
            "source_kind": source_kind,
            "mutating": _is_mutating(method),
        })

    return entries


def build_inventory() -> dict[str, Any]:
    if not FRONTEND_JS_DIR.exists():
        return {
            "status": "review",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": f"missing frontend js dir: {_relative(FRONTEND_JS_DIR)}",
            "calls": [],
        }

    js_files = sorted(FRONTEND_JS_DIR.rglob("*.js"))
    calls: list[dict[str, Any]] = []
    endpoint_references: list[dict[str, Any]] = []
    for js_file in js_files:
        calls.extend(_extract_calls(js_file))
        text = js_file.read_text(encoding="utf-8", errors="ignore")
        call_spans = []
        for match in CALL_START_RE.finditer(text):
            open_index = text.find("(", match.start())
            close_index = _find_matching_paren(text, open_index)
            if close_index >= 0:
                call_spans.append((match.start(), close_index + 1))
        endpoint_references.extend(_extract_endpoint_references(text, js_file, call_spans))

    calls = sorted(calls, key=lambda item: (item["file"], item["line"], item["method"], item["endpoint"]))
    endpoint_references = sorted(endpoint_references, key=lambda item: (item["file"], item["line"], item["endpoint"]))
    base_counter: Counter[str] = Counter(call["base_path"] for call in calls)
    method_counter: Counter[str] = Counter(call["method"] for call in calls)
    file_counter: Counter[str] = Counter(call["file"] for call in calls)
    mutating_calls = [call for call in calls if call["mutating"]]
    dynamic_calls = [call for call in calls if "{dynamic}" in call["endpoint"]]
    unique_endpoints = sorted({call["endpoint"] for call in calls})
    unique_base_paths = sorted({call["base_path"] for call in calls})
    required_base_paths = ["/api/dashboard/bundle", "/api/settings", "/api/auth/me", "/api/real/readiness"]
    missing_expected = [endpoint for endpoint in required_base_paths if endpoint not in unique_base_paths]
    runtime_policy = _runtime_policy()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        grouped[call["base_path"]].append(call)

    inventory: dict[str, Any] = {
        "status": "ok" if not missing_expected and not runtime_policy["tracked_runtime_stores"] and not runtime_policy["unignored_runtime_stores"] else "review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "frontend_js_file_count": len(js_files),
        "call_count": len(calls),
        "unique_endpoint_count": len(unique_endpoints),
        "unique_base_path_count": len(unique_base_paths),
        "method_count": dict(sorted(method_counter.items())),
        "file_count": dict(sorted(file_counter.items())),
        "top_base_paths": dict(base_counter.most_common(30)),
        "required_base_paths": required_base_paths,
        "missing_required_base_paths": missing_expected,
        "runtime_policy": runtime_policy,
        "runtime_leaks": runtime_policy["tracked_runtime_stores"],
        "mutating_call_count": len(mutating_calls),
        "dynamic_call_count": len(dynamic_calls),
        "endpoint_reference_count": len(endpoint_references),
        "unique_endpoints": unique_endpoints,
        "unique_base_paths": unique_base_paths,
        "calls_by_base_path": {key: grouped[key] for key in sorted(grouped)},
        "calls": calls,
        "endpoint_references": endpoint_references,
    }
    return inventory


def write_markdown(inventory: dict[str, Any], path: Path = MARKDOWN_PATH) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.07 Frontend API Inventory")
    lines.append("")
    lines.append("Bu rapor, frontend JavaScript dosyalarındaki API çağrılarını statik olarak çıkarır.")
    lines.append("Sonraki `API contract diff` adımı için frontend tarafı referans setidir.")
    lines.append("")
    lines.append(f"- Status: `{inventory.get('status')}`")
    lines.append(f"- Generated at: `{inventory.get('generated_at')}`")
    lines.append(f"- Frontend JS file count: `{inventory.get('frontend_js_file_count', 0)}`")
    lines.append(f"- API call count: `{inventory.get('call_count', 0)}`")
    lines.append(f"- Unique endpoint count: `{inventory.get('unique_endpoint_count', 0)}`")
    lines.append(f"- Unique base path count: `{inventory.get('unique_base_path_count', 0)}`")
    lines.append(f"- Mutating call count: `{inventory.get('mutating_call_count', 0)}`")
    lines.append(f"- Dynamic call count: `{inventory.get('dynamic_call_count', 0)}`")
    lines.append(f"- Endpoint reference count: `{inventory.get('endpoint_reference_count', 0)}`")
    lines.append("")
    lines.append("## Required base paths")
    lines.append("")
    missing = set(inventory.get("missing_required_base_paths", []))
    for required in inventory.get("required_base_paths", []):
        marker = "MISSING" if required in missing else "OK"
        lines.append(f"- `{required}` — {marker}")
    lines.append("")
    lines.append("## Method count")
    lines.append("")
    for method, count in inventory.get("method_count", {}).items():
        lines.append(f"- `{method}`: {count}")
    lines.append("")
    lines.append("## Top base paths")
    lines.append("")
    for base_path, count in inventory.get("top_base_paths", {}).items():
        lines.append(f"- `{base_path}`: {count}")
    lines.append("")
    lines.append("## Runtime store policy")
    lines.append("")
    runtime_policy = inventory.get("runtime_policy", {})
    lines.append(f"- Tracked runtime stores: `{len(runtime_policy.get('tracked_runtime_stores', []))}`")
    lines.append(f"- Unignored runtime stores: `{len(runtime_policy.get('unignored_runtime_stores', []))}`")
    lines.append(f"- Allowed ignored runtime stores: `{len(runtime_policy.get('allowed_ignored_runtime_stores', []))}`")
    lines.append("")
    lines.append("## Calls")
    lines.append("")
    lines.append("| Method | Endpoint | File | Line | Kind |")
    lines.append("|---|---|---|---:|---|")
    for call in inventory.get("calls", []):
        lines.append(f"| {call['method']} | `{call['endpoint']}` | `{call['file']}` | {call['line']} | {call['source_kind']} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build frontend API endpoint inventory for HMTSTC.")
    parser.add_argument("--json", dest="json_path", default=str(REPORT_PATH), help="JSON output path.")
    parser.add_argument("--markdown", dest="markdown_path", default=str(MARKDOWN_PATH), help="Markdown output path.")
    args = parser.parse_args(argv)

    inventory = build_inventory()
    json_path = Path(args.json_path)
    if not json_path.is_absolute():
        json_path = ROOT / json_path
    markdown_path = Path(args.markdown_path)
    if not markdown_path.is_absolute():
        markdown_path = ROOT / markdown_path

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(inventory, markdown_path)

    if inventory.get("status") != "ok":
        print(json.dumps({
            "status": inventory.get("status"),
            "missing_required_base_paths": inventory.get("missing_required_base_paths", []),
            "runtime_policy": inventory.get("runtime_policy", {}),
        }, indent=2, ensure_ascii=False))
        return 1

    print("LEVEL1_40_07_FRONTEND_API_INVENTORY_OK")
    print(f"frontend_js_file_count={inventory['frontend_js_file_count']}")
    print(f"call_count={inventory['call_count']}")
    print(f"unique_base_path_count={inventory['unique_base_path_count']}")
    print(f"json={json_path.relative_to(ROOT) if json_path.is_relative_to(ROOT) else json_path}")
    print(f"markdown={markdown_path.relative_to(ROOT) if markdown_path.is_relative_to(ROOT) else markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
