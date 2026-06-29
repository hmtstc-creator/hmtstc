from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from core.storage import now_iso
from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.rule_engine import evaluate_rule, get_active_rules


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _component(value: float, minimum: float = 0, maximum: float = 100) -> float:
    return round(max(minimum, min(maximum, value)), 2)


def build_strategy_runtime_contract(username: str) -> dict:
    _, strategies = get_active_rules(username)
    return {
        "contract": "strategy_runtime_v1",
        "mode": "live_shadow_strategy_runtime",
        "paper_lab_isolated": True,
        "active_strategy_ids": [str(item.get("id")) for item in strategies if item.get("id")],
        "active_strategies": [
            {
                "strategy_id": item.get("id"),
                "name": item.get("name"),
                "enabled": item.get("enabled", True),
                "strategy_type": item.get("strategy_type", "custom"),
            }
            for item in strategies
        ],
    }


def evaluate_strategy_candidates(username: str, candidate_handoff: dict) -> dict:
    contract = build_strategy_runtime_contract(username)
    _, strategies = get_active_rules(username)
    candidates = [
        item for item in (candidate_handoff.get("candidates") or [])
        if isinstance(item, dict) and item.get("passed") is True
    ]
    outputs = []
    approved_candidates = []

    for candidate in candidates:
        candidate_outputs = []
        for strategy in strategies:
            evaluation = evaluate_rule(strategy, candidate)
            invalid_reasons = [
                f"{item.get('metric')}:{item.get('reason')}"
                for item in (evaluation.get("failed") or []) + (evaluation.get("avoided") or [])
            ]
            if evaluation.get("reason") and not invalid_reasons:
                invalid_reasons.append(str(evaluation.get("reason")))
            passed = evaluation.get("passed") is True
            output = {
                "strategy_id": strategy.get("id"),
                "symbol": candidate.get("symbol"),
                "signal": "BUY" if passed else "NO_TRADE",
                "confidence": _component(candidate.get("score") or candidate.get("quality_score") or 0),
                "entry_reason": "all_strategy_conditions_met" if passed else None,
                "invalid_reasons": invalid_reasons,
            }
            outputs.append(output)
            candidate_outputs.append(output)

        approved = [item for item in candidate_outputs if item.get("signal") == "BUY"]
        if approved:
            selected = max(approved, key=lambda item: _safe_float(item.get("confidence")))
            approved_candidates.append({**candidate, "strategy_output": selected, "strategy_outputs": candidate_outputs})

    no_strategy = not strategies
    return {
        **contract,
        "status": "blocked" if no_strategy else "ok",
        "reason": "no_active_strategy" if no_strategy else None,
        "scan_id": candidate_handoff.get("scan_id"),
        "time": candidate_handoff.get("time"),
        "input_candidates": len(candidates),
        "outputs": outputs,
        "passed": len(approved_candidates),
        "approved_candidates": approved_candidates,
    }


FINAL_SCORE_WEIGHTS = {
    "pnl": 0.16,
    "profit_factor": 0.12,
    "drawdown": 0.15,
    "win_rate": 0.08,
    "trade_count": 0.09,
    "stability": 0.13,
    "exposure": 0.07,
    "execution_quality": 0.12,
    "sample_confidence": 0.04,
    "consistency": 0.04,
}


FINAL_SCORE_CRITERIA = {
    "min_trades_watch": 5,
    "min_trades_candidate": 10,
    "min_trades_switch": 15,
    "max_drawdown_candidate_pct": 7.0,
    "max_drawdown_switch_pct": 5.0,
    "min_stability_candidate": 60.0,
    "min_stability_switch": 70.0,
    "min_execution_quality_candidate": 50.0,
    "min_execution_quality_switch": 60.0,
    "min_final_score_candidate": 60.0,
    "min_final_score_switch": 68.0,
}


def _recent_consistency(model_state: dict) -> float:
    history = model_state.get("history", []) or []
    recent = history[-20:]
    if not recent:
        return 0.0
    wins = [row for row in recent if _safe_float(row.get("pnl")) > 0]
    recent_pnl = sum(_safe_float(row.get("pnl")) for row in recent)
    win_part = len(wins) / len(recent) * 70
    pnl_part = max(-30, min(30, recent_pnl * 2)) + 30
    return _component(win_part + pnl_part * 0.3)


def _sample_confidence(total_trades: int) -> float:
    if total_trades >= 50:
        return 100.0
    if total_trades >= 30:
        return 88.0
    if total_trades >= 20:
        return 76.0
    if total_trades >= 10:
        return 58.0
    if total_trades >= 5:
        return 38.0
    if total_trades > 0:
        return 18.0
    return 0.0


def _final_components(row: dict, model_state: dict | None = None) -> dict:
    total_pnl = _safe_float(row.get("total_pnl"))
    pf = _safe_float(row.get("profit_factor"))
    drawdown = abs(_safe_float(row.get("max_drawdown_percent")))
    win_rate = _safe_float(row.get("win_rate"))
    total_trades = _safe_int(row.get("total_trades"))
    stability = _safe_float(row.get("stability_score"))
    exposure = _safe_float(row.get("risk_exposure_percent"))
    execution = _safe_float(row.get("execution_quality_score"), 50.0)
    components = {
        "pnl": _component(50 + total_pnl * 2),
        "profit_factor": _component(pf * 25),
        "drawdown": _component(100 - drawdown * 10),
        "win_rate": _component(win_rate),
        "trade_count": _component(total_trades * 6),
        "stability": _component(stability),
        "exposure": _component(100 - max(0, exposure - 25) * 2.5),
        "execution_quality": _component(execution),
        "sample_confidence": _sample_confidence(total_trades),
        "consistency": _recent_consistency(model_state or {}),
    }
    return components


def calculate_final_model_score(row: dict, model_state: dict | None = None) -> dict:
    components = _final_components(row, model_state)
    weighted = 0.0
    for key, weight in FINAL_SCORE_WEIGHTS.items():
        weighted += _safe_float(components.get(key)) * weight

    penalties = []
    total_trades = _safe_int(row.get("total_trades"))
    drawdown = abs(_safe_float(row.get("max_drawdown_percent")))
    execution = _safe_float(row.get("execution_quality_score"), 50.0)
    stability = _safe_float(row.get("stability_score"))
    exposure = _safe_float(row.get("risk_exposure_percent"))

    if total_trades < FINAL_SCORE_CRITERIA["min_trades_candidate"]:
        penalties.append({"code": "low_sample", "points": min(18, (FINAL_SCORE_CRITERIA["min_trades_candidate"] - total_trades) * 2), "detail": "Trade örneklemi düşük."})
    if drawdown > FINAL_SCORE_CRITERIA["max_drawdown_candidate_pct"]:
        penalties.append({"code": "drawdown_risk", "points": min(25, (drawdown - FINAL_SCORE_CRITERIA["max_drawdown_candidate_pct"]) * 2.5), "detail": "Drawdown eşiği yüksek."})
    if execution < FINAL_SCORE_CRITERIA["min_execution_quality_candidate"]:
        penalties.append({"code": "execution_risk", "points": min(20, (FINAL_SCORE_CRITERIA["min_execution_quality_candidate"] - execution) * 0.8), "detail": "Execution kalitesi düşük."})
    if stability < FINAL_SCORE_CRITERIA["min_stability_candidate"]:
        penalties.append({"code": "stability_risk", "points": min(18, (FINAL_SCORE_CRITERIA["min_stability_candidate"] - stability) * 0.5), "detail": "Stability skoru düşük."})
    if exposure > 60:
        penalties.append({"code": "overexposure", "points": min(15, (exposure - 60) * 0.4), "detail": "Model risk exposure seviyesi yüksek."})

    penalty_total = round(sum(_safe_float(item.get("points")) for item in penalties), 2)
    final_score = _component(weighted - penalty_total)
    candidate_ready = (
        final_score >= FINAL_SCORE_CRITERIA["min_final_score_candidate"]
        and total_trades >= FINAL_SCORE_CRITERIA["min_trades_candidate"]
        and drawdown <= FINAL_SCORE_CRITERIA["max_drawdown_candidate_pct"]
        and execution >= FINAL_SCORE_CRITERIA["min_execution_quality_candidate"]
        and stability >= FINAL_SCORE_CRITERIA["min_stability_candidate"]
    )
    switch_ready = (
        final_score >= FINAL_SCORE_CRITERIA["min_final_score_switch"]
        and total_trades >= FINAL_SCORE_CRITERIA["min_trades_switch"]
        and drawdown <= FINAL_SCORE_CRITERIA["max_drawdown_switch_pct"]
        and execution >= FINAL_SCORE_CRITERIA["min_execution_quality_switch"]
        and stability >= FINAL_SCORE_CRITERIA["min_stability_switch"]
    )
    return {
        "final_score": final_score,
        "raw_weighted_score": round(weighted, 2),
        "penalty_total": penalty_total,
        "components": components,
        "weights": FINAL_SCORE_WEIGHTS,
        "penalties": penalties,
        "candidate_ready": candidate_ready,
        "switch_ready": switch_ready,
        "criteria": FINAL_SCORE_CRITERIA,
    }


def build_model_score_report(data: dict, settings: dict | None = None, persist_snapshot: bool = False) -> dict:
    lab = ensure_paper_lab(data)
    rankings = get_model_rankings(data)
    models = lab.get("models", {}) or {}
    rows = []
    for row in rankings:
        model_state = models.get(row.get("model_id"), {})
        scoring = calculate_final_model_score(row, model_state)
        enriched = deepcopy(row)
        enriched["final_score"] = scoring["final_score"]
        enriched["final_score_components"] = scoring["components"]
        enriched["final_score_penalties"] = scoring["penalties"]
        enriched["score_penalty_total"] = scoring["penalty_total"]
        enriched["candidate_ready"] = scoring["candidate_ready"]
        enriched["switch_ready"] = scoring["switch_ready"]
        rows.append(enriched)
    rows.sort(key=lambda item: (item.get("final_score", 0), item.get("total_pnl", 0), item.get("total_trades", 0)), reverse=True)
    for idx, item in enumerate(rows, 1):
        item["final_rank"] = idx

    summary = {
        "model_count": len(rows),
        "candidate_ready_count": sum(1 for row in rows if row.get("candidate_ready")),
        "switch_ready_count": sum(1 for row in rows if row.get("switch_ready")),
        "avg_final_score": round(sum(_safe_float(row.get("final_score")) for row in rows) / max(len(rows), 1), 2),
        "best_model_id": rows[0].get("model_id") if rows else None,
        "best_final_score": rows[0].get("final_score") if rows else 0,
    }
    report = {
        "status": "ok" if rows else "review",
        "generated_at": now_iso(),
        "formula_version": "final_score_v1_rev25",
        "weights": FINAL_SCORE_WEIGHTS,
        "criteria": FINAL_SCORE_CRITERIA,
        "summary": summary,
        "models": rows,
        "message": "Final model skoru PnL, risk, stability, execution ve sample confidence bileşenleriyle hesaplanır.",
    }

    if persist_snapshot:
        history = data.setdefault("model_score_history", [])
        history.append({
            "id": f"score_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "time": now_iso(),
            "formula_version": report["formula_version"],
            "summary": summary,
            "top_models": [{"model_id": row.get("model_id"), "final_score": row.get("final_score"), "rank": row.get("final_rank")} for row in rows[:10]],
        })
        data["model_score_history"] = history[-250:]
    return report


def build_model_score_history(data: dict, limit: int = 50) -> dict:
    history = list(data.get("model_score_history", []) or [])
    history = history[-limit:]
    return {"status": "ok", "count": len(history), "history": list(reversed(history))}
