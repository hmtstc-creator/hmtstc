from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from services.binance_futures_models import BINANCE_FUTURES_OFFICIAL_ENDPOINTS, normalize_permission, now_iso
from services.futures_phase1_karabasan_bridge_service import build_futures_karabasan_execution_bridge


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_phase1_order_preview(
    runtime: Dict[str, Any],
    settings: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal = signal or {}
    p = normalize_permission({"futures_permissions": permission})
    bridge = build_futures_karabasan_execution_bridge(runtime, settings, p, connection, signal)
    symbol = str(signal.get("symbol") or bridge.get("symbol") or "BTCUSDT").upper()
    side = str(signal.get("side") or bridge.get("side") or "long").lower()
    notional = min(_num(signal.get("notional"), p.get("futures_max_notional_per_trade", 50)), float(p.get("futures_max_notional_per_trade", 50)))
    leverage = min(int(_num(signal.get("leverage"), p.get("futures_max_leverage", 2))), int(p.get("futures_max_leverage", 2)))
    tp = _num(signal.get("take_profit_pct") or signal.get("target_profit_pct"), 0)
    sl = _num(signal.get("stop_loss_pct"), 0)
    blocks: List[str] = list(bridge.get("blocking_reasons") or [])
    if symbol not in set(p.get("futures_allowed_symbols") or []):
        blocks.append("Symbol owner izin listesinde değil")
    if side == "short" and not p.get("futures_short_enabled"):
        blocks.append("Short işlemler owner tarafından kapalı")
    if leverage > int(p.get("futures_max_leverage", 2)):
        blocks.append("Leverage owner limitini aşıyor")
    if notional <= 0 or notional > float(p.get("futures_max_notional_per_trade", 50)):
        blocks.append("İşlem büyüklüğü owner limitine uygun değil")
    if tp <= 0:
        blocks.append("Take profit eksik")
    if sl <= 0:
        blocks.append("Stop loss eksik")

    payload = {
        "symbol": symbol,
        "side": "BUY" if side == "long" else "SELL",
        "positionSide": "BOTH" if p.get("futures_position_mode") == "one_way" else side.upper(),
        "type": str(signal.get("entry_type") or "MARKET").upper(),
        "quantity": signal.get("quantity", "CALCULATE_FROM_NOTIONAL"),
        "notional": round(notional, 4),
        "leverage": leverage,
        "marginType": "ISOLATED",
        "takeProfitPct": tp,
        "stopLossPct": sl,
        "reduceOnly": False,
    }
    checksum_basis = json_safe = f"{payload['symbol']}|{payload['side']}|{payload['notional']}|{payload['leverage']}|{tp}|{sl}|{bridge.get('karabasan_futures_score')}"
    checksum = hashlib.sha256(json_safe.encode("utf-8")).hexdigest()
    return {
        "service": "futures_phase1_order_preview",
        "phase": "Faz1-5",
        "created_at": now_iso(),
        "dry_run": True,
        "real_order_sent": False,
        "submit_endpoint_locked": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["new_order"],
        "test_endpoint": BINANCE_FUTURES_OFFICIAL_ENDPOINTS["test_order"],
        "order_payload_preview": payload,
        "bridge": bridge,
        "status": "ready_for_tp_sl_and_liquidation_checks" if not blocks else "blocked",
        "blocking_reasons": blocks,
        "evidence": {"checksum": checksum, "basis": checksum_basis},
        "user_message": "İşlem hazırlandı; son TP/SL ve liquidation kontrolleri bekleniyor." if not blocks else "İşlem hazırlanmadı: " + blocks[0],
    }
