from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_owner, require_user
from core.config import DEFAULT_USER
from core.storage import append_audit, load_shadow, load_settings, save_shadow, now_iso
from services.intelligence_service import (
    build_ab_test_plan,
    build_ai_strategy_insights,
    build_cooldown_policy,
    build_dynamic_risk_adjustment,
    build_execution_quality_summary,
    build_micro_pilot_plan,
    build_model_degradation,
    build_optimization_overview,
    build_portfolio_allocation,
    build_replay_index,
    build_coin_quality_dashboard,
    build_coin_clusters,
    build_orderbook_intelligence,
    build_multi_timeframe_signal,
    build_news_risk_filter,
    build_observability,
    build_trade_explainability,
    build_safe_deploy_state,
    build_strategy_generator,
    build_walk_forward_summary,
    detect_market_regime,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/overview")
def intelligence_overview(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_optimization_overview(data, settings)
    payload["user"] = user
    return payload


@router.get("/market-regime")
def market_regime(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "market_regime": detect_market_regime(load_shadow(user), load_settings(user))}


@router.get("/dynamic-risk")
def dynamic_risk(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "dynamic_risk": build_dynamic_risk_adjustment(load_shadow(user), load_settings(user))}


@router.get("/ab-tests")
def ab_tests(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "plan": build_ab_test_plan(load_shadow(user), load_settings(user))}


@router.get("/portfolio-allocation")
def portfolio_allocation(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "allocation": build_portfolio_allocation(load_shadow(user), load_settings(user))}


@router.get("/cooldown")
def cooldown(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "cooldown": build_cooldown_policy(load_shadow(user), load_settings(user))}


@router.get("/walk-forward")
def walk_forward(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "walk_forward": build_walk_forward_summary(load_shadow(user), load_settings(user))}


@router.get("/degradation")
def degradation(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "degradation": build_model_degradation(load_shadow(user), load_settings(user))}


@router.get("/execution-quality")
def execution_quality(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "execution_quality": build_execution_quality_summary(load_shadow(user), load_settings(user))}


@router.get("/strategy-generator")
def strategy_generator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "generator": build_strategy_generator(load_shadow(user), load_settings(user))}


@router.post("/strategy-generator/accept-draft")
def accept_strategy_draft(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    draft_id = str((payload or {}).get("draft_id") or "AUTO_DRAFT_SCALP_001")
    append_audit(data, "strategy_generator", "ok", f"Paper-only strateji taslağı izlemeye alındı: {draft_id}", {"draft_id": draft_id}, user=user)
    data.setdefault("strategy_draft_watchlist", []).append({"draft_id": draft_id, "accepted_at": now_iso(), "paper_only": True})
    data["strategy_draft_watchlist"] = data.get("strategy_draft_watchlist", [])[-100:]
    save_shadow(data, user)
    return {"status": "accepted", "user": user, "draft_id": draft_id, "paper_only": True}


@router.get("/ai-insights")
def ai_insights(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "insights": build_ai_strategy_insights(load_shadow(user), load_settings(user))}


@router.get("/safe-deploy")
def safe_deploy(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "safe_deploy": build_safe_deploy_state(load_shadow(user), load_settings(user))}


@router.get("/replay")
def replay(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "replay": build_replay_index(load_shadow(user), load_settings(user))}


@router.get("/micro-pilot")
def micro_pilot(current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "pilot": build_micro_pilot_plan(load_shadow(user), load_settings(user))}


@router.get("/coin-quality")
def coin_quality(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "coin_quality": build_coin_quality_dashboard(load_shadow(user), load_settings(user))}


@router.get("/coin-clusters")
def coin_clusters(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "coin_clusters": build_coin_clusters(load_shadow(user), load_settings(user))}


@router.get("/orderbook")
def orderbook(symbol: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    rows = (data.get("last_scan") or {}).get("scan_rows") or (data.get("last_scan") or {}).get("candidates") or []
    candidate = None
    if symbol:
        candidate = next((row for row in rows if str(row.get("symbol") or "").upper() == symbol.upper()), None)
    candidate = candidate or (rows[0] if rows else {})
    return {"status": "ok", "user": user, "orderbook": build_orderbook_intelligence(candidate, load_settings(user))}


@router.get("/multi-timeframe")
def multi_timeframe(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "multi_timeframe": build_multi_timeframe_signal(load_shadow(user), load_settings(user))}


@router.get("/news-risk")
def news_risk(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "news_risk": build_news_risk_filter(load_shadow(user), load_settings(user))}


@router.get("/observability")
def observability(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "observability": build_observability(load_shadow(user), load_settings(user))}


@router.get("/trade-explainability")
def trade_explainability(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "trade_explainability": build_trade_explainability(load_shadow(user), load_settings(user))}

from services.market_intelligence_final_service import (
    build_market_intelligence_final_report,
    build_market_regime_strategy_match,
    build_no_trade_cooldown_final,
    build_orderbook_final_report,
)


@router.get("/market-intelligence-final")
def market_intelligence_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "market_intelligence_final": build_market_intelligence_final_report(load_shadow(user), load_settings(user))}


@router.get("/regime-strategy-match")
def regime_strategy_match(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "match": build_market_regime_strategy_match(load_shadow(user), load_settings(user))}


@router.get("/orderbook-final")
def orderbook_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "orderbook_final": build_orderbook_final_report(load_shadow(user), load_settings(user))}


@router.get("/no-trade-final")
def no_trade_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "no_trade_final": build_no_trade_cooldown_final(load_shadow(user), load_settings(user))}

from services.portfolio_allocation_final_service import (
    build_active_risk_budget,
    build_allocation_audit_report,
    build_allocation_recommendation_read_only_report,
    build_correlation_cluster_exposure,
    build_portfolio_allocation_final,
    build_portfolio_allocation_schema,
    build_portfolio_visibility_summary,
    build_usdt_reserve_policy,
)


@router.get("/portfolio-allocation-final")
def portfolio_allocation_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "allocation_final": build_portfolio_allocation_final(load_shadow(user), load_settings(user))}


@router.get("/usdt-reserve-policy")
def usdt_reserve_policy(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "reserve_policy": build_usdt_reserve_policy(load_shadow(user), load_settings(user))}


@router.get("/cluster-exposure")
def cluster_exposure(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "cluster_exposure": build_correlation_cluster_exposure(load_shadow(user), load_settings(user))}


@router.get("/allocation-audit")
def allocation_audit(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "allocation_audit": build_allocation_audit_report(load_shadow(user), load_settings(user))}


@router.get("/portfolio-allocation-schema-final")
def portfolio_allocation_schema_final(current_user: dict = Depends(require_user)):
    return build_portfolio_allocation_schema()


@router.get("/active-risk-budget")
def active_risk_budget(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "active_risk_budget": build_active_risk_budget(load_shadow(user), load_settings(user))}


@router.get("/allocation-recommendation")
def allocation_recommendation(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "allocation_recommendation": build_allocation_recommendation_read_only_report(load_shadow(user), load_settings(user))}


@router.get("/portfolio-visibility")
def portfolio_visibility(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "portfolio_visibility": build_portfolio_visibility_summary(load_shadow(user), load_settings(user))}

# Rev51 Coin Universe / Market Intelligence final endpoints
from services.coin_market_intelligence_service import (
    build_coin_market_intelligence_quality,
    build_coin_universe_funnel,
    build_coin_universe_schema,
    build_market_regime_final,
    build_market_visibility_summary,
    build_no_trade_reason_matrix,
    build_scan_history_final,
    build_scan_replay_final,
    build_strategy_suppression_matrix,
)


@router.get("/coin-universe/schema-final")
def coin_universe_schema_final(current_user: dict = Depends(require_user)):
    return build_coin_universe_schema()


@router.get("/coin-universe/funnel-final")
def coin_universe_funnel_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "coin_universe": build_coin_universe_funnel(load_shadow(user), load_settings(user))}


@router.get("/scan-history-final")
def scan_history_final(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "scan_history": build_scan_history_final(load_shadow(user), limit=limit)}


@router.get("/scan-replay-final")
def scan_replay_final(scan_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "scan_replay": build_scan_replay_final(load_shadow(user), scan_id=scan_id)}


@router.get("/market-regime-final")
def market_regime_final_v51(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "market_regime_final": build_market_regime_final(load_shadow(user), load_settings(user))}


@router.get("/no-trade-reason-matrix")
def no_trade_reason_matrix(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "no_trade_matrix": build_no_trade_reason_matrix(load_shadow(user), load_settings(user))}


@router.get("/strategy-suppression-matrix")
def strategy_suppression_matrix(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "suppression_matrix": build_strategy_suppression_matrix(load_shadow(user), load_settings(user))}


@router.get("/market-visibility")
def market_visibility(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "market_visibility": build_market_visibility_summary(load_shadow(user), load_settings(user))}


@router.get("/coin-market-quality")
def coin_market_quality(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "quality": build_coin_market_intelligence_quality(load_shadow(user), load_settings(user))}

# Rev60 Autonomous Market Scanner / Tradeability Engine
from services.autonomous_market_scanner_service import (
    build_autonomous_market_scanner,
    build_tradeability_decision,
    build_summary_autonomous_decision,
)


@router.get("/autonomous-market-scanner")
def autonomous_market_scanner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_market_scanner": build_autonomous_market_scanner(load_shadow(user), load_settings(user))}


@router.get("/tradeability-decision")
def tradeability_decision(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "tradeability_decision": build_tradeability_decision(load_shadow(user), load_settings(user))}


@router.get("/summary-autonomous-decision")
def summary_autonomous_decision(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_decision": build_summary_autonomous_decision(load_shadow(user), load_settings(user))}

# Rev61 Auto Bot Mode Decision Engine
from services.auto_bot_mode_decision_service import (
    build_auto_bot_mode_decision,
    build_summary_auto_bot_mode,
)


@router.get("/auto-bot-mode-decision")
def auto_bot_mode_decision(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "auto_bot_mode_decision": build_auto_bot_mode_decision(load_shadow(user), load_settings(user))}


@router.get("/summary-auto-bot-mode")
def summary_auto_bot_mode(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "auto_bot_mode": build_summary_auto_bot_mode(load_shadow(user), load_settings(user))}


# Rev62 Strategy Selection Engine
from services.strategy_selection_engine_service import (
    build_strategy_selection_engine,
    build_summary_strategy_selection,
)


@router.get("/strategy-selection-engine")
def strategy_selection_engine(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "strategy_selection": build_strategy_selection_engine(load_shadow(user), load_settings(user))}


@router.get("/summary-strategy-selection")
def summary_strategy_selection(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "strategy_selection_summary": build_summary_strategy_selection(load_shadow(user), load_settings(user))}


# Rev63 Risk Brain
from services.risk_brain_service import (
    build_risk_brain,
    build_summary_risk_brain,
)


@router.get("/risk-brain")
def risk_brain(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "risk_brain": build_risk_brain(load_shadow(user), load_settings(user))}


@router.get("/summary-risk-brain")
def summary_risk_brain(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "risk_brain_summary": build_summary_risk_brain(load_shadow(user), load_settings(user))}


# Rev64 Trade Quality Feedback Engine
from services.trade_quality_feedback_service import (
    build_summary_trade_quality_feedback,
    build_trade_quality_feedback,
)


@router.get("/trade-quality-feedback")
def trade_quality_feedback(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "trade_quality_feedback": build_trade_quality_feedback(load_shadow(user), load_settings(user))}


@router.get("/summary-trade-quality-feedback")
def summary_trade_quality_feedback(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "trade_quality_feedback_summary": build_summary_trade_quality_feedback(load_shadow(user), load_settings(user))}


# Rev65 Autonomous Daily Operation
from services.autonomous_daily_operation_service import (
    build_autonomous_daily_operation,
    build_summary_daily_operation,
)


@router.get("/autonomous-daily-operation")
def autonomous_daily_operation(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "daily_operation": build_autonomous_daily_operation(load_shadow(user), load_settings(user))}


@router.get("/summary-daily-operation")
def summary_daily_operation(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "daily_operation_summary": build_summary_daily_operation(load_shadow(user), load_settings(user))}




# Rev68 Autonomous Execution Governor
from core.auth import read_auth_store
from services.autonomous_execution_governor_service import (
    build_autonomous_execution_governor,
    build_summary_execution_governor,
)


@router.get("/autonomous-execution-governor")
def autonomous_execution_governor(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "execution_governor": build_autonomous_execution_governor(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-execution-governor")
def summary_execution_governor(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "execution_governor_summary": build_summary_execution_governor(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev66 Minimal Summary Dashboard
from services.minimal_summary_dashboard_service import build_minimal_summary_dashboard
from services.summary_service import build_summary


@router.get("/minimal-summary-dashboard")
def minimal_summary_dashboard(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    summary = build_summary(data, settings, user=user)
    return {"status": summary.get("minimal_dashboard", {}).get("status", "review"), "user": user, "minimal_dashboard": build_minimal_summary_dashboard(summary, data, settings)}

# Rev69 Adaptive Parameter Tuner
from services.adaptive_parameter_tuner_service import (
    build_adaptive_parameter_tuner,
    build_summary_adaptive_parameter_tuner,
)


@router.get("/adaptive-parameter-tuner")
def adaptive_parameter_tuner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "adaptive_parameter_tuner": build_adaptive_parameter_tuner(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-adaptive-parameter-tuner")
def summary_adaptive_parameter_tuner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "adaptive_parameter_tuner_summary": build_summary_adaptive_parameter_tuner(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev70 Autonomous Control Loop
from services.autonomous_control_loop_service import (
    build_autonomous_control_loop,
    build_summary_autonomous_control_loop,
)


@router.get("/autonomous-control-loop")
def autonomous_control_loop(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_control_loop": build_autonomous_control_loop(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-control-loop")
def summary_autonomous_control_loop(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_control_loop_summary": build_summary_autonomous_control_loop(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev71 Autonomous Safety Supervisor
from services.autonomous_safety_supervisor_service import (
    build_autonomous_safety_supervisor,
    build_summary_autonomous_safety_supervisor,
)


@router.get("/autonomous-safety-supervisor")
def autonomous_safety_supervisor(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_safety_supervisor": build_autonomous_safety_supervisor(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-safety-supervisor")
def summary_autonomous_safety_supervisor(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_safety_supervisor_summary": build_summary_autonomous_safety_supervisor(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev72 Autonomous Evidence & Learning Memory
from services.autonomous_evidence_learning_memory_service import (
    build_autonomous_evidence_learning_memory,
    build_summary_autonomous_evidence_learning_memory,
)


@router.get("/autonomous-evidence-learning-memory")
def autonomous_evidence_learning_memory(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_evidence_learning_memory": build_autonomous_evidence_learning_memory(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-evidence-learning-memory")
def summary_autonomous_evidence_learning_memory(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_evidence_learning_memory_summary": build_summary_autonomous_evidence_learning_memory(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev73 Autonomous Capital Allocator
from services.autonomous_capital_allocator_service import (
    build_autonomous_capital_allocator,
    build_summary_autonomous_capital_allocator,
)


@router.get("/autonomous-capital-allocator")
def autonomous_capital_allocator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_capital_allocator": build_autonomous_capital_allocator(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-capital-allocator")
def summary_autonomous_capital_allocator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_capital_allocator_summary": build_summary_autonomous_capital_allocator(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev74 Autonomous Position Manager
from services.autonomous_position_manager_service import (
    build_autonomous_position_manager,
    build_summary_autonomous_position_manager,
)


@router.get("/autonomous-position-manager")
def autonomous_position_manager(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_position_manager": build_autonomous_position_manager(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-position-manager")
def summary_autonomous_position_manager(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_position_manager_summary": build_summary_autonomous_position_manager(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev75 Autonomous Performance Sentinel
from services.autonomous_performance_sentinel_service import (
    build_autonomous_performance_sentinel,
    build_summary_autonomous_performance_sentinel,
)


@router.get("/autonomous-performance-sentinel")
def autonomous_performance_sentinel(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_performance_sentinel": build_autonomous_performance_sentinel(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-performance-sentinel")
def summary_autonomous_performance_sentinel(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_performance_sentinel_summary": build_summary_autonomous_performance_sentinel(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev76 Autonomous Opportunity Router
from services.autonomous_opportunity_router_service import (
    build_autonomous_opportunity_router,
    build_summary_autonomous_opportunity_router,
)


@router.get("/autonomous-opportunity-router")
def autonomous_opportunity_router(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_opportunity_router": build_autonomous_opportunity_router(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-opportunity-router")
def summary_autonomous_opportunity_router(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_opportunity_router_summary": build_summary_autonomous_opportunity_router(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev77 Autonomous Signal Validator
from services.autonomous_signal_validator_service import (
    build_autonomous_signal_validator,
    build_summary_autonomous_signal_validator,
)


@router.get("/autonomous-signal-validator")
def autonomous_signal_validator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_signal_validator": build_autonomous_signal_validator(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-signal-validator")
def summary_autonomous_signal_validator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_signal_validator_summary": build_summary_autonomous_signal_validator(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev78 Autonomous Trade Intent Builder
from services.autonomous_trade_intent_builder_service import (
    build_autonomous_trade_intent_builder,
    build_summary_autonomous_trade_intent_builder,
)


@router.get("/autonomous-trade-intent-builder")
def autonomous_trade_intent_builder(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_trade_intent_builder": build_autonomous_trade_intent_builder(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-trade-intent-builder")
def summary_autonomous_trade_intent_builder(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_trade_intent_builder_summary": build_summary_autonomous_trade_intent_builder(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev79 Autonomous Order Execution Planner
from services.autonomous_order_execution_planner_service import (
    build_autonomous_order_execution_planner,
    build_summary_autonomous_order_execution_planner,
)


@router.get("/autonomous-order-execution-planner")
def autonomous_order_execution_planner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_order_execution_planner": build_autonomous_order_execution_planner(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-order-execution-planner")
def summary_autonomous_order_execution_planner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_order_execution_planner_summary": build_summary_autonomous_order_execution_planner(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev80 Autonomous Execution Simulator
from services.autonomous_execution_simulator_service import (
    build_autonomous_execution_simulator,
    build_summary_autonomous_execution_simulator,
)


@router.get("/autonomous-execution-simulator")
def autonomous_execution_simulator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_execution_simulator": build_autonomous_execution_simulator(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-execution-simulator")
def summary_autonomous_execution_simulator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_execution_simulator_summary": build_summary_autonomous_execution_simulator(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev81 Autonomous Execution Approval Gate
from services.autonomous_execution_approval_gate_service import (
    build_autonomous_execution_approval_gate,
    build_summary_autonomous_execution_approval_gate,
)


@router.get("/autonomous-execution-approval-gate")
def autonomous_execution_approval_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_execution_approval_gate": build_autonomous_execution_approval_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-execution-approval-gate")
def summary_autonomous_execution_approval_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_execution_approval_gate_summary": build_summary_autonomous_execution_approval_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev82 Autonomous Paper Execution Runner
from services.autonomous_paper_execution_runner_service import (
    build_autonomous_paper_execution_runner,
    build_summary_autonomous_paper_execution_runner,
)


@router.get("/autonomous-paper-execution-runner")
def autonomous_paper_execution_runner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_paper_execution_runner": build_autonomous_paper_execution_runner(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-paper-execution-runner")
def summary_autonomous_paper_execution_runner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_paper_execution_runner_summary": build_summary_autonomous_paper_execution_runner(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev83 Autonomous Paper Result Evaluator
from services.autonomous_paper_result_evaluator_service import (
    build_autonomous_paper_result_evaluator,
    build_summary_autonomous_paper_result_evaluator,
)


@router.get("/autonomous-paper-result-evaluator")
def autonomous_paper_result_evaluator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_paper_result_evaluator": build_autonomous_paper_result_evaluator(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-paper-result-evaluator")
def summary_autonomous_paper_result_evaluator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_paper_result_evaluator_summary": build_summary_autonomous_paper_result_evaluator(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev84 Autonomous Paper Promotion Gate
from services.autonomous_paper_promotion_gate_service import (
    build_autonomous_paper_promotion_gate,
    build_summary_autonomous_paper_promotion_gate,
)


@router.get("/autonomous-paper-promotion-gate")
def autonomous_paper_promotion_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_paper_promotion_gate": build_autonomous_paper_promotion_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-paper-promotion-gate")
def summary_autonomous_paper_promotion_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_paper_promotion_gate_summary": build_summary_autonomous_paper_promotion_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev85 Autonomous Micro Real Readiness Gate
from services.autonomous_micro_real_readiness_gate_service import (
    build_autonomous_micro_real_readiness_gate,
    build_summary_autonomous_micro_real_readiness_gate,
)


@router.get("/autonomous-micro-real-readiness-gate")
def autonomous_micro_real_readiness_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_readiness_gate": build_autonomous_micro_real_readiness_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-readiness-gate")
def summary_autonomous_micro_real_readiness_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_readiness_gate_summary": build_summary_autonomous_micro_real_readiness_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev86 Autonomous Micro Real Probe Planner
from services.autonomous_micro_real_probe_planner_service import (
    build_autonomous_micro_real_probe_planner,
    build_summary_autonomous_micro_real_probe_planner,
)


@router.get("/autonomous-micro-real-probe-planner")
def autonomous_micro_real_probe_planner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_probe_planner": build_autonomous_micro_real_probe_planner(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-probe-planner")
def summary_autonomous_micro_real_probe_planner(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_probe_planner_summary": build_summary_autonomous_micro_real_probe_planner(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev87 Autonomous Micro Real Approval Gate
from services.autonomous_micro_real_approval_gate_service import (
    build_autonomous_micro_real_approval_gate,
    build_summary_autonomous_micro_real_approval_gate,
)


@router.get("/autonomous-micro-real-approval-gate")
def autonomous_micro_real_approval_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_approval_gate": build_autonomous_micro_real_approval_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-approval-gate")
def summary_autonomous_micro_real_approval_gate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_approval_gate_summary": build_summary_autonomous_micro_real_approval_gate(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev88 Autonomous Micro Real Execution Sandbox
from services.autonomous_micro_real_execution_sandbox_service import (
    build_autonomous_micro_real_execution_sandbox,
    build_summary_autonomous_micro_real_execution_sandbox,
)


@router.get("/autonomous-micro-real-execution-sandbox")
def autonomous_micro_real_execution_sandbox(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_execution_sandbox": build_autonomous_micro_real_execution_sandbox(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-execution-sandbox")
def summary_autonomous_micro_real_execution_sandbox(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_execution_sandbox_summary": build_summary_autonomous_micro_real_execution_sandbox(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev89 Autonomous Micro Real Exchange Adapter Hardening
from services.autonomous_micro_real_exchange_adapter_hardening_service import (
    build_autonomous_micro_real_exchange_adapter_hardening,
    build_summary_autonomous_micro_real_exchange_adapter_hardening,
)


@router.get("/autonomous-micro-real-exchange-adapter-hardening")
def autonomous_micro_real_exchange_adapter_hardening(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_exchange_adapter_hardening": build_autonomous_micro_real_exchange_adapter_hardening(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-exchange-adapter-hardening")
def summary_autonomous_micro_real_exchange_adapter_hardening(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_exchange_adapter_hardening_summary": build_summary_autonomous_micro_real_exchange_adapter_hardening(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev90 Autonomous Micro Real Order Submitter Preview
from services.autonomous_micro_real_order_submitter_preview_service import (
    build_autonomous_micro_real_order_submitter_preview,
    build_summary_autonomous_micro_real_order_submitter_preview,
)


@router.get("/autonomous-micro-real-order-submitter-preview")
def autonomous_micro_real_order_submitter_preview(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_order_submitter_preview": build_autonomous_micro_real_order_submitter_preview(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-order-submitter-preview")
def summary_autonomous_micro_real_order_submitter_preview(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_order_submitter_preview_summary": build_summary_autonomous_micro_real_order_submitter_preview(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev91 First Micro Real Controlled Execution
from services.autonomous_first_micro_real_controlled_execution_service import (
    build_autonomous_first_micro_real_controlled_execution,
    build_summary_autonomous_first_micro_real_controlled_execution,
)


@router.get("/autonomous-first-micro-real-controlled-execution")
def autonomous_first_micro_real_controlled_execution(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_first_micro_real_controlled_execution": build_autonomous_first_micro_real_controlled_execution(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-first-micro-real-controlled-execution")
def summary_autonomous_first_micro_real_controlled_execution(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_first_micro_real_controlled_execution_summary": build_summary_autonomous_first_micro_real_controlled_execution(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev92 Autonomous Micro Real Position Tracker
from services.autonomous_micro_real_position_tracker_service import (
    build_autonomous_micro_real_position_tracker,
    build_summary_autonomous_micro_real_position_tracker,
)


@router.get("/autonomous-micro-real-position-tracker")
def autonomous_micro_real_position_tracker(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_position_tracker": build_autonomous_micro_real_position_tracker(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-position-tracker")
def summary_autonomous_micro_real_position_tracker(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_position_tracker_summary": build_summary_autonomous_micro_real_position_tracker(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev93 Autonomous Micro Real Exit Manager
from services.autonomous_micro_real_exit_manager_service import (
    build_autonomous_micro_real_exit_manager,
    build_summary_autonomous_micro_real_exit_manager,
)


@router.get("/autonomous-micro-real-exit-manager")
def autonomous_micro_real_exit_manager(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_exit_manager": build_autonomous_micro_real_exit_manager(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-exit-manager")
def summary_autonomous_micro_real_exit_manager(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_exit_manager_summary": build_summary_autonomous_micro_real_exit_manager(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev94 Autonomous Micro Real Result Evaluator
from services.autonomous_micro_real_result_evaluator_service import (
    build_autonomous_micro_real_result_evaluator,
    build_summary_autonomous_micro_real_result_evaluator,
)


@router.get("/autonomous-micro-real-result-evaluator")
def autonomous_micro_real_result_evaluator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_result_evaluator": build_autonomous_micro_real_result_evaluator(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-result-evaluator")
def summary_autonomous_micro_real_result_evaluator(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_result_evaluator_summary": build_summary_autonomous_micro_real_result_evaluator(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev95 Autonomous Micro Real Promotion/Demotion Controller
from services.autonomous_micro_real_promotion_demotion_controller_service import (
    build_autonomous_micro_real_promotion_demotion_controller,
    build_summary_autonomous_micro_real_promotion_demotion_controller,
)


@router.get("/autonomous-micro-real-promotion-demotion-controller")
def autonomous_micro_real_promotion_demotion_controller(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_promotion_demotion_controller": build_autonomous_micro_real_promotion_demotion_controller(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-micro-real-promotion-demotion-controller")
def summary_autonomous_micro_real_promotion_demotion_controller(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_promotion_demotion_controller_summary": build_summary_autonomous_micro_real_promotion_demotion_controller(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev96 Semi-Autonomous Real Trading Lane
from services.autonomous_semi_autonomous_real_trading_lane_service import (
    build_autonomous_semi_autonomous_real_trading_lane,
    build_summary_autonomous_semi_autonomous_real_trading_lane,
)


@router.get("/autonomous-semi-autonomous-real-trading-lane")
def autonomous_semi_autonomous_real_trading_lane(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_semi_autonomous_real_trading_lane": build_autonomous_semi_autonomous_real_trading_lane(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-semi-autonomous-real-trading-lane")
def summary_autonomous_semi_autonomous_real_trading_lane(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_semi_autonomous_real_trading_lane_summary": build_summary_autonomous_semi_autonomous_real_trading_lane(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev97 Fully Autonomous Small-Capital Mode
from services.autonomous_fully_autonomous_small_capital_mode_service import (
    build_autonomous_fully_autonomous_small_capital_mode,
    build_summary_autonomous_fully_autonomous_small_capital_mode,
)


@router.get("/autonomous-fully-autonomous-small-capital-mode")
def autonomous_fully_autonomous_small_capital_mode(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_fully_autonomous_small_capital_mode": build_autonomous_fully_autonomous_small_capital_mode(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-fully-autonomous-small-capital-mode")
def summary_autonomous_fully_autonomous_small_capital_mode(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_fully_autonomous_small_capital_mode_summary": build_summary_autonomous_fully_autonomous_small_capital_mode(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev98 Profit Protection & Scaling Rules
from services.autonomous_profit_protection_scaling_rules_service import (
    build_autonomous_profit_protection_scaling_rules,
    build_summary_autonomous_profit_protection_scaling_rules,
)


@router.get("/autonomous-profit-protection-scaling-rules")
def autonomous_profit_protection_scaling_rules(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_profit_protection_scaling_rules": build_autonomous_profit_protection_scaling_rules(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-profit-protection-scaling-rules")
def summary_autonomous_profit_protection_scaling_rules(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_profit_protection_scaling_rules_summary": build_summary_autonomous_profit_protection_scaling_rules(load_shadow(user), load_settings(user), read_auth_store(), user)}


# Rev99 Operator-Free Dashboard
from services.autonomous_operator_free_dashboard_service import (
    build_autonomous_operator_free_dashboard,
    build_summary_autonomous_operator_free_dashboard,
)


@router.get("/autonomous-operator-free-dashboard")
def autonomous_operator_free_dashboard(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_operator_free_dashboard": build_autonomous_operator_free_dashboard(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-operator-free-dashboard")
def summary_autonomous_operator_free_dashboard(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_operator_free_dashboard_summary": build_summary_autonomous_operator_free_dashboard(load_shadow(user), load_settings(user), read_auth_store(), user)}

# Rev100 Production Go-Live Candidate
from services.autonomous_production_go_live_candidate_service import (
    build_autonomous_production_go_live_candidate,
    build_summary_autonomous_production_go_live_candidate,
)


@router.get("/autonomous-production-go-live-candidate")
def autonomous_production_go_live_candidate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_production_go_live_candidate": build_autonomous_production_go_live_candidate(load_shadow(user), load_settings(user), read_auth_store(), user)}


@router.get("/summary-autonomous-production-go-live-candidate")
def summary_autonomous_production_go_live_candidate(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_production_go_live_candidate_summary": build_summary_autonomous_production_go_live_candidate(load_shadow(user), load_settings(user), read_auth_store(), user)}

from services.autonomous_live_config_governance_service import (
    build_autonomous_live_config_governance,
    build_summary_autonomous_live_config_governance,
)
from core.auth import read_auth_store as read_auth_store_for_autonomous_live_config_governance


@router.get("/autonomous-live-config-governance")
def autonomous_live_config_governance(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_live_config_governance": build_autonomous_live_config_governance(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_live_config_governance(), user)}


@router.get("/summary-autonomous-live-config-governance")
def summary_autonomous_live_config_governance(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_live_config_governance_summary": build_summary_autonomous_live_config_governance(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_live_config_governance(), user)}

# Rev102 Binance Live Permission + Symbol Rules Verifier
from core.auth import read_auth_store as read_auth_store_for_autonomous_binance_live_permission_symbol_rules
from services.autonomous_binance_live_permission_symbol_rules_service import (
    build_autonomous_binance_live_permission_symbol_rules,
    build_summary_autonomous_binance_live_permission_symbol_rules,
)


@router.get("/autonomous-binance-live-permission-symbol-rules")
def autonomous_binance_live_permission_symbol_rules(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_binance_live_permission_symbol_rules": build_autonomous_binance_live_permission_symbol_rules(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_binance_live_permission_symbol_rules(), user)}


@router.get("/summary-autonomous-binance-live-permission-symbol-rules")
def summary_autonomous_binance_live_permission_symbol_rules(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_binance_live_permission_symbol_rules_summary": build_summary_autonomous_binance_live_permission_symbol_rules(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_binance_live_permission_symbol_rules(), user)}

# Rev103 Micro Real Submit Dry-Run + Emergency Close Rehearsal
from core.auth import read_auth_store as read_auth_store_for_autonomous_micro_real_submit_emergency_rehearsal
from services.autonomous_micro_real_submit_emergency_rehearsal_service import (
    build_autonomous_micro_real_submit_emergency_rehearsal,
    build_summary_autonomous_micro_real_submit_emergency_rehearsal,
)


@router.get("/autonomous-micro-real-submit-emergency-rehearsal")
def autonomous_micro_real_submit_emergency_rehearsal(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_submit_emergency_rehearsal": build_autonomous_micro_real_submit_emergency_rehearsal(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_micro_real_submit_emergency_rehearsal(), user)}


@router.get("/summary-autonomous-micro-real-submit-emergency-rehearsal")
def summary_autonomous_micro_real_submit_emergency_rehearsal(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_submit_emergency_rehearsal_summary": build_summary_autonomous_micro_real_submit_emergency_rehearsal(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_micro_real_submit_emergency_rehearsal(), user)}

# Rev104 Runtime Audit Store + Idempotency Runtime Lock
from core.auth import read_auth_store as read_auth_store_for_autonomous_runtime_audit_idempotency_lock
from services.autonomous_runtime_audit_idempotency_lock_service import (
    build_autonomous_runtime_audit_idempotency_lock,
    build_summary_autonomous_runtime_audit_idempotency_lock,
)


@router.get("/autonomous-runtime-audit-idempotency-lock")
def autonomous_runtime_audit_idempotency_lock(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_runtime_audit_idempotency_lock": build_autonomous_runtime_audit_idempotency_lock(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_runtime_audit_idempotency_lock(), user)}


@router.get("/summary-autonomous-runtime-audit-idempotency-lock")
def summary_autonomous_runtime_audit_idempotency_lock(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_runtime_audit_idempotency_lock_summary": build_summary_autonomous_runtime_audit_idempotency_lock(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_runtime_audit_idempotency_lock(), user)}

# Rev105 First Micro Real Submit Enable Flag
from core.auth import read_auth_store as read_auth_store_for_autonomous_first_micro_real_submit_enable_flag
from services.autonomous_first_micro_real_submit_enable_flag_service import (
    build_autonomous_first_micro_real_submit_enable_flag,
    build_summary_autonomous_first_micro_real_submit_enable_flag,
)


@router.get("/autonomous-first-micro-real-submit-enable-flag")
def autonomous_first_micro_real_submit_enable_flag(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_first_micro_real_submit_enable_flag": build_autonomous_first_micro_real_submit_enable_flag(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_first_micro_real_submit_enable_flag(), user)}


@router.get("/summary-autonomous-first-micro-real-submit-enable-flag")
def summary_autonomous_first_micro_real_submit_enable_flag(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_first_micro_real_submit_enable_flag_summary": build_summary_autonomous_first_micro_real_submit_enable_flag(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_first_micro_real_submit_enable_flag(), user)}

# Rev106 Real Binance Micro Order Submitter
from core.auth import read_auth_store as read_auth_store_for_autonomous_real_binance_micro_order_submitter
from services.autonomous_real_binance_micro_order_submitter_service import (
    build_autonomous_real_binance_micro_order_submitter,
    build_summary_autonomous_real_binance_micro_order_submitter,
)


@router.get("/autonomous-real-binance-micro-order-submitter")
def autonomous_real_binance_micro_order_submitter(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_real_binance_micro_order_submitter": build_autonomous_real_binance_micro_order_submitter(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_real_binance_micro_order_submitter(), user)}


@router.get("/summary-autonomous-real-binance-micro-order-submitter")
def summary_autonomous_real_binance_micro_order_submitter(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_real_binance_micro_order_submitter_summary": build_summary_autonomous_real_binance_micro_order_submitter(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_real_binance_micro_order_submitter(), user)}

# Rev107 Order Status Poller + Exchange Response Recorder
from core.auth import read_auth_store as read_auth_store_for_autonomous_order_status_poller_exchange_response_recorder
from services.autonomous_order_status_poller_exchange_response_recorder_service import (
    build_autonomous_order_status_poller_exchange_response_recorder,
    build_summary_autonomous_order_status_poller_exchange_response_recorder,
)


@router.get("/autonomous-order-status-poller-exchange-response-recorder")
def autonomous_order_status_poller_exchange_response_recorder(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_order_status_poller_exchange_response_recorder": build_autonomous_order_status_poller_exchange_response_recorder(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_order_status_poller_exchange_response_recorder(), user)}


@router.get("/summary-autonomous-order-status-poller-exchange-response-recorder")
def summary_autonomous_order_status_poller_exchange_response_recorder(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_order_status_poller_exchange_response_recorder_summary": build_summary_autonomous_order_status_poller_exchange_response_recorder(load_shadow(user), load_settings(user), read_auth_store_for_autonomous_order_status_poller_exchange_response_recorder(), user)}

# Rev108-113 Micro Real Live Ops Block
from core.auth import read_auth_store as read_auth_store_for_rev108_113_live_ops
from services.autonomous_micro_real_live_ops_block_service import (
    build_rev108_balance_reconciliation_manual_attention,
    build_rev109_live_position_tracker,
    build_rev110_live_stop_tp_trailing_guard,
    build_rev111_live_exit_submitter,
    build_rev112_emergency_close_submitter,
    build_rev113_realized_pnl_trade_journal,
    build_block_payload as build_rev108_113_live_ops_block,
    build_summary_for_revision as build_rev108_113_summary_for_revision,
)

_REV108_113_BUILDERS = {
    108: build_rev108_balance_reconciliation_manual_attention,
    109: build_rev109_live_position_tracker,
    110: build_rev110_live_stop_tp_trailing_guard,
    111: build_rev111_live_exit_submitter,
    112: build_rev112_emergency_close_submitter,
    113: build_rev113_realized_pnl_trade_journal,
}

_REV108_113_NAMES = {
    108: 'autonomous_balance_reconciliation_manual_attention',
    109: 'autonomous_live_position_tracker',
    110: 'autonomous_live_stop_tp_trailing_guard',
    111: 'autonomous_live_exit_submitter',
    112: 'autonomous_emergency_close_submitter',
    113: 'autonomous_realized_pnl_trade_journal',
}


@router.get("/autonomous-micro-real-live-ops-block")
def autonomous_micro_real_live_ops_block(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_micro_real_live_ops_block": build_rev108_113_live_ops_block(load_shadow(user), load_settings(user), read_auth_store_for_rev108_113_live_ops(), user)}


@router.get("/autonomous-rev{revision}-live-ops")
def autonomous_rev_live_ops(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    builder = _REV108_113_BUILDERS.get(int(revision))
    if not builder:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev108-113 revision."}
    key = _REV108_113_NAMES[int(revision)]
    return {"status": "ok", "user": user, key: builder(load_shadow(user), load_settings(user), read_auth_store_for_rev108_113_live_ops(), user)}


@router.get("/summary-autonomous-rev{revision}-live-ops")
def summary_autonomous_rev_live_ops(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV108_113_BUILDERS:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev108-113 summary revision."}
    return {"status": "ok", "user": user, "summary": build_rev108_113_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev108_113_live_ops(), user)}

# Rev114-119 Real Learning Runtime Block
from core.auth import read_auth_store as read_auth_store_for_rev114_119_runtime_block
from services.autonomous_real_learning_runtime_block_service import (
    build_rev114_real_learning_memory,
    build_rev115_promotion_demotion_runtime_controller,
    build_rev116_size_scaling_cooldown_controller,
    build_rev117_semi_auto_real_session_runner,
    build_rev118_real_approval_policy_capital_allocator,
    build_rev119_whitelist_daily_hard_stop,
    build_block_payload as build_rev114_119_runtime_block,
    build_summary_for_revision as build_rev114_119_summary_for_revision,
)

_REV114_119_BUILDERS = {
    114: build_rev114_real_learning_memory,
    115: build_rev115_promotion_demotion_runtime_controller,
    116: build_rev116_size_scaling_cooldown_controller,
    117: build_rev117_semi_auto_real_session_runner,
    118: build_rev118_real_approval_policy_capital_allocator,
    119: build_rev119_whitelist_daily_hard_stop,
}

_REV114_119_NAMES = {
    114: 'autonomous_real_learning_memory',
    115: 'autonomous_promotion_demotion_runtime_controller',
    116: 'autonomous_size_scaling_cooldown_controller',
    117: 'autonomous_semi_auto_real_session_runner_v2',
    118: 'autonomous_real_approval_policy_capital_allocator',
    119: 'autonomous_whitelist_daily_hard_stop',
}


@router.get("/autonomous-real-learning-runtime-block")
def autonomous_real_learning_runtime_block(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_real_learning_runtime_block": build_rev114_119_runtime_block(load_shadow(user), load_settings(user), read_auth_store_for_rev114_119_runtime_block(), user)}


@router.get("/autonomous-rev{revision}-real-runtime")
def autonomous_rev_real_runtime(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    builder = _REV114_119_BUILDERS.get(int(revision))
    if not builder:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev114-119 revision."}
    key = _REV114_119_NAMES[int(revision)]
    return {"status": "ok", "user": user, key: builder(load_shadow(user), load_settings(user), read_auth_store_for_rev114_119_runtime_block(), user)}


@router.get("/summary-autonomous-rev{revision}-real-runtime")
def summary_autonomous_rev_real_runtime(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV114_119_BUILDERS:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev114-119 summary revision."}
    return {"status": "ok", "user": user, "summary": build_rev114_119_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev114_119_runtime_block(), user)}

# Rev120-125 Live Production Ops Block
from core.auth import read_auth_store as read_auth_store_for_rev120_125_live_ops_block
from services.autonomous_live_production_ops_block_service import (
    build_rev120_autonomous_scheduler_runtime,
    build_rev121_full_opportunity_execution_loop,
    build_rev122_autonomous_risk_halt_profit_protection,
    build_rev123_operator_free_live_summary,
    build_rev124_vps_production_hardening,
    build_rev125_final_live_go_no_go_candidate,
    build_block_payload as build_rev120_125_live_ops_block,
    build_summary_for_revision as build_rev120_125_summary_for_revision,
)

_REV120_125_BUILDERS = {
    120: build_rev120_autonomous_scheduler_runtime,
    121: build_rev121_full_opportunity_execution_loop,
    122: build_rev122_autonomous_risk_halt_profit_protection,
    123: build_rev123_operator_free_live_summary,
    124: build_rev124_vps_production_hardening,
    125: build_rev125_final_live_go_no_go_candidate,
}

_REV120_125_NAMES = {
    120: 'autonomous_scheduler_runtime',
    121: 'autonomous_full_opportunity_execution_loop',
    122: 'autonomous_risk_halt_profit_protection',
    123: 'autonomous_operator_free_live_summary',
    124: 'autonomous_vps_production_hardening',
    125: 'autonomous_final_live_go_no_go_candidate',
}


@router.get("/autonomous-live-production-ops-block")
def autonomous_live_production_ops_block(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_live_production_ops_block": build_rev120_125_live_ops_block(load_shadow(user), load_settings(user), read_auth_store_for_rev120_125_live_ops_block(), user)}


@router.get("/autonomous-rev{revision}-live-production")
def autonomous_rev_live_production(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    builder = _REV120_125_BUILDERS.get(int(revision))
    if not builder:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev120-125 revision."}
    key = _REV120_125_NAMES[int(revision)]
    return {"status": "ok", "user": user, key: builder(load_shadow(user), load_settings(user), read_auth_store_for_rev120_125_live_ops_block(), user)}


@router.get("/summary-autonomous-rev{revision}-live-production")
def summary_autonomous_rev_live_production(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV120_125_BUILDERS:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev120-125 summary revision."}
    return {"status": "ok", "user": user, "summary": build_rev120_125_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev120_125_live_ops_block(), user)}


# Rev126-130 Live Stabilization Block
from core.auth import read_auth_store as read_auth_store_for_rev126_130_live_stabilization
from services.autonomous_live_stabilization_block_service import (
    build_block_payload as build_rev126_130_live_stabilization_block,
    build_for_revision as build_rev126_130_for_revision,
    build_summary_for_revision as build_rev126_130_summary_for_revision,
)

_REV126_130_NAMES = {
    126: 'autonomous_live_runtime_state_supervisor',
    127: 'autonomous_service_health_recovery_guard',
    128: 'autonomous_runtime_consistency_validator',
    129: 'autonomous_live_safety_regression_pack',
    130: 'autonomous_first_live_stabilization_report',
}


@router.get("/autonomous-live-stabilization-block")
def autonomous_live_stabilization_block(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_live_stabilization_block": build_rev126_130_live_stabilization_block(load_shadow(user), load_settings(user), read_auth_store_for_rev126_130_live_stabilization(), user)}


@router.get("/autonomous-rev{revision}-live-stabilization")
def autonomous_rev_live_stabilization(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV126_130_NAMES:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev126-130 revision."}
    key = _REV126_130_NAMES[int(revision)]
    return {"status": "ok", "user": user, key: build_rev126_130_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev126_130_live_stabilization(), user)}


@router.get("/summary-autonomous-rev{revision}-live-stabilization")
def summary_autonomous_rev_live_stabilization(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV126_130_NAMES:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev126-130 summary revision."}
    return {"status": "ok", "user": user, "summary": build_rev126_130_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev126_130_live_stabilization(), user)}


# Rev131-135 Performance Observability Block
from core.auth import read_auth_store as read_auth_store_for_rev131_135_performance_observability
from services.autonomous_performance_observability_block_service import (
    build_block_payload as build_rev131_135_performance_observability_block,
    build_for_revision as build_rev131_135_for_revision,
    build_summary_for_revision as build_rev131_135_summary_for_revision,
)

_REV131_135_NAMES = {
    131: 'autonomous_trade_performance_metrics_engine',
    132: 'autonomous_strategy_performance_attribution',
    133: 'autonomous_execution_quality_analytics',
    134: 'autonomous_risk_adjusted_return_scoring',
    135: 'autonomous_performance_sentinel_v2',
}


@router.get("/autonomous-performance-observability-block")
def autonomous_performance_observability_block(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_performance_observability_block": build_rev131_135_performance_observability_block(load_shadow(user), load_settings(user), read_auth_store_for_rev131_135_performance_observability(), user)}


@router.get("/autonomous-rev{revision}-performance-observability")
def autonomous_rev_performance_observability(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV131_135_NAMES:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev131-135 revision."}
    key = _REV131_135_NAMES[int(revision)]
    return {"status": "ok", "user": user, key: build_rev131_135_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev131_135_performance_observability(), user)}


@router.get("/summary-autonomous-rev{revision}-performance-observability")
def summary_autonomous_rev_performance_observability(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV131_135_NAMES:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev131-135 summary revision."}
    return {"status": "ok", "user": user, "summary": build_rev131_135_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev131_135_performance_observability(), user)}

# Rev136-140 Adaptive Optimization Block
from core.auth import read_auth_store as read_auth_store_for_rev136_140_adaptive_optimization
from services.autonomous_adaptive_optimization_block_service import (
    build_block_payload as build_rev136_140_adaptive_optimization_block,
    build_for_revision as build_rev136_140_for_revision,
    build_summary_for_revision as build_rev136_140_summary_for_revision,
)

_REV136_140_NAMES = {
    136: 'autonomous_adaptive_strategy_tuning_runtime',
    137: 'autonomous_symbol_rotation_controller',
    138: 'autonomous_market_regime_adaptation_v2',
    139: 'autonomous_anti_overtrade_governor',
    140: 'autonomous_optimization_review_report',
}


@router.get("/autonomous-adaptive-optimization-block")
def autonomous_adaptive_optimization_block(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return {"status": "ok", "user": user, "autonomous_adaptive_optimization_block": build_rev136_140_adaptive_optimization_block(load_shadow(user), load_settings(user), read_auth_store_for_rev136_140_adaptive_optimization(), user)}


@router.get("/autonomous-rev{revision}-adaptive-optimization")
def autonomous_rev_adaptive_optimization(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV136_140_NAMES:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev136-140 revision."}
    key = _REV136_140_NAMES[int(revision)]
    return {"status": "ok", "user": user, key: build_rev136_140_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev136_140_adaptive_optimization(), user)}


@router.get("/summary-autonomous-rev{revision}-adaptive-optimization")
def summary_autonomous_rev_adaptive_optimization(revision: int, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    if int(revision) not in _REV136_140_NAMES:
        return {"status": "blocked", "user": user, "message": "Unsupported Rev136-140 summary revision."}
    return {"status": "ok", "user": user, "summary": build_rev136_140_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev136_140_adaptive_optimization(), user)}

# Rev141-145 Capital Scaling & Profit Defense Block
from core.auth import read_auth_store as read_auth_store_for_rev141_145_capital_defense
from services.autonomous_capital_scaling_profit_defense_block_service import (
    build_block_payload as build_rev141_145_capital_defense_block,
    build_for_revision as build_rev141_145_for_revision,
    build_summary_for_revision as build_rev141_145_summary_for_revision,
)

_REV141_145_KEYS = {
    141: 'autonomous_capital_growth_policy',
    142: 'autonomous_profit_reserve_controller',
    143: 'autonomous_drawdown_recovery_mode',
    144: 'autonomous_dynamic_position_sizing_v2',
    145: 'autonomous_capital_protection_summary',
}

@router.get("/autonomous-capital-scaling-profit-defense-block")
def autonomous_capital_scaling_profit_defense_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_capital_scaling_profit_defense_block": build_rev141_145_capital_defense_block(load_shadow(user), load_settings(user), read_auth_store_for_rev141_145_capital_defense(), user)}

@router.get("/autonomous-rev{revision}-capital-defense")
def autonomous_rev_capital_defense(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV141_145_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev141-145 capital defense revision")
    user = current_user.get("username", "default")
    key = _REV141_145_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev141_145_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev141_145_capital_defense(), user)}

@router.get("/summary-autonomous-rev{revision}-capital-defense")
def summary_autonomous_rev_capital_defense(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV141_145_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev141-145 capital defense summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev141_145_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev141_145_capital_defense(), user)}


# Rev146-150 Live Autonomy Hardening Block
from core.auth import read_auth_store as read_auth_store_for_rev146_150_live_autonomy
from services.autonomous_live_autonomy_hardening_block_service import (
    build_block_payload as build_rev146_150_live_autonomy_block,
    build_for_revision as build_rev146_150_for_revision,
    build_summary_for_revision as build_rev146_150_summary_for_revision,
)

_REV146_150_KEYS = {
    146: "autonomous_daily_session_lifecycle",
    147: "autonomous_end_of_day_evaluator",
    148: "autonomous_attention_only_alert_system",
    149: "autonomous_live_ops_regression_safety_drill",
    150: "autonomous_live_stabilized_go_no_go_v2",
}

@router.get("/autonomous-live-autonomy-hardening-block")
def autonomous_live_autonomy_hardening_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_autonomy_hardening_block": build_rev146_150_live_autonomy_block(load_shadow(user), load_settings(user), read_auth_store_for_rev146_150_live_autonomy(), user)}

@router.get("/autonomous-rev{revision}-live-autonomy-hardening")
def autonomous_rev_live_autonomy_hardening(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV146_150_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev146-150 live autonomy hardening revision")
    user = current_user.get("username", "default")
    key = _REV146_150_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev146_150_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev146_150_live_autonomy(), user)}

@router.get("/summary-autonomous-rev{revision}-live-autonomy-hardening")
def summary_autonomous_rev_live_autonomy_hardening(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV146_150_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev146-150 live autonomy hardening summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev146_150_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev146_150_live_autonomy(), user)}


# Rev151-155 Live Launch Readiness & Guarded Activation Block
from core.auth import read_auth_store as read_auth_store_for_rev151_155_live_launch
from services.autonomous_live_launch_readiness_block_service import (
    build_block_payload as build_rev151_155_live_launch_block,
    build_for_revision as build_rev151_155_for_revision,
    build_summary_for_revision as build_rev151_155_summary_for_revision,
)

_REV151_155_KEYS = {
    151: "autonomous_launch_readiness_recheck",
    152: "autonomous_guarded_activation_playbook",
    153: "autonomous_seed_capital_limits_contract",
    154: "autonomous_incident_rollback_protocol",
    155: "autonomous_live_launch_packet_v1",
}

@router.get("/autonomous-live-launch-readiness-block")
def autonomous_live_launch_readiness_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_launch_readiness_block": build_rev151_155_live_launch_block(load_shadow(user), load_settings(user), read_auth_store_for_rev151_155_live_launch(), user)}

@router.get("/autonomous-rev{revision}-live-launch-readiness")
def autonomous_rev_live_launch_readiness(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV151_155_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev151-155 live launch readiness revision")
    user = current_user.get("username", "default")
    key = _REV151_155_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev151_155_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev151_155_live_launch(), user)}

@router.get("/summary-autonomous-rev{revision}-live-launch-readiness")
def summary_autonomous_rev_live_launch_readiness(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV151_155_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev151-155 live launch readiness summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev151_155_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev151_155_live_launch(), user)}


# Rev156-160 Controlled Micro-Real Pilot Readiness Block
from core.auth import read_auth_store as read_auth_store_for_rev156_160_micro_pilot
from services.autonomous_controlled_micro_real_pilot_readiness_block_service import (
    build_block_payload as build_rev156_160_micro_pilot_block,
    build_for_revision as build_rev156_160_for_revision,
    build_summary_for_revision as build_rev156_160_summary_for_revision,
)

_REV156_160_KEYS = {
    156: "autonomous_controlled_micro_probe_eligibility_gate",
    157: "autonomous_live_dry_run_shadow_execution_monitor",
    158: "autonomous_exchange_readiness_permission_drift_detector",
    159: "autonomous_pilot_risk_envelope_enforcer",
    160: "autonomous_micro_real_pilot_decision_packet",
}

@router.get("/autonomous-controlled-micro-real-pilot-readiness-block")
def autonomous_controlled_micro_real_pilot_readiness_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_controlled_micro_real_pilot_readiness_block": build_rev156_160_micro_pilot_block(load_shadow(user), load_settings(user), read_auth_store_for_rev156_160_micro_pilot(), user)}

@router.get("/autonomous-rev{revision}-controlled-micro-real-pilot")
def autonomous_rev_controlled_micro_real_pilot(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV156_160_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev156-160 controlled micro-real pilot revision")
    user = current_user.get("username", "default")
    key = _REV156_160_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev156_160_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev156_160_micro_pilot(), user)}

@router.get("/summary-autonomous-rev{revision}-controlled-micro-real-pilot")
def summary_autonomous_rev_controlled_micro_real_pilot(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV156_160_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev156-160 controlled micro-real pilot summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev156_160_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev156_160_micro_pilot(), user)}


# Rev161-165 Micro-Real Pilot Control & Evidence Loop Block
from core.auth import read_auth_store as read_auth_store_for_rev161_165_micro_pilot_control
from services.autonomous_micro_real_pilot_control_evidence_loop_service import (
    build_block_payload as build_rev161_165_micro_pilot_control_block,
    build_for_revision as build_rev161_165_for_revision,
    build_summary_for_revision as build_rev161_165_summary_for_revision,
)

_REV161_165_KEYS = {
    161: "autonomous_micro_probe_preview_contract",
    162: "autonomous_micro_probe_evidence_recorder",
    163: "autonomous_micro_probe_outcome_reconciler",
    164: "autonomous_micro_probe_auto_halt_demotion_gate",
    165: "autonomous_micro_pilot_feedback_decision_packet",
}

@router.get("/autonomous-micro-real-pilot-control-evidence-loop-block")
def autonomous_micro_real_pilot_control_evidence_loop_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_micro_real_pilot_control_evidence_loop_block": build_rev161_165_micro_pilot_control_block(load_shadow(user), load_settings(user), read_auth_store_for_rev161_165_micro_pilot_control(), user)}

@router.get("/autonomous-rev{revision}-micro-pilot-control")
def autonomous_rev_micro_pilot_control(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV161_165_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev161-165 micro pilot control revision")
    user = current_user.get("username", "default")
    key = _REV161_165_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev161_165_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev161_165_micro_pilot_control(), user)}

@router.get("/summary-autonomous-rev{revision}-micro-pilot-control")
def summary_autonomous_rev_micro_pilot_control(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV161_165_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev161-165 micro pilot control summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev161_165_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev161_165_micro_pilot_control(), user)}


# Rev166-170 Micro-Real Pilot Stabilization Block
from core.auth import read_auth_store as read_auth_store_for_rev166_170_micro_pilot_stabilization
from services.autonomous_micro_real_pilot_stabilization_block_service import (
    build_block_payload as build_rev166_170_micro_pilot_stabilization_block,
    build_for_revision as build_rev166_170_for_revision,
    build_summary_for_revision as build_rev166_170_summary_for_revision,
)

_REV166_170_KEYS = {
    166: "autonomous_micro_pilot_evidence_confidence_scorer",
    167: "autonomous_controlled_repeat_probe_gate",
    168: "autonomous_micro_real_scale_freeze_controller",
    169: "autonomous_pilot_drift_anomaly_watch",
    170: "autonomous_micro_pilot_stabilization_decision_v2",
}

@router.get("/autonomous-micro-real-pilot-stabilization-block")
def autonomous_micro_real_pilot_stabilization_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_micro_real_pilot_stabilization_block": build_rev166_170_micro_pilot_stabilization_block(load_shadow(user), load_settings(user), read_auth_store_for_rev166_170_micro_pilot_stabilization(), user)}

@router.get("/autonomous-rev{revision}-micro-pilot-stabilization")
def autonomous_rev_micro_pilot_stabilization(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV166_170_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev166-170 micro pilot stabilization revision")
    user = current_user.get("username", "default")
    key = _REV166_170_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev166_170_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev166_170_micro_pilot_stabilization(), user)}

@router.get("/summary-autonomous-rev{revision}-micro-pilot-stabilization")
def summary_autonomous_rev_micro_pilot_stabilization(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV166_170_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev166-170 micro pilot stabilization summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev166_170_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev166_170_micro_pilot_stabilization(), user)}

# Rev171-175 Live Edge Profitability Proof Block
from core.auth import read_auth_store as read_auth_store_for_rev171_175_live_edge_profitability_proof
from services.autonomous_live_edge_profitability_proof_block_service import (
    build_block_payload as build_rev171_175_live_edge_profitability_proof_block,
    build_for_revision as build_rev171_175_for_revision,
    build_summary_for_revision as build_rev171_175_summary_for_revision,
)

_REV171_175_KEYS = {
    171: "autonomous_post_pilot_edge_validation_gate",
    172: "autonomous_fee_slippage_break_even_controller",
    173: "autonomous_strategy_symbol_micro_allocation_matrix",
    174: "autonomous_learning_lock_regression_watch",
    175: "autonomous_profitability_proof_decision_packet",
}

@router.get("/autonomous-live-edge-profitability-proof-block")
def autonomous_live_edge_profitability_proof_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_edge_profitability_proof_block": build_rev171_175_live_edge_profitability_proof_block(load_shadow(user), load_settings(user), read_auth_store_for_rev171_175_live_edge_profitability_proof(), user)}

@router.get("/autonomous-rev{revision}-live-edge-profitability-proof")
def autonomous_rev_live_edge_profitability_proof(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV171_175_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev171-175 live edge profitability proof revision")
    user = current_user.get("username", "default")
    key = _REV171_175_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev171_175_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev171_175_live_edge_profitability_proof(), user)}

@router.get("/summary-autonomous-rev{revision}-live-edge-profitability-proof")
def summary_autonomous_rev_live_edge_profitability_proof(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV171_175_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev171-175 live edge profitability proof summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev171_175_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev171_175_live_edge_profitability_proof(), user)}

# Rev176-180 Proof-to-Limited-Live Control Block
from core.auth import read_auth_store as read_auth_store_for_rev176_180_proof_to_limited_live_control
from services.autonomous_proof_to_limited_live_control_block_service import (
    build_block_payload as build_rev176_180_proof_to_limited_live_control_block,
    build_for_revision as build_rev176_180_for_revision,
    build_summary_for_revision as build_rev176_180_summary_for_revision,
)

_REV176_180_KEYS = {
    176: "autonomous_limited_live_eligibility_recheck",
    177: "autonomous_activation_token_preview_owner_gate",
    178: "autonomous_micro_live_session_boundary_controller",
    179: "autonomous_real_time_loss_profit_tripwire",
    180: "autonomous_limited_live_control_decision_packet",
}

@router.get("/autonomous-proof-to-limited-live-control-block")
def autonomous_proof_to_limited_live_control_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_proof_to_limited_live_control_block": build_rev176_180_proof_to_limited_live_control_block(load_shadow(user), load_settings(user), read_auth_store_for_rev176_180_proof_to_limited_live_control(), user)}

@router.get("/autonomous-rev{revision}-proof-to-limited-live-control")
def autonomous_rev_proof_to_limited_live_control(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV176_180_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev176-180 proof-to-limited-live control revision")
    user = current_user.get("username", "default")
    key = _REV176_180_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev176_180_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev176_180_proof_to_limited_live_control(), user)}

@router.get("/summary-autonomous-rev{revision}-proof-to-limited-live-control")
def summary_autonomous_rev_proof_to_limited_live_control(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV176_180_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev176-180 proof-to-limited-live control summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev176_180_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev176_180_proof_to_limited_live_control(), user)}

# Rev181-185 Limited Live Activation Rehearsal Block
from core.auth import read_auth_store as read_auth_store_for_rev181_185_limited_live_activation_rehearsal
from services.autonomous_limited_live_activation_rehearsal_block_service import (
    build_block_payload as build_rev181_185_limited_live_activation_rehearsal_block,
    build_for_revision as build_rev181_185_for_revision,
    build_summary_for_revision as build_rev181_185_summary_for_revision,
)

_REV181_185_KEYS = {
    181: "autonomous_activation_preflight_matrix",
    182: "autonomous_limited_live_rehearsal_runner",
    183: "autonomous_activation_failure_reason_normalizer",
    184: "autonomous_owner_approval_audit_contract",
    185: "autonomous_limited_live_activation_rehearsal_report",
}

@router.get("/autonomous-limited-live-activation-rehearsal-block")
def autonomous_limited_live_activation_rehearsal_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_limited_live_activation_rehearsal_block": build_rev181_185_limited_live_activation_rehearsal_block(load_shadow(user), load_settings(user), read_auth_store_for_rev181_185_limited_live_activation_rehearsal(), user)}

@router.get("/autonomous-rev{revision}-limited-live-activation-rehearsal")
def autonomous_rev_limited_live_activation_rehearsal(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV181_185_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev181-185 limited live activation rehearsal revision")
    user = current_user.get("username", "default")
    key = _REV181_185_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev181_185_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev181_185_limited_live_activation_rehearsal(), user)}

@router.get("/summary-autonomous-rev{revision}-limited-live-activation-rehearsal")
def summary_autonomous_rev_limited_live_activation_rehearsal(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV181_185_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev181-185 limited live activation rehearsal summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev181_185_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev181_185_limited_live_activation_rehearsal(), user)}


# Rev186-190 Real Execution Reconciliation Block
from core.auth import read_auth_store as read_auth_store_for_rev186_190_real_execution_reconciliation
from services.autonomous_real_execution_reconciliation_block_service import (
    build_block_payload as build_rev186_190_real_execution_reconciliation_block,
    build_for_revision as build_rev186_190_for_revision,
    build_summary_for_revision as build_rev186_190_summary_for_revision,
)

_REV186_190_KEYS = {
    186: "autonomous_exchange_order_state_canonicalizer",
    187: "autonomous_position_journal_order_reconciliation_v2",
    188: "autonomous_partial_fill_residual_risk_handler",
    189: "autonomous_duplicate_stale_order_protection",
    190: "autonomous_execution_reconciliation_report",
}

@router.get("/autonomous-real-execution-reconciliation-block")
def autonomous_real_execution_reconciliation_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_real_execution_reconciliation_block": build_rev186_190_real_execution_reconciliation_block(load_shadow(user), load_settings(user), read_auth_store_for_rev186_190_real_execution_reconciliation(), user)}

@router.get("/autonomous-rev{revision}-real-execution-reconciliation")
def autonomous_rev_real_execution_reconciliation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV186_190_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev186-190 real execution reconciliation revision")
    user = current_user.get("username", "default")
    key = _REV186_190_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev186_190_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev186_190_real_execution_reconciliation(), user)}

@router.get("/summary-autonomous-rev{revision}-real-execution-reconciliation")
def summary_autonomous_rev_real_execution_reconciliation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV186_190_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev186-190 real execution reconciliation summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev186_190_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev186_190_real_execution_reconciliation(), user)}

# Rev191-195 Live Risk Firewall Block
from core.auth import read_auth_store as read_auth_store_for_rev191_195_live_risk_firewall
from services.autonomous_live_risk_firewall_block_service import (
    build_block_payload as build_rev191_195_live_risk_firewall_block,
    build_for_revision as build_rev191_195_for_revision,
    build_summary_for_revision as build_rev191_195_summary_for_revision,
)

_REV191_195_KEYS = {
    191: "autonomous_multi_layer_risk_firewall",
    192: "autonomous_real_time_exposure_guard",
    193: "autonomous_profit_lock_enforcement_preview",
    194: "autonomous_loss_escalation_ladder",
    195: "autonomous_live_risk_firewall_decision_packet",
}

@router.get("/autonomous-live-risk-firewall-block")
def autonomous_live_risk_firewall_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_risk_firewall_block": build_rev191_195_live_risk_firewall_block(load_shadow(user), load_settings(user), read_auth_store_for_rev191_195_live_risk_firewall(), user)}

@router.get("/autonomous-rev{revision}-live-risk-firewall")
def autonomous_rev_live_risk_firewall(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV191_195_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev191-195 live risk firewall revision")
    user = current_user.get("username", "default")
    key = _REV191_195_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev191_195_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev191_195_live_risk_firewall(), user)}

@router.get("/summary-autonomous-rev{revision}-live-risk-firewall")
def summary_autonomous_rev_live_risk_firewall(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV191_195_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev191-195 live risk firewall summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev191_195_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev191_195_live_risk_firewall(), user)}


# Rev196-200 First Controlled Micro Live Block
from core.auth import read_auth_store as read_auth_store_for_rev196_200_first_controlled_micro_live
from services.autonomous_first_controlled_micro_live_block_service import (
    build_block_payload as build_rev196_200_first_controlled_micro_live_block,
    build_for_revision as build_rev196_200_for_revision,
    build_summary_for_revision as build_rev196_200_summary_for_revision,
)

_REV196_200_KEYS = {
    196: "autonomous_first_micro_live_intent_contract",
    197: "autonomous_approval_gated_submit_path_hardening",
    198: "autonomous_micro_live_exit_plan_contract",
    199: "autonomous_micro_live_result_capture",
    200: "autonomous_first_controlled_micro_live_go_no_go",
}

@router.get("/autonomous-first-controlled-micro-live-block")
def autonomous_first_controlled_micro_live_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_first_controlled_micro_live_block": build_rev196_200_first_controlled_micro_live_block(load_shadow(user), load_settings(user), read_auth_store_for_rev196_200_first_controlled_micro_live(), user)}

@router.get("/autonomous-rev{revision}-first-controlled-micro-live")
def autonomous_rev_first_controlled_micro_live(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV196_200_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev196-200 first controlled micro live revision")
    user = current_user.get("username", "default")
    key = _REV196_200_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev196_200_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev196_200_first_controlled_micro_live(), user)}

@router.get("/summary-autonomous-rev{revision}-first-controlled-micro-live")
def summary_autonomous_rev_first_controlled_micro_live(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV196_200_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev196-200 first controlled micro live summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev196_200_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev196_200_first_controlled_micro_live(), user)}


# Rev201-205 Post First Trade Learning & Freeze Block
from core.auth import read_auth_store as read_auth_store_for_rev201_205_post_first_trade_learning_freeze
from services.autonomous_post_first_trade_learning_freeze_block_service import (
    build_block_payload as build_rev201_205_post_first_trade_learning_freeze_block,
    build_for_revision as build_rev201_205_for_revision,
    build_summary_for_revision as build_rev201_205_summary_for_revision,
)

_REV201_205_KEYS = {
    201: "autonomous_first_trade_evidence_quality_scorer",
    202: "autonomous_post_trade_freeze_gate",
    203: "autonomous_strategy_reality_check",
    204: "autonomous_live_cost_reality_calibration",
    205: "autonomous_post_first_trade_decision_packet",
}

@router.get("/autonomous-post-first-trade-learning-freeze-block")
def autonomous_post_first_trade_learning_freeze_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_post_first_trade_learning_freeze_block": build_rev201_205_post_first_trade_learning_freeze_block(load_shadow(user), load_settings(user), read_auth_store_for_rev201_205_post_first_trade_learning_freeze(), user)}

@router.get("/autonomous-rev{revision}-post-first-trade-learning-freeze")
def autonomous_rev_post_first_trade_learning_freeze(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV201_205_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev201-205 post first trade learning freeze revision")
    user = current_user.get("username", "default")
    key = _REV201_205_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev201_205_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev201_205_post_first_trade_learning_freeze(), user)}

@router.get("/summary-autonomous-rev{revision}-post-first-trade-learning-freeze")
def summary_autonomous_rev_post_first_trade_learning_freeze(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV201_205_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev201-205 post first trade learning freeze summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev201_205_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev201_205_post_first_trade_learning_freeze(), user)}

# Rev206-210 Controlled Repeat Micro Live Block
from core.auth import read_auth_store as read_auth_store_for_rev206_210_controlled_repeat_micro_live
from services.autonomous_controlled_repeat_micro_live_block_service import (
    build_block_payload as build_rev206_210_controlled_repeat_micro_live_block,
    build_for_revision as build_rev206_210_for_revision,
    build_summary_for_revision as build_rev206_210_summary_for_revision,
)

_REV206_210_KEYS = {
    206: "autonomous_repeat_trade_eligibility_gate",
    207: "autonomous_micro_live_sample_size_controller",
    208: "autonomous_controlled_trade_frequency_governor",
    209: "autonomous_repeat_micro_live_decision_engine",
    210: "autonomous_repeat_micro_live_report",
}

@router.get("/autonomous-controlled-repeat-micro-live-block")
def autonomous_controlled_repeat_micro_live_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_controlled_repeat_micro_live_block": build_rev206_210_controlled_repeat_micro_live_block(load_shadow(user), load_settings(user), read_auth_store_for_rev206_210_controlled_repeat_micro_live(), user)}

@router.get("/autonomous-rev{revision}-controlled-repeat-micro-live")
def autonomous_rev_controlled_repeat_micro_live(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV206_210_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev206-210 controlled repeat micro live revision")
    user = current_user.get("username", "default")
    key = _REV206_210_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev206_210_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev206_210_controlled_repeat_micro_live(), user)}

@router.get("/summary-autonomous-rev{revision}-controlled-repeat-micro-live")
def summary_autonomous_rev_controlled_repeat_micro_live(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV206_210_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev206-210 controlled repeat micro live summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev206_210_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev206_210_controlled_repeat_micro_live(), user)}

# Rev211-215 Small Capital Autonomy Preparation Block
from core.auth import read_auth_store as read_auth_store_for_rev211_215_small_capital_autonomy_preparation
from services.autonomous_small_capital_autonomy_preparation_block_service import (
    build_block_payload as build_rev211_215_small_capital_autonomy_preparation_block,
    build_for_revision as build_rev211_215_for_revision,
    build_summary_for_revision as build_rev211_215_summary_for_revision,
)

_REV211_215_KEYS = {
    211: "autonomous_small_capital_autonomy_envelope",
    212: "autonomous_autonomy_permission_ladder",
    213: "autonomous_halt_authority",
    214: "autonomous_minimal_operator_summary_v3",
    215: "autonomous_small_capital_autonomy_readiness_packet",
}

@router.get("/autonomous-small-capital-autonomy-preparation-block")
def autonomous_small_capital_autonomy_preparation_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_small_capital_autonomy_preparation_block": build_rev211_215_small_capital_autonomy_preparation_block(load_shadow(user), load_settings(user), read_auth_store_for_rev211_215_small_capital_autonomy_preparation(), user)}

@router.get("/autonomous-rev{revision}-small-capital-autonomy-preparation")
def autonomous_rev_small_capital_autonomy_preparation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV211_215_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev211-215 small capital autonomy preparation revision")
    user = current_user.get("username", "default")
    key = _REV211_215_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev211_215_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev211_215_small_capital_autonomy_preparation(), user)}

@router.get("/summary-autonomous-rev{revision}-small-capital-autonomy-preparation")
def summary_autonomous_rev_small_capital_autonomy_preparation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV211_215_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev211-215 small capital autonomy preparation summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev211_215_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev211_215_small_capital_autonomy_preparation(), user)}

# Rev216-220 Production Self-Governance Block
from core.auth import read_auth_store as read_auth_store_for_rev216_220_production_self_governance
from services.autonomous_production_self_governance_block_service import (
    build_block_payload as build_rev216_220_production_self_governance_block,
    build_for_revision as build_rev216_220_for_revision,
    build_summary_for_revision as build_rev216_220_summary_for_revision,
)

_REV216_220_KEYS = {
    216: "autonomous_production_self_governance_charter",
    217: "autonomous_governance_audit_trail_preview",
    218: "autonomous_rollback_freeze_runbook",
    219: "autonomous_operator_safe_action_router",
    220: "autonomous_production_self_governance_decision_packet",
}

@router.get("/autonomous-production-self-governance-block")
def autonomous_production_self_governance_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_production_self_governance_block": build_rev216_220_production_self_governance_block(load_shadow(user), load_settings(user), read_auth_store_for_rev216_220_production_self_governance(), user)}

@router.get("/autonomous-rev{revision}-production-self-governance")
def autonomous_rev_production_self_governance(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV216_220_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev216-220 production self-governance revision")
    user = current_user.get("username", "default")
    key = _REV216_220_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev216_220_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev216_220_production_self_governance(), user)}

@router.get("/summary-autonomous-rev{revision}-production-self-governance")
def summary_autonomous_rev_production_self_governance(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV216_220_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev216-220 production self-governance summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev216_220_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev216_220_production_self_governance(), user)}

# Rev221-225 Production Observability & Incident Drill Block
from core.auth import read_auth_store as read_auth_store_for_rev221_225_production_observability_incident_drill
from services.autonomous_production_observability_incident_drill_block_service import (
    build_block_payload as build_rev221_225_production_observability_incident_drill_block,
    build_for_revision as build_rev221_225_for_revision,
    build_summary_for_revision as build_rev221_225_summary_for_revision,
)

_REV221_225_KEYS = {
    221: "autonomous_production_telemetry_heartbeat",
    222: "autonomous_decision_trace_validator",
    223: "autonomous_incident_drill_simulator",
    224: "autonomous_operator_notification_compactor",
    225: "autonomous_production_observability_decision_packet",
}

@router.get("/autonomous-production-observability-incident-drill-block")
def autonomous_production_observability_incident_drill_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_production_observability_incident_drill_block": build_rev221_225_production_observability_incident_drill_block(load_shadow(user), load_settings(user), read_auth_store_for_rev221_225_production_observability_incident_drill(), user)}

@router.get("/autonomous-rev{revision}-production-observability-incident-drill")
def autonomous_rev_production_observability_incident_drill(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV221_225_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev221-225 production observability incident drill revision")
    user = current_user.get("username", "default")
    key = _REV221_225_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev221_225_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev221_225_production_observability_incident_drill(), user)}

@router.get("/summary-autonomous-rev{revision}-production-observability-incident-drill")
def summary_autonomous_rev_production_observability_incident_drill(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV221_225_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev221-225 production observability incident drill summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev221_225_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev221_225_production_observability_incident_drill(), user)}

# Rev226-230 Production Data Integrity Block
from core.auth import read_auth_store as read_auth_store_for_rev226_230_production_data_integrity
from services.autonomous_production_data_integrity_block_service import (
    build_block_payload as build_rev226_230_production_data_integrity_block,
    build_for_revision as build_rev226_230_for_revision,
    build_summary_for_revision as build_rev226_230_summary_for_revision,
)

_REV226_230_KEYS = {
    226: "autonomous_runtime_data_freshness_validator",
    227: "autonomous_journal_consistency_checksum",
    228: "autonomous_learning_memory_integrity_guard",
    229: "autonomous_decision_packet_schema_validator",
    230: "autonomous_production_data_integrity_report",
}

@router.get("/autonomous-production-data-integrity-block")
def autonomous_production_data_integrity_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_production_data_integrity_block": build_rev226_230_production_data_integrity_block(load_shadow(user), load_settings(user), read_auth_store_for_rev226_230_production_data_integrity(), user)}

@router.get("/autonomous-rev{revision}-production-data-integrity")
def autonomous_rev_production_data_integrity(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV226_230_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev226-230 production data integrity revision")
    user = current_user.get("username", "default")
    key = _REV226_230_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev226_230_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev226_230_production_data_integrity(), user)}

@router.get("/summary-autonomous-rev{revision}-production-data-integrity")
def summary_autonomous_rev_production_data_integrity(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV226_230_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev226-230 production data integrity summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev226_230_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev226_230_production_data_integrity(), user)}

# Rev231-235 Live Strategy Reality Validation Block
from core.auth import read_auth_store as read_auth_store_for_rev231_235_live_strategy_reality
from services.autonomous_live_strategy_reality_validation_block_service import (
    build_block_payload as build_rev231_235_live_strategy_reality_block,
    build_for_revision as build_rev231_235_for_revision,
    build_summary_for_revision as build_rev231_235_summary_for_revision,
)

_REV231_235_KEYS = {
    231: "autonomous_paper_vs_micro_live_expectancy_comparator",
    232: "autonomous_strategy_live_degradation_detector",
    233: "autonomous_symbol_strategy_pair_confidence_scorer",
    234: "autonomous_weak_strategy_quarantine_controller",
    235: "autonomous_live_strategy_reality_report",
}

@router.get("/autonomous-live-strategy-reality-validation-block")
def autonomous_live_strategy_reality_validation_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_strategy_reality_validation_block": build_rev231_235_live_strategy_reality_block(load_shadow(user), load_settings(user), read_auth_store_for_rev231_235_live_strategy_reality(), user)}

@router.get("/autonomous-rev{revision}-live-strategy-reality-validation")
def autonomous_rev_live_strategy_reality_validation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV231_235_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev231-235 live strategy reality validation revision")
    user = current_user.get("username", "default")
    key = _REV231_235_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev231_235_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev231_235_live_strategy_reality(), user)}

@router.get("/summary-autonomous-rev{revision}-live-strategy-reality-validation")
def summary_autonomous_rev_live_strategy_reality_validation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV231_235_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev231-235 live strategy reality validation summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev231_235_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev231_235_live_strategy_reality(), user)}

# Rev236-240 Capital Preservation & USDT Dominance Block
from core.auth import read_auth_store as read_auth_store_for_rev236_240_capital_preservation
from services.autonomous_capital_preservation_usdt_dominance_block_service import (
    build_block_payload as build_rev236_240_capital_preservation_block,
    build_for_revision as build_rev236_240_for_revision,
    build_summary_for_revision as build_rev236_240_summary_for_revision,
)

_REV236_240_KEYS = {
    236: "autonomous_usdt_reserve_dominance_policy",
    237: "autonomous_active_capital_exposure_limiter",
    238: "autonomous_profit_reserve_lock_v2",
    239: "autonomous_drawdown_capital_shrink_controller",
    240: "autonomous_capital_preservation_decision_packet",
}

@router.get("/autonomous-capital-preservation-usdt-dominance-block")
def autonomous_capital_preservation_usdt_dominance_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_capital_preservation_usdt_dominance_block": build_rev236_240_capital_preservation_block(load_shadow(user), load_settings(user), read_auth_store_for_rev236_240_capital_preservation(), user)}

@router.get("/autonomous-rev{revision}-capital-preservation-usdt-dominance")
def autonomous_rev_capital_preservation_usdt_dominance(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV236_240_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev236-240 capital preservation revision")
    user = current_user.get("username", "default")
    key = _REV236_240_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev236_240_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev236_240_capital_preservation(), user)}

@router.get("/summary-autonomous-rev{revision}-capital-preservation-usdt-dominance")
def summary_autonomous_rev_capital_preservation_usdt_dominance(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV236_240_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev236-240 capital preservation summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev236_240_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev236_240_capital_preservation(), user)}

# Rev241-245 Autonomous Opportunity Quality Block
from core.auth import read_auth_store as read_auth_store_for_rev241_245_opportunity_quality
from services.autonomous_opportunity_quality_block_service import (
    build_block_payload as build_rev241_245_opportunity_quality_block,
    build_for_revision as build_rev241_245_for_revision,
    build_summary_for_revision as build_rev241_245_summary_for_revision,
)

_REV241_245_KEYS = {
    241: "autonomous_opportunity_quality_score_v2",
    242: "autonomous_choch_imbalance_reliability_filter",
    243: "autonomous_low_quality_signal_suppressor",
    244: "autonomous_opportunity_queue_prioritizer",
    245: "autonomous_opportunity_quality_report",
}

@router.get("/autonomous-opportunity-quality-block")
def autonomous_opportunity_quality_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_opportunity_quality_block": build_rev241_245_opportunity_quality_block(load_shadow(user), load_settings(user), read_auth_store_for_rev241_245_opportunity_quality(), user)}

@router.get("/autonomous-rev{revision}-opportunity-quality")
def autonomous_rev_opportunity_quality(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV241_245_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev241-245 opportunity quality revision")
    user = current_user.get("username", "default")
    key = _REV241_245_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev241_245_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev241_245_opportunity_quality(), user)}

@router.get("/summary-autonomous-rev{revision}-opportunity-quality")
def summary_autonomous_rev_opportunity_quality(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV241_245_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev241-245 opportunity quality summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev241_245_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev241_245_opportunity_quality(), user)}

# Rev246-250 Limited-Live Operator Approval UX Block
from core.auth import read_auth_store as read_auth_store_for_rev246_250_operator_ux
from services.autonomous_limited_live_operator_approval_ux_block_service import (
    build_block_payload as build_rev246_250_operator_ux_block,
    build_for_revision as build_rev246_250_for_revision,
    build_summary_for_revision as build_rev246_250_summary_for_revision,
)

_REV246_250_KEYS = {
    246: "owner_approval_status_card",
    247: "activation_blocker_compact_view",
    248: "session_approval_preview_panel",
    249: "emergency_halt_reduce_visual_state",
    250: "limited_live_operator_ux_packet",
}

@router.get("/autonomous-limited-live-operator-approval-ux-block")
def autonomous_limited_live_operator_approval_ux_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_limited_live_operator_approval_ux_block": build_rev246_250_operator_ux_block(load_shadow(user), load_settings(user), read_auth_store_for_rev246_250_operator_ux(), user)}

@router.get("/autonomous-rev{revision}-limited-live-operator-approval-ux")
def autonomous_rev_limited_live_operator_approval_ux(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV246_250_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev246-250 limited-live operator UX revision")
    user = current_user.get("username", "default")
    key = _REV246_250_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev246_250_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev246_250_operator_ux(), user)}

@router.get("/summary-autonomous-rev{revision}-limited-live-operator-approval-ux")
def summary_autonomous_rev_limited_live_operator_approval_ux(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV246_250_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev246-250 limited-live operator UX summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev246_250_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev246_250_operator_ux(), user)}

# Rev251-255 Micro-Live Execution Dry Proof Block
from core.auth import read_auth_store as read_auth_store_for_rev251_255_execution_dry_proof
from services.autonomous_micro_live_execution_dry_proof_block_service import (
    build_block_payload as build_rev251_255_execution_dry_proof_block,
    build_for_revision as build_rev251_255_for_revision,
    build_summary_for_revision as build_rev251_255_summary_for_revision,
)

_REV251_255_KEYS = {
    251: "submit_path_dry_proof",
    252: "exit_path_dry_proof",
    253: "exchange_response_fixture_validator",
    254: "reconciliation_dry_proof_runner",
    255: "micro_live_execution_dry_proof_report",
}

@router.get("/autonomous-micro-live-execution-dry-proof-block")
def autonomous_micro_live_execution_dry_proof_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_micro_live_execution_dry_proof_block": build_rev251_255_execution_dry_proof_block(load_shadow(user), load_settings(user), read_auth_store_for_rev251_255_execution_dry_proof(), user)}

@router.get("/autonomous-rev{revision}-micro-live-execution-dry-proof")
def autonomous_rev_micro_live_execution_dry_proof(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV251_255_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev251-255 micro-live execution dry proof revision")
    user = current_user.get("username", "default")
    key = _REV251_255_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev251_255_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev251_255_execution_dry_proof(), user)}

@router.get("/summary-autonomous-rev{revision}-micro-live-execution-dry-proof")
def summary_autonomous_rev_micro_live_execution_dry_proof(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV251_255_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev251-255 micro-live execution dry proof summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev251_255_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev251_255_execution_dry_proof(), user)}

# Rev256-260 Small Capital Live Readiness Gate v2 Block
from core.auth import read_auth_store as read_auth_store_for_rev256_260_small_cap_live_readiness
from services.autonomous_small_capital_live_readiness_gate_v2_block_service import (
    build_block_payload as build_rev256_260_small_cap_live_readiness_block,
    build_for_revision as build_rev256_260_for_revision,
    build_summary_for_revision as build_rev256_260_summary_for_revision,
)

_REV256_260_KEYS = {
    256: "small_capital_readiness_recheck",
    257: "max_loss_max_notional_contract_v2",
    258: "daily_hard_stop_enforcement_proof",
    259: "live_permission_whitelist_final_gate",
    260: "small_capital_live_readiness_decision",
}

@router.get("/autonomous-small-capital-live-readiness-gate-v2-block")
def autonomous_small_capital_live_readiness_gate_v2_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_small_capital_live_readiness_gate_v2_block": build_rev256_260_small_cap_live_readiness_block(load_shadow(user), load_settings(user), read_auth_store_for_rev256_260_small_cap_live_readiness(), user)}

@router.get("/autonomous-rev{revision}-small-capital-live-readiness-gate-v2")
def autonomous_rev_small_capital_live_readiness_gate_v2(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV256_260_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev256-260 small-capital live readiness revision")
    user = current_user.get("username", "default")
    key = _REV256_260_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev256_260_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev256_260_small_cap_live_readiness(), user)}

@router.get("/summary-autonomous-rev{revision}-small-capital-live-readiness-gate-v2")
def summary_autonomous_rev_small_capital_live_readiness_gate_v2(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV256_260_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev256-260 small-capital live readiness summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev256_260_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev256_260_small_cap_live_readiness(), user)}

# Rev261-265 Production Limited-Live Candidate Packet Block
from core.auth import read_auth_store as read_auth_store_for_rev261_265_production_limited_live_candidate
from services.autonomous_production_limited_live_candidate_block_service import (
    build_block_payload as build_rev261_265_production_limited_live_candidate_block,
    build_for_revision as build_rev261_265_for_revision,
    build_summary_for_revision as build_rev261_265_summary_for_revision,
)

_REV261_265_KEYS = {
    261: "production_limited_live_checklist",
    262: "live_activation_contract_finalizer",
    263: "rollback_emergency_protocol_final_check",
    264: "deployment_safe_package_audit",
    265: "production_limited_live_candidate_packet",
}

@router.get("/autonomous-production-limited-live-candidate-block")
def autonomous_production_limited_live_candidate_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_production_limited_live_candidate_block": build_rev261_265_production_limited_live_candidate_block(load_shadow(user), load_settings(user), read_auth_store_for_rev261_265_production_limited_live_candidate(), user)}

@router.get("/autonomous-rev{revision}-production-limited-live-candidate")
def autonomous_rev_production_limited_live_candidate(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV261_265_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev261-265 production limited-live candidate revision")
    user = current_user.get("username", "default")
    key = _REV261_265_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev261_265_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev261_265_production_limited_live_candidate(), user)}

@router.get("/summary-autonomous-rev{revision}-production-limited-live-candidate")
def summary_autonomous_rev_production_limited_live_candidate(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV261_265_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev261-265 production limited-live candidate summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev261_265_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev261_265_production_limited_live_candidate(), user)}


# Rev266-270 Limited-Live Final Validation Block
from core.auth import read_auth_store as read_auth_store_for_rev266_270_limited_live_final_validation
from services.autonomous_limited_live_final_validation_block_service import (
    build_block_payload as build_rev266_270_limited_live_final_validation_block,
    build_for_revision as build_rev266_270_for_revision,
    build_summary_for_revision as build_rev266_270_summary_for_revision,
)

_REV266_270_KEYS = {
    266: "limited_live_candidate_consistency_recheck",
    267: "runtime_safety_state_final_validator",
    268: "risk_firewall_capital_preservation_combined_gate",
    269: "data_integrity_strategy_reality_combined_validator",
    270: "limited_live_final_validation_report",
}

@router.get("/autonomous-limited-live-final-validation-block")
def autonomous_limited_live_final_validation_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_limited_live_final_validation_block": build_rev266_270_limited_live_final_validation_block(load_shadow(user), load_settings(user), read_auth_store_for_rev266_270_limited_live_final_validation(), user)}

@router.get("/autonomous-rev{revision}-limited-live-final-validation")
def autonomous_rev_limited_live_final_validation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV266_270_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev266-270 limited-live final validation revision")
    user = current_user.get("username", "default")
    key = _REV266_270_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev266_270_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev266_270_limited_live_final_validation(), user)}

@router.get("/summary-autonomous-rev{revision}-limited-live-final-validation")
def summary_autonomous_rev_limited_live_final_validation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV266_270_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev266-270 limited-live final validation summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev266_270_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev266_270_limited_live_final_validation(), user)}


# Rev271-275 Owner-Controlled Activation Layer Block
from core.auth import read_auth_store as read_auth_store_for_rev271_275_owner_controlled_activation
from services.autonomous_owner_controlled_activation_layer_block_service import (
    build_block_payload as build_rev271_275_owner_controlled_activation_block,
    build_for_revision as build_rev271_275_for_revision,
    build_summary_for_revision as build_rev271_275_summary_for_revision,
)

_REV271_275_KEYS = {
    271: "owner_approval_scope_validator",
    272: "activation_token_lifecycle_preview",
    273: "session_bound_permission_contract",
    274: "approval_misuse_stale_token_guard",
    275: "owner_controlled_activation_decision_packet",
}

@router.get("/autonomous-owner-controlled-activation-layer-block")
def autonomous_owner_controlled_activation_layer_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_owner_controlled_activation_layer_block": build_rev271_275_owner_controlled_activation_block(load_shadow(user), load_settings(user), read_auth_store_for_rev271_275_owner_controlled_activation(), user)}

@router.get("/autonomous-rev{revision}-owner-controlled-activation")
def autonomous_rev_owner_controlled_activation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV271_275_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev271-275 owner-controlled activation revision")
    user = current_user.get("username", "default")
    key = _REV271_275_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev271_275_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev271_275_owner_controlled_activation(), user)}

@router.get("/summary-autonomous-rev{revision}-owner-controlled-activation")
def summary_autonomous_rev_owner_controlled_activation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV271_275_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev271-275 owner-controlled activation summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev271_275_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev271_275_owner_controlled_activation(), user)}

# Rev276-280 Micro-Live Execution Guardrail Block
from core.auth import read_auth_store as read_auth_store_for_rev276_280_micro_live_execution_guardrail
from services.autonomous_micro_live_execution_guardrail_block_service import (
    build_block_payload as build_rev276_280_micro_live_execution_guardrail_block,
    build_for_revision as build_rev276_280_for_revision,
    build_summary_for_revision as build_rev276_280_summary_for_revision,
)

_REV276_280_KEYS = {
    276: "submit_guardrail_finalizer",
    277: "close_emergency_close_guardrail_finalizer",
    278: "client_order_id_idempotency_hardening",
    279: "exchange_permission_drift_final_guard",
    280: "micro_live_execution_guardrail_report",
}

@router.get("/autonomous-micro-live-execution-guardrail-block")
def autonomous_micro_live_execution_guardrail_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_micro_live_execution_guardrail_block": build_rev276_280_micro_live_execution_guardrail_block(load_shadow(user), load_settings(user), read_auth_store_for_rev276_280_micro_live_execution_guardrail(), user)}

@router.get("/autonomous-rev{revision}-micro-live-execution-guardrail")
def autonomous_rev_micro_live_execution_guardrail(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV276_280_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev276-280 micro-live execution guardrail revision")
    user = current_user.get("username", "default")
    key = _REV276_280_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev276_280_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev276_280_micro_live_execution_guardrail(), user)}

@router.get("/summary-autonomous-rev{revision}-micro-live-execution-guardrail")
def summary_autonomous_rev_micro_live_execution_guardrail(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV276_280_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev276-280 micro-live execution guardrail summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev276_280_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev276_280_micro_live_execution_guardrail(), user)}

# Rev281-285 First Limited-Live Session Control Block
from core.auth import read_auth_store as read_auth_store_for_rev281_285_first_limited_live_session_control
from services.autonomous_first_limited_live_session_control_block_service import (
    build_block_payload as build_rev281_285_first_limited_live_session_control_block,
    build_for_revision as build_rev281_285_for_revision,
    build_summary_for_revision as build_rev281_285_summary_for_revision,
)

_REV281_285_KEYS = {
    281: "first_session_boundary_contract",
    282: "session_max_loss_max_notional_enforcement",
    283: "session_timeout_cooldown_controller",
    284: "session_halt_emergency_state_router",
    285: "first_limited_live_session_decision_packet",
}

@router.get("/autonomous-first-limited-live-session-control-block")
def autonomous_first_limited_live_session_control_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_first_limited_live_session_control_block": build_rev281_285_first_limited_live_session_control_block(load_shadow(user), load_settings(user), read_auth_store_for_rev281_285_first_limited_live_session_control(), user)}

@router.get("/autonomous-rev{revision}-first-limited-live-session-control")
def autonomous_rev_first_limited_live_session_control(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV281_285_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev281-285 first limited-live session control revision")
    user = current_user.get("username", "default")
    key = _REV281_285_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev281_285_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev281_285_first_limited_live_session_control(), user)}

@router.get("/summary-autonomous-rev{revision}-first-limited-live-session-control")
def summary_autonomous_rev_first_limited_live_session_control(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV281_285_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev281-285 first limited-live session control summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev281_285_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev281_285_first_limited_live_session_control(), user)}

from core.auth import read_auth_store as read_auth_store_for_rev286_290_live_result_reconciliation_freeze
from services.autonomous_live_result_reconciliation_freeze_block_service import (
    build_block_payload as build_rev286_290_live_result_reconciliation_freeze_block,
    build_for_revision as build_rev286_290_for_revision,
    build_summary_for_revision as build_rev286_290_summary_for_revision,
)

_REV286_290_KEYS = {
    286: "rev286_live_fill_result_collector",
    287: "rev287_fee_slippage_latency_reality_recorder",
    288: "rev288_position_order_journal_final_reconciler",
    289: "rev289_post_session_freeze_cooldown_gate",
    290: "rev290_live_result_reconciliation_report",
}

@router.get("/autonomous-live-result-reconciliation-freeze-block")
def autonomous_live_result_reconciliation_freeze_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_result_reconciliation_freeze_block": build_rev286_290_live_result_reconciliation_freeze_block(load_shadow(user), load_settings(user), read_auth_store_for_rev286_290_live_result_reconciliation_freeze(), user)}

@router.get("/autonomous-rev{revision}-live-result-reconciliation-freeze")
def autonomous_rev_live_result_reconciliation_freeze(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV286_290_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev286-290 live result reconciliation freeze revision")
    user = current_user.get("username", "default")
    key = _REV286_290_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev286_290_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev286_290_live_result_reconciliation_freeze(), user)}

@router.get("/summary-autonomous-rev{revision}-live-result-reconciliation-freeze")
def summary_autonomous_rev_live_result_reconciliation_freeze(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV286_290_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev286-290 live result reconciliation freeze summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev286_290_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev286_290_live_result_reconciliation_freeze(), user)}

# Rev291-295 Repeat / Stop / Reduce Decision Block
from core.auth import read_auth_store as read_auth_store_for_rev291_295_repeat_stop_reduce
from services.autonomous_repeat_stop_reduce_decision_block_service import (
    build_block_payload as build_rev291_295_repeat_stop_reduce_block,
    build_for_revision as build_rev291_295_for_revision,
    build_summary_for_revision as build_rev291_295_summary_for_revision,
)

_REV291_295_KEYS = {
    291: "repeat_eligibility_after_live_result",
    292: "loss_based_stop_reduce_decision",
    293: "profit_but_low_sample_freeze_rule",
    294: "strategy_symbol_continuation_decision",
    295: "repeat_stop_reduce_decision_packet",
}

@router.get("/autonomous-repeat-stop-reduce-decision-block")
def autonomous_repeat_stop_reduce_decision_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_repeat_stop_reduce_decision_block": build_rev291_295_repeat_stop_reduce_block(load_shadow(user), load_settings(user), read_auth_store_for_rev291_295_repeat_stop_reduce(), user)}

@router.get("/autonomous-rev{revision}-repeat-stop-reduce-decision")
def autonomous_rev_repeat_stop_reduce_decision(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV291_295_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev291-295 repeat/stop/reduce revision")
    user = current_user.get("username", "default")
    key = _REV291_295_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev291_295_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev291_295_repeat_stop_reduce(), user)}

@router.get("/summary-autonomous-rev{revision}-repeat-stop-reduce-decision")
def summary_autonomous_rev_repeat_stop_reduce_decision(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV291_295_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev291-295 repeat/stop/reduce summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev291_295_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev291_295_repeat_stop_reduce(), user)}

# Rev296-300 Small Capital Controlled Autonomy Candidate Block
from core.auth import read_auth_store as read_auth_store_for_rev296_300_small_capital_autonomy
from services.autonomous_small_capital_controlled_autonomy_candidate_block_service import (
    build_block_payload as build_rev296_300_small_capital_autonomy_block,
    build_for_revision as build_rev296_300_for_revision,
    build_summary_for_revision as build_rev296_300_summary_for_revision,
)

_REV296_300_KEYS = {
    296: "small_capital_autonomy_readiness_recheck",
    297: "usdt_dominance_exposure_final_gate",
    298: "autonomous_halt_authority_final_proof",
    299: "operator_free_summary_final_compact_mode",
    300: "small_capital_controlled_autonomy_candidate_packet",
}

@router.get("/autonomous-small-capital-controlled-autonomy-candidate-block")
def autonomous_small_capital_controlled_autonomy_candidate_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_small_capital_controlled_autonomy_candidate_block": build_rev296_300_small_capital_autonomy_block(load_shadow(user), load_settings(user), read_auth_store_for_rev296_300_small_capital_autonomy(), user)}

@router.get("/autonomous-rev{revision}-small-capital-controlled-autonomy")
def autonomous_rev_small_capital_controlled_autonomy(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV296_300_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev296-300 small-capital controlled autonomy revision")
    user = current_user.get("username", "default")
    key = _REV296_300_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev296_300_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev296_300_small_capital_autonomy(), user)}

@router.get("/summary-autonomous-rev{revision}-small-capital-controlled-autonomy")
def summary_autonomous_rev_small_capital_controlled_autonomy(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV296_300_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev296-300 small-capital controlled autonomy summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev296_300_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev296_300_small_capital_autonomy(), user)}

# Rev301-305 Autonomy Candidate Verification Block
from core.auth import read_auth_store as read_auth_store_for_rev301_305_autonomy_candidate_verification
from services.autonomous_autonomy_candidate_verification_block_service import (
    build_block_payload as build_rev301_305_autonomy_candidate_verification_block,
    build_for_revision as build_rev301_305_autonomy_candidate_verification_for_revision,
    build_summary_for_revision as build_rev301_305_autonomy_candidate_verification_summary_for_revision,
)

_REV301_305_KEYS = {
    301: 'candidate_evidence_recheck',
    302: 'permission_ladder_consistency_validator',
    303: 'halt_freeze_reduce_authority_proof',
    304: 'summary_compact_decision_consistency_check',
    305: 'autonomy_candidate_verification_packet',
}

@router.get("/autonomous-autonomy-candidate-verification-block")
def autonomous_autonomy_candidate_verification_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_autonomy_candidate_verification_block": build_rev301_305_autonomy_candidate_verification_block(load_shadow(user), load_settings(user), read_auth_store_for_rev301_305_autonomy_candidate_verification(), user)}

@router.get("/autonomous-rev{revision}-autonomy-candidate-verification")
def autonomous_rev_autonomy_candidate_verification(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV301_305_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev301-305 Autonomy Candidate Verification revision")
    user = current_user.get("username", "default")
    key = _REV301_305_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev301_305_autonomy_candidate_verification_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev301_305_autonomy_candidate_verification(), user)}

@router.get("/summary-autonomous-rev{revision}-autonomy-candidate-verification")
def summary_autonomous_rev_autonomy_candidate_verification(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV301_305_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev301-305 Autonomy Candidate Verification summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev301_305_autonomy_candidate_verification_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev301_305_autonomy_candidate_verification(), user)}

# Rev306-310 Controlled Autonomy Dry-Run Block
from core.auth import read_auth_store as read_auth_store_for_rev306_310_controlled_autonomy_dry_run
from services.autonomous_controlled_autonomy_dry_run_block_service import (
    build_block_payload as build_rev306_310_controlled_autonomy_dry_run_block,
    build_for_revision as build_rev306_310_controlled_autonomy_dry_run_for_revision,
    build_summary_for_revision as build_rev306_310_controlled_autonomy_dry_run_summary_for_revision,
)

_REV306_310_KEYS = {
    306: 'small_cap_autonomy_dry_run_session_planner',
    307: 'dry_run_opportunity_to_intent_loop',
    308: 'dry_run_risk_approval_capital_gate',
    309: 'dry_run_halt_freeze_reduce_simulation',
    310: 'controlled_autonomy_dry_run_report',
}

@router.get("/autonomous-controlled-autonomy-dry-run-block")
def autonomous_controlled_autonomy_dry_run_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_controlled_autonomy_dry_run_block": build_rev306_310_controlled_autonomy_dry_run_block(load_shadow(user), load_settings(user), read_auth_store_for_rev306_310_controlled_autonomy_dry_run(), user)}

@router.get("/autonomous-rev{revision}-controlled-autonomy-dry-run")
def autonomous_rev_controlled_autonomy_dry_run(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV306_310_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev306-310 Controlled Autonomy Dry-Run revision")
    user = current_user.get("username", "default")
    key = _REV306_310_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev306_310_controlled_autonomy_dry_run_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev306_310_controlled_autonomy_dry_run(), user)}

@router.get("/summary-autonomous-rev{revision}-controlled-autonomy-dry-run")
def summary_autonomous_rev_controlled_autonomy_dry_run(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV306_310_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev306-310 Controlled Autonomy Dry-Run summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev306_310_controlled_autonomy_dry_run_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev306_310_controlled_autonomy_dry_run(), user)}

# Rev311-315 Live Permission Safety Contract Block
from core.auth import read_auth_store as read_auth_store_for_rev311_315_live_permission_safety_contract
from services.autonomous_live_permission_safety_contract_block_service import (
    build_block_payload as build_rev311_315_live_permission_safety_contract_block,
    build_for_revision as build_rev311_315_live_permission_safety_contract_for_revision,
    build_summary_for_revision as build_rev311_315_live_permission_safety_contract_summary_for_revision,
)

_REV311_315_KEYS = {
    311: 'live_permission_contract_schema',
    312: 'owner_approval_session_scope_final_guard',
    313: 'whitelist_symbol_permission_enforcement',
    314: 'daily_hard_stop_max_notional_binding',
    315: 'live_permission_safety_decision_packet',
}

@router.get("/autonomous-live-permission-safety-contract-block")
def autonomous_live_permission_safety_contract_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_permission_safety_contract_block": build_rev311_315_live_permission_safety_contract_block(load_shadow(user), load_settings(user), read_auth_store_for_rev311_315_live_permission_safety_contract(), user)}

@router.get("/autonomous-rev{revision}-live-permission-safety-contract")
def autonomous_rev_live_permission_safety_contract(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV311_315_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev311-315 Live Permission Safety Contract revision")
    user = current_user.get("username", "default")
    key = _REV311_315_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev311_315_live_permission_safety_contract_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev311_315_live_permission_safety_contract(), user)}

@router.get("/summary-autonomous-rev{revision}-live-permission-safety-contract")
def summary_autonomous_rev_live_permission_safety_contract(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV311_315_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev311-315 Live Permission Safety Contract summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev311_315_live_permission_safety_contract_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev311_315_live_permission_safety_contract(), user)}

# Rev316-320 Autonomous Capital Defense Runtime Block
from core.auth import read_auth_store as read_auth_store_for_rev316_320_capital_defense_runtime
from services.autonomous_capital_defense_runtime_block_service import (
    build_block_payload as build_rev316_320_capital_defense_runtime_block,
    build_for_revision as build_rev316_320_capital_defense_runtime_for_revision,
    build_summary_for_revision as build_rev316_320_capital_defense_runtime_summary_for_revision,
)

_REV316_320_KEYS = {
    316: 'usdt_reserve_runtime_monitor',
    317: 'profit_lock_runtime_enforcement_preview',
    318: 'drawdown_shrink_runtime_controller',
    319: 'exposure_drift_detector',
    320: 'capital_defense_runtime_packet',
}

@router.get("/autonomous-autonomous-capital-defense-runtime-block")
def autonomous_capital_defense_runtime_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_capital_defense_runtime_block": build_rev316_320_capital_defense_runtime_block(load_shadow(user), load_settings(user), read_auth_store_for_rev316_320_capital_defense_runtime(), user)}

@router.get("/autonomous-rev{revision}-autonomous-capital-defense-runtime")
def autonomous_rev_capital_defense_runtime(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV316_320_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev316-320 Autonomous Capital Defense Runtime revision")
    user = current_user.get("username", "default")
    key = _REV316_320_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev316_320_capital_defense_runtime_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev316_320_capital_defense_runtime(), user)}

@router.get("/summary-autonomous-rev{revision}-autonomous-capital-defense-runtime")
def summary_autonomous_rev_capital_defense_runtime(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV316_320_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev316-320 Autonomous Capital Defense Runtime summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev316_320_capital_defense_runtime_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev316_320_capital_defense_runtime(), user)}

# Rev321-325 Strategy Survival & Kill-Switch Block
from core.auth import read_auth_store as read_auth_store_for_rev321_325_strategy_survival_kill_switch
from services.autonomous_strategy_survival_kill_switch_block_service import (
    build_block_payload as build_rev321_325_strategy_survival_kill_switch_block,
    build_for_revision as build_rev321_325_strategy_survival_kill_switch_for_revision,
    build_summary_for_revision as build_rev321_325_strategy_survival_kill_switch_summary_for_revision,
)

_REV321_325_KEYS = {
    321: 'strategy_survival_score',
    322: 'consecutive_underperformance_detector',
    323: 'strategy_symbol_kill_switch_preview',
    324: 'quarantine_downgrade_decision_controller',
    325: 'strategy_survival_decision_packet',
}

@router.get("/autonomous-strategy-survival-kill-switch-block")
def autonomous_strategy_survival_kill_switch_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_strategy_survival_kill_switch_block": build_rev321_325_strategy_survival_kill_switch_block(load_shadow(user), load_settings(user), read_auth_store_for_rev321_325_strategy_survival_kill_switch(), user)}

@router.get("/autonomous-rev{revision}-strategy-survival-kill-switch")
def autonomous_rev_strategy_survival_kill_switch(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV321_325_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev321-325 Strategy Survival & Kill-Switch revision")
    user = current_user.get("username", "default")
    key = _REV321_325_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev321_325_strategy_survival_kill_switch_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev321_325_strategy_survival_kill_switch(), user)}

@router.get("/summary-autonomous-rev{revision}-strategy-survival-kill-switch")
def summary_autonomous_rev_strategy_survival_kill_switch(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV321_325_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev321-325 Strategy Survival & Kill-Switch summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev321_325_strategy_survival_kill_switch_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev321_325_strategy_survival_kill_switch(), user)}

# Rev326-330 Operator-Free Summary v4 Block
from core.auth import read_auth_store as read_auth_store_for_rev326_330_operator_free_summary_v4
from services.autonomous_operator_free_summary_v4_block_service import (
    build_block_payload as build_rev326_330_operator_free_summary_v4_block,
    build_for_revision as build_rev326_330_operator_free_summary_v4_for_revision,
    build_summary_for_revision as build_rev326_330_operator_free_summary_v4_summary_for_revision,
)

_REV326_330_KEYS = {
    326: 'summary_decision_hierarchy_v4',
    327: 'single_line_daily_action_output',
    328: 'critical_blocker_priority_engine',
    329: 'owner_action_minimal_card',
    330: 'operator_free_summary_v4_packet',
}

@router.get("/autonomous-operator-free-summary-v4-block")
def autonomous_operator_free_summary_v4_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_operator_free_summary_v4_block": build_rev326_330_operator_free_summary_v4_block(load_shadow(user), load_settings(user), read_auth_store_for_rev326_330_operator_free_summary_v4(), user)}

@router.get("/autonomous-rev{revision}-operator-free-summary-v4")
def autonomous_rev_operator_free_summary_v4(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV326_330_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev326-330 Operator-Free Summary v4 revision")
    user = current_user.get("username", "default")
    key = _REV326_330_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev326_330_operator_free_summary_v4_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev326_330_operator_free_summary_v4(), user)}

@router.get("/summary-autonomous-rev{revision}-operator-free-summary-v4")
def summary_autonomous_rev_operator_free_summary_v4(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV326_330_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev326-330 Operator-Free Summary v4 summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev326_330_operator_free_summary_v4_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev326_330_operator_free_summary_v4(), user)}

# Rev331-335 First Small-Cap Limited Autonomy Candidate Block
from core.auth import read_auth_store as read_auth_store_for_rev331_335_first_small_cap_limited_autonomy_candidate
from services.autonomous_first_small_cap_limited_autonomy_candidate_block_service import (
    build_block_payload as build_rev331_335_first_small_cap_limited_autonomy_candidate_block,
    build_for_revision as build_rev331_335_first_small_cap_limited_autonomy_candidate_for_revision,
    build_summary_for_revision as build_rev331_335_first_small_cap_limited_autonomy_candidate_summary_for_revision,
)

_REV331_335_KEYS = {
    331: 'small_cap_autonomy_final_checklist',
    332: 'first_limited_autonomy_session_contract',
    333: 'autonomy_rollback_freeze_protocol_finalizer',
    334: 'deploy_safe_autonomy_package_audit',
    335: 'first_small_cap_limited_autonomy_candidate_packet',
}

@router.get("/autonomous-first-small-cap-limited-autonomy-candidate-block")
def autonomous_first_small_cap_limited_autonomy_candidate_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_first_small_cap_limited_autonomy_candidate_block": build_rev331_335_first_small_cap_limited_autonomy_candidate_block(load_shadow(user), load_settings(user), read_auth_store_for_rev331_335_first_small_cap_limited_autonomy_candidate(), user)}

@router.get("/autonomous-rev{revision}-first-small-cap-limited-autonomy-candidate")
def autonomous_rev_first_small_cap_limited_autonomy_candidate(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV331_335_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev331-335 First Small-Cap Limited Autonomy Candidate revision")
    user = current_user.get("username", "default")
    key = _REV331_335_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev331_335_first_small_cap_limited_autonomy_candidate_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev331_335_first_small_cap_limited_autonomy_candidate(), user)}

@router.get("/summary-autonomous-rev{revision}-first-small-cap-limited-autonomy-candidate")
def summary_autonomous_rev_first_small_cap_limited_autonomy_candidate(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV331_335_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev331-335 First Small-Cap Limited Autonomy Candidate summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev331_335_first_small_cap_limited_autonomy_candidate_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev331_335_first_small_cap_limited_autonomy_candidate(), user)}


# Rev336-370 generated autonomous continuation routes

# Rev336-340 Small-Cap Autonomy Final Validation Block
from core.auth import read_auth_store as read_auth_store_for_rev336_340_small_cap_autonomy_final_validation
from services.autonomous_small_cap_autonomy_final_validation_block_service import (
    build_block_payload as build_rev336_340_small_cap_autonomy_final_validation_block,
    build_for_revision as build_rev336_340_small_cap_autonomy_final_validation_for_revision,
    build_summary_for_revision as build_rev336_340_small_cap_autonomy_final_validation_summary_for_revision,
)

_REV336_340_KEYS = {
    336: 'rev335_autonomy_candidate_evidence_recheck',
    337: 'small_cap_risk_capital_final_validator',
    338: 'permission_ladder_owner_approval_final_check',
    339: 'summary_v4_decision_consistency_validator',
    340: 'small_cap_autonomy_final_validation_packet',
}

@router.get("/autonomous-small-cap-autonomy-final-validation-block")
def autonomous_small_cap_autonomy_final_validation_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_small_cap_autonomy_final_validation_block": build_rev336_340_small_cap_autonomy_final_validation_block(load_shadow(user), load_settings(user), read_auth_store_for_rev336_340_small_cap_autonomy_final_validation(), user)}

@router.get("/autonomous-rev{revision}-small-cap-autonomy-final-validation")
def autonomous_rev_small_cap_autonomy_final_validation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV336_340_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev336-340 Small-Cap Autonomy Final Validation revision")
    user = current_user.get("username", "default")
    key = _REV336_340_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev336_340_small_cap_autonomy_final_validation_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev336_340_small_cap_autonomy_final_validation(), user)}

@router.get("/summary-autonomous-rev{revision}-small-cap-autonomy-final-validation")
def summary_autonomous_rev_small_cap_autonomy_final_validation(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV336_340_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev336-340 Small-Cap Autonomy Final Validation summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev336_340_small_cap_autonomy_final_validation_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev336_340_small_cap_autonomy_final_validation(), user)}

# Rev341-345 Live Activation Command Contract Block
from core.auth import read_auth_store as read_auth_store_for_rev341_345_live_activation_command_contract
from services.autonomous_live_activation_command_contract_block_service import (
    build_block_payload as build_rev341_345_live_activation_command_contract_block,
    build_for_revision as build_rev341_345_live_activation_command_contract_for_revision,
    build_summary_for_revision as build_rev341_345_live_activation_command_contract_summary_for_revision,
)

_REV341_345_KEYS = {
    341: 'live_activation_command_schema',
    342: 'owner_approval_command_scope_binder',
    343: 'activation_expiry_stale_command_guard',
    344: 'command_to_session_audit_contract',
    345: 'live_activation_command_decision_packet',
}

@router.get("/autonomous-live-activation-command-contract-block")
def autonomous_live_activation_command_contract_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_activation_command_contract_block": build_rev341_345_live_activation_command_contract_block(load_shadow(user), load_settings(user), read_auth_store_for_rev341_345_live_activation_command_contract(), user)}

@router.get("/autonomous-rev{revision}-live-activation-command-contract")
def autonomous_rev_live_activation_command_contract(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV341_345_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev341-345 Live Activation Command Contract revision")
    user = current_user.get("username", "default")
    key = _REV341_345_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev341_345_live_activation_command_contract_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev341_345_live_activation_command_contract(), user)}

@router.get("/summary-autonomous-rev{revision}-live-activation-command-contract")
def summary_autonomous_rev_live_activation_command_contract(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV341_345_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev341-345 Live Activation Command Contract summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev341_345_live_activation_command_contract_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev341_345_live_activation_command_contract(), user)}

# Rev346-350 First Micro-Live Controlled Execution Path Block
from core.auth import read_auth_store as read_auth_store_for_rev346_350_first_micro_live_controlled_execution_path
from services.autonomous_first_micro_live_controlled_execution_path_block_service import (
    build_block_payload as build_rev346_350_first_micro_live_controlled_execution_path_block,
    build_for_revision as build_rev346_350_first_micro_live_controlled_execution_path_for_revision,
    build_summary_for_revision as build_rev346_350_first_micro_live_controlled_execution_path_summary_for_revision,
)

_REV346_350_KEYS = {
    346: 'first_micro_live_execution_intent_finalizer',
    347: 'submit_path_explicit_enable_proof',
    348: 'order_preview_to_execution_contract',
    349: 'execution_blocked_by_default_proof',
    350: 'first_micro_live_execution_path_report',
}

@router.get("/autonomous-first-micro-live-controlled-execution-path-block")
def autonomous_first_micro_live_controlled_execution_path_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_first_micro_live_controlled_execution_path_block": build_rev346_350_first_micro_live_controlled_execution_path_block(load_shadow(user), load_settings(user), read_auth_store_for_rev346_350_first_micro_live_controlled_execution_path(), user)}

@router.get("/autonomous-rev{revision}-first-micro-live-controlled-execution-path")
def autonomous_rev_first_micro_live_controlled_execution_path(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV346_350_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev346-350 First Micro-Live Controlled Execution Path revision")
    user = current_user.get("username", "default")
    key = _REV346_350_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev346_350_first_micro_live_controlled_execution_path_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev346_350_first_micro_live_controlled_execution_path(), user)}

@router.get("/summary-autonomous-rev{revision}-first-micro-live-controlled-execution-path")
def summary_autonomous_rev_first_micro_live_controlled_execution_path(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV346_350_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev346-350 First Micro-Live Controlled Execution Path summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev346_350_first_micro_live_controlled_execution_path_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev346_350_first_micro_live_controlled_execution_path(), user)}

# Rev351-355 Live Exit & Emergency Control Contract Block
from core.auth import read_auth_store as read_auth_store_for_rev351_355_live_exit_emergency_control_contract
from services.autonomous_live_exit_emergency_control_contract_block_service import (
    build_block_payload as build_rev351_355_live_exit_emergency_control_contract_block,
    build_for_revision as build_rev351_355_live_exit_emergency_control_contract_for_revision,
    build_summary_for_revision as build_rev351_355_live_exit_emergency_control_contract_summary_for_revision,
)

_REV351_355_KEYS = {
    351: 'exit_plan_final_contract',
    352: 'sl_tp_trailing_timeout_binding',
    353: 'manual_attention_emergency_close_guard',
    354: 'close_blocked_by_default_proof',
    355: 'live_exit_emergency_control_packet',
}

@router.get("/autonomous-live-exit-emergency-control-contract-block")
def autonomous_live_exit_emergency_control_contract_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_live_exit_emergency_control_contract_block": build_rev351_355_live_exit_emergency_control_contract_block(load_shadow(user), load_settings(user), read_auth_store_for_rev351_355_live_exit_emergency_control_contract(), user)}

@router.get("/autonomous-rev{revision}-live-exit-emergency-control-contract")
def autonomous_rev_live_exit_emergency_control_contract(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV351_355_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev351-355 Live Exit & Emergency Control Contract revision")
    user = current_user.get("username", "default")
    key = _REV351_355_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev351_355_live_exit_emergency_control_contract_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev351_355_live_exit_emergency_control_contract(), user)}

@router.get("/summary-autonomous-rev{revision}-live-exit-emergency-control-contract")
def summary_autonomous_rev_live_exit_emergency_control_contract(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV351_355_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev351-355 Live Exit & Emergency Control Contract summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev351_355_live_exit_emergency_control_contract_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev351_355_live_exit_emergency_control_contract(), user)}

# Rev356-360 Post-Live Evidence & Decision Freeze Block
from core.auth import read_auth_store as read_auth_store_for_rev356_360_post_live_evidence_decision_freeze
from services.autonomous_post_live_evidence_decision_freeze_block_service import (
    build_block_payload as build_rev356_360_post_live_evidence_decision_freeze_block,
    build_for_revision as build_rev356_360_post_live_evidence_decision_freeze_for_revision,
    build_summary_for_revision as build_rev356_360_post_live_evidence_decision_freeze_summary_for_revision,
)

_REV356_360_KEYS = {
    356: 'live_execution_evidence_completeness_scorer',
    357: 'fee_slippage_latency_final_reality_check',
    358: 'journal_order_position_reconciliation_confidence',
    359: 'post_live_freeze_cooldown_review_gate',
    360: 'post_live_evidence_decision_packet',
}

@router.get("/autonomous-post-live-evidence-decision-freeze-block")
def autonomous_post_live_evidence_decision_freeze_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_post_live_evidence_decision_freeze_block": build_rev356_360_post_live_evidence_decision_freeze_block(load_shadow(user), load_settings(user), read_auth_store_for_rev356_360_post_live_evidence_decision_freeze(), user)}

@router.get("/autonomous-rev{revision}-post-live-evidence-decision-freeze")
def autonomous_rev_post_live_evidence_decision_freeze(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV356_360_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev356-360 Post-Live Evidence & Decision Freeze revision")
    user = current_user.get("username", "default")
    key = _REV356_360_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev356_360_post_live_evidence_decision_freeze_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev356_360_post_live_evidence_decision_freeze(), user)}

@router.get("/summary-autonomous-rev{revision}-post-live-evidence-decision-freeze")
def summary_autonomous_rev_post_live_evidence_decision_freeze(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV356_360_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev356-360 Post-Live Evidence & Decision Freeze summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev356_360_post_live_evidence_decision_freeze_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev356_360_post_live_evidence_decision_freeze(), user)}

# Rev361-365 Controlled Growth Permission Block
from core.auth import read_auth_store as read_auth_store_for_rev361_365_controlled_growth_permission
from services.autonomous_controlled_growth_permission_block_service import (
    build_block_payload as build_rev361_365_controlled_growth_permission_block,
    build_for_revision as build_rev361_365_controlled_growth_permission_for_revision,
    build_summary_for_revision as build_rev361_365_controlled_growth_permission_summary_for_revision,
)

_REV361_365_KEYS = {
    361: 'repeat_permission_evidence_threshold',
    362: 'minimum_sample_size_growth_blocker',
    363: 'controlled_notional_increase_preview',
    364: 'growth_blocked_by_default_proof',
    365: 'controlled_growth_permission_packet',
}

@router.get("/autonomous-controlled-growth-permission-block")
def autonomous_controlled_growth_permission_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_controlled_growth_permission_block": build_rev361_365_controlled_growth_permission_block(load_shadow(user), load_settings(user), read_auth_store_for_rev361_365_controlled_growth_permission(), user)}

@router.get("/autonomous-rev{revision}-controlled-growth-permission")
def autonomous_rev_controlled_growth_permission(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV361_365_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev361-365 Controlled Growth Permission revision")
    user = current_user.get("username", "default")
    key = _REV361_365_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev361_365_controlled_growth_permission_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev361_365_controlled_growth_permission(), user)}

@router.get("/summary-autonomous-rev{revision}-controlled-growth-permission")
def summary_autonomous_rev_controlled_growth_permission(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV361_365_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev361-365 Controlled Growth Permission summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev361_365_controlled_growth_permission_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev361_365_controlled_growth_permission(), user)}

# Rev366-370 Production Small-Cap Live Candidate v2 Block
from core.auth import read_auth_store as read_auth_store_for_rev366_370_production_small_cap_live_candidate_v2
from services.autonomous_production_small_cap_live_candidate_v2_block_service import (
    build_block_payload as build_rev366_370_production_small_cap_live_candidate_v2_block,
    build_for_revision as build_rev366_370_production_small_cap_live_candidate_v2_for_revision,
    build_summary_for_revision as build_rev366_370_production_small_cap_live_candidate_v2_summary_for_revision,
)

_REV366_370_KEYS = {
    366: 'production_small_cap_live_checklist_v2',
    367: 'live_risk_capital_permission_combined_final_gate',
    368: 'deploy_safe_runtime_package_audit_v2',
    369: 'rollback_halt_freeze_final_readiness',
    370: 'production_small_cap_live_candidate_v2_packet',
}

@router.get("/autonomous-production-small-cap-live-candidate-v2-block")
def autonomous_production_small_cap_live_candidate_v2_block(current_user: dict = Depends(require_user)):
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "autonomous_production_small_cap_live_candidate_v2_block": build_rev366_370_production_small_cap_live_candidate_v2_block(load_shadow(user), load_settings(user), read_auth_store_for_rev366_370_production_small_cap_live_candidate_v2(), user)}

@router.get("/autonomous-rev{revision}-production-small-cap-live-candidate-v2")
def autonomous_rev_production_small_cap_live_candidate_v2(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV366_370_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev366-370 Production Small-Cap Live Candidate v2 revision")
    user = current_user.get("username", "default")
    key = _REV366_370_KEYS[int(revision)]
    return {"status": "ok", "user": user, key: build_rev366_370_production_small_cap_live_candidate_v2_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev366_370_production_small_cap_live_candidate_v2(), user)}

@router.get("/summary-autonomous-rev{revision}-production-small-cap-live-candidate-v2")
def summary_autonomous_rev_production_small_cap_live_candidate_v2(revision: int, current_user: dict = Depends(require_user)):
    if int(revision) not in _REV366_370_KEYS:
        raise HTTPException(status_code=404, detail="Unsupported Rev366-370 Production Small-Cap Live Candidate v2 summary revision")
    user = current_user.get("username", "default")
    return {"status": "ok", "user": user, "summary": build_rev366_370_production_small_cap_live_candidate_v2_summary_for_revision(int(revision), load_shadow(user), load_settings(user), read_auth_store_for_rev366_370_production_small_cap_live_candidate_v2(), user)}


# =========================

# Rev871-875: compatibility endpoint for stale-but-rendered frontend summary hooks.
# It prevents UI sync warnings from historical optional summary calls while keeping
# real trading disabled and clearly marking the response as compatibility-only.
@router.get("/summary-autonomous-rev{summary_path:path}")
def summary_autonomous_revision_compatibility(summary_path: str, current_user: dict = Depends(require_user)):
    revision = str(summary_path or "").strip("/-")
    user = current_user.get("username", "default")
    return {
        "status": "ok",
        "user": user,
        "summary": {
            "revision_reference": f"rev{revision}" if revision else "unknown",
            "decision": "COMPATIBILITY_REVIEW",
            "trade_allowed": False,
            "blocker": "historical_summary_route_compatibility_response",
            "owner_action": "none",
            "real_submit_close_default_off": True,
            "secret_values_returned": False,
        },
    }
