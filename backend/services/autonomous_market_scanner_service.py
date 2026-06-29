from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from services.coin_market_intelligence_service import build_market_visibility_summary
from services.market_intelligence_final_service import build_no_trade_cooldown_final, build_market_regime_strategy_match
from services.portfolio_allocation_final_service import build_active_risk_budget, build_usdt_reserve_policy
from services.real_trade_state_service import ensure_real_trade_state, open_real_positions


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _last_scan(data: dict | None) -> dict:
    data = data if isinstance(data, dict) else {}
    scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
    if not scan and isinstance(data.get("scan_trace"), dict):
        scan = data.get("scan_trace") or {}
    return deepcopy(scan)


def _scan_rows(data: dict | None) -> list[dict]:
    scan = _last_scan(data)
    rows = scan.get("scan_rows") or scan.get("candidates") or scan.get("items") or []
    return [deepcopy(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _row_symbol(row: dict) -> str:
    return str(row.get("symbol") or row.get("pair") or "").upper().strip()


def _row_score(row: dict) -> float:
    return _safe_float(
        row.get("tradeability_score")
        or row.get("quality_score")
        or row.get("score")
        or row.get("confidence")
    )


def _row_volume(row: dict) -> float:
    return _safe_float(row.get("quote_volume") or row.get("quoteVolume") or row.get("volume_usdt") or row.get("volume"))


def _row_spread(row: dict) -> float:
    return _safe_float(row.get("spread_pct") or row.get("spread_percent") or row.get("spread"))


def _row_volatility(row: dict) -> float:
    return _safe_float(row.get("volatility") or row.get("volatility_pct") or row.get("atr_pct") or row.get("range_pct"))


def _row_status(row: dict) -> str:
    return str(row.get("decision") or row.get("status") or row.get("signal") or "WATCH").upper().strip()


def _row_reasons(row: dict) -> list[str]:
    raw = row.get("rejection_reasons") or row.get("tradability_reasons") or row.get("reasons") or []
    if isinstance(raw, str):
        raw = [raw]
    reasons = [str(item) for item in raw if item]
    reason = row.get("reason")
    if reason and not reasons:
        reasons.append(str(reason))
    return reasons


def _strategy_hint(regime: str, row: dict) -> str:
    status = _row_status(row)
    volatility = _row_volatility(row)
    score = _row_score(row)
    if "CHOCH" in status:
        return "choch_imbalance_scalp"
    if "IMBALANCE" in status or "GAP" in status:
        return "imbalance_gap_fill"
    if regime in {"TREND_UP", "TRENDING_UP"} and score >= 65:
        return "momentum_pullback"
    if regime in {"RANGE_LOW_VOL", "RANGE"}:
        return "liquidity_sweep_retest"
    if volatility >= 8:
        return "paper_watch_high_volatility"
    return "micro_scalp_watch"


def _candidate_from_row(row: dict, regime: str, min_score: float, max_spread: float, min_volume: float) -> dict:
    symbol = _row_symbol(row)
    score = _row_score(row)
    volume = _row_volume(row)
    spread = _row_spread(row)
    volatility = _row_volatility(row)
    reasons = []
    eligible = True
    if not symbol:
        eligible = False
        reasons.append("missing_symbol")
    if score < min_score:
        eligible = False
        reasons.append("score_below_threshold")
    if min_volume and volume and volume < min_volume:
        eligible = False
        reasons.append("liquidity_below_threshold")
    if max_spread and spread and spread > max_spread:
        eligible = False
        reasons.append("spread_too_wide")
    if volatility >= 14:
        eligible = False
        reasons.append("volatility_too_high")
    if _row_status(row) in {"REJECT", "BLOCKED", "NO_TRADE", "DANGER"}:
        eligible = False
        reasons.extend(_row_reasons(row) or ["row_blocked"])
    priority_score = score + min(volume / 1_000_000, 25) - (spread * 4) - max(volatility - 6, 0)
    return {
        "symbol": symbol or "-",
        "eligible": eligible,
        "priority_score": round(_clamp(priority_score), 2),
        "source_score": round(score, 2),
        "quote_volume": round(volume, 2),
        "spread_pct": round(spread, 4),
        "volatility": round(volatility, 2),
        "strategy_hint": _strategy_hint(regime, row),
        "decision": "TRADEABLE" if eligible else "REJECTED",
        "reasons": sorted(set(reasons)) if reasons else ["eligible_micro_real_watch"],
    }


def _scanner_policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    scanner = settings.get("autonomous_scanner") if isinstance(settings.get("autonomous_scanner"), dict) else {}
    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    bot = settings.get("bot") if isinstance(settings.get("bot"), dict) else {}
    return {
        "min_score": _safe_float(scanner.get("min_score"), 55.0),
        "min_trade_score": _safe_float(scanner.get("min_trade_score"), 68.0),
        "min_quote_volume": _safe_float(scanner.get("min_quote_volume"), 0.0),
        "max_spread_pct": _safe_float(scanner.get("max_spread_pct"), 0.35),
        "max_candidates": _safe_int(scanner.get("max_candidates"), 12),
        "preferred_usdt_reserve_pct": _safe_float(scanner.get("preferred_usdt_reserve_pct") or risk.get("preferred_usdt_reserve_pct"), 70.0),
        "max_open_positions": _safe_int(scanner.get("max_open_positions") or bot.get("max_open_positions"), 5),
        "micro_real_requires_owner_unlock": True,
    }


def build_autonomous_market_scanner(data: dict | None, settings: dict | None = None) -> dict:
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _scanner_policy(settings)
    market_visibility = build_market_visibility_summary(data, settings)
    regime_payload = build_market_regime_strategy_match(data, settings)
    no_trade = build_no_trade_cooldown_final(data, settings)
    regime = str(regime_payload.get("regime") or (market_visibility.get("regime") or {}).get("regime") or "UNKNOWN")
    rows = _scan_rows(data)
    candidates = [
        _candidate_from_row(row, regime, policy["min_score"], policy["max_spread_pct"], policy["min_quote_volume"])
        for row in rows
    ]
    candidates = sorted(candidates, key=lambda item: item["priority_score"], reverse=True)
    eligible = [item for item in candidates if item["eligible"]]
    rejected = [item for item in candidates if not item["eligible"]]
    score_values = [item["source_score"] for item in candidates]
    rejection_counter = Counter(reason for item in rejected for reason in item.get("reasons", []))
    warnings = []
    blockers = []
    if not rows:
        warnings.append("scan_snapshot_missing")
    if no_trade.get("no_trade_active"):
        blockers.extend(no_trade.get("blockers") or ["no_trade_active"])
    if regime_payload.get("status") == "blocked":
        blockers.append("market_regime_blocks_trade")
    if not eligible:
        warnings.append("no_tradeable_candidate")
    avg_score = mean(score_values) if score_values else 0.0
    tradeable_ratio = len(eligible) / max(len(candidates), 1)
    environment_score = avg_score * 0.55 + tradeable_ratio * 35 + _safe_float(regime_payload.get("confidence"), 0) * 0.10
    if blockers:
        mode = "DANGER" if any(x in set(blockers) for x in {"emergency_lock", "market_regime_blocks_trade"}) else "WAIT"
        environment_score = min(environment_score, 45)
    elif eligible and environment_score >= policy["min_trade_score"]:
        mode = "TRADE"
    elif eligible:
        mode = "WATCH"
    else:
        mode = "WAIT"
    return {
        "status": "blocked" if blockers else ("review" if warnings or mode in {"WAIT", "WATCH"} else "ok"),
        "revision": 60,
        "engine": "autonomous_market_scanner",
        "generated_at": now_iso(),
        "read_only": True,
        "market_mode": mode,
        "environment_score": round(_clamp(environment_score), 2),
        "regime": regime,
        "regime_confidence": round(_safe_float(regime_payload.get("confidence")), 2),
        "no_trade_active": bool(no_trade.get("no_trade_active")),
        "cooldown_minutes": no_trade.get("cooldown_minutes") or 0,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "policy": policy,
        "scan_metrics": {
            "rows_seen": len(rows),
            "candidate_count": len(candidates),
            "tradeable_count": len(eligible),
            "rejected_count": len(rejected),
            "avg_source_score": round(avg_score, 2),
            "top_rejection_reasons": dict(rejection_counter.most_common(8)),
        },
        "best_symbols": eligible[: policy["max_candidates"]],
        "rejected_sample": rejected[:8],
        "market_visibility": {
            "status": market_visibility.get("status"),
            "summary_cards": market_visibility.get("summary_cards") or {},
        },
        "decision_text": _decision_text(mode, eligible, blockers, warnings),
    }


def _decision_text(mode: str, eligible: list[dict], blockers: list[str], warnings: list[str]) -> str:
    if blockers:
        return "Piyasa veya sistem riski nedeniyle bot işlem açmamalı."
    if mode == "TRADE":
        symbols = ", ".join(item["symbol"] for item in eligible[:3]) or "aday yok"
        return f"Piyasa işlem yapılabilir; öncelikli adaylar: {symbols}."
    if mode == "WATCH":
        return "Aday var ancak skor/risk seviyesi izleme modunda kalmayı gerektiriyor."
    if warnings:
        return "Tarama verisi eksik veya aday kalitesi yetersiz; bekle."
    return "Piyasa uygun değil; bekle."


def build_tradeability_decision(data: dict | None, settings: dict | None = None) -> dict:
    scanner = build_autonomous_market_scanner(data, settings)
    real_state = ensure_real_trade_state(deepcopy(data or {}))
    reserve = build_usdt_reserve_policy(deepcopy(data or {}), deepcopy(settings or {}))
    risk_budget = build_active_risk_budget(deepcopy(data or {}), deepcopy(settings or {}))
    real_positions = open_real_positions(real_state)
    blockers = set(scanner.get("blockers") or [])
    warnings = set(scanner.get("warnings") or [])
    if real_state.get("emergency_lock") or (data or {}).get("emergency_lock"):
        blockers.add("emergency_lock")
    if real_state.get("manual_attention_required"):
        blockers.add("manual_attention_required")
    if real_state.get("dry_run", True):
        warnings.add("real_trade_dry_run_or_locked")
    reserve_status = str(reserve.get("status") or "").lower()
    if reserve_status == "blocked":
        blockers.add("usdt_reserve_policy_blocked")
    elif reserve_status == "review":
        warnings.add("usdt_reserve_policy_review")
    if len(real_positions) >= scanner.get("policy", {}).get("max_open_positions", 5):
        blockers.add("max_real_positions_reached")

    if blockers:
        bot_mode = "SAFE_MODE"
    elif scanner.get("market_mode") == "TRADE" and scanner.get("best_symbols"):
        bot_mode = "MICRO_REAL_READY" if not real_state.get("dry_run", True) else "PAPER_READY"
    elif scanner.get("market_mode") in {"WATCH", "WAIT"}:
        bot_mode = "WATCH"
    else:
        bot_mode = "OFF"

    confidence = scanner.get("environment_score") or 0
    if blockers:
        confidence = min(confidence, 35)
    return {
        "status": "blocked" if blockers else ("review" if warnings or bot_mode in {"WATCH", "PAPER_READY"} else "ok"),
        "revision": 60,
        "engine": "tradeability_decision",
        "generated_at": now_iso(),
        "read_only": True,
        "recommended_bot_mode": bot_mode,
        "market_mode": scanner.get("market_mode"),
        "confidence": round(_clamp(_safe_float(confidence)), 2),
        "best_symbols": [item.get("symbol") for item in scanner.get("best_symbols", [])[:5]],
        "primary_strategy": (scanner.get("best_symbols") or [{}])[0].get("strategy_hint", "paper_watch"),
        "blockers": sorted(blockers),
        "warnings": sorted(warnings),
        "decision_text": _bot_decision_text(bot_mode, scanner, blockers),
        "risk_budget": risk_budget,
        "usdt_reserve_policy": reserve,
        "scanner": scanner,
    }


def _bot_decision_text(bot_mode: str, scanner: dict, blockers: set[str]) -> str:
    if blockers:
        return "Bot güvenlik nedeniyle işlem açmamalı; sadece izleme/koruma modu."
    if bot_mode == "MICRO_REAL_READY":
        return "Bot mikro gerçek işlem için hazır; adayları düşük riskle takip edebilir."
    if bot_mode == "PAPER_READY":
        return "Piyasa uygun fakat real kilit/dry-run nedeniyle paper veya izleme modu önerilir."
    if bot_mode == "WATCH":
        return "Piyasa net değil; bot beklemeli ve yeni tarama sonucunu izlemeli."
    return scanner.get("decision_text") or "Otonom karar bekleme modunda."


def build_summary_autonomous_decision(data: dict | None, settings: dict | None = None) -> dict:
    decision = build_tradeability_decision(data, settings)
    scanner = decision.get("scanner") or {}
    return {
        "status": decision.get("status"),
        "revision": 60,
        "read_only": True,
        "bot_mode": decision.get("recommended_bot_mode"),
        "market_mode": decision.get("market_mode"),
        "confidence": decision.get("confidence"),
        "best_symbols": decision.get("best_symbols") or [],
        "primary_strategy": decision.get("primary_strategy"),
        "risk_status": (decision.get("risk_budget") or {}).get("status", "review"),
        "no_trade_active": bool(scanner.get("no_trade_active")),
        "blocker_count": len(decision.get("blockers") or []),
        "warning_count": len(decision.get("warnings") or []),
        "decision_text": decision.get("decision_text"),
        "updated_at": decision.get("generated_at"),
    }


def build_autonomous_market_scanner_quality(data: dict | None, settings: dict | None = None) -> dict:
    scanner = build_autonomous_market_scanner(data, settings)
    decision = build_tradeability_decision(data, settings)
    checks = {
        "scanner_read_only": scanner.get("read_only") is True,
        "decision_read_only": decision.get("read_only") is True,
        "market_mode_present": scanner.get("market_mode") in {"TRADE", "WATCH", "WAIT", "DANGER"},
        "bot_mode_present": bool(decision.get("recommended_bot_mode")),
        "best_symbols_contract": isinstance(scanner.get("best_symbols"), list),
        "blocker_contract": isinstance(decision.get("blockers"), list),
        "summary_contract": bool(build_summary_autonomous_decision(data, settings).get("bot_mode")),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "status": "ok" if not failed else "review",
        "revision": 60,
        "checks": checks,
        "failed_checks": failed,
        "coverage": [
            "market_mode",
            "tradeability_candidate_ranking",
            "bot_mode_recommendation",
            "risk_reserve_awareness",
            "summary_minimal_decision",
        ],
        "read_only": True,
        "generated_at": now_iso(),
    }
