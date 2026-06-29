from services.karabasan_score_service import default_karabasan_settings


def build_karabasan_admin_settings_panel(settings):
    current = settings.get("karabasan") or default_karabasan_settings()
    return {
        "title": "Karabasan admin ayar paneli",
        "editable": True,
        "fields": [
            {"key": "minimum_score", "label": "Minimum Karabasan skoru", "value": current.get("minimum_score", 65)},
            {"key": "target_profit_min_pct", "label": "Minimum hedef kar %", "value": current.get("target_profit_min_pct", 0.6)},
            {"key": "target_profit_max_pct", "label": "Maksimum hedef kar %", "value": current.get("target_profit_max_pct", 2.0)},
            {"key": "minimum_liquidity_score", "label": "Minimum likidite", "value": current.get("minimum_liquidity_score", 50)},
            {"key": "minimum_risk_reward_score", "label": "Minimum risk/ödül", "value": current.get("minimum_risk_reward_score", 60)},
            {"key": "minimum_news_score", "label": "Minimum haber güveni", "value": current.get("minimum_news_score", 50)},
        ],
        "hard_blocks": current.get("hard_blocks", []),
        "weights": current.get("weights", {}),
    }
