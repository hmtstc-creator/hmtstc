from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.auto_bot_mode_decision_service import build_auto_bot_mode_decision
from services.autonomous_market_scanner_service import build_autonomous_market_scanner, build_tradeability_decision


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _strategy_policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    selector = settings.get("strategy_selector") if isinstance(settings.get("strategy_selector"), dict) else {}
    return {
        "enabled": bool(selector.get("enabled", True)),
        "min_confidence": _safe_float(selector.get("min_confidence"), 60.0),
        "min_symbol_score": _safe_float(selector.get("min_symbol_score"), 58.0),
        "max_spread_pct": _safe_float(selector.get("max_spread_pct"), 0.35),
        "max_volatility_for_micro": _safe_float(selector.get("max_volatility_for_micro"), 9.0),
        "prefer_scalp": bool(selector.get("prefer_scalp", True)),
    }


def _symbol_from_candidate(candidate: dict) -> str:
    return str(candidate.get("symbol") or candidate.get("pair") or "").upper().strip()


def _candidate_score(candidate: dict) -> float:
    return _safe_float(candidate.get("priority_score") or candidate.get("source_score") or candidate.get("score"))


def _candidate_spread(candidate: dict) -> float:
    return _safe_float(candidate.get("spread_pct") or candidate.get("spread"))


def _candidate_volatility(candidate: dict) -> float:
    return _safe_float(candidate.get("volatility") or candidate.get("volatility_pct") or candidate.get("atr_pct"))


def _normalize_strategy(raw: str | None, regime: str, candidate: dict, policy: dict) -> tuple[str, list[str]]:
    raw = str(raw or "").lower().strip()
    regime_u = str(regime or "UNKNOWN").upper()
    volatility = _candidate_volatility(candidate)
    spread = _candidate_spread(candidate)
    reasons: list[str] = []

    if "choch" in raw or "structure" in raw:
        reasons.append("structure_break_signal")
        return "CHOCH_IMBALANCE_SCALP", reasons
    if "imbalance" in raw or "gap" in raw:
        reasons.append("imbalance_or_gap_signal")
        return "IMBALANCE_GAP_FILL", reasons
    if "TREND" in regime_u and volatility <= policy["max_volatility_for_micro"]:
        reasons.append("trend_regime")
        return "MOMENTUM_PULLBACK_SCALP", reasons
    if "RANGE" in regime_u:
        reasons.append("range_regime")
        return "LIQUIDITY_SWEEP_RETEST", reasons
    if volatility >= policy["max_volatility_for_micro"]:
        reasons.append("high_volatility_requires_paper")
        return "PAPER_VOLATILITY_PROBE", reasons
    if spread > policy["max_spread_pct"]:
        reasons.append("spread_requires_wait")
        return "NO_TRADE_SPREAD_GUARD", reasons
    reasons.append("default_micro_scalp")
    return "MICRO_SCALP_WATCH", reasons


def _strategy_card(candidate: dict, regime: str, bot_mode: str, policy: dict) -> dict:
    symbol = _symbol_from_candidate(candidate)
    strategy, reasons = _normalize_strategy(candidate.get("strategy_hint"), regime, candidate, policy)
    score = _candidate_score(candidate)
    spread = _candidate_spread(candidate)
    volatility = _candidate_volatility(candidate)
    blockers: list[str] = []
    warnings: list[str] = []
    if not symbol:
        blockers.append("missing_symbol")
    if score < policy["min_symbol_score"]:
        blockers.append("score_below_strategy_threshold")
    if spread > policy["max_spread_pct"]:
        blockers.append("spread_too_wide")
    if volatility > policy["max_volatility_for_micro"] and bot_mode in {"MICRO_REAL", "REAL"}:
        blockers.append("volatility_too_high_for_real")
    if strategy.startswith("PAPER") and bot_mode in {"MICRO_REAL", "REAL"}:
        warnings.append("strategy_forces_validation_before_real")
    execution_lane = "NO_TRADE" if blockers else ("PAPER" if strategy.startswith("PAPER") or bot_mode in {"WATCH", "PAPER"} else "MICRO_REAL")
    confidence = _clamp(score - spread * 5 - max(volatility - 5, 0) * 2)
    return {
        "symbol": symbol or "-",
        "strategy": strategy,
        "execution_lane": execution_lane,
        "confidence": round(confidence, 2),
        "source_score": round(score, 2),
        "spread_pct": round(spread, 4),
        "volatility": round(volatility, 2),
        "reasons": sorted(set(reasons)),
        "warnings": sorted(set(warnings)),
        "blockers": sorted(set(blockers)),
        "decision": "SELECTED" if not blockers else "BLOCKED",
    }


def build_strategy_selection_engine(data: dict | None, settings: dict | None = None) -> dict:
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _strategy_policy(settings)
    scanner = build_autonomous_market_scanner(data, settings)
    tradeability = build_tradeability_decision(data, settings)
    bot_mode = build_auto_bot_mode_decision(data, settings)
    recommended_mode = str(bot_mode.get("recommended_mode") or "WATCH")
    regime = str(scanner.get("regime") or tradeability.get("regime") or "UNKNOWN")
    candidates = scanner.get("best_symbols") if isinstance(scanner.get("best_symbols"), list) else []

    blockers = set(bot_mode.get("blockers") or []) | set(tradeability.get("blockers") or [])
    warnings = set(bot_mode.get("warnings") or []) | set(tradeability.get("warnings") or [])
    if not policy["enabled"]:
        blockers.add("strategy_selector_disabled")
    if _safe_float(bot_mode.get("confidence"), 0) < policy["min_confidence"] and recommended_mode not in {"SAFE_MODE", "EMERGENCY_STOP"}:
        warnings.add("bot_confidence_below_strategy_threshold")
    if not candidates:
        warnings.add("no_candidate_for_strategy_selection")

    strategy_cards = [_strategy_card(item, regime, recommended_mode, policy) for item in candidates]
    selected = [item for item in strategy_cards if item["decision"] == "SELECTED"]
    strategy_counter = Counter(item["strategy"] for item in selected)
    primary = selected[0] if selected else None

    if recommended_mode in {"SAFE_MODE", "EMERGENCY_STOP", "OFF"} or blockers:
        status = "blocked"
        action = "do_not_open_new_trade"
    elif primary and recommended_mode in {"PAPER", "MICRO_REAL", "REAL"}:
        status = "ok" if recommended_mode in {"MICRO_REAL", "REAL"} else "review"
        action = "validate_selected_strategy" if recommended_mode == "PAPER" else "allow_selected_strategy"
    else:
        status = "review"
        action = "watch_for_clearer_strategy"

    return {
        "status": status,
        "revision": 62,
        "engine": "strategy_selection_engine",
        "generated_at": now_iso(),
        "read_only": True,
        "recommended_mode": recommended_mode,
        "recommended_action": action,
        "market_mode": tradeability.get("market_mode"),
        "regime": regime,
        "confidence": bot_mode.get("confidence"),
        "primary_strategy": primary.get("strategy") if primary else "NO_TRADE",
        "primary_symbol": primary.get("symbol") if primary else None,
        "selected_strategies": selected[:8],
        "blocked_strategies": [item for item in strategy_cards if item["decision"] == "BLOCKED"][:8],
        "strategy_mix": dict(strategy_counter.most_common()),
        "blockers": sorted(blockers),
        "warnings": sorted(warnings),
        "policy": policy,
        "decision_text": _decision_text(status, recommended_mode, primary, blockers, warnings),
        "source": {
            "scanner_revision": scanner.get("revision"),
            "auto_bot_revision": bot_mode.get("revision"),
            "tradeability_status": tradeability.get("status"),
        },
    }


def _decision_text(status: str, mode: str, primary: dict | None, blockers: set[str], warnings: set[str]) -> str:
    if blockers or status == "blocked":
        return "Strateji seçimi bloklandı; bot yeni işlem açmamalı."
    if not primary:
        return "Net strateji yok; sistem beklemeli ve piyasayı izlemeli."
    if mode == "PAPER":
        return f"{primary['symbol']} için {primary['strategy']} paper doğrulamada izlenmeli."
    if mode in {"MICRO_REAL", "REAL"}:
        return f"{primary['symbol']} için {primary['strategy']} öncelikli strateji olarak seçildi."
    return "Strateji seçimi izleme modunda."


def build_summary_strategy_selection(data: dict | None, settings: dict | None = None) -> dict:
    decision = build_strategy_selection_engine(data, settings)
    return {
        "status": decision.get("status"),
        "revision": 62,
        "read_only": True,
        "bot_mode": decision.get("recommended_mode"),
        "action": decision.get("recommended_action"),
        "primary_strategy": decision.get("primary_strategy"),
        "primary_symbol": decision.get("primary_symbol"),
        "confidence": decision.get("confidence"),
        "blocker_count": len(decision.get("blockers") or []),
        "warning_count": len(decision.get("warnings") or []),
        "decision_text": decision.get("decision_text"),
        "updated_at": decision.get("generated_at"),
    }


def build_strategy_selection_quality(data: dict | None, settings: dict | None = None) -> dict:
    decision = build_strategy_selection_engine(data, settings)
    summary = build_summary_strategy_selection(data, settings)
    checks = {
        "decision_read_only": decision.get("read_only") is True,
        "revision_62": decision.get("revision") == 62,
        "strategy_contract": bool(decision.get("primary_strategy")),
        "selected_strategy_list": isinstance(decision.get("selected_strategies"), list),
        "mode_input_present": decision.get("recommended_mode") in {"OFF", "WATCH", "PAPER", "MICRO_REAL", "REAL", "SAFE_MODE", "EMERGENCY_STOP"},
        "summary_minimal": set(summary.keys()).issuperset({"bot_mode", "primary_strategy", "confidence", "decision_text"}),
        "no_real_when_blocked": not (decision.get("status") == "blocked" and decision.get("recommended_action") == "allow_selected_strategy"),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "status": "ok" if not failed else "review",
        "revision": 62,
        "engine": "strategy_selection_quality",
        "checks": checks,
        "failed_checks": failed,
        "coverage": [
            "scanner_candidate_input",
            "auto_bot_mode_input",
            "regime_to_strategy_selection",
            "paper_vs_micro_real_lane_guard",
            "summary_minimal_strategy_output",
        ],
        "read_only": True,
        "generated_at": now_iso(),
    }
