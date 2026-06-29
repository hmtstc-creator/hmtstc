from datetime import datetime, timezone

from core.indicators import safe_round


def parse_dt(value):
    if not value:
        return None

    try:
        raw = str(value).strip().replace("Z", "+00:00")
        if not raw:
            return None
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def now_utc():
    return datetime.now(timezone.utc)


def seconds_between(start, end):
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)

    if not start_dt or not end_dt:
        return 0

    try:
        return max(int((end_dt - start_dt).total_seconds()), 0)
    except Exception:
        return 0


def format_duration(seconds):
    seconds = int(seconds or 0)

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}g {hours}s {minutes}dk"

    if hours > 0:
        return f"{hours}s {minutes}dk"

    return f"{minutes}dk"


def _pnl_sum(items):
    total = 0.0

    for item in items or []:
        try:
            total += float(item.get("pnl") or 0)
        except Exception:
            continue

    return total


def get_open_pnl(data):
    return safe_round(_pnl_sum(data.get("open_positions", [])), 4)


def get_closed_pnl(data):
    return safe_round(_pnl_sum(data.get("history", [])), 4)


def get_daily_realized_pnl(data):
    today = now_utc().date()
    total = 0.0

    for position in data.get("history", []):
        closed_at = position.get("exit_time") or position.get("closed_at")
        closed_dt = parse_dt(closed_at)

        if not closed_dt or closed_dt.date() != today:
            continue

        try:
            total += float(position.get("pnl") or 0)
        except Exception:
            continue

    return safe_round(total, 4)


def daily_pnl_value(data):
    return safe_round(get_open_pnl(data) + get_daily_realized_pnl(data), 4)


def total_pnl_value(data):
    return safe_round(get_open_pnl(data) + get_closed_pnl(data), 4)


def shadow_wallet_value(data, base_wallet=1000.0):
    return safe_round(base_wallet + total_pnl_value(data), 4)


def get_active_usdt(data):
    return safe_round(
        sum(float(position.get("usdt_size") or 0) for position in data.get("open_positions", [])),
        2
    )


def get_runtime_seconds(data):
    started_at = data.get("bot_started_at")

    if data.get("bot_running"):
        end_time = now_utc().isoformat(timespec="seconds")
    else:
        end_time = (
            data.get("bot_stopped_at")
            or data.get("last_updated_at")
            or data.get("last_tick")
        )

    return seconds_between(started_at, end_time)


def _position_pnl(item):
    try:
        return float((item or {}).get("pnl") or 0)
    except Exception:
        return 0.0


def get_trade_stats(data):
    history = data.get("history", []) if isinstance(data.get("history", []), list) else []

    total_trades = len(history)
    wins = [item for item in history if _position_pnl(item) > 0]
    losses = [item for item in history if _position_pnl(item) < 0]

    win_count = len(wins)
    loss_count = len(losses)

    gross_profit = sum(_position_pnl(item) for item in wins)
    gross_loss = abs(sum(_position_pnl(item) for item in losses))

    win_rate = (win_count / total_trades * 100) if total_trades else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)

    avg_win = (gross_profit / win_count) if win_count else 0
    avg_loss = (gross_loss / loss_count) if loss_count else 0

    expectancy = (
        ((win_rate / 100) * avg_win) -
        ((1 - (win_rate / 100)) * avg_loss)
        if total_trades else 0
    )

    durations = []
    for item in history:
        seconds = seconds_between(item.get("entry_time"), item.get("exit_time"))
        if seconds > 0:
            durations.append(seconds)

    avg_holding_seconds = int(sum(durations) / len(durations)) if durations else 0

    return {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": safe_round(win_rate, 2),
        "gross_profit": safe_round(gross_profit, 4),
        "gross_loss": safe_round(gross_loss, 4),
        "profit_factor": safe_round(profit_factor, 4),
        "avg_win": safe_round(avg_win, 4),
        "avg_loss": safe_round(avg_loss, 4),
        "expectancy": safe_round(expectancy, 4),
        "avg_holding_seconds": avg_holding_seconds,
        "avg_holding_text": format_duration(avg_holding_seconds)
    }


def calculate_max_drawdown(points):
    peak = None
    max_drawdown = 0

    for point in points:
        try:
            value = float((point or {}).get("wallet_value") or 0)
        except Exception:
            continue

        if peak is None or value > peak:
            peak = value

        if peak and peak > 0:
            drawdown = ((peak - value) / peak) * 100
            max_drawdown = max(max_drawdown, drawdown)

    return safe_round(max_drawdown, 2)


def record_performance_point(data):
    points = data.setdefault("performance_points", [])
    now = now_utc()

    if points:
        try:
            last_time = parse_dt(points[-1].get("time"))
            if last_time and (now - last_time).total_seconds() < 300:
                return data
        except Exception:
            pass

    open_pnl = get_open_pnl(data)
    closed_pnl = get_closed_pnl(data)
    daily_realized_pnl = get_daily_realized_pnl(data)
    daily_pnl = daily_pnl_value(data)
    total_pnl = total_pnl_value(data)

    point = {
        "time": now.isoformat(timespec="seconds"),
        "wallet_value": shadow_wallet_value(data),
        "active_usdt": get_active_usdt(data),
        "open_pnl": open_pnl,
        "unrealized_pnl": open_pnl,
        "closed_pnl": closed_pnl,
        "realized_pnl": closed_pnl,
        "daily_realized_pnl": daily_realized_pnl,
        "daily_pnl": daily_pnl,
        "total_pnl": total_pnl,
        "open_positions_count": len(data.get("open_positions", [])),
        "bot_running": bool(data.get("bot_running")),
        "engine_status": data.get("engine_status", "unknown")
    }

    points.append(point)

    data["performance_points"] = points[-5000:]
    data["last_calculation_at"] = point["time"]

    return data


def _last_error(data):
    for item in reversed(data.get("logs", [])):
        if str(item.get("level") or "").lower() == "error":
            return item
    return None


def build_dashboard_summary(data, settings):
    bot = settings.get("bot", {})
    points = data.get("performance_points", [])
    last_scan = data.get("last_scan", {}) or {}
    open_positions = data.get("open_positions", [])
    runtime_seconds = get_runtime_seconds(data)
    trade_stats = get_trade_stats(data)
    error = _last_error(data)

    open_pnl = get_open_pnl(data)
    realized_pnl = get_closed_pnl(data)
    daily_realized_pnl = get_daily_realized_pnl(data)
    daily_pnl = daily_pnl_value(data)
    total_pnl = total_pnl_value(data)

    return {
        "balance": "1000.00 USDT",
        "wallet_value": shadow_wallet_value(data),
        "active_usdt": get_active_usdt(data),

        "daily_pnl": daily_pnl,
        "daily_realized_pnl": daily_realized_pnl,
        "open_pnl": open_pnl,
        "unrealized_pnl": open_pnl,
        "closed_pnl": realized_pnl,
        "realized_pnl": realized_pnl,
        "total_pnl": total_pnl,

        "open_positions": f"{len(open_positions)} / {bot.get('max_open_positions', 5)}",
        "open_positions_count": len(open_positions),

        "mode": data.get("mode", "shadow"),
        "bot_running": data.get("bot_running", False),
        "engine_status": data.get("engine_status", "unknown"),

        "bot_started_at": data.get("bot_started_at"),
        "bot_stopped_at": data.get("bot_stopped_at"),
        "last_tick": data.get("last_tick"),
        "last_updated_at": data.get("last_updated_at"),
        "last_calculation_at": data.get("last_calculation_at"),
        "stop_reason": data.get("stop_reason"),

        "runtime_seconds": runtime_seconds,
        "runtime_text": format_duration(runtime_seconds),

        "scan_status": last_scan.get("status", "idle"),
        "scan_live": bool(last_scan.get("live")),
        "scan_time": last_scan.get("time"),
        "scan_id": last_scan.get("scan_id"),
        "scanned": last_scan.get("scanned", 0),
        "candidates_count": last_scan.get("candidates_count", 0),
        "rejected_count": last_scan.get("rejected_count", 0),
        "top_rejection_reason": last_scan.get("top_rejection_reason"),
        "rejection_breakdown": last_scan.get("rejection_breakdown", {}),
        "scan_error": last_scan.get("error"),

        "last_error": error,

        "total_trades": trade_stats["total_trades"],
        "win_count": trade_stats["win_count"],
        "loss_count": trade_stats["loss_count"],
        "win_rate": trade_stats["win_rate"],
        "gross_profit": trade_stats["gross_profit"],
        "gross_loss": trade_stats["gross_loss"],
        "avg_win": trade_stats["avg_win"],
        "avg_loss": trade_stats["avg_loss"],
        "profit_factor": trade_stats["profit_factor"],
        "expectancy": trade_stats["expectancy"],
        "avg_holding_seconds": trade_stats["avg_holding_seconds"],
        "avg_holding_text": trade_stats["avg_holding_text"],
        "max_drawdown_percent": calculate_max_drawdown(points)
    }


def filter_performance_points(data, start=None, end=None):
    points = data.get("performance_points", [])

    start_dt = parse_dt(start) if start else None
    end_dt = parse_dt(end) if end else None

    filtered = []

    for point in points:
        try:
            point_dt = parse_dt(point.get("time"))
            if not point_dt:
                continue
        except Exception:
            continue

        if start_dt and point_dt.date() < start_dt.date():
            continue

        if end_dt and point_dt.date() > end_dt.date():
            continue

        filtered.append(point)

    return {
        "status": "ok",
        "count": len(filtered),
        "last_calculation_at": data.get("last_calculation_at"),
        "max_drawdown_percent": calculate_max_drawdown(filtered),
        "trade_stats": get_trade_stats(data),
        "pnl": {
            "open_pnl": get_open_pnl(data),
            "unrealized_pnl": get_open_pnl(data),
            "realized_pnl": get_closed_pnl(data),
            "daily_realized_pnl": get_daily_realized_pnl(data),
            "daily_pnl": daily_pnl_value(data),
            "total_pnl": total_pnl_value(data),
            "wallet_value": shadow_wallet_value(data)
        },
        "points": filtered
    }
