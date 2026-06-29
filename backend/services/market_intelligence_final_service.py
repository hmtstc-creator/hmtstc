from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean

from core.storage import now_iso
from services.intelligence_service import (
    build_cooldown_policy,
    build_dynamic_risk_adjustment,
    build_orderbook_intelligence,
    detect_market_regime,
)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _scan_rows(data: dict) -> list[dict]:
    scan = (data or {}).get("last_scan") or {}
    rows = scan.get("scan_rows") or scan.get("candidates") or []
    return list(rows) if isinstance(rows, list) else []


def _coin_group(symbol: str) -> str:
    s = str(symbol or "").upper()
    majors = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
    if s in majors:
        return "major_liquid"
    if any(tag in s for tag in ["PEPE", "DOGE", "SHIB", "FLOKI", "BONK"]):
        return "meme_high_beta"
    if any(tag in s for tag in ["UPUSDT", "DOWNUSDT", "BULL", "BEAR"]):
        return "leveraged_or_synthetic_review"
    return "alt_spot"


def build_market_regime_strategy_match(data: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    regime = detect_market_regime(data or {}, settings)
    name = regime.get("regime") or "UNKNOWN"
    confidence = _safe_float(regime.get("confidence"))

    matrix = {
        "TREND_UP": {
            "preferred": ["breakout_scalper", "momentum_pullback", "choch_continuation"],
            "suppressed": ["mean_reversion_only"],
            "risk_posture": "balanced_review",
        },
        "TREND_DOWN": {
            "preferred": ["shadow_watch", "defensive_reversal_only"],
            "suppressed": ["breakout_long_aggressive", "late_momentum"],
            "risk_posture": "defensive",
        },
        "RANGE_LOW_VOL": {
            "preferred": ["mean_reversion_scalper", "liquidity_sweep_retest"],
            "suppressed": ["breakout_chase"],
            "risk_posture": "small_slots",
        },
        "HIGH_VOLATILITY": {
            "preferred": ["paper_only_observation", "fast_reversal_shadow"],
            "suppressed": ["real_trade", "wide_stop_scalp", "late_breakout"],
            "risk_posture": "no_trade_or_micro_only",
        },
        "CHOPPY": {
            "preferred": ["paper_only", "quality_watchlist_build"],
            "suppressed": ["all_aggressive_entries"],
            "risk_posture": "no_trade_bias",
        },
    }.get(name, {"preferred": ["paper_only"], "suppressed": [], "risk_posture": "review"})

    no_trade = bool(regime.get("no_trade_bias")) or name in {"HIGH_VOLATILITY", "CHOPPY", "TREND_DOWN"}
    status = "blocked" if no_trade and confidence >= 55 else ("review" if confidence < 55 else "ok")
    return {
        "status": status,
        "regime": name,
        "confidence": round(confidence, 2),
        "preferred_strategies": matrix["preferred"],
        "suppressed_strategies": matrix["suppressed"],
        "risk_posture": matrix["risk_posture"],
        "no_trade_bias": no_trade,
        "reason": "Rejime göre strateji seçimi ve risk baskısı üretildi.",
        "updated_at": now_iso(),
    }


def build_orderbook_final_report(data: dict, settings: dict | None = None) -> dict:
    rows = _scan_rows(data)
    candidates = [r for r in rows if str(r.get("status") or r.get("decision") or "").upper() in {"CANDIDATE", "WATCH", "BUY", "PASS"}]
    sample = candidates[:12] if candidates else rows[:12]
    items = []
    for row in sample:
        ob = build_orderbook_intelligence(row, settings or {})
        items.append({
            "symbol": row.get("symbol"),
            "entry_confirmation": bool(ob.get("entry_confirmation")),
            "imbalance_score": round(_safe_float(ob.get("imbalance_score")), 2),
            "fake_wall_risk": round(_safe_float(ob.get("fake_wall_risk") or ob.get("spoofing_risk")), 2),
            "liquidity_vacuum_risk": round(_safe_float(ob.get("liquidity_vacuum_risk")), 2),
            "spread_state": ob.get("spread_state") or ob.get("spread_signal") or "unknown",
            "decision": ob.get("decision") or ("confirm" if ob.get("entry_confirmation") else "watch"),
        })
    avg_imbalance = mean([x["imbalance_score"] for x in items]) if items else 0
    avg_fake = mean([x["fake_wall_risk"] for x in items]) if items else 0
    confirmed = sum(1 for x in items if x["entry_confirmation"])
    status = "ok" if confirmed and avg_fake < 65 else ("review" if items else "blocked")
    return {
        "status": status,
        "sample_size": len(items),
        "confirmed_count": confirmed,
        "avg_imbalance_score": round(avg_imbalance, 2),
        "avg_fake_wall_risk": round(avg_fake, 2),
        "items": items,
        "policy": "Order book verisi entry onayı olarak kullanılır; tek başına real order yetkisi vermez.",
    }


def build_no_trade_cooldown_final(data: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    cooldown = build_cooldown_policy(data or {}, settings)
    regime_match = build_market_regime_strategy_match(data or {}, settings)
    dynamic = build_dynamic_risk_adjustment(data or {}, settings)
    rows = _scan_rows(data)
    low_quality = sum(1 for r in rows if _safe_float(r.get("quality_score") or r.get("score")) < 40)
    blockers = set(cooldown.get("blockers") or [])
    if regime_match.get("no_trade_bias"):
        blockers.add("market_regime_no_trade_bias")
    if _safe_float(dynamic.get("risk_multiplier"), 1.0) <= 0.55:
        blockers.add("dynamic_risk_defensive")
    if rows and low_quality / max(len(rows), 1) > 0.55:
        blockers.add("coin_quality_environment_weak")
    if (data or {}).get("emergency_lock"):
        blockers.add("emergency_lock")

    severity = "blocked" if blockers else "ok"
    minutes = int(cooldown.get("cooldown_minutes") or 0)
    if blockers and minutes <= 0:
        minutes = 30 if "emergency_lock" not in blockers else 60
    return {
        "status": severity,
        "no_trade_active": bool(blockers),
        "cooldown_minutes": minutes,
        "blockers": sorted(blockers),
        "dynamic_risk_mode": dynamic.get("mode"),
        "risk_multiplier": dynamic.get("risk_multiplier"),
        "regime": regime_match.get("regime"),
        "message": "No-trade/cooldown aktif." if blockers else "İşlem engeli yok; yine de real trade manuel onaya bağlı.",
        "audit_required_for_real_override": True,
    }


def build_market_intelligence_final_report(data: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    rows = _scan_rows(data)
    regime = build_market_regime_strategy_match(data, settings)
    orderbook = build_orderbook_final_report(data, settings)
    no_trade = build_no_trade_cooldown_final(data, settings)
    groups = Counter(_coin_group(str(r.get("symbol") or "")) for r in rows)
    quality_values = [_safe_float(r.get("quality_score") or r.get("score")) for r in rows]
    avg_quality = mean(quality_values) if quality_values else 0
    blockers = []
    warnings = []
    if not rows:
        warnings.append("scan_rows_waiting_for_live_scan")
    if regime.get("status") == "blocked":
        warnings.append("regime_has_no_trade_bias")
    if no_trade.get("status") == "blocked":
        warnings.extend(no_trade.get("blockers") or [])
    if orderbook.get("status") == "blocked":
        warnings.append("orderbook_sample_missing")

    score = 100 - len(set(blockers)) * 35 - len(set(warnings)) * 6
    return {
        "revision": 31,
        "status": "blocked" if blockers else ("review" if warnings else "ok"),
        "score": int(_clamp(score)),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "regime_strategy_match": regime,
        "orderbook_intelligence": orderbook,
        "no_trade_cooldown": no_trade,
        "coin_cluster_summary": dict(groups),
        "avg_coin_quality": round(avg_quality, 2),
        "policy": {
            "regime_can_suppress_strategy": True,
            "orderbook_confirms_entry_only": True,
            "no_trade_blocks_real_order": True,
            "ai_or_recommendation_cannot_override_no_trade": True,
            "real_trade_still_owner_confirmed": True,
        },
        "updated_at": now_iso(),
    }
