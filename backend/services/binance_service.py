from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()


class BinanceConfigError(Exception):
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "" if default is None else str(default))).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    return bool(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, default)).replace(",", "."))
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(str(os.getenv(name, default)).replace(",", ".")))
    except Exception:
        return int(default)


def _split_symbols(value: str) -> set[str]:
    return {x.strip().upper() for x in str(value or "").split(",") if x.strip()}


def _default_base_url(testnet: bool) -> str:
    return "https://testnet.binance.vision/api" if testnet else "https://api.binance.com/api"


def decimal_floor(value: float | str | Decimal, step: float | str | Decimal) -> str:
    try:
        v = Decimal(str(value))
        s = Decimal(str(step))
        if s <= 0:
            return format(v.normalize(), "f")
        floored = (v / s).to_integral_value(rounding=ROUND_DOWN) * s
        return format(floored.normalize(), "f")
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _decimal(value: Any, fallback: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(str(fallback))


def _step_aligned(value: Decimal, step: Decimal) -> bool:
    if step <= 0:
        return True
    try:
        return (value % step) == 0
    except Exception:
        return False


def map_binance_error(error: Any) -> dict:
    payload = error if isinstance(error, dict) else {"message": str(error)}
    code = payload.get("code")
    msg = str(payload.get("msg") or payload.get("message") or payload.get("raw") or payload).lower()
    mapping = "binance_unknown_error"
    if code in {-1021, "-1021"} or "timestamp" in msg:
        mapping = "binance_timestamp_or_recv_window"
    elif code in {-1022, "-1022"} or "signature" in msg:
        mapping = "binance_signature_invalid"
    elif code in {-2010, "-2010"} and ("balance" in msg or "insufficient" in msg):
        mapping = "binance_insufficient_balance"
    elif code in {-1013, "-1013"} or "filter failure" in msg or "min_notional" in msg or "lot_size" in msg:
        mapping = "binance_filter_failure"
    elif code in {-1003, "-1003", 429, "429"} or "rate limit" in msg or "too many requests" in msg:
        mapping = "binance_rate_limit"
    elif code in {-2015, "-2015"} or "invalid api-key" in msg or "ip" in msg:
        mapping = "binance_api_key_or_ip_restricted"
    elif "network" in msg or "timed out" in msg or "timeout" in msg:
        mapping = "binance_network_or_timeout"
    elif "maintenance" in msg or "unavailable" in msg:
        mapping = "binance_maintenance_or_unavailable"
    return {"code": code, "category": mapping, "message": payload.get("msg") or payload.get("message") or str(error), "raw": error}


@dataclass
class BinanceRuntimeConfig:
    mode: str
    base_url: str
    testnet: bool
    has_api_key: bool
    has_api_secret: bool
    real_trading_enabled: bool
    real_trading_dry_run: bool
    max_order_usdt: float
    daily_loss_limit_usdt: float
    weekly_loss_limit_usdt: float
    max_open_positions: int
    allowed_symbols: set[str]
    blocked_symbols: set[str]
    recv_window: int
    timeout_seconds: int

    def public(self) -> dict:
        return {
            "mode": self.mode,
            "base_url": self.base_url,
            "testnet": self.testnet,
            "has_api_key": self.has_api_key,
            "has_api_secret": self.has_api_secret,
            "real_trading_enabled": self.real_trading_enabled,
            "real_trading_dry_run": self.real_trading_dry_run,
            "max_order_usdt": self.max_order_usdt,
            "daily_loss_limit_usdt": self.daily_loss_limit_usdt,
            "weekly_loss_limit_usdt": self.weekly_loss_limit_usdt,
            "max_open_positions": self.max_open_positions,
            "allowed_symbols": sorted(self.allowed_symbols),
            "blocked_symbols": sorted(self.blocked_symbols),
            "recv_window": self.recv_window,
            "timeout_seconds": self.timeout_seconds,
        }


def load_binance_runtime_config() -> BinanceRuntimeConfig:
    mode = str(os.getenv("BINANCE_MODE", "testnet") or "testnet").strip().lower()
    testnet = _env_bool("BINANCE_TESTNET", mode != "mainnet")
    if mode not in {"testnet", "mainnet"}:
        mode = "testnet" if testnet else "mainnet"
    default_base = _default_base_url(testnet or mode == "testnet")
    base_url = str(os.getenv("BINANCE_BASE_URL") or default_base).rstrip("/")
    return BinanceRuntimeConfig(
        mode=mode,
        base_url=base_url,
        testnet=testnet,
        has_api_key=bool(os.getenv("BINANCE_API_KEY", "")),
        has_api_secret=bool(os.getenv("BINANCE_API_SECRET", "")),
        real_trading_enabled=_env_bool("REAL_TRADING_ENABLED", False),
        real_trading_dry_run=_env_bool("REAL_TRADING_DRY_RUN", True),
        max_order_usdt=_env_float("REAL_MAX_ORDER_USDT", 5),
        daily_loss_limit_usdt=_env_float("REAL_DAILY_LOSS_LIMIT_USDT", 2),
        weekly_loss_limit_usdt=_env_float("REAL_WEEKLY_LOSS_LIMIT_USDT", 5),
        max_open_positions=_env_int("REAL_MAX_OPEN_POSITIONS", 1),
        allowed_symbols=_split_symbols(os.getenv("REAL_ALLOWED_SYMBOLS", "")),
        blocked_symbols=_split_symbols(os.getenv("REAL_BLOCKED_SYMBOLS", "")),
        recv_window=_env_int("BINANCE_RECV_WINDOW", 5000),
        timeout_seconds=_env_int("BINANCE_TIMEOUT_SECONDS", 10),
    )


class BinanceService:
    """Minimal Binance Spot REST client. Futures/margin/withdraw endpoint içermez."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None, mode: str | None = None, testnet: bool | None = None, base_url: str | None = None):
        runtime = load_binance_runtime_config()
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode in {"testnet", "mainnet"}:
            testnet = normalized_mode == "testnet"
        if testnet is not None:
            runtime = replace(
                runtime,
                mode="testnet" if testnet else "mainnet",
                testnet=bool(testnet),
                base_url=str(base_url or _default_base_url(bool(testnet))).rstrip("/"),
                has_api_key=bool(api_key) if api_key is not None else runtime.has_api_key,
                has_api_secret=bool(api_secret) if api_secret is not None else runtime.has_api_secret,
            )
        elif base_url:
            runtime = replace(runtime, base_url=str(base_url).rstrip("/"))

        self.runtime = runtime
        self.mode = self.runtime.mode
        self.api_key = str(api_key if api_key is not None else os.getenv("BINANCE_API_KEY", "") or "")
        self.api_secret = str(api_secret if api_secret is not None else os.getenv("BINANCE_API_SECRET", "") or "")
        self.timeout_seconds = self.runtime.timeout_seconds

    @property
    def base_url(self) -> str:
        return self.runtime.base_url

    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        return headers

    def _sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.has_credentials():
            raise BinanceConfigError("BINANCE_API_KEY veya BINANCE_API_SECRET eksik.")
        signed_params = dict(params)
        signed_params["timestamp"] = self.get_server_timestamp()
        signed_params.setdefault("recvWindow", self.runtime.recv_window)
        query_string = urlencode(signed_params)
        signature = hmac.new(self.api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
        signed_params["signature"] = signature
        return signed_params

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False, timeout: Optional[int] = None) -> Dict[str, Any]:
        params = params or {}
        started = time.perf_counter()
        try:
            if signed:
                params = self._sign_params(params)
            query = urlencode(params)
            url = f"{self.base_url}{path}"
            data = None
            if method.upper() == "GET":
                if query:
                    url = f"{url}?{query}"
            else:
                data = query.encode("utf-8")
            request = Request(url=url, data=data, method=method.upper(), headers=self._headers())
            with urlopen(request, timeout=timeout or self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return {"ok": True, "status_code": response.status, "data": parsed, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except HTTPError as error:
            raw_error = error.read().decode("utf-8") if error.fp else ""
            try:
                parsed_error = json.loads(raw_error) if raw_error else {}
            except json.JSONDecodeError:
                parsed_error = {"raw": raw_error}
            return {"ok": False, "status_code": error.code, "error": parsed_error, "mapped_error": map_binance_error(parsed_error), "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except URLError as error:
            return {"ok": False, "status_code": None, "error": str(error.reason), "mapped_error": map_binance_error(str(error.reason)), "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except BinanceConfigError as error:
            return {"ok": False, "status_code": None, "error": str(error), "mapped_error": map_binance_error(str(error)), "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
        except Exception as error:
            return {"ok": False, "status_code": None, "error": str(error), "mapped_error": map_binance_error(str(error)), "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

    def ping(self) -> Dict[str, Any]:
        return self._request("GET", "/v3/ping", timeout=5)

    def server_time(self) -> Dict[str, Any]:
        return self._request("GET", "/v3/time", timeout=5)

    def get_server_timestamp(self) -> int:
        response = self.server_time()
        if response.get("ok") and isinstance(response.get("data"), dict) and response["data"].get("serverTime"):
            return int(response["data"].get("serverTime"))
        return int(time.time() * 1000)

    def price(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        return self._request("GET", "/v3/ticker/price", {"symbol": symbol.upper()})

    def book_ticker(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        return self._request("GET", "/v3/ticker/bookTicker", {"symbol": symbol.upper()})

    def exchange_info(self, symbol: str | None = None) -> Dict[str, Any]:
        params = {"symbol": symbol.upper()} if symbol else {}
        return self._request("GET", "/v3/exchangeInfo", params)

    def account_check(self) -> Dict[str, Any]:
        return self._request("GET", "/v3/account", signed=True)

    def account(self) -> Dict[str, Any]:
        return self.account_check()

    def balances(self) -> Dict[str, Any]:
        account = self.account_check()
        if not account.get("ok"):
            return account
        balances = (account.get("data") or {}).get("balances", [])
        filtered = []
        for row in balances:
            free = float(row.get("free") or 0)
            locked = float(row.get("locked") or 0)
            if free or locked:
                filtered.append({"asset": row.get("asset"), "free": free, "locked": locked, "total": free + locked})
        return {"ok": True, "status_code": account.get("status_code"), "data": {"balances": filtered}, "latency_ms": account.get("latency_ms")}

    def symbol_filters(self, symbol: str) -> Dict[str, Any]:
        info = self.exchange_info(symbol)
        if not info.get("ok"):
            return info
        symbols = (info.get("data") or {}).get("symbols") or []
        if not symbols:
            return {"ok": False, "status_code": 404, "error": "symbol_not_found"}
        sym = symbols[0]
        filters = {f.get("filterType"): f for f in sym.get("filters", []) if isinstance(f, dict)}
        return {"ok": True, "data": {"symbol": sym.get("symbol"), "status": sym.get("status"), "permissions": sym.get("permissions", []), "orderTypes": sym.get("orderTypes", []), "filters": filters}}

    def validate_market_order_payload(self, symbol: str, side: str, quote_order_qty: float, quantity: float | None = None, price: float | None = None) -> Dict[str, Any]:
        symbol = str(symbol or "").upper().strip()
        side = str(side or "").upper().strip()
        quote_dec = _decimal(quote_order_qty)
        qty_dec = _decimal(quantity) if quantity is not None else None
        price_dec = _decimal(price) if price is not None else None
        blockers: list[str] = []
        warnings: list[str] = []
        filter_checks: dict[str, Any] = {}
        if not symbol.endswith("USDT"):
            blockers.append("symbol_not_usdt_spot")
        if side not in {"BUY", "SELL"}:
            blockers.append("invalid_side")
        if quote_dec <= 0:
            blockers.append("invalid_quote_order_qty")
        if self.runtime.allowed_symbols and symbol not in self.runtime.allowed_symbols:
            blockers.append("symbol_not_allowed_for_real")
        if symbol in self.runtime.blocked_symbols:
            blockers.append("symbol_blocked_for_real")
        if quote_dec > _decimal(self.runtime.max_order_usdt):
            blockers.append("max_order_usdt_exceeded")
        filters_payload = self.symbol_filters(symbol) if symbol and symbol.endswith("USDT") else {"ok": False, "error": "symbol_filters_skipped"}
        filters = ((filters_payload.get("data") or {}).get("filters") or {}) if filters_payload.get("ok") else {}
        min_notional = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        min_value = _decimal((min_notional or {}).get("minNotional") or 0) if isinstance(min_notional, dict) else Decimal("0")
        if min_value and quote_dec < min_value:
            blockers.append("min_notional_not_met")
        filter_checks["MIN_NOTIONAL"] = {"min_notional": float(min_value), "quote_order_qty": float(quote_dec), "ok": not bool(min_value and quote_dec < min_value)}

        for filter_name in ["LOT_SIZE", "MARKET_LOT_SIZE"]:
            f = filters.get(filter_name) or {}
            if not isinstance(f, dict) or not f:
                continue
            min_qty = _decimal(f.get("minQty") or 0)
            max_qty = _decimal(f.get("maxQty") or 0)
            step = _decimal(f.get("stepSize") or 0)
            check = {"min_qty": float(min_qty), "max_qty": float(max_qty), "step_size": float(step), "quantity": float(qty_dec) if qty_dec is not None else None, "ok": True}
            if qty_dec is None:
                check["ok"] = None
                warnings.append(f"{filter_name.lower()}_quantity_not_supplied")
            else:
                if min_qty and qty_dec < min_qty:
                    blockers.append(f"{filter_name.lower()}_min_qty_not_met")
                    check["ok"] = False
                if max_qty and qty_dec > max_qty:
                    blockers.append(f"{filter_name.lower()}_max_qty_exceeded")
                    check["ok"] = False
                if step and not _step_aligned(qty_dec, step):
                    blockers.append(f"{filter_name.lower()}_step_size_mismatch")
                    check["ok"] = False
            filter_checks[filter_name] = check

        price_filter = filters.get("PRICE_FILTER") or {}
        if isinstance(price_filter, dict) and price_filter:
            min_price = _decimal(price_filter.get("minPrice") or 0)
            max_price = _decimal(price_filter.get("maxPrice") or 0)
            tick = _decimal(price_filter.get("tickSize") or 0)
            check = {"min_price": float(min_price), "max_price": float(max_price), "tick_size": float(tick), "price": float(price_dec) if price_dec is not None else None, "ok": True}
            if price_dec is None:
                check["ok"] = None
                warnings.append("price_filter_price_not_supplied_for_market_order")
            else:
                if min_price and price_dec < min_price:
                    blockers.append("price_filter_min_price_not_met")
                    check["ok"] = False
                if max_price and price_dec > max_price:
                    blockers.append("price_filter_max_price_exceeded")
                    check["ok"] = False
                if tick and not _step_aligned(price_dec, tick):
                    blockers.append("price_filter_tick_size_mismatch")
                    check["ok"] = False
            filter_checks["PRICE_FILTER"] = check
        if filters_payload.get("ok") is False:
            warnings.append("symbol_filters_unavailable")
        payload = {"symbol": symbol, "side": side, "type": "MARKET", "quoteOrderQty": float(quote_dec)}
        return {
            "status": "blocked" if blockers else "ok",
            "payload": payload,
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "filters": filters,
            "filter_checks": filter_checks,
            "min_notional": float(min_value),
            "normalized": {
                "quote_order_qty": float(quote_dec),
                "quantity": float(qty_dec) if qty_dec is not None else None,
                "price": float(price_dec) if price_dec is not None else None,
            },
        }

    def test_market_buy_order(self, symbol: str = "BTCUSDT", quote_order_qty: float = 10) -> Dict[str, Any]:
        return self._request("POST", "/v3/order/test", {"symbol": symbol.upper(), "side": "BUY", "type": "MARKET", "quoteOrderQty": quote_order_qty}, signed=True)

    def place_market_order(self, symbol: str, side: str, quote_order_qty: float, new_client_order_id: str | None = None) -> Dict[str, Any]:
        params = {"symbol": symbol.upper(), "side": side.upper(), "type": "MARKET", "quoteOrderQty": quote_order_qty}
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id
        return self._request("POST", "/v3/order", params, signed=True)

    def get_order(self, symbol: str, order_id: str | int | None = None, orig_client_order_id: str | None = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"symbol": symbol.upper()}
        if order_id:
            params["orderId"] = order_id
        if orig_client_order_id:
            params["origClientOrderId"] = orig_client_order_id
        return self._request("GET", "/v3/order", params, signed=True)

    def open_orders(self, symbol: str | None = None) -> Dict[str, Any]:
        params = {"symbol": symbol.upper()} if symbol else {}
        return self._request("GET", "/v3/openOrders", params, signed=True)

    def summary(self) -> Dict[str, Any]:
        ping = self.ping()
        server_time = self.server_time()
        account = self.account_check() if self.has_credentials() else None
        return {
            "status": "ok" if ping.get("ok") else "error",
            "mode": self.mode,
            "base_url": self.base_url,
            "testnet": self.runtime.testnet,
            "public_connection": ping.get("ok", False),
            "server_time_ok": server_time.get("ok", False),
            "latency_ms": ping.get("latency_ms"),
            "api_key_saved": bool(self.api_key),
            "api_secret_saved": bool(self.api_secret),
            "account_access": account.get("ok", False) if account else False,
            "account_error": account.get("error") if account and not account.get("ok") else None,
            "runtime_config": self.runtime.public(),
        }
