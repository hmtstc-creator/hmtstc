from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.risk_brain_service import build_risk_brain
from services.strategy_selection_engine_service import build_strategy_selection_engine


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _quality_policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    policy = settings.get("trade_quality") if isinstance(settings.get("trade_quality"), dict) else {}
    return {
        "enabled": bool(policy.get("enabled", True)),
        "good_score": _safe_float(policy.get("good_score"), 70.0),
        "review_score": _safe_float(policy.get("review_score"), 50.0),
        "max_entry_slippage_pct": _safe_float(policy.get("max_entry_slippage_pct"), 0.25),
        "max_exit_slippage_pct": _safe_float(policy.get("max_exit_slippage_pct"), 0.35),
        "max_spread_pct": _safe_float(policy.get("max_spread_pct"), 0.35),
        "min_rr": _safe_float(policy.get("min_rr"), 1.05),
        "late_entry_penalty_pct": _safe_float(policy.get("late_entry_penalty_pct"), 0.45),
        "early_exit_profit_keep_pct": _safe_float(policy.get("early_exit_profit_keep_pct"), 55.0),
    }


def _trade_candidates(data: dict) -> list[dict]:
    candidates: list[dict] = []
    for key in ("closed_trades", "trade_history", "history", "trades", "orders"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    real_trade = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    for key in ("closed_trades", "trade_history", "history", "orders"):
        value = real_trade.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    paper = data.get("paper") if isinstance(data.get("paper"), dict) else {}
    for key in ("closed_trades", "trade_history", "history", "orders"):
        value = paper.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    return candidates


def _last_trade(data: dict) -> dict | None:
    candidates = _trade_candidates(data)
    if not candidates:
        return None

    def sort_key(item: dict) -> str:
        return str(item.get("closed_at") or item.get("exit_time") or item.get("updated_at") or item.get("created_at") or item.get("time") or "")

    return sorted(candidates, key=sort_key)[-1]


def _notional(trade: dict) -> float:
    return max(
        _safe_float(trade.get("notional_usdt")),
        _safe_float(trade.get("quote_qty")),
        _safe_float(trade.get("quote_order_qty")),
        _safe_float(trade.get("value_usdt")),
        _safe_float(trade.get("size_usdt")),
    )


def _pnl(trade: dict) -> tuple[float, float]:
    pnl_usdt = _safe_float(trade.get("pnl_usdt"), _safe_float(trade.get("pnl"), 0.0))
    pnl_pct = _safe_float(trade.get("pnl_pct"), _safe_float(trade.get("profit_pct"), 0.0))
    notional = _notional(trade)
    if pnl_pct == 0.0 and notional:
        pnl_pct = pnl_usdt / notional * 100.0
    return pnl_usdt, pnl_pct


def _side(trade: dict) -> str:
    return str(trade.get("side") or trade.get("direction") or "LONG").upper()


def _entry_quality(trade: dict, policy: dict) -> tuple[float, list[str], str]:
    entry_slippage = abs(_safe_float(trade.get("entry_slippage_pct"), _safe_float(trade.get("slippage_pct"), 0.0)))
    spread = abs(_safe_float(trade.get("spread_pct"), 0.0))
    signal_age = _safe_float(trade.get("signal_age_seconds"), _safe_float(trade.get("entry_delay_seconds"), 0.0))
    penalties = []
    score = 100.0
    if entry_slippage > policy["max_entry_slippage_pct"]:
        score -= min(35.0, (entry_slippage - policy["max_entry_slippage_pct"]) * 55.0)
        penalties.append("entry_slippage_high")
    if spread > policy["max_spread_pct"]:
        score -= min(25.0, (spread - policy["max_spread_pct"]) * 45.0)
        penalties.append("spread_too_wide")
    if signal_age > 90:
        score -= min(20.0, signal_age / 30.0)
        penalties.append("entry_late")
    timing = "late" if "entry_late" in penalties else "clean"
    return _clamp(score), penalties, timing


def _exit_quality(trade: dict, policy: dict) -> tuple[float, list[str], str]:
    pnl_usdt, pnl_pct = _pnl(trade)
    exit_slippage = abs(_safe_float(trade.get("exit_slippage_pct"), 0.0))
    max_favorable = abs(_safe_float(trade.get("max_favorable_pct"), _safe_float(trade.get("mfe_pct"), pnl_pct)))
    max_adverse = abs(_safe_float(trade.get("max_adverse_pct"), _safe_float(trade.get("mae_pct"), 0.0)))
    penalties = []
    score = 100.0
    if exit_slippage > policy["max_exit_slippage_pct"]:
        score -= min(25.0, (exit_slippage - policy["max_exit_slippage_pct"]) * 40.0)
        penalties.append("exit_slippage_high")
    if pnl_usdt < 0:
        score -= min(35.0, abs(pnl_pct) * 8.0 + 10.0)
        penalties.append("loss_trade")
    elif max_favorable > 0:
        kept = max(0.0, pnl_pct) / max_favorable * 100.0
        if kept < policy["early_exit_profit_keep_pct"]:
            score -= min(25.0, (policy["early_exit_profit_keep_pct"] - kept) / 2.5)
            penalties.append("exit_too_early")
    if max_adverse > abs(pnl_pct) * 3 and pnl_usdt <= 0:
        score -= 10.0
        penalties.append("stop_or_exit_late")
    timing = "early" if "exit_too_early" in penalties else ("late" if "stop_or_exit_late" in penalties else "clean")
    return _clamp(score), penalties, timing


def _strategy_alignment(trade: dict, strategy: dict) -> tuple[float, list[str]]:
    penalties = []
    trade_strategy = str(trade.get("strategy") or trade.get("strategy_name") or "").upper()
    selected = str(strategy.get("primary_strategy") or "").upper()
    trade_symbol = str(trade.get("symbol") or "").upper()
    selected_symbol = str(strategy.get("primary_symbol") or "").upper()
    confidence = _safe_float(strategy.get("confidence"), 0.0)
    score = 75.0 + min(20.0, confidence / 5.0)
    if trade_strategy and selected and trade_strategy != selected:
        score -= 25.0
        penalties.append("strategy_mismatch")
    if trade_symbol and selected_symbol and trade_symbol != selected_symbol:
        score -= 12.0
        penalties.append("symbol_not_primary")
    return _clamp(score), penalties


def _risk_alignment(trade: dict, risk: dict) -> tuple[float, list[str]]:
    penalties = []
    score = 100.0
    suggested = _safe_float(risk.get("suggested_order_usdt"), 0.0)
    notional = _notional(trade)
    if risk.get("status") == "blocked" and notional > 0:
        score -= 45.0
        penalties.append("trade_opened_while_risk_blocked")
    if suggested > 0 and notional > suggested * 1.35:
        score -= min(35.0, (notional / suggested - 1.0) * 18.0)
        penalties.append("position_size_above_suggestion")
    if _safe_float(risk.get("reserve_pct"), 100.0) < _safe_float((risk.get("policy") or {}).get("min_usdt_reserve_pct"), 85.0):
        score -= 20.0
        penalties.append("reserve_policy_pressure")
    return _clamp(score), penalties


def _rr_score(trade: dict, policy: dict) -> tuple[float, list[str]]:
    rr = _safe_float(trade.get("risk_reward"), _safe_float(trade.get("rr"), 0.0))
    pnl_usdt, _ = _pnl(trade)
    penalties = []
    if rr <= 0:
        return (70.0 if pnl_usdt >= 0 else 45.0), ["rr_missing"]
    score = min(100.0, rr / max(policy["min_rr"], 0.1) * 75.0)
    if rr < policy["min_rr"]:
        penalties.append("rr_below_policy")
    return _clamp(score), penalties


def build_trade_quality_feedback(data: dict | None, settings: dict | None = None) -> dict:
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _quality_policy(settings)
    strategy = build_strategy_selection_engine(data, settings)
    risk = build_risk_brain(data, settings)
    trade = _last_trade(data)

    if not policy["enabled"]:
        return {
            "status": "blocked",
            "revision": 64,
            "engine": "trade_quality_feedback",
            "generated_at": now_iso(),
            "read_only": True,
            "quality_score": 0,
            "quality_status": "DISABLED",
            "latest_trade": None,
            "feedback": ["trade_quality_feedback_disabled"],
            "decision_text": "İşlem kalite geri bildirimi kapalı.",
            "source": {"strategy_revision": strategy.get("revision"), "risk_revision": risk.get("revision")},
        }

    if trade is None:
        return {
            "status": "review",
            "revision": 64,
            "engine": "trade_quality_feedback",
            "generated_at": now_iso(),
            "read_only": True,
            "quality_score": 0,
            "quality_status": "NO_TRADE_DATA",
            "latest_trade": None,
            "feedback": ["closed_trade_history_missing"],
            "improvement_actions": ["Kapalı işlem verisi oluşunca giriş/çıkış kalitesi otomatik puanlanacak."],
            "decision_text": "Değerlendirilecek kapanmış işlem bulunamadı.",
            "source": {"strategy_revision": strategy.get("revision"), "risk_revision": risk.get("revision")},
        }

    entry_score, entry_flags, entry_timing = _entry_quality(trade, policy)
    exit_score, exit_flags, exit_timing = _exit_quality(trade, policy)
    strategy_score, strategy_flags = _strategy_alignment(trade, strategy)
    risk_score, risk_flags = _risk_alignment(trade, risk)
    rr_score, rr_flags = _rr_score(trade, policy)
    all_flags = entry_flags + exit_flags + strategy_flags + risk_flags + rr_flags
    score = _clamp(entry_score * 0.24 + exit_score * 0.26 + strategy_score * 0.20 + risk_score * 0.20 + rr_score * 0.10)

    if score >= policy["good_score"] and not any(flag in all_flags for flag in ("trade_opened_while_risk_blocked", "loss_trade")):
        status = "ok"
        quality_status = "GOOD"
        repeatability = "repeat_with_same_rules"
    elif score >= policy["review_score"]:
        status = "review"
        quality_status = "REVIEW"
        repeatability = "repeat_with_lower_size"
    else:
        status = "blocked"
        quality_status = "POOR"
        repeatability = "do_not_repeat_until_adjusted"

    actions = _improvement_actions(all_flags, status)
    pnl_usdt, pnl_pct = _pnl(trade)
    latest = {
        "symbol": trade.get("symbol") or risk.get("primary_symbol") or strategy.get("primary_symbol"),
        "side": _side(trade),
        "strategy": trade.get("strategy") or trade.get("strategy_name") or strategy.get("primary_strategy"),
        "notional_usdt": round(_notional(trade), 4),
        "pnl_usdt": round(pnl_usdt, 4),
        "pnl_pct": round(pnl_pct, 4),
        "closed_at": trade.get("closed_at") or trade.get("exit_time") or trade.get("updated_at") or trade.get("time"),
    }

    return {
        "status": status,
        "revision": 64,
        "engine": "trade_quality_feedback",
        "generated_at": now_iso(),
        "read_only": True,
        "quality_score": round(score, 2),
        "quality_status": quality_status,
        "repeatability": repeatability,
        "entry_timing": entry_timing,
        "exit_timing": exit_timing,
        "latest_trade": latest,
        "score_breakdown": {
            "entry": round(entry_score, 2),
            "exit": round(exit_score, 2),
            "strategy_alignment": round(strategy_score, 2),
            "risk_alignment": round(risk_score, 2),
            "risk_reward": round(rr_score, 2),
        },
        "feedback": sorted(set(all_flags)) or ["trade_execution_clean"],
        "improvement_actions": actions,
        "decision_text": _decision_text(status, quality_status, latest, score, all_flags),
        "source": {"strategy_revision": strategy.get("revision"), "risk_revision": risk.get("revision")},
        "policy": policy,
    }


def _improvement_actions(flags: list[str], status: str) -> list[str]:
    actions = []
    flag_set = set(flags)
    if "entry_slippage_high" in flag_set or "spread_too_wide" in flag_set:
        actions.append("Spread/slippage yüksekse giriş eşiğini sıkılaştır ve limit emir önceliğini artır.")
    if "entry_late" in flag_set:
        actions.append("Sinyal yaşı yükseldiğinde işlem açma veya pozisyon boyutunu düşür.")
    if "exit_too_early" in flag_set:
        actions.append("Kârı erken bırakmamak için trailing/partial exit kuralını gözden geçir.")
    if "stop_or_exit_late" in flag_set or "loss_trade" in flag_set:
        actions.append("Zarar yönüne giden işlemde stop/çıkış gecikmesini azalt.")
    if "strategy_mismatch" in flag_set:
        actions.append("İşlem stratejisi ile seçilen otonom strateji uyumsuzsa yeni sinyal üretme.")
    if "position_size_above_suggestion" in flag_set or "trade_opened_while_risk_blocked" in flag_set:
        actions.append("Risk Brain önerisinin üstünde pozisyon açmayı engelle.")
    if not actions and status == "ok":
        actions.append("Mevcut kurallar düşük riskle tekrar edilebilir.")
    if not actions:
        actions.append("Bir sonraki işlem mikro boyutta izlenmeli ve karar eşiği sıkılaştırılmalı.")
    return actions[:5]


def _decision_text(status: str, quality_status: str, latest: dict, score: float, flags: list[str]) -> str:
    symbol = latest.get("symbol") or "son işlem"
    if status == "ok":
        return f"{symbol} işlemi {round(score, 1)}/100 kaliteyle tekrar edilebilir görünüyor."
    if status == "blocked":
        return f"{symbol} işlemi kalite eşiğinin altında; aynı koşulda tekrar edilmemeli."
    if "loss_trade" in set(flags):
        return f"{symbol} zarar üretti; giriş/çıkış kalitesi revize edilmeli."
    return f"{symbol} işlemi {quality_status} durumunda; sadece düşük boyutla tekrar denenebilir."


def build_summary_trade_quality_feedback(data: dict | None, settings: dict | None = None) -> dict:
    feedback = build_trade_quality_feedback(data, settings)
    latest = feedback.get("latest_trade") or {}
    return {
        "status": feedback.get("status"),
        "revision": 64,
        "read_only": True,
        "quality_score": feedback.get("quality_score"),
        "quality_status": feedback.get("quality_status"),
        "repeatability": feedback.get("repeatability"),
        "entry_timing": feedback.get("entry_timing"),
        "exit_timing": feedback.get("exit_timing"),
        "symbol": latest.get("symbol"),
        "pnl_usdt": latest.get("pnl_usdt"),
        "feedback_count": len(feedback.get("feedback") or []),
        "top_action": (feedback.get("improvement_actions") or [None])[0],
        "decision_text": feedback.get("decision_text"),
        "updated_at": feedback.get("generated_at"),
    }


def build_trade_quality_feedback_quality(data: dict | None, settings: dict | None = None) -> dict:
    feedback = build_trade_quality_feedback(data, settings)
    summary = build_summary_trade_quality_feedback(data, settings)
    checks = {
        "decision_read_only": feedback.get("read_only") is True,
        "revision_64": feedback.get("revision") == 64,
        "score_contract": 0 <= _safe_float(feedback.get("quality_score")) <= 100,
        "summary_contract": summary.get("revision") == 64 and summary.get("read_only") is True,
        "source_linked": feedback.get("source", {}).get("risk_revision") == 63,
        "feedback_present": bool(feedback.get("feedback")),
        "actions_present": bool(feedback.get("improvement_actions") or feedback.get("quality_status") in {"DISABLED", "NO_TRADE_DATA"}),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 64,
        "engine": "trade_quality_feedback_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "quality_status": feedback.get("quality_status"),
        "quality_score": feedback.get("quality_score"),
        "feedback": feedback.get("feedback", []),
    }
