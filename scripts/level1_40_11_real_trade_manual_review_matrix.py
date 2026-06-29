#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MUTATING_AUDIT_PATH = ROOT / "docs" / "LEVEL1_40_10_MUTATING_ENDPOINT_SAFETY_AUDIT.json"
CONTRACT_DIFF_PATH = ROOT / "docs" / "LEVEL1_40_08_API_CONTRACT_DIFF.json"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(value: object) -> str:
    text = str(value or "").strip()
    if "?" in text:
        text = text.split("?", 1)[0]
    return text.rstrip("/") or "/"


def _runtime_policy(diff: dict[str, Any]) -> dict[str, list[Any]]:
    policy = diff.get("runtime_policy") if isinstance(diff.get("runtime_policy"), dict) else {}
    return {
        "runtime_leaks": diff.get("runtime_leaks") if isinstance(diff.get("runtime_leaks"), list) else [],
        "tracked_runtime_stores": policy.get("tracked_runtime_stores") if isinstance(policy.get("tracked_runtime_stores"), list) else [],
        "unignored_runtime_stores": policy.get("unignored_runtime_stores") if isinstance(policy.get("unignored_runtime_stores"), list) else [],
    }


def _risk_profile(endpoint: str) -> dict[str, Any]:
    path = _norm(endpoint)
    common = {
        "risk_level": "critical",
        "owner_approval_required": True,
        "readiness_required": False,
        "dry_run_before_required": False,
        "audit_reason_required": False,
        "position_state_required": False,
        "emergency_reason_required": False,
        "pilot_limits_required": False,
        "emergency_lock_must_be_false": False,
        "does_not_submit_order_expected": False,
    }

    if path == "/api/real/orders/place":
        return common | {
            "risk_type": "ORDER_SUBMISSION",
            "readiness_required": True,
            "dry_run_before_required": True,
            "audit_reason_required": True,
            "emergency_lock_must_be_false": True,
            "expected_behavior_note": "Canli emir gonderme hattini tetikleyebilen endpoint olarak ele alinmali.",
            "manual_review_note": "Owner onayi, readiness kontrolu, dry-run kaniti ve emergency lock kapali durumu olmadan kullanilmamali.",
        }

    if path in {"/api/real/orders/preview", "/api/real/orders/dry-run"}:
        return common | {
            "risk_type": "ORDER_PREVIEW_OR_DRY_RUN",
            "owner_approval_required": False,
            "readiness_required": True,
            "does_not_submit_order_expected": True,
            "expected_behavior_note": "Emir gondermeden sadece preview veya dry-run sonucu uretmesi beklenir.",
            "manual_review_note": "Canli emir uretmedigi ve readiness baglamini bozmadigi manuel olarak dogrulanmali.",
        }

    if path in {
        "/api/real/positions/emergency-close",
        "/api/real/positions/transition",
        "/api/real/positions/reconcile",
    }:
        return common | {
            "risk_type": "POSITION_CONTROL",
            "position_state_required": True,
            "emergency_reason_required": path == "/api/real/positions/emergency-close",
            "audit_reason_required": True,
            "expected_behavior_note": "Canli pozisyon durumunu etkileyebilecek kontrol endpointi olarak incelenmeli.",
            "manual_review_note": "Owner onayi, pozisyon state kaniti ve gerekirse emergency gerekcesi beklenmeli.",
        }

    if path in {
        "/api/real/lock",
        "/api/real/unlock",
        "/api/real/emergency/lock",
        "/api/real/emergency/recovery-unlock",
    }:
        return common | {
            "risk_type": "REAL_TRADE_LOCK_CONTROL",
            "audit_reason_required": True,
            "expected_behavior_note": "Real-trade kilit durumunu degistiren endpoint olarak incelenmeli.",
            "manual_review_note": "Owner onayi ve audit gerekcesi olmadan kilit acma/kapama islemi yapilmamali.",
        }

    if path in {"/api/real/pilot/start", "/api/real/pilot/stop"}:
        return common | {
            "risk_type": "PILOT_CONTROL",
            "pilot_limits_required": True,
            "audit_reason_required": True,
            "expected_behavior_note": "Real-trade pilot calisma durumunu etkileyen endpoint olarak incelenmeli.",
            "manual_review_note": "Owner onayi ve pilot limitleri belgelenmeden pilot baslatma/durdurma yapilmamali.",
        }

    return common | {
        "risk_type": "UNKNOWN_REAL_TRADE_RISK_TYPE",
        "expected_behavior_note": "Endpoint Paket 6 risk tipleriyle eslesmedi.",
        "manual_review_note": "Bu endpoint icin risk tipi eklenmeli ve owner onay beklentisi tanimlanmali.",
    }


def _matrix_row(item: dict[str, Any]) -> dict[str, Any]:
    profile = _risk_profile(item.get("base_path") or item.get("endpoint"))
    return {
        "method": item.get("method"),
        "endpoint": item.get("endpoint"),
        "base_path": item.get("base_path"),
        "file": item.get("file"),
        "line": item.get("line"),
        **profile,
    }


def build_report(mutating_audit: dict[str, Any], diff: dict[str, Any]) -> dict[str, Any]:
    critical_items = mutating_audit.get("critical_real_trade") if isinstance(mutating_audit.get("critical_real_trade"), list) else []
    matrix = [_matrix_row(item) for item in critical_items]
    unknown_count = sum(1 for item in matrix if item["risk_type"] == "UNKNOWN_REAL_TRADE_RISK_TYPE")
    by_risk_type = Counter(item["risk_type"] for item in matrix)

    runtime = _runtime_policy(diff)
    missing_path_count = int(diff.get("missing_path_count") or 0)
    method_mismatch_count = int(diff.get("method_mismatch_count") or 0)
    runtime_leak_count = len(runtime["runtime_leaks"])
    tracked_runtime_store_count = len(runtime["tracked_runtime_stores"])
    unignored_runtime_store_count = len(runtime["unignored_runtime_stores"])

    blockers: list[str] = []
    if mutating_audit.get("status") != "ok":
        blockers.append(f"40.10 mutating audit status is {mutating_audit.get('status')}")
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
    if not critical_items:
        blockers.append("critical_real_trade_count is 0")

    review_items: list[str] = []
    if unknown_count:
        review_items.append(f"unknown_real_trade_risk_type_count={unknown_count}")

    status = "blocker" if blockers else ("review" if unknown_count else "ok")

    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_mutating_audit": str(MUTATING_AUDIT_PATH.relative_to(ROOT)),
        "source_contract_diff": str(CONTRACT_DIFF_PATH.relative_to(ROOT)),
        "critical_real_trade_count": len(critical_items),
        "review_matrix_count": len(matrix),
        "unknown_real_trade_risk_type_count": unknown_count,
        "contract_missing_path_count": missing_path_count,
        "contract_method_mismatch_count": method_mismatch_count,
        "runtime_leak_count": runtime_leak_count,
        "tracked_runtime_store_count": tracked_runtime_store_count,
        "unignored_runtime_store_count": unignored_runtime_store_count,
        "by_risk_type": dict(sorted(by_risk_type.items())),
        "matrix": matrix,
        "blockers": blockers,
        "review_items": review_items,
        "recommended_next_actions": [
            "Use this matrix before any live-trade package or owner approval workflow change.",
            "Verify ORDER_SUBMISSION endpoints require owner approval, readiness, prior dry-run and emergency-lock clear state.",
            "Verify POSITION_CONTROL endpoints require owner approval and current position state evidence.",
            "Keep real-trade route and executor behavior changes out of audit-only packages.",
        ],
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# Level1 40.11 Real Trade Manual Review Matrix")
    lines.append("")
    lines.append("## Ozet")
    lines.append("")
    lines.append(f"- Durum: `{report['status']}`")
    lines.append(f"- Critical real-trade endpoint satiri: `{report['critical_real_trade_count']}`")
    lines.append(f"- Manuel inceleme matrisi satiri: `{report['review_matrix_count']}`")
    lines.append(f"- Bilinmeyen real-trade risk tipi: `{report['unknown_real_trade_risk_type_count']}`")
    lines.append("")
    lines.append("## Contract Guard Durumu")
    lines.append("")
    lines.append(f"- Missing path: `{report['contract_missing_path_count']}`")
    lines.append(f"- Method mismatch: `{report['contract_method_mismatch_count']}`")
    lines.append(f"- Runtime leak: `{report['runtime_leak_count']}`")
    lines.append(f"- Tracked runtime store: `{report['tracked_runtime_store_count']}`")
    lines.append(f"- Unignored runtime store: `{report['unignored_runtime_store_count']}`")
    lines.append("")
    lines.append("## Real Trade Risk Tipleri")
    lines.append("")
    lines.append("| Risk tipi | Adet |")
    lines.append("|---|---:|")
    for risk_type, count in report["by_risk_type"].items():
        lines.append(f"| `{risk_type}` | {count} |")
    lines.append("")
    lines.append("## Manuel Inceleme Matrisi")
    lines.append("")
    lines.append("| Method | Endpoint | Dosya | Satir | Risk tipi | Owner | Readiness | Not |")
    lines.append("|---|---|---|---:|---|---|---|---|")
    for item in report["matrix"]:
        owner = "evet" if item["owner_approval_required"] else "hayir"
        readiness = "evet" if item["readiness_required"] else "hayir"
        lines.append(
            f"| `{item.get('method')}` | `{item.get('base_path') or item.get('endpoint')}` | `{item.get('file')}` | {item.get('line')} | `{item['risk_type']}` | {owner} | {readiness} | {item['manual_review_note']} |"
        )
    lines.append("")
    lines.append("## Owner Onay Beklentileri")
    lines.append("")
    lines.append("- `ORDER_SUBMISSION`: owner onayi, readiness, once dry-run, emergency lock kapali olmasi beklenir.")
    lines.append("- `ORDER_PREVIEW_OR_DRY_RUN`: order gondermemesi ve readiness baglaminda kalmasi beklenir.")
    lines.append("- `POSITION_CONTROL`: owner onayi, pozisyon state kaniti ve emergency-close icin gerekce beklenir.")
    lines.append("- `REAL_TRADE_LOCK_CONTROL`: owner onayi ve audit gerekcesi beklenir.")
    lines.append("- `PILOT_CONTROL`: owner onayi ve pilot limitlerinin belgelenmesi beklenir.")
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
        lines.append("Real-trade kritik endpointleri icin manuel inceleme matrisi uretildi ve risk tipi bilinmeyen endpoint yok.")
    elif report["status"] == "review":
        lines.append("Bazi real-trade endpointleri icin risk tipi eklenmeli.")
    else:
        lines.append("40.10, contract guard veya runtime store guvenligi blocker durumunda.")
    lines.append("")
    lines.append("## Paket 7 Icin Onerilen Devam")
    lines.append("")
    for action in report["recommended_next_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        mutating_audit = _load_json(MUTATING_AUDIT_PATH)
        diff = _load_json(CONTRACT_DIFF_PATH)
        report = build_report(mutating_audit, diff)
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX_ERROR: {exc}", file=sys.stderr)
        return 1

    marker = {
        "ok": "LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX_OK",
        "review": "LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX_REVIEW",
        "blocker": "LEVEL1_40_11_REAL_TRADE_MANUAL_REVIEW_MATRIX_BLOCKER",
    }[report["status"]]

    print(marker)
    print(f"status={report['status']}")
    print(f"critical_real_trade_count={report['critical_real_trade_count']}")
    print(f"review_matrix_count={report['review_matrix_count']}")
    print(f"unknown_real_trade_risk_type_count={report['unknown_real_trade_risk_type_count']}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")

    return 1 if report["status"] == "blocker" else 0


if __name__ == "__main__":
    raise SystemExit(main())
