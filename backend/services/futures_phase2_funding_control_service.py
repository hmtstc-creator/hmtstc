from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def build_phase2_funding_control(
    permission: Dict[str, Any],
    market: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Funding risk gate for real Futures live preparation.

    It is intentionally exchange-adapter agnostic here: Binance data can be
    passed in from a connector, testnet reader, or cached market snapshot.
    """
    market = market or {}
    side = str(market.get("side") or market.get("position_side") or "long").lower()
    funding_rate_pct = _num(market.get("funding_rate_pct"), _num(market.get("funding_rate"), 0.0) * 100)
    minutes_to_funding = _num(market.get("minutes_to_next_funding"), 240)
    max_abs_rate = _num(permission.get("futures_max_funding_rate_pct"), 0.08)
    warning_abs_rate = _num(permission.get("futures_warning_funding_rate_pct"), max_abs_rate * 0.65)
    avoid_window_min = _num(permission.get("futures_funding_avoid_window_min"), 20)

    abs_rate = abs(funding_rate_pct)
    blocking_reasons: List[str] = []
    warnings: List[str] = []

    if not permission.get("futures_enabled"):
        blocking_reasons.append("Futures yetkisi kapalı")
    if abs_rate > max_abs_rate:
        blocking_reasons.append("Funding rate owner limitini aşıyor")
    elif abs_rate > warning_abs_rate:
        warnings.append("Funding rate uyarı seviyesinde")
    if minutes_to_funding <= avoid_window_min and abs_rate > warning_abs_rate:
        blocking_reasons.append("Funding zamanı yaklaştı ve oran riskli")

    direction_effect = "neutral"
    if funding_rate_pct > 0 and side in {"long", "buy"}:
        direction_effect = "long_pays_funding"
    elif funding_rate_pct < 0 and side in {"short", "sell"}:
        direction_effect = "short_pays_funding"
    elif funding_rate_pct > 0 and side in {"short", "sell"}:
        direction_effect = "short_receives_funding"
    elif funding_rate_pct < 0 and side in {"long", "buy"}:
        direction_effect = "long_receives_funding"

    risk_score = max(0, min(100, 100 - (abs_rate / max(max_abs_rate, 0.0001)) * 70))
    if minutes_to_funding <= avoid_window_min:
        risk_score = max(0, risk_score - 15)

    return {
        "service": "futures_phase2_funding_control",
        "phase": "Faz2-1",
        "checked_at": now_iso(),
        "funding_rate_pct": round(funding_rate_pct, 6),
        "max_allowed_funding_rate_pct": max_abs_rate,
        "minutes_to_next_funding": minutes_to_funding,
        "funding_direction_effect": direction_effect,
        "funding_risk_score": round(risk_score, 2),
        "funding_gate_passed": not blocking_reasons,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "karabasan_effect": "high_risk_hard_block" if blocking_reasons else ("score_penalty" if warnings else "score_support"),
        "user_message": "Funding riski uygun." if not blocking_reasons else "Funding riski nedeniyle yeni işlem bekletiliyor.",
        "admin_detail_enabled": True,
    }
