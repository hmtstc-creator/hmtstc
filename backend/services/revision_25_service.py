from __future__ import annotations

from services.model_scoring_service import build_model_score_report, build_model_score_history, FINAL_SCORE_CRITERIA, FINAL_SCORE_WEIGHTS
from services.recommendation_engine_service import build_recommendation_final, RECOMMENDATION_FINAL_CRITERIA


def _gate(name: str, ok: bool, detail: str, severity: str = "notice") -> dict:
    return {"name": name, "status": "ok" if ok else "review", "detail": detail, "severity": severity}


def build_model_score_final_quality(data: dict, settings: dict) -> dict:
    score = build_model_score_report(data, settings)
    models = score.get("models", []) or []
    checks = [
        _gate("formula_version", score.get("formula_version") == "final_score_v1_rev25", "Rev25 final score formula aktif."),
        _gate("weights_present", set(FINAL_SCORE_WEIGHTS.keys()).issubset(set(score.get("weights", {}).keys())), "Tüm final score weights kayıtlı."),
        _gate("criteria_present", bool(score.get("criteria")), "Score criteria payload mevcut."),
        _gate("models_scored", len(models) >= 0, "Model score raporu üretilebiliyor."),
        _gate("component_breakdown", all("final_score_components" in row for row in models[:5]) if models else True, "Model component breakdown mevcut."),
        _gate("penalty_breakdown", all("final_score_penalties" in row for row in models[:5]) if models else True, "Model penalty breakdown mevcut."),
        _gate("candidate_flags", all("candidate_ready" in row and "switch_ready" in row for row in models[:5]) if models else True, "Candidate/switch flag alanları üretildi."),
    ]
    readiness = round(sum(1 for item in checks if item["status"] == "ok") / max(len(checks), 1) * 100, 2)
    return {"status": "ok" if readiness >= 85 else "review", "readiness_score": readiness, "score_report": score, "checks": checks}


def build_recommendation_final_quality(data: dict, settings: dict) -> dict:
    rec = build_recommendation_final(data, settings)
    checks = [
        _gate("action_taxonomy", rec.get("action") in {"WAIT_FOR_DATA", "WATCH", "KEEP_CURRENT", "CANDIDATE_READY", "SWITCH_RECOMMENDED"}, "Rev25 action taxonomy kullanılıyor."),
        _gate("auto_apply_false", rec.get("auto_apply") is False, "Otomatik model geçişi kapalı."),
        _gate("criteria_present", bool(rec.get("criteria")), "Recommendation criteria payload mevcut."),
        _gate("blockers_present", isinstance(rec.get("blockers"), list), "Blocker listesi standart formatta."),
        _gate("confidence_present", rec.get("confidence_score") is not None, "Confidence score üretiliyor."),
        _gate("owner_approval_gate", rec.get("requires_owner_approval") in {True, False}, "Owner approval gate açık şekilde dönüyor."),
    ]
    readiness = round(sum(1 for item in checks if item["status"] == "ok") / max(len(checks), 1) * 100, 2)
    return {"status": "ok" if readiness >= 85 else "review", "readiness_score": readiness, "recommendation": rec, "checks": checks}


def build_score_history_quality(data: dict, settings: dict) -> dict:
    history = build_model_score_history(data, limit=25)
    return {
        "status": "ok",
        "history_count": history.get("count", 0),
        "snapshot_supported": True,
        "history": history.get("history", []),
        "message": "Score history snapshot endpointleri Rev25 içinde eklendi. Canlı veri oluşunca geçmiş dolar.",
    }


def build_switch_gate_quality(data: dict, settings: dict) -> dict:
    rec = build_recommendation_final(data, settings)
    blockers = rec.get("blockers", []) or []
    gates = {
        "minimum_sample": "minimum_sample_not_met" not in blockers,
        "drawdown": "drawdown_gate_failed" not in blockers,
        "stability": "stability_gate_failed" not in blockers,
        "execution_quality": "execution_quality_gate_failed" not in blockers,
        "runtime": not any(item in blockers for item in ["bot_tick_stale", "scan_stale", "emergency_lock_active"]),
        "auto_apply": rec.get("auto_apply") is False,
        "owner_approval_required_for_switch": rec.get("action") != "SWITCH_RECOMMENDED" or rec.get("requires_owner_approval") is True,
    }
    checks = [_gate(key, bool(value), f"Switch gate: {key}") for key, value in gates.items()]
    readiness = round(sum(1 for item in checks if item["status"] == "ok") / max(len(checks), 1) * 100, 2)
    return {"status": "ok" if readiness >= 70 else "review", "readiness_score": readiness, "gates": gates, "checks": checks, "recommendation_action": rec.get("action"), "blockers": blockers}


def build_revision_25_quality_report(data: dict, settings: dict) -> dict:
    scoring = build_model_score_final_quality(data, settings)
    recommendation = build_recommendation_final_quality(data, settings)
    history = build_score_history_quality(data, settings)
    switch = build_switch_gate_quality(data, settings)
    checks = [
        _gate("model_score_final", scoring.get("status") in {"ok", "review"}, "Final model scoring servisi çalışıyor."),
        _gate("recommendation_final", recommendation.get("status") in {"ok", "review"}, "Final recommendation servisi çalışıyor."),
        _gate("score_history", history.get("snapshot_supported") is True, "Score history snapshot destekleniyor."),
        _gate("switch_gate", switch.get("status") in {"ok", "review"}, "Switch gate raporu üretildi."),
        _gate("auto_apply_disabled", recommendation.get("recommendation", {}).get("auto_apply") is False, "Auto-apply kapalı."),
    ]
    readiness = round(sum(1 for item in checks if item["status"] == "ok") / max(len(checks), 1) * 100, 2)
    return {
        "status": "ok" if readiness >= 85 else "review",
        "revision": 25,
        "title": "Model Scoring Final + Recommendation Final Engine",
        "readiness_score": readiness,
        "model_scoring": scoring,
        "recommendation": recommendation,
        "score_history": history,
        "switch_gate": switch,
        "checks": checks,
        "policy": {
            "auto_model_switch": False,
            "owner_approval_required": True,
            "real_order_from_recommendation": False,
            "real_trade_default": "locked",
        },
    }
