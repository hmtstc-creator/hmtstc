from __future__ import annotations

from typing import Any, Dict

from services.binance_futures_models import now_iso


def build_phase3_mobile_futures_experience(permission: Dict[str, Any], context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    context = context or {}
    critical_action = str(context.get("critical_action", "none"))
    requires_modal = critical_action in {"open_live", "enable_auto", "emergency_stop", "close_position"}
    return {
        "service": "futures_phase3_mobile_experience",
        "phase": "Faz3-4",
        "checked_at": now_iso(),
        "mobile_first": True,
        "layout_contract": {
            "cards": "single_column",
            "position_card": "compact",
            "admin_details": "collapsible",
            "risk_and_pnl": "top_visible",
            "emergency_stop": "sticky_bottom",
        },
        "button_contract": {
            "open": {"large_touch_target": True, "confirm_modal": True},
            "closed": {"large_touch_target": True, "confirm_modal": False},
            "auto": {"large_touch_target": True, "confirm_modal": True},
            "emergency_stop": {"large_touch_target": True, "confirm_modal": True, "sticky": True},
        },
        "modal_required_for_action": requires_modal,
        "modal_text": "Bu işlem Futures botunu canlı etkiler. Onaylıyor musun?" if requires_modal else "Onay gerekmiyor.",
        "wrong_tap_prevention": True,
        "accessibility": {"min_button_height_px": 44, "risk_color_text_pairing": True, "plain_language_status": True},
        "user_can_change_live_permission": False,
        "futures_visible": bool(permission.get("futures_enabled")),
    }
