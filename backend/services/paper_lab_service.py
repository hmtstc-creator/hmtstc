from copy import deepcopy
from datetime import datetime
import time
from uuid import uuid4

from core.storage import now_iso
from services.market_service import get_current_price
from services.execution_simulator import simulate_entry, simulate_exit
from services.model_registry import build_model_registry, get_default_real_model_id
from services.rule_engine import build_custom_models, evaluate_rule


def _safe_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_score(value, max_value=100.0):
    value = _safe_float(value)
    if value <= 0:
        return 0.0
    return max(0.0, min(value, max_value))


def _component_scores(candidate: dict) -> dict:
    quote_volume = _safe_float(candidate.get("quote_volume"), _safe_float(candidate.get("volume_today")))
    volume_today = _safe_float(candidate.get("volume_today"))
    volatility = _safe_float(candidate.get("volatility"))
    rsi_value = _safe_float(candidate.get("rsi"))

    liquidity = min(max(quote_volume, volume_today) / 5_000_000 * 100, 100)
    volatility_score = 100 - min(abs(volatility - 2.0) * 30, 100)
    momentum = 0
    momentum += 35 if candidate.get("volume_growth") else 0
    momentum += 35 if candidate.get("macd_signal") else 0
    momentum += 30 if 50 <= rsi_value <= 72 else 0
    trend = 70 if candidate.get("ema_signal") else 20
    if candidate.get("rsi_signal"):
        trend += 20
    spread = 85
    data_quality = 100 if _safe_float(candidate.get("price")) > 0 else 0

    return {
        "liquidity": round(_normalize_score(liquidity), 2),
        "volatility": round(_normalize_score(volatility_score), 2),
        "momentum": round(_normalize_score(momentum), 2),
        "trend": round(_normalize_score(trend), 2),
        "spread": round(_normalize_score(spread), 2),
        "data_quality": round(_normalize_score(data_quality), 2),
    }


def evaluate_filter(candidate: dict, filter_item: dict) -> dict:
    components = _component_scores(candidate)
    weights = filter_item.get("weights", {})
    score = 0.0

    for key, value in components.items():
        score += value * _safe_float(weights.get(key), 0)

    score = round(score, 2)
    min_score = _safe_float(filter_item.get("min_score"), 65)
    passed = score >= min_score

    return {
        "filter_id": filter_item.get("id"),
        "filter_score": score,
        "filter_passed": passed,
        "filter_components": components,
        "filter_reject_reason": None if passed else "filter_score_below_threshold",
    }


def evaluate_strategy(candidate: dict, strategy_id: str) -> dict:
    volatility = _safe_float(candidate.get("volatility"))
    rsi_value = _safe_float(candidate.get("rsi"))
    ema_signal = bool(candidate.get("ema_signal"))
    macd_signal = bool(candidate.get("macd_signal"))
    volume_growth = bool(candidate.get("volume_growth"))

    if strategy_id == "STRATEGY_TREND_1":
        passed = ema_signal and macd_signal and 48 <= rsi_value <= 72
        reason = None if passed else "trend_conditions_not_met"
    elif strategy_id == "STRATEGY_PULLBACK_1":
        passed = ema_signal and 42 <= rsi_value <= 62 and volatility >= 0.4
        reason = None if passed else "pullback_conditions_not_met"
    elif strategy_id == "STRATEGY_BREAKOUT_1":
        passed = volume_growth and macd_signal and volatility >= 0.8 and rsi_value >= 52
        reason = None if passed else "breakout_conditions_not_met"
    elif strategy_id == "STRATEGY_MOMENTUM_1":
        passed = volume_growth and macd_signal and 55 <= rsi_value <= 78
        reason = None if passed else "momentum_conditions_not_met"
    else:
        passed = False
        reason = "unknown_strategy"

    return {
        "strategy_id": strategy_id,
        "strategy_signal": passed,
        "strategy_reject_reason": reason,
    }


def _canonical_model_id(filter_id: str | None, strategy_id: str | None, fallback: str | None = None) -> str:
    if filter_id and strategy_id:
        return f"{filter_id}__{strategy_id}"
    fallback = str(fallback or "").strip()
    parts = fallback.split("__")
    if len(parts) >= 2:
        return "__".join(parts[:2])
    return fallback


def _clean_risk_profile_fields(item: dict):
    if not isinstance(item, dict):
        return
    item.pop("risk_profile_id", None)
    item.pop("risk_profile_name", None)
    snapshot = item.get("rule_snapshot")
    if isinstance(snapshot, dict):
        snapshot.pop("risk_profile_id", None)
        snapshot.pop("risk_profile_name", None)


def _merge_unique(target_items: list, source_items: list, model_id: str) -> list:
    seen = {str(item.get("id")) for item in target_items if isinstance(item, dict) and item.get("id")}
    for item in source_items or []:
        if not isinstance(item, dict):
            continue
        cloned = deepcopy(item)
        cloned["model_id"] = model_id
        _clean_risk_profile_fields(cloned)
        item_id = str(cloned.get("id") or "")
        if item_id and item_id in seen:
            continue
        target_items.append(cloned)
        if item_id:
            seen.add(item_id)
    return target_items


def _migrate_risk_profile_models(models: dict) -> dict:
    if not isinstance(models, dict):
        return {}

    migrated: dict = {}
    for key, raw_model in list(models.items()):
        if not isinstance(raw_model, dict):
            continue
        canonical_id = _canonical_model_id(raw_model.get("filter_id"), raw_model.get("strategy_id"), key)
        if not canonical_id:
            continue
        target = migrated.setdefault(canonical_id, {})
        if not target:
            target.update(deepcopy(raw_model))
            target["model_id"] = canonical_id
            _clean_risk_profile_fields(target)
            target["open_positions"] = []
            target["history"] = []
        target.setdefault("filter_id", raw_model.get("filter_id"))
        target.setdefault("strategy_id", raw_model.get("strategy_id"))
        target.setdefault("compatibility", raw_model.get("compatibility", "primary"))
        target.setdefault("source", raw_model.get("source", "system"))
        target.setdefault("filter_rule", raw_model.get("filter_rule"))
        target.setdefault("strategy_rule", raw_model.get("strategy_rule"))
        _merge_unique(target.setdefault("open_positions", []), raw_model.get("open_positions", []), canonical_id)
        _merge_unique(target.setdefault("history", []), raw_model.get("history", []), canonical_id)

    return migrated


def _upsert_lab_model(models: dict, model: dict):
    model_id = _canonical_model_id(model.get("filter_id"), model.get("strategy_id"), model.get("model_id"))
    existing = models.setdefault(model_id, {})

    existing["model_id"] = model_id
    existing.setdefault("filter_id", model.get("filter_id"))
    existing.setdefault("strategy_id", model.get("strategy_id"))
    existing.setdefault("compatibility", model.get("compatibility", "primary"))
    existing.setdefault("source", model.get("source", "system"))
    existing.setdefault("filter_rule", model.get("filter_rule"))
    existing.setdefault("strategy_rule", model.get("strategy_rule"))

    existing.setdefault("wallet_start", model.get("wallet_start", 1000))
    existing.setdefault("wallet_value", model.get("wallet_start", 1000))
    existing.setdefault("slot_size", model.get("slot_size", 200))
    existing.setdefault("max_slots", model.get("max_slots", 5))
    existing.setdefault("max_open_positions", model.get("max_open_positions", 5))
    existing.setdefault("take_profit_percent", model.get("take_profit_percent", 1.5))
    existing.setdefault("stop_loss_percent", model.get("stop_loss_percent", 2.0))

    existing.setdefault("open_positions", [])
    existing.setdefault("history", [])
    existing.setdefault("status", "active")
    _clean_risk_profile_fields(existing)

    for position in existing.get("open_positions", []) or []:
        if isinstance(position, dict):
            position["model_id"] = model_id
            _clean_risk_profile_fields(position)
    for trade in existing.get("history", []) or []:
        if isinstance(trade, dict):
            trade["model_id"] = model_id
            _clean_risk_profile_fields(trade)

    return existing



def ensure_paper_lab(data: dict) -> dict:
    registry = build_model_registry(include_secondary=True)
    lab = data.setdefault("paper_lab", {})
    models = lab.setdefault("models", {})
    models = _migrate_risk_profile_models(models)

    for model in registry["models"]:
        _upsert_lab_model(models, model)

    username = str(data.get("username") or data.get("user") or "ahmet")
    try:
        custom_models, compatibility_logs = build_custom_models(username)
    except Exception:
        custom_models, compatibility_logs = [], []

    for model in custom_models:
        _upsert_lab_model(models, model)

    lab["models"] = models

    active_real_model_id = _canonical_model_id(None, None, lab.get("active_real_model_id") or get_default_real_model_id())
    lab["active_real_model_id"] = active_real_model_id if active_real_model_id in models else get_default_real_model_id()
    lab["registry_count"] = registry["count"] + len(custom_models)
    lab["custom_registry_count"] = len(custom_models)
    lab["last_compatibility_logs"] = compatibility_logs[-100:]
    lab["last_updated_at"] = now_iso()
    return lab


def _calculate_pnl(entry, current, quantity):
    return round((_safe_float(current) - _safe_float(entry)) * _safe_float(quantity), 4)


def _update_model_positions(model_state: dict, price_cache: dict | None = None, settings: dict | None = None, *, cancel_requested=None, deadline: float | None = None):
    remaining = []
    history = model_state.setdefault("history", [])
    tp = _safe_float(model_state.get("take_profit_percent"), 2.0) / 100
    sl = _safe_float(model_state.get("stop_loss_percent"), 1.0) / 100

    price_cache = price_cache if price_cache is not None else {}

    open_positions = model_state.get("open_positions", [])
    for position_index, position in enumerate(open_positions):
        if (callable(cancel_requested) and cancel_requested()) or (deadline is not None and time.monotonic() >= deadline):
            remaining.extend(open_positions[position_index:])
            break
        symbol = position.get("symbol")
        entry = _safe_float(position.get("entry"))
        quantity = _safe_float(position.get("quantity"))

        if not symbol or entry <= 0 or quantity <= 0:
            remaining.append(position)
            continue

        try:
            if symbol in price_cache:
                current = price_cache[symbol]
            else:
                remaining_timeout = max(0.1, min(3.0, (deadline - time.monotonic()) if deadline is not None else 3.0))
                current = get_current_price(symbol, timeout=remaining_timeout)
                price_cache[symbol] = current
        except Exception:
            current = _safe_float(position.get("current"), entry)

        position["current"] = current
        position["pnl"] = _calculate_pnl(entry, current, quantity)
        position["last_price_update_at"] = now_iso()

        close_reason = None
        if current >= entry * (1 + tp):
            close_reason = "Take Profit"
        elif current <= entry * (1 - sl):
            close_reason = "Stop Loss"

        if close_reason:
            closed = deepcopy(position)
            execution = simulate_exit(position, current, settings or {}, close_reason)
            closed["exit"] = execution.get("executed_price", current)
            closed["exit_time"] = execution.get("filled_at") or now_iso()
            closed["reason"] = close_reason
            closed["status"] = "closed"
            closed["execution_exit"] = execution
            closed["pnl"] = execution.get("net_pnl", position.get("pnl", 0))
            try:
                start_ts = datetime.fromisoformat(str(position.get("entry_time")).replace("Z", "+00:00"))
                end_ts = datetime.fromisoformat(str(closed.get("exit_time")).replace("Z", "+00:00"))
                closed["holding_seconds"] = max(0, int((end_ts - start_ts).total_seconds()))
            except Exception:
                closed["holding_seconds"] = 0
            history.append(closed)
        else:
            remaining.append(position)

    model_state["open_positions"] = remaining
    model_state["history"] = history[-5000:]


def _recalculate_wallet(model_state: dict):
    realized = sum(_safe_float(item.get("pnl")) for item in model_state.get("history", []))
    unrealized = sum(_safe_float(item.get("pnl")) for item in model_state.get("open_positions", []))
    total = round(realized + unrealized, 4)
    start = _safe_float(model_state.get("wallet_start"), 1000.0)

    model_state["realized_pnl"] = round(realized, 4)
    model_state["unrealized_pnl"] = round(unrealized, 4)
    model_state["total_pnl"] = total
    model_state["wallet_value"] = round(start + total, 4)


def _can_open_for_model(model_state: dict, symbol: str) -> bool:
    open_positions = model_state.get("open_positions", [])
    if len(open_positions) >= int(model_state.get("max_open_positions") or 1):
        return False
    if any(item.get("symbol") == symbol for item in open_positions):
        return False
    slot_size = _safe_float(model_state.get("slot_size"), 50)
    used = sum(_safe_float(item.get("usdt_size")) for item in open_positions)
    max_budget = _safe_float(model_state.get("wallet_start"), 1000)
    return used + slot_size <= max_budget


def run_paper_lab_tick(data: dict, scan: dict, settings: dict | None = None, *, cancel_requested=None, deadline: float | None = None) -> dict:
    if not scan or scan.get("status") != "ok":
        return {"status": "skipped", "reason": "scan_not_ok"}

    settings = settings or {}
    lab = ensure_paper_lab(data)
    registry = build_model_registry(include_secondary=True)
    filter_map = {item["id"]: item for item in registry["filters"]}
    candidates = scan.get("candidates", []) or []
    opened_count = 0

    price_cache = {}

    for model in lab.get("models", {}).values():
        if (callable(cancel_requested) and cancel_requested()) or (deadline is not None and time.monotonic() >= deadline):
            return {"status": "cancelled", "reason": "scan_worker_cancelled"}
        if model.get("status") != "active":
            continue
        _update_model_positions(model, price_cache, settings, cancel_requested=cancel_requested, deadline=deadline)

    for candidate in candidates:
        if (callable(cancel_requested) and cancel_requested()) or (deadline is not None and time.monotonic() >= deadline):
            return {"status": "cancelled", "reason": "scan_worker_cancelled"}
        symbol = candidate.get("symbol")
        price = _safe_float(candidate.get("price"))
        if not symbol or price <= 0:
            continue

        for model in lab.get("models", {}).values():
            if (callable(cancel_requested) and cancel_requested()) or (deadline is not None and time.monotonic() >= deadline):
                return {"status": "cancelled", "reason": "scan_worker_cancelled"}
            if model.get("status") != "active":
                continue

            if model.get("source") == "user_rule":
                filter_rule = model.get("filter_rule") or {}
                strategy_rule = model.get("strategy_rule") or {}
                custom_filter = evaluate_rule(filter_rule, candidate)
                if not custom_filter.get("passed"):
                    continue
                custom_strategy = evaluate_rule(strategy_rule, candidate)
                if not custom_strategy.get("passed"):
                    continue
                filter_result = {
                    "filter_id": model.get("filter_id"),
                    "filter_score": custom_filter.get("score", candidate.get("score")),
                    "filter_passed": True,
                    "filter_components": {},
                    "filter_reject_reason": None,
                    "rule_version": filter_rule.get("version"),
                }
                strategy_result = {
                    "strategy_id": model.get("strategy_id"),
                    "strategy_signal": True,
                    "strategy_reject_reason": None,
                    "rule_version": strategy_rule.get("version"),
                }
            else:
                filter_item = filter_map.get(model.get("filter_id"))
                if not filter_item:
                    continue

                filter_result = evaluate_filter(candidate, filter_item)
                if not filter_result["filter_passed"]:
                    continue

                strategy_result = evaluate_strategy(candidate, model.get("strategy_id"))
                if not strategy_result["strategy_signal"]:
                    continue

            if not _can_open_for_model(model, symbol):
                continue

            slot_size = _safe_float(model.get("slot_size"), 50)
            execution = simulate_entry(candidate, slot_size, settings)
            if execution.get("status") != "filled":
                model.setdefault("execution_rejections", []).append({
                    "time": now_iso(),
                    "symbol": symbol,
                    "reason": execution.get("reason"),
                    "quality": execution.get("quality"),
                    "scan_id": scan.get("scan_id"),
                })
                model["execution_rejections"] = model.get("execution_rejections", [])[-250:]
                continue
            quantity = execution.get("quantity", round(slot_size / price, 8))
            rule_snapshot = None
            if model.get("source") == "user_rule":
                rule_snapshot = {
                    "filter_id": model.get("filter_id"),
                    "filter_version": (model.get("filter_rule") or {}).get("version"),
                    "strategy_id": model.get("strategy_id"),
                    "strategy_version": (model.get("strategy_rule") or {}).get("version"),
                    "captured_at": now_iso(),
                }
            position = {
                "id": str(uuid4()),
                "mode": "paper_lab",
                "model_id": model.get("model_id"),
                "filter_id": model.get("filter_id"),
                "strategy_id": model.get("strategy_id"),
                "scan_id": scan.get("scan_id"),
                "symbol": symbol,
                "entry": execution.get("executed_price", price),
                "entry_source_price": execution.get("source_price", price),
                "current": price,
                "quantity": quantity,
                "usdt_size": slot_size,
                "pnl": 0,
                "entry_time": execution.get("filled_at") or now_iso(),
                "status": "open",
                "execution_entry": execution,
                "rule_snapshot": rule_snapshot,
                "entry_signal": {
                    **filter_result,
                    **strategy_result,
                    "candidate_score": candidate.get("score"),
                    "rsi": candidate.get("rsi"),
                    "volatility": candidate.get("volatility"),
                    "volume_growth": candidate.get("volume_growth"),
                },
            }
            model.setdefault("open_positions", []).append(position)
            opened_count += 1

    for model in lab.get("models", {}).values():
        _recalculate_wallet(model)

    lab["last_scan_id"] = scan.get("scan_id")
    lab["last_run_at"] = now_iso()
    lab["last_opened_count"] = opened_count

    return {
        "status": "ok",
        "models_count": len(lab.get("models", {})),
        "opened_count": opened_count,
        "last_run_at": lab["last_run_at"],
    }


def _history_drawdown(history: list[dict]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in history or []:
        equity += _safe_float(trade.get("pnl"))
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 4)


def _history_exposure_seconds(history: list[dict]) -> int:
    total = 0
    for trade in history or []:
        total += int(_safe_float(trade.get("holding_seconds"), 0))
    return total


def get_model_rankings(data: dict) -> list[dict]:
    lab = ensure_paper_lab(data)
    rows = []

    for model in lab.get("models", {}).values():
        history = model.get("history", []) or []
        open_positions = model.get("open_positions", []) or []
        wins = [item for item in history if _safe_float(item.get("pnl")) > 0]
        losses = [item for item in history if _safe_float(item.get("pnl")) < 0]
        gross_profit = sum(_safe_float(item.get("pnl")) for item in wins)
        gross_loss = abs(sum(_safe_float(item.get("pnl")) for item in losses))
        total_trades = len(history)
        win_rate = (len(wins) / total_trades * 100) if total_trades else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
        realized_pnl = _safe_float(model.get("realized_pnl"), sum(_safe_float(item.get("pnl")) for item in history))
        unrealized_pnl = _safe_float(model.get("unrealized_pnl"), sum(_safe_float(item.get("pnl")) for item in open_positions))
        total_pnl = round(realized_pnl + unrealized_pnl, 4)
        wallet_start = _safe_float(model.get("wallet_start"), 1000.0)
        wallet_value = round(wallet_start + total_pnl, 4)
        open_count = len(open_positions)
        avg_win = gross_profit / len(wins) if wins else 0
        avg_loss = gross_loss / len(losses) if losses else 0
        expectancy = ((win_rate / 100) * avg_win) - ((1 - win_rate / 100) * avg_loss) if total_trades else 0
        drawdown_value = _history_drawdown(history)
        max_drawdown_percent = round((drawdown_value / wallet_start) * 100, 4) if wallet_start else 0
        exposure_seconds = _history_exposure_seconds(history)
        open_exposure = sum(_safe_float(item.get("usdt_size")) for item in open_positions)
        risk_exposure_percent = round((open_exposure / wallet_start) * 100, 2) if wallet_start else 0
        execution_samples = []
        for trade in history:
            entry_exec = trade.get("execution_entry") or {}
            exit_exec = trade.get("execution_exit") or {}
            if entry_exec.get("execution_quality_score") is not None:
                execution_samples.append(_safe_float(entry_exec.get("execution_quality_score")))
            if exit_exec.get("execution_quality_score") is not None:
                execution_samples.append(_safe_float(exit_exec.get("execution_quality_score")))
        for position in open_positions:
            entry_exec = position.get("execution_entry") or {}
            if entry_exec.get("execution_quality_score") is not None:
                execution_samples.append(_safe_float(entry_exec.get("execution_quality_score")))
        execution_quality_score = round(sum(execution_samples) / len(execution_samples), 2) if execution_samples else 50.0

        pnl_score = max(0, min(100, 50 + total_pnl * 2))
        pf_score = max(0, min(100, profit_factor * 25))
        drawdown_score = max(0, min(100, 100 - abs(max_drawdown_percent) * 8))
        win_score = max(0, min(100, win_rate))
        trade_score = max(0, min(100, total_trades * 8))
        exposure_score = max(0, min(100, 100 - max(0, risk_exposure_percent - 30) * 2))
        recent = history[-20:]
        recent_wins = [item for item in recent if _safe_float(item.get("pnl")) > 0]
        recent_pnl = sum(_safe_float(item.get("pnl")) for item in recent)
        trade_depth_score = 90 if total_trades >= 20 else (75 if total_trades >= 10 else (60 if total_trades >= 5 else (35 if total_trades >= 1 else 0)))
        consistency_score = (len(recent_wins) / len(recent) * 100) if recent else 0
        drawdown_penalty = min(45, abs(max_drawdown_percent) * 4)
        aggression_penalty = max(0, risk_exposure_percent - 35) * 1.4
        recency_score = 65 + max(-35, min(35, recent_pnl * 2)) if recent else 0
        stability_score = max(0, min(100, trade_depth_score * 0.35 + consistency_score * 0.25 + recency_score * 0.25 - drawdown_penalty - aggression_penalty))

        score_components = {
            "pnl": round(pnl_score, 2),
            "profit_factor": round(pf_score, 2),
            "drawdown": round(drawdown_score, 2),
            "win_rate": round(win_score, 2),
            "trade_count": round(trade_score, 2),
            "stability": round(stability_score, 2),
            "exposure": round(exposure_score, 2),
            "execution_quality": round(execution_quality_score, 2),
        }
        score = round(
            pnl_score * 0.21 +
            pf_score * 0.15 +
            drawdown_score * 0.18 +
            win_score * 0.10 +
            trade_score * 0.11 +
            stability_score * 0.13 +
            exposure_score * 0.05 +
            execution_quality_score * 0.07,
            2,
        )

        rows.append({
            "model_id": model.get("model_id"),
            "filter_id": model.get("filter_id"),
            "strategy_id": model.get("strategy_id"),
            "source": model.get("source", "registry"),
            "compatibility": model.get("compatibility"),
            "wallet_start": wallet_start,
            "wallet_value": wallet_value,
            "total_pnl": total_pnl,
            "realized_pnl": round(realized_pnl, 4),
            "unrealized_pnl": round(unrealized_pnl, 4),
            "open_positions": open_count,
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "expectancy": round(expectancy, 4),
            "max_drawdown": drawdown_value,
            "max_drawdown_percent": max_drawdown_percent,
            "exposure_seconds": exposure_seconds,
            "risk_exposure_percent": risk_exposure_percent,
            "execution_quality_score": round(execution_quality_score, 2),
            "stability_score": round(stability_score, 2),
            "score_components": score_components,
            "score": score,
        })

    rows.sort(key=lambda item: (item["score"], item["total_pnl"], item["total_trades"]), reverse=True)
    count = len(rows)
    cutoff = int(count * 0.6) if count else 0
    cutoff = max(cutoff, 1) if count else 0

    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        row["evaluation_group"] = "top_60" if index <= cutoff else "bottom_40"
        row["eligible_for_real"] = (
            index <= cutoff
            and _safe_float(row.get("total_trades")) >= 5
            and abs(_safe_float(row.get("max_drawdown_percent"))) <= 8
            and _safe_float(row.get("stability_score")) >= 55
            and _safe_float(row.get("execution_quality_score")) >= 45
        )

    return rows
