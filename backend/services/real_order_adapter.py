from __future__ import annotations

from uuid import uuid4

from core.storage import now_iso
from services.real_trade_safety_service import build_real_trade_safety_status


def build_real_order_dry_run(data: dict, settings: dict, order: dict) -> dict:
    safety = build_real_trade_safety_status(data, settings)
    symbol = str((order or {}).get("symbol") or "").upper().strip()
    side = str((order or {}).get("side") or "BUY").upper().strip()
    usdt_size = float((order or {}).get("usdt_size") or 0)
    blockers = list(safety.get("blockers", []))
    if not symbol.endswith("USDT"):
        blockers.append("symbol_not_usdt_spot")
    if side not in {"BUY", "SELL"}:
        blockers.append("invalid_side")
    if usdt_size <= 0:
        blockers.append("invalid_usdt_size")
    return {
        "status": "blocked" if blockers else "dry_run_ready",
        "dry_run": True,
        "real_order_created": False,
        "order_id": str(uuid4()),
        "symbol": symbol,
        "side": side,
        "usdt_size": usdt_size,
        "checked_at": now_iso(),
        "blockers": blockers,
        "safety": safety,
        "message": "Gerçek emir adaptörü dry-run modunda. Safety layer geçmeden canlı emir üretmez.",
    }
