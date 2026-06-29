from __future__ import annotations

from services.portfolio_allocation_final_service import (
    build_allocation_audit_report,
    build_correlation_cluster_exposure,
    build_portfolio_allocation_final,
    build_usdt_reserve_policy,
)


def _status(parts: list[dict]) -> str:
    statuses = [p.get("status") for p in parts if isinstance(p, dict)]
    if "blocked" in statuses:
        return "blocked"
    if "review" in statuses:
        return "review"
    return "ok"


def build_revision_32_quality_report(data: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    allocation = build_portfolio_allocation_final(data, settings)
    reserve = build_usdt_reserve_policy(data, settings)
    exposure = build_correlation_cluster_exposure(data, settings)
    audit = build_allocation_audit_report(data, settings)
    ui = build_revision_32_ui_quality()
    parts = [allocation, reserve, exposure, audit, ui]
    return {
        "revision": 32,
        "title": "Portfolio Allocation Final Pack",
        "status": _status(parts),
        "score": min([int(p.get("score", 100)) for p in parts if isinstance(p, dict)] or [100]),
        "checks": {
            "portfolio_allocation": allocation,
            "usdt_reserve": reserve,
            "cluster_exposure": exposure,
            "allocation_audit": audit,
            "ui": ui,
        },
        "policy": {
            "usdt_reserve_first": True,
            "allocation_is_recommendation_only": True,
            "no_automatic_real_order": True,
            "owner_approval_required_for_real_allocation": True,
        },
    }


def build_revision_32_allocation_quality(data: dict, settings: dict | None = None) -> dict:
    return build_portfolio_allocation_final(data, settings or {})


def build_revision_32_usdt_reserve_quality(data: dict, settings: dict | None = None) -> dict:
    return build_usdt_reserve_policy(data, settings or {})


def build_revision_32_cluster_exposure_quality(data: dict, settings: dict | None = None) -> dict:
    return build_correlation_cluster_exposure(data, settings or {})


def build_revision_32_allocation_audit_quality(data: dict, settings: dict | None = None) -> dict:
    return build_allocation_audit_report(data, settings or {})


def build_revision_32_ui_quality() -> dict:
    return {
        "status": "ok",
        "features": [
            "dashboard_portfolio_allocation_compact_block",
            "intelligence_portfolio_allocation_final_panel",
            "usdt_reserve_policy_panel",
            "cluster_exposure_panel",
            "allocation_audit_panel",
        ],
        "files": [
            "frontend/js/pages/dashboard.js",
            "frontend/js/pages/intelligence.js",
            "frontend/css/styles.css",
        ],
    }
