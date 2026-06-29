from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from services.analysis_service import scan_market
from services.intelligence_service import (
    build_cooldown_policy,
    build_dynamic_risk_adjustment,
    build_observability,
    build_portfolio_allocation,
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


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _ok(name: str, detail: str = "OK", severity: str = "ok", meta: dict | None = None) -> dict:
    return {"name": name, "severity": severity, "detail": detail, "meta": meta or {}}


def build_api_contract_matrix() -> dict:
    """Single source contract map for buttons/pages/endpoints.

    This is intentionally explicit. It allows frontend and backend changes to be
    reviewed against one table instead of being checked only by memory.
    """
    contracts = [
        {"page": "auth", "action": "login", "method": "POST", "endpoint": "/api/auth/login", "role": "public"},
        {"page": "auth", "action": "me", "method": "GET", "endpoint": "/api/auth/me", "role": "user"},
        {"page": "auth", "action": "change_password", "method": "POST", "endpoint": "/api/auth/change-password", "role": "user"},
        {"page": "dashboard", "action": "bot_start", "method": "POST", "endpoint": "/api/bot/start", "role": "user"},
        {"page": "dashboard", "action": "bot_stop", "method": "POST", "endpoint": "/api/bot/stop", "role": "user"},
        {"page": "dashboard", "action": "emergency_stop", "method": "POST", "endpoint": "/api/bot/emergency-stop", "role": "user"},
        {"page": "dashboard", "action": "emergency_unlock", "method": "POST", "endpoint": "/api/bot/recovery/unlock", "role": "owner"},
        {"page": "dashboard", "action": "reset", "method": "POST", "endpoint": "/api/bot/reset", "role": "user"},
        {"page": "coinFilter", "action": "last_scan", "method": "GET", "endpoint": "/api/bot/last-scan", "role": "user"},
        {"page": "coinFilter", "action": "scan_now", "method": "GET", "endpoint": "/api/bot/scan", "role": "user"},
        {"page": "ruleEditor", "action": "list_rules", "method": "GET", "endpoint": "/api/rules", "role": "owner"},
        {"page": "ruleEditor", "action": "save_rule", "method": "POST", "endpoint": "/api/rules/save", "role": "owner"},
        {"page": "ruleEditor", "action": "delete_rule", "method": "DELETE", "endpoint": "/api/rules/{rule_id}", "role": "owner"},
        {"page": "ruleEditor", "action": "validate_rule", "method": "POST", "endpoint": "/api/rules/validate", "role": "owner"},
        {"page": "ruleEditor", "action": "restore_rule_version", "method": "POST", "endpoint": "/api/rules/{rule_id}/restore-version", "role": "owner"},
        {"page": "settings", "action": "save", "method": "POST", "endpoint": "/api/settings", "role": "user"},
        {"page": "settings", "action": "risk_profile", "method": "POST", "endpoint": "/api/settings/risk-profiles/{profile_id}", "role": "user"},
        {"page": "reports", "action": "export", "method": "GET", "endpoint": "/api/models/reports/export", "role": "user"},
        {"page": "reports", "action": "archive", "method": "POST", "endpoint": "/api/models/reports/archive", "role": "user"},
        {"page": "realApproval", "action": "decision", "method": "POST", "endpoint": "/api/models/real-approval/decision", "role": "owner"},
        {"page": "realApproval", "action": "dry_run_order", "method": "POST", "endpoint": "/api/models/real-order/dry-run", "role": "owner"},
        {"page": "users", "action": "create", "method": "POST", "endpoint": "/api/users", "role": "owner"},
        {"page": "users", "action": "reset_password", "method": "POST", "endpoint": "/api/users/{username}/reset-password", "role": "owner"},
        {"page": "users", "action": "active", "method": "POST", "endpoint": "/api/users/{username}/active", "role": "owner"},
        {"page": "backups", "action": "list", "method": "GET", "endpoint": "/api/bot/backups", "role": "owner"},
        {"page": "backups", "action": "restore", "method": "POST", "endpoint": "/api/bot/restore-backup", "role": "owner"},
        {"page": "audit", "action": "clear", "method": "DELETE", "endpoint": "/api/audit", "role": "owner"},
        {"page": "audit", "action": "export", "method": "GET", "endpoint": "/api/audit/export", "role": "owner"},
        {"page": "intelligence", "action": "overview", "method": "GET", "endpoint": "/api/intelligence/overview", "role": "user"},
        {"page": "quality", "action": "revision_10", "method": "GET", "endpoint": "/api/quality/revision-10", "role": "user"},

        {"page": "real", "action": "real_readiness", "method": "GET", "endpoint": "/api/real/readiness", "role": "user"},
        {"page": "real", "action": "real_balances", "method": "GET", "endpoint": "/api/real/balances", "role": "owner"},
        {"page": "real", "action": "real_order_preview", "method": "POST", "endpoint": "/api/real/orders/preview", "role": "owner"},
        {"page": "real", "action": "real_order_dry_run", "method": "POST", "endpoint": "/api/real/orders/dry-run", "role": "owner"},
        {"page": "real", "action": "real_order_place", "method": "POST", "endpoint": "/api/real/orders/place", "role": "owner"},
        {"page": "real", "action": "real_unlock", "method": "POST", "endpoint": "/api/real/unlock", "role": "owner"},
        {"page": "quality", "action": "revision_14", "method": "GET", "endpoint": "/api/quality/revision-14", "role": "user"},
    ]
    by_page = defaultdict(int)
    by_role = defaultdict(int)
    for row in contracts:
        by_page[row["page"]] += 1
        by_role[row["role"]] += 1
    return {"status": "ok", "count": len(contracts), "contracts": contracts, "by_page": dict(by_page), "by_role": dict(by_role)}


def audit_scan_universe(data: dict, settings: dict, limit: int = 1000, run_live_scan: bool = False) -> dict:
    source = "last_scan"
    scan = data.get("last_scan") or {}
    if run_live_scan:
        scan = scan_market(settings, limit=limit)
        source = "live_scan"
    rows = scan.get("scan_rows") or []
    rejection_breakdown = scan.get("rejection_breakdown") or {}
    scanned = int(scan.get("scanned") or len(rows))
    candidates = int(scan.get("candidates_count") or len(scan.get("candidates") or []))
    diagnostics = scan.get("scan_diagnostics") or {}
    issues = []
    if scanned == 0:
        issues.append("scan_empty")
    if scanned and scanned < 50 and not scan.get("error"):
        issues.append("scan_universe_suspiciously_small")
    if not diagnostics:
        issues.append("missing_scan_diagnostics")
    quality_values = [_safe_float(row.get("quality_score")) for row in rows if _safe_float(row.get("quality_score")) > 0]
    return {
        "status": "ok" if not issues else "review",
        "source": source,
        "scanned": scanned,
        "candidates_count": candidates,
        "rejected_count": int(scan.get("rejected_count") or max(0, scanned - candidates)),
        "top_rejection_reason": scan.get("top_rejection_reason"),
        "rejection_breakdown": rejection_breakdown,
        "avg_quality_score": round(sum(quality_values) / len(quality_values), 2) if quality_values else 0,
        "diagnostics": diagnostics,
        "issues": issues,
    }


def audit_paper_lab_integrity(data: dict, settings: dict) -> dict:
    lab = ensure_paper_lab(data)
    rankings = get_model_rankings(data)
    issues = []
    model_count = len(lab.get("models", {}) or {})
    if model_count < 1:
        issues.append("paper_lab_no_models")
    if rankings and all(int(row.get("total_trades") or 0) == 0 for row in rankings):
        issues.append("paper_lab_waiting_for_closed_trades")
    bad_wallets = []
    for row in rankings:
        expected = _safe_float(row.get("wallet_start"), 1000) + _safe_float(row.get("total_pnl"))
        if abs(expected - _safe_float(row.get("wallet_value"))) > 0.05:
            bad_wallets.append(row.get("model_id"))
    if bad_wallets:
        issues.append("wallet_value_mismatch")
    return {
        "status": "ok" if not bad_wallets else "blocked",
        "models_count": model_count,
        "ranked_models": len(rankings),
        "eligible_for_real": len([row for row in rankings if row.get("eligible_for_real")]),
        "bad_wallets": bad_wallets,
        "issues": issues,
    }


def audit_model_decision_integrity(data: dict, settings: dict) -> dict:
    rankings = get_model_rankings(data)
    recommendation = build_weighted_recommendation(data, settings)
    approval = build_real_model_approval(data, settings)
    safety = build_real_trade_safety_status(data, settings)
    runtime = build_runtime_health(data, settings)
    issues = []
    if recommendation.get("action") == "SWITCH_TO_NEW_MODEL" and safety.get("real_order_allowed"):
        issues.append("real_order_unexpectedly_allowed")
    if recommendation.get("action") == "SWITCH_TO_NEW_MODEL" and not recommendation.get("candidate_model_id"):
        issues.append("switch_without_candidate")
    if runtime.get("status") != "ok" and recommendation.get("action") == "SWITCH_TO_NEW_MODEL":
        issues.append("switch_recommendation_while_runtime_degraded")
    top = rankings[0] if rankings else None
    return {
        "status": "ok" if not issues else "review",
        "top_model": top,
        "recommendation": recommendation,
        "approval": approval,
        "safety_status": safety.get("status"),
        "runtime_status": runtime.get("status"),
        "issues": issues,
    }


def audit_rule_snapshot_and_attribution(data: dict, settings: dict) -> dict:
    lab = ensure_paper_lab(data)
    versioned_positions = 0
    total_positions = 0
    combo_counter = Counter()
    for model in (lab.get("models") or {}).values():
        for pos in (model.get("open_positions") or []) + (model.get("history") or []):
            total_positions += 1
            if pos.get("rule_snapshot") or pos.get("settings_snapshot") or pos.get("filter_id"):
                versioned_positions += 1
            combo_counter[(model.get("filter_id"), model.get("strategy_id"))] += 1
    return {
        "status": "ok" if total_positions == 0 or versioned_positions >= max(1, int(total_positions * 0.8)) else "review",
        "total_positions": total_positions,
        "versioned_positions": versioned_positions,
        "top_combinations": [
            {"filter_id": k[0], "strategy_id": k[1], "samples": v}
            for k, v in combo_counter.most_common(10)
        ],
    }


def audit_real_safety_and_recovery(data: dict, settings: dict) -> dict:
    safety = build_real_trade_safety_status(data, settings)
    runtime = build_runtime_health(data, settings)
    cooldown = build_cooldown_policy(data, settings)
    issues = []
    if safety.get("real_order_allowed"):
        issues.append("real_order_allowed_should_remain_false")
    if data.get("emergency_lock") and data.get("bot_running"):
        issues.append("bot_running_under_emergency_lock")
    if cooldown.get("status") == "blocked" and safety.get("status") not in {"blocked", "ready_locked_review"}:
        issues.append("cooldown_not_reflected_in_safety")
    return {"status": "ok" if not issues else "blocked", "safety": safety, "runtime": runtime, "cooldown": cooldown, "issues": issues}


def build_product_readiness_score(data: dict, settings: dict) -> dict:
    checks = [
        audit_scan_universe(data, settings),
        audit_paper_lab_integrity(data, settings),
        audit_model_decision_integrity(data, settings),
        audit_rule_snapshot_and_attribution(data, settings),
        audit_real_safety_and_recovery(data, settings),
    ]
    penalties = 0
    for check in checks:
        if check.get("status") == "blocked":
            penalties += 25
        elif check.get("status") == "review":
            penalties += 10
    score = max(0, 100 - penalties)
    return {
        "score": score,
        "state": "ready_for_shadow_observation" if score >= 80 else ("needs_review" if score >= 55 else "blocked"),
        "checks": checks,
    }


def build_revision10_quality_report(data: dict, settings: dict, run_live_scan: bool = False) -> dict:
    reports = build_reports(data, settings)
    readiness = build_product_readiness_score(data, settings)
    return {
        "status": "ok",
        "revision": "revizyon_10",
        "api_contract": build_api_contract_matrix(),
        "scan_universe": audit_scan_universe(data, settings, run_live_scan=run_live_scan),
        "paper_lab": audit_paper_lab_integrity(data, settings),
        "model_decision": audit_model_decision_integrity(data, settings),
        "rule_snapshot": audit_rule_snapshot_and_attribution(data, settings),
        "real_safety": audit_real_safety_and_recovery(data, settings),
        "market_regime": detect_market_regime(data, settings),
        "dynamic_risk": build_dynamic_risk_adjustment(data, settings),
        "portfolio_allocation": build_portfolio_allocation(data, settings),
        "observability": build_observability(data, settings),
        "reports_summary": {
            "models_count": (reports.get("paper_lab") or {}).get("models_count", 0),
            "recommendation": (reports.get("recommendation") or {}).get("action"),
            "filter_groups": len(reports.get("filter_ranking") or []),
            "strategy_groups": len(reports.get("strategy_ranking") or []),
        },
        "product_readiness": readiness,
        "next_gate": "24h shadow/paper observation" if readiness.get("score", 0) >= 80 else "fix review/blocker items first",
    }
