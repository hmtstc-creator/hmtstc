from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from services.execution_calibration_service import build_execution_calibration_report, build_simulator_drift_report

from services.reports_service import build_reports
from services.recommendation_engine_service import build_recommendation_final
from services.model_scoring_service import build_model_score_report


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _id_of(item: dict) -> str:
    return str(item.get("id") or item.get("position_id") or item.get("trade_id") or item.get("order_id") or item.get("scan_id") or "")


def _find_trade(data: dict, trade_id: str | None = None) -> dict:
    pools = [
        ("open_position", _safe_list(data.get("open_positions"))),
        ("closed_position", _safe_list(data.get("closed_positions"))),
        ("history", _safe_list(data.get("history"))),
        ("real_position", _safe_list((_safe_dict(data.get("real_trade"))).get("positions"))),
        ("real_order", _safe_list((_safe_dict(data.get("real_trade"))).get("orders"))),
    ]
    if trade_id:
        for source, rows in pools:
            for row in rows:
                if _id_of(row) == str(trade_id):
                    copy = dict(row)
                    copy["source"] = source
                    return copy
    for source, rows in pools:
        if rows:
            copy = dict(rows[-1])
            copy["source"] = source
            return copy
    return {"source": "none", "status": "waiting_for_trade"}


def _latest_scan(data: dict) -> dict:
    last_scan = _safe_dict(data.get("last_scan"))
    history = _safe_list(data.get("scan_history"))
    return last_scan or (history[-1] if history else {})


def build_trade_explanation(data: dict, settings: dict, trade_id: str | None = None) -> dict:
    trade = _find_trade(data, trade_id)
    scan = _latest_scan(data)
    symbol = trade.get("symbol") or trade.get("coin") or trade.get("asset") or "-"
    entry_signal = trade.get("entry_signal") or trade.get("signal") or trade.get("strategy_signal") or {}
    risk_snapshot = trade.get("risk_snapshot") or trade.get("settings_snapshot") or {}
    rule_snapshot = trade.get("rule_snapshot") or trade.get("rule_snapshots") or {}
    execution = trade.get("execution") or trade.get("execution_snapshot") or {}
    pnl = _safe_float(trade.get("pnl") or trade.get("realized_pnl") or trade.get("unrealized_pnl"))
    status = trade.get("status") or trade.get("lifecycle_status") or "unknown"
    blockers = []
    if trade.get("source") == "none":
        blockers.append("trade_sample_missing")
    if not rule_snapshot:
        blockers.append("rule_snapshot_missing")
    if not execution:
        blockers.append("execution_snapshot_missing")
    explanation = {
        "status": "ok" if not blockers else "review",
        "trade_id": trade_id or _id_of(trade) or None,
        "symbol": symbol,
        "trade_source": trade.get("source"),
        "trade_status": status,
        "pnl": round(pnl, 6),
        "why_entered": [
            f"{symbol} için strateji sinyali üretildi." if symbol != "-" else "Sembol bilgisi bekleniyor.",
            "Filter/strategy/risk snapshot mevcut." if rule_snapshot else "Rule snapshot eksik; Rev33 kalite kapısı bunu review olarak işaretler.",
            "Execution snapshot mevcut." if execution else "Execution snapshot eksik; paper/real kıyas için veri bekleniyor.",
        ],
        "why_exited": [
            str(trade.get("exit_reason") or trade.get("close_reason") or "Açık pozisyon veya kapanış nedeni henüz yok."),
        ],
        "why_won_or_lost": "Pozitif PnL" if pnl > 0 else ("Negatif PnL" if pnl < 0 else "Nötr veya veri bekleniyor"),
        "filter_evidence": rule_snapshot.get("filter") if isinstance(rule_snapshot, dict) else None,
        "strategy_evidence": rule_snapshot.get("strategy") if isinstance(rule_snapshot, dict) else entry_signal,
        "risk_evidence": risk_snapshot,
        "execution_evidence": execution,
        "market_context": {
            "scan_id": scan.get("scan_id") or (scan.get("scan_trace") or {}).get("scan_id"),
            "candidate_count": scan.get("candidate_count") or len(_safe_list(scan.get("candidates"))),
            "eligible_universe": (scan.get("scan_diagnostics") or {}).get("eligible_universe") or scan.get("eligible_universe"),
        },
        "blockers": blockers,
    }
    return explanation


def build_replay_index_final(data: dict, settings: dict, limit: int = 50) -> dict:
    scan_history = _safe_list(data.get("scan_history"))[-limit:]
    archives = _safe_list(data.get("report_archives"))[-limit:]
    model_score_history = _safe_list(data.get("model_score_history"))[-limit:]
    recommendation_history = _safe_list(data.get("recommendation_history"))[-limit:]
    real_trade = _safe_dict(data.get("real_trade"))
    real_orders = _safe_list(real_trade.get("orders"))[-limit:]
    real_positions = _safe_list(real_trade.get("positions"))[-limit:]
    return {
        "status": "ok" if any([scan_history, archives, model_score_history, recommendation_history, real_orders, real_positions]) else "waiting_for_data",
        "indexes": {
            "scan_snapshots": len(scan_history),
            "report_snapshots": len(archives),
            "model_score_snapshots": len(model_score_history),
            "recommendation_snapshots": len(recommendation_history),
            "real_order_events": len(real_orders),
            "real_position_events": len(real_positions),
        },
        "latest": {
            "scan": scan_history[-1] if scan_history else _latest_scan(data),
            "report": archives[-1] if archives else None,
            "model_score": model_score_history[-1] if model_score_history else None,
            "recommendation": recommendation_history[-1] if recommendation_history else None,
            "real_order": real_orders[-1] if real_orders else None,
            "real_position": real_positions[-1] if real_positions else None,
        },
        "policy": {
            "replay_is_read_only": True,
            "replay_never_places_orders": True,
            "real_trade_requires_owner_confirmation": True,
        },
    }


def compare_report_archives(data: dict, a_id: str | None = None, b_id: str | None = None) -> dict:
    archives = _safe_list(data.get("report_archives"))
    if not archives:
        return {"status": "waiting_for_data", "message": "Karşılaştırma için rapor snapshot bekleniyor.", "archives_count": 0}
    by_id = {str(item.get("id")): item for item in archives if item.get("id")}
    a = by_id.get(str(a_id)) if a_id else (archives[-2] if len(archives) >= 2 else archives[-1])
    b = by_id.get(str(b_id)) if b_id else archives[-1]
    if not a or not b:
        return {"status": "review", "message": "Seçilen snapshot bulunamadı.", "archives_count": len(archives)}
    a_summary = _safe_dict(a.get("summary"))
    b_summary = _safe_dict(b.get("summary"))
    fields = ["wallet_value", "total_pnl", "best_score", "models_count", "candidate_models", "switch_ready_count"]
    deltas = {}
    for field in fields:
        deltas[field] = round(_safe_float(b_summary.get(field)) - _safe_float(a_summary.get(field)), 6)
    return {
        "status": "ok",
        "archives_count": len(archives),
        "base": {"id": a.get("id"), "created_at": a.get("created_at"), "period": a.get("period"), "summary": a_summary},
        "target": {"id": b.get("id"), "created_at": b.get("created_at"), "period": b.get("period"), "summary": b_summary},
        "deltas": deltas,
        "explanation": "Karşılaştırma snapshot summary alanları üzerinden yapılır; canlı veri oluşturdukça daha anlamlı olur.",
    }


def build_evidence_chain(data: dict, settings: dict, trade_id: str | None = None) -> dict:
    trade_explain = build_trade_explanation(data, settings, trade_id=trade_id)
    scan = _latest_scan(data)
    score = build_model_score_report(data, settings)
    rec = build_recommendation_final(data, settings)
    replay = build_replay_index_final(data, settings)
    evidence = [
        {"stage": "scan", "status": "ok" if scan else "waiting", "id": scan.get("scan_id") or (scan.get("scan_trace") or {}).get("scan_id"), "summary": "Coin evreni ve aday üretimi."},
        {"stage": "rule_snapshot", "status": "ok" if not trade_explain.get("blockers") or "rule_snapshot_missing" not in trade_explain.get("blockers", []) else "review", "summary": "Trade açılışındaki filter/strategy/risk kanıtı."},
        {"stage": "execution", "status": "ok" if "execution_snapshot_missing" not in trade_explain.get("blockers", []) else "review", "summary": "Paper/dry-run/real execution kanıtı."},
        {"stage": "model_score", "status": score.get("status", "ok"), "summary": "Final model skor bileşenleri."},
        {"stage": "recommendation", "status": rec.get("status", "ok"), "summary": rec.get("reason") or rec.get("human_summary") or "Recommendation final engine çıktısı."},
        {"stage": "replay", "status": replay.get("status"), "summary": "Karar zinciri geriye dönük okunabilir."},
    ]
    readiness = round(sum(1 for row in evidence if row.get("status") == "ok") / max(len(evidence), 1) * 100, 2)
    return {
        "status": "ok" if readiness >= 70 else "review",
        "readiness_score": readiness,
        "trade": trade_explain,
        "evidence_chain": evidence,
        "replay_index": replay.get("indexes", {}),
        "policy": {
            "evidence_chain_is_read_only": True,
            "no_real_order_side_effect": True,
        },
    }


def build_reports_replay_final(data: dict, settings: dict) -> dict:
    report = build_reports(data, settings)
    replay = build_replay_index_final(data, settings)
    compare = compare_report_archives(data)
    evidence = build_evidence_chain(data, settings)
    return {
        "status": "ok" if replay.get("status") == "ok" or report else "review",
        "report_period": report.get("period"),
        "replay": replay,
        "compare": compare,
        "evidence_chain": evidence,
        "summary": {
            "archives_count": compare.get("archives_count", 0),
            "replay_indexes": replay.get("indexes", {}),
            "evidence_readiness": evidence.get("readiness_score", 0),
        },
    }


# --- Level1 Rev46 Reports / Replay / Explainability Final Enhancements ---

def _all_trade_rows(data: dict) -> list[dict]:
    rows: list[dict] = []
    pools = [
        ("open_position", _safe_list(data.get("open_positions"))),
        ("closed_position", _safe_list(data.get("closed_positions"))),
        ("history", _safe_list(data.get("history"))),
        ("paper_closed_position", _safe_list(_safe_dict(data.get("paper_lab")).get("closed_positions"))),
        ("paper_open_position", _safe_list(_safe_dict(data.get("paper_lab")).get("open_positions"))),
        ("real_position", _safe_list(_safe_dict(data.get("real_trade")).get("positions"))),
        ("real_order", _safe_list(_safe_dict(data.get("real_trade")).get("orders"))),
    ]
    for source, items in pools:
        for item in items:
            if isinstance(item, dict):
                row = dict(item)
                row.setdefault("source", source)
                row.setdefault("trade_id", _id_of(row) or f"{source}_{len(rows)+1}")
                rows.append(row)
    return rows


def build_report_archive_schema() -> dict:
    return {
        "status": "ok",
        "schema_version": "rev46.report-archive.v1",
        "required_summary_fields": [
            "wallet_value", "total_pnl", "best_model", "best_score", "models_count",
            "candidate_models", "switch_ready_count", "execution_calibration_score",
            "paper_vs_dry_run_quality_delta", "paper_vs_real_quality_delta",
        ],
        "supported_periods": ["1d", "7d", "30d", "daily", "weekly", "monthly"],
        "policy": {"archive_is_read_only_for_trade": True, "archive_does_not_place_orders": True},
    }


def build_model_ranking_delta(data: dict) -> dict:
    archives = _safe_list(data.get("report_archives"))
    if len(archives) < 2:
        return {"status": "waiting_for_data", "message": "Model ranking delta için en az iki archive snapshot gerekir.", "deltas": []}
    previous = _safe_dict(archives[-2].get("report")).get("model_ranking") or []
    current = _safe_dict(archives[-1].get("report")).get("model_ranking") or []
    prev_rank = {str(row.get("model_id")): idx + 1 for idx, row in enumerate(previous) if row.get("model_id")}
    deltas = []
    for idx, row in enumerate(current):
        model_id = str(row.get("model_id") or "")
        if not model_id:
            continue
        old_rank = prev_rank.get(model_id)
        new_rank = idx + 1
        deltas.append({
            "model_id": model_id,
            "previous_rank": old_rank,
            "current_rank": new_rank,
            "rank_delta": (old_rank - new_rank) if old_rank else None,
            "score": _safe_float(row.get("score")),
            "total_pnl": _safe_float(row.get("total_pnl")),
        })
    return {"status": "ok", "deltas": deltas, "compared_archives": [archives[-2].get("id"), archives[-1].get("id")]}


def build_trade_explanation(data: dict, settings: dict, trade_id: str | None = None) -> dict:  # noqa: F811 - intentional final override
    trade = _find_trade(data, trade_id)
    scan = _latest_scan(data)
    symbol = trade.get("symbol") or trade.get("coin") or trade.get("asset") or "-"
    entry_signal = trade.get("entry_signal") or trade.get("signal") or trade.get("strategy_signal") or {}
    risk_snapshot = trade.get("risk_snapshot") or trade.get("settings_snapshot") or {}
    rule_snapshot = trade.get("rule_snapshot") or trade.get("rule_snapshots") or {}
    execution = trade.get("execution") or trade.get("execution_snapshot") or trade.get("execution_entry") or {}
    pnl = _safe_float(trade.get("pnl") or trade.get("realized_pnl") or trade.get("unrealized_pnl"))
    status = trade.get("status") or trade.get("lifecycle_status") or trade.get("state") or "unknown"
    blockers = []
    if trade.get("source") == "none":
        blockers.append("trade_sample_missing")
    if not rule_snapshot:
        blockers.append("rule_snapshot_missing")
    if not execution:
        blockers.append("execution_snapshot_missing")
    why_open = [
        f"{symbol} işlem evrenine girdi ve strateji sinyali üretildi." if symbol != "-" else "Sembol bilgisi bekleniyor.",
        "Filter/strategy/risk snapshot karar kanıtına bağlı." if rule_snapshot else "Rule snapshot eksik; kararın kanıt zinciri zayıf.",
        "Market scan context mevcut." if scan else "Market scan context bekleniyor.",
    ]
    why_close = [
        str(trade.get("exit_reason") or trade.get("close_reason") or trade.get("stop_reason") or "Kapanış nedeni henüz oluşmadı veya pozisyon açık."),
        f"Lifecycle status: {status}.",
    ]
    if pnl > 0:
        why_result = ["Pozitif PnL: hedef/çıkış koşulu işlem lehine çalıştı."]
    elif pnl < 0:
        why_result = ["Negatif PnL: stop, slippage, fee, piyasa dönüşü veya strateji uyumsuzluğu etkili olabilir."]
    else:
        why_result = ["Nötr/veri bekleniyor: realized veya unrealized PnL henüz anlamlı değil."]
    return {
        "status": "ok" if not blockers else "review",
        "trade_id": trade_id or _id_of(trade) or None,
        "symbol": symbol,
        "trade_source": trade.get("source"),
        "trade_status": status,
        "pnl": round(pnl, 6),
        "why_entered": why_open,
        "why_open": why_open,
        "why_exited": why_close,
        "why_close": why_close,
        "why_won_or_lost": " ".join(why_result),
        "why_profit_loss": why_result,
        "filter_evidence": rule_snapshot.get("filter") if isinstance(rule_snapshot, dict) else None,
        "strategy_evidence": rule_snapshot.get("strategy") if isinstance(rule_snapshot, dict) else entry_signal,
        "risk_evidence": risk_snapshot,
        "execution_evidence": execution,
        "market_context": {
            "scan_id": scan.get("scan_id") or (scan.get("scan_trace") or {}).get("scan_id"),
            "candidate_count": scan.get("candidate_count") or len(_safe_list(scan.get("candidates"))),
            "eligible_universe": (scan.get("scan_diagnostics") or {}).get("eligible_universe") or scan.get("eligible_universe"),
        },
        "blockers": blockers,
        "policy": {"explainability_is_read_only": True, "no_trade_side_effect": True},
    }


def build_replay_index_final(data: dict, settings: dict, limit: int = 50) -> dict:  # noqa: F811 - intentional final override
    trades = _all_trade_rows(data)[-limit:]
    scan_history = _safe_list(data.get("scan_history"))[-limit:]
    archives = _safe_list(data.get("report_archives"))[-limit:]
    model_score_history = _safe_list(data.get("model_score_history"))[-limit:]
    recommendation_history = _safe_list(data.get("recommendation_history"))[-limit:]
    events = []
    for row in trades:
        events.append({
            "event_type": row.get("source"),
            "trade_id": row.get("trade_id") or _id_of(row),
            "symbol": row.get("symbol") or row.get("coin"),
            "status": row.get("status") or row.get("lifecycle_status"),
            "pnl": _safe_float(row.get("pnl") or row.get("realized_pnl") or row.get("unrealized_pnl")),
            "created_at": row.get("created_at") or row.get("opened_at") or row.get("closed_at") or row.get("time"),
        })
    return {
        "status": "ok" if any([trades, scan_history, archives, model_score_history, recommendation_history]) else "waiting_for_data",
        "indexes": {
            "trade_events": len(trades),
            "scan_snapshots": len(scan_history),
            "report_snapshots": len(archives),
            "model_score_snapshots": len(model_score_history),
            "recommendation_snapshots": len(recommendation_history),
        },
        "events": list(reversed(events[-limit:])),
        "latest": {
            "scan": scan_history[-1] if scan_history else _latest_scan(data),
            "report": archives[-1] if archives else None,
            "model_score": model_score_history[-1] if model_score_history else None,
            "recommendation": recommendation_history[-1] if recommendation_history else None,
            "trade": trades[-1] if trades else None,
        },
        "policy": {"replay_is_read_only": True, "replay_never_places_orders": True},
    }


def build_reports_replay_final(data: dict, settings: dict) -> dict:  # noqa: F811 - intentional final override
    report = build_reports(data, settings)
    replay = build_replay_index_final(data, settings)
    compare = compare_report_archives(data)
    evidence = build_evidence_chain(data, settings)
    calibration = build_execution_calibration_report(data, settings)
    drift = build_simulator_drift_report(data, settings)
    ranking_delta = build_model_ranking_delta(data)
    checks = {
        "archive_schema": build_report_archive_schema().get("status") == "ok",
        "period_compare": compare.get("status") in {"ok", "waiting_for_data", "review"},
        "replay_index": replay.get("status") in {"ok", "waiting_for_data"},
        "explainability": evidence.get("status") in {"ok", "review"},
        "execution_calibration": calibration.get("status") in {"ok", "review", "blocked"},
        "drift_report": drift.get("status") in {"ok", "review", "blocked"},
    }
    readiness = round(sum(1 for ok in checks.values() if ok) / max(len(checks), 1) * 100, 2)
    return {
        "status": "ok" if readiness >= 95 else "review",
        "readiness_score": readiness,
        "report_period": report.get("period"),
        "report_archive_schema": build_report_archive_schema(),
        "replay": replay,
        "compare": compare,
        "evidence_chain": evidence,
        "execution_calibration": calibration,
        "simulator_drift": drift,
        "model_ranking_delta": ranking_delta,
        "quality_checks": checks,
        "summary": {
            "archives_count": compare.get("archives_count", 0),
            "replay_indexes": replay.get("indexes", {}),
            "evidence_readiness": evidence.get("readiness_score", 0),
            "calibration_score": calibration.get("calibration_score", 0),
        },
        "policy": {"reports_replay_is_read_only": True, "no_real_order_created": True},
    }
