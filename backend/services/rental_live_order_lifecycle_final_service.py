from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _ok(value: bool) -> str:
    return "Hazır" if value else "Kontrol gerekli"


def build_rental_live_order_lifecycle_final(
    lifecycle: dict,
    trade_ledger: dict,
    live_ops_guard: dict,
    *,
    role: str = "user",
    user: str = "default",
) -> dict:
    """Kiralanabilir canlı ürün için emir yaşam döngüsü final kontrolü.

    Bu servis emir göndermez. Summary/Admin tarafına canlı emir zincirinin
    hangi noktalarının gerçek veriye bağlanması gerektiğini ve mevcut görünürlük
    durumunu sade şekilde döner.
    """
    lifecycle = _as_dict(lifecycle)
    trade_ledger = _as_dict(trade_ledger)
    live_ops_guard = _as_dict(live_ops_guard)
    role = str(role or "user").lower()
    is_owner = role in {"owner", "admin", "superadmin"}

    orders = _as_list(lifecycle.get("orders"))
    positions = _as_list(lifecycle.get("positions"))
    open_positions = _as_list(lifecycle.get("open_positions"))
    evidence = _as_list(lifecycle.get("recent_evidence"))
    events = _as_list(lifecycle.get("recent_events"))
    blockers = _as_list(lifecycle.get("blockers")) + _as_list(live_ops_guard.get("blockers"))
    ledger_summary = _as_dict(trade_ledger.get("summary"))

    has_order_chain = bool(orders or lifecycle.get("last_order"))
    has_position_tracking = bool(positions or open_positions)
    has_close_preview = bool(_as_list(lifecycle.get("close_previews")))
    has_evidence = bool(evidence or events or lifecycle.get("evidence_count"))
    has_net_pnl = any(key in ledger_summary for key in ("net_pnl_usdt", "gross_pnl_usdt", "platform_commission_usdt", "binance_fee_usdt"))
    gate_clear = not bool(blockers)

    checks = [
        {"area": "Emir ön kontrol", "current": _ok(gate_clear), "expected": "Paket, ödeme, API, risk ve acil kilit geçmeli", "ok": gate_clear, "action": "Canlı kullanım guard engeli yoksa emir zinciri başlar."},
        {"area": "Order ID", "current": "Var" if has_order_chain else "Veri bekliyor", "expected": "Binance order id kayıt altına alınmalı", "ok": has_order_chain, "action": "Gerçek emir sonrası order id ledger/lifecycle içine yazılmalı."},
        {"area": "Fill takibi", "current": "Var" if has_position_tracking else "Veri bekliyor", "expected": "Executed qty, fiyat ve durum izlenmeli", "ok": has_position_tracking, "action": "Fill cevabı pozisyon takip modeline bağlanmalı."},
        {"area": "Kapanış", "current": "Preview var" if has_close_preview else "Preview bekliyor", "expected": "Pozisyon kapatma ön izlemesi ve onayı olmalı", "ok": has_close_preview or not open_positions, "action": "Açık pozisyon varsa kapatma preview üretilmeli."},
        {"area": "Net PnL", "current": "Bağlı" if has_net_pnl else "Veri bekliyor", "expected": "Brüt - Binance fee - sistem payı görünmeli", "ok": has_net_pnl, "action": "Trade ledger net PnL canlı kapanışa bağlanmalı."},
        {"area": "Kanıt", "current": "Var" if has_evidence else "Veri bekliyor", "expected": "Her kritik adım checksum/evidence kaydı üretmeli", "ok": has_evidence, "action": "Submit, fill, close ve PnL kayıtları evidence ile dondurulmalı."},
        {"area": "Kullanıcı görünümü", "current": "Summary" if not is_owner else "Summary + Admin", "expected": "Kullanıcı sadece canlı log ve net sonucu görmeli", "ok": True, "action": "Owner gelir detayı son kullanıcıya gösterilmez."},
    ]

    failed = [item for item in checks if not item.get("ok")]
    return {
        "status": "ready" if not failed else "review",
        "user": user,
        "role": role,
        "headline": "Canlı emir yaşam döngüsü submit, fill, close, net PnL ve evidence zinciriyle izlenir.",
        "summary": {
            "order_count": len(orders),
            "position_count": len(positions),
            "open_position_count": len(open_positions),
            "evidence_count": int(lifecycle.get("evidence_count") or len(evidence)),
            "blocker_count": len(blockers),
            "net_pnl_connected": has_net_pnl,
            "owner_only_details": is_owner,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": "Gerçek emir/fill/close kayıtlarını Binance cevabıyla doğrula." if failed else "Canlı emir lifecycle final kontrolü OK.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
