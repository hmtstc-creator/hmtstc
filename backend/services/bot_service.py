import time
from uuid import uuid4
from core.config import DEFAULT_USER
from core.storage import append_log, now_iso, sync_last_scan_state
from services.analysis_service import build_candidate_handoff, scan_market
from services.performance_service import (
    build_dashboard_summary,
    record_performance_point,
)
from services.position_service import (
    close_all_shadow_positions,
    create_shadow_position,
    update_open_positions,
)
from services.paper_lab_service import ensure_paper_lab, run_paper_lab_tick
from services.model_scoring_service import evaluate_strategy_candidates
from services.karabasan_final_decision_service import build_karabasan_final_decision
from services.coin_universe_final_service import append_scan_history
from services.risk_service import (
    can_open_new_position,
    get_position_size,
    is_daily_loss_limit_reached,
)


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if parsed == parsed and parsed not in {float("inf"), float("-inf")} else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback



def _apply_active_real_model(candidate: dict, data: dict) -> dict:
    lab = ensure_paper_lab(data)
    model_id = lab.get("active_real_model_id")
    model_state = lab.get("models", {}).get(model_id, {})

    candidate["mode"] = "shadow"
    candidate["model_id"] = model_id
    candidate["filter_id"] = model_state.get("filter_id")
    candidate["strategy_id"] = model_state.get("strategy_id")

    return candidate

def start_bot(data: dict, mode: str = "paper") -> dict:
    now = now_iso()

    normalized_mode = str(mode or "paper").strip().lower()
    if normalized_mode not in {"paper", "shadow"}:
        raise ValueError("Bot start mode sadece paper veya shadow olabilir. Canlı emir akışı /api/real altında ayrı safety kapılarıyla çalışır.")

    already_running = bool(
        data.get("requested_running")
        and data.get("bot_running")
        and str(data.get("engine_status") or "") == "running"
    )

    data["bot_running"] = True
    data["requested_running"] = True
    data["mode"] = normalized_mode
    data["engine_status"] = "running"
    data["primary_runtime_problem"] = None
    data["tick_in_progress"] = False
    data["active_scan_worker"] = False
    data["scan_worker_started_at"] = None
    data["scan_worker_deadline_at"] = None
    data["scan_worker_pid"] = None
    data["scan_cancel_requested"] = False
    data["last_tick_started_at"] = now
    data["last_tick_finished_at"] = now
    data["next_tick_not_before"] = None
    data["bot_loop_backoff_seconds"] = max(60, _safe_int(data.get("bot_loop_backoff_seconds"), 60))

    data["bot_started_at"] = data.get("bot_started_at") if already_running else now
    data["bot_stopped_at"] = None
    data["last_tick"] = now
    data["last_runtime_restore_at"] = now
    data["last_runtime_restore_first_tick_ok_at"] = now
    data["last_runtime_error"] = None
    data["last_updated_at"] = now
    data["last_calculation_at"] = now

    data["stop_reason"] = None
    append_log(
        data,
        "info",
        f"BOT_START_HEARTBEAT_ONLY_OK mode={normalized_mode} already_running={str(already_running).lower()}",
        "bot_start_heartbeat_only_ok"
    )

    return data


def stop_bot(data: dict, reason: str = "manual_stop") -> dict:
    now = now_iso()

    data["bot_running"] = False
    data["requested_running"] = False
    data["engine_status"] = "stopped"
    data["primary_runtime_problem"] = None
    data["tick_in_progress"] = False
    data["active_scan_worker"] = False
    data["scan_worker_deadline_at"] = None
    data["scan_worker_pid"] = None
    data["scan_cancel_requested"] = True
    data["next_tick_not_before"] = None

    data["bot_stopped_at"] = now
    data["last_updated_at"] = now
    data["last_calculation_at"] = now
    data["stop_reason"] = reason

    append_log(
        data,
        "info",
        f"BOT_STOP_REQUESTED reason={reason}",
        "bot_stop_requested"
    )

    record_performance_point(data)

    return data


def emergency_stop_bot(data: dict, action: str = "stop_new_buys") -> dict:
    now = now_iso()

    data["bot_running"] = False
    data["requested_running"] = False
    data["engine_status"] = "emergency_stopped"
    data["tick_in_progress"] = False
    data["active_scan_worker"] = False
    data["scan_worker_deadline_at"] = None
    data["scan_cancel_requested"] = True
    data["next_tick_not_before"] = None

    data["bot_stopped_at"] = now
    data["last_updated_at"] = now
    data["last_calculation_at"] = now
    data["stop_reason"] = f"emergency_stop:{action}"

    append_log(
        data,
        "warn",
        f"Acil durdur uygulandı. Aksiyon: {action}",
        "emergency_stop"
    )

    if action == "close_all_shadow":
        close_all_shadow_positions(data, reason="Emergency Stop")

    record_performance_point(data)

    return data


def reset_bot_state() -> dict:
    now = now_iso()

    return {
        "bot_running": False,
        "requested_running": False,
        "mode": "shadow",
        "engine_status": "reset",
        "tick_in_progress": False,
        "active_scan_worker": False,
        "scan_worker_started_at": None,
        "scan_worker_deadline_at": None,
        "scan_cancel_requested": True,
        "scan_worker_generation": 0,
        "last_tick_started_at": None,
        "last_tick_finished_at": None,
        "next_tick_not_before": None,
        "bot_loop_backoff_seconds": 60,

        "bot_started_at": None,
        "bot_stopped_at": now,
        "last_tick": None,
        "last_updated_at": now,
        "last_calculation_at": now,
        "stop_reason": "reset",

        "open_positions": [],
        "history": [],
        "logs": [
            {
                "level": "warn",
                "event": "reset",
                "time": now,
                "message": "Bot verileri sıfırlandı."
            }
        ],
        "performance_points": [],
        "last_scan": {
            "status": "idle",
            "live": False,
            "source": "binance",
            "time": None,
            "scanned": 0,
            "candidates_count": 0,
            "candidates": [],
            "scan_rows": [],
            "error": None
        },
        "paper_lab": {}
    }


def _cancelled(cancel_requested=None, deadline: float | None = None) -> bool:
    return bool(
        (callable(cancel_requested) and cancel_requested())
        or (deadline is not None and time.monotonic() >= deadline)
    )


def run_bot_first_tick_guarded(data: dict, settings: dict, limit: int = 100) -> dict:
    """Complete startup with a pure heartbeat tick; real market scan runs separately."""
    try:
        if not data.get("requested_running", data.get("bot_running", False)):
            return {"status": "skipped", "reason": "bot_not_requested"}

        now = now_iso()
        data["bot_running"] = True
        data["last_tick"] = now
        data["last_updated_at"] = now
        data["last_calculation_at"] = now
        data["engine_status"] = "running"
        data["primary_runtime_problem"] = None

        existing_scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
        if not existing_scan:
            existing_scan = {
                "status": "startup_pending_scan",
                "time": now,
                "live": False,
                "scanned": 0,
                "candidates_count": 0,
                "candidates": [],
                "scan_rows": [],
                "error": None,
            }
            data["last_scan"] = existing_scan
            data["last_scan_time"] = now
        elif not existing_scan.get("time"):
            existing_scan["time"] = now
            data["last_scan"] = existing_scan
            data["last_scan_time"] = now

        append_log(data, "info", "BOT_LIGHTWEIGHT_FIRST_TICK_OK", "bot_lightweight_first_tick_ok")
        return {
            "status": "ok",
            "mode": "heartbeat_first_tick",
            "last_tick": now,
            "last_scan": data.get("last_scan"),
        }
    except Exception as exc:
        now = now_iso()
        data["bot_running"] = False
        data["engine_status"] = "failed"
        data["primary_runtime_problem"] = "first_tick_exception"
        data["last_error"] = str(exc)
        append_log(data, "error", f"BOT_LIGHTWEIGHT_FIRST_TICK_ERROR {exc}", "bot_lightweight_first_tick_error")
        return {"status": "error", "reason": "first_tick_exception", "error": str(exc)}
    finally:
        data["tick_in_progress"] = False
        data["last_tick_finished_at"] = now_iso()


def run_bot_tick_guarded(data: dict, settings: dict, limit: int = 1000, *, cancel_requested=None, deadline: float | None = None) -> dict:
    try:
        return run_bot_tick(data, settings, limit=limit, cancel_requested=cancel_requested, deadline=deadline)
    finally:
        data["tick_in_progress"] = False
        data["last_tick_finished_at"] = now_iso()


def run_bot_tick(data: dict, settings: dict, limit: int = 1000, *, cancel_requested=None, deadline: float | None = None) -> dict:
    if not data.get("bot_running", False):
        return {
            "status": "skipped",
            "reason": "bot_not_running"
        }

    now = now_iso()
    tick_started_monotonic = time.monotonic()
    tick_id = str(uuid4())
    tick_trace = {
        "tick_id": tick_id,
        "start_time": now,
        "scan_ran": False,
        "paper_lab_ran": False,
        "recommendation_ran": False,
        "error": None,
        "coins_processed": 0,
        "models_updated": 0,
    }

    if _cancelled(cancel_requested, deadline):
        return {"status": "cancelled", "reason": "scan_worker_cancelled"}

    update_open_positions(data, settings, cancel_requested=cancel_requested, deadline=deadline)

    daily_loss_check = is_daily_loss_limit_reached(data, settings)

    if not daily_loss_check["passed"]:
        data["bot_running"] = False
        data["requested_running"] = False
        data["engine_status"] = "stopped"
        data["tick_in_progress"] = False
        data["next_tick_not_before"] = None
        data["bot_stopped_at"] = now
        data["last_updated_at"] = now
        data["last_calculation_at"] = now
        data["stop_reason"] = "daily_loss_limit"

        append_log(
            data,
            "warn",
            (
                "Günlük zarar limiti aşıldı. "
                f"Bot durduruldu. PnL: {daily_loss_check['daily_pnl']}"
            ),
            "daily_loss_limit"
        )

        tick_trace.update({"end_time": now_iso(), "duration_ms": round((time.monotonic() - tick_started_monotonic) * 1000, 2), "status": "stopped", "error": "daily_loss_limit", "next_tick_estimate_seconds": None})
        data.setdefault("bot_loop_traces", []).append(tick_trace)
        data["bot_loop_traces"] = data["bot_loop_traces"][-250:]
        record_performance_point(data)

        return {
            "status": "stopped",
            "reason": "daily_loss_limit",
            "daily_pnl": daily_loss_check["daily_pnl"],
            "daily_loss_limit": daily_loss_check["daily_loss_limit"]
        }

    if _cancelled(cancel_requested, deadline):
        return {"status": "cancelled", "reason": "scan_worker_cancelled"}

    scan = scan_market(
        settings,
        limit=limit,
        deep_analysis=True,
        timeout_seconds=20,
        deep_analysis_timeout_seconds=15,
        cancel_requested=cancel_requested,
        deadline=deadline,
    )
    tick_trace["scan_ran"] = True
    tick_trace["coins_processed"] = int(scan.get("scanned") or 0)

    sync_last_scan_state(data, scan)
    append_scan_history(data, scan)

    if scan.get("status") != "ok" or not scan.get("live"):
        data["engine_status"] = "scan_error"
        data["last_tick"] = now
        data["last_updated_at"] = now
        data["last_calculation_at"] = now

        append_log(
            data,
            "error",
            f"Canlı tarama başarısız. Sebep: {scan.get('error')}",
            "scan_error"
        )

        tick_trace.update({"end_time": now_iso(), "duration_ms": round((time.monotonic() - tick_started_monotonic) * 1000, 2), "status": "scan_error", "error": scan.get("error", "live_scan_failed"), "next_tick_estimate_seconds": 30})
        data.setdefault("bot_loop_traces", []).append(tick_trace)
        data["bot_loop_traces"] = data["bot_loop_traces"][-250:]
        record_performance_point(data)

        return {
            "status": "scan_error",
            "reason": scan.get("error", "live_scan_failed"),
            "last_scan": scan
        }

    if _cancelled(cancel_requested, deadline):
        return {"status": "cancelled", "reason": "scan_worker_cancelled"}

    paper_lab_result = run_paper_lab_tick(
        data,
        scan,
        settings,
        cancel_requested=cancel_requested,
        deadline=deadline,
    )
    tick_trace["paper_lab_ran"] = True
    tick_trace["models_updated"] = len(((data.get("paper_lab") or {}).get("models") or {}))

    handoff = scan.get("candidate_handoff") or build_candidate_handoff(scan)
    username = str(data.get("_runtime_username") or DEFAULT_USER)
    strategy_runtime = evaluate_strategy_candidates(username, handoff)
    scan["strategy_runtime"] = strategy_runtime
    sync_last_scan_state(data, scan)
    candidates = strategy_runtime.get("approved_candidates", [])
    if strategy_runtime.get("reason") == "no_active_strategy":
        append_log(data, "warn", "Aktif strateji yok; yeni işlem açılmadı.", "no_active_strategy")
    open_positions = data.setdefault("open_positions", [])

    opened_position = None

    for candidate in candidates:
        if _cancelled(cancel_requested, deadline):
            return {"status": "cancelled", "reason": "scan_worker_cancelled"}
        symbol = candidate.get("symbol")
        price = _safe_float(candidate.get("price"), 0.0)

        if not symbol or price <= 0:
            append_log(
                data,
                "warn",
                f"Aday geçersiz olduğu için atlandı: {symbol or '-'}",
                "candidate_rejected"
            )
            continue

        karabasan_input = {**candidate, "candidate": candidate, "strategy_output": candidate.get("strategy_output") or {}}
        karabasan_decision = build_karabasan_final_decision(data, settings, karabasan_input)
        candidate["karabasan_decision"] = karabasan_decision
        scan["karabasan_runtime"] = karabasan_decision
        if not karabasan_decision.get("approved"):
            append_log(
                data,
                "warn",
                f"Karabasan final gate reddetti: {symbol} - {karabasan_decision.get('explanation')}",
                "karabasan_final_rejected",
            )
            continue

        risk_check = can_open_new_position(data, settings, symbol)

        if not risk_check.get("passed"):
            candidate["risk_rejected"] = True
            candidate["risk_rejection_reason"] = risk_check.get("reason")
            append_log(
                data,
                "warn",
                (
                    f"Aday risk nedeniyle reddedildi: {symbol} - "
                    f"Sebep: {risk_check.get('reason')}"
                ),
                "risk_rejected"
            )
            continue

        usdt_size = _safe_float(get_position_size(data, settings, candidate), 0.0)

        if usdt_size <= 0:
            append_log(
                data,
                "warn",
                f"Aday geçersiz pozisyon büyüklüğü nedeniyle reddedildi: {symbol}",
                "risk_rejected"
            )
            continue

        candidate = _apply_active_real_model(candidate, data)

        opened_position = create_shadow_position(
            candidate,
            settings,
            usdt_size
        )

        open_positions.append(opened_position)

        append_log(
            data,
            "info",
            (
                f"Shadow pozisyon açıldı: {symbol} "
                f"Strateji: {opened_position.get('strategy')} "
                f"USDT: {usdt_size}"
            ),
            "position_opened"
        )

        break

    sync_last_scan_state(data, scan)
    data["engine_status"] = "running"
    data["last_tick"] = now
    data["last_updated_at"] = now
    data["last_calculation_at"] = now

    append_log(
        data,
        "info",
        (
            f"Shadow tick tamamlandı. "
            f"Taranan: {scan.get('scanned', 0)} "
            f"Aday: {len(candidates)} "
            f"Yeni pozisyon: {opened_position.get('symbol') if opened_position else 'yok'}"
        ),
        "bot_tick"
    )

    tick_trace.update({
        "end_time": now_iso(),
        "duration_ms": round((time.monotonic() - tick_started_monotonic) * 1000, 2),
        "status": "ok",
        "opened_symbol": opened_position.get("symbol") if opened_position else None,
        "stale_data_warning": False,
        "next_tick_estimate_seconds": 30,
    })
    data.setdefault("bot_loop_traces", []).append(tick_trace)
    data["bot_loop_traces"] = data["bot_loop_traces"][-250:]

    record_performance_point(data)

    return {
        "status": "ok",
        "mode": "shadow",
        "scanned": scan.get("scanned", 0),
        "candidates_count": len(candidates),
        "opened": opened_position,
        "open_positions_count": len(open_positions),
        "dashboard": build_dashboard_summary(data, settings),
        "last_scan": scan,
        "paper_lab": paper_lab_result
    }
