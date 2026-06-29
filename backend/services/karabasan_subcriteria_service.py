from services.karabasan_score_service import build_karabasan_score


def build_karabasan_subcriteria(runtime, settings, signal=None):
    result = build_karabasan_score(runtime, settings, signal)
    return {
        "title": "Karabasan alt kriter analizi",
        "items": [
            {"criterion": row["label"], "score": row["score"], "details": row.get("details", {})}
            for row in result["breakdown_table"]
        ],
        "admin_note": "Her ana kriter açılabilir olmalı; admin alt kriterin skora etkisini görür.",
    }
