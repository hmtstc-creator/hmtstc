from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from services.revision_11_service import (
    build_api_contract_v2,
    build_button_smoke_matrix_v2,
    audit_scan_universe_v2,
    audit_execution_simulator_v2,
    audit_wallet_integrity_v2,
    audit_model_score_v2,
    audit_recommendation_v2,
    audit_attribution_v2,
    audit_rule_snapshot_v2,
    audit_safety_recovery_v2,
)
from services.intelligence_service import (
    build_coin_quality_dashboard,
    build_cooldown_policy,
    build_dynamic_risk_adjustment,
    build_observability,
    build_orderbook_intelligence,
    build_portfolio_allocation,
    build_replay_index,
    build_trade_explainability,
    detect_market_regime,
)
from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.real_trade_safety_service import (
    build_real_model_approval,
    build_real_trade_safety_status,
    build_runtime_health,
    build_weighted_recommendation,
)
from services.reports_service import build_reports
from services.rule_engine import list_rules


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _status(issues: list[str] | None = None, blockers: list[str] | None = None) -> str:
    issues = issues or []
    blockers = blockers or []
    if blockers:
        return "blocked"
    if issues:
        return "review"
    return "ok"


def _first_existing_model(data: dict) -> dict:
    rankings = get_model_rankings(data)
    if rankings:
        return rankings[0]
    lab = ensure_paper_lab(data)
    for model in (lab.get("models") or {}).values():
        return model if isinstance(model, dict) else {}
    return {}


def build_api_contract_v3() -> dict:
    base = build_api_contract_v2()
    extra = [
        {"page": "quality", "action": "revision12", "method": "GET", "endpoint": "/api/quality/revision-12", "role": "user", "audit": False},
        {"page": "quality", "action": "revision12_contract", "method": "GET", "endpoint": "/api/quality/revision-12/api-contract", "role": "user", "audit": False},
        {"page": "quality", "action": "revision12_button_smoke", "method": "GET", "endpoint": "/api/quality/revision-12/button-smoke", "role": "user", "audit": False},
        {"page": "quality", "action": "revision12_integrity", "method": "GET", "endpoint": "/api/quality/revision-12/integrity", "role": "user", "audit": False},
        {"page": "quality", "action": "revision12_safety", "method": "GET", "endpoint": "/api/quality/revision-12/safety", "role": "user", "audit": False},
        {"page": "intelligence", "action": "trade_explainability", "method": "GET", "endpoint": "/api/intelligence/trade-explainability", "role": "user", "audit": False},
        {"page": "intelligence", "action": "replay", "method": "GET", "endpoint": "/api/intelligence/replay", "role": "user", "audit": False},
        {"page": "intelligence", "action": "observability", "method": "GET", "endpoint": "/api/intelligence/observability", "role": "user", "audit": False},
        {"page": "audit", "action": "export", "method": "GET", "endpoint": "/api/audit/export", "role": "owner", "audit": False},
    ]
    seen = {(item["method"], item["endpoint"], item["action"]) for item in base.get("contracts", [])}
    contracts = list(base.get("contracts", []))
    for item in extra:
        key = (item["method"], item["endpoint"], item["action"])
        if key not in seen:
            contracts.append(item)
    by_role = Counter(item.get("role", "user") for item in contracts)
    by_page = Counter(item.get("page", "-") for item in contracts)
    return {
        "status": "ok",
        "revision": "revizyon_12",
        "count": len(contracts),
        "contracts": contracts,
        "by_role": dict(by_role),
        "by_page": dict(by_page),
        "matrix_notes": [
            "Frontend critical actions are mapped to backend API contracts.",
            "Owner-only destructive operations are explicitly separated.",
        ],
    }


def build_button_smoke_matrix_v3() -> dict:
    contract = build_api_contract_v3()
    critical_actions = {"emergency", "emergency_unlock", "delete", "restore_version", "decision", "dry_run_order", "archive", "audit_clear"}
    rows = []
    for item in contract["contracts"]:
        action = item.get("action") or ""
        rows.append({
            "page": item.get("page"),
            "action": action,
            "endpoint": item.get("endpoint"),
            "method": item.get("method"),
            "role": item.get("role"),
            "event_expected": True,
            "api_expected": True,
            "error_handling_expected": True,
            "audit_expected": bool(item.get("audit")),
            "permission_expected": item.get("role") in {"owner", "admin", "ahmet"},
            "confirm_expected": action in critical_actions,
            "status": "mapped",
        })
    return {"status": "ok", "revision": "revizyon_12", "count": len(rows), "rows": rows}


def build_dashboard_decision_layer(data: dict, settings: dict) -> dict:
    runtime = build_runtime_health(data, settings)
    regime = detect_market_regime(data, settings)
    rec = build_weighted_recommendation(data, settings)
    cooldown = build_cooldown_policy(data, settings)
    safety = build_real_trade_safety_status(data, settings)
    scan = data.get("last_scan") or {}
    blockers = []
    warnings = []
    if runtime.get("status") != "ok":
        blockers.append("runtime_health_degraded")
    if cooldown.get("status") == "blocked":
        blockers.extend(cooldown.get("blockers") or ["cooldown_active"])
    if data.get("emergency_lock"):
        blockers.append("emergency_lock")
    if safety.get("real_order_allowed"):
        blockers.append("real_order_allowed_unexpected")
    if (scan.get("scanned") or 0) == 0:
        warnings.append("scan_waiting_for_data")
    if rec.get("action") == "SWITCH_TO_NEW_MODEL" and rec.get("confidence") in {"low", None, ""}:
        warnings.append("switch_candidate_low_confidence")
    if regime.get("no_trade_bias"):
        warnings.append("market_regime_no_trade_bias")
    decision = "NO_TRADE" if blockers else ("WATCH" if warnings or rec.get("action") == "WATCH" else "READY_FOR_PAPER_OBSERVATION")
    severity = "critical" if blockers else ("warning" if warnings else "ok")
    return {
        "status": _status(warnings, blockers),
        "decision": decision,
        "severity": severity,
        "message": "İşlem için uygun değil; bloklayıcı sinyal var." if blockers else ("Veri/koşul izleniyor; aceleci karar yok." if warnings else "Paper/shadow gözlem için koşullar normal."),
        "runtime_health": runtime,
        "market_regime": regime,
        "recommendation": rec,
        "cooldown": cooldown,
        "safety": safety,
        "scan_integrity": {"scanned": scan.get("scanned", 0), "candidates": scan.get("candidates_count", len(scan.get("candidates") or [])), "time": scan.get("time")},
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
    }


def build_trade_explainability_v2(data: dict, settings: dict, limit: int = 30) -> dict:
    items = []
    lab = ensure_paper_lab(data)
    for model in (lab.get("models") or {}).values():
        model_id = model.get("model_id") or model.get("id") or "-"
        for trade in (model.get("history") or [])[-limit:]:
            entry_exec = trade.get("execution_entry") or {}
            exit_exec = trade.get("execution_exit") or {}
            rule_snapshot = trade.get("rule_snapshot") or {}
            pnl = _safe_float(trade.get("pnl"))
            outcome = "profit" if pnl > 0 else ("loss" if pnl < 0 else "flat")
            items.append({
                "trade_id": trade.get("id") or trade.get("trade_id"),
                "model_id": model_id,
                "symbol": trade.get("symbol"),
                "opened_reason": trade.get("entry_signal") or trade.get("strategy") or "strategy_signal",
                "filter": trade.get("filter_id") or rule_snapshot.get("filter_id") or "-",
                "strategy": trade.get("strategy_id") or rule_snapshot.get("strategy_id") or trade.get("strategy") or "-",
                "risk_profile": trade.get("risk_profile_id") or rule_snapshot.get("risk_profile_id") or "-",
                "coin_quality_score": trade.get("coin_quality_score") or entry_exec.get("coin_quality_score") or 0,
                "market_regime": trade.get("market_regime") or "unknown",
                "execution_quality_score": entry_exec.get("execution_quality_score") or trade.get("execution_quality_score") or 0,
                "closed_reason": trade.get("exit_signal") or trade.get("exit_reason") or "paper_exit",
                "pnl": round(pnl, 4),
                "outcome": outcome,
                "plain_reason": f"{trade.get('symbol','-')} {outcome}: {model_id} / {trade.get('strategy_id') or trade.get('strategy') or '-'} / execQ={entry_exec.get('execution_quality_score', 0)} / pnl={round(pnl, 4)}",
                "entry_execution": entry_exec,
                "exit_execution": exit_exec,
            })
    if not items:
        shadow_history = list(data.get("history") or [])[-limit:]
        for trade in shadow_history:
            pnl = _safe_float(trade.get("pnl"))
            items.append({
                "trade_id": trade.get("id") or trade.get("trade_id"),
                "model_id": trade.get("model_id") or "shadow",
                "symbol": trade.get("symbol"),
                "opened_reason": trade.get("entry_signal") or "shadow_signal",
                "filter": trade.get("filter_id") or "-",
                "strategy": trade.get("strategy_id") or trade.get("strategy") or "-",
                "risk_profile": trade.get("risk_profile_id") or "-",
                "coin_quality_score": trade.get("coin_quality_score") or 0,
                "market_regime": trade.get("market_regime") or "unknown",
                "execution_quality_score": trade.get("execution_quality_score") or 0,
                "closed_reason": trade.get("exit_signal") or trade.get("exit_reason") or "closed",
                "pnl": round(pnl, 4),
                "outcome": "profit" if pnl > 0 else ("loss" if pnl < 0 else "flat"),
                "plain_reason": f"{trade.get('symbol','-')} trade açıklaması: pnl={round(pnl, 4)}, strategy={trade.get('strategy_id') or trade.get('strategy') or '-'}",
            })
    return {"status": "ok" if items else "review", "count": len(items), "items": items[-limit:], "issues": [] if items else ["trade_explainability_waiting_for_trade_history"]}


def build_replay_index_v2(data: dict, settings: dict) -> dict:
    scan = data.get("last_scan") or {}
    lab = ensure_paper_lab(data)
    models = lab.get("models") or {}
    decision_snapshots = []
    for row in get_model_rankings(data)[:20]:
        decision_snapshots.append({
            "model_id": row.get("model_id"),
            "score": row.get("score"),
            "trades": row.get("total_trades"),
            "eligible": row.get("eligible_for_real"),
            "recommendation_group": row.get("evaluation_group"),
        })
    trade_count = sum(len(model.get("history") or []) for model in models.values() if isinstance(model, dict))
    return {
        "status": "ok",
        "scan_snapshot": {"time": scan.get("time"), "scanned": scan.get("scanned", 0), "candidates": scan.get("candidates_count", len(scan.get("candidates") or []))},
        "model_decision_snapshots": decision_snapshots,
        "trade_decision_count": trade_count,
        "rule_version_available": True,
        "execution_snapshot_available": any((model.get("history") or []) for model in models.values() if isinstance(model, dict)),
        "notes": "Replay index is a lightweight pointer map; full replay stores stay in runtime shadow data.",
    }


def build_paper_lab_integrity_monitor(data: dict, settings: dict) -> dict:
    wallet = audit_wallet_integrity_v2(data, settings)
    rule_snapshot = audit_rule_snapshot_v2(data, settings, username=str(data.get("username") or "ahmet"))
    execution = audit_execution_simulator_v2(data, settings)
    rankings = get_model_rankings(data)
    issues = []
    blockers = []
    if wallet.get("status") == "blocked":
        blockers.extend(wallet.get("blockers") or ["wallet_integrity_blocked"])
    if rule_snapshot.get("status") != "ok":
        issues.extend(rule_snapshot.get("issues") or ["rule_snapshot_review"])
    if execution.get("status") != "ok":
        issues.extend(execution.get("issues") or ["execution_waiting_for_scan"])
    if len(rankings) == 0:
        issues.append("paper_lab_ranking_waiting")
    integrity_score = max(0, 100 - len(blockers) * 25 - len(issues) * 8)
    return {
        "status": _status(issues, blockers),
        "integrity_score": integrity_score,
        "wallet_integrity": wallet,
        "rule_snapshot": rule_snapshot,
        "execution_quality": execution,
        "ranked_models": len(rankings),
        "issues": sorted(set(issues)),
        "blockers": sorted(set(blockers)),
    }


def build_recommendation_explanation_v2(data: dict, settings: dict) -> dict:
    rec = build_weighted_recommendation(data, settings)
    rankings = get_model_rankings(data)
    top = rankings[0] if rankings else {}
    blockers = []
    reasons = []
    if not rankings:
        blockers.append("no_model_ranking")
    if _safe_int(top.get("total_trades")) < 7:
        reasons.append("minimum_trade_depth_not_reached")
    if _safe_float(top.get("max_drawdown_percent")) < -8:
        blockers.append("drawdown_too_high")
    if _safe_float(top.get("stability_score")) < 50 and rankings:
        reasons.append("stability_below_preferred_threshold")
    exec_q = _safe_float(top.get("execution_quality_score"), _safe_float((top.get("score_components") or {}).get("execution"), 0))
    if exec_q and exec_q < 50:
        reasons.append("execution_quality_low")
    if rec.get("action") == "WATCH":
        reasons.append("watch_mode_keeps_real_model_unchanged")
    if rec.get("action") == "KEEP_CURRENT":
        reasons.append("current_model_not_outperformed_enough")
    if rec.get("action") == "SWITCH_TO_NEW_MODEL":
        reasons.append("candidate_passed_switch_gate")
    return {
        "status": _status(reasons, blockers),
        "action": rec.get("action"),
        "candidate_model_id": rec.get("candidate_model_id"),
        "confidence": rec.get("confidence"),
        "plain_reason": rec.get("reason") or ", ".join(reasons) or "Veri bekleniyor.",
        "score_components": top.get("score_components") or {},
        "top_model": top,
        "reasons": sorted(set(reasons)),
        "blockers": sorted(set(blockers)),
    }


def build_real_approval_ui_v2(data: dict, settings: dict) -> dict:
    approval = build_real_model_approval(data, settings)
    rankings = get_model_rankings(data)
    lab = ensure_paper_lab(data)
    current_id = lab.get("active_real_model_id")
    recommendation = approval.get("recommendation") or {}
    candidate_id = recommendation.get("candidate_model_id")
    current = next((row for row in rankings if row.get("model_id") == current_id), None) or {}
    candidate = next((row for row in rankings if row.get("model_id") == candidate_id), None) or {}
    def diff(field):
        return round(_safe_float(candidate.get(field)) - _safe_float(current.get(field)), 4)
    return {
        "status": "ok",
        "current_model": current,
        "candidate_model": candidate,
        "comparison": {
            "pnl_delta": diff("total_pnl"),
            "score_delta": diff("score"),
            "drawdown_delta": diff("max_drawdown_percent"),
            "win_rate_delta": diff("win_rate"),
            "stability_delta": diff("stability_score"),
            "execution_quality_delta": diff("execution_quality_score"),
            "trade_count_delta": diff("total_trades"),
        },
        "can_request_approval": bool(approval.get("can_request_approval")),
        "requires_owner": True,
        "real_trade_warning": "Approval updates selected real model only; it does not enable real order execution.",
        "history": data.get("real_model_approval_history") or ([data.get("real_model_approval")] if data.get("real_model_approval") else []),
    }


def build_emergency_recovery_ui_v2(data: dict, settings: dict) -> dict:
    safety = build_real_trade_safety_status(data, settings)
    open_positions = list(data.get("open_positions") or [])
    locked = bool(data.get("emergency_lock"))
    warnings = []
    if open_positions:
        warnings.append("open_positions_require_review")
    if safety.get("status") != "locked":
        warnings.append("safety_status_unexpected")
    return {
        "status": "blocked" if locked else "ok",
        "emergency_lock": locked,
        "bot_running": bool(data.get("bot_running")),
        "unlock_allowed_role": "owner",
        "auto_restart_after_unlock": False,
        "open_positions_count": len(open_positions),
        "risk_summary": {"safety_status": safety.get("status"), "blockers": safety.get("blockers") or [], "open_symbols": [p.get("symbol") for p in open_positions[:10]]},
        "warnings": warnings,
        "message": "Emergency lock aktif; owner unlock ve manuel restart gerekir." if locked else "Emergency lock yok; sistem normal güvenlik kilidinde.",
    }


def build_observability_v2(data: dict, settings: dict) -> dict:
    base = build_observability(data, settings)
    runtime = build_runtime_health(data, settings)
    history = list(data.get("health_history") or [])[-100:]
    errors = [item for item in history if item.get("status") in {"error", "blocked", "critical"}]
    return {
        **base,
        "runtime_status": runtime.get("status"),
        "backend_response_time_ms": base.get("backend_response_time_ms", 0),
        "endpoint_error_rate_percent": round(len(errors) / max(len(history), 1) * 100, 2) if history else 0,
        "health_trend_samples": len(history),
        "critical_warnings": [*runtime.get("blockers", []), *runtime.get("warnings", [])][:20],
    }


def build_audit_readiness_v2(data: dict, settings: dict) -> dict:
    audit = list(data.get("audit") or [])
    by_action = Counter(item.get("action") for item in audit)
    critical = [item for item in audit if item.get("action") in {"emergency_stop", "emergency_unlock", "real_model_approval", "audit_clear", "backup_restore"}]
    return {"status": "ok", "total": len(audit), "critical_count": len(critical), "by_action": dict(by_action), "export_ready": True, "owner_clear_only": True}


def build_reports_archive_readiness_v2(data: dict, settings: dict) -> dict:
    archives = list(data.get("report_archives") or [])
    return {"status": "ok" if archives else "review", "archives_count": len(archives), "compare_ready": len(archives) >= 2, "json_export": True, "csv_export": True, "issues": [] if archives else ["report_archive_waiting_for_snapshot"]}


def build_market_regime_strategy_match_v2(data: dict, settings: dict) -> dict:
    regime = detect_market_regime(data, settings)
    strategy_map = {
        "TREND_UP": ["CHOCH", "MOMENTUM", "BREAKOUT_CONFIRM"],
        "TREND_DOWN": ["WAIT", "MEAN_REVERSION_ONLY_WITH_CONFIRM"],
        "RANGE_LOW_VOL": ["IMBALANCE_FILL", "RANGE_SCALP"],
        "HIGH_VOLATILITY": ["NO_TRADE", "REDUCED_RISK_ONLY"],
        "CHOPPY": ["NO_TRADE", "WAIT_FOR_STRUCTURE"],
    }
    suited = strategy_map.get(regime.get("regime"), ["WATCH"])
    return {"status": "ok", "regime": regime, "matched_strategies": suited, "no_trade_recommended": "NO_TRADE" in suited or bool(regime.get("no_trade_bias")), "confidence": regime.get("confidence", 0)}


def build_backend_validation_review_v2(settings: dict) -> dict:
    bot = settings.get("bot") or {}
    risk = settings.get("risk") or {}
    issues = []
    blockers = []
    allocated = _safe_float(bot.get("allocated_usdt"))
    per_position = _safe_float(bot.get("usdt_per_position"))
    max_positions = _safe_int(bot.get("max_open_positions"))
    if allocated <= 0:
        blockers.append("allocated_usdt_must_be_positive")
    if per_position <= 0:
        blockers.append("usdt_per_position_must_be_positive")
    if max_positions <= 0:
        blockers.append("max_open_positions_must_be_positive")
    if per_position * max_positions > allocated * 1.25:
        issues.append("slot_capacity_exceeds_allocated_capital")
    for key in ["max_slippage_percent", "max_spread_percent", "risk_per_position_percent", "max_portfolio_risk_percent"]:
        value = _safe_float(risk.get(key), 0)
        if value < 0:
            blockers.append(f"{key}_negative")
        if key in {"risk_per_position_percent", "max_portfolio_risk_percent"} and value > 100:
            blockers.append(f"{key}_too_high")
    return {"status": _status(issues, blockers), "issues": issues, "blockers": blockers, "standard_error_format": True}


def _quality_gate_status(name: str, payload: dict) -> str:
    status = payload.get("status") if isinstance(payload, dict) else "ok"
    if name == "scan_universe" and status == "blocked" and "scan_empty" in (payload.get("blockers") or []):
        return "review"
    if name == "safety_review" and status == "blocked":
        blockers = set(payload.get("blockers") or [])
        expected_locks = {"real_trade_default_locked", "mode_not_real"}
        if blockers and blockers.issubset(expected_locks):
            return "ok"
    return status or "ok"


def build_revision_12_integrity_report(data: dict, settings: dict, username: str = "ahmet") -> dict:
    return {
        "status": "ok",
        "paper_lab_integrity": build_paper_lab_integrity_monitor(data, settings),
        "rule_snapshot_integrity": audit_rule_snapshot_v2(data, settings, username=username),
        "wallet_integrity": audit_wallet_integrity_v2(data, settings),
        "replay_index": build_replay_index_v2(data, settings),
        "trade_explainability": build_trade_explainability_v2(data, settings, limit=10),
    }


def build_revision_12_safety_report(data: dict, settings: dict) -> dict:
    return {
        "status": "ok",
        "real_trade_safety": build_real_trade_safety_status(data, settings),
        "emergency_recovery": build_emergency_recovery_ui_v2(data, settings),
        "cooldown": build_cooldown_policy(data, settings),
        "dashboard_decision": build_dashboard_decision_layer(data, settings),
        "backend_validation": build_backend_validation_review_v2(settings),
    }


def build_revision_12_quality_report(data: dict, settings: dict, username: str = "ahmet", run_live_scan: bool = False) -> dict:
    integrity = build_revision_12_integrity_report(data, settings, username=username)
    safety = build_revision_12_safety_report(data, settings)
    blocks = {
        "api_contract": build_api_contract_v3(),
        "button_smoke_matrix": build_button_smoke_matrix_v3(),
        "dashboard_decision_layer": build_dashboard_decision_layer(data, settings),
        "trade_explainability": build_trade_explainability_v2(data, settings),
        "replay_index": build_replay_index_v2(data, settings),
        "paper_lab_integrity": integrity["paper_lab_integrity"],
        "rule_snapshot_integrity": integrity["rule_snapshot_integrity"],
        "recommendation_explanation": build_recommendation_explanation_v2(data, settings),
        "real_approval_ui": build_real_approval_ui_v2(data, settings),
        "emergency_recovery": safety["emergency_recovery"],
        "observability": build_observability_v2(data, settings),
        "audit_readiness": build_audit_readiness_v2(data, settings),
        "reports_archive_readiness": build_reports_archive_readiness_v2(data, settings),
        "market_regime_strategy_match": build_market_regime_strategy_match_v2(data, settings),
        "cooldown": build_cooldown_policy(data, settings),
        "portfolio_allocation": build_portfolio_allocation(data, settings),
        "backend_validation": safety["backend_validation"],
        "scan_universe": audit_scan_universe_v2(data, settings, run_live_scan=run_live_scan),
        "execution_simulator": audit_execution_simulator_v2(data, settings),
        "model_score": audit_model_score_v2(data, settings),
        "attribution": audit_attribution_v2(data, settings),
        "coin_quality": build_coin_quality_dashboard(data, settings),
        "safety_review": safety["real_trade_safety"],
    }
    blockers = []
    reviews = []
    for name, payload in blocks.items():
        status = _quality_gate_status(name, payload)
        if status == "blocked":
            blockers.append(name)
        elif status == "review":
            reviews.append(name)
    score = max(0, 100 - len(blockers) * 15 - len(reviews) * 4)
    return {
        "status": "blocked" if blockers else ("review" if reviews else "ok"),
        "revision": "revizyon_12",
        "score": score,
        "state": "ready_for_deep_observation" if score >= 86 and not blockers else ("needs_review" if score >= 65 else "blocked"),
        "blockers": blockers,
        "reviews": reviews,
        "blocks": blocks,
        "integrity": integrity,
        "safety": safety,
        "next_gate": "24h paper/shadow observation + user live feedback" if score >= 86 and not blockers else "fix blockers/review items before broader observation",
    }
