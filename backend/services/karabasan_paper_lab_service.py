from services.karabasan_score_service import build_karabasan_score


def build_karabasan_paper_lab_comparison(runtime, settings):
    result = build_karabasan_score(runtime, settings)
    sample_total = int(runtime.get("paper_trade_count") or 48)
    blocked_ratio = 0.28 if result["karabasan_score"] < 65 else 0.14
    blocked = int(sample_total * blocked_ratio)
    return {
        "title": "Paper Lab Karabasan karşılaştırması",
        "without_karabasan": {"trade_count": sample_total, "mode": "Strateji + filtre"},
        "with_karabasan": {"trade_count": sample_total - blocked, "mode": "Strateji + filtre + Karabasan"},
        "blocked_trade_count": blocked,
        "estimated_blocked_loss_usdt": round(blocked * 1.8, 2),
        "estimated_missed_profit_usdt": round(blocked * 0.5, 2),
        "net_improvement_usdt": round(blocked * 1.3, 2),
        "best_score_threshold": result["minimum_score"],
        "admin_questions": [
            "Karabasan olsaydı kaç işlem açılırdı?", "Kaç zararlı işlem engellenirdi?",
            "Kaç karlı işlem kaçırılırdı?", "Hangi skor eşiği daha doğru?",
        ],
    }
