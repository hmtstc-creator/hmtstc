import os
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import DEFAULT_USER, SHADOW_FILE
from core.storage import (
    append_log,
    get_user_container,
    load_shadow,
    load_settings,
    read_json_file,
    save_shadow,
)
from routes.auth_routes import router as auth_router
from routes.agent_routes import router as agent_router
from routes.binance_routes import router as binance_router
from routes.bot_routes import router as bot_router
from routes.dashboard_routes import router as dashboard_router
from routes.settings_routes import router as settings_router
from routes.model_routes import router as model_router
from routes.rule_routes import router as rule_router
from routes.users_routes import router as users_router
from routes.audit_routes import router as audit_router
from routes.intelligence_routes import router as intelligence_router
from routes.quality_routes import router as quality_router
from routes.real_routes import router as real_router
from routes.observability_routes import router as observability_router
from routes.summary_routes import router as summary_router
from routes.production_routes import router as production_router
from routes.reports_routes import router as reports_router
from services.bot_service import run_bot_first_tick_guarded
from services.real_trade_safety_service import build_runtime_health
from services.deploy_safety_service import build_deploy_safety_report, enforce_post_deploy_lock
from infrastructure.runtime.scheduler import RuntimeScheduler
from infrastructure.runtime.bot_runtime_registry import mark_bot_task_exception, mark_bot_task_heartbeat, mark_user_bot_requested
from infrastructure.runtime.bot_loop_control import ensure_bot_loop_running, register_runtime_scheduler
from infrastructure.runtime.bot_scan_worker import cancel_scan_worker, start_scan_worker
from infrastructure.runtime.bot_runtime_flags import ENABLE_BACKGROUND_SCAN_WORKER


runtime_scheduler = RuntimeScheduler(lambda: bot_loop())
register_runtime_scheduler(runtime_scheduler)
MIN_TICK_INTERVAL_SECONDS = 30
BOT_LOOP_ERROR_BACKOFF_SECONDS = 60


def _runtime_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _runtime_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_iso_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, _runtime_int(seconds, 0)))).isoformat()


def _runtime_time_pending(value) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > datetime.now(timezone.utc)
    except Exception:
        return False


def _apply_persisted_stop_guard(user: str, data: dict) -> bool:
    persisted = load_shadow(user)
    requested_running = bool(persisted.get("requested_running", persisted.get("bot_running", False)))
    if requested_running:
        return False
    data["requested_running"] = False
    data["bot_running"] = False
    data["engine_status"] = "stopped"
    data["tick_in_progress"] = False
    data["active_scan_worker"] = False
    data["scan_worker_deadline_at"] = None
    data["scan_cancel_requested"] = True
    data["next_tick_not_before"] = None
    data["bot_stopped_at"] = persisted.get("bot_stopped_at") or data.get("bot_stopped_at")
    data["stop_reason"] = persisted.get("stop_reason") or "user_requested_stop"
    if isinstance(persisted.get("logs"), list):
        data["logs"] = persisted["logs"]
    mark_user_bot_requested(user, False)
    return True


def runtime_scheduler_disabled_for_tests() -> bool:
    """Keep quality gates deterministic by preventing background bot-loop startup in tests."""
    return any(
        str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}
        for name in ("HMTSTC_TESTING", "HMTSTC_DISABLE_RUNTIME_SCHEDULER")
    ) or "PYTEST_CURRENT_TEST" in os.environ


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not runtime_scheduler_disabled_for_tests():
        apply_startup_real_trade_lock()
        restore_started = restore_requested_bot_loops()
        if ENABLE_BACKGROUND_SCAN_WORKER and restore_started and not runtime_scheduler.is_alive():
            runtime_scheduler.start()
    yield


app = FastAPI(title="HMTSTC Backend API", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://178.105.40.99",
        "http://178.105.40.99:8000",
        "https://hmtstc-creator.github.io",
        "https://hmtstc-creator.github.io/hmtstc",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(agent_router)
app.include_router(binance_router)
app.include_router(bot_router)
app.include_router(dashboard_router)
app.include_router(settings_router)
app.include_router(model_router)
app.include_router(rule_router)
app.include_router(users_router)
app.include_router(audit_router)
app.include_router(intelligence_router)
app.include_router(quality_router)
app.include_router(real_router)
app.include_router(observability_router)
app.include_router(summary_router)
app.include_router(production_router)
app.include_router(reports_router)


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "hmtstc-backend",
        "mode": "modular",
        "revision": 1000,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/health/ops")
def operational_health():
    data = load_shadow(DEFAULT_USER)
    settings = load_settings(DEFAULT_USER)
    runtime = build_runtime_health(data, settings)
    deploy = build_deploy_safety_report(data, settings)
    return {
        "status": "ok" if runtime.get("status") in {"ok", "healthy"} and deploy.get("status") != "blocked" else "review",
        "service": "hmtstc-backend",
        "revision": 1000,
        "runtime_health": runtime,
        "deploy_safety": deploy,
        "real_trading_locked_after_deploy_policy": True,
    }


def get_shadow_users():
    """
    Shadow dosyasındaki kullanıcıları bulur.

    Amaç:
    - Bot hangi kullanıcıda çalışıyorsa loop içinde o kullanıcının verisi işlenir.
    - Çok kullanıcılı yapı varsa kullanıcı verileri ayrı tutulur.
    - Eski tek kullanıcılı yapı varsa default kullanıcı çalışır.
    """

    raw_data = read_json_file(SHADOW_FILE, {})
    container = get_user_container(raw_data)

    users = list(container.get("users", {}).keys())

    if not users:
        return [DEFAULT_USER]

    return users


def apply_startup_real_trade_lock():
    """Rev34: every backend start/deploy keeps real trading locked until owner unlocks again."""
    for user in get_shadow_users():
        data = load_shadow(user)
        enforce_post_deploy_lock(data, reason="rev34_startup_runtime_lock")
        save_shadow(data, user)


def restore_requested_bot_loops():
    """Restore requested shadow/paper bot loops after backend restart without unlocking real trading."""
    restored_any = False
    for user in get_shadow_users():
        data = load_shadow(user)
        requested_running = bool(data.get("requested_running", data.get("bot_running", False)))

        if not requested_running:
            continue

        restored_any = True
        append_log(data, "info", f"BOT_RESTORE_CHECK user={user} requested_running=true", "bot_restore_check")

        if data.get("emergency_lock"):
            append_log(data, "warn", f"BOT_RESTORE_FAILED user={user} reason=emergency_lock", "bot_restore_failed")
            data["requested_running"] = False
            data["bot_running"] = False
            data["engine_status"] = "stopped"
            data["stop_reason"] = "startup_restore_skipped_emergency_lock"
            mark_user_bot_requested(user, False)
            save_shadow(data, user)
            continue

        if not ENABLE_BACKGROUND_SCAN_WORKER:
            now = _runtime_now_iso()
            data["requested_running"] = True
            data["bot_running"] = True
            data["engine_status"] = "running"
            data["primary_runtime_problem"] = None
            data["tick_in_progress"] = False
            data["active_scan_worker"] = False
            data["scan_worker_started_at"] = None
            data["scan_worker_deadline_at"] = None
            data["scan_worker_pid"] = None
            data["scan_cancel_requested"] = False
            data["next_tick_not_before"] = None
            data["last_tick"] = now
            data["last_updated_at"] = now
            data["last_runtime_restore_at"] = now
            data["last_runtime_restore_first_tick_ok_at"] = now
            append_log(data, "info", f"BOT_RESTORE_HEARTBEAT_ONLY_OK user={user}", "bot_restore_heartbeat_only_ok")
            mark_user_bot_requested(user, True)
            save_shadow(data, user)
            continue

        mode = str(data.get("mode") or "shadow")
        append_log(data, "info", f"BOT_RESTORE_START user={user} mode={mode}", "bot_restore_start")
        data["requested_running"] = True
        data["bot_running"] = False
        data["engine_status"] = "restoring"
        data["tick_in_progress"] = False
        data["active_scan_worker"] = False
        data["scan_worker_started_at"] = None
        data["scan_worker_deadline_at"] = None
        data["scan_cancel_requested"] = False
        data["next_tick_not_before"] = None
        data["last_runtime_restore_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        mark_user_bot_requested(user, True)
        save_shadow(data, user)
        restore_result = ensure_bot_loop_running(user, mode=mode)
        data = load_shadow(user)
        data["last_runtime_restore_result"] = restore_result
        if restore_result.get("first_tick_ok"):
            append_log(data, "info", f"BOT_RESTORE_TASK_STARTED user={user}", "bot_restore_task_started")
            data["engine_status"] = "running"
        elif restore_result.get("thread_alive"):
            append_log(data, "info", f"BOT_RESTORE_TASK_STARTED user={user}", "bot_restore_task_started")
            data["engine_status"] = "restoring"
            data["bot_running"] = False
            data["primary_runtime_problem"] = "waiting_first_tick"
        else:
            data["engine_status"] = "failed"
            data["primary_runtime_problem"] = restore_result.get("reason") or "bot_loop_task_failed_to_start"
            append_log(data, "error", f"BOT_RESTORE_FAILED user={user} reason={restore_result.get('reason') or 'bot_loop_task_failed_to_start'}", "bot_restore_failed")
        save_shadow(data, user)
    return restored_any


def bot_loop():
    if not ENABLE_BACKGROUND_SCAN_WORKER:
        return
    while True:
        try:
            users = get_shadow_users()
            requested_user_seen = False

            for user in users:
                try:
                    data = load_shadow(user)
                    requested_running = bool(data.get("requested_running", data.get("bot_running", False)))

                    if not requested_running:
                        continue

                    append_log(data, "info", f"BOT_LOOP_USER_CHECK user={user} requested_running=true", "bot_loop_user_check")

                    if data.get("emergency_lock"):
                        cancel_scan_worker(user, reason="emergency_lock_active")
                        data = load_shadow(user)
                        data["requested_running"] = False
                        data["bot_running"] = False
                        data["engine_status"] = "stopped"
                        data["tick_in_progress"] = False
                        data["next_tick_not_before"] = None
                        data["stop_reason"] = "emergency_lock_active"
                        mark_user_bot_requested(user, False)
                        save_shadow(data, user)
                        continue

                    if _apply_persisted_stop_guard(user, data):
                        cancel_scan_worker(user, reason="persisted_stop_guard")
                        continue

                    requested_user_seen = True

                    if data.get("tick_in_progress"):
                        continue

                    if _runtime_time_pending(data.get("next_tick_not_before")):
                        continue

                    first_tick_pending = not bool(data.get("last_runtime_restore_first_tick_ok_at"))
                    if not first_tick_pending:
                        data["tick_in_progress"] = False
                        data["last_tick_finished_at"] = _runtime_now_iso()
                        data["next_tick_not_before"] = _runtime_iso_after(MIN_TICK_INTERVAL_SECONDS)
                        mark_bot_task_heartbeat(user)
                        save_shadow(data, user)
                        if ENABLE_BACKGROUND_SCAN_WORKER:
                            start_scan_worker(user, limit=100)
                        continue

                    data["bot_running"] = True
                    data["tick_in_progress"] = True
                    data["last_tick_started_at"] = _runtime_now_iso()
                    data["last_tick_finished_at"] = None
                    data["next_tick_not_before"] = None
                    data["bot_loop_backoff_seconds"] = max(BOT_LOOP_ERROR_BACKOFF_SECONDS, _runtime_int(data.get("bot_loop_backoff_seconds"), BOT_LOOP_ERROR_BACKOFF_SECONDS))
                    save_shadow(data, user)

                    settings = load_settings(user)

                    # run_bot_tick fonksiyonu user parametresi almaz.
                    # Kullanıcı ayrımı load_shadow/save_shadow katmanında yapılır.
                    append_log(data, "info", f"BOT_LOOP_TICK_START user={user}", "bot_loop_tick_start")
                    tick_started_at = time.monotonic()
                    try:
                        result = run_bot_first_tick_guarded(data, settings, limit=100)
                    except Exception as tick_error:
                        if _apply_persisted_stop_guard(user, data):
                            data["last_tick_finished_at"] = _runtime_now_iso()
                            save_shadow(data, user)
                            continue
                        first_tick_timeout = not data.get("last_runtime_restore_first_tick_ok_at")
                        data["engine_status"] = "failed"
                        data["requested_running"] = False
                        data["bot_running"] = False
                        data["tick_in_progress"] = False
                        data["active_scan_worker"] = False
                        data["scan_worker_deadline_at"] = None
                        data["scan_cancel_requested"] = True
                        data["last_tick_finished_at"] = _runtime_now_iso()
                        data["next_tick_not_before"] = None
                        error_type = type(tick_error).__name__
                        error_text = str(tick_error)[:240]
                        trace_text = traceback.format_exc(limit=8)[-2000:]
                        data["primary_runtime_problem"] = "first_tick_timeout" if first_tick_timeout else f"run_bot_tick_exception:{error_type}:{error_text}"[:240]
                        data["last_runtime_error"] = error_text
                        data["last_runtime_traceback"] = trace_text
                        mark_user_bot_requested(user, False)
                        save_shadow(data, user)
                        cancel_scan_worker(user, reason=data["primary_runtime_problem"])
                        data = load_shadow(user)
                        append_log(data, "error", f"BOT_LOOP_TICK_FAILED user={user} reason={error_type}:{error_text} traceback={trace_text}", "bot_loop_tick_failed")
                        save_shadow(data, user)
                        mark_bot_task_heartbeat(user)
                        continue
                    if _apply_persisted_stop_guard(user, data):
                        data["last_tick_finished_at"] = _runtime_now_iso()
                        save_shadow(data, user)
                        continue
                    data["tick_in_progress"] = False
                    data["last_tick_finished_at"] = _runtime_now_iso()
                    if result.get("status") == "ok":
                        data["engine_status"] = "running"
                        data["primary_runtime_problem"] = None
                    tick_delay = MIN_TICK_INTERVAL_SECONDS if result.get("status") in {"ok", "skipped"} else data.get("bot_loop_backoff_seconds") or BOT_LOOP_ERROR_BACKOFF_SECONDS
                    data["next_tick_not_before"] = _runtime_iso_after(tick_delay)
                    if time.monotonic() - tick_started_at > 6:
                        data["requested_running"] = False
                        data["bot_running"] = False
                        data["engine_status"] = "failed"
                        data["tick_in_progress"] = False
                        data["active_scan_worker"] = False
                        data["scan_worker_deadline_at"] = None
                        data["scan_cancel_requested"] = True
                        data["next_tick_not_before"] = None
                        data["primary_runtime_problem"] = "first_tick_timeout"
                        data["last_runtime_error"] = "Lightweight first tick exceeded 6 seconds"
                        append_log(data, "error", f"BOT_LOOP_TICK_FAILED user={user} reason=first_tick_timeout", "bot_loop_tick_failed")
                        mark_user_bot_requested(user, False)
                        save_shadow(data, user)
                        cancel_scan_worker(user, reason="first_tick_timeout")
                        continue
                    mark_bot_task_heartbeat(user)

                    if result.get("status") == "ok" and data.get("last_runtime_restore_at") and not data.get("last_runtime_restore_first_tick_ok_at"):
                        data["last_runtime_restore_first_tick_ok_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                        data["primary_runtime_problem"] = None
                        append_log(data, "info", f"BOT_RESTORE_FIRST_TICK_OK user={user}", "bot_restore_first_tick_ok")
                    if result.get("status") == "ok":
                        append_log(data, "info", f"BOT_LOOP_TICK_OK user={user}", "bot_loop_tick_ok")

                    save_shadow(data, user)

                    if result.get("status") not in {"ok", "skipped"}:
                        append_log(data, "error", f"BOT_LOOP_TICK_FAILED user={user} reason={result.get('reason') or result.get('status')}", "bot_loop_tick_failed")
                        append_log(
                            data,
                            "warn",
                            f"Bot loop uyarı: {result.get('reason') or result.get('status')}",
                            "bot_loop_warning"
                        )
                        save_shadow(data, user)

                except Exception as user_error:
                    cancel_scan_worker(user, reason="bot_loop_user_error")
                    data = load_shadow(user)
                    error_type = type(user_error).__name__
                    error_text = str(user_error)[:240]
                    trace_text = traceback.format_exc(limit=8)[-2000:]
                    data["requested_running"] = False
                    data["bot_running"] = False
                    data["engine_status"] = "failed"
                    data["tick_in_progress"] = False
                    data["active_scan_worker"] = False
                    data["scan_worker_deadline_at"] = None
                    data["scan_cancel_requested"] = True
                    data["last_tick_finished_at"] = _runtime_now_iso()
                    data["next_tick_not_before"] = None
                    data["primary_runtime_problem"] = f"bot_loop_user_error:{error_type}:{error_text}"[:240]
                    data["last_runtime_error"] = error_text
                    data["last_runtime_traceback"] = trace_text
                    mark_user_bot_requested(user, False)
                    mark_bot_task_heartbeat(user)

                    append_log(
                        data,
                        "error",
                        f"Kullanıcı bot loop hatası: {user} - {error_type}:{error_text} traceback={trace_text}",
                        "bot_loop_user_error"
                    )

                    save_shadow(data, user)

            if not requested_user_seen:
                return

        except Exception as error:
            mark_bot_task_exception(error)
            try:
                data = load_shadow(DEFAULT_USER)

                append_log(
                    data,
                    "error",
                    f"Genel bot loop hatası: {str(error)}",
                    "bot_loop_error"
                )

                save_shadow(data, DEFAULT_USER)

            except Exception:
                pass

        time.sleep(30)
