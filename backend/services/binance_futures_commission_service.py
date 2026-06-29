from __future__ import annotations
from typing import Any, Dict
from services.binance_futures_ledger_service import build_futures_ledger


def build_futures_commission_income(runtime: Dict[str, Any] | None, permission: Dict[str, Any] | None) -> Dict[str, Any]:
    ledger = build_futures_ledger(runtime, permission, owner_view=True)
    return {
        "service": "binance_futures_commission",
        "market": "futures",
        "owner_only": True,
        "receivable_usdt": ledger.get("summary", {}).get("owner_commission_income", 0),
        "collection_model": "manual_usdt_iban",
        "user_does_not_see_owner_income": True,
    }
