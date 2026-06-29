from copy import deepcopy
import time
from uuid import uuid4

from core.indicators import parse_percent
from core.storage import append_log, now_iso
from services.market_service import get_current_price


HISTORY_LIMIT = 5000


def _safe_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _calculate_pnl(entry, current, quantity):
    return round((float(current) - float(entry)) * float(quantity), 4)


def _entry_signal(candidate: dict) -> dict:
    return {
        "score": candidate.get("score", 0),
        "rsi": candidate.get("rsi"),
        "rsi_15m": candidate.get("rsi_15m"),
        "rsi_1h": candidate.get("rsi_1h"),
        "rsi_4h": candidate.get("rsi_4h"),
        "ema_signal": candidate.get("ema_signal"),
        "macd_signal": candidate.get("macd_signal"),
        "volatility": candidate.get("volatility"),
        "volume_growth": candidate.get("volume_growth"),
        "strategy": candidate.get("strategy"),
        "reason": candidate.get("reason")
    }


def update_open_positions(data: dict, settings: dict, *, cancel_requested=None, deadline: float | None = None) -> dict:
    risk = settings.get("risk", {})

    stop_loss = parse_percent(
        risk.get("stop_loss", "0.75%"),
        0.0075
    )

    take_profit = parse_percent(
        risk.get("take_profit", "2%"),
        0.02
    )

    open_positions = data.get("open_positions", [])
    remaining_positions = []
    history = data.setdefault("history", [])

    for position_index, position in enumerate(open_positions):
        if (callable(cancel_requested) and cancel_requested()) or (deadline is not None and time.monotonic() >= deadline):
            remaining_positions.extend(open_positions[position_index:])
            break
        try:
            symbol = position.get("symbol")
            entry = _safe_float(position.get("entry"))
            quantity = _safe_float(position.get("quantity"))

            if not symbol or entry <= 0 or quantity <= 0:
                remaining_positions.append(position)
                continue

            remaining_timeout = max(0.1, min(3.0, (deadline - time.monotonic()) if deadline is not None else 3.0))
            current = _safe_float(get_current_price(symbol, timeout=remaining_timeout))
            if current <= 0:
                position["last_price_error"] = "invalid_current_price"
                remaining_positions.append(position)
                continue
            target = round(entry * (1 + take_profit), 8)
            stop = round(entry * (1 - stop_loss), 8)
            pnl = _calculate_pnl(entry, current, quantity)

            position.setdefault("id", str(uuid4()))
            position["current"] = current
            position["target"] = target
            position["stop"] = stop
            position["pnl"] = pnl
            position["last_price_update_at"] = now_iso()
            position["last_price_source"] = "binance_live"

            close_reason = None

            if current >= target:
                close_reason = "Take Profit"
            elif current <= stop:
                close_reason = "Stop Loss"

            if close_reason:
                closed_position = dict(position)
                closed_position["exit"] = current
                closed_position["exit_time"] = now_iso()
                closed_position["reason"] = close_reason
                closed_position["status"] = "closed"
                closed_position["exit_price_source"] = "binance_live"
                closed_position["pnl"] = pnl

                history.append(closed_position)

                append_log(
                    data,
                    "info",
                    f"Shadow pozisyon kapandı: {symbol} - {close_reason} - PnL: {pnl}",
                    "position_closed"
                )
            else:
                remaining_positions.append(position)

        except Exception as error:
            position["last_error"] = str(error)
            remaining_positions.append(position)

            append_log(
                data,
                "error",
                f"Pozisyon güncelleme hatası: {position.get('symbol')} - {str(error)}",
                "position_update_error"
            )

    data["open_positions"] = remaining_positions
    data["history"] = history[-HISTORY_LIMIT:]

    return data


def close_all_shadow_positions(data: dict, reason: str = "Emergency Stop") -> dict:
    open_positions = data.get("open_positions", [])
    history = data.setdefault("history", [])

    for position in open_positions:
        closed_position = dict(position)
        symbol = position.get("symbol")
        entry = _safe_float(position.get("entry"))
        quantity = _safe_float(position.get("quantity"))
        price_source = "last_known"

        current = _safe_float(position.get("current"), _safe_float(position.get("entry")))

        if symbol:
            try:
                current = get_current_price(symbol)
                price_source = "binance_live"
            except Exception as error:
                append_log(
                    data,
                    "error",
                    f"Emergency close fiyat alma hatası: {symbol} - {str(error)}",
                    "emergency_price_error"
                )

        pnl = _calculate_pnl(entry, current, quantity) if entry > 0 and quantity > 0 else _safe_float(position.get("pnl"))

        closed_position.setdefault("id", str(uuid4()))
        closed_position["current"] = current
        closed_position["exit"] = current
        closed_position["exit_time"] = now_iso()
        closed_position["reason"] = reason
        closed_position["status"] = "closed"
        closed_position["exit_price_source"] = price_source
        closed_position["pnl"] = pnl

        history.append(closed_position)

    data["open_positions"] = []
    data["history"] = history[-HISTORY_LIMIT:]

    append_log(
        data,
        "warn",
        f"Tüm shadow pozisyonlar kapatıldı. Sebep: {reason}",
        "close_all_positions"
    )

    return data


def create_shadow_position(candidate: dict, settings: dict, usdt_size: float) -> dict:
    symbol = candidate.get("symbol")
    price = _safe_float(candidate.get("price"))

    if not symbol or price <= 0:
        raise ValueError("Pozisyon oluşturmak için geçerli symbol ve price gerekli.")

    quantity = round(float(usdt_size) / price, 8)
    now = now_iso()
    settings_snapshot = deepcopy(settings) if isinstance(settings, dict) else {}

    return {
        "id": str(uuid4()),
        "scan_id": candidate.get("scan_id"),
        "symbol": symbol,
        "entry": price,
        "current": price,

        "usdt_size": usdt_size,
        "quantity": quantity,

        "pnl": 0,
        "mode": candidate.get("mode", "shadow"),
        "model_id": candidate.get("model_id"),
        "filter_id": candidate.get("filter_id"),
        "strategy_id": candidate.get("strategy_id"),

        "entry_time": now,
        "last_price_update_at": now,
        "entry_price_source": candidate.get("price_source", "scan_market"),
        "last_price_source": candidate.get("price_source", "scan_market"),

        "score": candidate.get("score", 0),
        "strategy": candidate.get("strategy_id") or settings.get("current_strategy", "-"),
        "entry_signal": _entry_signal(candidate),
        "settings_snapshot": settings_snapshot,

        "status": "open"
    }
