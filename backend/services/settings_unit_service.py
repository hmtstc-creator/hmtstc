from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any

PERCENT_FIELDS = {
    "stop_loss", "take_profit", "risk_per_position_percent", "max_portfolio_risk_percent",
    "daily_loss_limit_percent", "weekly_loss_limit_percent", "max_slippage_percent",
    "max_spread_percent", "exposure_limit_percent", "drawdown_threshold_percent",
}
MONEY_FIELDS = {
    "allocated_usdt", "usdt_per_position", "slot_size", "max_position_value",
    "daily_loss_limit", "weekly_loss_limit", "reserve_usdt_amount",
}
INTEGER_FIELDS = {
    "max_open_positions", "slot_count", "max_same_direction_positions", "minimum_trade_count",
    "cooldown_minutes", "max_paper_models", "scan_limit", "scan_deep_analysis_limit",
}
DURATION_FIELDS = {
    "cooldown_minutes": "minutes",
    "new_coin_exclusion_days": "days",
    "report_period_days": "days",
    "model_observation_hours": "hours",
    "health_stale_threshold_minutes": "minutes",
}

FIELD_LABELS = {
    "stop_loss": "Stop Loss",
    "take_profit": "Kar Hedefi",
    "risk_per_position_percent": "Pozisyon Risk",
    "max_portfolio_risk_percent": "Maks. Portföy Risk",
    "max_slippage_percent": "Maks. Slippage",
    "max_spread_percent": "Maks. Spread",
    "allocated_usdt": "Bot Bütçesi",
    "usdt_per_position": "USDT / Pozisyon",
    "max_open_positions": "Maks. Açık Pozisyon",
    "daily_loss_limit": "Günlük Zarar Limiti",
    "weekly_loss_limit": "Haftalık Zarar Limiti",
}


def _clean_number(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    text = text.replace("₺", "").replace("$", "").replace("€", "")
    text = re.sub(r"\bUSDT\b", "", text, flags=re.IGNORECASE)
    text = text.replace("%", "").replace(" ", "").replace("\u00a0", "")
    if "," in text and "." in text:
        # Treat the last separator as decimal separator.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    return text


def parse_decimal(value: Any, fallback: float | None = None) -> float | None:
    if value is None or str(value).strip() == "":
        return fallback
    try:
        number = float(_clean_number(value))
        if not math.isfinite(number):
            return fallback
        return number
    except Exception:
        return fallback


def normalize_percent(value: Any, fallback: float = 0.0, minimum: float = 0.0, maximum: float = 100.0) -> dict:
    raw = value
    number = parse_decimal(value, fallback)
    if number is None:
        number = fallback
    number = max(minimum, min(float(number), maximum))
    return {
        "raw": raw,
        "value": round(number, 6),
        "unit": "percent",
        "display": f"{round(number, 4):g}%",
        "ratio": round(number / 100, 8),
    }


def normalize_money(value: Any, fallback: float = 0.0, minimum: float = 0.0, maximum: float = 1_000_000.0) -> dict:
    raw = value
    number = parse_decimal(value, fallback)
    if number is None:
        number = fallback
    number = max(minimum, min(float(number), maximum))
    return {
        "raw": raw,
        "value": round(number, 4),
        "unit": "USDT",
        "display": f"{round(number, 4):g} USDT",
    }


def normalize_integer(value: Any, fallback: int = 0, minimum: int = 0, maximum: int = 100_000) -> dict:
    raw = value
    number = parse_decimal(value, fallback)
    if number is None:
        number = fallback
    number = int(round(number))
    number = max(minimum, min(number, maximum))
    return {"raw": raw, "value": number, "unit": "adet", "display": str(number)}


def normalize_duration(value: Any, fallback: int = 0, unit: str = "minutes", minimum: int = 0, maximum: int = 525600) -> dict:
    normalized = normalize_integer(value, fallback=fallback, minimum=minimum, maximum=maximum)
    normalized["unit"] = unit
    labels = {"minutes": "dk", "hours": "saat", "days": "gün"}
    normalized["display"] = f"{normalized['value']} {labels.get(unit, unit)}"
    return normalized


def normalize_risk_settings(risk: dict | None) -> tuple[dict, dict]:
    risk = deepcopy(risk or {})
    units = {"percent_fields": {}, "money_fields": {}, "integer_fields": {}, "duration_fields": {}}

    percent_defaults = {
        "stop_loss": 0.75,
        "take_profit": 2.0,
        "risk_per_position_percent": 1.0,
        "max_portfolio_risk_percent": 5.0,
        "max_slippage_percent": 0.35,
        "max_spread_percent": 0.35,
        "daily_loss_limit_percent": 3.0,
        "weekly_loss_limit_percent": 9.0,
        "exposure_limit_percent": 25.0,
        "drawdown_threshold_percent": 8.0,
    }
    percent_ranges = {
        "stop_loss": (0.01, 20),
        "take_profit": (0.01, 100),
        "risk_per_position_percent": (0, 20),
        "max_portfolio_risk_percent": (0, 100),
        "max_slippage_percent": (0, 10),
        "max_spread_percent": (0, 10),
        "daily_loss_limit_percent": (0, 100),
        "weekly_loss_limit_percent": (0, 100),
        "exposure_limit_percent": (0, 100),
        "drawdown_threshold_percent": (0, 100),
    }
    for key, fallback in percent_defaults.items():
        minimum, maximum = percent_ranges.get(key, (0, 100))
        normalized = normalize_percent(risk.get(key, fallback), fallback=fallback, minimum=minimum, maximum=maximum)
        risk[key] = normalized["value"]
        units["percent_fields"][key] = normalized

    money_defaults = {"daily_loss_limit": 30.0, "weekly_loss_limit": 90.0}
    for key, fallback in money_defaults.items():
        normalized = normalize_money(risk.get(key, fallback), fallback=fallback, minimum=0)
        risk[key] = normalized["value"]
        units["money_fields"][key] = normalized

    integer_defaults = {"max_same_direction_positions": 3, "minimum_trade_count": 8, "cooldown_minutes": 15}
    for key, fallback in integer_defaults.items():
        normalized = normalize_integer(risk.get(key, fallback), fallback=fallback, minimum=0, maximum=1000)
        risk[key] = normalized["value"]
        units["integer_fields"][key] = normalized

    for key, unit in DURATION_FIELDS.items():
        if key in risk:
            normalized = normalize_duration(risk.get(key), fallback=int(risk.get(key) or 0), unit=unit, minimum=0)
            risk[key] = normalized["value"]
            units["duration_fields"][key] = normalized

    risk.setdefault("profile", "balanced")
    risk["unit_schema_version"] = 13
    return risk, units


def normalize_bot_settings(bot: dict | None) -> tuple[dict, dict]:
    bot = deepcopy(bot or {})
    units = {"money_fields": {}, "integer_fields": {}}
    money_defaults = {"allocated_usdt": 1000.0, "usdt_per_position": 50.0, "reserve_usdt_amount": 0.0, "max_position_value": 0.0}
    for key, fallback in money_defaults.items():
        normalized = normalize_money(bot.get(key, fallback), fallback=fallback, minimum=0)
        bot[key] = normalized["value"]
        units["money_fields"][key] = normalized
    integer_defaults = {"max_open_positions": 20, "slot_count": 20, "scan_limit": 1000, "scan_deep_analysis_limit": 80, "max_paper_models": 20}
    for key, fallback in integer_defaults.items():
        normalized = normalize_integer(bot.get(key, fallback), fallback=fallback, minimum=1, maximum=2000)
        bot[key] = normalized["value"]
        units["integer_fields"][key] = normalized
    if bot["usdt_per_position"] <= 0:
        bot["usdt_per_position"] = 50
    bot["slot_count"] = max(1, int(bot.get("slot_count") or round(bot["allocated_usdt"] / max(bot["usdt_per_position"], 1))))
    bot.setdefault("default_mode", "shadow")
    return bot, units


def normalize_settings_units(settings: dict | None) -> dict:
    settings = deepcopy(settings or {})
    bot, bot_units = normalize_bot_settings(settings.get("bot"))
    risk, risk_units = normalize_risk_settings(settings.get("risk"))
    settings["bot"] = {**(settings.get("bot") or {}), **bot, "default_mode": "shadow"}
    settings["risk"] = {**(settings.get("risk") or {}), **risk}
    settings.setdefault("api", {})["mode"] = "shadow"
    settings["unit_schema"] = {
        "version": 13,
        "bot": bot_units,
        "risk": risk_units,
        "user_input_policy": {
            "percent": "0,75 veya 0.75 yazımı yüzde olarak yorumlanır; % yazmak zorunlu değildir.",
            "money": "1000 yazımı USDT olarak yorumlanır.",
            "integer": "Adet alanları tam sayıya yuvarlanır.",
        },
    }
    settings["risk_calculation"] = calculate_risk_summary(settings)
    return settings


def calculate_risk_summary(settings: dict | None) -> dict:
    settings = settings or {}
    bot = settings.get("bot") or {}
    risk = settings.get("risk") or {}
    capital = float(bot.get("allocated_usdt") or 1000)
    slot_size = float(bot.get("usdt_per_position") or 50)
    max_open = int(bot.get("max_open_positions") or 1)
    stop_pct = float(risk.get("stop_loss") or 0.75)
    daily_loss = float(risk.get("daily_loss_limit") or 30)
    weekly_loss = float(risk.get("weekly_loss_limit") or 90)
    slot_risk = round(slot_size * (stop_pct / 100), 4)
    concurrent_risk = round(slot_risk * max_open, 4)
    max_portfolio_risk_pct = float(risk.get("max_portfolio_risk_percent") or 5)
    take_profit_pct = float(risk.get("take_profit") or 2)
    risk_reward = round(take_profit_pct / stop_pct, 4) if stop_pct > 0 else 0
    deployed_capacity = round(slot_size * max_open, 4)
    deployed_capacity_pct = round((deployed_capacity / capital) * 100, 4) if capital > 0 else 0
    portfolio_risk_cap_usdt = round(capital * (max_portfolio_risk_pct / 100), 4)
    return {
        "capital_usdt": round(capital, 4),
        "slot_size_usdt": round(slot_size, 4),
        "max_open_positions": max_open,
        "effective_stop_loss_percent": round(stop_pct, 4),
        "effective_take_profit_percent": round(take_profit_pct, 4),
        "risk_reward_ratio": risk_reward,
        "slot_risk_usdt": slot_risk,
        "max_concurrent_risk_usdt": concurrent_risk,
        "worst_case_open_loss_usdt": concurrent_risk,
        "portfolio_risk_cap_usdt": portfolio_risk_cap_usdt,
        "concurrent_risk_percent_of_capital": round((concurrent_risk / capital) * 100, 4) if capital > 0 else 0,
        "deployed_capacity_usdt": deployed_capacity,
        "deployed_capacity_percent": deployed_capacity_pct,
        "unused_reserve_usdt": round(max(capital - deployed_capacity, 0), 4),
        "daily_loss_limit_usdt": round(daily_loss, 4),
        "weekly_loss_limit_usdt": round(weekly_loss, 4),
        "daily_stop_capacity": int(daily_loss / slot_risk) if slot_risk > 0 else 0,
        "weekly_stop_capacity": int(weekly_loss / slot_risk) if slot_risk > 0 else 0,
        "real_trade_readiness": "locked_review" if concurrent_risk <= daily_loss and concurrent_risk <= portfolio_risk_cap_usdt and capital > 0 else "blocked",
        "paper_lab_readiness": "ok" if capital > 0 and slot_size > 0 else "blocked",
        "risk_notes": [
            "Stop loss kullanıcı girdisi yüzde olarak normalize edilir.",
            "Günlük/haftalık zarar limitleri USDT kabul edilir.",
            "Worst-case açık risk, slot riski x maksimum açık pozisyon olarak hesaplanır.",
        ],
    }


def validate_normalized_settings(settings: dict | None) -> dict:
    normalized = normalize_settings_units(settings)
    errors = []
    warnings = []
    bot = normalized.get("bot") or {}
    risk = normalized.get("risk") or {}
    capital = float(bot.get("allocated_usdt") or 0)
    slot = float(bot.get("usdt_per_position") or 0)
    max_open = int(bot.get("max_open_positions") or 0)
    if capital <= 0:
        errors.append({"field": "bot.allocated_usdt", "message": "Bot bütçesi pozitif USDT olmalı."})
    if slot <= 0:
        errors.append({"field": "bot.usdt_per_position", "message": "Pozisyon büyüklüğü pozitif USDT olmalı."})
    if max_open <= 0:
        errors.append({"field": "bot.max_open_positions", "message": "Maksimum açık pozisyon en az 1 olmalı."})
    if slot * max_open > capital * 1.5:
        warnings.append({"field": "bot.usdt_per_position", "message": "Toplam slot kapasitesi sermayeyi yüksek oranda aşıyor."})
    for key in ["stop_loss", "take_profit", "risk_per_position_percent", "max_portfolio_risk_percent", "max_slippage_percent", "max_spread_percent"]:
        value = float(risk.get(key) or 0)
        if value < 0:
            errors.append({"field": f"risk.{key}", "message": "Negatif değer kullanılamaz."})
    if float(risk.get("stop_loss") or 0) > 10:
        warnings.append({"field": "risk.stop_loss", "message": "Stop loss değeri spot scalping için yüksek görünüyor."})
    return {"ok": not errors, "valid": not errors, "errors": errors, "warnings": warnings, "normalized": normalized}


def standard_success(data: Any = None, **extra) -> dict:
    payload = {"ok": True, "data": data if data is not None else {}}
    payload.update(extra)
    return payload


def standard_error(code: str, message: str, field: str | None = None, expected: str | None = None, received: Any = None) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "field": field, "expected": expected, "received": received}}
