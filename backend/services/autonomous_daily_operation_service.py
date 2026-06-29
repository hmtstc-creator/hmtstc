from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.auto_bot_mode_decision_service import build_auto_bot_mode_decision
from services.risk_brain_service import build_risk_brain
from services.strategy_selection_engine_service import build_strategy_selection_engine
from services.trade_quality_feedback_service import build_trade_quality_feedback


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


def _operation_policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    op = settings.get("daily_operation") if isinstance(settings.get("daily_operation"), dict) else {}
    bot = settings.get("bot") if isinstance(settings.get("bot"), dict) else {}
    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    return {
        "enabled": bool(op.get("enabled", True)),
        "target_cycle_minutes": _safe_int(op.get("target_cycle_minutes"), 15),
        "max_daily_trades": _safe_int(op.get("max_daily_trades"), _safe_int(bot.get("max_daily_trades"), 120)),
        "max_review_flags": _safe_int(op.get("max_review_flags"), 5),
        "min_quality_score": _safe_float(op.get("min_quality_score"), 50.0),
        "good_quality_score": _safe_float(op.get("good_quality_score"), 70.0),
        "min_confidence_for_active": _safe_float(op.get("min_confidence_for_active"), 58.0),
        "max_daily_loss_pct": _safe_float(op.get("max_daily_loss_pct"), _safe_float(risk.get("daily_loss_stop_pct"), 2.0)),
        "prefer_micro_real": bool(op.get("prefer_micro_real", True)),
        "paper_until_quality_ok": bool(op.get("paper_until_quality_ok", True)),
    }


def _today_trades(data: dict) -> list[dict]:
    today = now_iso()[:10]
    rows: list[dict] = []
    for key in ("closed_trades", "trade_history", "history", "trades", "orders"):
        value = data.get(key)
        if isinstance(value, list):
            rows.extend([item for item in value if isinstance(item, dict)])
    real_trade = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    for key in ("closed_trades", "trade_history", "history", "orders"):
        value = real_trade.get(key)
        if isinstance(value, list):
            rows.extend([item for item in value if isinstance(item, dict)])
    out = []
    for item in rows:
        when = str(item.get("closed_at") or item.get("created_at") or item.get("time") or item.get("updated_at") or "")
        if not when or when[:10] == today:
            out.append(item)
    return out[-500:]


def _pnl_usdt(data: dict, trades: list[dict]) -> float:
    perf = data.get("performance") if isinstance(data.get("performance"), dict) else {}
    direct = data.get("today_pnl_usdt", perf.get("today_pnl_usdt"))
    if direct is not None:
        return round(_safe_float(direct), 4)
    total = 0.0
    for item in trades:
        total += _safe_float(item.get("pnl_usdt"), _safe_float(item.get("pnl"), 0.0))
    return round(total, 4)


def _win_rate(trades: list[dict]) -> float:
    wins = 0
    losses = 0
    for item in trades:
        pnl = _safe_float(item.get("pnl_usdt"), _safe_float(item.get("pnl"), 0.0))
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
    return round(wins / max(wins + losses, 1) * 100.0, 2)


def _session_phase() -> str:
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 7:
        return "asia_watch"
    if 7 <= hour < 13:
        return "europe_scan"
    if 13 <= hour < 20:
        return "us_active"
    return "late_risk_reduce"


def _mode_rank(mode: str) -> int:
    order = {"EMERGENCY_STOP": 0, "SAFE_MODE": 1, "OFF": 2, "WATCH": 3, "PAPER": 4, "MICRO_REAL": 5, "REAL": 6}
    return order.get(str(mode or "WATCH"), 3)


def _lower_mode(current: str, target: str) -> str:
    return target if _mode_rank(target) < _mode_rank(current) else current


def _normalize_mode(mode: Any) -> str:
    text = str(mode or "WATCH").upper()
    return text if text in {"OFF", "WATCH", "PAPER", "MICRO_REAL", "REAL", "SAFE_MODE", "EMERGENCY_STOP"} else "WATCH"


def _decision_text(status: str, mode: str, action: str, blockers: list[str], symbol: str | None, quality_score: float) -> str:
    if blockers:
        return f"Günlük operasyon durduruldu: {', '.join(blockers[:3])}."
    if mode == "MICRO_REAL":
        return f"Günlük operasyon mikro gerçek işlem için uygun; öncelik {symbol or 'en iyi aday'} ve kalite {round(quality_score, 1)}/100."
    if mode == "PAPER":
        return "Piyasa denenebilir; kalite/risk teyidi için paper modda devam edilmeli."
    if mode == "WATCH":
        return "Sistem izleme modunda; yeni gerçek işlem için yeterli güven yok."
    if mode == "SAFE_MODE":
        return "Risk yüksek; günlük operasyon safe mode içinde korunmalı."
    if mode == "EMERGENCY_STOP":
        return "Acil durum kilidi nedeniyle bütün yeni işlemler kapalı."
    return f"Günlük operasyon {action} aksiyonunda."


def build_autonomous_daily_operation(data: dict | None, settings: dict | None = None) -> dict:
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _operation_policy(settings)
    bot = build_auto_bot_mode_decision(data, settings)
    strategy = build_strategy_selection_engine(data, settings)
    risk = build_risk_brain(data, settings)
    quality = build_trade_quality_feedback(data, settings)

    trades = _today_trades(data)
    today_pnl = _pnl_usdt(data, trades)
    trade_count = len(trades)
    win_rate = _win_rate(trades)
    capital = max(_safe_float(risk.get("capital_usdt"), _safe_float((settings.get("bot") or {}).get("allocated_usdt"), 1000.0)), 1.0)
    today_loss_pct = abs(min(0.0, today_pnl)) / capital * 100.0

    blockers = set(bot.get("blockers") or []) | set(risk.get("blockers") or [])
    warnings = set(bot.get("warnings") or []) | set(risk.get("warnings") or []) | set(quality.get("feedback") or [])

    if not policy["enabled"]:
        blockers.add("daily_operation_disabled")
    if trade_count >= policy["max_daily_trades"]:
        blockers.add("max_daily_trades_reached")
    if today_loss_pct >= policy["max_daily_loss_pct"]:
        blockers.add("daily_operation_loss_limit_reached")
    if _safe_float(quality.get("quality_score"), 0.0) < policy["min_quality_score"] and quality.get("quality_status") not in {"NO_TRADE_DATA", "DISABLED"}:
        blockers.add("trade_quality_below_daily_threshold")

    mode = _normalize_mode(bot.get("recommended_mode"))
    confidence = min(_safe_float(bot.get("confidence"), 0.0), _safe_float(strategy.get("confidence"), 0.0) or 100.0, _safe_float(risk.get("confidence"), 0.0) or 100.0)
    quality_score = _safe_float(quality.get("quality_score"), 0.0)

    if blockers:
        action = "pause_new_entries"
        mode = "EMERGENCY_STOP" if "emergency_lock" in blockers or mode == "EMERGENCY_STOP" else "SAFE_MODE"
        status = "blocked"
    else:
        if confidence < policy["min_confidence_for_active"]:
            mode = _lower_mode(mode, "WATCH")
            action = "watch_market"
        elif policy["paper_until_quality_ok"] and quality.get("quality_status") in {"NO_TRADE_DATA", "REVIEW"}:
            mode = _lower_mode(mode, "PAPER")
            action = "paper_validate"
        elif mode in {"MICRO_REAL", "REAL"}:
            mode = "MICRO_REAL" if policy["prefer_micro_real"] else mode
            action = "allow_micro_entries"
        elif mode == "PAPER":
            action = "paper_validate"
        else:
            action = "watch_market"
        status = "review" if mode in {"WATCH", "PAPER"} or len(warnings) > policy["max_review_flags"] else "ok"

    cadence = "recheck_fast" if mode in {"MICRO_REAL", "REAL"} else ("recheck_normal" if mode in {"PAPER", "WATCH"} else "risk_hold")
    primary_symbol = strategy.get("primary_symbol") or risk.get("primary_symbol")
    best_symbols = [s for s in (strategy.get("candidate_symbols") or bot.get("best_symbols") or []) if s][:5]
    if primary_symbol and primary_symbol not in best_symbols:
        best_symbols = [primary_symbol] + best_symbols

    summary_cards = {
        "bot_mode": mode,
        "market": strategy.get("market_mode") or bot.get("market_mode") or "WAIT",
        "today_pnl_usdt": round(today_pnl, 4),
        "risk_status": risk.get("risk_status"),
        "action": action,
    }

    return {
        "status": status,
        "revision": 65,
        "engine": "autonomous_daily_operation",
        "generated_at": now_iso(),
        "read_only": True,
        "session_phase": _session_phase(),
        "recommended_mode": mode,
        "recommended_action": action,
        "cadence": cadence,
        "next_check_minutes": policy["target_cycle_minutes"] if cadence != "risk_hold" else max(policy["target_cycle_minutes"], 60),
        "primary_symbol": primary_symbol,
        "primary_strategy": strategy.get("primary_strategy"),
        "best_symbols": best_symbols[:5],
        "confidence": round(confidence, 2),
        "today": {
            "trade_count": trade_count,
            "max_daily_trades": policy["max_daily_trades"],
            "pnl_usdt": round(today_pnl, 4),
            "loss_pct": round(today_loss_pct, 3),
            "win_rate": win_rate,
            "quality_score": round(quality_score, 2),
        },
        "budget": {
            "suggested_order_usdt": risk.get("suggested_order_usdt", 0.0),
            "remaining_risk_usdt": risk.get("remaining_risk_usdt", 0.0),
            "reserve_pct": risk.get("reserve_pct"),
            "active_risk_pct": risk.get("active_risk_pct"),
        },
        "blockers": sorted(blockers),
        "warnings": sorted(warnings)[:10],
        "summary_cards": summary_cards,
        "decision_text": _decision_text(status, mode, action, sorted(blockers), primary_symbol, quality_score),
        "source": {
            "auto_bot_revision": bot.get("revision"),
            "strategy_revision": strategy.get("revision"),
            "risk_revision": risk.get("revision"),
            "trade_quality_revision": quality.get("revision"),
        },
        "policy": policy,
    }


def build_summary_daily_operation(data: dict | None, settings: dict | None = None) -> dict:
    operation = build_autonomous_daily_operation(data, settings)
    today = operation.get("today") or {}
    budget = operation.get("budget") or {}
    return {
        "status": operation.get("status"),
        "revision": 65,
        "read_only": True,
        "bot_mode": operation.get("recommended_mode"),
        "market": (operation.get("summary_cards") or {}).get("market"),
        "today_pnl_usdt": today.get("pnl_usdt"),
        "risk_status": (operation.get("summary_cards") or {}).get("risk_status"),
        "action": operation.get("recommended_action"),
        "primary_symbol": operation.get("primary_symbol"),
        "primary_strategy": operation.get("primary_strategy"),
        "suggested_order_usdt": budget.get("suggested_order_usdt"),
        "trade_count": today.get("trade_count"),
        "quality_score": today.get("quality_score"),
        "decision_text": operation.get("decision_text"),
        "updated_at": operation.get("generated_at"),
    }


def build_autonomous_daily_operation_quality(data: dict | None, settings: dict | None = None) -> dict:
    operation = build_autonomous_daily_operation(data, settings)
    summary = build_summary_daily_operation(data, settings)
    source = operation.get("source") or {}
    checks = {
        "decision_read_only": operation.get("read_only") is True,
        "revision_65": operation.get("revision") == 65,
        "source_chain_linked": source.get("auto_bot_revision") == 61 and source.get("strategy_revision") == 62 and source.get("risk_revision") == 63 and source.get("trade_quality_revision") == 64,
        "summary_contract": summary.get("revision") == 65 and summary.get("read_only") is True and bool(summary.get("bot_mode")),
        "budget_contract": isinstance(operation.get("budget"), dict) and "suggested_order_usdt" in operation.get("budget", {}),
        "action_contract": operation.get("recommended_action") in {"pause_new_entries", "watch_market", "paper_validate", "allow_micro_entries"},
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 65,
        "engine": "autonomous_daily_operation_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "recommended_mode": operation.get("recommended_mode"),
        "recommended_action": operation.get("recommended_action"),
        "blockers": operation.get("blockers", []),
    }
