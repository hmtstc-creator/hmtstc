from __future__ import annotations
from typing import Any, Dict, List
from services.binance_futures_lifecycle_service import evidence_checksum


def _n(v, d=0.0):
    try: return float(v)
    except Exception: return d


def build_futures_ledger(runtime: Dict[str, Any] | None = None, permission: Dict[str, Any] | None = None, owner_view: bool = False) -> Dict[str, Any]:
    runtime = runtime or {}
    permission = permission or {}
    buy_comm = _n(permission.get("futures_commission_buy_pct"), 0.1)
    sell_comm = _n(permission.get("futures_commission_sell_pct"), 0.1)
    raw = runtime.get("futures_trade_ledger") or []
    if not isinstance(raw, list): raw = []
    rows: List[Dict[str, Any]] = []
    totals = {"realized_pnl": 0.0, "funding_fee": 0.0, "binance_fee": 0.0, "system_commission": 0.0, "net_user_pnl": 0.0, "owner_commission_income": 0.0}
    for i, item in enumerate(raw):
        notional = _n(item.get("notional"), 0)
        realized = _n(item.get("realized_pnl"), 0)
        funding = _n(item.get("funding_fee"), 0)
        binance_fee = _n(item.get("binance_fee"), notional * 0.0008)
        system_buy = _n(item.get("system_buy_commission"), notional * buy_comm / 100)
        system_sell = _n(item.get("system_sell_commission"), notional * sell_comm / 100)
        owner_income = system_buy + system_sell
        net = realized - funding - binance_fee - owner_income
        row = {
            "symbol": item.get("symbol", "BTCUSDT"), "side": item.get("side", "long"), "position_side": item.get("position_side", "BOTH"),
            "entry_price": item.get("entry_price", 0), "exit_price": item.get("exit_price", 0), "mark_price": item.get("mark_price", 0),
            "liquidation_price": item.get("liquidation_price", 0), "leverage": item.get("leverage", 1), "margin_type": item.get("margin_type", "isolated"),
            "notional": notional, "margin_used": item.get("margin_used", 0), "realized_pnl": round(realized, 4), "unrealized_pnl": _n(item.get("unrealized_pnl"), 0),
            "funding_fee": round(funding, 4), "binance_fee": round(binance_fee, 4), "system_buy_commission": round(system_buy, 4),
            "system_sell_commission": round(system_sell, 4), "net_user_pnl": round(net, 4), "order_id": item.get("order_id", f"dry-{i}"),
            "position_id": item.get("position_id", f"pos-{i}"),
        }
        row["evidence_checksum"] = item.get("evidence_checksum") or evidence_checksum(row)
        if owner_view:
            row["owner_commission_income"] = round(owner_income, 4)
        rows.append(row)
        totals["realized_pnl"] += realized; totals["funding_fee"] += funding; totals["binance_fee"] += binance_fee; totals["system_commission"] += owner_income; totals["net_user_pnl"] += net; totals["owner_commission_income"] += owner_income
    summary = {k: round(v, 4) for k,v in totals.items()}
    if not owner_view:
        summary.pop("owner_commission_income", None)
        for r in rows: r.pop("owner_commission_income", None)
    return {"service": "binance_futures_ledger", "market": "futures", "spot_ledger_separated": True, "summary": summary, "recent": rows[-50:], "owner_view": owner_view}
