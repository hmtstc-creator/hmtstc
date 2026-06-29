from services.karabasan_score_service import build_karabasan_score


def build_karabasan_target_profit_fit(runtime, settings, signal=None):
    result = build_karabasan_score(runtime, settings, signal)
    row = next((r for r in result["breakdown_table"] if r["key"] == "target_profit_fit"), {})
    detail = row.get("details", {})
    return {
        "title": "Karabasan hedef kar uygunluğu",
        "score": row.get("score"),
        "weight_pct": row.get("weight_pct"),
        "contribution": row.get("contribution"),
        "formula": "Net Hedef Kar = Hedef Kar - Binance Fee - Sistem Komisyonu - Tahmini Slippage",
        "critical_rules": ["Dirence mesafe hedef kardan düşükse işlem açma", "Net hedef kar <= 0 ise işlem açma"],
        "details": detail,
    }
