from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso, public_permission
from services.futures_phase2_alarm_service import build_phase2_alarm_center
from services.futures_phase2_live_position_service import build_phase2_live_position_monitor


def _safe_num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def build_phase3_user_futures_experience(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Customer-facing Futures view.

    Keeps the rented user away from technical exchange details while still
    explaining what the bot is doing and why it may be waiting.
    """
    context = context or {}
    visible = bool(permission.get("futures_enabled"))
    mode = permission.get("futures_user_control_mode") or "closed"
    days_left = _safe_num(context.get("rental_days_left", runtime.get("rental_days_left", 7)), 0)
    karabasan = context.get("karabasan_futures") or {"score": context.get("karabasan_score", 0), "decision": context.get("decision", "wait")}
    score = _safe_num(karabasan.get("karabasan_futures_score", karabasan.get("score", 0)), 0)
    monitor = build_phase2_live_position_monitor(runtime, permission, context.get("position_context") or context)
    alarm_center = build_phase2_alarm_center(runtime, permission, connection, context)

    if not visible:
        status = "Futures alanı owner onayı bekliyor."
    elif days_left <= 0:
        status = "Kiralama süresi bitti; Futures bekleme modunda."
    elif permission.get("futures_emergency_stop"):
        status = "Acil durdurma aktif; yeni işlem açılmıyor."
    elif not alarm_center.get("new_trade_allowed"):
        status = alarm_center.get("user_alarm_summary")
    elif score >= 65 and mode in {"open", "auto", "automatic"}:
        status = "Futures bot hazır; Karabasan ve risk kapıları uygun fırsat bekliyor."
    elif mode == "closed":
        status = "Futures bot kapalı."
    else:
        status = "Bot bekliyor: Piyasa şu an işlem için uygun değil."

    user_cards: List[Dict[str, Any]] = [
        {"title": "Futures Durumu", "value": "Açık" if visible else "Kapalı", "tone": "success" if visible else "muted"},
        {"title": "Bot Modu", "value": mode, "tone": "warning" if mode == "auto" else "default"},
        {"title": "Karabasan", "value": f"{int(score)}/100", "tone": "success" if score >= 65 else "danger"},
        {"title": "Kalan Gün", "value": days_left, "tone": "danger" if days_left <= 1 else "default"},
        {"title": "Açık Pozisyon", "value": monitor.get("open_position_count", 0), "tone": monitor.get("global_risk_status", "default")},
    ]

    return {
        "service": "futures_phase3_user_experience",
        "phase": "Faz3-1",
        "checked_at": now_iso(),
        "visible_to_user": visible,
        "vip_area": True,
        "simple_status": status,
        "user_cards": user_cards,
        "safe_user_messages": {
            "waiting": "Bot bekliyor: Piyasa şu an işlem için uygun değil.",
            "opened": "İşlem açıldı: Karabasan skoru güçlü ve risk güvenli.",
            "blocked": alarm_center.get("user_alarm_summary", "İşlem açılmadı: Risk kapısı izin vermedi."),
        },
        "hidden_from_user": ["owner_commission_income", "api_secret", "raw_endpoint_details", "internal_gate_json"],
        "permission_public": public_permission(permission, is_owner=False),
        "position_summary": {
            "open_position_count": monitor.get("open_position_count", 0),
            "risk_status": monitor.get("global_risk_status"),
            "user_summary": monitor.get("user_summary"),
        },
        "alarm_summary": alarm_center.get("user_alarm_summary"),
        "rental_ready_user_experience": visible and days_left > 0 and not permission.get("futures_emergency_stop"),
    }
