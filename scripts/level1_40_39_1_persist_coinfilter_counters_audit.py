#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / "backend" / "core" / "storage.py"
JSON_OUT = ROOT / "docs" / "LEVEL1_40_39_1_PERSIST_COINFILTER_COUNTERS_AUDIT.json"
MD_OUT = ROOT / "docs" / "LEVEL1_40_39_1_PERSIST_COINFILTER_COUNTERS_AUDIT.md"


def _text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path.relative_to(ROOT))
    return path.read_text(encoding="utf-8")


def _import_storage():
    sys.path.insert(0, str(ROOT / "backend"))
    from core.storage import normalize_shadow_state, sync_last_scan_state  # type: ignore
    return normalize_shadow_state, sync_last_scan_state


def build_report() -> dict[str, Any]:
    storage_text = _text(STORAGE)
    normalize_shadow_state, sync_last_scan_state = _import_storage()

    scan = {
        "status": "ok",
        "live": True,
        "source": "binance",
        "mode": "coinfilter_test_scan",
        "test_scan": True,
        "time": "2026-06-14T23:38:55",
        "scan_id": "audit-scan",
        "scanned": 350,
        "eligible_universe_count": 350,
        "universe_total_seen": 431,
        "universe_rejected_count": 11,
        "universe_rejection_breakdown": {"stable_pair": 9, "leveraged_token": 2},
        "candidates_count": 4,
        "rejected_count": 346,
        "top_rejection_reason": "score_below_threshold",
        "rejection_breakdown": {"wide_spread": 284, "score_below_threshold": 344, "low_quality_score": 307, "low_volatility": 1},
        "filter_rejection_counts": {
            "min_quote_volume": 0,
            "min_trade_count": 0,
            "min_volatility": 1,
            "quality_score_min": 307,
            "lightweight_score_min": 344,
            "stable_pair_guard": 9,
            "leveraged_token_guard": 2,
        },
        "scan_diagnostics": {
            "filter_rejection_counts": {"lightweight_score_min": 344},
            "volume_rejection_diagnostics": {
                "effective_min_quote_volume": 1,
                "low_quote_volume_count": 0,
                "sample_low_quote_volume": [],
            },
            "liquidity_rejection_diagnostics": {
                "effective_min_quote_volume": 1,
                "low_liquidity_count": 0,
            },
        },
        "candidates": [{"symbol": "DOGEUSDT", "passed": True}],
        "scan_rows": [{"symbol": "DOGEUSDT", "passed": True}, {"symbol": "BADUSDT", "passed": False}],
        "pipeline": {"coinfilter": {"passed": 4, "rejected": 346}},
        "error": None,
    }

    data = {"last_scan": {}, "last_scan_time": None}
    sync_last_scan_state(data, scan)
    normalized = normalize_shadow_state(data)
    saved_scan = normalized.get("last_scan") or {}

    checks = {
        "storage_whitelist_has_filter_rejection_counts": '"filter_rejection_counts"' in storage_text,
        "storage_whitelist_has_volume_rejection_diagnostics": '"volume_rejection_diagnostics"' in storage_text,
        "storage_whitelist_has_liquidity_rejection_diagnostics": '"liquidity_rejection_diagnostics"' in storage_text,
        "sync_last_scan_state_keeps_full_scan_before_normalize": data.get("last_scan", {}).get("filter_rejection_counts", {}).get("lightweight_score_min") == 344,
        "normalize_preserves_filter_rejection_counts": saved_scan.get("filter_rejection_counts", {}).get("lightweight_score_min") == 344,
        "normalize_preserves_min_quote_volume_zero_count": saved_scan.get("filter_rejection_counts", {}).get("min_quote_volume") == 0,
        "normalize_preserves_volume_diagnostics": saved_scan.get("volume_rejection_diagnostics", {}).get("effective_min_quote_volume") == 1,
        "normalize_preserves_liquidity_diagnostics": saved_scan.get("liquidity_rejection_diagnostics", {}).get("low_liquidity_count") == 0,
        "normalize_preserves_scan_rows": len(saved_scan.get("scan_rows") or []) == 2,
        "normalize_preserves_candidates": len(saved_scan.get("candidates") or []) == 1,
        "normalize_preserves_pipeline": saved_scan.get("pipeline", {}).get("coinfilter", {}).get("rejected") == 346,
    }
    blockers = [f"{key}=false" for key, ok in checks.items() if not ok]
    return {
        "status": "blocker" if blockers else "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **checks,
        "saved_last_scan_sample": {
            "filter_rejection_counts": saved_scan.get("filter_rejection_counts"),
            "volume_rejection_diagnostics": saved_scan.get("volume_rejection_diagnostics"),
            "liquidity_rejection_diagnostics": saved_scan.get("liquidity_rejection_diagnostics"),
            "scan_rows_count": len(saved_scan.get("scan_rows") or []),
            "candidates_count": len(saved_scan.get("candidates") or []),
        },
        "blockers": blockers,
    }


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Level1 40.39.1 Persist CoinFilter Counters Audit",
        "",
        f"- Durum: `{report['status']}`",
        f"- Store filter_rejection_counts korunuyor: `{report['normalize_preserves_filter_rejection_counts']}`",
        f"- Store volume diagnostics korunuyor: `{report['normalize_preserves_volume_diagnostics']}`",
        f"- Store liquidity diagnostics korunuyor: `{report['normalize_preserves_liquidity_diagnostics']}`",
        "",
        "## Blocker Listesi",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- BLOCKER: {item}" for item in report["blockers"])
    else:
        lines.append("Blocker yok.")
    lines.append("")
    MD_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_markdown(report)
    except Exception as exc:
        print(f"LEVEL1_40_39_1_PERSIST_COINFILTER_COUNTERS_AUDIT_ERROR: {exc}", file=sys.stderr)
        return 1
    marker = "LEVEL1_40_39_1_PERSIST_COINFILTER_COUNTERS_AUDIT_OK" if report["status"] == "ok" else "LEVEL1_40_39_1_PERSIST_COINFILTER_COUNTERS_AUDIT_BLOCKER"
    print(marker)
    print(f"status={report['status']}")
    print(f"normalize_preserves_filter_rejection_counts={str(report['normalize_preserves_filter_rejection_counts']).lower()}")
    print(f"normalize_preserves_volume_diagnostics={str(report['normalize_preserves_volume_diagnostics']).lower()}")
    print(f"json={JSON_OUT.relative_to(ROOT)}")
    print(f"markdown={MD_OUT.relative_to(ROOT)}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
