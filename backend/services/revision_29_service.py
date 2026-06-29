from __future__ import annotations

from services.observability_service import (
    build_deploy_report,
    build_endpoint_error_report,
    build_latency_report,
    build_observability_summary,
    build_observability_ui_contract,
    build_stale_report,
)


def _gate(name: str, report: dict) -> dict:
    status = report.get("status", "review") if isinstance(report, dict) else "review"
    return {
        "name": name,
        "status": status,
        "score": report.get("score") if isinstance(report, dict) else None,
        "report": report,
    }


def build_revision_29_quality_report(data: dict, settings: dict) -> dict:
    summary = build_observability_summary(data, settings)
    gates = [
        _gate("latency", summary.get("latency") or {}),
        _gate("endpoint_errors", summary.get("endpoint_errors") or {}),
        _gate("stale_data", summary.get("stale_data") or {}),
        _gate("deploy_revision_health", summary.get("deploy") or {}),
        _gate("observability_ui", build_observability_ui_contract()),
    ]
    blockers = []
    reviews = []
    for gate in gates:
        if gate["status"] == "blocked":
            blockers.append(gate["name"])
        elif gate["status"] == "review":
            reviews.append(gate["name"])
    return {
        "revision": 29,
        "status": "blocked" if blockers else ("review" if reviews else "ok"),
        "score": summary.get("score", 0),
        "summary": summary,
        "gates": gates,
        "blockers": blockers,
        "reviews": reviews,
        "policy": {
            "observability_is_read_only": True,
            "real_trade_actions_remain_locked": True,
            "degraded_runtime_blocks_real_order": True,
        },
    }


def build_revision_29_latency_quality(data: dict, settings: dict) -> dict:
    return build_latency_report(data)


def build_revision_29_endpoint_error_quality(data: dict) -> dict:
    return build_endpoint_error_report(data)


def build_revision_29_stale_quality(data: dict, settings: dict) -> dict:
    return build_stale_report(data, settings)


def build_revision_29_deploy_quality(data: dict) -> dict:
    return build_deploy_report(data)


def build_revision_29_ui_quality() -> dict:
    return build_observability_ui_contract()
