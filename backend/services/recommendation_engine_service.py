from __future__ import annotations

from datetime import datetime

from core.storage import now_iso
from services.model_scoring_service import build_model_score_report, FINAL_SCORE_CRITERIA
from services.paper_lab_service import ensure_paper_lab


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _fresh(value, seconds: int) -> bool:
    stamp = _parse_iso(value)
    if not stamp:
        return False
    return max(0, (datetime.now(stamp.tzinfo) - stamp).total_seconds()) <= seconds


def _runtime_gate(data: dict) -> dict:
    problems = []
    if data.get("bot_running"):
        if not _fresh(data.get("last_tick"), 180):
            problems.append("bot_tick_stale")
        if not _fresh((data.get("last_scan") or {}).get("time"), 300):
            problems.append("scan_stale")
    if data.get("emergency_lock") or ((data.get("real_trade") or {}).get("emergency_lock")):
        problems.append("emergency_lock_active")
    return {"status": "ok" if not problems else "blocked", "problems": problems}


RECOMMENDATION_FINAL_CRITERIA = {
    "min_score_delta_switch": 8.0,
    "min_score_delta_candidate": 4.0,
    "min_confidence_switch": 70.0,
    "auto_apply": False,
}


def build_recommendation_final(data: dict, settings: dict | None = None) -> dict:
    lab = ensure_paper_lab(data)
    active_id = lab.get("active_real_model_id")
    score_report = build_model_score_report(data, settings or {})
    models = score_report.get("models", [])
    best = models[0] if models else None
    active = next((row for row in models if row.get("model_id") == active_id), None)
    runtime = _runtime_gate(data)
    blockers = []
    warnings = []

    if runtime.get("status") != "ok":
        blockers.extend(runtime.get("problems", []))
    if not best:
        return {
            "status": "review",
            "action": "WAIT_FOR_DATA",
            "reason": "Model skorlaması için paper veri bekleniyor.",
            "candidate_model_id": None,
            "active_model_id": active_id,
            "score_delta": 0,
            "confidence_score": 0,
            "blockers": ["no_model_score_data"],
            "warnings": [],
            "score_report_summary": score_report.get("summary"),
            "criteria": {**FINAL_SCORE_CRITERIA, **RECOMMENDATION_FINAL_CRITERIA},
            "auto_apply": False,
        }

    best_score = _safe_float(best.get("final_score"))
    active_score = _safe_float((active or {}).get("final_score"))
    score_delta = round(best_score - active_score, 2)
    total_trades = int(best.get("total_trades") or 0)
    drawdown = abs(_safe_float(best.get("max_drawdown_percent")))
    stability = _safe_float(best.get("stability_score"))
    execution = _safe_float(best.get("execution_quality_score"))
    candidate_ready = bool(best.get("candidate_ready"))
    switch_ready = bool(best.get("switch_ready"))

    if total_trades < FINAL_SCORE_CRITERIA["min_trades_candidate"]:
        blockers.append("minimum_sample_not_met")
    if drawdown > FINAL_SCORE_CRITERIA["max_drawdown_candidate_pct"]:
        blockers.append("drawdown_gate_failed")
    if stability < FINAL_SCORE_CRITERIA["min_stability_candidate"]:
        blockers.append("stability_gate_failed")
    if execution < FINAL_SCORE_CRITERIA["min_execution_quality_candidate"]:
        blockers.append("execution_quality_gate_failed")
    if best.get("final_score", 0) < FINAL_SCORE_CRITERIA["min_final_score_candidate"]:
        blockers.append("final_score_too_low")
    if score_delta < RECOMMENDATION_FINAL_CRITERIA["min_score_delta_candidate"] and best.get("model_id") != active_id:
        warnings.append("score_delta_low")

    if best.get("model_id") == active_id:
        action = "KEEP_CURRENT"
        reason = "Aktif real model final scoring içinde lider veya yeterince güçlü görünüyor."
    elif blockers:
        action = "WATCH"
        reason = "Aday model izleniyor; switch için kalite kapıları tam geçilmedi."
    elif switch_ready and score_delta >= RECOMMENDATION_FINAL_CRITERIA["min_score_delta_switch"]:
        action = "SWITCH_RECOMMENDED"
        reason = "Aday model final skor, sample depth, drawdown, stability ve execution kapılarını geçti. Owner approval gerekir."
    elif candidate_ready:
        action = "CANDIDATE_READY"
        reason = "Aday model güçlü; skor farkı veya switch eşiği için izleme devam etmeli."
    else:
        action = "WATCH"
        reason = "Aday model izleniyor; henüz switch için yeterli güven yok."

    confidence = min(100, max(0, best_score * 0.65 + min(100, total_trades * 3) * 0.15 + stability * 0.1 + execution * 0.1))
    if blockers:
        confidence = min(confidence, 55)

    return {
        "status": "ok" if action in {"KEEP_CURRENT", "CANDIDATE_READY", "SWITCH_RECOMMENDED"} else "review",
        "action": action,
        "reason": reason,
        "candidate_model_id": best.get("model_id"),
        "active_model_id": active_id,
        "candidate": best,
        "active": active,
        "score_delta": score_delta,
        "confidence_score": round(confidence, 2),
        "blockers": blockers,
        "warnings": warnings,
        "runtime_gate": runtime,
        "score_report_summary": score_report.get("summary"),
        "criteria": {**FINAL_SCORE_CRITERIA, **RECOMMENDATION_FINAL_CRITERIA},
        "auto_apply": False,
        "requires_owner_approval": action == "SWITCH_RECOMMENDED",
        "generated_at": now_iso(),
    }


def build_recommendation_history_snapshot(data: dict, settings: dict | None = None, persist_snapshot: bool = False) -> dict:
    recommendation = build_recommendation_final(data, settings or {})
    if persist_snapshot:
        history = data.setdefault("recommendation_history", [])
        history.append({
            "time": now_iso(),
            "action": recommendation.get("action"),
            "candidate_model_id": recommendation.get("candidate_model_id"),
            "active_model_id": recommendation.get("active_model_id"),
            "score_delta": recommendation.get("score_delta"),
            "confidence_score": recommendation.get("confidence_score"),
            "blockers": recommendation.get("blockers", []),
            "auto_apply": False,
        })
        data["recommendation_history"] = history[-250:]
    return {"status": "ok", "recommendation": recommendation, "history_count": len(data.get("recommendation_history", []) or [])}
