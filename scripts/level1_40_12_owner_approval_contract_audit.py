#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REVIEW_MATRIX_PATH = ROOT / "docs" / "LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX.json"
CONTRACT_DIFF_PATH = ROOT / "docs" / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_12_OWNER_APPROVAL_CONTRACT_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_12_OWNER_APPROVAL_CONTRACT_AUDIT.md"

CONTRACT_FIELDS = (
    "owner_approval_required",
    "readiness_required",
    "dry_run_before_required",
    "audit_reason_required",
    "position_state_required",
    "emergency_reason_required",
    "pilot_limits_required",
    "emergency_lock_must_be_false",
    "does_not_submit_order_expected",
)

ORDER_SUBMISSION_REQUIRED = (
    "owner_approval_required",
    "readiness_required",
    "dry_run_before_required",
    "audit_reason_required",
    "emergency_lock_must_be_false",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_policy(diff: dict[str, Any]) -> dict[str, list[Any]]:
    policy = diff.get("runtime_policy") if isinstance(diff.get("runtime_policy"), dict) else {}
    return {
        "runtime_leaks": diff.get("runtime_leaks") if isinstance(diff.get("runtime_leaks"), list) else [],
        "tracked_runtime_stores": policy.get("tracked_runtime_stores") if isinstance(policy.get("tracked_runtime_stores"), list) else [],
        "unignored_runtime_stores": policy.get("unignored_runtime_stores") if isinstance(policy.get("unignored_runtime_stores"), list) else [],
    }


def _contract_row(item: dict[str, Any]) -> dict[str, Any]:
    row = {
        "method": item.get("method"),
        "endpoint": item.get("endpoint"),
        "base_path": item.get("base_path"),
        "file": item.get("file"),
        "line": item.get("line"),
        "risk_type": item.get("risk_type"),
        "risk_level": item.get("risk_level"),
        "expected_behavior_note": item.get("expected_behavior_note"),
        "manual_review_note": item.get("manual_review_note"),
    }
    for field in CONTRACT_FIELDS:
        row[field] = bool(item.get(field))
    return row


def _is_order_submission(row: dict[str, Any]) -> bool:
    return (row.get("method") == "POST") and ((row.get("base_path") or row.get("endpoint")) == "/api/real/orders/place")


def build_report(review_matrix: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    matrix_source = review_matrix.get("matrix") if isinstance(review_matrix.get("matrix"), list) else []
    matrix_contract = [_contract_row(item) for item in matrix_source]

    counts = {
        f"{field}_count": sum(1 for item in matrix_contract if item.get(field) is True)
        for field in CONTRACT_FIELDS
    }

    order_rows = [item for item in matrix_contract if _is_order_submission(item)]
    order_submission_contract_ok = bool(order_rows) and all(
        all(row.get(field) is True for field in ORDER_SUBMISSION_REQUIRED)
        for row in order_rows
    )

    runtime = _runtime_policy(diff)
    missing_path_count = int(diff.get("missing_path_count") or 0)
    method_mismatch_count = int(diff.get("method_mismatch_count") or 0)
    runtime_leak_count = len(runtime["runtime_leaks"])
    tracked_runtime_store_count = len(runtime["tracked_runtime_stores"])
    unignored_runtime_store_count = len(runtime["unignored_runtime_stores"])

    blockers: list[str] = []
    if review_matrix.get("status") != "ok":
        blockers.append(f"40.11 review matrix status is {review_matrix.get('status')}")
    if not matrix_contract:
        blockers.append("review_matrix_count is 0")
    if not order_submission_contract_ok:
        blockers.append("/api/real/orders/place owner approval contract is incomplete")
    if missing_path_count:
        blockers.append(f"Contract diff has missing_path_count={missing_path_count}")
    if method_mismatch_count:
        blockers.append(f"Contract diff has method_mismatch_count={method_mismatch_count}")
    if runtime_leak_count:
        blockers.append(f"Runtime leak count is {runtime_leak_count}")
    if tracked_runtime_store_count:
        blockers.append(f"Tracked runtime store count is {tracked_runtime_store_count}")
    if unignored_runtime_store_count:
        blockers.append(f"Unignored runtime store count is {unignored_runtime_store_count}")

    review_items: list[str] = []
    if counts["owner_approval_required_count"] == 0:
        review_items.append("owner_approval_required_count is 0")
    if counts["audit_reason_required_count"] == 0:
        review_items.append("audit_reason_required_count is 0")

    status = "blocker" if blockers else ("review" if review_items else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_review_matrix": str(REVIEW_MATRIX_PATH.relative_to(ROOT)),
        "source_contract_diff": str(CONTRACT_DIFF_PATH.relative_to(ROOT)),
        "review_matrix_count": len(matrix_contract),
        **counts,
        "order_submission_contract_ok": order_submission_contract_ok,
        "contract_missing_path_count": missing_path_count,
        "contract_method_mismatch_count": method_mismatch_count,
        "runtime_leak_count": runtime_leak_count,
        "tracked_runtime_store_count": tracked_runtime_store_count,
        "unignored_runtime_store_count": unignored_runtime_store_count,
        "matrix_contract": matrix_contract,
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Keep 40.12 in the quality chain before any package that changes live-trade UI or backend behavior.",
            "Treat /api/real/orders/place as blocked unless owner approval, readiness, dry-run evidence, audit reason and emergency-lock-clear expectations remain true.",
            "Keep frontend owner approval visibility informational unless a dedicated behavior-change package is approved.",
            "Do not change Binance, order executor, strategy, filter, Karabasan or Futures behavior from this audit package.",
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.12 Owner Approval Contract Audit")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Matrix satiri: `{report['review_matrix_count']}`")
    lines.append(f"- Owner onayi gerekli: `{report['owner_approval_required_count']}`")
    lines.append(f"- Audit gerekcesi gerekli: `{report['audit_reason_required_count']}`")
    lines.append(f"- Order submission contract OK: `{str(report['order_submission_contract_ok']).lower()}`")
    lines.append("")
    lines.append("## Contract Guard Durumu")
    lines.append("")
    lines.append(f"- Missing path: `{report['contract_missing_path_count']}`")
    lines.append(f"- Method mismatch: `{report['contract_method_mismatch_count']}`")
    lines.append(f"- Runtime leak: `{report['runtime_leak_count']}`")
    lines.append(f"- Tracked runtime store: `{report['tracked_runtime_store_count']}`")
    lines.append(f"- Unignored runtime store: `{report['unignored_runtime_store_count']}`")
    lines.append("")
    lines.append("## Owner Onay Sayilari")
    lines.append("")
    lines.append("| Contract alani | Adet |")
    lines.append("|---|---:|")
    for field in CONTRACT_FIELDS:
        lines.append(f"| `{field}` | {report[field + '_count']} |")
    lines.append("")
    lines.append("## Order Submission Contract")
    lines.append("")
    if report["order_submission_contract_ok"]:
        lines.append("`POST /api/real/orders/place` icin owner onayi, readiness, dry-run kaniti, audit gerekcesi ve emergency lock kapali beklentisi tamam.")
    else:
        lines.append("`POST /api/real/orders/place` contract beklentilerinden en az biri eksik.")
    lines.append("")
    lines.append("## Endpoint Contract Matrisi")
    lines.append("")
    lines.append("| Method | Endpoint | Risk tipi | Owner | Readiness | Dry-run | Audit | Emergency clear |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for item in report["matrix_contract"]:
        lines.append(
            f"| `{item.get('method')}` | `{item.get('base_path') or item.get('endpoint')}` | `{item.get('risk_type')}` | {_yn(item['owner_approval_required'])} | {_yn(item['readiness_required'])} | {_yn(item['dry_run_before_required'])} | {_yn(item['audit_reason_required'])} | {_yn(item['emergency_lock_must_be_false'])} |"
        )
    lines.append("")
    lines.append("## Blocker / Review Listesi")
    lines.append("")
    if report["blockers"]:
        for blocker in report["blockers"]:
            lines.append(f"- BLOCKER: {blocker}")
    if report["review_items"]:
        for item in report["review_items"]:
            lines.append(f"- REVIEW: {item}")
    if not report["blockers"] and not report["review_items"]:
        lines.append("Blocker veya review item yok.")
    lines.append("")
    lines.append("## Sonuc")
    lines.append("")
    if report["status"] == "ok":
        lines.append("Owner onay beklentileri contract seviyesinde gorunur ve order submission ozel kontrolu temiz.")
    elif report["status"] == "review":
        lines.append("Owner onay veya audit gerekcesi sayilari manuel inceleme gerektiriyor.")
    else:
        lines.append("Owner approval contract, contract guard veya runtime store guvenligi blocker durumunda.")
    lines.append("")
    lines.append("## Paket 8 Icin Onerilen Devam")
    lines.append("")
    for action in report["recommended_next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def _yn(value: bool) -> str:
    return "evet" if value else "hayir"


def main() -> int:
    try:
        review_matrix = _load_json(REVIEW_MATRIX_PATH)
        diff = _load_json(CONTRACT_DIFF_PATH)
        report = build_report(review_matrix, diff)
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_12_OWNER_APPROVAL_CONTRACT_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_12_OWNER_APPROVAL_CONTRACT_AUDIT_OK",
        "review": "LEVEL1_40_12_OWNER_APPROVAL_CONTRACT_AUDIT_REVIEW",
        "blocker": "LEVEL1_40_12_OWNER_APPROVAL_CONTRACT_AUDIT_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"review_matrix_count={report['review_matrix_count']}")
    print(f"owner_approval_required_count={report['owner_approval_required_count']}")
    print(f"order_submission_contract_ok={str(report['order_submission_contract_ok']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
