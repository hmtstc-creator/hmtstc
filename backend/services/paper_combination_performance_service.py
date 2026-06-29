from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.storage import now_iso
from services.model_registry import build_model_registry
from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.strategy_filter_toggle_service import get_strategy_filter_toggles


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _plain_name(value: Any, item_type: str) -> str:
    text = str(value or "").replace("_", " ").replace("-", " ").strip()
    lower = text.lower()
    if item_type == "strategy":
        if "choch" in lower or "yön" in lower or "yon" in lower:
            return "Yön değişimi"
        if "imbalance" in lower or "boşluk" in lower or "bosluk" in lower:
            return "Boşluk fırsatı"
        if "trend" in lower:
            return "Trend takibi"
        if "pullback" in lower:
            return "Geri dönüş fırsatı"
        if "breakout" in lower:
            return "Kırılım fırsatı"
        if "momentum" in lower:
            return "Güçlü hareket"
        return text.title() if text else "Strateji"
    if "spread" in lower or "liquid" in lower:
        return "Al-sat farkı güvenliği"
    if "volume" in lower or "hacim" in lower or "momentum" in lower:
        return "Hacim kontrolü"
    if "stable" in lower or "quality" in lower:
        return "Kalite kontrolü"
    return text.title() if text else "Filtre"


def _decision(pnl: float, win_rate: float, trades: int, max_drawdown: float = 0.0) -> tuple[str, str]:
    wr = win_rate * 100 if 0 <= win_rate <= 1 else win_rate
    if trades < 10:
        return "Daha çok izle", "warn"
    if pnl > 0 and wr >= 60 and abs(max_drawdown) <= 8:
        return "Güçlü", "ok"
    if pnl > 0 and wr >= 50:
        return "İzle", "warn"
    if pnl < 0 and wr < 50:
        return "Kapat", "bad"
    return "Zayıf", "off"


def _active_sets(user: str) -> tuple[set[str], set[str]]:
    try:
        toggles = get_strategy_filter_toggles(user)
    except Exception:
        toggles = {}
    strategies = {str(v) for v in toggles.get("selected_strategy_ids") or []}
    filters = {str(v) for v in toggles.get("selected_filter_ids") or []}
    return strategies, filters


def _registry_names() -> tuple[dict[str, str], dict[str, str]]:
    registry = build_model_registry(include_secondary=True)
    strategy_names = {str(item.get("id")): str(item.get("name") or item.get("id")) for item in registry.get("strategies", [])}
    filter_names = {str(item.get("id")): str(item.get("name") or item.get("id")) for item in registry.get("filters", [])}
    return strategy_names, filter_names


def _aggregate_from_rankings(rankings: list[dict], user: str) -> list[dict]:
    active_strategies, active_filters = _active_sets(user)
    strategy_names, filter_names = _registry_names()
    grouped: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "paper_pnl": 0.0,
        "open_pnl": 0.0,
        "trade_count": 0,
        "open_position_count": 0,
        "wins_weighted": 0.0,
        "score_weighted": 0.0,
        "max_drawdown_percent": 0.0,
        "models": 0,
        "eligible_models": 0,
        "model_ids": [],
    })
    for row in rankings or []:
        strategy_id = str(row.get("strategy_id") or "unknown_strategy")
        filter_id = str(row.get("filter_id") or "unknown_filter")
        key = (strategy_id, filter_id)
        item = grouped[key]
        trades = _safe_int(row.get("total_trades"), 0)
        win_rate = _safe_float(row.get("win_rate"), 0.0)
        score = _safe_float(row.get("score"), 0.0)
        drawdown = _safe_float(row.get("max_drawdown_percent"), 0.0)
        item["paper_pnl"] += _safe_float(row.get("realized_pnl") or row.get("total_pnl"), 0.0)
        item["open_pnl"] += _safe_float(row.get("unrealized_pnl"), 0.0)
        item["trade_count"] += trades
        item["open_position_count"] += _safe_int(row.get("open_positions"), 0)
        item["wins_weighted"] += win_rate * max(trades, 1)
        item["score_weighted"] += score * max(trades, 1)
        item["max_drawdown_percent"] = min(item["max_drawdown_percent"], drawdown)
        item["models"] += 1
        item["eligible_models"] += 1 if row.get("eligible_for_real") else 0
        if row.get("model_id"):
            item["model_ids"].append(row.get("model_id"))
    rows: list[dict] = []
    for (strategy_id, filter_id), item in grouped.items():
        trades = _safe_int(item.get("trade_count"), 0)
        denominator = max(trades, item.get("models") or 1)
        win_rate = round(_safe_float(item.get("wins_weighted")) / denominator, 2) if denominator else 0.0
        score = round(_safe_float(item.get("score_weighted")) / denominator, 2) if denominator else 0.0
        pnl = round(_safe_float(item.get("paper_pnl")), 4)
        open_pnl = round(_safe_float(item.get("open_pnl")), 4)
        max_dd = round(_safe_float(item.get("max_drawdown_percent")), 4)
        decision, tone = _decision(pnl, win_rate, trades, max_dd)
        rows.append({
            "strategy_id": strategy_id,
            "filter_id": filter_id,
            "strategy": _plain_name(strategy_names.get(strategy_id) or strategy_id, "strategy"),
            "filter": _plain_name(filter_names.get(filter_id) or filter_id, "filter"),
            "combination_key": f"{strategy_id}+{filter_id}",
            "paper_pnl": pnl,
            "open_pnl": open_pnl,
            "net_pnl": round(pnl + open_pnl, 4),
            "trade_count": trades,
            "open_position_count": _safe_int(item.get("open_position_count"), 0),
            "win_rate": win_rate,
            "score": score,
            "max_drawdown_percent": max_dd,
            "decision": decision,
            "tone": tone,
            "enabled": (not active_strategies or strategy_id in active_strategies) and (not active_filters or filter_id in active_filters),
            "eligible_model_count": _safe_int(item.get("eligible_models"), 0),
            "model_count": _safe_int(item.get("models"), 0),
            "model_ids": item.get("model_ids", [])[:12],
        })
    rows.sort(key=lambda r: (r.get("enabled", False), _safe_float(r.get("net_pnl")), _safe_int(r.get("trade_count")), _safe_float(r.get("score"))), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def build_paper_combination_performance(data: dict | None, settings: dict | None = None, user: str = "default") -> dict:
    data = data if isinstance(data, dict) else {}
    data["username"] = user
    lab = ensure_paper_lab(data)
    rankings = get_model_rankings(data)
    combinations = _aggregate_from_rankings(rankings, user)
    strong = [row for row in combinations if row.get("decision") == "Güçlü"]
    watch = [row for row in combinations if row.get("decision") in {"İzle", "Daha çok izle"}]
    close = [row for row in combinations if row.get("decision") == "Kapat"]
    total_pnl = round(sum(_safe_float(row.get("net_pnl")) for row in combinations), 4)
    total_trades = sum(_safe_int(row.get("trade_count")) for row in combinations)
    best = combinations[0] if combinations else None
    weakest = None
    if combinations:
        weakest = sorted(combinations, key=lambda r: (_safe_float(r.get("net_pnl")), _safe_int(r.get("trade_count"))))[0]
    return {
        "status": "ok",
        "user": user,
        "generated_at": now_iso(),
        "source": "paper_lab_history_and_open_positions",
        "models_count": len((lab.get("models") or {})),
        "combination_count": len(combinations),
        "summary": {
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "strong_count": len(strong),
            "watch_count": len(watch),
            "close_count": len(close),
            "best_combination": best,
            "weakest_combination": weakest,
        },
        "combinations": combinations,
        "plain_explanation": "Bu ekran gerçek para kullanmadan hangi strateji ve filtre eşleşmesinin iyi çalıştığını gösterir.",
    }
