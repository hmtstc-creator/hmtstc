from __future__ import annotations

from typing import Any, Dict, List

from services.binance_futures_models import now_iso


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _ledger(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = runtime.get("futures_trade_ledger") or runtime.get("futures_ledger") or []
    return raw if isinstance(raw, list) else []


def build_phase3_rental_finance_link(
    runtime: Dict[str, Any],
    permission: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    owner_view: bool = False,
) -> Dict[str, Any]:
    context = context or {}
    days_left = _num(context.get("rental_days_left", runtime.get("rental_days_left", 7)), 0)
    ledger = _ledger(runtime) or context.get("ledger", [])
    volume = sum(_num(row.get("notional", row.get("volume", 0))) for row in ledger if isinstance(row, dict))
    binance_fee = sum(_num(row.get("binance_fee", 0)) for row in ledger if isinstance(row, dict))
    funding_fee = sum(_num(row.get("funding_fee", 0)) for row in ledger if isinstance(row, dict))
    system_buy = sum(_num(row.get("system_buy_commission", 0)) for row in ledger if isinstance(row, dict))
    system_sell = sum(_num(row.get("system_sell_commission", 0)) for row in ledger if isinstance(row, dict))
    net_user_pnl = sum(_num(row.get("net_user_pnl", row.get("realized_pnl", 0))) for row in ledger if isinstance(row, dict))
    owner_income = system_buy + system_sell
    manual_paid = _num(context.get("manual_paid", runtime.get("futures_owner_paid", 0)), 0)
    receivable = max(0.0, owner_income - manual_paid)
    futures_active_by_rental = bool(permission.get("futures_enabled") and days_left > 0)
    return {
        "service": "futures_phase3_rental_finance_link",
        "phase": "Faz3-3",
        "checked_at": now_iso(),
        "rental": {
            "days_left": days_left,
            "futures_active_by_rental": futures_active_by_rental,
            "expired_action": "block_new_futures_orders_and_warn_owner" if days_left <= 0 else "allow_if_other_gates_pass",
        },
        "user_finance_view": {
            "futures_trade_count": len(ledger),
            "futures_volume": round(volume, 4),
            "binance_fee": round(binance_fee, 4),
            "funding_fee": round(funding_fee, 4),
            "net_user_pnl": round(net_user_pnl, 4),
            "owner_commission_hidden": True,
        },
        "owner_finance_view": {
            "visible": bool(owner_view),
            "futures_owner_commission_income": round(owner_income, 4) if owner_view else "owner_only",
            "manual_paid": round(manual_paid, 4) if owner_view else "owner_only",
            "receivable": round(receivable, 4) if owner_view else "owner_only",
            "collection_status": "paid" if receivable <= 0 else "waiting_collection",
            "payment_methods": ["manual", "USDT", "IBAN"] if owner_view else [],
        },
        "commercial_ready": futures_active_by_rental and (owner_view or True),
    }
