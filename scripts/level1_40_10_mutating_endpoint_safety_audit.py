#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_INVENTORY_PATH = ROOT / "docs" / "LEVEL1_40_07_FRONTEND_API_INVENTORY.json"
CONTRACT_DIFF_PATH = ROOT / "docs" / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT.md"

RUNTIME_STORE_BLOCKLIST = {
    "backend/binance_credentials_store.json",
    "backend/settings_store.json",
    "backend/shadow_store.json",
}

CATEGORIES: dict[str, tuple[str, ...]] = {
    "CRITICAL_REAL_TRADE": (
        "/api/real/orders/place",
        "/api/real/positions/emergency-close",
        "/api/real/positions/transition",
        "/api/real/pilot/start",
        "/api/real/pilot/stop",
        "/api/real/unlock",
        "/api/real/lock",
        "/api/real/emergency/lock",
        "/api/real/emergency/recovery-unlock",
    ),
    "HIGH_BOT_CONTROL": (
        "/api/bot/start",
        "/api/bot/stop",
        "/api/bot/emergency-stop",
        "/api/bot/reset",
    ),
    "HIGH_USER_SECRET_OR_PERMISSION": (
        "/api/users/me/api-connection",
        "/api/users",
        "/api/users/{dynamic}/active",
        "/api/users/{dynamic}/reset-password",
    ),
    "MEDIUM_SETTINGS_RISK_RULES": (
        "/api/settings",
        "/api/settings/coin-filter",
        "/api/settings/risk-preview",
        "/api/settings/risk-impact",
        "/api/settings/rollback-preview",
        "/api/settings/rollback",
        "/api/settings/strategies",
        "/api/settings/risk-profiles/{dynamic}",
        "/api/rules",
        "/api/rules/get",
        "/api/rules/save",
        "/api/rules/delete",
        "/api/rules/{dynamic}",
        "/api/rules/activate-paper-lab",
        "/api/rules/auto-paper-lab",
    ),
    "MEDIUM_MODEL_APPROVAL_OR_REPORT": (
        "/api/models/real-approval/decision",
        "/api/models/real-order/dry-run",
        "/api/models/reports/archive",
        "/api/intelligence/strategy-generator/accept-draft",
    ),
    "LOW_AUDIT_AUTH_AGENT": (
        "/api/audit",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/change-password",
        "/api/agent/chat",
        "/api/agent/report",
    ),
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(value: object) -> str:
    text = str(value or "").strip()
    if "?" in text:
        text = text.split("?", 1)[0]
    return text.rstrip("/") or "/"


def _matches(path: str, rule: str) -> bool:
    path_norm = _norm(path)
    rule_norm = _norm(rule)
    return path_norm == rule_norm or path_norm.startswith(rule_norm + "/")


def _classify(call: dict[str, Any]) -> tuple[str, str]:
    base_path = _norm(call.get("base_path") or call.get("endpoint"))
    endpoint = _norm(call.get("endpoint") or base_path)

    for category, rules in CATEGORIES.items():
        for rule in rules:
            if _matches(base_path, rule) or _matches(endpoint, rule):
                return category, f"Matched safety rule {rule}"

    if base_path.startswith("/api/real/") or endpoint.startswith("/api/real/"):
        return "CRITICAL_REAL_TRADE", "Conservative real-trade namespace review"

    return "UNCLASSIFIED_MUTATING", "No mutating endpoint safety category matched"


def _call_key(call: dict[str, Any]) -> str:
    return "|".join(
        [
            str(call.get("method") or ""),
            str(call.get("base_path") or call.get("endpoint") or ""),
            str(call.get("file") or ""),
            str(call.get("line") or ""),
        ]
    )


def _runtime_policy(diff: dict[str, Any]) -> dict[str, Any]:
    policy = diff.get("runtime_policy") if isinstance(diff.get("runtime_policy"), dict) else {}
    return {
        "runtime_leaks": diff.get("runtime_leaks") if isinstance(diff.get("runtime_leaks"), list) else [],
        "tracked_runtime_stores": policy.get("tracked_runtime_stores") if isinstance(policy.get("tracked_runtime_stores"), list) else [],
        "unignored_runtime_stores": policy.get("unignored_runtime_stores") if isinstance(policy.get("unignored_runtime_stores"), list) else [],
    }


def _normalize_call(call: dict[str, Any], category: str, reason: str) -> dict[str, Any]:
    return {
        "method": call.get("method"),
        "endpoint": call.get("endpoint"),
        "base_path": call.get("base_path"),
        "file": call.get("file"),
        "line": call.get("line"),
        "category": category,
        "reason": reason,
    }


def build_report(frontend: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    calls = frontend.get("calls") if isinstance(frontend.get("calls"), list) else []
    mutating_calls = [call for call in calls if call.get("mutating") is True]
    classified: list[dict[str, Any]] = []
    seen: set[str] = set()

    for call in mutating_calls:
        key = _call_key(call)
        if key in seen:
            continue
        seen.add(key)
        category, reason = _classify(call)
        classified.append(_normalize_call(call, category, reason))

    by_category = Counter(item["category"] for item in classified)
    by_file: dict[str, Counter[str]] = defaultdict(Counter)
    for item in classified:
        by_file[str(item.get("file") or "unknown")][item["category"]] += 1

    critical_real_trade = [item for item in classified if item["category"] == "CRITICAL_REAL_TRADE"]
    unclassified = [item for item in classified if item["category"] == "UNCLASSIFIED_MUTATING"]
    runtime = _runtime_policy(diff)

    missing_path_count = int(diff.get("missing_path_count") or 0)
    method_mismatch_count = int(diff.get("method_mismatch_count") or 0)
    runtime_leaks = runtime["runtime_leaks"]
    tracked_runtime_stores = runtime["tracked_runtime_stores"]
    unignored_runtime_stores = runtime["unignored_runtime_stores"]

    blocked_runtime_stores = sorted(
        RUNTIME_STORE_BLOCKLIST.intersection(str(item) for item in tracked_runtime_stores + unignored_runtime_stores)
    )

    blockers: list[str] = []
    if missing_path_count:
        blockers.append(f"Contract diff has missing_path_count={missing_path_count}")
    if method_mismatch_count:
        blockers.append(f"Contract diff has method_mismatch_count={method_mismatch_count}")
    if runtime_leaks:
        blockers.append(f"Runtime leak count is {len(runtime_leaks)}")
    if tracked_runtime_stores:
        blockers.append(f"Tracked runtime store count is {len(tracked_runtime_stores)}")
    if unignored_runtime_stores:
        blockers.append(f"Unignored runtime store count is {len(unignored_runtime_stores)}")
    if blocked_runtime_stores:
        blockers.append("Blocked runtime stores are visible: " + ", ".join(blocked_runtime_stores))

    review_items: list[str] = []
    if unclassified:
        review_items.append(f"Unclassified mutating endpoint count is {len(unclassified)}")
    if critical_real_trade:
        review_items.append(f"Critical real-trade mutating endpoint count is {len(critical_real_trade)}; special review required")

    status = "blocker" if blockers else ("review" if unclassified else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_frontend_inventory": str(FRONTEND_INVENTORY_PATH.relative_to(ROOT)),
        "source_contract_diff": str(CONTRACT_DIFF_PATH.relative_to(ROOT)),
        "frontend_call_count": int(frontend.get("call_count") or len(calls)),
        "mutating_call_count": int(frontend.get("mutating_call_count") or len(mutating_calls)),
        "classified_mutating_count": len(classified) - len(unclassified),
        "unclassified_mutating_count": len(unclassified),
        "special_review_required_count": len(critical_real_trade),
        "contract_missing_path_count": missing_path_count,
        "contract_method_mismatch_count": method_mismatch_count,
        "runtime_leak_count": len(runtime_leaks),
        "tracked_runtime_store_count": len(tracked_runtime_stores),
        "unignored_runtime_store_count": len(unignored_runtime_stores),
        "by_category": dict(sorted(by_category.items())),
        "by_file": {path: dict(counter) for path, counter in sorted(by_file.items())},
        "critical_real_trade": critical_real_trade,
        "unclassified_mutating": unclassified,
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Keep this audit in the package quality sequence after the API contract diff.",
            "Review CRITICAL_REAL_TRADE items manually before any live-trade package.",
            "Add every new mutating frontend API call to a safety category before merging.",
            "Keep runtime stores ignored and untracked.",
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.10 Mutating Endpoint Safety Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Frontend API cagrisi: `{report['frontend_call_count']}`")
    lines.append(f"- Mutating cagri: `{report['mutating_call_count']}`")
    lines.append(f"- Siniflandirilan mutating cagri: `{report['classified_mutating_count']}`")
    lines.append(f"- Unclassified mutating cagri: `{report['unclassified_mutating_count']}`")
    lines.append(f"- Ozel real-trade inceleme sayisi: `{report['special_review_required_count']}`")
    lines.append("")
    lines.append("## Contract Guard Durumu")
    lines.append("")
    lines.append(f"- Missing path: `{report['contract_missing_path_count']}`")
    lines.append(f"- Method mismatch: `{report['contract_method_mismatch_count']}`")
    lines.append(f"- Runtime leak: `{report['runtime_leak_count']}`")
    lines.append(f"- Tracked runtime store: `{report['tracked_runtime_store_count']}`")
    lines.append(f"- Unignored runtime store: `{report['unignored_runtime_store_count']}`")
    lines.append("")
    lines.append("## Mutating Endpoint Kategorileri")
    lines.append("")
    lines.append("| Kategori | Adet |")
    lines.append("|---|---:|")
    for category, count in report["by_category"].items():
        lines.append(f"| `{category}` | {count} |")
    lines.append("")
    lines.append("## Critical Real Trade Ozel Inceleme")
    lines.append("")
    if report["critical_real_trade"]:
        lines.append("| Method | Endpoint | Dosya | Satir | Sebep |")
        lines.append("|---|---|---|---:|---|")
        for item in report["critical_real_trade"]:
            lines.append(
                f"| `{item.get('method')}` | `{item.get('base_path') or item.get('endpoint')}` | `{item.get('file')}` | {item.get('line')} | {item.get('reason')} |"
            )
    else:
        lines.append("Critical real-trade mutating endpoint bulunmadi.")
    lines.append("")
    lines.append("## Unclassified Mutating Endpointler")
    lines.append("")
    if report["unclassified_mutating"]:
        lines.append("| Method | Endpoint | Dosya | Satir |")
        lines.append("|---|---|---|---:|")
        for item in report["unclassified_mutating"]:
            lines.append(
                f"| `{item.get('method')}` | `{item.get('base_path') or item.get('endpoint')}` | `{item.get('file')}` | {item.get('line')} |"
            )
    else:
        lines.append("Unclassified mutating endpoint yok.")
    lines.append("")
    lines.append("## Runtime Store Guvenligi")
    lines.append("")
    if report["runtime_leak_count"] or report["tracked_runtime_store_count"] or report["unignored_runtime_store_count"]:
        lines.append("Runtime store guvenligi blocker durumunda incelenmeli.")
    else:
        lines.append("Runtime store leak, tracked runtime store veya unignored runtime store yok.")
    lines.append("")
    lines.append("## Sonuc")
    lines.append("")
    if report["status"] == "ok":
        lines.append("Mutating endpointler guvenlik siniflarina ayrildi ve contract guard temiz.")
    elif report["status"] == "review":
        lines.append("Mutating endpoint audit manuel inceleme gerektiriyor.")
    else:
        lines.append("Contract veya runtime store guvenligi blocker durumunda.")
    lines.append("")
    if report["blockers"]:
        lines.append("Blocker listesi:")
        for blocker in report["blockers"]:
            lines.append(f"- {blocker}")
        lines.append("")
    if report["review_items"]:
        lines.append("Review listesi:")
        for item in report["review_items"]:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("## Paket 6 Icin Onerilen Devam")
    lines.append("")
    for action in report["recommended_next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        frontend = _load_json(FRONTEND_INVENTORY_PATH)
        diff = _load_json(CONTRACT_DIFF_PATH)
        report = build_report(frontend, diff)
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT_OK",
        "review": "LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT_REVIEW",
        "blocker": "LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"mutating_call_count={report['mutating_call_count']}")
    print(f"unclassified_mutating_count={report['unclassified_mutating_count']}")
    print(f"special_review_required_count={report['special_review_required_count']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
