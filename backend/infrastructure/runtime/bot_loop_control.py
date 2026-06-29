from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from core.storage import append_log, load_shadow, save_shadow
from infrastructure.runtime.bot_runtime_registry import is_bot_task_alive, mark_user_bot_requested
from infrastructure.runtime.bot_scan_worker import cancel_scan_worker
from infrastructure.runtime.bot_runtime_flags import ENABLE_BACKGROUND_SCAN_WORKER


_RUNTIME_SCHEDULER: Any = None
RESTORE_FIRST_TICK_WAIT_SECONDS = 0.25
RESTORE_FIRST_TICK_TIMEOUT_SECONDS = 25


def register_runtime_scheduler(scheduler: Any) -> None:
    global _RUNTIME_SCHEDULER
    _RUNTIME_SCHEDULER = scheduler


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _after(value: Any, floor: Any) -> bool:
    stamp = _parse_iso(value)
    floor_stamp = _parse_iso(floor)
    if not stamp or not floor_stamp:
        return False
    if stamp.tzinfo is None and floor_stamp.tzinfo is not None:
        floor_stamp = floor_stamp.replace(tzinfo=None)
    if stamp.tzinfo is not None and floor_stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=None)
    return stamp >= floor_stamp


def restore_first_tick_ok(data: dict[str, Any], restore_started_at: str) -> bool:
    if data.get("last_runtime_restore_first_tick_ok_at"):
        return True
    return _after(data.get("last_tick"), restore_started_at)


def _restore_result(started: bool, already_running: bool, thread_alive: bool, first_tick_ok: bool, reason: str, mode: str, restore_started_at: str) -> dict[str, Any]:
    return {
        "started": bool(started),
        "already_running": bool(already_running),
        "thread_alive": bool(thread_alive),
        "first_tick_ok": bool(first_tick_ok),
        "loop_alive": bool(thread_alive and first_tick_ok),
        "reason": "" if thread_alive and first_tick_ok else reason,
        "mode": mode,
        "restore_started_at": restore_started_at,
        "checked_at": _now_iso(),
        "restore_first_tick_wait_seconds": RESTORE_FIRST_TICK_WAIT_SECONDS,
        "restore_first_tick_timeout_seconds": RESTORE_FIRST_TICK_TIMEOUT_SECONDS,
    }


def _monitor_restore_first_tick(username: str, mode: str, restore_started_at: str) -> None:
    deadline = time.monotonic() + RESTORE_FIRST_TICK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        data = load_shadow(username)
        if not data.get("requested_running", data.get("bot_running", False)):
            return
        thread_alive = is_bot_task_alive(username)
        if restore_first_tick_ok(data, restore_started_at):
            data["engine_status"] = "running"
            data["bot_running"] = True
            data["primary_runtime_problem"] = None
            data["last_runtime_restore_first_tick_ok_at"] = data.get("last_runtime_restore_first_tick_ok_at") or _now_iso()
            data["last_runtime_restore_result"] = _restore_result(
                started=False,
                already_running=True,
                thread_alive=thread_alive,
                first_tick_ok=True,
                reason="",
                mode=mode,
                restore_started_at=restore_started_at,
            )
            append_log(data, "info", f"BOT_START_FIRST_TICK_OK user={username}", "bot_start_first_tick_ok")
            save_shadow(data, username)
            return
        time.sleep(2)

    data = load_shadow(username)
    if data.get("requested_running", data.get("bot_running", False)) and not restore_first_tick_ok(data, restore_started_at):
        data["requested_running"] = False
        data["engine_status"] = "failed"
        data["bot_running"] = False
        data["tick_in_progress"] = False
        data["active_scan_worker"] = False
        data["scan_worker_deadline_at"] = None
        data["scan_cancel_requested"] = True
        data["next_tick_not_before"] = None
        data["primary_runtime_problem"] = "first_tick_timeout"
        data["last_runtime_error"] = "First bot tick did not complete within 25 seconds."
        data["last_runtime_restore_result"] = _restore_result(
            started=False,
            already_running=True,
            thread_alive=is_bot_task_alive(username),
            first_tick_ok=False,
            reason="first_tick_timeout",
            mode=mode,
            restore_started_at=restore_started_at,
        )
        mark_user_bot_requested(username, False)
        save_shadow(data, username)
        cancel_scan_worker(username, reason="first_tick_timeout")
        data = load_shadow(username)
        append_log(data, "error", f"BOT_RESTORE_FAILED user={username} reason=first_tick_timeout", "bot_restore_failed")
        append_log(data, "error", f"BOT_START_FAILED user={username} reason=first_tick_timeout", "bot_start_failed")
        save_shadow(data, username)


def ensure_bot_loop_running(username: str, mode: str = "shadow", wait_seconds: float = RESTORE_FIRST_TICK_WAIT_SECONDS) -> dict[str, Any]:
    restore_started_at = _now_iso()
    data = load_shadow(username)
    restore_started_at = str(data.get("last_runtime_restore_at") or restore_started_at)

    if not bool(data.get("requested_running", data.get("bot_running", False))):
        return {
            "started": False,
            "already_running": False,
            "thread_alive": False,
            "first_tick_ok": False,
            "loop_alive": False,
            "reason": "bot_not_requested",
            "mode": mode,
            "restore_started_at": restore_started_at,
            "checked_at": _now_iso(),
        }

    if not ENABLE_BACKGROUND_SCAN_WORKER:
        return {
            "started": False,
            "already_running": False,
            "thread_alive": False,
            "first_tick_ok": bool(data.get("last_tick")),
            "loop_alive": False,
            "reason": "background_scan_worker_disabled",
            "mode": "heartbeat_only",
            "restore_started_at": restore_started_at,
            "checked_at": _now_iso(),
        }

    mark_user_bot_requested(username, True)

    if _RUNTIME_SCHEDULER is None:
        return {
            "started": False,
            "already_running": False,
            "thread_alive": False,
            "first_tick_ok": False,
            "loop_alive": False,
            "reason": "runtime_scheduler_not_registered",
            "mode": mode,
            "restore_started_at": restore_started_at,
            "checked_at": _now_iso(),
        }

    already_running = bool(getattr(_RUNTIME_SCHEDULER, "is_alive", lambda: False)())
    started = False
    if not already_running:
        started = bool(_RUNTIME_SCHEDULER.start())

    deadline = time.monotonic() + max(0.0, float(wait_seconds or 0))
    thread_alive = is_bot_task_alive(username)
    first_tick_ok = restore_first_tick_ok(load_shadow(username), restore_started_at)
    while not thread_alive and time.monotonic() < deadline:
        time.sleep(0.05)
        thread_alive = is_bot_task_alive(username)
    first_tick_ok = restore_first_tick_ok(load_shadow(username), restore_started_at)

    reason = ""
    if not thread_alive:
        reason = "bot_loop_task_failed_to_start"
    elif not first_tick_ok:
        reason = "waiting_first_tick"

    if thread_alive:
        monitor = threading.Thread(
            target=_monitor_restore_first_tick,
            args=(username, mode, restore_started_at),
            name=f"hmtstc-restore-watchdog-{username}",
            daemon=True,
        )
        monitor.start()

    return _restore_result(started, already_running, thread_alive, first_tick_ok, reason, mode, restore_started_at)
