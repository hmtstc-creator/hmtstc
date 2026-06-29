from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from typing import Any


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _bucket_quality(score: float) -> str:
    if score >= 80:
        return "premium"
    if score >= 65:
        return "tradable"
    if score >= 45:
        return "watch"
    if score > 0:
        return "weak"
    return "unknown"


def _row_reasons(row: dict) -> list[str]:
    reasons = row.get("rejection_reasons") or row.get("tradability_reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    if not reasons and row.get("reason"):
        reasons = [str(row.get("reason"))]
    return [str(item) for item in reasons if item]


def build_coin_universe_summary(scan: dict | None = None) -> dict:
    scan = scan or {}
    rows = scan.get("scan_rows") or []
    candidates = scan.get("candidates") or []
    rejection_breakdown = scan.get("rejection_breakdown") or scan.get("universe_rejection_breakdown") or {}
    universe_total = _safe_int(scan.get("universe_total_seen") or scan.get("total_pairs") or scan.get("scanned") or len(rows))
    eligible = _safe_int(scan.get("eligible_universe_count") or scan.get("scanned") or len(rows))
    rejected = _safe_int(scan.get("rejected_count") or max(0, len(rows) - len(candidates)))
    deep = _safe_int(((scan.get("scan_diagnostics") or {}).get("deep_analyzed_count")) or ((scan.get("scan_trace") or {}).get("deep_analyzed_count")))

    status_counter = Counter()
    quality_counter = Counter()
    reason_counter = Counter()
    depth_counter = Counter()
    scores = []
    qualities = []
    volumes = []

    for row in rows:
        raw_status = str(row.get("status") or ("PASSED" if row.get("passed") else "REJECT")).lower()
        if "pass" in raw_status or "candidate" in raw_status:
            status_counter["candidate"] += 1
        elif "watch" in raw_status:
            status_counter["watch"] += 1
        else:
            status_counter["reject"] += 1
        q = _safe_float(row.get("quality_score"))
        quality_counter[_bucket_quality(q)] += 1
        if q > 0:
            qualities.append(q)
        score = _safe_float(row.get("score"))
        if score:
            scores.append(score)
        volume = _safe_float(row.get("quote_volume") or row.get("volume_today"))
        if volume:
            volumes.append(volume)
        depth_counter[str(row.get("analysis_depth") or "unknown")] += 1
        for reason in _row_reasons(row):
            reason_counter[reason] += 1

    for reason, count in (rejection_breakdown or {}).items():
        if reason_counter[reason] < int(count or 0):
            reason_counter[reason] = int(count or 0)

    low_liquidity = reason_counter.get("low_quote_volume", 0) + reason_counter.get("low_trade_count", 0)
    return {
        "status": "ok" if scan.get("status") == "ok" or rows else "waiting_for_scan",
        "scan_id": scan.get("scan_id"),
        "time": scan.get("time"),
        "total_binance_usdt_pairs": universe_total,
        "eligible_spot_universe": eligible,
        "deep_analyzed_count": deep,
        "candidate_count": _safe_int(scan.get("candidates_count") or len(candidates)),
        "reject_count": rejected,
        "watch_count": status_counter.get("watch", 0),
        "low_liquidity_watch": low_liquidity,
        "excluded_stable_pairs": _safe_int((scan.get("universe_rejection_breakdown") or {}).get("stable_pair", 0)),
        "excluded_leveraged_tokens": _safe_int((scan.get("universe_rejection_breakdown") or {}).get("leveraged_token", 0)),
        "excluded_new_listings": _safe_int((scan.get("universe_rejection_breakdown") or {}).get("new_listing", 0)),
        "status_distribution": dict(status_counter),
        "quality_distribution": dict(quality_counter),
        "analysis_depth_distribution": dict(depth_counter),
        "reject_reason_distribution": dict(reason_counter.most_common(25)),
        "avg_score": round(mean(scores), 2) if scores else 0,
        "avg_quality_score": round(mean(qualities), 2) if qualities else 0,
        "avg_quote_volume": round(mean(volumes), 2) if volumes else 0,
        "coverage_note": "Total pair -> exclusion -> eligible universe -> deep analysis -> candidate/watchlist ayrımı açıklanır.",
    }


def build_scan_explanation(scan: dict | None = None) -> dict:
    summary = build_coin_universe_summary(scan)
    candidate_count = summary.get("candidate_count", 0)
    eligible = summary.get("eligible_spot_universe", 0)
    deep = summary.get("deep_analyzed_count", 0)
    reasons = summary.get("reject_reason_distribution", {})
    explanation = []
    explanation.append(f"Uygun spot evreni {eligible} coin olarak sayıldı.")
    if deep:
        explanation.append(f"Teknik derin analiz en güçlü {deep} aday üzerinde çalıştı; diğer coinler lightweight kalite/likidite taramasında kaldı.")
    explanation.append(f"Final aday sayısı {candidate_count}; aday sayısı düşükse ana sebepler: " + ", ".join(list(reasons.keys())[:5]) if reasons else "Reject sebebi bekleniyor.")
    return {"status": summary.get("status"), "summary": summary, "explanation": explanation}


def build_scan_history(data: dict | None = None, limit: int = 50) -> dict:
    data = data or {}
    history = data.get("scan_history") or []
    if not history and data.get("last_scan"):
        history = [data.get("last_scan")]
    items = history[-max(1, min(limit, 250)):]
    compact = []
    for item in reversed(items):
        summary = build_coin_universe_summary(item)
        compact.append({
            "scan_id": item.get("scan_id") or summary.get("scan_id"),
            "time": item.get("time") or summary.get("time"),
            "total": summary.get("total_binance_usdt_pairs"),
            "eligible": summary.get("eligible_spot_universe"),
            "deep": summary.get("deep_analyzed_count"),
            "candidates": summary.get("candidate_count"),
            "rejected": summary.get("reject_count"),
            "top_reason": next(iter(summary.get("reject_reason_distribution", {}) or {}), None),
            "status": item.get("status") or summary.get("status"),
        })
    return {"status": "ok", "count": len(compact), "items": compact}


def build_scan_replay(data: dict | None = None, scan_id: str | None = None) -> dict:
    data = data or {}
    history = data.get("scan_history") or []
    if data.get("last_scan"):
        history = history + [data.get("last_scan")]
    selected = None
    for item in reversed(history):
        if not scan_id or str(item.get("scan_id")) == str(scan_id):
            selected = item
            break
    if not selected:
        return {"status": "not_found", "scan_id": scan_id, "summary": {}, "rows": []}
    return {
        "status": "ok",
        "scan_id": selected.get("scan_id"),
        "summary": build_coin_universe_summary(selected),
        "trace": selected.get("scan_trace") or {},
        "diagnostics": selected.get("scan_diagnostics") or {},
        "candidates": selected.get("candidates") or [],
        "rows": selected.get("scan_rows") or [],
        "explanation": build_scan_explanation(selected).get("explanation", []),
    }


def append_scan_history(data: dict, scan: dict, limit: int = 250) -> None:
    if not isinstance(data, dict) or not isinstance(scan, dict):
        return
    history = data.setdefault("scan_history", [])
    compact_scan = dict(scan)
    # Keep full rows for recent history but cap memory to avoid runtime bloat.
    compact_scan["scan_rows"] = (scan.get("scan_rows") or [])[:1500]
    compact_scan["candidates"] = (scan.get("candidates") or [])[:200]
    history.append(compact_scan)
    data["scan_history"] = history[-limit:]
