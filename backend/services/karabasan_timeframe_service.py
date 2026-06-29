from services.karabasan_score_service import TARGET_BY_TIMEFRAME, TIMEFRAME_WEIGHTS, build_karabasan_score


def build_karabasan_timeframe_analysis(runtime, settings, signal=None):
    result = build_karabasan_score(runtime, settings, signal)
    row = next((r for r in result["breakdown_table"] if r["key"] == "timeframe_alignment"), {})
    return {
        "title": "Karabasan zaman dilimi analizi",
        "score": row.get("score"),
        "weight_pct": row.get("weight_pct"),
        "contribution": row.get("contribution"),
        "timeframe_weights": TIMEFRAME_WEIGHTS,
        "target_by_timeframe": TARGET_BY_TIMEFRAME,
        "details": row.get("details", {}),
        "rule": "5m kısa hedef, 15m orta hedef, 1h/4h güçlü hedef; 1D/1W büyük yön filtresidir.",
    }
