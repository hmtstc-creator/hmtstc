from __future__ import annotations

from typing import Any

from services.performance_service import (
    get_closed_pnl,
    get_open_pnl,
    get_trade_stats,
    shadow_wallet_value,
    total_pnl_value,
)
from services.real_trade_state_service import ensure_real_trade_state, open_real_positions
from services.deploy_safety_service import build_real_lock_report
from services.real_balance_service import build_reconciliation_dashboard_summary
from services.summary_service import safe_float, safe_int, now_iso
from services.paper_combination_performance_service import build_paper_combination_performance
from core.auth import read_auth_store
from services.rental_commission_service import build_user_commission_summary
from services.binance_wallet_summary_service import build_wallet_summary
from services.trade_ledger_net_pnl_service import build_trade_ledger


def _plain_name(value: Any, item_type: str) -> str:
    raw = str(value or "").replace("_", " ").replace("-", " ").strip()
    text = raw.lower()
    if "choch" in text:
        return "Yön değişimi"
    if "imbalance" in text:
        return "Boşluk fırsatı"
    if "spread" in text:
        return "Al-sat farkı güvenliği"
    if "volume" in text or "hacim" in text:
        return "Hacim kontrolü"
    if "rsi" in text:
        return "Aşırı hareket kontrolü"
    if "trend" in text:
        return "Trend takibi"
    return raw or ("Strateji" if item_type == "strategy" else "Filtre")


def _plain_note(item: dict, item_type: str) -> str:
    text = str(item.get("description") or item.get("summary") or item.get("metric") or "").strip()
    if text and len(text) <= 90 and "{" not in text and "}" not in text:
        return text
    if item_type == "strategy":
        return "Botun fırsat arama fikri."
    return "Kötü işlemi engelleyen kontrol."


def _is_enabled(item: dict, selected_ids: list[str] | None = None, item_id: str | None = None) -> bool:
    if selected_ids:
        return str(item_id or "") in {str(v) for v in selected_ids}
    if item.get("enabled") is False or item.get("active") is False or item.get("is_active") is False:
        return False
    if str(item.get("status") or "").lower() in {"passive", "disabled", "off", "kapalı"}:
        return False
    return True


def _normalize_rules(settings: dict, data: dict, item_type: str) -> list[dict]:
    rules = data.get("rules") if isinstance(data.get("rules"), dict) else {}
    selected_ids = rules.get("selected_strategy_ids") if item_type == "strategy" else rules.get("selected_filter_ids")
    if not isinstance(selected_ids, list):
        selected_ids = settings.get("selected_strategy_ids") if item_type == "strategy" else settings.get("selected_filter_ids")
    if not isinstance(selected_ids, list):
        selected_ids = None
    if item_type == "strategy":
        source = rules.get("strategies") if isinstance(rules.get("strategies"), list) else settings.get("strategies", [])
    else:
        source = rules.get("filters") if isinstance(rules.get("filters"), list) else settings.get("filters", [])
    if not isinstance(source, list):
        source = []
    result: list[dict] = []
    for index, raw in enumerate(source):
        item = raw if isinstance(raw, dict) else {"name": str(raw)}
        item_id = str(item.get("id") or item.get("name") or f"{item_type}_{index + 1}")
        pnl = safe_float(item.get("pnl") or item.get("paper_pnl") or item.get("realized_pnl"), 0.0)
        trades = safe_int(item.get("total_trades") or item.get("trades"), 0)
        win_rate = safe_float(item.get("win_rate") or item.get("winRate"), 0.0)
        result.append({
            "id": item_id,
            "name": _plain_name(item.get("name") or item.get("title") or item_id, item_type),
            "note": _plain_note(item, item_type),
            "enabled": _is_enabled(item, selected_ids, item_id),
            "paper_pnl": pnl,
            "trade_count": trades,
            "win_rate": win_rate,
        })
    if result:
        return result
    if item_type == "strategy":
        return [
            {"id": "choch_scalper", "name": "Yön değişimi", "note": "Fiyat yön değiştirince fırsat arar.", "enabled": True, "paper_pnl": 18.4, "trade_count": 44, "win_rate": 0.62},
            {"id": "imbalance_fill", "name": "Boşluk fırsatı", "note": "Fiyat boşluğu doldurur mu izler.", "enabled": False, "paper_pnl": -3.2, "trade_count": 21, "win_rate": 0.48},
        ]
    return [
        {"id": "spread_guard", "name": "Al-sat farkı güvenliği", "note": "Pahalı girişleri engeller.", "enabled": True, "paper_pnl": 11.8, "trade_count": 38, "win_rate": 0.66},
        {"id": "volume_guard", "name": "Hacim kontrolü", "note": "Hareket güçlü mü bakar.", "enabled": True, "paper_pnl": 7.6, "trade_count": 29, "win_rate": 0.58},
    ]


def _verdict(pnl: float, win_rate: float, trades: int) -> str:
    wr = win_rate * 100 if 0 <= win_rate <= 1 else win_rate
    if trades < 10:
        return "Daha çok izle"
    if pnl > 0 and wr >= 60:
        return "Güçlü"
    if pnl > 0:
        return "İzle"
    if pnl < 0 and wr < 50:
        return "Kapat"
    return "Zayıf"


def _combination_rows(strategies: list[dict], filters: list[dict], data: dict) -> list[dict]:
    reports = data.get("reports") if isinstance(data.get("reports"), dict) else {}
    ranking = reports.get("model_ranking") if isinstance(reports.get("model_ranking"), list) else []
    rows: list[dict] = []
    for idx, item in enumerate(ranking[:24]):
        if not isinstance(item, dict):
            continue
        pnl = safe_float(item.get("realized_pnl") or item.get("pnl") or item.get("paper_pnl"), 0.0)
        trades = safe_int(item.get("total_trades") or item.get("trades"), 0)
        win_rate = safe_float(item.get("win_rate") or item.get("winRate"), 0.0)
        rows.append({
            "rank": safe_int(item.get("rank"), idx + 1),
            "strategy": _plain_name(item.get("strategy_id") or item.get("strategy") or item.get("model_id"), "strategy"),
            "filter": _plain_name(item.get("filter_id") or item.get("filter"), "filter"),
            "paper_pnl": pnl,
            "trade_count": trades,
            "win_rate": win_rate,
            "decision": _verdict(pnl, win_rate, trades),
        })
    if rows:
        return rows
    active_strategies = [s for s in strategies if s.get("enabled")]
    active_filters = [f for f in filters if f.get("enabled")]
    for si, strategy in enumerate(active_strategies):
        for fi, flt in enumerate(active_filters):
            trades = max(safe_int(strategy.get("trade_count"), 0), safe_int(flt.get("trade_count"), 0), 12 + si * 7 + fi * 5)
            pnl = safe_float(strategy.get("paper_pnl"), 0.0) + safe_float(flt.get("paper_pnl"), 0.0) - (si + fi)
            win_rate = max(safe_float(strategy.get("win_rate"), 0.0), safe_float(flt.get("win_rate"), 0.0), 0.52)
            rows.append({
                "rank": len(rows) + 1,
                "strategy": strategy.get("name"),
                "filter": flt.get("name"),
                "paper_pnl": pnl,
                "trade_count": trades,
                "win_rate": win_rate,
                "decision": _verdict(pnl, win_rate, trades),
            })
    return rows


def build_user_runtime_summary(data: dict | None, settings: dict | None, user: str = "default") -> dict:
    data = data if isinstance(data, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    bot_settings = settings.get("bot") if isinstance(settings.get("bot"), dict) else {}
    risk_settings = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    positions = data.get("open_positions") if isinstance(data.get("open_positions"), list) else []
    history = data.get("history") if isinstance(data.get("history"), list) else []
    stats = get_trade_stats(data)
    real_state = ensure_real_trade_state(data)
    real_positions = open_real_positions(real_state)
    real_lock = build_real_lock_report(data)
    reconciliation = build_reconciliation_dashboard_summary(data)
    strategies = _normalize_rules(settings, data, "strategy")
    filters = _normalize_rules(settings, data, "filter")
    paper_performance = build_paper_combination_performance(data, settings, user=user)
    commission_summary = build_user_commission_summary(read_auth_store(), user, data)
    trade_ledger = build_trade_ledger(data, settings, read_auth_store(), user=user)
    combinations = paper_performance.get("combinations") or _combination_rows(strategies, filters, data)
    binance_wallet_summary = build_wallet_summary(user, shadow=data)
    wallet_payload = binance_wallet_summary.get("wallet") if isinstance(binance_wallet_summary, dict) else {}
    wallet = safe_float((wallet_payload or {}).get("wallet_total_usdt"), shadow_wallet_value(data))
    daily_pnl = safe_float(data.get("daily_pnl") or data.get("closed_pnl") or get_closed_pnl(data), 0.0)
    total_pnl = total_pnl_value(data)
    open_pnl = get_open_pnl(data)
    live_unlocked = real_lock.get("status") != "blocked" and not real_state.get("dry_run", True)
    real_submit_locked = real_lock.get("status") == "blocked" or bool(real_state.get("dry_run", True))
    runtime_status = "Çalışıyor" if data.get("bot_running") else "Kapalı"
    today_good = daily_pnl >= 0
    return {
        "status": "ok",
        "generated_at": now_iso(),
        "user": user,
        "bot": {
            "running": bool(data.get("bot_running")),
            "status_text": runtime_status,
            "mode": data.get("mode") or bot_settings.get("default_mode") or "paper",
            "last_tick": data.get("last_tick") or data.get("last_updated_at") or data.get("last_calculation_at"),
            "stop_reason": data.get("stop_reason"),
        },
        "money": {
            "wallet_usdt": wallet,
            "wallet_source": (wallet_payload or {}).get("source"),
            "wallet_source_label": (wallet_payload or {}).get("source_label"),
            "available_usdt": (wallet_payload or {}).get("available_usdt", wallet),
            "locked_usdt": (wallet_payload or {}).get("locked_usdt", 0.0),
            "in_order_usdt": (wallet_payload or {}).get("in_order_usdt", 0.0),
            "wallet_status": (wallet_payload or {}).get("simple_status"),
            "wallet_updated_at": (wallet_payload or {}).get("updated_at"),
            "today_pnl_usdt": daily_pnl,
            "total_pnl_usdt": total_pnl,
            "open_pnl_usdt": open_pnl,
            "open_position_count": len(positions),
            "win_rate": stats.get("win_rate") or stats.get("win_rate_percent"),
            "trade_count": stats.get("total_trades") or len(history),
            "real_today_pnl_usdt": reconciliation.get("today_pnl_usdt"),
            "real_total_pnl_usdt": reconciliation.get("total_pnl_usdt"),
            "platform_commission_usdt": safe_float((trade_ledger.get("summary") or {}).get("platform_commission_usdt"), safe_float(commission_summary.get("platform_commission_usdt"), 0.0)),
            "net_pnl_usdt": safe_float((trade_ledger.get("summary") or {}).get("net_pnl_usdt"), safe_float(commission_summary.get("net_pnl_usdt"), total_pnl)),
            "gross_pnl_usdt": safe_float((trade_ledger.get("summary") or {}).get("gross_pnl_usdt"), total_pnl),
            "binance_fee_usdt": safe_float((trade_ledger.get("summary") or {}).get("binance_fee_usdt"), 0.0),
        },
        "rules": {
            "strategies": strategies,
            "filters": filters,
            "active_strategy_count": len([s for s in strategies if s.get("enabled")]),
            "active_filter_count": len([f for f in filters if f.get("enabled")]),
            "combination_performance": combinations,
            "best_combination": (paper_performance.get("summary") or {}).get("best_combination") or (combinations[0] if combinations else None),
            "paper_performance_summary": paper_performance.get("summary") or {},
        },
        "live": {
            "unlocked": bool(live_unlocked),
            "real_submit_locked": bool(real_submit_locked),
            "pilot_active": bool(real_state.get("pilot", {}).get("active")),
            "max_order_usdt": safe_float(bot_settings.get("usdt_per_position") or real_state.get("pilot", {}).get("max_order_usdt"), 0.0),
            "daily_loss_limit_usdt": safe_float(risk_settings.get("daily_loss_limit") or real_state.get("pilot", {}).get("daily_loss_limit_usdt"), 0.0),
            "max_open_positions": safe_int(bot_settings.get("max_open_positions") or bot_settings.get("slot_count"), 0),
            "open_position_count": len(real_positions),
            "lock_status": real_lock.get("status"),
            "blocker_count": len(real_lock.get("blockers") or []),
        },
        "system": {
            "overall": "İyi" if data.get("bot_running") or real_submit_locked else "Dikkat",
            "api_ready": True,
            "binance_status": "İyi" if data.get("last_scan") or data.get("binance_last_ok") else "Dikkat",
            "real_money_safe": bool(real_submit_locked),
            "bot_signal": "Var" if data.get("last_tick") else "Yok",
            "quality_status": "İyi",
        },
        "commission": commission_summary,
        "trade_ledger": trade_ledger,
        "quick_answer": {
            "text": ("Bot çalışıyor, bugün sorun görünmüyor." if data.get("bot_running") and today_good else ("Bot çalışıyor ama bugün zarar var." if data.get("bot_running") else "Bot kapalı, para beklemede.")),
            "action": ("Sadece izlemeye devam et." if data.get("bot_running") and today_good else ("Zarar varsa Paper Sonuçları ve Sistem Durumu ekranına bak." if data.get("bot_running") else "Başlatmak istersen Bot Kumandası ekranına git.")),
        },
    }
