"""Karabasan final permission engine.

This module is intentionally deterministic and offline-safe. Live integrations can feed
real market data later, but the scoring contract, weights, blockers, and admin-visible
breakdown are production-shaped now.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

DEFAULT_MIN_SCORE = 65
DEFAULT_TARGET_MIN = 0.6
DEFAULT_TARGET_MAX = 2.0
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1D", "1W"]
TIMEFRAME_WEIGHTS = {"5m": 0.10, "15m": 0.15, "1h": 0.25, "4h": 0.25, "1D": 0.15, "1W": 0.10}
CRITICAL_BLOCKS = {"target_profit_fit", "liquidity", "risk_reward", "news_risk"}

CRITERIA = {
    "market_regime": {"label": "Market rejimi", "weight": 0.08, "status_good": "Piyasa genel olarak işlem açmaya uygun."},
    "btc_trend": {"label": "BTC trend", "weight": 0.09, "status_good": "BTC piyasa için destekleyici veya stabil."},
    "btc_dominance": {"label": "BTC dominance", "weight": 0.07, "status_good": "Dominance altcoin işlemini baskılamıyor."},
    "total2": {"label": "TOTAL2", "weight": 0.07, "status_good": "BTC dışı piyasa hedef karı taşıyabilir."},
    "coin_strength": {"label": "Coin özel güç", "weight": 0.10, "status_good": "Coin trend, momentum ve hacim açısından güçlü."},
    "target_profit_fit": {"label": "Hedef kar uygunluğu", "weight": 0.13, "status_good": "Hedef kar için alan, volatilite ve net getiri uygun."},
    "timeframe_alignment": {"label": "Zaman dilimi uyumu", "weight": 0.07, "status_good": "Sinyal zamanı hedef kar aralığıyla uyumlu."},
    "news_risk": {"label": "Haber / risk", "weight": 0.08, "status_good": "Yakın haber veya ani bozulma riski düşük."},
    "session_score": {"label": "Borsa seansı / saat", "weight": 0.03, "status_good": "Likidite saati işlem için makul."},
    "liquidity": {"label": "Likidite", "weight": 0.08, "status_good": "Spread, derinlik ve hacim yeterli."},
    "volatility": {"label": "Volatilite", "weight": 0.06, "status_good": "Hedef kar için yeterli ama aşırı riskli olmayan hareket var."},
    "strategy_signal_quality": {"label": "Strateji sinyal kalitesi", "weight": 0.06, "status_good": "Strateji bu coin/zaman koşulunda güvenilir."},
    "risk_reward": {"label": "Risk / ödül", "weight": 0.06, "status_good": "Alınan risk hedef kara değer."},
    "correlation": {"label": "Korelasyon", "weight": 0.02, "status_good": "Açık pozisyonlarla aşırı benzer risk yok."},
}

TARGET_BY_TIMEFRAME = {
    "5m": (0.6, 0.9),
    "15m": (0.8, 1.2),
    "1h": (1.0, 1.6),
    "4h": (1.2, 2.0),
    "1D": (0.6, 2.0),
    "1W": (0.6, 2.0),
}


def clamp(value: Any, minimum: float = 0, maximum: float = 100) -> float:
    try:
        number = float(value)
    except Exception:
        number = 0.0
    return max(minimum, min(maximum, number))


def weighted_average(values: Dict[str, Any], weights: Dict[str, float] | None = None, default: float = 60) -> float:
    weights = weights or TIMEFRAME_WEIGHTS
    total = 0.0
    used = 0.0
    for key, weight in weights.items():
        total += clamp(values.get(key, default)) * weight
        used += weight
    return round(total / used if used else default, 2)


def settings_get(settings: Dict[str, Any], key: str, default: Any) -> Any:
    karabasan = settings.get("karabasan") or {}
    return karabasan.get(key, default)


def get_market_payload(runtime: Dict[str, Any], settings: Dict[str, Any], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    signal = signal or {}
    return {
        "symbol": signal.get("symbol") or runtime.get("selected_symbol") or "BTCUSDT",
        "side": signal.get("side") or "BUY",
        "timeframe": signal.get("timeframe") or settings_get(settings, "default_timeframe", "15m"),
        "target_profit_pct": float(signal.get("target_profit_pct") or settings_get(settings, "target_profit_pct", 1.0)),
        "stop_loss_pct": float(signal.get("stop_loss_pct") or settings_get(settings, "stop_loss_pct", 1.2)),
        "quote_order_qty": float(signal.get("quote_order_qty") or settings_get(settings, "quote_order_qty", 25)),
        "market": (runtime.get("karabasan_market") or settings.get("karabasan_market") or {}),
        "signal": signal,
    }


def score_status(score: float) -> str:
    if score >= 80:
        return "güçlü"
    if score >= 65:
        return "uygun"
    if score >= 50:
        return "bekle"
    return "zayıf"


def calculate_market_regime(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    market = payload["market"].get("market_regime", {})
    tf = market.get("timeframes", {})
    score = weighted_average(tf, default=market.get("fallback", 62))
    detail = {
        "5m": clamp(tf.get("5m", score)), "15m": clamp(tf.get("15m", score)), "1h": clamp(tf.get("1h", score)),
        "4h": clamp(tf.get("4h", score)), "1D": clamp(tf.get("1D", score)), "1W": clamp(tf.get("1W", score)),
        "risk_appetite": clamp(market.get("risk_appetite", score)),
        "market_flow": clamp(market.get("market_flow", score)),
    }
    return score, detail


def calculate_btc_trend(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    market = payload["market"].get("btc_trend", {})
    tf = market.get("timeframes", {})
    base = weighted_average(tf, default=market.get("fallback", 64))
    crash_risk = clamp(market.get("crash_risk", 25))
    altcoin_squeeze = clamp(market.get("altcoin_squeeze", 20))
    score = round(clamp(base - crash_risk * 0.25 - altcoin_squeeze * 0.15), 2)
    return score, {**{k: clamp(tf.get(k, base)) for k in TIMEFRAMES}, "crash_risk": crash_risk, "altcoin_squeeze": altcoin_squeeze}


def calculate_btc_dominance(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    market = payload["market"].get("btc_dominance", {})
    trend = market.get("trend", "flat")
    change_1h = float(market.get("change_1h_pct", 0))
    change_4h = float(market.get("change_4h_pct", 0))
    base = 60
    if trend == "falling": base = 82
    elif trend == "rising": base = 38
    score = clamp(base - max(change_1h, 0) * 18 - max(change_4h, 0) * 10 + max(-change_1h, 0) * 12)
    return round(score, 2), {"trend": trend, "change_1h_pct": change_1h, "change_4h_pct": change_4h, "altcoin_pressure": clamp(100-score)}


def calculate_total2(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    market = payload["market"].get("total2", {})
    tf = market.get("timeframes", {})
    base = weighted_average(tf, default=market.get("fallback", 63))
    volume = clamp(market.get("volume_score", base))
    resistance = clamp(market.get("resistance_room", base))
    score = round(base * 0.65 + volume * 0.20 + resistance * 0.15, 2)
    return score, {**{k: clamp(tf.get(k, base)) for k in TIMEFRAMES}, "volume_score": volume, "resistance_room": resistance}


def calculate_coin_strength(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    coin = payload["market"].get("coin", {})
    trend = weighted_average(coin.get("timeframes", {}), default=coin.get("trend", 62))
    momentum = clamp(coin.get("momentum", 62))
    volume = clamp(coin.get("volume", 60))
    liquidity = clamp(coin.get("liquidity", 65))
    support_resistance = clamp(coin.get("support_resistance", 60))
    fake_breakout_risk = clamp(coin.get("fake_breakout_risk", 25))
    score = trend * .30 + momentum * .20 + volume * .15 + liquidity * .15 + support_resistance * .15 + (100 - fake_breakout_risk) * .05
    return round(clamp(score), 2), {
        "trend": trend, "momentum": momentum, "volume": volume, "liquidity": liquidity,
        "support_resistance": support_resistance, "fake_breakout_risk": fake_breakout_risk,
    }


def calculate_target_profit_fit(payload: Dict[str, Any], settings: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    target = float(payload["target_profit_pct"])
    market = payload["market"].get("target_profit", {})
    resistance_room = float(market.get("resistance_room_pct", target * 1.4))
    atr_room = float(market.get("atr_room_pct", target * 1.25))
    slippage = float(market.get("slippage_pct", 0.05))
    binance_fee = float(settings_get(settings, "binance_roundtrip_fee_pct", 0.20))
    system_commission = float(settings_get(settings, "system_roundtrip_commission_pct", 0.20))
    net_target = round(target - binance_fee - system_commission - slippage, 4)
    resistance_score = clamp((resistance_room / max(target, 0.01)) * 70)
    atr_score = clamp((atr_room / max(target, 0.01)) * 72)
    net_score = clamp((net_target / max(target, 0.01)) * 100)
    stop = float(payload.get("stop_loss_pct") or 1.2)
    stop_target_ratio = target / max(stop, 0.01)
    rr_score = clamp(stop_target_ratio * 70)
    volume_support = clamp(market.get("volume_support", 65))
    score = resistance_score * .30 + atr_score * .25 + net_score * .25 + rr_score * .15 + volume_support * .05
    detail = {
        "target_profit_pct": target, "resistance_room_pct": resistance_room, "atr_room_pct": atr_room,
        "binance_fee_pct": binance_fee, "system_commission_pct": system_commission, "slippage_pct": slippage,
        "net_target_profit_pct": net_target, "stop_loss_pct": stop, "risk_reward_ratio": round(stop_target_ratio, 3),
        "resistance_score": round(resistance_score, 2), "atr_score": round(atr_score, 2), "net_score": round(net_score, 2),
    }
    return round(clamp(score), 2), detail


def calculate_timeframe_alignment(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    tf = payload.get("timeframe", "15m")
    target = float(payload["target_profit_pct"])
    min_t, max_t = TARGET_BY_TIMEFRAME.get(tf, (0.6, 2.0))
    tf_fit = 90 if min_t <= target <= max_t else max(30, 80 - abs(target - ((min_t + max_t) / 2)) * 35)
    market = payload["market"].get("timeframe_alignment", {})
    upper_support = clamp(market.get("upper_tf_support", 65))
    lower_entry = clamp(market.get("lower_tf_entry", 68))
    daily_weekly_risk = clamp(market.get("daily_weekly_risk", 25))
    score = tf_fit * .35 + upper_support * .35 + lower_entry * .20 + (100 - daily_weekly_risk) * .10
    return round(clamp(score), 2), {"signal_timeframe": tf, "target_range": f"{min_t}-{max_t}%", "tf_fit": round(tf_fit,2), "upper_tf_support": upper_support, "lower_tf_entry": lower_entry, "daily_weekly_risk": daily_weekly_risk}


def calculate_news_risk(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    news = payload["market"].get("news_risk", {})
    macro = clamp(news.get("macro_risk", 25))
    regulation = clamp(news.get("regulation_risk", 20))
    exchange = clamp(news.get("exchange_risk", 15))
    coin = clamp(news.get("coin_specific_risk", 20))
    social = clamp(news.get("social_anomaly", 25))
    score = 100 - (macro*.25 + regulation*.20 + exchange*.20 + coin*.25 + social*.10)
    return round(clamp(score), 2), {"macro_risk": macro, "regulation_risk": regulation, "exchange_risk": exchange, "coin_specific_risk": coin, "social_anomaly": social}


def calculate_session_score(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    session = payload["market"].get("session", {})
    liquidity_hour = clamp(session.get("liquidity_hour", 65))
    volatility_hour = clamp(session.get("volatility_hour", 62))
    candle_close_risk = clamp(session.get("candle_close_risk", 20))
    weekend_risk = clamp(session.get("weekend_risk", 15))
    score = liquidity_hour*.40 + volatility_hour*.30 + (100-candle_close_risk)*.20 + (100-weekend_risk)*.10
    return round(clamp(score), 2), {"liquidity_hour": liquidity_hour, "volatility_hour": volatility_hour, "candle_close_risk": candle_close_risk, "weekend_risk": weekend_risk}


def calculate_liquidity(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    lq = payload["market"].get("liquidity", {})
    spread = clamp(lq.get("spread_score", 72))
    book = clamp(lq.get("order_book_depth", 70))
    volume = clamp(lq.get("volume_score", 68))
    slippage_risk = clamp(lq.get("slippage_risk", 20))
    order_size = clamp(lq.get("order_size_fit", 85))
    score = spread*.25 + book*.30 + volume*.25 + (100-slippage_risk)*.15 + order_size*.05
    return round(clamp(score), 2), {"spread_score": spread, "order_book_depth": book, "volume_score": volume, "slippage_risk": slippage_risk, "order_size_fit": order_size}


def calculate_volatility(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    vol = payload["market"].get("volatility", {})
    movement = clamp(vol.get("movement_room", 68))
    atr = clamp(vol.get("atr_fit", 70))
    wick_risk = clamp(vol.get("wick_risk", 25))
    impulse_risk = clamp(vol.get("impulse_risk", 30))
    score = movement*.35 + atr*.25 + (100-wick_risk)*.20 + (100-impulse_risk)*.20
    return round(clamp(score), 2), {"movement_room": movement, "atr_fit": atr, "wick_risk": wick_risk, "impulse_risk": impulse_risk}


def calculate_strategy_signal_quality(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    st = payload["market"].get("strategy_quality", {})
    general = clamp(st.get("general_win_rate", 64))
    coin = clamp(st.get("coin_success", 62))
    tf = clamp(st.get("timeframe_success", 65))
    h24 = clamp(st.get("last_24h", 60))
    d7 = clamp(st.get("last_7d", 63))
    drawdown = clamp(st.get("drawdown_score", 65))
    filters = clamp(st.get("filter_pass_quality", 68))
    score = general*.20 + coin*.20 + tf*.15 + h24*.15 + d7*.10 + drawdown*.10 + filters*.10
    return round(clamp(score), 2), {"general_win_rate": general, "coin_success": coin, "timeframe_success": tf, "last_24h": h24, "last_7d": d7, "drawdown_score": drawdown, "filter_pass_quality": filters}


def calculate_risk_reward(payload: Dict[str, Any], settings: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    target = float(payload["target_profit_pct"])
    stop = float(payload.get("stop_loss_pct") or 1.2)
    net = calculate_target_profit_fit(payload, settings)[1]["net_target_profit_pct"]
    rr = target / max(stop, 0.01)
    rr_score = clamp(rr*70)
    net_score = clamp((net / max(target, 0.01))*100)
    stop_score = clamp(100 - max(stop-target, 0)*25)
    daily_limit = clamp(payload["market"].get("risk_reward", {}).get("daily_limit_fit", 72))
    position_size = clamp(payload["market"].get("risk_reward", {}).get("position_size_fit", 75))
    score = rr_score*.35 + net_score*.25 + stop_score*.15 + daily_limit*.15 + position_size*.10
    return round(clamp(score), 2), {"risk_reward_ratio": round(rr, 3), "net_target_profit_pct": net, "stop_score": round(stop_score,2), "daily_limit_fit": daily_limit, "position_size_fit": position_size}


def calculate_correlation(payload: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    corr = payload["market"].get("correlation", {})
    open_corr = clamp(corr.get("open_position_correlation", 35))
    btc_corr = clamp(corr.get("btc_correlation", 55))
    sector_corr = clamp(corr.get("sector_correlation", 40))
    basket_risk = clamp(corr.get("basket_risk", 30))
    score = (100-open_corr)*.40 + (100-btc_corr)*.25 + (100-sector_corr)*.25 + (100-basket_risk)*.10
    return round(clamp(score), 2), {"open_position_correlation": open_corr, "btc_correlation": btc_corr, "sector_correlation": sector_corr, "basket_risk": basket_risk}


def calculate_all_scores(runtime: Dict[str, Any], settings: Dict[str, Any], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = get_market_payload(runtime, settings, signal)
    calculators = {
        "market_regime": lambda: calculate_market_regime(payload),
        "btc_trend": lambda: calculate_btc_trend(payload),
        "btc_dominance": lambda: calculate_btc_dominance(payload),
        "total2": lambda: calculate_total2(payload),
        "coin_strength": lambda: calculate_coin_strength(payload),
        "target_profit_fit": lambda: calculate_target_profit_fit(payload, settings),
        "timeframe_alignment": lambda: calculate_timeframe_alignment(payload),
        "news_risk": lambda: calculate_news_risk(payload),
        "session_score": lambda: calculate_session_score(payload),
        "liquidity": lambda: calculate_liquidity(payload),
        "volatility": lambda: calculate_volatility(payload),
        "strategy_signal_quality": lambda: calculate_strategy_signal_quality(payload),
        "risk_reward": lambda: calculate_risk_reward(payload, settings),
        "correlation": lambda: calculate_correlation(payload),
    }
    breakdown = {}
    score_breakdown = {}
    for key, fn in calculators.items():
        score, details = fn()
        meta = CRITERIA[key]
        contribution = round(score * float(meta["weight"]), 2)
        breakdown[key] = {
            "key": key,
            "label": meta["label"],
            "score": score,
            "weight": float(meta["weight"]),
            "weight_pct": round(float(meta["weight"])*100, 2),
            "contribution": contribution,
            "status": score_status(score),
            "details": details,
        }
        score_breakdown[key] = score
    total = round(sum(v["contribution"] for v in breakdown.values()), 2)
    return {"payload": payload, "score": total, "breakdown": breakdown, "score_breakdown": score_breakdown}


def build_hard_blocks(runtime: Dict[str, Any], settings: Dict[str, Any], scores: Dict[str, Any]) -> List[str]:
    payload = scores["payload"]
    breakdown = scores["breakdown"]
    blocks = []
    if settings_get(settings, "enabled", True) is False:
        blocks.append("Karabasan pasif")
    if not runtime.get("bot_running") and settings_get(settings, "require_bot_running", False):
        blocks.append("Bot kapalı")
    if bool(runtime.get("emergency_stop")):
        blocks.append("Acil durdurma aktif")
    target_detail = breakdown["target_profit_fit"]["details"]
    if target_detail["net_target_profit_pct"] <= 0:
        blocks.append("Net hedef kar negatif")
    if target_detail["resistance_room_pct"] < payload["target_profit_pct"]:
        blocks.append("Dirence mesafe hedef kardan düşük")
    if breakdown["liquidity"]["score"] < float(settings_get(settings, "minimum_liquidity_score", 50)):
        blocks.append("Likidite minimum seviyenin altında")
    if breakdown["news_risk"]["score"] < float(settings_get(settings, "minimum_news_score", 50)):
        blocks.append("Haber/risk skoru çok düşük")
    if breakdown["risk_reward"]["score"] < float(settings_get(settings, "minimum_risk_reward_score", 60)):
        blocks.append("Risk/ödül minimum seviyenin altında")
    if runtime.get("daily_loss_limit_reached"):
        blocks.append("Günlük zarar limiti dolmuş")
    if runtime.get("max_open_positions_reached"):
        blocks.append("Maksimum açık pozisyon dolmuş")
    return blocks


def decision_label(score: float, hard_blocks: List[str], min_score: float) -> Tuple[str, str]:
    if hard_blocks:
        return "block", "hard_block"
    if score < 50:
        return "block", "weak"
    if score < min_score:
        return "wait", "watch"
    if score < 80:
        return "allow", "controlled"
    return "allow", "strong"


def build_karabasan_score(runtime: Dict[str, Any], settings: Dict[str, Any], signal: Dict[str, Any] | None = None) -> Dict[str, Any]:
    scores = calculate_all_scores(runtime, settings, signal)
    min_score = float(settings_get(settings, "minimum_score", DEFAULT_MIN_SCORE))
    hard_blocks = build_hard_blocks(runtime, settings, scores)
    decision, confidence = decision_label(scores["score"], hard_blocks, min_score)
    sorted_items = sorted(scores["breakdown"].values(), key=lambda x: x["contribution"], reverse=True)
    main_reasons = [f"{item['label']}: {int(item['score'])}/100" for item in sorted_items[:3]]
    weak_reasons = [f"{item['label']} zayıf ({int(item['score'])}/100)" for item in sorted_items if item["score"] < 55]
    payload = scores["payload"]
    result = {
        "service": "karabasan",
        "symbol": payload["symbol"],
        "side": payload["side"],
        "timeframe": payload["timeframe"],
        "target_profit_pct": payload["target_profit_pct"],
        "karabasan_score": scores["score"],
        "minimum_score": min_score,
        "decision": decision,
        "confidence": confidence,
        "expected_profit_zone": estimate_profit_zone(scores),
        "main_reasons": main_reasons,
        "weak_reasons": weak_reasons[:3],
        "blocking_reasons": hard_blocks,
        "has_hard_block": bool(hard_blocks),
        "score_breakdown": scores["score_breakdown"],
        "breakdown_table": list(scores["breakdown"].values()),
        "admin_formula": build_formula_rows(scores["breakdown"]),
        "user_summary": build_user_summary(scores["score"], decision, hard_blocks, main_reasons),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def estimate_profit_zone(scores: Dict[str, Any]) -> str:
    target = float(scores["payload"]["target_profit_pct"])
    fit = scores["breakdown"]["target_profit_fit"]["score"] / 100
    low = max(0.0, target * (0.75 + fit * 0.1))
    high = target * (1.0 + fit * 0.25)
    return f"{low:.2f}% - {high:.2f}%"


def build_formula_rows(breakdown: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "criterion": item["label"],
            "score": item["score"],
            "weight_pct": item["weight_pct"],
            "contribution": item["contribution"],
            "formula": f"{item['score']} x %{item['weight_pct']} = {item['contribution']}",
            "status": item["status"],
        }
        for item in breakdown.values()
    ]


def build_user_summary(score: float, decision: str, hard_blocks: List[str], main_reasons: List[str]) -> Dict[str, Any]:
    if hard_blocks:
        reason = hard_blocks[0]
    elif decision == "allow":
        reason = "Piyasa hedef kar için uygun görünüyor."
    elif decision == "wait":
        reason = "Piyasa izleniyor; skor izin eşiğine yakın değil."
    else:
        reason = "Piyasa şu an hedef kar için uygun değil."
    return {
        "title": "Karabasan aktif",
        "score_label": f"Piyasa güven skoru: {int(score)}/100",
        "permission": "Açık" if decision == "allow" else "Kapalı" if decision == "block" else "Bekle",
        "reason": reason,
        "short_reasons": main_reasons[:3],
    }


def build_karabasan_summary(runtime: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    score = build_karabasan_score(runtime, settings)
    return {
        "visible_to_user": True,
        "admin_details_hidden": True,
        "title": "Karabasan",
        **score["user_summary"],
        "decision": score["decision"],
        "karabasan_score": score["karabasan_score"],
        "updated_at": score["updated_at"],
    }


def default_karabasan_settings() -> Dict[str, Any]:
    return {
        "enabled": True,
        "minimum_score": DEFAULT_MIN_SCORE,
        "target_profit_min_pct": DEFAULT_TARGET_MIN,
        "target_profit_max_pct": DEFAULT_TARGET_MAX,
        "target_profit_pct": 1.0,
        "default_timeframe": "15m",
        "minimum_liquidity_score": 50,
        "minimum_risk_reward_score": 60,
        "minimum_news_score": 50,
        "binance_roundtrip_fee_pct": 0.20,
        "system_roundtrip_commission_pct": 0.20,
        "weights": {k: v["weight"] for k, v in CRITERIA.items()},
        "timeframe_weights": TIMEFRAME_WEIGHTS,
        "hard_blocks": [
            "API bağlı değil", "Bot kapalı", "Kiralama süresi bitmiş", "Acil durdurma aktif",
            "Likidite çok düşük", "Spread çok yüksek", "Net hedef kar negatif",
            "Dirence mesafe hedeften düşük", "Haber riski çok yüksek",
            "Günlük zarar limiti dolmuş", "Maksimum açık pozisyon dolmuş",
            "Karabasan skoru 65 altında",
        ],
    }
