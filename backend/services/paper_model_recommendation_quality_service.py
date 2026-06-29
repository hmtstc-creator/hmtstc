from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from core.storage import now_iso
from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.model_scoring_service import build_model_score_report, build_model_score_history, calculate_final_model_score
from services.recommendation_engine_service import build_recommendation_final, build_recommendation_history_snapshot
from services.replay_explainability_service import build_evidence_chain, build_replay_index_final


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _status(ok: bool, review_reason: str | None = None) -> dict:
    return {"status": "ok" if ok else "review", "review_reason": review_reason}


def _model_map(data: dict) -> dict:
    lab = ensure_paper_lab(data)
    return lab.get("models", {}) or {}


def build_paper_wallet_integrity_report(data: dict) -> dict:
    working = deepcopy(data or {})
    models = _model_map(working)
    rows = []
    failing = []
    for model_id, model in models.items():
        start = _safe_float(model.get("wallet_start"), 1000.0)
        realized = sum(_safe_float(row.get("pnl")) for row in model.get("history", []) or [])
        unrealized = sum(_safe_float(row.get("pnl")) for row in model.get("open_positions", []) or [])
        expected = round(start + realized + unrealized, 4)
        actual = round(_safe_float(model.get("wallet_value"), expected), 4)
        delta = round(actual - expected, 6)
        row = {
            "model_id": model_id,
            "wallet_start": start,
            "realized_pnl_expected": round(realized, 4),
            "unrealized_pnl_expected": round(unrealized, 4),
            "wallet_value_expected": expected,
            "wallet_value_actual": actual,
            "delta": delta,
            "ok": abs(delta) <= 0.01,
        }
        rows.append(row)
        if not row["ok"]:
            failing.append(row)
    status = "ok" if not failing else "review"
    return {
        "status": status,
        "generated_at": now_iso(),
        "model_count": len(rows),
        "failing_count": len(failing),
        "rows": rows,
        "failing": failing[:50],
        "policy": {"read_only": True, "no_store_mutation": True},
    }


def build_paper_position_integrity_report(data: dict) -> dict:
    working = deepcopy(data or {})
    models = _model_map(working)
    rows = []
    issues = []
    for model_id, model in models.items():
        open_positions = model.get("open_positions", []) or []
        history = model.get("history", []) or []
        open_ids = [str(row.get("id") or row.get("position_id") or "") for row in open_positions]
        closed_ids = [str(row.get("id") or row.get("position_id") or "") for row in history]
        duplicate_ids = sorted({pid for pid in open_ids + closed_ids if pid and (open_ids + closed_ids).count(pid) > 1})
        bad_open = [row for row in open_positions if str(row.get("status") or "open") not in {"open", "paper_open", "active"}]
        bad_closed = [row for row in history if str(row.get("status") or "closed") not in {"closed", "paper_closed", "exited"}]
        row = {
            "model_id": model_id,
            "open_count": len(open_positions),
            "closed_count": len(history),
            "duplicate_ids": duplicate_ids,
            "bad_open_status_count": len(bad_open),
            "bad_closed_status_count": len(bad_closed),
            "ok": not duplicate_ids and not bad_open and not bad_closed,
        }
        rows.append(row)
        if not row["ok"]:
            issues.append(row)
    return {
        "status": "ok" if not issues else "review",
        "generated_at": now_iso(),
        "model_count": len(rows),
        "issue_count": len(issues),
        "rows": rows,
        "issues": issues[:50],
        "policy": {"read_only": True, "no_store_mutation": True},
    }


def build_model_scoring_regression_report(data: dict, settings: dict | None = None) -> dict:
    working = deepcopy(data or {})
    report = build_model_score_report(working, deepcopy(settings or {}), persist_snapshot=False)
    rows = report.get("models", []) or []
    issues = []
    for row in rows:
        score = _safe_float(row.get("final_score"), -1)
        components = row.get("final_score_components") or {}
        if not 0 <= score <= 100:
            issues.append({"model_id": row.get("model_id"), "issue": "score_out_of_range", "score": score})
        if not components:
            issues.append({"model_id": row.get("model_id"), "issue": "missing_score_components"})
        required = {"pnl", "profit_factor", "drawdown", "win_rate", "trade_count", "stability", "exposure", "execution_quality", "sample_confidence", "consistency"}
        missing = sorted(required - set(components.keys()))
        if missing:
            issues.append({"model_id": row.get("model_id"), "issue": "component_keys_missing", "missing": missing})
    return {
        "status": "ok" if rows and not issues else "review",
        "generated_at": now_iso(),
        "formula_version": report.get("formula_version"),
        "model_count": len(rows),
        "summary": report.get("summary", {}),
        "issues": issues,
        "policy": {"read_only": True, "no_store_mutation": True},
    }


def build_model_score_component_explanation(data: dict, settings: dict | None = None, model_id: str | None = None) -> dict:
    working = deepcopy(data or {})
    report = build_model_score_report(working, deepcopy(settings or {}), persist_snapshot=False)
    models = report.get("models", []) or []
    selected = None
    if model_id:
        selected = next((row for row in models if str(row.get("model_id")) == str(model_id)), None)
    if selected is None and models:
        selected = models[0]
    if not selected:
        return {"status": "waiting_for_data", "generated_at": now_iso(), "message": "Skor açıklaması için model verisi yok.", "policy": {"read_only": True}}
    components = selected.get("final_score_components") or {}
    explanations = []
    for key, value in components.items():
        explanations.append({
            "component": key,
            "score": round(_safe_float(value), 2),
            "weight": report.get("weights", {}).get(key),
            "interpretation": _component_interpretation(key, _safe_float(value)),
        })
    return {
        "status": "ok",
        "generated_at": now_iso(),
        "model_id": selected.get("model_id"),
        "final_score": selected.get("final_score"),
        "penalties": selected.get("final_score_penalties", []),
        "components": explanations,
        "criteria": report.get("criteria"),
        "policy": {"read_only": True, "no_trade_side_effect": True},
    }


def _component_interpretation(key: str, value: float) -> str:
    level = "strong" if value >= 75 else "acceptable" if value >= 50 else "weak"
    labels = {
        "pnl": "Net kârlılık etkisi",
        "profit_factor": "Gross profit/gross loss oranı",
        "drawdown": "Zarar derinliği riski",
        "win_rate": "Kazanan işlem oranı",
        "trade_count": "Örneklem derinliği",
        "stability": "Son dönem tutarlılık",
        "exposure": "Açık risk yükü",
        "execution_quality": "Fill/slippage/fee kalitesi",
        "sample_confidence": "Veri güven seviyesi",
        "consistency": "Yakın dönem düzenlilik",
    }
    return f"{labels.get(key, key)}: {level}."


def build_recommendation_decision_table(data: dict, settings: dict | None = None) -> dict:
    recommendation = build_recommendation_final(deepcopy(data or {}), deepcopy(settings or {}))
    action = recommendation.get("action")
    rows = [
        {"gate": "runtime", "passed": recommendation.get("runtime_gate", {}).get("status") == "ok", "detail": recommendation.get("runtime_gate", {})},
        {"gate": "minimum_sample", "passed": "minimum_sample_not_met" not in recommendation.get("blockers", []), "detail": "Minimum trade sample"},
        {"gate": "drawdown", "passed": "drawdown_gate_failed" not in recommendation.get("blockers", []), "detail": "Drawdown threshold"},
        {"gate": "stability", "passed": "stability_gate_failed" not in recommendation.get("blockers", []), "detail": "Stability threshold"},
        {"gate": "execution_quality", "passed": "execution_quality_gate_failed" not in recommendation.get("blockers", []), "detail": "Execution quality threshold"},
        {"gate": "final_score", "passed": "final_score_too_low" not in recommendation.get("blockers", []), "detail": "Final score threshold"},
        {"gate": "owner_approval", "passed": not recommendation.get("auto_apply"), "detail": "Auto apply disabled; owner approval required for switch."},
    ]
    return {
        "status": recommendation.get("status", "review"),
        "generated_at": now_iso(),
        "action": action,
        "candidate_model_id": recommendation.get("candidate_model_id"),
        "active_model_id": recommendation.get("active_model_id"),
        "confidence_score": recommendation.get("confidence_score"),
        "blockers": recommendation.get("blockers", []),
        "warnings": recommendation.get("warnings", []),
        "decision_rows": rows,
        "policy": {"auto_apply": False, "requires_owner_approval": recommendation.get("requires_owner_approval", False), "read_only": True},
    }


def build_recommendation_history_report(data: dict, settings: dict | None = None, limit: int = 50) -> dict:
    working = deepcopy(data or {})
    # Build current recommendation without persisting, then merge with stored history.
    current = build_recommendation_final(working, deepcopy(settings or {}))
    history = list((data or {}).get("recommendation_history", []) or [])[-limit:]
    return {
        "status": "ok",
        "generated_at": now_iso(),
        "current": current,
        "history_count": len(history),
        "history": list(reversed(history)),
        "policy": {"read_only": True, "auto_apply": False},
    }


def build_real_paper_divergence_penalty_report(data: dict, settings: dict | None = None) -> dict:
    calibration = (data or {}).get("execution_calibration") or {}
    drift = (data or {}).get("simulator_drift") or {}
    real_trade = (data or {}).get("real_trade") or {}
    orders = real_trade.get("orders", []) or []
    dry_samples = [row for row in orders if row.get("dry_run") is True]
    real_samples = [row for row in orders if row.get("dry_run") is False]
    dry_quality = _avg([row.get("execution_quality_score") for row in dry_samples])
    real_quality = _avg([row.get("execution_quality_score") for row in real_samples])
    quality_delta = abs(dry_quality - real_quality) if dry_samples and real_samples else 0.0
    stored_delta = _safe_float((drift.get("drift") or {}).get("paper_vs_dry_run_quality_delta"), quality_delta)
    penalty = min(30.0, round(max(quality_delta, abs(stored_delta)) * 0.35, 2))
    status = "ok" if penalty <= 8 else "review"
    return {
        "status": status,
        "generated_at": now_iso(),
        "dry_run_samples": len(dry_samples),
        "real_samples": len(real_samples),
        "dry_run_avg_quality": round(dry_quality, 2),
        "real_avg_quality": round(real_quality, 2),
        "quality_delta": round(quality_delta, 2),
        "stored_drift_delta": round(stored_delta, 2),
        "recommended_score_penalty": penalty,
        "penalty_code": "real_paper_divergence" if penalty else None,
        "policy": {"read_only": True, "does_not_change_scores": True},
    }


def _avg(values: list[Any]) -> float:
    nums = [_safe_float(v) for v in values if v is not None]
    return sum(nums) / len(nums) if nums else 0.0


def build_model_score_history_report(data: dict, settings: dict | None = None, limit: int = 50) -> dict:
    current = build_model_score_report(deepcopy(data or {}), deepcopy(settings or {}), persist_snapshot=False)
    history = build_model_score_history(data or {}, limit=limit)
    return {
        "status": "ok" if current.get("models") is not None else "review",
        "generated_at": now_iso(),
        "current_summary": current.get("summary", {}),
        "current_top_models": [{"model_id": row.get("model_id"), "final_score": row.get("final_score"), "rank": row.get("final_rank")} for row in (current.get("models") or [])[:10]],
        "history": history.get("history", []),
        "history_count": history.get("count", 0),
        "policy": {"read_only": True},
    }


def build_recommendation_replay_linkage(data: dict, settings: dict | None = None) -> dict:
    working = deepcopy(data or {})
    recommendation = build_recommendation_final(working, deepcopy(settings or {}))
    replay = build_replay_index_final(working, deepcopy(settings or {}), limit=50)
    candidate_id = recommendation.get("candidate_model_id")
    replay_items = replay.get("items") or replay.get("replay_items") or []
    linked_items = []
    for item in replay_items:
        if not candidate_id or str(item.get("model_id") or item.get("candidate_model_id") or "") == str(candidate_id):
            linked_items.append(item)
    evidence = build_evidence_chain(working, deepcopy(settings or {}), trade_id=None)
    return {
        "status": "ok" if recommendation.get("status") in {"ok", "review"} else "review",
        "generated_at": now_iso(),
        "recommendation_action": recommendation.get("action"),
        "candidate_model_id": candidate_id,
        "active_model_id": recommendation.get("active_model_id"),
        "linked_replay_count": len(linked_items),
        "linked_replay_items": linked_items[:20],
        "evidence_chain": evidence,
        "linkage": {
            "score_report_summary": recommendation.get("score_report_summary"),
            "blockers": recommendation.get("blockers", []),
            "warnings": recommendation.get("warnings", []),
            "confidence_score": recommendation.get("confidence_score"),
        },
        "policy": {"read_only": True, "auto_apply": False, "no_trade_side_effect": True},
    }


def build_paper_model_recommendation_quality_report(data: dict, settings: dict | None = None) -> dict:
    settings = deepcopy(settings or {})
    data = deepcopy(data or {})
    sections = {
        "paper_wallet_integrity": build_paper_wallet_integrity_report(data),
        "paper_position_integrity": build_paper_position_integrity_report(data),
        "model_scoring_regression": build_model_scoring_regression_report(data, settings),
        "score_component_explanation": build_model_score_component_explanation(data, settings),
        "recommendation_decision_table": build_recommendation_decision_table(data, settings),
        "recommendation_history": build_recommendation_history_report(data, settings),
        "real_paper_divergence_penalty": build_real_paper_divergence_penalty_report(data, settings),
        "model_score_history": build_model_score_history_report(data, settings),
        "recommendation_replay_linkage": build_recommendation_replay_linkage(data, settings),
    }
    review_sections = [name for name, section in sections.items() if section.get("status") not in {"ok", "waiting_for_data"}]
    return {
        "status": "ok" if not review_sections else "review",
        "generated_at": now_iso(),
        "package": "level1_47_paper_model_recommendation_quality",
        "sections": sections,
        "review_sections": review_sections,
        "policy": {"read_only": True, "auto_apply": False, "no_trade_side_effect": True},
    }
