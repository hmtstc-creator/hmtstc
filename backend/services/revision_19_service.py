from services.reports_service import build_reports


def _status(ok: bool, detail: str) -> dict:
    return {"status": "ok" if ok else "review", "detail": detail}


def build_revision_19_quality_report(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    checks = {
        "reports_decision_quality": build_reports_decision_quality_report(data, settings, period),
        "paper_lab_panel": build_paper_lab_decision_report(data, settings, period),
        "execution_quality": build_execution_quality_report(data, settings, period),
        "score_breakdown": build_model_score_breakdown_report(data, settings, period),
        "recommendation_explanation": build_recommendation_explanation_report(data, settings, period),
        "attribution": build_attribution_quality_report(data, settings, period),
    }
    ok_count = sum(1 for item in checks.values() if item.get("status") == "ok")
    return {
        "status": "ok" if ok_count >= 4 else "review",
        "revision": 19,
        "title": "Reports + Paper Lab Decision Quality",
        "period": period,
        "readiness_score": round(ok_count / max(len(checks), 1) * 100, 2),
        "checks": checks,
        "models_count": len(report.get("model_ranking", []) or []),
        "message": "Rev19 Reports ekranını model karar merkezi, execution quality, score breakdown ve recommendation explanation katmanlarıyla güçlendirir.",
    }


def build_reports_decision_quality_report(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    dq = report.get("decision_quality") or {}
    return {
        "status": dq.get("status", "review"),
        "readiness_score": dq.get("readiness_score", 0),
        "checks": dq.get("checks", []),
    }


def build_paper_lab_decision_report(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    lab = report.get("paper_lab") or {}
    rankings = report.get("model_ranking") or []
    return {
        "status": "ok" if lab.get("models_count", 0) > 0 and rankings else "review",
        "models_count": lab.get("models_count", 0),
        "last_run_at": lab.get("last_run_at"),
        "best_model": (rankings[0] if rankings else {}).get("model_id"),
        "fields": ["wallet_value", "realized_pnl", "unrealized_pnl", "execution_quality_score", "stability_score", "score_components"],
    }


def build_execution_quality_report(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    eq = report.get("execution_quality_summary") or {}
    return {
        "status": eq.get("status", "review"),
        "avg_execution_quality": eq.get("avg_execution_quality", 0),
        "low_quality_count": eq.get("low_quality_count", 0),
        "low_quality_models": eq.get("low_quality_models", []),
        "message": eq.get("message"),
    }


def build_model_score_breakdown_report(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    sb = report.get("score_breakdown") or {}
    components = sb.get("components") or {}
    required = {"pnl", "profit_factor", "drawdown", "win_rate", "trade_count", "stability", "exposure", "execution_quality"}
    present = set(components.keys())
    return {
        "status": "ok" if required.intersection(present) else sb.get("status", "review"),
        "avg_score": sb.get("avg_score", 0),
        "avg_stability": sb.get("avg_stability", 0),
        "avg_execution_quality": sb.get("avg_execution_quality", 0),
        "components": components,
        "missing_components": sorted(required - present) if components else [],
    }


def build_recommendation_explanation_report(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    exp = report.get("recommendation_explanation") or {}
    return {
        "status": "ok" if exp.get("reason") or exp.get("human_summary") else "review",
        "action": exp.get("action"),
        "candidate_model_id": exp.get("candidate_model_id"),
        "blockers": exp.get("blockers", []),
        "human_summary": exp.get("human_summary"),
        "auto_apply": exp.get("auto_apply", False),
    }


def build_attribution_quality_report(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    attr = report.get("attribution_summary") or {}
    return {
        "status": attr.get("status", "review"),
        "best_filter": attr.get("best_filter"),
        "best_strategy": attr.get("best_strategy"),
        "best_risk_profile": attr.get("best_risk_profile"),
        "filter_count": attr.get("filter_count", 0),
        "strategy_count": attr.get("strategy_count", 0),
        "risk_profile_count": attr.get("risk_profile_count", 0),
    }
