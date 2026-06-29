from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import normalize_permission, now_iso

ALLOWED_USER_MODES = ["closed", "open", "automatic", "emergency_stop"]


def normalize_control_mode(value: Any) -> str:
    text = str(value or "closed").strip().lower().replace("kapalı", "closed").replace("açık", "open")
    return text if text in ALLOWED_USER_MODES else "closed"


def build_user_futures_control_contract(permission: Dict[str, Any], requested_mode: Any | None = None) -> Dict[str, Any]:
    p = normalize_permission({"futures_permissions": permission})
    mode = normalize_control_mode(requested_mode if requested_mode is not None else p.get("futures_user_control_mode"))
    blocks: List[str] = []
    if not p.get("futures_enabled"):
        blocks.append("Futures alanı owner tarafından açılmadı")
    if mode in {"open", "automatic"} and p.get("futures_emergency_stop"):
        blocks.append("Emergency stop aktif")
    if mode in {"open", "automatic"} and p.get("futures_access_level") in {"futures_disabled", "futures_suspended"}:
        blocks.append("Kullanıcı Futures erişim seviyesi işlem açmaya uygun değil")

    return {
        "service": "futures_phase1_user_control_contract",
        "phase": "Faz1-3",
        "checked_at": now_iso(),
        "requested_mode": mode,
        "button_set": [
            {"mode": "closed", "label": "Kapalı", "effect": "Yeni Futures işlem açılmaz; açık pozisyon izlenir."},
            {"mode": "open", "label": "Açık", "effect": "Karabasan + Risk Gate izin verirse işlem arar."},
            {"mode": "automatic", "label": "Otomatik", "effect": "Sistem piyasa güvenine göre bekler veya işlem arar."},
            {"mode": "emergency_stop", "label": "Acil Durdur", "effect": "Yeni emir anında durur; kapatma politikası ayrıca uygulanır."},
        ],
        "user_visible_status": "Hazır" if not blocks and mode != "closed" else ("Kapalı" if mode == "closed" else "Bloklu"),
        "can_search_new_trade": not blocks and mode in {"open", "automatic"},
        "new_order_blocked": bool(blocks) or mode in {"closed", "emergency_stop"},
        "blocking_reasons": blocks,
        "admin_trace": {
            "owner_controls_required": True,
            "mode_change_is_auditable": True,
            "emergency_stop_has_priority": True,
        },
    }
