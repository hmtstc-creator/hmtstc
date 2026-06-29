from services.risk_service import can_open_new_position, is_daily_loss_limit_reached


def _safe_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def build_karabasan_hard_blocks(runtime: dict, settings: dict, strategy_output: dict | None = None) -> dict:
    strategy_output = strategy_output if isinstance(strategy_output, dict) else {}
    candidate = strategy_output.get("candidate") if isinstance(strategy_output.get("candidate"), dict) else strategy_output
    signal = strategy_output.get("strategy_output") if isinstance(strategy_output.get("strategy_output"), dict) else strategy_output
    symbol = str(candidate.get("symbol") or signal.get("symbol") or "").upper()
    blocks = []
    warnings = []

    last_scan = runtime.get("last_scan") if isinstance(runtime.get("last_scan"), dict) else {}
    api_available = bool(
        runtime.get("api_connected")
        or runtime.get("binance_connected")
        or (last_scan.get("status") == "ok" and last_scan.get("live") is True)
    )
    if not api_available:
        blocks.append("api_unavailable")
    if not runtime.get("bot_running", False):
        blocks.append("bot_not_running")
    if runtime.get("emergency_stop") or str(runtime.get("engine_status") or "") == "emergency_stopped":
        blocks.append("emergency_stop_active")
    if signal.get("signal") not in {"BUY", "LONG"}:
        blocks.append("strategy_signal_not_approved")

    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    coin_filter = settings.get("coin_filter") if isinstance(settings.get("coin_filter"), dict) else {}
    spread = candidate.get("spread_percent")
    max_spread = _safe_float(risk.get("max_spread_percent"), 0.35)
    if spread is None:
        blocks.append("spread_unavailable")
    elif _safe_float(spread, max_spread + 1) > max_spread:
        blocks.append("spread_limit_exceeded")

    quote_volume = _safe_float(candidate.get("quote_volume") or candidate.get("volume_today"))
    min_quote_volume = _safe_float(coin_filter.get("min_quote_volume"), 1_000_000)
    if quote_volume < min_quote_volume:
        blocks.append("liquidity_below_minimum")

    daily_loss = is_daily_loss_limit_reached(runtime, settings)
    if daily_loss.get("reached"):
        blocks.append("daily_loss_limit_reached")

    if symbol:
        risk_check = can_open_new_position(runtime, settings, symbol)
        if not risk_check.get("passed"):
            blocks.append(str(risk_check.get("reason") or "risk_limit_rejected"))
    else:
        blocks.append("symbol_missing")

    confidence = _safe_float(signal.get("confidence"))
    if confidence < 60:
        warnings.append("strategy_confidence_below_60")
    if spread is not None and _safe_float(spread) > max_spread * 0.75:
        warnings.append("spread_near_limit")

    return {
        "symbol": symbol or None,
        "blocks": list(dict.fromkeys(blocks)),
        "warnings": list(dict.fromkeys(warnings)),
        "has_hard_block": bool(blocks),
        "risk_check": risk_check if symbol else {"passed": False, "reason": "symbol_missing"},
    }


def build_karabasan_hard_block_report(runtime, settings, signal=None):
    result = build_karabasan_hard_blocks(runtime, settings, signal)
    return {
        "title": "Karabasan hard block raporu",
        "has_hard_block": result["has_hard_block"],
        "blocks": result["blocks"],
        "warnings": result["warnings"],
        "blocking_reasons": result["blocks"],
        "decision": "block" if result["has_hard_block"] else "allow",
        "critical_blocks": ["api", "bot", "risk_limit", "liquidity", "spread", "same_symbol", "daily_loss"],
        "rule": "Hard block varsa toplam skor yüksek olsa bile işlem açılmaz.",
    }
