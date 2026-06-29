from collections import defaultdict

from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.real_trade_safety_service import build_real_trade_safety_status, build_weighted_recommendation, build_runtime_health
from services.performance_service import get_trade_stats, total_pnl_value, shadow_wallet_value, calculate_max_drawdown
from services.execution_calibration_service import build_execution_calibration_report, build_simulator_drift_report
from services.model_scoring_service import build_model_score_report
from services.recommendation_engine_service import build_recommendation_final


def _safe_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _aggregate(rows: list[dict], key: str) -> list[dict]:
    groups = defaultdict(lambda: {
        "total_pnl": 0.0,
        "score_sum": 0.0,
        "count": 0,
        "trades": 0,
        "wins_weighted": 0.0,
        "drawdown_sum": 0.0,
        "profit_factor_sum": 0.0,
        "eligible": 0,
    })

    for row in rows:
        group_key = row.get(key) or "-"
        trades = int(row.get("total_trades") or 0)
        groups[group_key]["total_pnl"] += _safe_float(row.get("total_pnl"))
        groups[group_key]["score_sum"] += _safe_float(row.get("score"))
        groups[group_key]["count"] += 1
        groups[group_key]["trades"] += trades
        groups[group_key]["wins_weighted"] += _safe_float(row.get("win_rate")) * max(trades, 1)
        groups[group_key]["drawdown_sum"] += abs(_safe_float(row.get("max_drawdown_percent")))
        groups[group_key]["profit_factor_sum"] += _safe_float(row.get("profit_factor"))
        groups[group_key]["eligible"] += 1 if row.get("eligible_for_real") else 0

    result = []
    for group_key, item in groups.items():
        count = item["count"] or 1
        trades = item["trades"] or 1
        result.append({
            key: group_key,
            "models_count": item["count"],
            "total_pnl": round(item["total_pnl"], 4),
            "avg_score": round(item["score_sum"] / count, 2),
            "total_trades": item["trades"],
            "weighted_win_rate": round(item["wins_weighted"] / trades, 2),
            "avg_drawdown_percent": round(item["drawdown_sum"] / count, 4),
            "avg_profit_factor": round(item["profit_factor_sum"] / count, 4),
            "eligible_models": item["eligible"],
        })

    result.sort(key=lambda row: (row["avg_score"], row["total_pnl"], row["total_trades"]), reverse=True)
    return result




def _score_band(value: float) -> str:
    value = _safe_float(value)
    if value >= 75:
        return "strong"
    if value >= 55:
        return "watch"
    if value > 0:
        return "weak"
    return "no_data"


def _build_score_breakdown(rankings: list[dict]) -> dict:
    if not rankings:
        return {
            "status": "waiting_for_data",
            "models_count": 0,
            "strong_models": 0,
            "watch_models": 0,
            "weak_models": 0,
            "avg_score": 0,
            "avg_execution_quality": 0,
            "avg_stability": 0,
            "components": {},
            "message": "Paper Lab modeli henüz skor üretmedi.",
        }
    components = defaultdict(float)
    component_count = 0
    for row in rankings:
        for key, value in (row.get("score_components") or {}).items():
            components[key] += _safe_float(value)
        if row.get("score_components"):
            component_count += 1
    count = len(rankings) or 1
    buckets = {"strong": 0, "watch": 0, "weak": 0, "no_data": 0}
    for row in rankings:
        buckets[_score_band(row.get("score"))] += 1
    return {
        "status": "ok",
        "models_count": len(rankings),
        "strong_models": buckets["strong"],
        "watch_models": buckets["watch"],
        "weak_models": buckets["weak"],
        "no_data_models": buckets["no_data"],
        "avg_score": round(sum(_safe_float(row.get("score")) for row in rankings) / count, 2),
        "avg_execution_quality": round(sum(_safe_float(row.get("execution_quality_score")) for row in rankings) / count, 2),
        "avg_stability": round(sum(_safe_float(row.get("stability_score")) for row in rankings) / count, 2),
        "components": {key: round(value / max(component_count, 1), 2) for key, value in components.items()},
        "message": "Model skoru PnL, drawdown, win rate, trade count, stability, exposure ve execution quality bileşenlerinden hesaplandı.",
    }


def _build_execution_quality_summary(rankings: list[dict]) -> dict:
    if not rankings:
        return {"status": "waiting_for_data", "avg_execution_quality": 0, "low_quality_models": [], "message": "Execution örneği bekleniyor."}
    low = [row for row in rankings if _safe_float(row.get("execution_quality_score"), 50) < 45]
    high = [row for row in rankings if _safe_float(row.get("execution_quality_score"), 50) >= 70]
    return {
        "status": "review" if low else "ok",
        "avg_execution_quality": round(sum(_safe_float(row.get("execution_quality_score"), 50) for row in rankings) / len(rankings), 2),
        "high_quality_models": [row.get("model_id") for row in high[:10]],
        "low_quality_models": [row.get("model_id") for row in low[:10]],
        "low_quality_count": len(low),
        "message": "Düşük execution quality olan modeller gerçek aday değerlendirmesinde cezalandırılır.",
    }


def _build_recommendation_explanation(recommendation: dict, rankings: list[dict], runtime_health: dict, safety: dict) -> dict:
    action = recommendation.get("action") or "WATCH"
    candidate_id = recommendation.get("candidate_model_id") or recommendation.get("recommended_model_id")
    candidate = next((row for row in rankings if row.get("model_id") == candidate_id), None)
    blockers = []
    if runtime_health.get("status") not in {"healthy", "ok", None}:
        blockers.append("runtime_health_not_clean")
    if safety.get("status") not in {"locked", "blocked", "safe", "ok", None} and safety.get("real_order_allowed") is False:
        blockers.append("real_trade_safety_locked")
    if candidate and _safe_float(candidate.get("total_trades")) < 5:
        blockers.append("minimum_trade_count_not_met")
    if candidate and _safe_float(candidate.get("execution_quality_score"), 50) < 45:
        blockers.append("execution_quality_too_low")
    if candidate and abs(_safe_float(candidate.get("max_drawdown_percent"))) > 8:
        blockers.append("drawdown_too_high")
    if candidate and _safe_float(candidate.get("stability_score")) < 55:
        blockers.append("stability_too_low")
    return {
        "action": action,
        "candidate_model_id": candidate_id,
        "candidate_found": bool(candidate),
        "reason": recommendation.get("reason") or "Karar motoru izleme modunda.",
        "score_delta": recommendation.get("score_delta", 0),
        "blockers": blockers,
        "human_summary": build_report_explanation({"recommendation": recommendation, "real_vs_paper": {"best_paper_model": rankings[0] if rankings else None}}),
        "auto_apply": False,
        "requires_owner_approval": action in {"SWITCH_TO_NEW_MODEL", "SWITCH_RECOMMENDED", "CANDIDATE_READY"},
    }


def _build_attribution_summary(rankings: list[dict]) -> dict:
    filters = _aggregate(rankings, "filter_id")
    strategies = _aggregate(rankings, "strategy_id")
    return {
        "status": "ok" if rankings else "waiting_for_data",
        "best_filter": filters[0] if filters else None,
        "best_strategy": strategies[0] if strategies else None,
        "filter_count": len(filters),
        "strategy_count": len(strategies),
        "message": "Attribution, model ranking verisinden filtre ve strateji kırılımı üretir.",
    }


def _build_paper_wallet_integrity(data: dict, rankings: list[dict]) -> dict:
    lab = ensure_paper_lab(data)
    issues = []
    checked = 0
    max_delta = 0.0
    worst_model = None

    for model_id, model in (lab.get("models") or {}).items():
        checked += 1
        wallet_start = _safe_float(model.get("wallet_start"), 1000.0)
        realized = sum(_safe_float(item.get("pnl")) for item in model.get("history", []) or [])
        unrealized = sum(_safe_float(item.get("pnl")) for item in model.get("open_positions", []) or [])
        expected_wallet = round(wallet_start + realized + unrealized, 4)
        actual_wallet = round(_safe_float(model.get("wallet_value"), expected_wallet), 4)
        delta = round(actual_wallet - expected_wallet, 4)
        abs_delta = abs(delta)
        if abs_delta > max_delta:
            max_delta = abs_delta
            worst_model = model_id
        if abs_delta > 0.05:
            issues.append({
                "model_id": model_id,
                "expected_wallet": expected_wallet,
                "actual_wallet": actual_wallet,
                "delta": delta,
            })

    return {
        "status": "ok" if not issues else "review",
        "checked_models": checked,
        "issue_count": len(issues),
        "max_delta": round(max_delta, 4),
        "worst_model_id": worst_model,
        "issues": issues[:10],
        "message": "Paper cüzdanı başlangıç bakiye + realize PnL + açık PnL formülüyle kontrol edildi.",
    }


def _build_paper_position_integrity(data: dict) -> dict:
    lab = ensure_paper_lab(data)
    open_count = 0
    closed_count = 0
    invalid_count = 0
    duplicate_count = 0
    seen_ids = set()
    issues = []

    def check_position(model_id: str, position: dict, expected_status: str):
        nonlocal open_count, closed_count, invalid_count, duplicate_count
        if expected_status == "open":
            open_count += 1
        else:
            closed_count += 1

        pos_id = str(position.get("id") or "")
        if pos_id:
            if pos_id in seen_ids:
                duplicate_count += 1
                issues.append({"model_id": model_id, "position_id": pos_id, "issue": "duplicate_position_id"})
            seen_ids.add(pos_id)

        status = str(position.get("status") or "").lower()
        symbol = position.get("symbol")
        entry = _safe_float(position.get("entry"))
        quantity = _safe_float(position.get("quantity"))
        if not symbol or entry <= 0 or quantity <= 0:
            invalid_count += 1
            issues.append({"model_id": model_id, "position_id": pos_id or "-", "issue": "invalid_symbol_entry_or_quantity"})
        if expected_status == "open" and status not in {"open", ""}:
            invalid_count += 1
            issues.append({"model_id": model_id, "position_id": pos_id or "-", "issue": "open_bucket_status_mismatch", "status": status})
        if expected_status == "closed" and status not in {"closed", ""}:
            invalid_count += 1
            issues.append({"model_id": model_id, "position_id": pos_id or "-", "issue": "history_bucket_status_mismatch", "status": status})

    for model_id, model in (lab.get("models") or {}).items():
        for position in model.get("open_positions", []) or []:
            if isinstance(position, dict):
                check_position(model_id, position, "open")
        for trade in model.get("history", []) or []:
            if isinstance(trade, dict):
                check_position(model_id, trade, "closed")

    return {
        "status": "ok" if invalid_count == 0 and duplicate_count == 0 else "review",
        "open_positions": open_count,
        "closed_positions": closed_count,
        "invalid_count": invalid_count,
        "duplicate_count": duplicate_count,
        "issues": issues[:10],
        "message": "Paper pozisyonları açık/kapalı durum, tekrar ID ve temel fiyat/adet tutarlılığıyla kontrol edildi.",
    }


def _build_report_decision_quality(rankings: list[dict], recommendation: dict, runtime_health: dict, safety: dict) -> dict:
    score = 0
    checks = []
    def add(name, ok, detail):
        nonlocal score
        checks.append({"name": name, "status": "ok" if ok else "review", "detail": detail})
        if ok:
            score += 1
    add("model_ranking", bool(rankings), "Paper Lab model ranking üretildi." if rankings else "Model ranking için paper veri bekleniyor.")
    add("score_components", any(row.get("score_components") for row in rankings), "Score component breakdown mevcut.")
    add("execution_quality", any(row.get("execution_quality_score") is not None for row in rankings), "Execution quality ranking içine dahil.")
    add("recommendation", bool(recommendation), "Recommendation payload mevcut.")
    add("runtime_health", bool(runtime_health), "Runtime health karar katmanına dahil.")
    add("safety", bool(safety), "Real trade safety karar katmanına dahil.")
    readiness = round(score / max(len(checks), 1) * 100, 2)
    return {"status": "ok" if readiness >= 80 else "review", "readiness_score": readiness, "checks": checks}

def build_reports(data: dict, settings: dict, period: str = "7d") -> dict:
    lab = ensure_paper_lab(data)
    rankings = get_model_rankings(data)
    trade_stats = get_trade_stats(data)
    points = data.get("performance_points", [])

    real_summary = {
        "mode": data.get("mode", "shadow"),
        "wallet_value": shadow_wallet_value(data),
        "total_pnl": total_pnl_value(data),
        "open_positions": len(data.get("open_positions", [])),
        "total_trades": trade_stats.get("total_trades", 0),
        "win_rate": trade_stats.get("win_rate", 0),
        "profit_factor": trade_stats.get("profit_factor", 0),
        "max_drawdown_percent": calculate_max_drawdown(points),
        "active_real_model_id": lab.get("active_real_model_id"),
    }

    best_model = rankings[0] if rankings else None
    active_real_model_id = lab.get("active_real_model_id")
    current_paper_peer = next((item for item in rankings if item.get("model_id") == active_real_model_id), None)

    recommendation = build_weighted_recommendation(data, settings)
    final_recommendation = build_recommendation_final(data, settings)
    final_model_scoring = build_model_score_report(data, settings)
    safety = build_real_trade_safety_status(data, settings)
    runtime_health = build_runtime_health(data, settings)

    filter_ranking = _aggregate(rankings, "filter_id")
    strategy_ranking = _aggregate(rankings, "strategy_id")
    return {
        "status": "ok",
        "period": period,
        "real_model": real_summary,
        "paper_lab": {
            "models_count": len(rankings),
            "last_run_at": lab.get("last_run_at"),
            "last_scan_id": lab.get("last_scan_id"),
            "last_opened_count": lab.get("last_opened_count", 0),
        },
        "model_ranking": rankings,
        "filter_ranking": filter_ranking,
        "strategy_ranking": strategy_ranking,
        "real_vs_paper": {
            "active_real_model_id": active_real_model_id,
            "paper_peer": current_paper_peer,
            "best_paper_model": best_model,
        },
        "recommendation": recommendation,
        "final_recommendation": final_recommendation,
        "final_model_scoring": final_model_scoring,
        "recommendation_explanation": _build_recommendation_explanation(final_recommendation, final_model_scoring.get("models") or rankings, runtime_health, safety),
        "real_trade_safety": safety,
        "runtime_health": runtime_health,
        "score_breakdown": _build_score_breakdown(rankings),
        "execution_quality_summary": _build_execution_quality_summary(rankings),
        "attribution_summary": _build_attribution_summary(rankings),
        "decision_quality": _build_report_decision_quality(rankings, recommendation, runtime_health, safety),
        "execution_calibration": build_execution_calibration_report(data, settings),
        "simulator_drift": build_simulator_drift_report(data, settings),
        "paper_wallet_integrity": _build_paper_wallet_integrity(data, rankings),
        "paper_position_integrity": _build_paper_position_integrity(data),
        "strategy_attribution": strategy_ranking,
        "filter_attribution": filter_ranking,
    }



def build_report_archive_schema() -> dict:
    return {
        "status": "ok",
        "schema_version": "rev46.report-archive.v1",
        "required_summary_fields": [
            "wallet_value", "total_pnl", "best_model", "best_score",
            "models_count", "candidate_models", "switch_ready_count",
            "execution_calibration_score", "paper_vs_dry_run_quality_delta",
            "paper_vs_real_quality_delta",
        ],
        "supported_periods": ["1d", "7d", "30d", "daily", "weekly", "monthly"],
        "policy": {"archive_is_read_only_for_trade": True, "archive_does_not_place_orders": True},
    }


def _archive_summary(report: dict) -> dict:
    best = ((report.get("real_vs_paper") or {}).get("best_paper_model") or {})
    rec = report.get("recommendation") or {}
    final_rec = report.get("final_recommendation") or {}
    calib = report.get("execution_calibration") or {}
    drift = calib.get("drift") or (report.get("simulator_drift") or {}).get("drift") or {}
    ranking = report.get("model_ranking") or []
    candidate_models = [row for row in ranking if row.get("eligible_for_real") or row.get("candidate_ready")]
    switch_ready = [row for row in ranking if (row.get("score") or 0) and _safe_float(row.get("score")) >= 75]
    real_model = report.get("real_model") or {}
    return {
        "wallet_value": _safe_float(real_model.get("wallet_value")),
        "total_pnl": _safe_float(real_model.get("total_pnl")),
        "best_model": best.get("model_id"),
        "best_score": _safe_float(best.get("score")),
        "models_count": (report.get("paper_lab") or {}).get("models_count", 0),
        "candidate_models": len(candidate_models),
        "switch_ready_count": len(switch_ready),
        "recommendation": final_rec.get("action") or rec.get("action"),
        "execution_calibration_score": _safe_float(calib.get("calibration_score")),
        "paper_vs_dry_run_quality_delta": drift.get("paper_vs_dry_run_quality_delta"),
        "paper_vs_real_quality_delta": drift.get("paper_vs_real_quality_delta"),
    }

def build_report_explanation(report: dict) -> str:
    rec = report.get("recommendation") or {}
    best = ((report.get("real_vs_paper") or {}).get("best_paper_model") or {})
    if not best:
        return "Henüz yeterli paper trade olmadığı için model seçimi izleme modunda."
    return (
        f"{best.get('model_id')} modeli skor={best.get('score')} ve PnL={best.get('total_pnl')} USDT ile öne çıktı. "
        f"Karar motoru aksiyonu: {rec.get('action', 'WATCH')}. Sebep: {rec.get('reason', '-')}"
    )


def archive_report_snapshot(data: dict, settings: dict, period: str = "7d") -> dict:
    report = build_reports(data, settings, period=period)
    report["explanation"] = build_report_explanation(report)
    archives = data.setdefault("report_archives", [])
    existing_same_period = sum(1 for item in archives if item.get("period") == period)
    snapshot = {
        "id": f"report_{period}_{existing_same_period + 1}",
        "period": period,
        "created_at": __import__('core.storage', fromlist=['now_iso']).now_iso(),
        "schema_version": build_report_archive_schema()["schema_version"],
        "summary": _archive_summary(report),
        "report": report,
        "policy": {"read_only_snapshot": True, "no_trade_side_effect": True},
    }
    archives.append(snapshot)
    data["report_archives"] = archives[-180:]
    return snapshot


def archive_standard_report_set(data: dict, settings: dict) -> dict:
    snapshots = {
        "daily": archive_report_snapshot(data, settings, period="1d"),
        "weekly": archive_report_snapshot(data, settings, period="7d"),
        "monthly": archive_report_snapshot(data, settings, period="30d"),
    }
    return {"status": "ok", "snapshots": snapshots, "schema": build_report_archive_schema()}

def list_report_archives(data: dict, limit: int = 50) -> dict:
    archives = list(data.get("report_archives", []) or [])[-limit:]
    return {"status": "ok", "count": len(archives), "archives": list(reversed(archives))}


def report_to_csv(report: dict) -> str:
    rows = ["rank,model_id,filter_id,strategy_id,total_pnl,score,win_rate,total_trades,max_drawdown_percent,stability_score"]
    for item in report.get("model_ranking", []) or []:
        rows.append(",".join(str(item.get(key, "")) for key in [
            "rank", "model_id", "filter_id", "strategy_id", "total_pnl", "score", "win_rate", "total_trades", "max_drawdown_percent", "stability_score"
        ]))
    return "\n".join(rows)
