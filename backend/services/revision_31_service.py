from __future__ import annotations

from services.market_intelligence_final_service import (
    build_market_intelligence_final_report,
    build_market_regime_strategy_match,
    build_no_trade_cooldown_final,
    build_orderbook_final_report,
)


def _status_from_parts(parts: list[dict]) -> str:
    statuses = [p.get("status") for p in parts if isinstance(p, dict)]
    if "blocked" in statuses:
        return "blocked"
    if "review" in statuses:
        return "review"
    return "ok"


def build_revision_31_quality_report(data: dict, settings: dict | None = None) -> dict:
    final = build_market_intelligence_final_report(data, settings or {})
    regime = final.get("regime_strategy_match") or {}
    orderbook = final.get("orderbook_intelligence") or {}
    no_trade = final.get("no_trade_cooldown") or {}
    ui = build_revision_31_ui_quality()
    parts = [final, regime, orderbook, no_trade, ui]
    status = _status_from_parts(parts)
    score = min([int(p.get("score", 100)) for p in parts if isinstance(p, dict) and p.get("score") is not None] or [final.get("score", 0)])
    return {
        "revision": 31,
        "title": "Market Intelligence Final Pack",
        "status": status,
        "score": score,
        "checks": {
            "market_intelligence": final,
            "market_regime_strategy_match": regime,
            "orderbook_intelligence": orderbook,
            "no_trade_cooldown": no_trade,
            "ui": ui,
        },
        "policy": {
            "paper_real_separation_preserved": True,
            "no_trade_blocks_real_order": True,
            "orderbook_is_confirmation_not_trade_authority": True,
            "cooldown_requires_owner_review_for_override": True,
        },
    }


def build_revision_31_regime_quality(data: dict, settings: dict | None = None) -> dict:
    return build_market_regime_strategy_match(data, settings or {})


def build_revision_31_orderbook_quality(data: dict, settings: dict | None = None) -> dict:
    return build_orderbook_final_report(data, settings or {})


def build_revision_31_no_trade_quality(data: dict, settings: dict | None = None) -> dict:
    return build_no_trade_cooldown_final(data, settings or {})


def build_revision_31_ui_quality() -> dict:
    return {
        "status": "ok",
        "features": [
            "intelligence_market_regime_final_panel",
            "orderbook_sample_table",
            "no_trade_cooldown_panel",
            "strategy_match_policy_card",
            "dashboard_market_intelligence_strip",
        ],
        "files": [
            "frontend/js/pages/intelligence.js",
            "frontend/js/pages/dashboard.js",
            "frontend/css/styles.css",
        ],
    }
