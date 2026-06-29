from services.karabasan_score_service import build_karabasan_score


def evaluate_karabasan_live_gate(runtime, settings, signal=None):
    result = build_karabasan_score(runtime, settings, signal)
    allowed = result["decision"] == "allow" and not result["has_hard_block"]
    return {
        "title": "Karabasan canlı emir kapısı",
        "allowed": allowed,
        "decision": result["decision"],
        "score": result["karabasan_score"],
        "minimum_score": result["minimum_score"],
        "blocking_reasons": result["blocking_reasons"],
        "chain": [
            "Bot açık mı?", "Kiralama aktif mi?", "API güvenli mi?", "Strateji sinyali var mı?",
            "Filtreler geçti mi?", "Risk kapısı geçti mi?", "Karabasan skoru yeterli mi?", "Hard block yok mu?",
        ],
    }
