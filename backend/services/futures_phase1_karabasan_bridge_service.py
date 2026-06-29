from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_karabasan_service import build_karabasan_futures_score
from services.binance_futures_models import now_iso
from services.binance_futures_risk_service import futures_hard_blocks
from services.futures_phase1_user_control_service import build_user_futures_control_contract


def build_futures_karabasan_execution_bridge(
    runtime: Dict[str, Any],
    settings: Dict[str, Any],
    permission: Dict[str, Any],
    connection: Dict[str, Any],
    signal: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal = signal or {}
    user_control = build_user_futures_control_contract(permission, signal.get("control_mode"))
    score = build_karabasan_futures_score(runtime, settings, permission, connection, signal)
    hard_blocks: List[str] = futures_hard_blocks(
        permission,
        connection,
        signal,
        open_positions=len(runtime.get("futures_open_positions", [])),
        daily_loss=float(runtime.get("futures_daily_loss", 0) or 0),
    )
    blocks = []
    if user_control.get("new_order_blocked"):
        blocks.extend(user_control.get("blocking_reasons") or ["Kullanıcı Futures modu işlem açmaya uygun değil"])
    if score.get("decision") != "allow":
        blocks.append("Karabasan Futures izin vermedi")
    blocks.extend([b for b in hard_blocks if b not in blocks])

    return {
        "service": "futures_phase1_karabasan_execution_bridge",
        "phase": "Faz1-4",
        "checked_at": now_iso(),
        "flow": ["strategy_signal", "filters", "spot_karabasan", "futures_risk_score", "hard_blocks", "execution_gate"],
        "symbol": score.get("symbol"),
        "side": score.get("side"),
        "karabasan_futures_score": score.get("karabasan_futures_score"),
        "decision": "allow_execution_gate" if not blocks else "blocked_before_order_preview",
        "karabasan": score,
        "user_control": user_control,
        "blocking_reasons": blocks,
        "user_message": "Piyasa ve risk uygun; emir önizleme hazırlanabilir." if not blocks else "İşlem açılmadı: " + blocks[0],
    }
