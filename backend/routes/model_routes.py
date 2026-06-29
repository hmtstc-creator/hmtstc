from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_owner, require_user
from core.config import DEFAULT_USER
from core.storage import append_audit, load_shadow, load_settings, now_iso, save_shadow
from services.model_registry import build_model_registry
from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.real_trade_safety_service import (
    build_real_model_approval,
    build_real_trade_safety_status,
    build_runtime_health,
    build_weighted_recommendation,
)
from services.reports_service import build_reports, archive_report_snapshot, archive_standard_report_set, build_report_archive_schema, list_report_archives, report_to_csv
from services.real_order_adapter import build_real_order_dry_run


router = APIRouter(
    prefix="/api/models",
    tags=["models"]
)


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/registry")
def model_registry(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    registry = build_model_registry(include_secondary=True)
    registry["user"] = user
    return registry


@router.get("/paper-lab")
def paper_lab_status(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    data["username"] = user
    lab = ensure_paper_lab(data)
    save_shadow(data, user)

    return {
        "status": "ok",
        "user": user,
        "active_real_model_id": lab.get("active_real_model_id"),
        "registry_count": lab.get("registry_count"),
        "last_run_at": lab.get("last_run_at"),
        "last_scan_id": lab.get("last_scan_id"),
        "last_opened_count": lab.get("last_opened_count", 0),
        "rankings": get_model_rankings(data),
    }


@router.get("/reports")
def reports(
    period: str = "7d",
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    data = load_shadow(user)
    data["username"] = user
    settings = load_settings(user)
    report = build_reports(data, settings, period=period)
    save_shadow(data, user)
    report["user"] = user
    return report


@router.get("/recommendation")
def model_recommendation(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    return {
        "status": "ok",
        "user": user,
        "recommendation": build_weighted_recommendation(data, settings),
        "runtime_health": build_runtime_health(data, settings),
        "real_trade_safety": build_real_trade_safety_status(data, settings),
    }


@router.get("/real-approval")
def real_model_approval(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_real_model_approval(data, settings)
    payload["user"] = user
    return payload


@router.post("/real-approval/decision")
def real_model_approval_decision(payload: dict, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    approval = build_real_model_approval(data, settings)
    recommendation = approval.get("recommendation") or {}
    decision = str((payload or {}).get("decision") or "").lower()
    candidate_id = str((payload or {}).get("candidate_model_id") or recommendation.get("candidate_model_id") or "")
    rankings = get_model_rankings(data)
    candidate = next((row for row in rankings if row.get("model_id") == candidate_id), None)

    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision approve veya reject olmalı.")
    if not candidate:
        raise HTTPException(status_code=400, detail="Aday model bulunamadı.")

    lab = ensure_paper_lab(data)
    if decision == "approve":
        if recommendation.get("action") != "SWITCH_TO_NEW_MODEL":
            raise HTTPException(status_code=400, detail="Bu model için geçiş önerisi henüz yeterli değil.")
        lab["previous_real_model_id"] = lab.get("active_real_model_id")
        lab["active_real_model_id"] = candidate_id
        result = "approved"
        message = f"Real model adayı onaylandı: {candidate_id}. Gerçek trade emri açılmaz; sadece seçili model güncellendi."
    else:
        result = "rejected"
        message = f"Real model adayı reddedildi: {candidate_id}."

    data["paper_lab"] = lab
    data["real_model_approval"] = {
        "decision": result,
        "candidate_model_id": candidate_id,
        "decided_by": user,
        "decided_at": now_iso(),
        "recommendation_action": recommendation.get("action"),
        "auto_trade_enabled": False,
    }
    append_audit(data, "real_model_approval", "ok", message, {"candidate_model_id": candidate_id, "decision": result}, user=user)
    save_shadow(data, user)
    return {"status": "ok", "user": user, "decision": result, "candidate_model_id": candidate_id, "active_real_model_id": lab.get("active_real_model_id"), "real_order_created": False}

@router.get("/reports/export")
def reports_export(period: str = "7d", format: str = "json", current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    report = build_reports(data, settings, period=period)
    save_shadow(data, user)
    report["explanation"] = __import__("services.reports_service", fromlist=["build_report_explanation"]).build_report_explanation(report)
    if str(format).lower() == "csv":
        return {"status": "ok", "user": user, "format": "csv", "exported_at": now_iso(), "csv": report_to_csv(report)}
    return {"status": "ok", "user": user, "format": "json", "exported_at": now_iso(), "report": report}


@router.post("/reports/archive")
def reports_archive(period: str = "7d", current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    snapshot = archive_report_snapshot(data, settings, period=period)
    append_audit(data, "reports_archive", "ok", f"Rapor snapshot alındı: {period}", {"period": period, "snapshot_id": snapshot.get("id")}, user=user)
    save_shadow(data, user)
    return {"status": "ok", "user": user, "snapshot": snapshot}


@router.get("/reports/archive")
def reports_archive_list(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = list_report_archives(data, limit=limit)
    payload["user"] = user
    return payload


@router.post("/real-order/dry-run")
def real_order_dry_run(payload: dict, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    result = build_real_order_dry_run(data, settings, payload or {})
    append_audit(data, "real_order_dry_run", "ok" if result.get("status") != "blocked" else "blocked", result.get("message"), {"symbol": result.get("symbol"), "blockers": result.get("blockers")}, user=user)
    save_shadow(data, user)
    return result

from services.model_scoring_service import build_model_score_report, build_model_score_history
from services.recommendation_engine_service import build_recommendation_final, build_recommendation_history_snapshot


@router.get("/score-final")
def model_score_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_model_score_report(data, settings)
    payload["user"] = user
    return payload


@router.post("/score-final/snapshot")
def model_score_final_snapshot(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_model_score_report(data, settings, persist_snapshot=True)
    save_shadow(data, user)
    payload["user"] = user
    return payload


@router.get("/score-final/history")
def model_score_final_history(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = build_model_score_history(data, limit=limit)
    payload["user"] = user
    return payload


@router.get("/recommendation-final")
def model_recommendation_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_recommendation_final(data, settings)
    payload["user"] = user
    return payload


@router.post("/recommendation-final/snapshot")
def model_recommendation_final_snapshot(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_recommendation_history_snapshot(data, settings, persist_snapshot=True)
    save_shadow(data, user)
    payload["user"] = user
    return payload

from services.execution_calibration_service import build_execution_calibration_report, build_simulator_drift_report
from services.replay_explainability_service import (
    build_evidence_chain,
    build_replay_index_final,
    build_reports_replay_final,
    build_trade_explanation,
    compare_report_archives,
)


@router.get("/trade-explain")
def model_trade_explain(trade_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "trade_explainability": build_trade_explanation(load_shadow(user), load_settings(user), trade_id=trade_id)}


@router.get("/replay-index")
def model_replay_index(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "replay": build_replay_index_final(load_shadow(user), load_settings(user), limit=limit)}


@router.get("/evidence-chain")
def model_evidence_chain(trade_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "evidence_chain": build_evidence_chain(load_shadow(user), load_settings(user), trade_id=trade_id)}


@router.get("/reports/compare")
def model_reports_compare(a_id: str | None = None, b_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "compare": compare_report_archives(load_shadow(user), a_id=a_id, b_id=b_id)}


@router.get("/reports/replay-final")
def model_reports_replay_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "reports_replay_final": build_reports_replay_final(load_shadow(user), load_settings(user))}


# --- Level1 Rev46 Reports / Replay / Explainability Final Routes ---

@router.get("/reports/archive/schema")
def reports_archive_schema(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_report_archive_schema()
    payload["user"] = user
    return payload


@router.post("/reports/archive/daily")
def reports_archive_daily(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    snapshot = archive_report_snapshot(data, settings, period="1d")
    append_audit(data, "reports_archive_daily", "ok", "Günlük rapor snapshot alındı.", {"snapshot_id": snapshot.get("id")}, user=user)
    save_shadow(data, user)
    return {"status": "ok", "user": user, "snapshot": snapshot}


@router.post("/reports/archive/weekly-monthly")
def reports_archive_weekly_monthly(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    weekly = archive_report_snapshot(data, settings, period="7d")
    monthly = archive_report_snapshot(data, settings, period="30d")
    append_audit(data, "reports_archive_weekly_monthly", "ok", "Haftalık/aylık rapor snapshot alındı.", {"weekly": weekly.get("id"), "monthly": monthly.get("id")}, user=user)
    save_shadow(data, user)
    return {"status": "ok", "user": user, "snapshots": {"weekly": weekly, "monthly": monthly}}


@router.post("/reports/archive/standard-set")
def reports_archive_standard_set(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = archive_standard_report_set(data, settings)
    append_audit(data, "reports_archive_standard_set", "ok", "Daily/weekly/monthly rapor seti alındı.", {"snapshot_ids": [v.get("id") for v in (payload.get("snapshots") or {}).values()]}, user=user)
    save_shadow(data, user)
    payload["user"] = user
    return payload


@router.get("/reports/execution-calibration")
def reports_execution_calibration(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_execution_calibration_report(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload


@router.get("/reports/simulator-drift")
def reports_simulator_drift(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_simulator_drift_report(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload


@router.get("/reports/export-snapshot")
def reports_export_snapshot(period: str = "7d", current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    report = build_reports(data, settings, period=period)
    return {
        "status": "ok",
        "user": user,
        "period": period,
        "json_snapshot": report,
        "csv_snapshot": report_to_csv(report),
        "policy": {"export_is_read_only": True, "no_trade_side_effect": True},
    }


@router.get("/reports/why-open")
def reports_why_open(trade_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    explanation = build_trade_explanation(load_shadow(user), load_settings(user), trade_id=trade_id)
    return {"status": explanation.get("status"), "user": user, "trade_id": explanation.get("trade_id"), "why_open": explanation.get("why_open") or explanation.get("why_entered"), "explanation": explanation}


@router.get("/reports/why-close")
def reports_why_close(trade_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    explanation = build_trade_explanation(load_shadow(user), load_settings(user), trade_id=trade_id)
    return {"status": explanation.get("status"), "user": user, "trade_id": explanation.get("trade_id"), "why_close": explanation.get("why_close") or explanation.get("why_exited"), "explanation": explanation}


@router.get("/reports/why-profit-loss")
def reports_why_profit_loss(trade_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    explanation = build_trade_explanation(load_shadow(user), load_settings(user), trade_id=trade_id)
    return {"status": explanation.get("status"), "user": user, "trade_id": explanation.get("trade_id"), "why_profit_loss": explanation.get("why_profit_loss") or explanation.get("why_won_or_lost"), "explanation": explanation}

# --- Level1 Rev47 Paper Lab / Model / Recommendation Quality Routes ---
from services.paper_model_recommendation_quality_service import (
    build_model_score_component_explanation,
    build_model_score_history_report,
    build_model_scoring_regression_report,
    build_paper_model_recommendation_quality_report,
    build_paper_position_integrity_report,
    build_paper_wallet_integrity_report,
    build_real_paper_divergence_penalty_report,
    build_recommendation_decision_table,
    build_recommendation_history_report,
    build_recommendation_replay_linkage,
)


@router.get("/paper-lab/wallet-integrity")
def paper_lab_wallet_integrity(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_paper_wallet_integrity_report(load_shadow(user))
    payload["user"] = user
    return payload


@router.get("/paper-lab/position-integrity")
def paper_lab_position_integrity(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_paper_position_integrity_report(load_shadow(user))
    payload["user"] = user
    return payload


@router.get("/score-regression")
def model_score_regression(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_model_scoring_regression_report(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload


@router.get("/score-components")
def model_score_components(model_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_model_score_component_explanation(load_shadow(user), load_settings(user), model_id=model_id)
    payload["user"] = user
    return payload


@router.get("/score-history")
def model_score_history_report(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_model_score_history_report(load_shadow(user), load_settings(user), limit=limit)
    payload["user"] = user
    return payload


@router.get("/recommendation/decision-table")
def recommendation_decision_table(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_recommendation_decision_table(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload


@router.get("/recommendation/history-final")
def recommendation_history_final(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_recommendation_history_report(load_shadow(user), load_settings(user), limit=limit)
    payload["user"] = user
    return payload


@router.get("/recommendation/replay-linkage")
def recommendation_replay_linkage(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_recommendation_replay_linkage(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload


@router.get("/real-paper-divergence-penalty")
def real_paper_divergence_penalty(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_real_paper_divergence_penalty_report(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload


@router.get("/quality/model-recommendation")
def model_recommendation_quality(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_paper_model_recommendation_quality_report(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload
