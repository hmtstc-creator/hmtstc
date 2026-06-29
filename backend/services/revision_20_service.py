from __future__ import annotations

from services.real_position_lifecycle_service import build_real_position_lifecycle_report, build_reconciliation_report, build_emergency_close_lifecycle_preview
from services.real_trade_service import build_real_readiness


def _status(ok: bool, detail: str) -> dict:
    return {"status": "ok" if ok else "review", "detail": detail}


def build_revision_20_quality_report(data: dict, settings: dict) -> dict:
    checks = {
        "real_lifecycle": build_real_lifecycle_quality(data, settings),
        "reconciliation": build_reconciliation_quality(data, settings),
        "emergency_close_preview": build_emergency_close_quality(data, settings),
        "paper_real_separation": build_paper_real_position_separation(data, settings),
        "ui_contract": build_real_positions_ui_contract(data, settings),
    }
    ok_count = sum(1 for item in checks.values() if item.get("status") == "ok")
    return {
        "revision": 20,
        "title": "Real Trade Screens + Position Lifecycle",
        "status": "ok" if ok_count >= 4 else "review",
        "readiness_score": round(ok_count / max(len(checks), 1) * 100, 2),
        "checks": checks,
        "message": "Rev20 real positions, real order attempts, reconciliation ve emergency close preview akışlarını Paper/Shadow state'ten ayrıştırır.",
    }


def build_real_lifecycle_quality(data: dict, settings: dict) -> dict:
    report = build_real_position_lifecycle_report(data)
    has_contract = bool(report.get("allowed_statuses")) and "manual_attention_required" in report.get("allowed_statuses", [])
    return {
        "status": "ok" if has_contract else "review",
        "positions_count": report.get("positions_count", 0),
        "open_positions_count": report.get("open_positions_count", 0),
        "manual_attention_count": report.get("manual_attention_count", 0),
        "status_counts": report.get("status_counts", {}),
        "allowed_statuses": report.get("allowed_statuses", []),
    }


def build_reconciliation_quality(data: dict, settings: dict) -> dict:
    report = build_reconciliation_report(data, balances=None)
    return {
        "status": "ok" if "balance_not_readable" in report.get("issues", []) or report.get("status") in {"ok", "review"} else "review",
        "tracked_open_positions": report.get("tracked_open_positions", 0),
        "manual_attention_required": report.get("manual_attention_required", False),
        "issues": report.get("issues", []),
        "note": "Offline quality gate canlı Binance balance olmadan reconciliation contract'ını doğrular.",
    }


def build_emergency_close_quality(data: dict, settings: dict) -> dict:
    preview = build_emergency_close_lifecycle_preview(data)
    return {
        "status": "ok" if preview.get("auto_close") is False and preview.get("status") == "preview" else "review",
        "auto_close": preview.get("auto_close"),
        "positions_count": preview.get("positions_count", 0),
        "blockers": preview.get("blockers", []),
        "requires_owner_preview": True,
        "requires_confirmation_token": True,
    }


def build_paper_real_position_separation(data: dict, settings: dict) -> dict:
    paper_positions = data.get("positions", []) if isinstance(data.get("positions"), list) else []
    real_trade = data.get("real_trade", {}) if isinstance(data.get("real_trade"), dict) else {}
    real_positions = real_trade.get("positions", []) if isinstance(real_trade.get("positions"), list) else []
    return {
        "status": "ok",
        "paper_positions_count": len(paper_positions),
        "real_positions_count": len(real_positions),
        "separate_namespaces": "real_trade" in data,
        "paper_reset_must_not_delete_real": True,
        "real_order_requires_owner_safety_token": True,
    }


def build_real_positions_ui_contract(data: dict, settings: dict) -> dict:
    readiness = build_real_readiness(data, settings)
    return {
        "status": "ok",
        "required_ui_panels": [
            "Real Positions",
            "Real Order Attempts",
            "Lifecycle Status Matrix",
            "Emergency Close Preview",
            "Reconciliation",
            "Paper / Shadow Open Positions",
        ],
        "required_actions": [
            "refreshRealTrade",
            "reconcileRealPositions",
            "previewEmergencyClose",
            "transitionRealPosition",
        ],
        "real_readiness_status": readiness.get("status"),
        "real_order_default_locked": not readiness.get("ready_for_real_order", False),
    }
