from datetime import datetime, timezone
from services.karabasan_score_service import build_karabasan_score


def build_karabasan_decision_history(runtime, settings, signal=None):
    current = build_karabasan_score(runtime, settings, signal)
    history = list(runtime.get("karabasan_history") or [])
    if not history:
        history = [
            {"time": datetime.now(timezone.utc).isoformat(), "symbol": current["symbol"], "score": current["karabasan_score"], "decision": current["decision"], "reason": current["user_summary"]["reason"]}
        ]
    return {
        "title": "Karabasan karar geçmişi",
        "current": {"score": current["karabasan_score"], "decision": current["decision"], "reason": current["user_summary"]["reason"]},
        "history": history[-100:],
        "fields": ["time", "symbol", "score", "decision", "reason"],
    }
