from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean

from services.analysis_service import scan_market
from services.execution_simulator import build_execution_quality
from services.intelligence_service import (
    build_coin_quality_dashboard,
    build_cooldown_policy,
    build_dynamic_risk_adjustment,
    build_observability,
    build_orderbook_intelligence,
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
from services.rule_engine import list_rules


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _status(issues: list[str], blockers: list[str] | None = None) -> str:
    blockers = blockers or []
    if blockers:
        return "blocked"
    if issues:
        return "review"
    return "ok"


def build_api_contract_v2() -> dict:
    contracts = [
        {"page": "dashboard", "action": "start", "method": "POST", "endpoint": "/api/bot/start", "role": "user", "audit": True},
        {"page": "dashboard", "action": "stop", "method": "POST", "endpoint": "/api/bot/stop", "role": "user", "audit": True},
        {"page": "dashboard", "action": "emergency", "method": "POST", "endpoint": "/api/bot/emergency-stop", "role": "user", "audit": True},
        {"page": "dashboard", "action": "emergency_unlock", "method": "POST", "endpoint": "/api/bot/emergency-unlock", "role": "owner", "audit": True},
        {"page": "settings", "action": "save", "method": "POST", "endpoint": "/api/settings", "role": "user", "audit": True},
        {"page": "settings", "action": "risk_profile", "method": "POST", "endpoint": "/api/settings/risk-profiles/{profile_id}", "role": "user", "audit": True},
        {"page": "rules", "action": "validate", "method": "POST", "endpoint": "/api/rules/validate", "role": "ahmet", "audit": False},
        {"page": "rules", "action": "save", "method": "POST", "endpoint": "/api/rules/save", "role": "ahmet", "audit": True},
        {"page": "rules", "action": "delete", "method": "DELETE", "endpoint": "/api/rules/{rule_id}", "role": "ahmet", "audit": True},
        {"page": "rules", "action": "import", "method": "POST", "endpoint": "/api/rules/import", "role": "ahmet", "audit": True},
        {"page": "rules", "action": "export", "method": "GET", "endpoint": "/api/rules/export", "role": "ahmet", "audit": False},
        {"page": "rules", "action": "restore_version", "method": "POST", "endpoint": "/api/rules/{rule_id}/restore-version", "role": "ahmet", "audit": True},
        {"page": "reports", "action": "export", "method": "GET", "endpoint": "/api/models/reports/export", "role": "user", "audit": False},
        {"page": "reports", "action": "archive", "method": "POST", "endpoint": "/api/models/reports/archive", "role": "user", "audit": True},
        {"page": "realApproval", "action": "decision", "method": "POST", "endpoint": "/api/models/real-approval/decision", "role": "owner", "audit": True},
        {"page": "realApproval", "action": "dry_run_order", "method": "POST", "endpoint": "/api/models/real-order/dry-run", "role": "owner", "audit": True},
        {"page": "users", "action": "create", "method": "POST", "endpoint": "/api/users", "role": "owner", "audit": True},
        {"page": "users", "action": "reset_password", "method": "POST", "endpoint": "/api/users/{username}/reset-password", "role": "owner", "audit": True},
        {"page": "users", "action": "active", "method": "POST", "endpoint": "/api/users/{username}/active", "role": "owner", "audit": True},
        {"page": "backups", "action": "list", "method": "GET", "endpoint": "/api/bot/backups", "role": "owner", "audit": False},
        {"page": "backups", "action": "restore", "method": "POST", "endpoint": "/api/bot/restore-backup", "role": "owner", "audit": True},
        {"page": "audit", "action": "clear", "method": "DELETE", "endpoint": "/api/audit", "role": "owner", "audit": True},
        {"page": "audit", "action": "export", "method": "GET", "endpoint": "/api/audit/export", "role": "owner", "audit": False},
        {"page": "intelligence", "action": "overview", "method": "GET", "endpoint": "/api/intelligence/overview", "role": "user", "audit": False},
        {"page": "quality", "action": "revision_11", "method": "GET", "endpoint": "/api/quality/revision-11", "role": "user", "audit": False},
    ]
    by_page = Counter(row["page"] for row in contracts)
    by_role = Counter(row["role"] for row in contracts)
    coverage = {
        "requires_owner": sum(1 for row in contracts if row["role"] == "owner"),
        "requires_ahmet": sum(1 for row in contracts if row["role"] == "ahmet"),
        "audited_mutations": sum(1 for row in contracts if row["audit"]),
        "mutations": sum(1 for row in contracts if row["method"] in {"POST", "PUT", "PATCH", "DELETE"}),
    }
    return {"status": "ok", "revision": "revizyon_11", "count": len(contracts), "contracts": contracts, "by_page": dict(by_page), "by_role": dict(by_role), "coverage": coverage}


def audit_scan_universe_v2(data: dict, settings: dict, run_live_scan: bool = False, limit: int = 1000) -> dict:
    scan = data.get("last_scan") or {}
    source = "last_scan"
    if run_live_scan:
        scan = scan_market(settings, limit=limit)
        source = "live_scan"
    rows = scan.get("scan_rows") or []
    scanned = int(scan.get("scanned") or len(rows))
    candidates = scan.get("candidates") or []
    diagnostics = scan.get("scan_diagnostics") or {}
    rejection = scan.get("rejection_breakdown") or {}
    blockers, issues = [], []
    if scanned == 0:
        blockers.append("scan_empty")
    elif scanned < 50 and not scan.get("error"):
        issues.append("scan_universe_suspiciously_small")
    if not diagnostics:
        issues.append("missing_scan_diagnostics")
    if scanned and len(rows) and scanned < len(rows):
        issues.append("scanned_count_less_than_rows")
    quality_values = [_safe_float(row.get("quality_score")) for row in rows if _safe_float(row.get("quality_score")) > 0]
    return {
        "status": _status(issues, blockers),
        "source": source,
        "scanned": scanned,
        "rows_returned": len(rows),
        "candidates_count": int(scan.get("candidates_count") or len(candidates)),
        "rejected_count": int(scan.get("rejected_count") or max(0, scanned - len(candidates))),
        "top_rejection_reason": scan.get("top_rejection_reason"),
        "rejection_breakdown": rejection,
        "avg_quality_score": round(mean(quality_values), 2) if quality_values else 0,
        "diagnostics": diagnostics,
        "issues": issues,
        "blockers": blockers,
    }


def audit_execution_simulator_v2(data: dict, settings: dict) -> dict:
    rows = (data.get("last_scan") or {}).get("scan_rows") or []
    candidates = (data.get("last_scan") or {}).get("candidates") or rows[:25]
    samples = []
    rejected = Counter()
    for candidate in candidates[:50]:
        quality = build_execution_quality(candidate, settings)
        samples.append({
            "symbol": candidate.get("symbol"),
            "status": quality.get("status"),
            "execution_quality_score": quality.get("execution_quality_score"),
            "fill_probability": quality.get("fill_probability"),
            "spread_percent": quality.get("spread_percent"),
            "slippage_percent": quality.get("slippage_percent"),
            "blockers": quality.get("blockers"),
        })
        for blocker in quality.get("blockers") or []:
            rejected[blocker] += 1
    scores = [_safe_float(item.get("execution_quality_score")) for item in samples if item.get("execution_quality_score") is not None]
    issues = []
    if not samples:
        issues.append("execution_sample_waiting_for_scan")
    if scores and mean(scores) < 45:
        issues.append("low_execution_quality_universe")
    return {"status": _status(issues), "sample_size": len(samples), "avg_execution_quality": round(mean(scores), 2) if scores else 0, "rejections": dict(rejected), "samples": samples[:15], "issues": issues}


def audit_wallet_integrity_v2(data: dict, settings: dict) -> dict:
    lab = ensure_paper_lab(data)
    rankings = get_model_rankings(data)
    bad_wallets = []
    low_execution_models = []
    for row in rankings:
        expected = _safe_float(row.get("wallet_start"), 1000) + _safe_float(row.get("total_pnl"))
        if abs(expected - _safe_float(row.get("wallet_value"))) > 0.05:
            bad_wallets.append({"model_id": row.get("model_id"), "expected": round(expected, 4), "actual": row.get("wallet_value")})
        if _safe_float(row.get("execution_quality_score"), 50) < 45 and int(row.get("total_trades") or 0) > 0:
            low_execution_models.append(row.get("model_id"))
    issues = []
    blockers = []
    if bad_wallets:
        blockers.append("wallet_value_mismatch")
    if low_execution_models:
        issues.append("low_execution_quality_models")
    return {"status": _status(issues, blockers), "models_count": len(lab.get("models", {}) or {}), "ranked_models": len(rankings), "bad_wallets": bad_wallets[:20], "low_execution_models": low_execution_models[:20], "issues": issues, "blockers": blockers}


def audit_model_score_v2(data: dict, settings: dict) -> dict:
    rankings = get_model_rankings(data)
    issues = []
    if rankings and rankings[0].get("eligible_for_real") and int(rankings[0].get("total_trades") or 0) < 7:
        issues.append("top_model_eligible_with_low_trade_depth")
    component_coverage = Counter()
    for row in rankings:
        for key in (row.get("score_components") or {}).keys():
            component_coverage[key] += 1
    top = rankings[0] if rankings else None
    return {"status": _status(issues), "top_model": top, "ranked_models": len(rankings), "component_coverage": dict(component_coverage), "issues": issues}


def audit_recommendation_v2(data: dict, settings: dict) -> dict:
    rec = build_weighted_recommendation(data, settings)
    safety = build_real_trade_safety_status(data, settings)
    health = build_runtime_health(data, settings)
    issues = []
    blockers = []
    if rec.get("action") == "SWITCH_TO_NEW_MODEL" and not rec.get("candidate_model_id"):
        blockers.append("switch_without_candidate")
    if rec.get("action") == "SWITCH_TO_NEW_MODEL" and health.get("status") != "ok":
        blockers.append("switch_while_runtime_degraded")
    if safety.get("real_order_allowed"):
        blockers.append("real_order_allowed_unexpected")
    return {"status": _status(issues, blockers), "recommendation": rec, "safety_status": safety.get("status"), "runtime_status": health.get("status"), "issues": issues, "blockers": blockers}


def audit_attribution_v2(data: dict, settings: dict) -> dict:
    reports = build_reports(data, settings)
    filter_rows = reports.get("filter_ranking") or []
    strategy_rows = reports.get("strategy_ranking") or []
    risk_rows = reports.get("risk_ranking") or []
    issues = []
    if not filter_rows and not strategy_rows:
        issues.append("attribution_waiting_for_trade_history")
    return {"status": _status(issues), "filter_groups": len(filter_rows), "strategy_groups": len(strategy_rows), "risk_groups": len(risk_rows), "top_filter": filter_rows[0] if filter_rows else None, "top_strategy": strategy_rows[0] if strategy_rows else None, "issues": issues}


def audit_rule_snapshot_v2(data: dict, settings: dict, username: str = "ahmet") -> dict:
    rules = list_rules(username) if username == "ahmet" else {"rules": []}
    lab = ensure_paper_lab(data)
    total_positions = 0
    snapshot_positions = 0
    for model in (lab.get("models") or {}).values():
        for pos in (model.get("open_positions") or []) + (model.get("history") or []):
            total_positions += 1
            if pos.get("rule_snapshot") or pos.get("filter_id"):
                snapshot_positions += 1
    issues = []
    if total_positions and snapshot_positions / max(total_positions, 1) < 0.8:
        issues.append("rule_snapshot_coverage_low")
    return {"status": _status(issues), "custom_rules": len(rules.get("rules") or []), "total_positions": total_positions, "snapshot_positions": snapshot_positions, "coverage_percent": round(snapshot_positions / max(total_positions, 1) * 100, 2) if total_positions else 100, "issues": issues}


def audit_safety_recovery_v2(data: dict, settings: dict) -> dict:
    safety = build_real_trade_safety_status(data, settings)
    approval = build_real_model_approval(data, settings)
    cooldown = build_cooldown_policy(data, settings)
    issues, blockers = [], []
    if safety.get("real_order_allowed"):
        blockers.append("real_order_allowed_must_stay_false")
    if data.get("emergency_lock") and data.get("bot_running"):
        blockers.append("bot_running_under_emergency_lock")
    if approval.get("can_request_approval") and safety.get("real_order_allowed"):
        blockers.append("approval_enables_real_order")
    if cooldown.get("status") == "blocked" and not safety.get("blockers"):
        issues.append("cooldown_not_visible_in_safety")
    return {"status": _status(issues, blockers), "safety": safety, "approval": approval, "cooldown": cooldown, "issues": issues, "blockers": blockers}


def build_button_smoke_matrix_v2() -> dict:
    contract = build_api_contract_v2()
    rows = []
    for item in contract["contracts"]:
        rows.append({
            "page": item["page"],
            "action": item["action"],
            "endpoint": item["endpoint"],
            "method": item["method"],
            "role": item["role"],
            "event_expected": True,
            "api_expected": True,
            "audit_expected": item["audit"],
            "status": "mapped",
        })
    return {"status": "ok", "count": len(rows), "rows": rows}


def build_revision_11_quality_report(data: dict, settings: dict, username: str = "ahmet", run_live_scan: bool = False) -> dict:
    blocks = {
        "api_contract": build_api_contract_v2(),
        "button_smoke_matrix": build_button_smoke_matrix_v2(),
        "scan_universe": audit_scan_universe_v2(data, settings, run_live_scan=run_live_scan),
        "execution_simulator": audit_execution_simulator_v2(data, settings),
        "wallet_integrity": audit_wallet_integrity_v2(data, settings),
        "model_score": audit_model_score_v2(data, settings),
        "recommendation": audit_recommendation_v2(data, settings),
        "attribution": audit_attribution_v2(data, settings),
        "coin_quality": build_coin_quality_dashboard(data, settings),
        "market_regime": detect_market_regime(data, settings),
        "orderbook": build_orderbook_intelligence(data, settings),
        "cooldown": build_cooldown_policy(data, settings),
        "dynamic_risk": build_dynamic_risk_adjustment(data, settings),
        "portfolio_allocation": build_portfolio_allocation(data, settings),
        "rule_snapshot": audit_rule_snapshot_v2(data, settings, username=username),
        "safety_recovery": audit_safety_recovery_v2(data, settings),
        "observability": build_observability(data, settings),
    }
    blockers = []
    reviews = []
    for name, payload in blocks.items():
        status = payload.get("status") if isinstance(payload, dict) else "ok"
        if status == "blocked":
            blockers.append(name)
        elif status == "review":
            reviews.append(name)
    score = max(0, 100 - len(blockers) * 18 - len(reviews) * 6)
    return {
        "status": "blocked" if blockers else ("review" if reviews else "ok"),
        "revision": "revizyon_11",
        "score": score,
        "state": "ready_for_observation" if score >= 82 and not blockers else ("needs_review" if score >= 60 else "blocked"),
        "blockers": blockers,
        "reviews": reviews,
        "blocks": blocks,
        "next_gate": "24h shadow/paper observation" if score >= 82 and not blockers else "fix blocked/review items before live expansion",
    }
