from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _num(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _indicator(key: str, label: str, score: float, detail: str) -> dict:
    score = round(_clamp(score), 1)
    if score >= 70:
        status = "Uygun"
        tone = "ok"
    elif score >= 55:
        status = "İzle"
        tone = "warn"
    else:
        status = "Zayıf"
        tone = "bad"
    return {"key": key, "label": label, "score": score, "status": status, "tone": tone, "detail": detail}


def _session_score(now: datetime) -> tuple[float, str]:
    hour = now.hour
    # UTC üzerinden sade ve deterministik seans okuması.
    if 7 <= hour <= 16:
        return 74.0, "Avrupa/ABD likidite penceresi aktif."
    if 0 <= hour <= 6:
        return 58.0, "Asya seansı; likidite kontrollü izlenir."
    return 66.0, "ABD kapanış/uzatma saatleri; hareket takip edilir."


def build_automatic_market_decision(runtime_data: dict | None, settings: dict | None) -> dict:
    """Compact market-confidence model for the rentable dashboard.

    This is a product-ready visual/decision contract, not the final deep AI engine.
    It intentionally uses available runtime data and deterministic fallbacks so the
    UI can already show how automatic mode will reason.
    """
    runtime = runtime_data if isinstance(runtime_data, dict) else {}
    setting_map = settings if isinstance(settings, dict) else {}
    bot_settings = setting_map.get("bot") if isinstance(setting_map.get("bot"), dict) else {}
    last_scan = runtime.get("last_scan") if isinstance(runtime.get("last_scan"), dict) else {}
    candidates = last_scan.get("candidates") if isinstance(last_scan.get("candidates"), list) else []
    scan_rows = last_scan.get("scan_rows") if isinstance(last_scan.get("scan_rows"), list) else []
    rejection_breakdown = last_scan.get("rejection_breakdown") if isinstance(last_scan.get("rejection_breakdown"), dict) else {}
    rejection_count = _num(last_scan.get("rejected_count"), 0)
    scanned = max(_num(last_scan.get("scanned"), 0), 1)
    candidate_count = _num(last_scan.get("candidates_count"), len(candidates))
    candidate_ratio = candidate_count / scanned

    now = datetime.now(timezone.utc)
    session, session_detail = _session_score(now)

    avg_candidate_score = 0.0
    if candidates:
        avg_candidate_score = sum(_num(item.get("score"), 0) for item in candidates if isinstance(item, dict)) / max(len(candidates), 1)
    elif scan_rows:
        avg_candidate_score = sum(_num(item.get("score"), 0) for item in scan_rows if isinstance(item, dict)) / max(len(scan_rows), 1)
    if avg_candidate_score <= 0:
        avg_candidate_score = 62.0

    spread_rejections = _num(rejection_breakdown.get("spread") or rejection_breakdown.get("spread_guard"), 0)
    volume_rejections = _num(rejection_breakdown.get("volume") or rejection_breakdown.get("volume_guard"), 0)
    risk_rejections = _num(rejection_breakdown.get("risk") or rejection_breakdown.get("risk_rejected"), 0)

    market_trend = 58.0 + min(candidate_ratio * 380.0, 22.0) + (4.0 if candidate_count > 0 else -3.0)
    btc_trend = 64.0 + min(avg_candidate_score / 10.0, 9.0) - min(risk_rejections * 1.4, 8.0)
    dominance = 63.0 - min(risk_rejections * 1.2, 10.0) + (3.0 if candidate_count >= 2 else 0.0)
    total2 = 57.0 + min(candidate_count * 4.5, 17.0) - min(rejection_count / scanned * 18.0, 14.0)
    news_risk = 70.0 - min(risk_rejections * 4.0, 22.0)
    volatility = 68.0 - min(spread_rejections * 3.2, 18.0) + min(candidate_count * 1.5, 5.0)
    liquidity = 72.0 - min(volume_rejections * 4.0, 20.0) - min(spread_rejections * 1.5, 10.0)
    strategy_confidence = 55.0 + min(avg_candidate_score / 2.0, 32.0)

    indicators = [
        _indicator("market_trend", "Market trend", market_trend, "Tarama aday oranı ve genel piyasa ivmesi."),
        _indicator("btc_trend", "BTC trend", btc_trend, "BTC yönü için mevcut tarama gücüyle üretilen ön skor."),
        _indicator("btc_dominance", "BTC dominance", dominance, "Dominance baskısı yüksekse altcoin girişleri azaltılır."),
        _indicator("total2", "TOTAL2", total2, "Altcoin toplam piyasa gücü için karar yardımcısı."),
        _indicator("news_risk", "Haber/risk", news_risk, "Haber ve ani risk tarafı düşük güvenliyse işlem bekler."),
        _indicator("session", "Borsa seansı", session, session_detail),
        _indicator("volatility", "Volatilite", volatility, "Çok düşük veya düzensiz oynaklık giriş kalitesini düşürür."),
        _indicator("liquidity", "Likidite", liquidity, "Hacim ve spread kalitesi yeterli olmalı."),
        _indicator("strategy_confidence", "Strateji güveni", strategy_confidence, "Aktif strateji sinyallerinin ortalama gücü."),
    ]
    overall = round(sum(item["score"] for item in indicators) / max(len(indicators), 1), 1)
    threshold = _num(bot_settings.get("automatic_confidence_threshold"), 65.0)
    allow_trade = overall >= threshold
    control_mode = str(runtime.get("bot_control_mode") or bot_settings.get("control_mode") or "closed").lower()
    if control_mode not in {"closed", "open", "automatic"}:
        control_mode = "closed"

    if control_mode == "automatic":
        headline = "Piyasa güveni yeterli, bot işlem arayabilir." if allow_trade else "Piyasa güveni zayıf, bot yeni işleme girmemeli."
    elif control_mode == "open":
        headline = "Bot manuel açık; risk kapıları yine işlem öncesi kontrol eder."
    else:
        headline = "Bot kapalı; sistem sadece izleme yapar."

    return {
        "status": "ok",
        "control_mode": control_mode,
        "control_label": {"closed": "Kapalı", "open": "Açık", "automatic": "Otomatik"}.get(control_mode, "Kapalı"),
        "overall_score": overall,
        "threshold": round(threshold, 1),
        "allow_trade": bool(allow_trade),
        "decision": "ALLOW" if allow_trade else "WAIT",
        "headline": headline,
        "indicators": indicators,
        "strategy_signal_count": int(candidate_count),
        "model_stage": "visual_contract_v1",
        "deep_ai_ready": False,
        "generated_at": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "simple_rule": "Otomatik modda strateji fırsat bulsa bile genel piyasa güveni eşik altındaysa yeni işlem açılmaz.",
    }


def build_automatic_market_decision_quality_report() -> dict:
    strong_runtime = {
        "bot_control_mode": "automatic",
        "last_scan": {"scanned": 100, "candidates_count": 8, "candidates": [{"score": 76}, {"score": 82}], "rejected_count": 12, "rejection_breakdown": {}},
    }
    weak_runtime = {
        "bot_control_mode": "automatic",
        "last_scan": {"scanned": 100, "candidates_count": 0, "candidates": [], "rejected_count": 85, "rejection_breakdown": {"risk": 6, "spread": 8, "volume": 7}},
    }
    settings = {"bot": {"automatic_confidence_threshold": 65}}
    strong = build_automatic_market_decision(strong_runtime, settings)
    weak = build_automatic_market_decision(weak_runtime, settings)
    blockers = []
    if strong.get("control_mode") != "automatic" or strong.get("overall_score", 0) <= 0:
        blockers.append("automatic_contract_missing")
    if len(strong.get("indicators") or []) < 8:
        blockers.append("indicator_count_low")
    if weak.get("allow_trade") is True and weak.get("overall_score", 100) < weak.get("threshold", 65):
        blockers.append("weak_market_should_not_allow")
    return {"status": "ok" if not blockers else "blocked", "blockers": blockers, "strong_sample": strong, "weak_sample": weak}
