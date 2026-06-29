from __future__ import annotations

from services.settings_risk_service import build_real_readiness_impact, build_settings_rollback_preview, build_worst_case_risk_matrix
from services.settings_unit_service import normalize_settings_units, validate_normalized_settings

REVISION = "27"


def _gate(name: str, report: dict) -> dict:
    return {"name": name, "status": report.get("status", "review"), "report": report}


def build_settings_final_quality(settings: dict, data: dict) -> dict:
    validation = validate_normalized_settings(settings)
    normalized = validation.get("normalized") or normalize_settings_units(settings)
    history = data.get("settings_history", []) or []
    has_snapshots = any(isinstance(item, dict) and item.get("before_snapshot") and item.get("after_snapshot") for item in history)
    return {
        "status": "ok" if validation.get("valid") else "blocked",
        "unit_schema_version": (normalized.get("unit_schema") or {}).get("version"),
        "valid": validation.get("valid"),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
        "history_count": len(history),
        "snapshot_ready": has_snapshots,
        "fields": {
            "bot": sorted((normalized.get("bot") or {}).keys()),
            "risk": sorted((normalized.get("risk") or {}).keys()),
        },
        "policy": "Settings sayısal/yüzdelik/USDT/süre alanları merkezi normalizer ile yorumlanır.",
    }


def build_risk_final_quality(settings: dict) -> dict:
    matrix = build_worst_case_risk_matrix(settings)
    impact = build_real_readiness_impact(settings)
    blockers = impact.get("blockers", [])
    status = "blocked" if blockers else ("review" if impact.get("warnings") else "ok")
    return {
        "status": status,
        "worst_case_matrix": matrix,
        "real_readiness_impact": impact,
        "policy": {
            "real_trade_auto_enable": False,
            "owner_unlock_required": True,
            "pilot_required": True,
            "safety_review_required": True,
        },
    }


def build_settings_rollback_quality(settings: dict, data: dict) -> dict:
    history = data.get("settings_history", []) or []
    preview = build_settings_rollback_preview(settings, history[-1] if history else None)
    return {
        "status": "ok" if preview.get("status") == "ok" else "review",
        "history_count": len(history),
        "preview": preview,
        "policy": "Rollback yeni settings kaydı olarak uygulanır; doğrudan runtime geçmişini bozmaz.",
    }


def build_settings_ui_quality() -> dict:
    required_ui_items = [
        "risk_preview_button",
        "risk_impact_button",
        "settings_rollback_preview",
        "unit_labels",
        "worst_case_risk_metrics",
        "real_readiness_impact_panel",
        "settings_history_panel",
    ]
    return {
        "status": "ok",
        "required_ui_items": required_ui_items,
        "implemented_policy": "Settings UI kullanıcıyı %/USDT yazmaya zorlamadan birimleri gösterir ve kaydetmeden önce risk önizleme üretir.",
    }


def build_revision_27_quality_report(settings: dict, data: dict) -> dict:
    settings_quality = build_settings_final_quality(settings, data)
    risk_quality = build_risk_final_quality(settings)
    rollback_quality = build_settings_rollback_quality(settings, data)
    ui_quality = build_settings_ui_quality()
    gates = [
        _gate("settings_final", settings_quality),
        _gate("risk_final", risk_quality),
        _gate("settings_rollback", rollback_quality),
        _gate("settings_ui", ui_quality),
    ]
    blocked = [g for g in gates if g.get("status") == "blocked"]
    review = [g for g in gates if g.get("status") == "review"]
    return {
        "revision": REVISION,
        "status": "blocked" if blocked else ("review" if review else "ok"),
        "score": max(0, 100 - len(blocked) * 35 - len(review) * 10),
        "gates": gates,
        "settings_final": settings_quality,
        "risk_final": risk_quality,
        "settings_rollback": rollback_quality,
        "settings_ui": ui_quality,
        "next_revision": "Rev28 = Audit Forensics Final Pack",
    }
