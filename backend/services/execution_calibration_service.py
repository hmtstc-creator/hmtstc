from __future__ import annotations

from collections import defaultdict
from math import isfinite
from statistics import mean
from typing import Any
from uuid import uuid4

from core.storage import now_iso


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
        return number if isfinite(number) else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _entry_execution(position: dict) -> dict:
    for key in ("execution_entry", "entry_execution", "execution", "entry_price_source"):
        value = position.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _exit_execution(position: dict) -> dict:
    for key in ("execution_exit", "exit_execution", "exit_price_source"):
        value = position.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _execution_quality_from_position(position: dict) -> float:
    entry = _entry_execution(position)
    exit_ = _exit_execution(position)
    values = [
        _safe_float(entry.get("execution_quality_score"), -1),
        _safe_float(exit_.get("execution_quality_score"), -1),
        _safe_float(position.get("execution_quality_score"), -1),
    ]
    valid = [value for value in values if value >= 0]
    return round(mean(valid), 2) if valid else 0.0


def _symbol_from_position(position: dict) -> str:
    return str(position.get("symbol") or position.get("coin") or "-").upper()


def build_execution_sample_index(data: dict) -> dict:
    """Build one normalized index for paper, dry-run and real execution evidence.

    This service is intentionally read-only. It does not create orders and does not mutate
    trading state. It only measures how realistic the simulator looks versus dry-run and
    real execution evidence already present in runtime stores.
    """
    paper_positions = _safe_list(data.get("open_positions")) + _safe_list(data.get("closed_positions")) + _safe_list(data.get("history"))
    real_state = data.get("real_trade") if isinstance(data.get("real_trade"), dict) else {}
    real_orders = _safe_list(real_state.get("orders")) + _safe_list(data.get("real_orders"))
    real_positions = _safe_list(real_state.get("positions")) + _safe_list(data.get("real_positions"))

    samples = []
    for position in paper_positions:
        if not isinstance(position, dict):
            continue
        entry = _entry_execution(position)
        exit_ = _exit_execution(position)
        samples.append({
            "sample_id": position.get("id") or position.get("position_id") or f"paper_{len(samples)+1}",
            "source": "paper",
            "symbol": _symbol_from_position(position),
            "model_id": position.get("model_id") or position.get("paper_model_id") or "-",
            "strategy_id": position.get("strategy_id") or "-",
            "quality": _execution_quality_from_position(position),
            "spread_percent": _safe_float(entry.get("spread_percent"), _safe_float(position.get("spread_percent"), 0)),
            "slippage_percent": _safe_float(entry.get("slippage_percent"), _safe_float(position.get("slippage_percent"), 0)),
            "commission_usdt": _safe_float(entry.get("commission_usdt")) + _safe_float(exit_.get("commission_usdt")),
            "source_price": _safe_float(entry.get("source_price"), _safe_float(position.get("entry"), 0)),
            "executed_price": _safe_float(entry.get("executed_price"), _safe_float(position.get("entry"), 0)),
            "pnl": _safe_float(position.get("pnl"), _safe_float(position.get("net_pnl"), 0)),
            "status": position.get("status") or "paper_sample",
            "timestamp": position.get("opened_at") or position.get("created_at") or position.get("time") or "",
        })

    for order in real_orders:
        if not isinstance(order, dict):
            continue
        dry_run = bool(order.get("dry_run", True))
        quality = _safe_float(order.get("execution_quality_score"), _safe_float(((order.get("safety") or {}).get("execution_quality_score")), 0))
        samples.append({
            "sample_id": order.get("order_id") or order.get("client_order_id") or f"order_{len(samples)+1}",
            "source": "dry_run" if dry_run else "real_order",
            "symbol": str(order.get("symbol") or "-").upper(),
            "model_id": order.get("model_id") or "-",
            "strategy_id": order.get("strategy_id") or "-",
            "quality": quality,
            "spread_percent": _safe_float(order.get("spread_percent"), 0),
            "slippage_percent": _safe_float(order.get("slippage_percent"), 0),
            "commission_usdt": _safe_float(order.get("commission_usdt"), 0),
            "source_price": _safe_float(order.get("source_price"), _safe_float(order.get("price"), 0)),
            "executed_price": _safe_float(order.get("executed_price"), _safe_float(order.get("price"), 0)),
            "pnl": _safe_float(order.get("pnl"), 0),
            "status": order.get("status") or ("dry_run" if dry_run else "real_order"),
            "timestamp": order.get("created_at") or order.get("checked_at") or order.get("time") or "",
        })

    for position in real_positions:
        if not isinstance(position, dict):
            continue
        samples.append({
            "sample_id": position.get("position_id") or position.get("id") or f"real_position_{len(samples)+1}",
            "source": "real_position",
            "symbol": _symbol_from_position(position),
            "model_id": position.get("model_id") or "-",
            "strategy_id": position.get("strategy_id") or "-",
            "quality": _safe_float(position.get("execution_quality_score"), 0),
            "spread_percent": _safe_float(position.get("spread_percent"), 0),
            "slippage_percent": _safe_float(position.get("slippage_percent"), 0),
            "commission_usdt": _safe_float(position.get("commission_usdt"), 0),
            "source_price": _safe_float(position.get("source_price"), _safe_float(position.get("entry_price"), 0)),
            "executed_price": _safe_float(position.get("avg_fill_price"), _safe_float(position.get("entry_price"), 0)),
            "pnl": _safe_float(position.get("realized_pnl"), _safe_float(position.get("unrealized_pnl"), 0)),
            "status": position.get("status") or "real_position",
            "timestamp": position.get("opened_at") or position.get("created_at") or "",
        })

    return {"status": "ok", "count": len(samples), "samples": samples[-500:]}


def _avg(items: list[float]) -> float:
    valid = [item for item in items if item is not None]
    return round(sum(valid) / len(valid), 4) if valid else 0.0


def build_execution_calibration_report(data: dict, settings: dict | None = None) -> dict:
    index = build_execution_sample_index(data)
    samples = index["samples"]
    by_source = defaultdict(list)
    by_symbol = defaultdict(list)
    by_model = defaultdict(list)

    for sample in samples:
        by_source[sample["source"]].append(sample)
        by_symbol[sample["symbol"]].append(sample)
        by_model[sample["model_id"]].append(sample)

    source_summary = {}
    for source, rows in by_source.items():
        source_summary[source] = {
            "count": len(rows),
            "avg_quality": _avg([_safe_float(row.get("quality")) for row in rows]),
            "avg_spread_percent": _avg([_safe_float(row.get("spread_percent")) for row in rows]),
            "avg_slippage_percent": _avg([_safe_float(row.get("slippage_percent")) for row in rows]),
            "avg_commission_usdt": _avg([_safe_float(row.get("commission_usdt")) for row in rows]),
        }

    paper_quality = source_summary.get("paper", {}).get("avg_quality", 0)
    dry_quality = source_summary.get("dry_run", {}).get("avg_quality", 0)
    real_quality = max(
        source_summary.get("real_order", {}).get("avg_quality", 0),
        source_summary.get("real_position", {}).get("avg_quality", 0),
    )
    drift_vs_dry_run = round(abs(paper_quality - dry_quality), 4) if dry_quality else None
    drift_vs_real = round(abs(paper_quality - real_quality), 4) if real_quality else None

    symbol_rows = []
    for symbol, rows in by_symbol.items():
        if symbol == "-":
            continue
        symbol_rows.append({
            "symbol": symbol,
            "samples": len(rows),
            "avg_quality": _avg([_safe_float(row.get("quality")) for row in rows]),
            "avg_spread_percent": _avg([_safe_float(row.get("spread_percent")) for row in rows]),
            "avg_slippage_percent": _avg([_safe_float(row.get("slippage_percent")) for row in rows]),
        })
    symbol_rows.sort(key=lambda row: (row["avg_quality"], row["samples"]), reverse=True)

    model_rows = []
    for model_id, rows in by_model.items():
        if model_id == "-":
            continue
        model_rows.append({
            "model_id": model_id,
            "samples": len(rows),
            "avg_quality": _avg([_safe_float(row.get("quality")) for row in rows]),
            "avg_slippage_percent": _avg([_safe_float(row.get("slippage_percent")) for row in rows]),
            "quality_penalty": round(max(0.0, 60.0 - _avg([_safe_float(row.get("quality")) for row in rows])) * 0.35, 4),
        })
    model_rows.sort(key=lambda row: (row["avg_quality"], row["samples"]), reverse=True)

    blockers = []
    warnings = []
    if source_summary.get("paper", {}).get("count", 0) == 0:
        warnings.append("paper_execution_samples_missing")
    if source_summary.get("dry_run", {}).get("count", 0) == 0:
        warnings.append("dry_run_samples_missing")
    if real_quality == 0:
        warnings.append("real_execution_samples_waiting")
    if drift_vs_dry_run is not None and drift_vs_dry_run > 25:
        blockers.append("paper_vs_dry_run_drift_high")
    if drift_vs_real is not None and drift_vs_real > 25:
        blockers.append("paper_vs_real_drift_high")

    calibration_score = 100.0
    calibration_score -= len(blockers) * 30
    calibration_score -= len(warnings) * 7
    if drift_vs_dry_run is not None:
        calibration_score -= min(20, drift_vs_dry_run * 0.4)
    if drift_vs_real is not None:
        calibration_score -= min(20, drift_vs_real * 0.4)
    calibration_score = round(max(0, min(100, calibration_score)), 2)

    status = "blocked" if blockers else ("review" if warnings or calibration_score < 75 else "ok")
    return {
        "status": status,
        "calibration_id": f"calib_{uuid4().hex[:12]}",
        "created_at": now_iso(),
        "calibration_score": calibration_score,
        "sample_count": len(samples),
        "source_summary": source_summary,
        "drift": {
            "paper_vs_dry_run_quality_delta": drift_vs_dry_run,
            "paper_vs_real_quality_delta": drift_vs_real,
            "interpretation": "Düşük delta, paper simulator davranışının dry-run/real execution ile daha uyumlu olduğunu gösterir.",
        },
        "model_execution_penalties": model_rows[:30],
        "symbol_execution_quality": symbol_rows[:30],
        "recent_samples": list(reversed(samples[-25:])),
        "blockers": blockers,
        "warnings": warnings,
        "message": "Execution calibration; Paper Lab, dry-run ve real fill kanıtlarını tek kalite raporunda karşılaştırır.",
    }


def build_simulator_drift_report(data: dict, settings: dict | None = None) -> dict:
    report = build_execution_calibration_report(data, settings)
    return {
        "status": report["status"],
        "calibration_score": report["calibration_score"],
        "drift": report["drift"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "source_summary": report["source_summary"],
    }
