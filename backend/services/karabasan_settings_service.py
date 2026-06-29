from services.karabasan_score_service import CRITERIA, TIMEFRAME_WEIGHTS, default_karabasan_settings


def build_karabasan_settings_contract(settings):
    current = settings.get("karabasan") or default_karabasan_settings()
    weights = current.get("weights") or {k: v["weight"] for k, v in CRITERIA.items()}
    total_weight = round(sum(float(v) for v in weights.values()), 6)
    return {
        "title": "Karabasan ayar sözleşmesi",
        "minimum_score": current.get("minimum_score", 65),
        "target_profit_min_pct": current.get("target_profit_min_pct", 0.6),
        "target_profit_max_pct": current.get("target_profit_max_pct", 2.0),
        "weights": weights,
        "weight_total": total_weight,
        "weight_total_ok": abs(total_weight - 1.0) < 0.0001,
        "timeframe_weights": current.get("timeframe_weights") or TIMEFRAME_WEIGHTS,
        "admin_editable_fields": [
            "minimum_score", "target_profit_min_pct", "target_profit_max_pct", "weights",
            "timeframe_weights", "minimum_liquidity_score", "minimum_risk_reward_score", "minimum_news_score",
        ],
    }
