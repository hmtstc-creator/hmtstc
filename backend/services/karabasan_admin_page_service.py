from services.karabasan_score_service import build_karabasan_score


def build_karabasan_admin_page(runtime, settings, signal=None):
    result = build_karabasan_score(runtime, settings, signal)
    return {
        "title": "Karabasan Admin Sayfası",
        "description": "Admin her kriterin skor, ağırlık, katkı ve alt kriter detayını analiz eder.",
        "general": {
            "symbol": result["symbol"],
            "target_profit_pct": result["target_profit_pct"],
            "score": result["karabasan_score"],
            "decision": result["decision"],
            "confidence": result["confidence"],
        },
        "breakdown_table": result["breakdown_table"],
        "formula_table": result["admin_formula"],
        "hard_blocks": result["blocking_reasons"],
        "explanation": result["user_summary"]["reason"],
    }
