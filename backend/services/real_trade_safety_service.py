from __future__ import annotations

from datetime import datetime, timedelta

from core.storage import now_iso
from services.paper_lab_service import ensure_paper_lab, get_model_rankings
from services.paper_lab_store import get_last_paper_lab_run, get_latest_paper_lab_run_any_user
from services.bot_runtime_truth_service import build_bot_runtime_truth
from services.binance_service import load_binance_runtime_config
from services.real_trade_state_service import ensure_real_trade_state, is_unlock_valid, open_real_positions
from services.performance_service import daily_pnl_value
from services.risk_service import build_risk_snapshot, get_risk_config


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _freshness_status(value, stale_after_seconds: int) -> dict:
    stamp = _parse_iso(value)
    if not stamp:
        return {"state": "missing", "seconds": None, "fresh": False}
    age = max(0, int((datetime.now(stamp.tzinfo) - stamp).total_seconds()))
    return {"state": "fresh" if age <= stale_after_seconds else "stale", "seconds": age, "fresh": age <= stale_after_seconds}


def _runtime_username(data: dict, settings: dict) -> str:
    for source in [settings, data]:
        if not isinstance(source, dict):
            continue
        for key in ["username", "user"]:
            value = str(source.get(key) or "").strip()
            if value:
                return value
    return "admin"


def _paper_lab_store_payload(last_run: dict | None, stale_after_seconds: int = 600) -> dict | None:
    if not last_run:
        return None

    completed_at = last_run.get("completed_at")
    started_at = last_run.get("started_at")
    timestamp = completed_at or started_at
    freshness = _freshness_status(timestamp, stale_after_seconds)

    return {
        "state": "ok",
        "seconds": freshness.get("seconds"),
        "fresh": bool(freshness.get("fresh")),
        "username": last_run.get("username"),
        "started_at": started_at,
        "completed_at": completed_at,
        "run_id": last_run.get("run_id"),
        "status": last_run.get("status"),
        "source": "paper_lab_store",
    }


def _paper_lab_store_runtime_health(username: str, stale_after_seconds: int = 600) -> dict | None:
    try:
        last_run = get_last_paper_lab_run(username)
        if last_run:
            last_run = dict(last_run)
            last_run.setdefault("username", username)
            return _paper_lab_store_payload(last_run, stale_after_seconds)

        latest_run = get_latest_paper_lab_run_any_user()
        return _paper_lab_store_payload(latest_run, stale_after_seconds)
    except Exception as exc:
        return {
            "state": "missing",
            "seconds": None,
            "fresh": False,
            "source": "paper_lab_store",
            "error": str(exc)[:240],
        }


def _legacy_paper_lab_runtime_health(data: dict, lab: dict, stale_after_seconds: int = 600) -> dict:
    timestamp = (
        data.get("last_paper_lab_tick")
        or data.get("last_model_evaluation_at")
        or lab.get("last_run_at")
    )
    status = _freshness_status(timestamp, stale_after_seconds)
    status["source"] = "legacy_runtime_fields"
    status["timestamp"] = timestamp
    return status


def build_runtime_health(data: dict, settings: dict) -> dict:
    last_tick = _freshness_status(data.get("last_tick"), 180)
    last_scan = _freshness_status((data.get("last_scan") or {}).get("time"), 300)
    lab = ensure_paper_lab(data)
    runtime_username = _runtime_username(data, settings)
    bot_truth = build_bot_runtime_truth(data, settings, username=runtime_username)
    last_paper = _paper_lab_store_runtime_health(runtime_username) or _legacy_paper_lab_runtime_health(data, lab)
    running = bool(bot_truth.get("requested_running"))
    problems = []
    if running and not bot_truth.get("loop_alive") and bot_truth.get("primary_runtime_problem"):
        problems.append(bot_truth.get("primary_runtime_problem"))
    if running and not last_tick["fresh"] and "bot_tick_stale" not in problems:
        problems.append("bot_tick_stale")
    if running and not last_scan["fresh"] and "scan_stale" not in problems:
        problems.append("scan_stale")
    if running and not last_paper["fresh"]:
        problems.append("paper_lab_stale")
    if (data.get("last_scan") or {}).get("error"):
        problems.append("last_scan_error")
    return {
        "status": "ok" if not problems else "degraded",
        "requested_running": bot_truth.get("requested_running"),
        "loop_alive": bot_truth.get("loop_alive"),
        "bot_running": bot_truth.get("bot_running"),
        "engine_status": bot_truth.get("engine_status"),
        "last_tick_age_seconds": bot_truth.get("last_tick_age_seconds"),
        "last_scan_age_seconds": bot_truth.get("last_scan_age_seconds"),
        "restart_required": bot_truth.get("restart_required"),
        "primary_runtime_problem": bot_truth.get("primary_runtime_problem"),
        "checked_at": now_iso(),
        "last_tick": last_tick,
        "last_scan": last_scan,
        "last_paper_lab": last_paper,
        "problems": problems,
        "message": "Operasyonel sağlık normal." if not problems else "Stale veya hatalı veri akışı var.",
    }


def build_real_trade_safety_status(data: dict, settings: dict) -> dict:
    risk = build_risk_snapshot(data, settings)
    config = get_risk_config(settings)
    health = build_runtime_health(data, settings)
    api = settings.get("api", {}) if isinstance(settings, dict) else {}
    runtime_cfg = load_binance_runtime_config()
    real_state = ensure_real_trade_state(data)
    real_enabled = bool(runtime_cfg.real_trading_enabled and api.get("real_trade_enabled", runtime_cfg.real_trading_enabled))
    mode = str(api.get("mode") or data.get("mode") or "shadow").lower()

    blockers = []
    if not runtime_cfg.real_trading_enabled:
        blockers.append("env_real_trading_disabled")
    if runtime_cfg.real_trading_dry_run:
        blockers.append("dry_run_active")
    if not real_enabled:
        blockers.append("real_trade_default_locked")
    if not is_unlock_valid(real_state):
        blockers.append("owner_unlock_missing_or_expired")
    if mode != "real":
        blockers.append("mode_not_real")
    if data.get("emergency_lock") or real_state.get("emergency_lock"):
        blockers.append("emergency_lock_active")
    if len(open_real_positions(real_state)) >= runtime_cfg.max_open_positions:
        blockers.append("max_open_real_positions_reached")
    if risk.get("risk_status") == "blocked":
        blockers.append("daily_loss_limit_reached")
    if health.get("status") != "ok":
        blockers.append("runtime_health_degraded")
    try:
        from services.intelligence_service import build_cooldown_policy
        cooldown = build_cooldown_policy(data, settings)
        if cooldown.get("status") == "blocked":
            blockers.append("cooldown_no_trade_active")
    except Exception:
        cooldown = {"status": "unknown"}

    weekly_limit = abs(_safe_float(str((settings.get("risk") or {}).get("weekly_loss_limit", "0")).replace("USDT", "").strip(), 0))
    if weekly_limit > 0:
        closed = data.get("history", []) or []
        week_floor = datetime.now() - timedelta(days=7)
        weekly_pnl = 0.0
        for item in closed:
            ts = _parse_iso(item.get("exit_time") or item.get("entry_time"))
            if ts and ts.replace(tzinfo=None) >= week_floor:
                weekly_pnl += _safe_float(item.get("pnl"))
        if weekly_pnl <= -weekly_limit:
            blockers.append("weekly_loss_limit_reached")
    else:
        weekly_pnl = 0.0

    return {
        "status": "blocked" if blockers else "ready_locked_review",
        "real_trade_enabled": real_enabled,
        "real_order_allowed": False,
        "dry_run": runtime_cfg.real_trading_dry_run,
        "owner_unlocked": is_unlock_valid(real_state),
        "mode": mode,
        "blockers": blockers,
        "risk": risk,
        "weekly_pnl": round(weekly_pnl, 4),
        "weekly_loss_limit": weekly_limit,
        "runtime_health": health,
        "cooldown": cooldown,
        "limits": {
            "daily_loss_limit": config.get("daily_loss_limit"),
            "max_open_positions": config.get("max_open_positions"),
            "usdt_per_position": config.get("usdt_per_position"),
            "allocated_usdt": config.get("allocated_usdt"),
            "real_max_order_usdt": runtime_cfg.max_order_usdt,
            "real_daily_loss_limit_usdt": runtime_cfg.daily_loss_limit_usdt,
            "real_weekly_loss_limit_usdt": runtime_cfg.weekly_loss_limit_usdt,
            "real_max_open_positions": runtime_cfg.max_open_positions,
        },
        "message": "Gerçek emir üretimi kilitli; safety layer sadece hazırlık ve go/no-go kontrolü yapar.",
    }


def build_weighted_recommendation(data: dict, settings: dict) -> dict:
    """
    Rev25 final recommendation facade.

    Eski endpointler bu fonksiyonu kullanmaya devam eder; gerçek karar motoru
    services.recommendation_engine_service içinde tutulur. Bu sayede önceki API
    sözleşmesi bozulmadan final scoring + switch gate mantığı devreye girer.
    """
    try:
        from services.recommendation_engine_service import build_recommendation_final
        rec = build_recommendation_final(data, settings)
        action_map = {
            "SWITCH_RECOMMENDED": "SWITCH_TO_NEW_MODEL",
            "CANDIDATE_READY": "WATCH",
            "WAIT_FOR_DATA": "WATCH",
        }
        legacy_action = action_map.get(rec.get("action"), rec.get("action") or "WATCH")
        payload = dict(rec)
        payload["final_action"] = rec.get("action")
        payload["action"] = legacy_action
        payload["recommendation_engine_version"] = "rev25_final"
        return payload
    except Exception as exc:
        return {
            "action": "WATCH",
            "final_action": "WATCH",
            "reason": f"Recommendation engine güvenli moda düştü: {exc}",
            "candidate_model_id": None,
            "active_model_id": (ensure_paper_lab(data) or {}).get("active_real_model_id"),
            "score_delta": 0,
            "confidence": "locked",
            "auto_apply": False,
            "recommendation_engine_version": "fallback",
        }

def build_real_model_approval(data: dict, settings: dict) -> dict:
    safety = build_real_trade_safety_status(data, settings)
    recommendation = build_weighted_recommendation(data, settings)
    pending = data.setdefault("real_model_approval", {})
    candidate_id = recommendation.get("candidate_model_id")
    return {
        "status": "ok",
        "recommendation": recommendation,
        "safety": safety,
        "pending": pending,
        "can_request_approval": bool(candidate_id) and recommendation.get("action") == "SWITCH_TO_NEW_MODEL",
        "real_trade_locked": True,
    }
