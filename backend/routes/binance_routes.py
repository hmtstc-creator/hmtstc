from fastapi import APIRouter, Depends

from core.auth import require_owner, require_user
from services.binance_service import BinanceService
from services.market_service import (
    binance_ping,
    get_binance_summary,
    get_market_symbols,
    get_symbol_price,
)


router = APIRouter(
    prefix="/api/binance",
    tags=["binance"]
)


@router.get("/ping")
def ping(current_user: dict = Depends(require_user)):
    return binance_ping()


@router.get("/price")
def price(symbol: str = "BTCUSDT", current_user: dict = Depends(require_user)):
    return get_symbol_price(symbol)


@router.get("/summary")
def summary(current_user: dict = Depends(require_user)):
    return get_binance_summary()


@router.get("/market")
def market(limit: int = 1000, strict: bool = False, current_user: dict = Depends(require_user)):
    return get_market_symbols(limit=limit, strict=strict, timeout=3 if not strict else 10)


@router.get("/connection")
def connection(current_user: dict = Depends(require_user)):
    service = BinanceService()
    return service.summary()


@router.get("/server-time")
def server_time(current_user: dict = Depends(require_user)):
    service = BinanceService()
    return service.server_time()


@router.get("/account-check")
def account_check(current_user: dict = Depends(require_owner)):
    service = BinanceService()

    return {
        "mode": service.mode,
        "has_credentials": service.has_credentials(),
        "result": service.account_check()
    }


@router.post("/test-market-buy")
def test_market_buy(
    symbol: str = "BTCUSDT",
    quote_order_qty: float = 10,
    current_user: dict = Depends(require_owner),
):
    service = BinanceService()

    if quote_order_qty <= 0:
        return {
            "status": "error",
            "message": "quote_order_qty sıfırdan büyük olmalı."
        }

    if quote_order_qty > 50:
        return {
            "status": "blocked",
            "message": "Güvenlik için test order limiti 50 USDT ile sınırlandı."
        }

    result = service.test_market_buy_order(
        symbol=symbol,
        quote_order_qty=quote_order_qty
    )

    return {
        "mode": service.mode,
        "symbol": symbol.upper(),
        "quote_order_qty": quote_order_qty,
        "real_order_created": False,
        "result": result
    }
