from __future__ import annotations

from services.coin_universe_final_service import (
    build_coin_universe_summary,
    build_scan_explanation,
    build_scan_history,
    build_scan_replay,
)


def _status_from_score(score: int, blockers: list[str] | None = None) -> str:
    blockers = blockers or []
    if blockers:
        return "blocked"
    if score >= 85:
        return "ok"
    if score >= 65:
        return "review"
    return "blocked"


def build_coin_universe_quality(data: dict, settings: dict | None = None) -> dict:
    scan = (data or {}).get("last_scan") or {}
    summary = build_coin_universe_summary(scan)
    blockers = []
    warnings = []
    if summary.get("eligible_spot_universe", 0) <= 0:
        blockers.append("eligible_universe_missing")
    if summary.get("total_binance_usdt_pairs", 0) <= 0:
        blockers.append("binance_universe_missing")
    if summary.get("deep_analyzed_count", 0) <= 0 and summary.get("eligible_spot_universe", 0) > 0:
        warnings.append("deep_analysis_not_started")
    if summary.get("candidate_count", 0) <= 0 and summary.get("eligible_spot_universe", 0) > 0:
        warnings.append("no_candidate_after_filters")
    score = 100 - len(blockers) * 35 - len(warnings) * 10
    return {"status": _status_from_score(score, blockers), "score": max(0, score), "blockers": blockers, "warnings": warnings, "summary": summary}


def build_reject_distribution_quality(data: dict) -> dict:
    summary = build_coin_universe_summary((data or {}).get("last_scan") or {})
    dist = summary.get("reject_reason_distribution") or {}
    return {
        "status": "ok" if dist else "review",
        "reason_count": len(dist),
        "top_reasons": [{"reason": key, "count": value} for key, value in list(dist.items())[:10]],
        "coverage_note": "Reject reason distribution CoinFilter ve Dashboard açıklama katmanını besler.",
    }


def build_scan_history_quality(data: dict) -> dict:
    history = build_scan_history(data, limit=50)
    count = history.get("count", 0)
    return {
        "status": "ok" if count else "review",
        "history_count": count,
        "latest": (history.get("items") or [{}])[0] if count else {},
        "items": history.get("items", [])[:20],
    }


def build_coinfilter_ui_quality() -> dict:
    return {
        "status": "ok",
        "features": [
            "universe_summary_cards",
            "reject_reason_distribution",
            "quality_distribution",
            "scan_history_panel",
            "scan_replay_panel",
            "candidate_watchlist",
            "fixed_height_scroll_tables",
            "why_only_n_candidates_explanation",
        ],
        "owner": "frontend/js/pages/coinFilter.js",
    }


def build_revision_30_quality_report(data: dict, settings: dict | None = None) -> dict:
    universe = build_coin_universe_quality(data, settings)
    reject = build_reject_distribution_quality(data)
    history = build_scan_history_quality(data)
    ui = build_coinfilter_ui_quality()
    blockers = list(universe.get("blockers", []))
    warnings = list(universe.get("warnings", []))
    if reject.get("status") != "ok":
        warnings.append("reject_distribution_waiting_for_scan")
    if history.get("status") != "ok":
        warnings.append("scan_history_waiting_for_scan")
    score = min(universe.get("score", 0), 100 - len(warnings) * 3)
    return {
        "revision": 30,
        "status": _status_from_score(score, blockers),
        "score": max(0, score),
        "blockers": blockers,
        "warnings": warnings,
        "summary": {
            "coin_universe": universe,
            "reject_distribution": reject,
            "scan_history": history,
            "coinfilter_ui": ui,
        },
        "policy": {
            "full_universe_accounting": True,
            "deep_analysis_is_candidate_refinement": True,
            "paper_real_trade_unchanged": True,
            "real_trade_still_locked_by_default": True,
        },
    }


def build_scan_replay_quality(data: dict, scan_id: str | None = None) -> dict:
    return build_scan_replay(data, scan_id=scan_id)


def build_scan_explanation_quality(data: dict) -> dict:
    return build_scan_explanation((data or {}).get("last_scan") or {})
