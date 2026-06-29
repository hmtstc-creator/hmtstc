from core.indicators import parse_usdt
from services.performance_service import daily_pnl_value, get_active_usdt


def safe_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def get_risk_config(settings: dict) -> dict:
    risk = settings.get("risk", {})
    bot = settings.get("bot", {})

    max_open_positions = max(1, safe_int(bot.get("max_open_positions", 5), 5))
    usdt_per_position = max(1, safe_float(bot.get("usdt_per_position", 200), 200))

    allocated_usdt = max(
        usdt_per_position,
        safe_float(bot.get("allocated_usdt", 1000), 1000)
    )

    return {
        "max_open_positions": max_open_positions,
        "usdt_per_position": usdt_per_position,
        "allocated_usdt": allocated_usdt,

        "daily_loss_limit": abs(
            parse_usdt(risk.get("daily_loss_limit", "30 USDT"), 30)
        ),

        "max_portfolio_risk_percent": max(
            0,
            safe_float(risk.get("max_portfolio_risk_percent", 5), 5)
        ),
        "risk_per_position_percent": max(
            0,
            safe_float(risk.get("risk_per_position_percent", 1), 1)
        ),
        "dynamic_position_size": bool(
            risk.get("dynamic_position_size", False)
        ),
        "max_same_direction_positions": max(
            1,
            safe_int(risk.get("max_same_direction_positions", 3), 3)
        )
    }


def is_daily_loss_limit_reached(data: dict, settings: dict) -> dict:
    config = get_risk_config(settings)

    current_pnl = daily_pnl_value(data)
    limit = config["daily_loss_limit"]

    reached = current_pnl <= -limit

    return {
        "passed": not reached,
        "reached": reached,
        "daily_pnl": current_pnl,
        "daily_loss_limit": limit,
        "reason": "daily_loss_limit" if reached else None
    }


def can_open_new_position(data: dict, settings: dict, symbol: str) -> dict:
    config = get_risk_config(settings)

    open_positions = data.get("open_positions", [])

    opened_symbols = {
        position.get("symbol")
        for position in open_positions
    }

    if symbol in opened_symbols:
        return {
            "passed": False,
            "reason": "symbol_already_open"
        }

    if len(open_positions) >= config["max_open_positions"]:
        return {
            "passed": False,
            "reason": "max_open_positions_reached",
            "open_positions_count": len(open_positions),
            "max_open_positions": config["max_open_positions"]
        }

    same_direction_count = sum(
        1 for position in open_positions
        if str(position.get("side") or "LONG").upper() == "LONG"
    )

    if same_direction_count >= config["max_same_direction_positions"]:
        return {
            "passed": False,
            "reason": "max_same_direction_positions_reached",
            "same_direction_count": same_direction_count,
            "max_same_direction_positions": config["max_same_direction_positions"]
        }

    active_usdt = get_active_usdt(data)
    next_position_size = config["usdt_per_position"]
    allocated_usdt = config["allocated_usdt"]

    if next_position_size <= 0:
        return {
            "passed": False,
            "reason": "invalid_position_size",
            "next_position_size": next_position_size
        }

    if active_usdt + next_position_size > allocated_usdt:
        return {
            "passed": False,
            "reason": "allocated_budget_exceeded",
            "active_usdt": active_usdt,
            "next_position_size": next_position_size,
            "allocated_usdt": allocated_usdt
        }

    return {
        "passed": True,
        "reason": None,
        "active_usdt": active_usdt,
        "next_position_size": next_position_size,
        "allocated_usdt": allocated_usdt
    }


def get_position_size(data: dict, settings: dict, candidate: dict) -> float:
    config = get_risk_config(settings)

    if not config["dynamic_position_size"]:
        return config["usdt_per_position"]

    allocated_usdt = config["allocated_usdt"]
    risk_percent = config["risk_per_position_percent"]

    dynamic_size = allocated_usdt * (risk_percent / 100)

    return round(
        min(dynamic_size, config["usdt_per_position"]),
        2
    )


def build_risk_snapshot(data: dict, settings: dict) -> dict:
    config = get_risk_config(settings)

    active_usdt = get_active_usdt(data)
    daily_pnl = daily_pnl_value(data)

    return {
        "active_usdt": active_usdt,
        "allocated_usdt": config["allocated_usdt"],
        "available_usdt": round(config["allocated_usdt"] - active_usdt, 2),

        "daily_pnl": daily_pnl,
        "daily_loss_limit": config["daily_loss_limit"],
        "daily_loss_remaining": round(config["daily_loss_limit"] + daily_pnl, 4),

        "max_open_positions": config["max_open_positions"],
        "open_positions_count": len(data.get("open_positions", [])),

        "usdt_per_position": config["usdt_per_position"],
        "dynamic_position_size": config["dynamic_position_size"],
        "max_same_direction_positions": config["max_same_direction_positions"],

        "risk_status": (
            "blocked"
            if daily_pnl <= -config["daily_loss_limit"]
            else "ok"
        )
    }