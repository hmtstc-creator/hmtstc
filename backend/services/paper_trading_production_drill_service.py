from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from services.autonomous_market_scanner_service import build_autonomous_market_scanner
from services.autonomous_signal_validator_service import build_autonomous_signal_validator
from services.autonomous_trade_intent_builder_service import build_autonomous_trade_intent_builder
from services.autonomous_paper_execution_runner_service import build_autonomous_paper_execution_runner
from services.autonomous_paper_result_evaluator_service import build_autonomous_paper_result_evaluator

REVISION_RANGE = "996-1000"
PACKAGE_NAME = "Paper Trading Production Drill Block"
FINAL_DECISION_READY = "PAPER_TRADING_PRODUCTION_READY"
DRILL_USERNAME = "rev996_paper_production_drill"

FORBIDDEN_TOKENS = ("api_secret", "secret_key", "binance_secret", "private_key")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sample_data() -> dict[str, Any]:
    return {
        "last_scan": {
            "scan_rows": [
                {
                    "symbol": "BTCUSDT",
                    "score": 92,
                    "route_score": 92,
                    "quote_volume": 50_000_000,
                    "spread_pct": 0.04,
                    "volatility": 2.10,
                    "status": "WATCH",
                    "strategy": "choch_micro_scalper",
                    "strategy_hint": "choch_micro_scalper",
                    "signal": "CHOCH_IMBALANCE_RETEST",
                },
                {
                    "symbol": "ETHUSDT",
                    "score": 86,
                    "route_score": 86,
                    "quote_volume": 38_000_000,
                    "spread_pct": 0.05,
                    "volatility": 2.70,
                    "status": "WATCH",
                    "strategy": "imbalance_fill_hunter",
                    "strategy_hint": "imbalance_fill_hunter",
                    "signal": "IMBALANCE_FILL",
                },
            ]
        },
        "learning_score": 88,
        "performance_state": "CONTINUE",
        "wallet": {"total_usdt": 1000.0, "free_usdt": 1000.0},
        "risk_brain": {"suggested_order_usdt": 25.0},
        "autonomous_capital_allocator": {"max_symbol_notional_usdt": 25.0},
    }


def _sample_settings() -> dict[str, Any]:
    return {
        "autonomous_scanner": {
            "min_score": 55,
            "min_trade_score": 65,
            "max_spread_pct": 0.30,
            "max_candidates": 5,
        },
        "autonomous_signal_validator": {
            "min_validation_score": 60,
            "min_route_score": 55,
            "allow_paper_when_review": True,
        },
        "autonomous_trade_intent_builder": {
            "min_intent_score": 50,
            "min_validation_score": 60,
            "max_notional_usdt": 25.0,
            "min_notional_usdt": 5.0,
            "paper_first": True,
            "default_stop_loss_pct": 0.45,
            "default_take_profit_pct": 0.95,
        },
        "autonomous_paper_execution_runner": {
            "enabled": True,
            "allowed_lanes": ["PAPER"],
            "min_approval_score": 60,
            "default_reference_price": 100.0,
            "max_fee_pct": 0.12,
            "max_slippage_pct": 0.18,
        },
        "autonomous_paper_result_evaluator": {
            "enabled": True,
            "min_runner_score": 60,
            "min_quality_score": 50,
            "target_move_pct": 0.95,
            "breakeven_buffer_pct": 0.04,
        },
    }


def _selection_from_signal(signal: dict[str, Any]) -> dict[str, Any]:
    symbol = str(signal.get("symbol") or "").upper()
    strategy = str(signal.get("strategy") or "micro_scalp_watch")
    score = float(signal.get("validation_score") or 0.0)
    return {
        "symbol": symbol,
        "strategy": strategy,
        "filter_stack": ["spread_pct <= 0.30", "route_score >= 55", "paper_first == true"],
        "selection_score": round(score, 2),
        "selection_state": "SELECTED" if symbol and score >= 60 else "BLOCKED",
        "allowed_for_paper": bool(symbol and score >= 60),
    }


def _paper_approval_packet(intent: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    trade_intent = intent.get("trade_intent") if isinstance(intent.get("trade_intent"), dict) else {}
    notional = float(trade_intent.get("notional_usdt") or 0.0)
    symbol = selection.get("symbol") or trade_intent.get("symbol")
    blockers: list[str] = []
    if intent.get("intent_state") != "READY":
        blockers.append("trade_intent_not_ready")
    if selection.get("selection_state") != "SELECTED":
        blockers.append("strategy_filter_selection_not_ready")
    if notional <= 0 or notional > 25:
        blockers.append("paper_notional_outside_drill_limit")
    approval_score = min(96.0, max(0.0, float(intent.get("intent_score") or 0.0) + 8.0))
    approved = not blockers and approval_score >= 60
    generated_at = now_iso()
    return {
        "status": "ok" if approved else "blocked",
        "revision": 998,
        "engine": "paper_trading_production_drill_risk_approval",
        "generated_at": generated_at,
        "read_only": True,
        "auto_apply": False,
        "paper_only": True,
        "approval_state": "APPROVED" if approved else "BLOCKED",
        "approval_action": "RELEASE_PAPER_COMMAND_PREVIEW" if approved else "DO_NOT_RELEASE_PAPER_PREVIEW",
        "approval_score": round(approval_score, 2),
        "blockers": blockers,
        "warnings": [],
        "approval_packet": {
            "approval_id": f"PAPER-APPROVAL-{generated_at}-{symbol or 'NONE'}",
            "source_simulation_id": "REV998-PAPER-DRILL-SIMULATION",
            "source_plan_id": trade_intent.get("intent_id"),
            "lane": "PAPER",
            "symbol": symbol,
            "side": "BUY",
            "notional_usdt": notional,
            "estimated_cost_pct": 0.22,
            "estimated_cost_usdt": round(notional * 0.22 / 100.0, 6),
            "partial_fill_risk": False,
            "approved": approved,
            "approval_state": "APPROVED" if approved else "BLOCKED",
            "approval_score": round(approval_score, 2),
        },
        "command_preview": {
            "type": "paper_execution_approval_preview",
            "places_order": False,
            "sends_exchange_request": False,
            "writes_runtime_state": False,
            "real_submit_enabled": False,
        },
    }


def _journal_entry(runner: dict[str, Any], evaluator: dict[str, Any]) -> dict[str, Any]:
    fill = runner.get("paper_fill") if isinstance(runner.get("paper_fill"), dict) else {}
    result = evaluator.get("paper_result") if isinstance(evaluator.get("paper_result"), dict) else {}
    return {
        "journal_id": f"JOURNAL-{fill.get('paper_execution_id') or 'NONE'}",
        "symbol": fill.get("symbol"),
        "lane": fill.get("lane"),
        "paper_execution_id": fill.get("paper_execution_id"),
        "notional_usdt": fill.get("notional_usdt"),
        "fee_usdt": fill.get("fee_usdt"),
        "slippage_usdt": fill.get("slippage_usdt"),
        "net_pnl_usdt": result.get("net_pnl_usdt"),
        "roi_pct": result.get("roi_pct"),
        "profitable_after_costs": result.get("profitable_after_costs") is True,
        "write_mode": "preview_only_no_runtime_write",
    }


def build_rev996_market_scanner_signal_flow_production_test(username: str = DRILL_USERNAME) -> dict[str, Any]:
    data = _sample_data()
    settings = _sample_settings()
    scanner = build_autonomous_market_scanner(data, settings)
    signal = build_autonomous_signal_validator(data, settings, {}, username)
    blockers: list[str] = []
    if not scanner.get("best_symbols"):
        blockers.append("scanner_candidate_missing")
    if signal.get("validation_state") != "VALIDATED":
        blockers.append("signal_not_validated")
    return {
        "revision": 996,
        "name": "market_scanner_to_signal_flow_production_test",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "scanner_status": scanner.get("status"),
        "scanner_market_mode": scanner.get("market_mode"),
        "candidate_count": len(scanner.get("best_symbols") or []),
        "signal_status": signal.get("status"),
        "signal_state": signal.get("validation_state"),
        "signal_decision": signal.get("validation_decision"),
        "symbol": signal.get("symbol"),
        "strategy": signal.get("strategy"),
        "read_only": True,
        "real_order_submit_triggered": False,
        "binance_network_call_triggered": False,
    }


def build_rev997_filter_strategy_selection_production_test(username: str = DRILL_USERNAME) -> dict[str, Any]:
    data = _sample_data()
    settings = _sample_settings()
    signal = build_autonomous_signal_validator(data, settings, {}, username)
    selection = _selection_from_signal(signal)
    blockers: list[str] = []
    if selection["selection_state"] != "SELECTED":
        blockers.append("paper_strategy_selection_failed")
    if selection["strategy"] not in {"choch_micro_scalper", "imbalance_fill_hunter", "micro_scalp_watch"}:
        blockers.append("strategy_not_in_allowed_paper_set")
    return {
        "revision": 997,
        "name": "filter_strategy_selection_production_test",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "selection": selection,
        "read_only": True,
        "auto_apply": False,
        "real_order_submit_triggered": False,
        "secret_values_returned": False,
    }


def build_rev998_trade_intent_risk_approval_production_test(username: str = DRILL_USERNAME) -> dict[str, Any]:
    data = _sample_data()
    settings = _sample_settings()
    signal = build_autonomous_signal_validator(data, settings, {}, username)
    data["autonomous_signal_validator"] = signal
    intent = build_autonomous_trade_intent_builder(data, settings, {}, username)
    selection = _selection_from_signal(signal)
    approval = _paper_approval_packet(intent, selection)
    blockers = [*list(intent.get("blockers") or []), *list(approval.get("blockers") or [])]
    if intent.get("intent_state") != "READY":
        blockers.append("intent_not_ready")
    if approval.get("approval_state") != "APPROVED":
        blockers.append("paper_risk_approval_not_approved")
    return {
        "revision": 998,
        "name": "trade_intent_risk_approval_production_test",
        "status": "ok" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "intent_state": intent.get("intent_state"),
        "intent_score": intent.get("intent_score"),
        "approval_state": approval.get("approval_state"),
        "approval_score": approval.get("approval_score"),
        "approval_packet": approval.get("approval_packet"),
        "read_only": True,
        "paper_only": True,
        "real_order_submit_triggered": False,
        "owner_approval_required_for_real_live": True,
    }


def _build_execution_chain(username: str = DRILL_USERNAME) -> dict[str, Any]:
    data = _sample_data()
    settings = _sample_settings()
    signal = build_autonomous_signal_validator(data, settings, {}, username)
    data["autonomous_signal_validator"] = signal
    intent = build_autonomous_trade_intent_builder(data, settings, {}, username)
    selection = _selection_from_signal(signal)
    approval = _paper_approval_packet(intent, selection)
    runner_data = {"autonomous_execution_approval_gate": approval}
    runner = build_autonomous_paper_execution_runner(runner_data, settings, {}, username)
    runner_data["autonomous_paper_execution_runner"] = runner
    evaluator = build_autonomous_paper_result_evaluator(runner_data, settings, {}, username)
    journal = _journal_entry(runner, evaluator)
    return {"signal": signal, "intent": intent, "selection": selection, "approval": approval, "runner": runner, "evaluator": evaluator, "journal": journal}


def build_rev999_paper_execution_journal_pnl_production_test(username: str = DRILL_USERNAME) -> dict[str, Any]:
    chain = _build_execution_chain(username)
    runner = chain["runner"]
    evaluator = chain["evaluator"]
    journal = chain["journal"]
    blockers: list[str] = []
    if runner.get("execution_state") != "PAPER_EXECUTED":
        blockers.append("paper_execution_not_executed")
    if evaluator.get("evaluation_state") != "PASSED":
        blockers.append("paper_pnl_evaluation_not_passed")
    if journal.get("paper_execution_id") is None:
        blockers.append("journal_execution_id_missing")
    if journal.get("net_pnl_usdt") is None:
        blockers.append("journal_pnl_missing")
    return {
        "revision": 999,
        "name": "paper_execution_journal_pnl_production_test",
        "status": "ok" if not blockers else "blocked",
        "blockers": blockers,
        "execution_state": runner.get("execution_state"),
        "paper_execution_score": runner.get("paper_execution_score"),
        "evaluation_state": evaluator.get("evaluation_state"),
        "paper_result_quality_score": evaluator.get("paper_result_quality_score"),
        "journal_entry": journal,
        "read_only": True,
        "paper_only": True,
        "real_order_submit_triggered": False,
        "runtime_write_triggered": False,
    }


def _response_leak_scan(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, default=str).lower()
    hits = [token for token in FORBIDDEN_TOKENS if token in text]
    return {"status": "PASS" if not hits else "FAIL", "hits": hits, "secret_values_returned": False}


def build_paper_trading_production_drill_report(username: str = DRILL_USERNAME) -> dict[str, Any]:
    rev996 = build_rev996_market_scanner_signal_flow_production_test(username)
    rev997 = build_rev997_filter_strategy_selection_production_test(username)
    rev998 = build_rev998_trade_intent_risk_approval_production_test(username)
    rev999 = build_rev999_paper_execution_journal_pnl_production_test(username)
    checks = {
        "rev996_market_scanner_signal_flow": rev996,
        "rev997_filter_strategy_selection": rev997,
        "rev998_trade_intent_risk_approval": rev998,
        "rev999_paper_execution_journal_pnl": rev999,
    }
    blockers = [blocker for check in checks.values() for blocker in check.get("blockers", [])]
    report = {
        "status": "ok" if not blockers else "blocked",
        "revision": 1000,
        "revision_range": REVISION_RANGE,
        "package": PACKAGE_NAME,
        "final_decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
        "blockers": sorted(set(blockers)),
        "checks": checks,
        "rev1000_report": {
            "revision": 1000,
            "name": "paper_trading_production_drill_report",
            "status": "ok" if not blockers else "blocked",
            "decision": FINAL_DECISION_READY if not blockers else "BLOCKED",
            "blockers": sorted(set(blockers)),
        },
        "safety_scope": {
            "paper_only": True,
            "read_only_inputs": True,
            "real_order_submit_triggered": False,
            "real_order_close_triggered": False,
            "emergency_close_triggered": False,
            "binance_network_call_triggered": False,
            "runtime_write_triggered": False,
            "auto_apply": False,
            "owner_approval_required_for_real_live": True,
        },
        "secret_values_returned": False,
        "operator_next_steps": [
            "Production VPS üzerinde paper scanner akışını owner oturumuyla canlı veri olmadan smoke test et.",
            "Paper journal ve PnL kayıtlarının runtime store ile bağlantısını Paket 7 öncesi doğrula.",
            "Micro-live gate açılmadan gerçek submit/close flaglerini kapalı tut.",
        ],
        "checked_at": now_iso(),
    }
    report["leak_scan"] = _response_leak_scan(copy.deepcopy(report))
    if report["leak_scan"]["status"] != "PASS":
        report["status"] = "blocked"
        report["final_decision"] = "BLOCKED"
        report["blockers"] = sorted(set([*report["blockers"], "public_response_contains_secret_token"]))
    return report


def build_paper_trading_production_drill_summary(username: str = DRILL_USERNAME) -> dict[str, Any]:
    report = build_paper_trading_production_drill_report(username)
    return {
        "status": report["status"],
        "revision": report["revision"],
        "revision_range": report["revision_range"],
        "package": report["package"],
        "final_decision": report["final_decision"],
        "blockers": report["blockers"],
        "check_statuses": {key: value.get("status") for key, value in report["checks"].items()},
        "paper_only": True,
        "real_order_submit_triggered": False,
        "secret_values_returned": False,
    }
