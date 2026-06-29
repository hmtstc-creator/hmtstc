from __future__ import annotations

from copy import deepcopy
import json
from datetime import datetime, timezone
from typing import Any

from services.performance_service import (
    format_duration,
    get_active_usdt,
    get_closed_pnl,
    get_open_pnl,
    get_trade_stats,
    shadow_wallet_value,
    total_pnl_value,
)
from services.real_trade_state_service import ensure_real_trade_state, open_real_positions
from services.real_trade_safety_service import build_runtime_health
from services.real_balance_service import build_reconciliation_dashboard_summary
from services.deploy_safety_service import build_real_lock_report, build_deploy_safety_report
from services.portfolio_allocation_final_service import build_portfolio_visibility_summary
from services.revision_37_service import (
    build_endpoint_contract_report,
    build_gate_report,
    build_runtime_leak_report,
    build_revision_37_quality_report,
)



_SUMMARY_CACHE: dict[str, Any] = {"key": None, "payload": None, "created_at": 0.0}
_SUMMARY_CACHE_TTL_SECONDS = 10.0

def _summary_cache_key(user: str, data: dict, settings: dict) -> str:
    try:
        raw = json.dumps({"user": user, "data": data, "settings": settings}, sort_keys=True, default=str, separators=(",", ":"))
    except TypeError:
        raw = repr((user, data, settings))
    return str(hash(raw))

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def compact_status(value: Any, fallback: str = "unknown") -> str:
    text = str(value or fallback).strip().lower()
    if text in {"ok", "healthy", "pass", "passed", "ready", "clear"}:
        return "ok"
    if text in {"blocked", "error", "critical", "danger", "failed"}:
        return "blocked"
    if text in {"warning", "warn", "review", "degraded", "partial", "pending"}:
        return "review"
    return text or fallback


def newest(*values: Any) -> Any:
    for value in values:
        if value:
            return value
    return None


def _best_position(items: list[dict], reverse: bool = True) -> dict | None:
    usable = [item for item in items if isinstance(item, dict)]
    if not usable:
        return None
    return sorted(usable, key=lambda item: safe_float(item.get("pnl"), 0.0), reverse=reverse)[0]


def _position_summary(item: dict | None) -> dict | None:
    if not item:
        return None
    return {
        "symbol": item.get("symbol") or item.get("pair") or "-",
        "pnl": safe_float(item.get("pnl"), 0.0),
        "side": item.get("side") or item.get("direction") or "-",
        "status": item.get("status") or "open",
    }


def _scan_summary(data: dict) -> dict:
    scan = data.get("last_scan") or data.get("scan_trace") or {}
    candidates = scan.get("candidates") if isinstance(scan.get("candidates"), list) else []
    rejected = scan.get("rejected") if isinstance(scan.get("rejected"), list) else []
    total = safe_int(scan.get("scanned") or scan.get("total_symbols") or scan.get("total") or len(candidates) + len(rejected), 0)
    candidate_count = safe_int(scan.get("candidates_count") or scan.get("candidate_symbols") or len(candidates), 0)
    rejected_count = safe_int(scan.get("rejected_count") or scan.get("excluded_symbols") or len(rejected), 0)
    eligible = safe_int(scan.get("eligible_symbols") or scan.get("eligible_count") or max(total - rejected_count, candidate_count), 0)
    reason = scan.get("top_rejection_reason") or scan.get("main_reject_reason") or scan.get("dominant_reject_reason")
    return {
        "regime": scan.get("market_regime") or scan.get("regime") or "unknown",
        "total_symbols": total,
        "eligible_symbols": eligible,
        "excluded_symbols": rejected_count,
        "candidate_symbols": candidate_count,
        "deep_analyzed_symbols": safe_int(scan.get("deep_analyzed") or scan.get("deep_analyzed_symbols") or eligible, eligible),
        "main_reject_reason": reason or "not_available",
        "volatility_state": scan.get("volatility_state") or scan.get("volatility") or "unknown",
        "last_scan_at": scan.get("time") or scan.get("created_at") or scan.get("started_at"),
    }


def _quality_summary(data: dict, settings: dict) -> dict:
    try:
        rev37 = build_revision_37_quality_report(data, settings)
    except Exception as error:
        rev37 = {"status": "review", "error": str(error)}
    try:
        gates = build_gate_report(data, settings)
    except Exception:
        gates = {}
    try:
        leak = build_runtime_leak_report()
    except Exception:
        leak = {}
    try:
        endpoint = build_endpoint_contract_report()
    except Exception:
        endpoint = {}
    try:
        deploy = build_deploy_safety_report(data, settings)
    except Exception:
        deploy = {}
    sections = rev37.get("sections") if isinstance(rev37.get("sections"), dict) else {}
    return {
        "revision_37": compact_status(rev37.get("status")),
        "deploy_safety": compact_status(deploy.get("status") or (sections.get("package_manifest") or {}).get("status")),
        "ai_safe_mode": "ok" if "rev35_ai_analyst_safe_mode" not in (gates.get("blockers") or []) else "review",
        "pilot_procedure": "ok" if "rev36_live_micro_pilot_procedure" not in (gates.get("blockers") or []) else "review",
        "runtime_leak": compact_status(leak.get("status")),
        "endpoint_contract": compact_status(endpoint.get("status")),
        "real_readiness_blockers": 0,
        "gates_passed": safe_int(gates.get("passed_count"), 0),
        "gates_total": safe_int(gates.get("gate_count"), 0),
        "blockers": rev37.get("blockers") or gates.get("blockers") or [],
    }


def _alerts_summary(data: dict) -> dict:
    logs = data.get("logs") if isinstance(data.get("logs"), list) else []
    critical = []
    blocked = []
    api_errors = 0
    stale = []
    for item in reversed(logs[-300:]):
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or item.get("severity") or "").lower()
        event = str(item.get("event") or item.get("category") or "").lower()
        message = str(item.get("message") or item.get("detail") or "")
        row = {"time": item.get("time") or item.get("created_at"), "level": level or event or "info", "message": message[:180]}
        if level in {"critical", "error"} and len(critical) < 5:
            critical.append(row)
        if "blocked" in level or "blocked" in event or "block" in message.lower():
            if len(blocked) < 5:
                blocked.append(row)
        if "api" in event and level in {"error", "critical"}:
            api_errors += 1
        if "stale" in event or "stale" in message.lower():
            if len(stale) < 5:
                stale.append(row)
    real = ensure_real_trade_state(data)
    return {
        "critical_logs": critical,
        "blocked_events": blocked,
        "api_errors": api_errors,
        "stale_warnings": stale,
        "last_backup": data.get("last_backup_at") or data.get("last_runtime_backup_at"),
        "last_deploy_check": real.get("last_deploy_lock_at") or data.get("last_deploy_check_at"),
    }


def attach_portfolio_allocation_summary(result: dict, data: dict, settings: dict) -> dict:
    """Attach Rev52 portfolio allocation visibility without side effects.

    This keeps Summary read-only and prevents missing optional portfolio helpers
    from crashing the core summary endpoint.
    """
    try:
        visibility = build_portfolio_visibility_summary(data or {}, settings or {})
    except Exception as exc:  # defensive summary fallback
        visibility = {
            "status": "review",
            "read_only": True,
            "error": str(exc),
            "summary_cards": {},
        }
    result["portfolio_allocation"] = visibility
    result.setdefault("quality", {})["portfolio_allocation"] = visibility.get("status", "review")
    return result


def build_summary(data: dict | None, settings: dict | None, user: str = "default") -> dict:
    # Summary is a read-only reporting payload. Some lower-level helpers normalize
    # structures with setdefault, so work on deep copies to avoid mutating runtime stores.
    source_data = data if isinstance(data, dict) else {}
    source_settings = settings if isinstance(settings, dict) else {}
    # Final3 audit fix: the Summary route aggregates many legacy read-only
    # decision helpers. Repeated calls with unchanged runtime state should not
    # rebuild the full legacy tree and stall API/UI smoke tests. The cache is
    # short-lived, user-scoped, source-hash guarded and returns a deepcopy so
    # callers cannot mutate the cached payload.
    try:
        from time import monotonic
        cache_key = _summary_cache_key(user, source_data, source_settings)
        if _SUMMARY_CACHE.get("key") == cache_key and _SUMMARY_CACHE.get("payload") is not None:
            if monotonic() - float(_SUMMARY_CACHE.get("created_at") or 0.0) <= _SUMMARY_CACHE_TTL_SECONDS:
                return deepcopy(_SUMMARY_CACHE["payload"])
    except Exception:
        cache_key = None
    data = deepcopy(source_data)
    settings = deepcopy(source_settings)
    real_state = ensure_real_trade_state(data)
    paper_positions = data.get("open_positions") if isinstance(data.get("open_positions"), list) else []
    real_positions = open_real_positions(real_state)
    bot = settings.get("bot", {}) if isinstance(settings.get("bot"), dict) else {}
    risk = settings.get("risk", {}) if isinstance(settings.get("risk"), dict) else {}
    runtime = build_runtime_health(data, settings)
    lock = build_real_lock_report(data)
    market = _scan_summary(data)
    trade_stats = get_trade_stats(data)
    active_usdt = get_active_usdt(data)
    wallet = shadow_wallet_value(data)
    allocated = safe_float(bot.get("allocated_usdt"), 1000.0)
    reserve_pct = max(0.0, min(100.0, ((wallet - active_usdt) / wallet * 100.0) if wallet else 0.0))
    risk_usage = max(0.0, min(100.0, (active_usdt / allocated * 100.0) if allocated else 0.0))
    recommendation = data.get("recommendation") if isinstance(data.get("recommendation"), dict) else {}
    real_status = "locked"
    if lock.get("status") == "blocked":
        real_status = "blocked"
    elif real_state.get("pilot", {}).get("active"):
        real_status = "pilot"
    elif real_state.get("dry_run", True):
        real_status = "dry-run"
    quality = _quality_summary(data, settings)
    quality["real_readiness_blockers"] = len(lock.get("blockers") or [])
    reconciliation_summary = build_reconciliation_dashboard_summary(data)
    missing_sources = []
    if not data.get("last_scan"):
        missing_sources.append("scan_snapshot")
    if not recommendation:
        missing_sources.append("model_recommendation")
    status = "ok" if not missing_sources else "partial"
    result = {
        "status": status,
        "generated_at": now_iso(),
        "user": user,
        "missing_sources": missing_sources,
        "system": {
            "mode": settings.get("api", {}).get("mode") if isinstance(settings.get("api"), dict) else "shadow",
            "runtime_health": compact_status(runtime.get("status") or runtime.get("runtime_status"), "healthy"),
            "real_trading": real_status,
            "emergency": bool(data.get("emergency_stop") or real_state.get("emergency_lock")),
            "last_sync": newest(data.get("last_tick"), data.get("last_updated_at"), data.get("last_calculation_at")),
            "bot_running": bool(data.get("bot_running")),
        },
        "money": {
            "paper_wallet": wallet,
            "paper_pnl": total_pnl_value(data),
            "paper_realized_pnl": get_closed_pnl(data),
            "paper_unrealized_pnl": get_open_pnl(data),
            "real_usdt_free": real_state.get("wallet", {}).get("USDT", {}).get("free") if isinstance(real_state.get("wallet"), dict) else None,
            "real_usdt_locked": real_state.get("wallet", {}).get("USDT", {}).get("locked") if isinstance(real_state.get("wallet"), dict) else None,
            "usdt_reserve_percent": round(reserve_pct, 2),
            "risk_usage_percent": round(risk_usage, 2),
            "daily_risk_limit": risk.get("daily_loss_limit") or risk.get("daily_loss_limit_usdt"),
            "real_realized_pnl": reconciliation_summary.get("realized_pnl_usdt"),
            "real_unrealized_pnl": reconciliation_summary.get("unrealized_pnl_usdt"),
            "real_total_pnl": reconciliation_summary.get("total_pnl_usdt"),
            "real_today_pnl": reconciliation_summary.get("today_pnl_usdt"),
            "real_weekly_pnl": reconciliation_summary.get("this_week_pnl_usdt"),
            "active_usdt": active_usdt,
            "max_slots": safe_int(bot.get("max_open_positions"), 5),
            "used_slots": len(paper_positions),
        },
        "models": {
            "best_model": recommendation.get("best_model_id") or recommendation.get("current_model_id") or recommendation.get("model_id"),
            "candidate_model": recommendation.get("candidate_model_id") or recommendation.get("candidate"),
            "recommendation": recommendation.get("action") or recommendation.get("decision") or "WATCH",
            "confidence": recommendation.get("confidence_score") or recommendation.get("confidence"),
            "reason": recommendation.get("reason") or recommendation.get("message") or "Model önerisi için yeterli canlı örnek yok.",
            "insufficient_data": bool(recommendation.get("insufficient_data") or trade_stats.get("total_trades", 0) < 10),
            "trade_stats": trade_stats,
        },
        "market": market,
        "positions": {
            "paper_open_count": len(paper_positions),
            "real_open_count": len(real_positions),
            "manual_attention_required": bool(real_state.get("manual_attention_required")),
            "best_open_position": _position_summary(_best_position(paper_positions + real_positions, True)),
            "worst_open_position": _position_summary(_best_position(paper_positions + real_positions, False)),
            "avg_holding_time": trade_stats.get("avg_holding_text") or format_duration(0),
        },
        "quality": {**quality, "reconciliation": reconciliation_summary.get("status"), "reconciliation_required": reconciliation_summary.get("reconciliation_required"), "reconciliation_issues": reconciliation_summary.get("issues_count"), "mismatch_lock": reconciliation_summary.get("real_trade_locked_by_reconciliation")},
        "reconciliation": reconciliation_summary,
        "alerts": _alerts_summary(data),
    }
    result = attach_emergency_summary(result, data, settings)
    result = attach_pilot_summary(result, data, settings)
    result = attach_market_intelligence_summary(result, data, settings)
    result = attach_autonomous_decision_summary(result, data, settings)
    result = attach_strategy_selection_summary(result, data, settings)
    result = attach_risk_brain_summary(result, data, settings)
    result = attach_trade_quality_feedback_summary(result, data, settings)
    result = attach_daily_operation_summary(result, data, settings)
    result = attach_user_api_secret_layer_summary(result, data, settings)
    result = attach_execution_governor_summary(result, data, settings)
    result = attach_adaptive_parameter_tuner_summary(result, data, settings)
    result = attach_autonomous_control_loop_summary(result, data, settings)
    result = attach_autonomous_safety_supervisor_summary(result, data, settings)
    result = attach_autonomous_capital_allocator_summary(result, data, settings)
    result = attach_autonomous_position_manager_summary(result, data, settings)
    result = attach_autonomous_paper_result_evaluator_summary(result, data, settings)
    result = attach_autonomous_paper_promotion_gate_summary(result, data, settings)
    result = attach_autonomous_micro_real_readiness_gate_summary(result, data, settings)
    result = attach_autonomous_micro_real_probe_planner_summary(result, data, settings)
    result = attach_autonomous_micro_real_approval_gate_summary(result, data, settings)
    result = attach_autonomous_micro_real_execution_sandbox_summary(result, data, settings)
    result = attach_autonomous_micro_real_exchange_adapter_hardening_summary(result, data, settings)
    result = attach_autonomous_micro_real_order_submitter_preview_summary(result, data, settings)
    result = attach_autonomous_first_micro_real_controlled_execution_summary(result, data, settings)
    result = attach_autonomous_micro_real_position_tracker_summary(result, data, settings)
    result = attach_autonomous_micro_real_exit_manager_summary(result, data, settings)
    result = attach_autonomous_micro_real_result_evaluator_summary(result, data, settings)
    result = attach_autonomous_micro_real_promotion_demotion_controller_summary(result, data, settings)
    result = attach_autonomous_semi_autonomous_real_trading_lane_summary(result, data, settings)
    result = attach_autonomous_fully_autonomous_small_capital_mode_summary(result, data, settings)
    result = attach_autonomous_profit_protection_scaling_rules_summary(result, data, settings)
    result = attach_autonomous_operator_free_dashboard_summary(result, data, settings)
    result = attach_autonomous_production_go_live_candidate_summary(result, data, settings)
    result = attach_autonomous_live_config_governance_summary(result, data, settings)
    result = attach_autonomous_first_micro_real_submit_enable_flag_summary(result, data, settings)
    result = attach_autonomous_real_binance_micro_order_submitter_summary(result, data, settings)
    result = attach_autonomous_order_status_poller_exchange_response_recorder_summary(result, data, settings)
    result = attach_autonomous_micro_real_live_ops_block_summary(result, data, settings)
    result = attach_autonomous_real_learning_runtime_block_summary(result, data, settings)
    result = attach_autonomous_live_production_ops_block_summary(result, data, settings)
    result = attach_autonomous_limited_live_activation_rehearsal_block_summary(result, data, settings)
    result = attach_autonomous_real_execution_reconciliation_block_summary(result, data, settings)
    result = attach_autonomous_live_risk_firewall_block_summary(result, data, settings)
    result = attach_autonomous_first_controlled_micro_live_block_summary(result, data, settings)
    result = attach_autonomous_production_data_integrity_block_summary(result, data, settings)
    result = attach_autonomous_live_strategy_reality_validation_block_summary(result, data, settings)
    result = attach_autonomous_opportunity_quality_block_summary(result, data, settings)
    result = attach_autonomous_limited_live_operator_approval_ux_block_summary(result, data, settings)
    result = attach_autonomous_small_capital_controlled_autonomy_candidate_block_summary(result, data, settings)
    result = attach_autonomous_micro_live_execution_dry_proof_block_summary(result, data, settings)
    result = attach_autonomous_small_capital_live_readiness_gate_v2_block_summary(result, data, settings)
    result = attach_autonomous_production_limited_live_candidate_block_summary(result, data, settings)
    result = attach_autonomous_limited_live_final_validation_block_summary(result, data, settings)
    result = attach_autonomous_owner_controlled_activation_layer_block_summary(result, data, settings)
    result = attach_autonomous_small_cap_autonomy_final_validation_block_summary(result, data, settings)
    result = attach_autonomous_live_activation_command_contract_block_summary(result, data, settings)
    result = attach_autonomous_first_micro_live_controlled_execution_path_block_summary(result, data, settings)
    result = attach_autonomous_live_exit_emergency_control_contract_block_summary(result, data, settings)
    result = attach_autonomous_post_live_evidence_decision_freeze_block_summary(result, data, settings)
    result = attach_autonomous_controlled_growth_permission_block_summary(result, data, settings)
    result = attach_autonomous_production_small_cap_live_candidate_v2_block_summary(result, data, settings)
    result = attach_minimal_summary_dashboard(result, data, settings)
    result = attach_portfolio_allocation_summary(result, data, settings)
    try:
        from time import monotonic
        if cache_key is not None:
            _SUMMARY_CACHE["key"] = cache_key
            _SUMMARY_CACHE["payload"] = deepcopy(result)
            _SUMMARY_CACHE["created_at"] = monotonic()
    except Exception:
        pass
    return result

# Rev44 emergency visibility helper kept separate so Summary remains read-only.
def attach_emergency_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.emergency_recovery_service import build_emergency_visibility
        summary["emergency"] = build_emergency_visibility(data, settings)
        summary.setdefault("quality", {})["emergency_close"] = summary["emergency"].get("status", "unknown")
    except Exception as error:
        summary["emergency"] = {"status": "review", "error": str(error), "last_close_status": "unknown"}
        summary.setdefault("quality", {})["emergency_close"] = "review"
    return summary


# Rev45 pilot visibility helper kept separate so Summary remains read-only.
def attach_pilot_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.real_pilot_service import build_pilot_visibility
        summary["pilot"] = build_pilot_visibility(data, settings)
        summary.setdefault("quality", {})["micro_pilot_controller"] = summary["pilot"].get("status", "unknown")
    except Exception as error:
        summary["pilot"] = {"status": "review", "error": str(error), "active": False}
        summary.setdefault("quality", {})["micro_pilot_controller"] = "review"
    return summary


# Rev51 market intelligence visibility helper kept separate so Summary remains read-only.
def attach_market_intelligence_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.coin_market_intelligence_service import build_market_visibility_summary
        visibility = build_market_visibility_summary(data, settings)
        summary["market_intelligence"] = visibility
        cards = visibility.get("summary_cards") or {}
        market = summary.setdefault("market", {})
        market["coin_universe_status"] = visibility.get("status")
        market["total_symbols"] = cards.get("total_symbols", market.get("total_symbols", 0))
        market["candidate_symbols"] = cards.get("candidate_symbols", market.get("candidate_symbols", 0))
        market["no_trade_active"] = cards.get("no_trade_active")
        market["strategy_suppression_count"] = cards.get("suppression_count")
        summary.setdefault("quality", {})["coin_market_intelligence"] = visibility.get("status", "unknown")
    except Exception as error:
        summary["market_intelligence"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["coin_market_intelligence"] = "review"
    return summary

# Rev60 autonomous decision visibility helper kept read-only for minimal Summary control.
def attach_autonomous_decision_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_market_scanner_service import build_summary_autonomous_decision
        decision = build_summary_autonomous_decision(data, settings)
        summary["autonomous_decision"] = decision
        market = summary.setdefault("market", {})
        market["autonomous_market_mode"] = decision.get("market_mode")
        market["autonomous_bot_mode"] = decision.get("bot_mode")
        market["autonomous_confidence"] = decision.get("confidence")
        market["autonomous_best_symbols"] = decision.get("best_symbols") or []
        summary.setdefault("quality", {})["autonomous_market_scanner"] = decision.get("status", "review")
    except Exception as error:
        summary["autonomous_decision"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_market_scanner"] = "review"
    return summary


# Rev62 strategy selection visibility helper kept read-only for minimal Summary control.
def attach_strategy_selection_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.strategy_selection_engine_service import build_summary_strategy_selection
        strategy = build_summary_strategy_selection(data, settings)
        summary["strategy_selection"] = strategy
        market = summary.setdefault("market", {})
        market["autonomous_primary_strategy"] = strategy.get("primary_strategy")
        market["autonomous_primary_symbol"] = strategy.get("primary_symbol")
        market["strategy_decision_text"] = strategy.get("decision_text")
        summary.setdefault("quality", {})["strategy_selection_engine"] = strategy.get("status", "review")
    except Exception as error:
        summary["strategy_selection"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["strategy_selection_engine"] = "review"
    return summary


# Rev63 risk brain visibility helper kept read-only for minimal Summary control.
def attach_risk_brain_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.risk_brain_service import build_summary_risk_brain
        risk_brain = build_summary_risk_brain(data, settings)
        summary["risk_brain"] = risk_brain
        market = summary.setdefault("market", {})
        money = summary.setdefault("money", {})
        market["autonomous_risk_status"] = risk_brain.get("risk_status")
        market["risk_brain_decision_text"] = risk_brain.get("decision_text")
        money["risk_brain_suggested_order_usdt"] = risk_brain.get("suggested_order_usdt")
        money["risk_brain_active_risk_pct"] = risk_brain.get("active_risk_pct")
        summary.setdefault("quality", {})["risk_brain"] = risk_brain.get("status", "review")
    except Exception as error:
        summary["risk_brain"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["risk_brain"] = "review"
    return summary


# Rev64 trade quality feedback visibility helper kept read-only for minimal Summary control.
def attach_trade_quality_feedback_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.trade_quality_feedback_service import build_summary_trade_quality_feedback
        feedback = build_summary_trade_quality_feedback(data, settings)
        summary["trade_quality_feedback"] = feedback
        market = summary.setdefault("market", {})
        market["trade_quality_status"] = feedback.get("quality_status")
        market["trade_quality_score"] = feedback.get("quality_score")
        market["trade_quality_decision_text"] = feedback.get("decision_text")
        summary.setdefault("quality", {})["trade_quality_feedback"] = feedback.get("status", "review")
    except Exception as error:
        summary["trade_quality_feedback"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["trade_quality_feedback"] = "review"
    return summary



# Rev65 daily operation visibility helper kept read-only for minimal Summary control.
def attach_daily_operation_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_daily_operation_service import build_summary_daily_operation
        operation = build_summary_daily_operation(data, settings)
        summary["daily_operation"] = operation
        system = summary.setdefault("system", {})
        money = summary.setdefault("money", {})
        market = summary.setdefault("market", {})
        system["autonomous_daily_mode"] = operation.get("bot_mode")
        system["autonomous_daily_action"] = operation.get("action")
        money["autonomous_today_pnl_usdt"] = operation.get("today_pnl_usdt")
        money["autonomous_suggested_order_usdt"] = operation.get("suggested_order_usdt")
        market["autonomous_daily_decision_text"] = operation.get("decision_text")
        summary.setdefault("quality", {})["autonomous_daily_operation"] = operation.get("status", "review")
    except Exception as error:
        summary["daily_operation"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_daily_operation"] = "review"
    return summary


# Rev66 minimal Summary dashboard helper. This is the owner-facing 3-5 signal surface.

def attach_autonomous_semi_autonomous_real_trading_lane_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_semi_autonomous_real_trading_lane_service import build_summary_autonomous_semi_autonomous_real_trading_lane

        username = str(data.get("username") or settings.get("username") or "default")
        lane = build_summary_autonomous_semi_autonomous_real_trading_lane(data, settings, read_auth_store(), username)
        summary["autonomous_semi_autonomous_real_trading_lane"] = lane
        summary.setdefault("quality", {})["autonomous_semi_autonomous_real_trading_lane"] = lane.get("status", "review")
    except Exception as error:
        summary["autonomous_semi_autonomous_real_trading_lane"] = {"status": "review", "revision": 96, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_semi_autonomous_real_trading_lane"] = "review"
    return summary


def attach_autonomous_fully_autonomous_small_capital_mode_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_fully_autonomous_small_capital_mode_service import build_summary_autonomous_fully_autonomous_small_capital_mode

        username = str(data.get("username") or settings.get("username") or "default")
        mode = build_summary_autonomous_fully_autonomous_small_capital_mode(data, settings, read_auth_store(), username)
        summary["autonomous_fully_autonomous_small_capital_mode"] = mode
        summary.setdefault("quality", {})["autonomous_fully_autonomous_small_capital_mode"] = mode.get("status", "review")
    except Exception as error:
        summary["autonomous_fully_autonomous_small_capital_mode"] = {"status": "review", "revision": 97, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_fully_autonomous_small_capital_mode"] = "review"
    return summary



def attach_autonomous_profit_protection_scaling_rules_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_profit_protection_scaling_rules_service import build_summary_autonomous_profit_protection_scaling_rules

        username = str(data.get("username") or settings.get("username") or "default")
        rules = build_summary_autonomous_profit_protection_scaling_rules(data, settings, read_auth_store(), username)
        summary["autonomous_profit_protection_scaling_rules"] = rules
        summary.setdefault("quality", {})["autonomous_profit_protection_scaling_rules"] = rules.get("status", "review")
    except Exception as error:
        summary["autonomous_profit_protection_scaling_rules"] = {"status": "review", "revision": 98, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_profit_protection_scaling_rules"] = "review"
    return summary


def attach_autonomous_operator_free_dashboard_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_operator_free_dashboard_service import build_summary_autonomous_operator_free_dashboard

        username = str(data.get("username") or settings.get("username") or "default")
        dashboard = build_summary_autonomous_operator_free_dashboard(data, settings, read_auth_store(), username)
        summary["autonomous_operator_free_dashboard"] = dashboard
        summary.setdefault("quality", {})["autonomous_operator_free_dashboard"] = dashboard.get("status", "review")
    except Exception as error:
        summary["autonomous_operator_free_dashboard"] = {"status": "review", "revision": 99, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_operator_free_dashboard"] = "review"
    return summary



def attach_autonomous_production_go_live_candidate_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_production_go_live_candidate_service import build_summary_autonomous_production_go_live_candidate

        username = str(data.get("username") or settings.get("username") or "default")
        candidate = build_summary_autonomous_production_go_live_candidate(data, settings, read_auth_store(), username)
        summary["autonomous_production_go_live_candidate"] = candidate
        summary.setdefault("quality", {})["autonomous_production_go_live_candidate"] = candidate.get("status", "review")
    except Exception as error:
        summary["autonomous_production_go_live_candidate"] = {"status": "review", "revision": 100, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_production_go_live_candidate"] = "review"
    return summary


def attach_autonomous_live_config_governance_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_live_config_governance_service import build_summary_autonomous_live_config_governance

        username = str(data.get("username") or settings.get("username") or "default")
        governance = build_summary_autonomous_live_config_governance(data, settings, read_auth_store(), username)
        summary["autonomous_live_config_governance"] = governance
        summary.setdefault("quality", {})["autonomous_live_config_governance"] = governance.get("status", "review")
    except Exception as error:
        summary["autonomous_live_config_governance"] = {"status": "review", "revision": 101, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_live_config_governance"] = "review"
    return summary


def attach_autonomous_first_micro_real_submit_enable_flag_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_first_micro_real_submit_enable_flag_service import build_summary_autonomous_first_micro_real_submit_enable_flag

        username = str(data.get("username") or settings.get("username") or "default")
        flag = build_summary_autonomous_first_micro_real_submit_enable_flag(data, settings, read_auth_store(), username)
        summary["autonomous_first_micro_real_submit_enable_flag"] = flag
        summary.setdefault("quality", {})["autonomous_first_micro_real_submit_enable_flag"] = flag.get("status", "review")
    except Exception as error:
        summary["autonomous_first_micro_real_submit_enable_flag"] = {"status": "review", "revision": 105, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_first_micro_real_submit_enable_flag"] = "review"
    return summary


def attach_autonomous_real_binance_micro_order_submitter_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_real_binance_micro_order_submitter_service import build_summary_autonomous_real_binance_micro_order_submitter

        username = str(data.get("username") or settings.get("username") or "default")
        submitter = build_summary_autonomous_real_binance_micro_order_submitter(data, settings, read_auth_store(), username)
        summary["autonomous_real_binance_micro_order_submitter"] = submitter
        summary.setdefault("quality", {})["autonomous_real_binance_micro_order_submitter"] = submitter.get("status", "review")
    except Exception as error:
        summary["autonomous_real_binance_micro_order_submitter"] = {"status": "review", "revision": 106, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_real_binance_micro_order_submitter"] = "review"
    return summary


def attach_autonomous_order_status_poller_exchange_response_recorder_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_order_status_poller_exchange_response_recorder_service import build_summary_autonomous_order_status_poller_exchange_response_recorder

        username = str(data.get("username") or settings.get("username") or "default")
        poller = build_summary_autonomous_order_status_poller_exchange_response_recorder(data, settings, read_auth_store(), username)
        summary["autonomous_order_status_poller_exchange_response_recorder"] = poller
        summary.setdefault("quality", {})["autonomous_order_status_poller_exchange_response_recorder"] = poller.get("status", "review")
    except Exception as error:
        summary["autonomous_order_status_poller_exchange_response_recorder"] = {"status": "review", "revision": 107, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_order_status_poller_exchange_response_recorder"] = "review"
    return summary


def attach_autonomous_micro_real_live_ops_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_live_ops_block_service import build_block_payload

        username = str(data.get("username") or settings.get("username") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_live_ops_block"] = {
            "revision": 113,
            "status": block.get("status", "review"),
            "readiness": block.get("readiness"),
            "blockers": block.get("blockers", []),
            "command_preview": block.get("command_preview"),
            "contains_secret": False,
            "secret_values_returned": False,
        }
        for key, payload in (block.get("outputs") or {}).items():
            summary[key] = {
                "revision": payload.get("revision"),
                "status": payload.get("status"),
                "readiness": payload.get("readiness"),
                "check_totals": payload.get("check_totals"),
                "next_allowed_step": payload.get("next_allowed_step"),
                "command_preview": payload.get("command_preview"),
                "contains_secret": False,
                "secret_values_returned": False,
            }
            summary.setdefault("quality", {})[key] = payload.get("status", "review")
        summary.setdefault("quality", {})["autonomous_micro_real_live_ops_block"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_live_ops_block"] = {"status": "review", "revision": 113, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_live_ops_block"] = "review"
    return summary


# Rev114-119 real learning/runtime block visibility helper. Read-only: no order, no network, no runtime write.
def attach_autonomous_real_learning_runtime_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_real_learning_runtime_block_service import build_block_payload
        username = str(summary.get("user") or data.get("username") or settings.get("username") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        summary["autonomous_real_learning_runtime_block"] = {
            "revision": 119,
            "status": block.get("status", "review"),
            "readiness": block.get("readiness"),
            "blockers": block.get("blockers", []),
            "command_preview": block.get("command_preview"),
            "contains_secret": False,
            "secret_values_returned": False,
        }
        for key, payload in (block.get("outputs") or {}).items():
            summary[key] = {
                "revision": payload.get("revision"),
                "status": payload.get("status"),
                "readiness": payload.get("readiness"),
                "decision": payload.get("decision") or payload.get("final_real_lane_action") or payload.get("approval_decision") or payload.get("scaling_action"),
                "check_totals": payload.get("check_totals"),
                "next_allowed_step": payload.get("next_allowed_step"),
                "command_preview": payload.get("command_preview"),
                "contains_secret": False,
                "secret_values_returned": False,
            }
            summary.setdefault("quality", {})[key] = payload.get("status", "review")
        summary.setdefault("quality", {})["autonomous_real_learning_runtime_block"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_real_learning_runtime_block"] = {"status": "review", "revision": 119, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_real_learning_runtime_block"] = "review"
    return summary


# Rev120-125 live production ops block visibility helper. Read-only: no order, no network, no runtime write.
def attach_autonomous_live_production_ops_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_live_production_ops_block_service import build_block_payload
        username = str(summary.get("user") or data.get("username") or settings.get("username") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        final = (block.get("outputs") or {}).get("autonomous_final_live_go_no_go_candidate", {})
        summary["autonomous_live_production_ops_block"] = {
            "revision": 125,
            "status": block.get("status", "review"),
            "readiness": block.get("readiness"),
            "go_no_go": final.get("go_no_go"),
            "blockers": block.get("blockers", []),
            "command_preview": block.get("command_preview"),
            "contains_secret": False,
            "secret_values_returned": False,
        }
        for key, payload in (block.get("outputs") or {}).items():
            summary[key] = {
                "revision": payload.get("revision"),
                "status": payload.get("status"),
                "readiness": payload.get("readiness"),
                "decision": payload.get("decision") or payload.get("risk_action") or payload.get("go_no_go"),
                "check_totals": payload.get("check_totals"),
                "next_allowed_step": payload.get("next_allowed_step"),
                "command_preview": payload.get("command_preview"),
                "contains_secret": False,
                "secret_values_returned": False,
            }
            summary.setdefault("quality", {})[key] = payload.get("status", "review")
        summary.setdefault("quality", {})["autonomous_live_production_ops_block"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_live_production_ops_block"] = {"status": "review", "revision": 125, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_live_production_ops_block"] = "review"
    return summary


# Rev181-185 limited-live activation rehearsal visibility helper. Read-only: no order, no network, no runtime write.
def attach_autonomous_limited_live_activation_rehearsal_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_limited_live_activation_rehearsal_block_service import build_block_payload
        username = str(summary.get("user") or data.get("username") or settings.get("username") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        report = block.get("activation_rehearsal_report") or {}
        visible = report.get("summary_visible") or block.get("summary_result") or {}
        summary["autonomous_limited_live_activation_rehearsal_block"] = {
            "revision": 185,
            "status": block.get("status", "review"),
            "activation": visible.get("activation") or report.get("decision"),
            "blocker": visible.get("blocker") or ((report.get("critical_blocker") or {}).get("name")),
            "operator_action": visible.get("action") or report.get("operator_action"),
            "allowed_max_notional_usdt": report.get("allowed_max_notional_usdt"),
            "allowed_symbols": report.get("allowed_symbols"),
            "live_action_scope": report.get("live_action_scope"),
            "real_submit_close": "OFF",
            "network": "OFF",
            "command_preview": block.get("command_preview"),
            "contains_secret": False,
            "secret_values_returned": False,
        }
        system = summary.setdefault("system", {})
        system["limited_live_activation"] = summary["autonomous_limited_live_activation_rehearsal_block"].get("activation")
        system["limited_live_blocker"] = summary["autonomous_limited_live_activation_rehearsal_block"].get("blocker")
        system["limited_live_operator_action"] = summary["autonomous_limited_live_activation_rehearsal_block"].get("operator_action")
        for key, payload in (block.get("outputs") or {}).items():
            summary[key] = {
                "revision": payload.get("revision"),
                "status": payload.get("status"),
                "decision": (payload.get("activation_preflight") or payload.get("rehearsal_runner") or payload.get("failure_normalizer") or payload.get("owner_approval_audit_contract") or payload.get("activation_rehearsal_report") or {}).get("decision"),
                "check_totals": payload.get("check_totals"),
                "next_allowed_step": payload.get("next_allowed_step"),
                "command_preview": payload.get("command_preview"),
                "contains_secret": False,
                "secret_values_returned": False,
            }
            summary.setdefault("quality", {})[key] = payload.get("status", "review")
        summary.setdefault("quality", {})["autonomous_limited_live_activation_rehearsal_block"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_limited_live_activation_rehearsal_block"] = {"status": "review", "revision": 185, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_limited_live_activation_rehearsal_block"] = "review"
    return summary


# Rev186-190 real execution reconciliation visibility helper. Read-only: no order, no network, no runtime write.
def attach_autonomous_real_execution_reconciliation_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_real_execution_reconciliation_block_service import build_block_payload
        username = str(summary.get("user") or data.get("username") or settings.get("username") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        report = block.get("execution_reconciliation_report") or {}
        visible = report.get("summary_visible") or block.get("summary_result") or {}
        summary["autonomous_real_execution_reconciliation_block"] = {
            "revision": 190,
            "status": block.get("status", "review"),
            "execution": visible.get("execution") or report.get("decision"),
            "critical_issue": visible.get("issue") or ((report.get("critical_issue") or {}).get("code")),
            "operator_action": visible.get("action") or report.get("recommended_action"),
            "consistency_score": report.get("consistency_score"),
            "issue_count": report.get("issue_count"),
            "real_submit_close": "OFF",
            "network": "OFF",
            "command_preview": block.get("command_preview"),
            "contains_secret": False,
            "secret_values_returned": False,
        }
        system = summary.setdefault("system", {})
        system["execution_reconciliation"] = summary["autonomous_real_execution_reconciliation_block"].get("execution")
        system["execution_reconciliation_issue"] = summary["autonomous_real_execution_reconciliation_block"].get("critical_issue")
        system["execution_reconciliation_action"] = summary["autonomous_real_execution_reconciliation_block"].get("operator_action")
        for key, payload in (block.get("outputs") or {}).items():
            summary[key] = {
                "revision": payload.get("revision"),
                "status": payload.get("status"),
                "decision": (payload.get("canonical_order_state") or payload.get("reconciliation") or payload.get("partial_fill_residual_risk") or payload.get("duplicate_stale_order_protection") or payload.get("execution_reconciliation_report") or {}).get("decision"),
                "check_totals": payload.get("check_totals"),
                "next_allowed_step": payload.get("next_allowed_step"),
                "command_preview": payload.get("command_preview"),
                "contains_secret": False,
                "secret_values_returned": False,
            }
            summary.setdefault("quality", {})[key] = payload.get("status", "review")
        summary.setdefault("quality", {})["autonomous_real_execution_reconciliation_block"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_real_execution_reconciliation_block"] = {"status": "review", "revision": 190, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_real_execution_reconciliation_block"] = "review"
    return summary


# Rev191-195 live risk firewall visibility helper. Read-only: no order, no network, no runtime write.
def attach_autonomous_live_risk_firewall_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_live_risk_firewall_block_service import build_block_payload
        username = str(summary.get("user") or data.get("username") or settings.get("username") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        packet = block.get("live_risk_firewall_packet") or {}
        visible = packet.get("summary_visible") or block.get("summary_result") or {}
        summary["autonomous_live_risk_firewall_block"] = {
            "revision": 195,
            "status": block.get("status", "review"),
            "trade_permission": visible.get("trade_permission") or packet.get("decision"),
            "reason": visible.get("reason") or ((packet.get("reason") or {}).get("code")),
            "max_allowed_exposure_usdt": visible.get("max_allowed_exposure_usdt") or packet.get("max_allowed_exposure_usdt"),
            "allowed_symbols": visible.get("allowed_symbols") or packet.get("allowed_symbols"),
            "session_risk_score": visible.get("session_risk_score") or packet.get("session_risk_score"),
            "operator_action": visible.get("operator_action") or packet.get("operator_action"),
            "real_submit_close": "OFF",
            "network": "OFF",
            "command_preview": block.get("command_preview"),
            "contains_secret": False,
            "secret_values_returned": False,
        }
        system = summary.setdefault("system", {})
        system["live_risk_firewall"] = summary["autonomous_live_risk_firewall_block"].get("trade_permission")
        system["live_risk_firewall_reason"] = summary["autonomous_live_risk_firewall_block"].get("reason")
        system["live_risk_firewall_action"] = summary["autonomous_live_risk_firewall_block"].get("operator_action")
        for key, payload in (block.get("outputs") or {}).items():
            body = payload.get("risk_firewall") or payload.get("exposure_guard") or payload.get("profit_lock") or payload.get("loss_ladder") or payload.get("live_risk_firewall_packet") or {}
            summary[key] = {
                "revision": payload.get("revision"),
                "status": payload.get("status"),
                "decision": body.get("decision") or body.get("mode"),
                "check_totals": payload.get("check_totals"),
                "next_allowed_step": payload.get("next_allowed_step"),
                "command_preview": payload.get("command_preview"),
                "contains_secret": False,
                "secret_values_returned": False,
            }
            summary.setdefault("quality", {})[key] = payload.get("status", "review")
        summary.setdefault("quality", {})["autonomous_live_risk_firewall_block"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_live_risk_firewall_block"] = {"status": "review", "revision": 195, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_live_risk_firewall_block"] = "review"
    return summary


def attach_autonomous_first_controlled_micro_live_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_first_controlled_micro_live_block_service import build_block_payload
        username = str(summary.get("user") or data.get("username") or settings.get("username") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        packet = block.get("first_controlled_micro_live_packet") or {}
        visible = packet.get("summary_visible") or block.get("summary_result") or {}
        summary["autonomous_first_controlled_micro_live_block"] = {
            "revision": 200,
            "status": block.get("status", "review"),
            "go_no_go": visible.get("go_no_go") or packet.get("decision"),
            "symbol": visible.get("symbol") or packet.get("symbol"),
            "max_notional_usdt": visible.get("max_notional_usdt") or packet.get("max_notional_usdt"),
            "session_minutes": visible.get("session_minutes") or packet.get("session_minutes"),
            "max_loss_usdt": visible.get("max_loss_usdt") or packet.get("max_loss_usdt"),
            "blocker": visible.get("blocker") or ((packet.get("critical_blocker") or {}).get("code")),
            "owner_action": visible.get("owner_action") or packet.get("owner_action"),
            "real_submit_close": "OFF",
            "network": "OFF",
            "auto_scale": "OFF",
            "auto_apply": "OFF",
            "command_preview": block.get("command_preview"),
            "contains_secret": False,
            "secret_values_returned": False,
        }
        system = summary.setdefault("system", {})
        system["first_micro_live_go_no_go"] = summary["autonomous_first_controlled_micro_live_block"].get("go_no_go")
        system["first_micro_live_blocker"] = summary["autonomous_first_controlled_micro_live_block"].get("blocker")
        system["first_micro_live_owner_action"] = summary["autonomous_first_controlled_micro_live_block"].get("owner_action")
        for key, payload in (block.get("outputs") or {}).items():
            body = payload.get("intent_contract") or payload.get("submit_path") or payload.get("exit_plan_contract") or payload.get("result_capture") or payload.get("first_controlled_micro_live_packet") or {}
            summary[key] = {
                "revision": payload.get("revision"),
                "status": payload.get("status"),
                "decision": body.get("decision") or body.get("submit_allowed") or body.get("symbol"),
                "check_totals": payload.get("check_totals"),
                "next_allowed_step": payload.get("next_allowed_step"),
                "command_preview": payload.get("command_preview"),
                "contains_secret": False,
                "secret_values_returned": False,
            }
            summary.setdefault("quality", {})[key] = payload.get("status", "review")
        summary.setdefault("quality", {})["autonomous_first_controlled_micro_live_block"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_first_controlled_micro_live_block"] = {"status": "review", "revision": 200, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_first_controlled_micro_live_block"] = "review"
    return summary


def attach_autonomous_micro_live_execution_dry_proof_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_micro_live_execution_dry_proof_block_service import build_block_payload
        block = build_block_payload(data, settings)
        summary["autonomous_micro_live_execution_dry_proof_block"] = block
        report = block.get("micro_live_execution_dry_proof_report") or {}
        quality = summary.setdefault("quality", {})
        quality["micro_live_execution_dry_proof"] = block.get("status", "review")
        system = summary.setdefault("system", {})
        system["execution_dry_proof"] = report.get("decision")
        system["execution_dry_proof_action"] = report.get("recommended_action")
    except Exception as error:
        summary["autonomous_micro_live_execution_dry_proof_block"] = {"status": "review", "revision": 255, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["micro_live_execution_dry_proof"] = "review"
    return summary


def attach_autonomous_small_capital_live_readiness_gate_v2_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_small_capital_live_readiness_gate_v2_block_service import build_block_payload
        block = build_block_payload(data, settings)
        summary["autonomous_small_capital_live_readiness_gate_v2_block"] = block
        packet = block.get("small_capital_live_readiness_decision") or {}
        quality = summary.setdefault("quality", {})
        quality["small_capital_live_readiness_gate_v2"] = block.get("status", "review")
        system = summary.setdefault("system", {})
        system["limited_live_readiness_v2"] = packet.get("limited_live")
        system["limited_live_readiness_action"] = packet.get("operator_action")
        system["limited_live_readiness_blocker"] = (packet.get("critical_blocker") or {}).get("code")
    except Exception as error:
        summary["autonomous_small_capital_live_readiness_gate_v2_block"] = {"status": "review", "revision": 260, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["small_capital_live_readiness_gate_v2"] = "review"
    return summary


def attach_autonomous_production_limited_live_candidate_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_production_limited_live_candidate_block_service import build_block_payload
        block = build_block_payload(data, settings)
        summary["autonomous_production_limited_live_candidate_block"] = block
        packet = block.get("production_limited_live_candidate_packet") or {}
        quality = summary.setdefault("quality", {})
        quality["production_limited_live_candidate"] = block.get("status", "review")
        system = summary.setdefault("system", {})
        system["production_limited_live_candidate"] = packet.get("limited_live_candidate")
        system["production_limited_live_candidate_action"] = packet.get("operator_action")
        system["production_limited_live_candidate_blocker"] = (packet.get("critical_blocker") or {}).get("code")
    except Exception as error:
        summary["autonomous_production_limited_live_candidate_block"] = {"status": "review", "revision": 265, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["production_limited_live_candidate"] = "review"
    return summary


def attach_autonomous_limited_live_final_validation_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_limited_live_final_validation_block_service import build_block_payload
        block = build_block_payload(data, settings)
        summary["autonomous_limited_live_final_validation_block"] = block
        report = block.get("limited_live_final_validation_report") or {}
        quality = summary.setdefault("quality", {})
        quality["limited_live_final_validation"] = block.get("status", "review")
        system = summary.setdefault("system", {})
        system["limited_live_final_validation"] = report.get("limited_live_final_validation")
        system["limited_live_final_validation_action"] = report.get("operator_action")
        system["limited_live_final_validation_blocker"] = (report.get("critical_blocker") or {}).get("code")
    except Exception as error:
        summary["autonomous_limited_live_final_validation_block"] = {"status": "review", "revision": 270, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["limited_live_final_validation"] = "review"
    return summary


def attach_autonomous_owner_controlled_activation_layer_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_owner_controlled_activation_layer_block_service import build_block_payload
        block = build_block_payload(data, settings)
        summary["autonomous_owner_controlled_activation_layer_block"] = block
        packet = block.get("owner_controlled_activation_decision_packet") or {}
        quality = summary.setdefault("quality", {})
        quality["owner_controlled_activation"] = block.get("status", "review")
        system = summary.setdefault("system", {})
        system["owner_controlled_activation"] = packet.get("owner_controlled_activation")
        system["owner_controlled_activation_action"] = packet.get("owner_action")
        system["owner_controlled_activation_blocker"] = (packet.get("critical_blocker") or {}).get("code")
    except Exception as error:
        summary["autonomous_owner_controlled_activation_layer_block"] = {"status": "review", "revision": 275, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["owner_controlled_activation"] = "review"
    return summary

def attach_minimal_summary_dashboard(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.minimal_summary_dashboard_service import build_minimal_summary_dashboard
        minimal = build_minimal_summary_dashboard(summary, data, settings)
        summary["minimal_dashboard"] = minimal
        summary.setdefault("quality", {})["minimal_summary_dashboard"] = minimal.get("status", "review")
    except Exception as error:
        summary["minimal_dashboard"] = {"status": "review", "error": str(error), "read_only": True, "minimal": True}
        summary.setdefault("quality", {})["minimal_summary_dashboard"] = "review"
    return summary

# Rev67 user API/secret visibility helper. This is read-only and never returns plaintext secrets.
def attach_user_api_secret_layer_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.user_api_secret_layer_service import build_user_api_secret_summary
        username = str(summary.get("user") or "default")
        layer = build_user_api_secret_summary(read_auth_store(), username)
        summary["user_api_secret_layer"] = layer
        system = summary.setdefault("system", {})
        system["api_connection_configured"] = layer.get("configured")
        system["api_connection_readiness"] = layer.get("readiness")
        summary.setdefault("quality", {})["user_api_secret_layer"] = layer.get("status", "review")
    except Exception as error:
        summary["user_api_secret_layer"] = {"status": "review", "revision": 67, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["user_api_secret_layer"] = "review"
    return summary


# Rev68 execution governor visibility helper. Read-only final gate before autonomous execution.
def attach_execution_governor_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_execution_governor_service import build_summary_execution_governor
        username = str(summary.get("user") or "default")
        governor = build_summary_execution_governor(data, settings, read_auth_store(), username)
        summary["execution_governor"] = governor
        system = summary.setdefault("system", {})
        system["execution_can_execute"] = governor.get("can_execute")
        system["execution_lane"] = governor.get("execution_lane")
        system["execution_state"] = governor.get("execution_state")
        summary.setdefault("quality", {})["autonomous_execution_governor"] = governor.get("status", "review")
    except Exception as error:
        summary["execution_governor"] = {"status": "review", "revision": 68, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_execution_governor"] = "review"
    return summary


# Rev69 adaptive parameter tuner visibility helper. Read-only; proposes bounded tuning only.
def attach_adaptive_parameter_tuner_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.adaptive_parameter_tuner_service import build_summary_adaptive_parameter_tuner
        username = str(summary.get("user") or "default")
        tuner = build_summary_adaptive_parameter_tuner(data, settings, read_auth_store(), username)
        summary["adaptive_parameter_tuner"] = tuner
        system = summary.setdefault("system", {})
        system["adaptive_tuner_apply_mode"] = tuner.get("apply_mode")
        system["adaptive_tuner_proposal_count"] = tuner.get("proposal_count")
        system["adaptive_tuner_decision_text"] = tuner.get("decision_text")
        summary.setdefault("quality", {})["adaptive_parameter_tuner"] = tuner.get("status", "review")
    except Exception as error:
        summary["adaptive_parameter_tuner"] = {"status": "review", "revision": 69, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["adaptive_parameter_tuner"] = "review"
    return summary


# Rev70 autonomous control loop visibility helper. Read-only closed-loop supervisor.
def attach_autonomous_control_loop_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_control_loop_service import build_summary_autonomous_control_loop
        username = str(summary.get("user") or "default")
        loop = build_summary_autonomous_control_loop(data, settings, read_auth_store(), username)
        summary["autonomous_control_loop"] = loop
        system = summary.setdefault("system", {})
        system["autopilot_state"] = loop.get("autopilot_state")
        system["autopilot_next_action"] = loop.get("next_action")
        system["autopilot_can_execute"] = loop.get("can_execute")
        summary.setdefault("quality", {})["autonomous_control_loop"] = loop.get("status", "review")
    except Exception as error:
        summary["autonomous_control_loop"] = {"status": "review", "revision": 70, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_control_loop"] = "review"
    return summary


# Rev71 autonomous safety supervisor visibility helper. Read-only hard kill-switch surface.
def attach_autonomous_safety_supervisor_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_safety_supervisor_service import build_summary_autonomous_safety_supervisor
        username = str(summary.get("user") or "default")
        supervisor = build_summary_autonomous_safety_supervisor(data, settings, read_auth_store(), username)
        summary["autonomous_safety_supervisor"] = supervisor
        system = summary.setdefault("system", {})
        system["safety_state"] = supervisor.get("safety_state")
        system["safety_action"] = supervisor.get("safety_action")
        system["kill_switch_active"] = supervisor.get("kill_switch_active")
        system["safe_mode_required"] = supervisor.get("safe_mode_required")
        summary.setdefault("quality", {})["autonomous_safety_supervisor"] = supervisor.get("status", "review")
    except Exception as error:
        summary["autonomous_safety_supervisor"] = {"status": "review", "revision": 71, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_safety_supervisor"] = "review"
    return summary




# Rev74 autonomous position manager visibility helper. Read-only lifecycle guard.
def attach_autonomous_position_manager_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_position_manager_service import build_summary_autonomous_position_manager
        username = str(summary.get("user") or "default")
        manager = build_summary_autonomous_position_manager(data, settings, read_auth_store(), username)
        summary["autonomous_position_manager"] = manager
        positions = summary.setdefault("positions", {})
        positions["autonomous_lifecycle_state"] = manager.get("lifecycle_state")
        positions["autonomous_primary_action"] = manager.get("primary_action")
        positions["autonomous_protective_actions"] = manager.get("protective_action_count")
        summary.setdefault("quality", {})["autonomous_position_manager"] = manager.get("status", "review")
    except Exception as error:
        summary["autonomous_position_manager"] = {"status": "review", "revision": 74, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_position_manager"] = "review"
    return summary


# Rev73 autonomous capital allocator visibility helper. Read-only capital/reserve guard.
def attach_autonomous_capital_allocator_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_capital_allocator_service import build_summary_autonomous_capital_allocator
        username = str(summary.get("user") or "default")
        capital = build_summary_autonomous_capital_allocator(data, settings, read_auth_store(), username)
        summary["capital_allocator"] = capital
        money = summary.setdefault("money", {})
        money["capital_allocation_state"] = capital.get("allocation_state")
        money["capital_suggested_order_usdt"] = capital.get("suggested_order_usdt")
        money["capital_usdt_reserve_pct"] = capital.get("usdt_reserve_pct")
        money["capital_profit_lock_usdt"] = capital.get("profit_lock_usdt")
        summary.setdefault("quality", {})["autonomous_capital_allocator"] = capital.get("status", "review")
    except Exception as error:
        summary["capital_allocator"] = {"status": "review", "revision": 73, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_capital_allocator"] = "review"
    return summary


# Rev83 autonomous paper result evaluator visibility helper. Read-only paper PnL feedback.
def attach_autonomous_paper_result_evaluator_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_paper_result_evaluator_service import build_summary_autonomous_paper_result_evaluator
        username = str(summary.get("user") or "default")
        evaluator = build_summary_autonomous_paper_result_evaluator(data, settings, read_auth_store(), username)
        summary["autonomous_paper_result_evaluator"] = evaluator
        paper = summary.setdefault("paper", {})
        paper["result_evaluation_state"] = evaluator.get("evaluation_state")
        paper["result_quality_score"] = evaluator.get("paper_result_quality_score")
        paper["net_pnl_usdt"] = evaluator.get("net_pnl_usdt")
        paper["roi_pct"] = evaluator.get("roi_pct")
        paper["next_action"] = evaluator.get("next_action")
        summary.setdefault("quality", {})["autonomous_paper_result_evaluator"] = evaluator.get("status", "review")
    except Exception as error:
        summary["autonomous_paper_result_evaluator"] = {"status": "review", "revision": 83, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_paper_result_evaluator"] = "review"
    return summary


# Rev84 autonomous paper promotion gate visibility helper. Read-only paper-to-micro-real promotion preview.
def attach_autonomous_paper_promotion_gate_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_paper_promotion_gate_service import build_summary_autonomous_paper_promotion_gate
        username = str(summary.get("user") or "default")
        promotion = build_summary_autonomous_paper_promotion_gate(data, settings, read_auth_store(), username)
        summary["autonomous_paper_promotion_gate"] = promotion
        paper = summary.setdefault("paper", {})
        paper["promotion_state"] = promotion.get("promotion_state")
        paper["promotion_score"] = promotion.get("promotion_score")
        paper["promotion_target_lane"] = promotion.get("target_lane")
        paper["promotion_next_action"] = promotion.get("next_action")
        summary.setdefault("quality", {})["autonomous_paper_promotion_gate"] = promotion.get("status", "review")
    except Exception as error:
        summary["autonomous_paper_promotion_gate"] = {"status": "review", "revision": 84, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_paper_promotion_gate"] = "review"
    return summary


# Rev85 autonomous micro-real readiness gate visibility helper. Read-only paper-to-micro-real probation readiness preview.
def attach_autonomous_micro_real_readiness_gate_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_readiness_gate_service import build_summary_autonomous_micro_real_readiness_gate
        username = str(summary.get("user") or "default")
        readiness = build_summary_autonomous_micro_real_readiness_gate(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_readiness_gate"] = readiness
        paper = summary.setdefault("paper", {})
        paper["micro_real_readiness_state"] = readiness.get("readiness_state")
        paper["micro_real_readiness_score"] = readiness.get("readiness_score")
        paper["micro_real_probe_notional_usdt"] = readiness.get("probe_notional_usdt")
        paper["micro_real_next_action"] = readiness.get("next_action")
        summary.setdefault("quality", {})["autonomous_micro_real_readiness_gate"] = readiness.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_readiness_gate"] = {"status": "review", "revision": 85, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_readiness_gate"] = "review"
    return summary


# Rev86 autonomous micro-real probe planner visibility helper. Read-only bounded probe plan preview.
def attach_autonomous_micro_real_probe_planner_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_probe_planner_service import build_summary_autonomous_micro_real_probe_planner
        username = str(summary.get("user") or "default")
        planner = build_summary_autonomous_micro_real_probe_planner(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_probe_planner"] = planner
        paper = summary.setdefault("paper", {})
        paper["micro_real_probe_plan_state"] = planner.get("plan_state")
        paper["micro_real_probe_plan_score"] = planner.get("plan_score")
        paper["micro_real_probe_notional_usdt"] = planner.get("probe_notional_usdt")
        paper["micro_real_probe_max_loss_usdt"] = planner.get("max_probe_loss_usdt")
        paper["micro_real_probe_next_action"] = planner.get("next_action")
        summary.setdefault("quality", {})["autonomous_micro_real_probe_planner"] = planner.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_probe_planner"] = {"status": "review", "revision": 86, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_probe_planner"] = "review"
    return summary


# Rev87 autonomous micro-real approval gate visibility helper. Read-only final approval preview before any execution bridge.
def attach_autonomous_micro_real_approval_gate_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_approval_gate_service import build_summary_autonomous_micro_real_approval_gate
        username = str(summary.get("user") or "default")
        approval = build_summary_autonomous_micro_real_approval_gate(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_approval_gate"] = approval
        paper = summary.setdefault("paper", {})
        paper["micro_real_approval_state"] = approval.get("approval_state")
        paper["micro_real_approval_score"] = approval.get("approval_score")
        paper["micro_real_approved_notional_usdt"] = approval.get("approved_notional_usdt")
        paper["micro_real_approved_max_loss_usdt"] = approval.get("approved_max_loss_usdt")
        paper["micro_real_approval_next_action"] = approval.get("next_action")
        summary.setdefault("quality", {})["autonomous_micro_real_approval_gate"] = approval.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_approval_gate"] = {"status": "review", "revision": 87, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_approval_gate"] = "review"
    return summary


# Rev88 autonomous micro-real execution sandbox visibility helper. Dry-run/live-ready bridge; no direct exchange call.
def attach_autonomous_micro_real_execution_sandbox_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_execution_sandbox_service import build_summary_autonomous_micro_real_execution_sandbox
        username = str(summary.get("user") or "default")
        sandbox = build_summary_autonomous_micro_real_execution_sandbox(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_execution_sandbox"] = sandbox
        paper = summary.setdefault("paper", {})
        paper["micro_real_execution_sandbox_state"] = sandbox.get("sandbox_state")
        paper["micro_real_execution_sandbox_score"] = sandbox.get("sandbox_score")
        paper["micro_real_execution_sandbox_dry_run"] = sandbox.get("dry_run")
        paper["micro_real_execution_sandbox_notional_usdt"] = sandbox.get("notional_usdt")
        paper["micro_real_execution_sandbox_next_action"] = sandbox.get("next_action")
        summary.setdefault("quality", {})["autonomous_micro_real_execution_sandbox"] = sandbox.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_execution_sandbox"] = {"status": "review", "revision": 88, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_execution_sandbox"] = "review"
    return summary


# Rev89 autonomous micro-real exchange adapter hardening visibility helper. Binance adapter contract; no network call.
def attach_autonomous_micro_real_exchange_adapter_hardening_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_exchange_adapter_hardening_service import build_summary_autonomous_micro_real_exchange_adapter_hardening
        username = str(summary.get("user") or "default")
        adapter = build_summary_autonomous_micro_real_exchange_adapter_hardening(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_exchange_adapter_hardening"] = adapter
        paper = summary.setdefault("paper", {})
        paper["micro_real_exchange_adapter_state"] = adapter.get("adapter_state")
        paper["micro_real_exchange_adapter_score"] = adapter.get("adapter_score")
        paper["micro_real_exchange_adapter_target_lane"] = adapter.get("target_lane")
        paper["micro_real_exchange_adapter_next_action"] = adapter.get("next_action")
        summary.setdefault("quality", {})["autonomous_micro_real_exchange_adapter_hardening"] = adapter.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_exchange_adapter_hardening"] = {"status": "review", "revision": 89, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_exchange_adapter_hardening"] = "review"
    return summary

# Rev90 autonomous micro-real order submitter preview visibility helper. Final submitter contract; default OFF.
def attach_autonomous_micro_real_order_submitter_preview_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_order_submitter_preview_service import build_summary_autonomous_micro_real_order_submitter_preview
        username = str(summary.get("user") or "default")
        submitter = build_summary_autonomous_micro_real_order_submitter_preview(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_order_submitter_preview"] = submitter
        paper = summary.setdefault("paper", {})
        paper["micro_real_order_submitter_state"] = submitter.get("submitter_state")
        paper["micro_real_order_submitter_score"] = submitter.get("submitter_score")
        paper["micro_real_order_submitter_next_action"] = submitter.get("next_action")
        summary.setdefault("quality", {})["autonomous_micro_real_order_submitter_preview"] = submitter.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_order_submitter_preview"] = {"status": "review", "revision": 90, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_order_submitter_preview"] = "review"
    return summary


# Rev91 first controlled micro-real execution visibility helper. Direct submit remains gated.
def attach_autonomous_first_micro_real_controlled_execution_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_first_micro_real_controlled_execution_service import build_summary_autonomous_first_micro_real_controlled_execution
        username = str(summary.get("user") or "default")
        execution = build_summary_autonomous_first_micro_real_controlled_execution(data, settings, read_auth_store(), username)
        summary["autonomous_first_micro_real_controlled_execution"] = execution
        paper = summary.setdefault("paper", {})
        paper["first_micro_real_execution_state"] = execution.get("execution_state")
        paper["first_micro_real_execution_score"] = execution.get("execution_score")
        paper["first_micro_real_next_action"] = execution.get("next_action")
        paper["first_micro_real_live_submit_ready"] = execution.get("live_submit_ready")
        summary.setdefault("quality", {})["autonomous_first_micro_real_controlled_execution"] = execution.get("status", "review")
    except Exception as error:
        summary["autonomous_first_micro_real_controlled_execution"] = {"status": "review", "revision": 91, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_first_micro_real_controlled_execution"] = "review"
    return summary


# Rev92 micro-real position tracker visibility helper. Tracks state/PnL only; no close or exchange calls.
def attach_autonomous_micro_real_position_tracker_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_position_tracker_service import build_summary_autonomous_micro_real_position_tracker
        username = str(summary.get("user") or "default")
        tracker = build_summary_autonomous_micro_real_position_tracker(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_position_tracker"] = tracker
        paper = summary.setdefault("paper", {})
        paper["micro_real_position_tracker_state"] = tracker.get("tracker_state")
        paper["micro_real_position_tracker_score"] = tracker.get("tracker_score")
        paper["micro_real_position_status"] = tracker.get("position_status")
        paper["micro_real_position_unrealized_pnl_usdt"] = tracker.get("unrealized_pnl_usdt")
        paper["micro_real_position_next_action"] = tracker.get("next_action")
        summary.setdefault("quality", {})["autonomous_micro_real_position_tracker"] = tracker.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_position_tracker"] = {"status": "review", "revision": 92, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_position_tracker"] = "review"
    return summary


# Rev93 micro-real exit manager visibility helper. Builds exit preview/approval only; no close or exchange calls.
def attach_autonomous_micro_real_exit_manager_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_exit_manager_service import build_summary_autonomous_micro_real_exit_manager
        username = str(summary.get("user") or "default")
        exit_manager = build_summary_autonomous_micro_real_exit_manager(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_exit_manager"] = exit_manager
        paper = summary.setdefault("paper", {})
        paper["micro_real_exit_manager_state"] = exit_manager.get("manager_state")
        paper["micro_real_exit_manager_score"] = exit_manager.get("manager_score")
        paper["micro_real_exit_reason"] = exit_manager.get("exit_reason")
        paper["micro_real_exit_next_action"] = exit_manager.get("next_action")
        paper["micro_real_exit_ready_for_explicit_close"] = exit_manager.get("ready_for_explicit_close")
        summary.setdefault("quality", {})["autonomous_micro_real_exit_manager"] = exit_manager.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_exit_manager"] = {"status": "review", "revision": 93, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_exit_manager"] = "review"
    return summary


# Rev94 micro-real result evaluator visibility helper. Evaluates realized result/cost/learning only; no order, network or runtime write.
def attach_autonomous_micro_real_result_evaluator_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_result_evaluator_service import build_summary_autonomous_micro_real_result_evaluator
        username = str(summary.get("user") or "default")
        evaluator = build_summary_autonomous_micro_real_result_evaluator(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_result_evaluator"] = evaluator
        paper = summary.setdefault("paper", {})
        paper["micro_real_result_evaluator_state"] = evaluator.get("evaluator_state")
        paper["micro_real_result_quality_score"] = evaluator.get("result_quality_score")
        paper["micro_real_result_net_pnl_usdt"] = evaluator.get("net_pnl_usdt")
        paper["micro_real_result_roi_pct"] = evaluator.get("realized_roi_pct")
        paper["micro_real_result_next_action"] = evaluator.get("next_action")
        paper["micro_real_promotion_review"] = evaluator.get("allow_promotion_review")
        summary.setdefault("quality", {})["autonomous_micro_real_result_evaluator"] = evaluator.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_result_evaluator"] = {"status": "review", "revision": 94, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_result_evaluator"] = "review"
    return summary

# Rev95 micro-real promotion/demotion controller visibility helper. Produces increase/hold/reduce/stop only; no order, network or runtime write.
def attach_autonomous_micro_real_promotion_demotion_controller_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_micro_real_promotion_demotion_controller_service import build_summary_autonomous_micro_real_promotion_demotion_controller
        username = str(summary.get("user") or "default")
        controller = build_summary_autonomous_micro_real_promotion_demotion_controller(data, settings, read_auth_store(), username)
        summary["autonomous_micro_real_promotion_demotion_controller"] = controller
        paper = summary.setdefault("paper", {})
        paper["micro_real_scale_controller_state"] = controller.get("controller_state")
        paper["micro_real_scale_decision"] = controller.get("decision")
        paper["micro_real_scale_target_notional_usdt"] = controller.get("target_notional_usdt")
        paper["micro_real_scale_next_action"] = controller.get("next_action")
        paper["micro_real_scale_cooldown_minutes"] = controller.get("cooldown_minutes")
        summary.setdefault("quality", {})["autonomous_micro_real_promotion_demotion_controller"] = controller.get("status", "review")
    except Exception as error:
        summary["autonomous_micro_real_promotion_demotion_controller"] = {"status": "review", "revision": 95, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["autonomous_micro_real_promotion_demotion_controller"] = "review"
    return summary


# Rev226-230 production data integrity visibility helper. Read-only; no network, submit, close or runtime write.
def attach_autonomous_production_data_integrity_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_production_data_integrity_block_service import build_block_payload
        username = str(summary.get("user") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        summary["autonomous_production_data_integrity_block"] = block
        packet = block.get("production_data_integrity_report") or {}
        quality = summary.setdefault("quality", {})
        quality["production_data_integrity"] = block.get("status", "review")
        quality["production_data_integrity_ready"] = packet.get("data_integrity_ready", False)
        quality["production_data_integrity_action"] = packet.get("operator_action")
    except Exception as error:
        summary["autonomous_production_data_integrity_block"] = {"status": "review", "revision": 230, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["production_data_integrity"] = "review"
    return summary


# Rev231-235 live strategy reality validation visibility helper. Read-only; no network, submit, close or runtime write.
def attach_autonomous_live_strategy_reality_validation_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_live_strategy_reality_validation_block_service import build_block_payload
        username = str(summary.get("user") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        summary["autonomous_live_strategy_reality_validation_block"] = block
        packet = block.get("live_strategy_reality_report") or {}
        quality = summary.setdefault("quality", {})
        quality["live_strategy_reality_validation"] = block.get("status", "review")
        quality["live_strategy_ready"] = packet.get("strategy_live_ready", False)
        quality["live_strategy_action"] = packet.get("operator_action")
    except Exception as error:
        summary["autonomous_live_strategy_reality_validation_block"] = {"status": "review", "revision": 235, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["live_strategy_reality_validation"] = "review"
    return summary


# Rev241-245 autonomous opportunity quality visibility helper. Read-only; no network, submit, close or runtime write.
def attach_autonomous_opportunity_quality_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_opportunity_quality_block_service import build_block_payload
        username = str(summary.get("user") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        summary["autonomous_opportunity_quality_block"] = block
        packet = block.get("autonomous_opportunity_quality_report") or {}
        quality = summary.setdefault("quality", {})
        quality["opportunity_quality"] = block.get("status", "review")
        quality["opportunity_quality_ready"] = packet.get("opportunity_quality_ready", False)
        quality["opportunity_quality_action"] = packet.get("operator_action")
    except Exception as error:
        summary["autonomous_opportunity_quality_block"] = {"status": "review", "revision": 245, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["opportunity_quality"] = "review"
    return summary


# Rev246-250 limited-live operator approval UX visibility helper. Read-only; no network, submit, close or runtime write.
def attach_autonomous_limited_live_operator_approval_ux_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_limited_live_operator_approval_ux_block_service import build_block_payload
        username = str(summary.get("user") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        summary["autonomous_limited_live_operator_approval_ux_block"] = block
        packet = block.get("limited_live_operator_ux_packet") or {}
        quality = summary.setdefault("quality", {})
        quality["limited_live_operator_approval_ux"] = block.get("status", "review")
        quality["limited_live_owner_action"] = packet.get("owner_action")
        quality["limited_live_visual_state"] = packet.get("visual_state")
    except Exception as error:
        summary["autonomous_limited_live_operator_approval_ux_block"] = {"status": "review", "revision": 250, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["limited_live_operator_approval_ux"] = "review"
    return summary


# Rev296-300 small capital controlled autonomy candidate visibility helper. Read-only; no network, submit, close, auto-scale or auto-apply.
def attach_autonomous_small_capital_controlled_autonomy_candidate_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from core.auth import read_auth_store
        from services.autonomous_small_capital_controlled_autonomy_candidate_block_service import build_block_payload
        username = str(summary.get("user") or "default")
        block = build_block_payload(data, settings, read_auth_store(), username)
        summary["autonomous_small_capital_controlled_autonomy_candidate_block"] = block
        packet = block.get("small_capital_controlled_autonomy_candidate_packet") or {}
        compact = {
            "candidate": packet.get("small_capital_controlled_autonomy_candidate"),
            "max_notional_usdt": packet.get("max_notional_usdt"),
            "max_daily_loss_usdt": packet.get("max_daily_loss_usdt"),
            "allowed_symbols": packet.get("allowed_symbols"),
            "operator_action": packet.get("operator_action"),
            "real_submit_close": "OFF",
            "network": "OFF",
            "auto_scale": "OFF",
            "auto_apply": "OFF",
        }
        summary["small_capital_controlled_autonomy_candidate"] = compact
        quality = summary.setdefault("quality", {})
        quality["small_capital_controlled_autonomy_candidate"] = block.get("status", "review")
        quality["small_cap_autonomy_operator_action"] = compact.get("operator_action")
    except Exception as error:
        summary["autonomous_small_capital_controlled_autonomy_candidate_block"] = {"status": "review", "revision": 300, "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["small_capital_controlled_autonomy_candidate"] = "review"
    return summary


# Rev336-370 generated summary helpers

def attach_autonomous_small_cap_autonomy_final_validation_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_small_cap_autonomy_final_validation_block_service import build_summary_for_revision
        block = build_summary_for_revision(340, data, settings, {}, "default")
        summary["autonomous_small_cap_autonomy_final_validation_block"] = block
        summary.setdefault("minimal", {})["small_cap_autonomy_final_validation"] = block.get("decision") or block.get("status")
        summary.setdefault("quality", {})["small_cap_autonomy_final_validation"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_small_cap_autonomy_final_validation_block"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["small_cap_autonomy_final_validation"] = "review"
    return summary

def attach_autonomous_live_activation_command_contract_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_live_activation_command_contract_block_service import build_summary_for_revision
        block = build_summary_for_revision(345, data, settings, {}, "default")
        summary["autonomous_live_activation_command_contract_block"] = block
        summary.setdefault("minimal", {})["live_activation_command_contract"] = block.get("decision") or block.get("status")
        summary.setdefault("quality", {})["live_activation_command_contract"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_live_activation_command_contract_block"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["live_activation_command_contract"] = "review"
    return summary

def attach_autonomous_first_micro_live_controlled_execution_path_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_first_micro_live_controlled_execution_path_block_service import build_summary_for_revision
        block = build_summary_for_revision(350, data, settings, {}, "default")
        summary["autonomous_first_micro_live_controlled_execution_path_block"] = block
        summary.setdefault("minimal", {})["first_micro_live_controlled_execution_path"] = block.get("decision") or block.get("status")
        summary.setdefault("quality", {})["first_micro_live_controlled_execution_path"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_first_micro_live_controlled_execution_path_block"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["first_micro_live_controlled_execution_path"] = "review"
    return summary

def attach_autonomous_live_exit_emergency_control_contract_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_live_exit_emergency_control_contract_block_service import build_summary_for_revision
        block = build_summary_for_revision(355, data, settings, {}, "default")
        summary["autonomous_live_exit_emergency_control_contract_block"] = block
        summary.setdefault("minimal", {})["live_exit_emergency_control_contract"] = block.get("decision") or block.get("status")
        summary.setdefault("quality", {})["live_exit_emergency_control_contract"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_live_exit_emergency_control_contract_block"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["live_exit_emergency_control_contract"] = "review"
    return summary

def attach_autonomous_post_live_evidence_decision_freeze_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_post_live_evidence_decision_freeze_block_service import build_summary_for_revision
        block = build_summary_for_revision(360, data, settings, {}, "default")
        summary["autonomous_post_live_evidence_decision_freeze_block"] = block
        summary.setdefault("minimal", {})["post_live_evidence_decision_freeze"] = block.get("decision") or block.get("status")
        summary.setdefault("quality", {})["post_live_evidence_decision_freeze"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_post_live_evidence_decision_freeze_block"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["post_live_evidence_decision_freeze"] = "review"
    return summary

def attach_autonomous_controlled_growth_permission_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_controlled_growth_permission_block_service import build_summary_for_revision
        block = build_summary_for_revision(365, data, settings, {}, "default")
        summary["autonomous_controlled_growth_permission_block"] = block
        summary.setdefault("minimal", {})["controlled_growth_permission"] = block.get("decision") or block.get("status")
        summary.setdefault("quality", {})["controlled_growth_permission"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_controlled_growth_permission_block"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["controlled_growth_permission"] = "review"
    return summary

def attach_autonomous_production_small_cap_live_candidate_v2_block_summary(summary: dict, data: dict, settings: dict) -> dict:
    try:
        from services.autonomous_production_small_cap_live_candidate_v2_block_service import build_summary_for_revision
        block = build_summary_for_revision(370, data, settings, {}, "default")
        summary["autonomous_production_small_cap_live_candidate_v2_block"] = block
        summary.setdefault("minimal", {})["production_small_cap_live_candidate_v2"] = block.get("decision") or block.get("status")
        summary.setdefault("quality", {})["production_small_cap_live_candidate_v2"] = block.get("status", "review")
    except Exception as error:
        summary["autonomous_production_small_cap_live_candidate_v2_block"] = {"status": "review", "error": str(error), "read_only": True}
        summary.setdefault("quality", {})["production_small_cap_live_candidate_v2"] = "review"
    return summary
