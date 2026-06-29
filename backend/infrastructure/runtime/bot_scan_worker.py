from __future__ import annotations

import copy
import multiprocessing
import queue
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from core.storage import append_log, load_settings, load_shadow, update_shadow_state
from infrastructure.runtime.bot_runtime_registry import mark_user_bot_requested
from services.bot_service import run_bot_tick_guarded
from infrastructure.runtime.bot_runtime_flags import ENABLE_BACKGROUND_SCAN_WORKER


SCAN_WORKER_TIMEOUT_SECONDS = 25
_WORKERS: dict[str, dict[str, Any]] = {}
_WORKERS_LOCK = threading.Lock()
_RESULT_KEYS = (
    "last_scan",
    "last_scan_time",
    "last_tick",
    "last_updated_at",
    "last_calculation_at",
    "last_tick_started_at",
    "last_tick_finished_at",
    "open_positions",
    "history",
    "paper_lab",
    "performance_points",
    "bot_loop_traces",
)
_TERMINATE_GRACE_SECONDS = 1.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deadline_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(1, seconds))).isoformat()


def _worker_write_allowed(current: dict, generation: int, cancel_event) -> bool:
    return bool(
        int(current.get("scan_worker_generation") or 0) == generation
        and current.get("requested_running", current.get("bot_running", False))
        and str(current.get("engine_status") or "") not in {"failed", "stopped", "emergency_stopped"}
        and not current.get("scan_cancel_requested")
        and not cancel_event.is_set()
    )


def _extract_result_data(local_data: dict) -> dict:
    return {key: copy.deepcopy(local_data[key]) for key in _RESULT_KEYS if key in local_data}


def _run_scan_child(username: str, generation: int, cancel_event, deadline: float, limit: int, result_queue) -> None:
    """Run the expensive scan outside the uvicorn process.

    A Python thread cannot be killed while it is blocked in CPU/network work. The
    parent process monitors this child and terminates it when the deadline is
    exceeded, so uvicorn cannot stay at 100% CPU after a stale deep scan.
    """
    result: dict[str, Any] = {"status": "cancelled", "reason": "scan_worker_cancelled"}
    result_data: dict[str, Any] = {}
    try:
        if cancel_event.is_set() or time.monotonic() >= deadline:
            result_queue.put({"result": result, "data": result_data, "timed_out": False})
            return

        local_data = copy.deepcopy(load_shadow(username))
        local_settings = copy.deepcopy(load_settings(username))
        local_data["_runtime_username"] = username
        local_data["bot_running"] = True
        local_data["active_scan_worker"] = True

        result = run_bot_tick_guarded(
            local_data,
            local_settings,
            limit=limit,
            cancel_requested=cancel_event.is_set,
            deadline=deadline,
        )
        result_data = _extract_result_data(local_data)
        result_queue.put({"result": result, "data": result_data, "timed_out": time.monotonic() >= deadline})
    except BaseException as error:  # child must report every failure, including KeyboardInterrupt/SystemExit
        timed_out = isinstance(error, TimeoutError) or time.monotonic() >= deadline
        if timed_out:
            cancel_event.set()
        result_queue.put({
            "result": {
                "status": "error",
                "reason": f"{type(error).__name__}:{str(error)[:200]}",
                "traceback": traceback.format_exc(limit=8)[-2000:],
            },
            "data": result_data,
            "timed_out": timed_out,
        })


def _terminate_process(process: multiprocessing.Process) -> None:
    if not process.is_alive():
        return
    process.terminate()
    process.join(_TERMINATE_GRACE_SECONDS)
    if process.is_alive():
        try:
            process.kill()
        except AttributeError:
            process.terminate()
        process.join(_TERMINATE_GRACE_SECONDS)


def _persist_worker_result(username: str, generation: int, cancel_event, result: dict[str, Any], result_data: dict[str, Any], timed_out: bool) -> None:
    def persist_result(current: dict) -> dict:
        same_generation = int(current.get("scan_worker_generation") or 0) == generation
        if not same_generation:
            return current

        if timed_out:
            current["requested_running"] = False
            current["bot_running"] = False
            current["engine_status"] = "failed"
            current["primary_runtime_problem"] = "scan_worker_timeout"
            current["scan_cancel_requested"] = True
            current["next_tick_not_before"] = None
            append_log(current, "warn", f"BOT_SCAN_WORKER_TIMEOUT generation={generation}", "bot_scan_worker_timeout")
        elif _worker_write_allowed(current, generation, cancel_event):
            for key in _RESULT_KEYS:
                if key in result_data:
                    current[key] = copy.deepcopy(result_data[key])
            if result.get("status") == "ok":
                current["engine_status"] = "running"
                current["primary_runtime_problem"] = None
                append_log(current, "info", f"BOT_SCAN_WORKER_OK generation={generation}", "bot_scan_worker_ok")
            elif result.get("status") not in {"cancelled", "skipped"}:
                current["primary_runtime_problem"] = str(result.get("reason") or "scan_worker_failed")[:240]
                append_log(current, "error", f"BOT_SCAN_WORKER_FAILED generation={generation} reason={current['primary_runtime_problem']}", "bot_scan_worker_failed")
        else:
            append_log(current, "warn", f"BOT_SCAN_WORKER_RESULT_DROPPED generation={generation}", "bot_scan_worker_result_dropped")

        current["active_scan_worker"] = False
        current["scan_worker_started_at"] = None
        current["scan_worker_deadline_at"] = None
        current["tick_in_progress"] = False
        if not timed_out and _worker_write_allowed(current, generation, cancel_event):
            current["scan_cancel_requested"] = False
        return current

    update_shadow_state(username, persist_result)
    if timed_out:
        mark_user_bot_requested(username, False)


def _monitor_scan_worker(username: str, generation: int, cancel_event, deadline: float, result_queue, process: multiprocessing.Process) -> None:
    result: dict[str, Any] = {"status": "cancelled", "reason": "scan_worker_cancelled"}
    result_data: dict[str, Any] = {}
    timed_out = False
    try:
        remaining = max(0.1, deadline - time.monotonic())
        try:
            payload = result_queue.get(timeout=remaining)
            result = payload.get("result") or result
            result_data = payload.get("data") or {}
            timed_out = bool(payload.get("timed_out")) or time.monotonic() >= deadline
        except queue.Empty:
            timed_out = True
            result = {"status": "error", "reason": "scan_worker_timeout"}

        if timed_out:
            cancel_event.set()
            _terminate_process(process)
        else:
            process.join(0.2)
            if process.is_alive() and time.monotonic() >= deadline:
                timed_out = True
                cancel_event.set()
                _terminate_process(process)
                result = {"status": "error", "reason": "scan_worker_timeout"}

        _persist_worker_result(username, generation, cancel_event, result, result_data, timed_out)
    except Exception as error:
        cancel_event.set()
        _terminate_process(process)
        _persist_worker_result(
            username,
            generation,
            cancel_event,
            {"status": "error", "reason": f"scan_worker_monitor_error:{type(error).__name__}:{str(error)[:160]}"},
            {},
            True,
        )
    finally:
        with _WORKERS_LOCK:
            entry = _WORKERS.get(username)
            if entry and entry.get("generation") == generation:
                _WORKERS.pop(username, None)


def _cleanup_dead_worker(username: str, entry: dict[str, Any]) -> None:
    process = entry.get("process")
    if process and not process.is_alive():
        try:
            process.join(0.1)
        except Exception:
            pass
        _WORKERS.pop(username, None)


def start_scan_worker(username: str, *, limit: int = 100) -> dict[str, Any]:
    if not ENABLE_BACKGROUND_SCAN_WORKER:
        return {"started": False, "active": False, "reason": "background_scan_worker_disabled"}

    with _WORKERS_LOCK:
        existing = _WORKERS.get(username)
        if existing:
            process = existing.get("process")
            if process and process.is_alive():
                return {"started": False, "active": True, "generation": existing.get("generation")}
            _cleanup_dead_worker(username, existing)

        prepared: dict[str, Any] = {}

        def prepare_start(data: dict) -> dict:
            if not data.get("requested_running", data.get("bot_running", False)):
                prepared["reason"] = "bot_not_requested"
                return data
            if str(data.get("engine_status") or "") in {"failed", "stopped", "emergency_stopped"}:
                prepared["reason"] = "engine_not_running"
                return data
            generation = int(data.get("scan_worker_generation") or 0) + 1
            prepared["generation"] = generation
            data["scan_worker_generation"] = generation
            data["active_scan_worker"] = True
            data["scan_worker_started_at"] = _now_iso()
            data["scan_worker_deadline_at"] = _deadline_iso(SCAN_WORKER_TIMEOUT_SECONDS)
            data["scan_cancel_requested"] = False
            append_log(data, "info", f"BOT_SCAN_WORKER_STARTED generation={generation}", "bot_scan_worker_started")
            return data

        update_shadow_state(username, prepare_start)
        if "generation" not in prepared:
            return {"started": False, "active": False, "reason": prepared.get("reason") or "worker_start_rejected"}

        generation = int(prepared["generation"])
        cancel_event = multiprocessing.Event()
        result_queue = multiprocessing.Queue(maxsize=1)
        deadline = time.monotonic() + SCAN_WORKER_TIMEOUT_SECONDS
        bounded_limit = max(20, min(int(limit or 100), 120))

        process = multiprocessing.Process(
            target=_run_scan_child,
            args=(username, generation, cancel_event, deadline, bounded_limit, result_queue),
            name=f"hmtstc-scan-worker-{username}-{generation}",
            daemon=True,
        )
        monitor = threading.Thread(
            target=_monitor_scan_worker,
            args=(username, generation, cancel_event, deadline, result_queue, process),
            name=f"hmtstc-scan-monitor-{username}-{generation}",
            daemon=True,
        )
        _WORKERS[username] = {"process": process, "monitor": monitor, "cancel_event": cancel_event, "generation": generation}
        process.start()
        monitor.start()
        return {"started": True, "active": True, "generation": generation, "pid": process.pid}


def cancel_scan_worker(username: str, *, reason: str = "cancel_requested") -> dict[str, Any]:
    entry = None
    with _WORKERS_LOCK:
        entry = _WORKERS.pop(username, None)
        if entry:
            try:
                entry["cancel_event"].set()
            except Exception:
                pass
            process = entry.get("process")
            if process:
                _terminate_process(process)

    def apply_cancel(data: dict) -> dict:
        data["scan_worker_generation"] = int(data.get("scan_worker_generation") or 0) + 1
        data["active_scan_worker"] = False
        data["scan_worker_started_at"] = None
        data["scan_worker_deadline_at"] = None
        data["scan_cancel_requested"] = True
        data["tick_in_progress"] = False
        append_log(data, "warn", f"BOT_SCAN_WORKER_CANCEL reason={reason}", "bot_scan_worker_cancel")
        return data

    data = update_shadow_state(username, apply_cancel)
    return {"cancelled": bool(entry), "generation": data["scan_worker_generation"], "reason": reason}


def scan_worker_alive(username: str) -> bool:
    with _WORKERS_LOCK:
        entry = _WORKERS.get(username)
        process = entry.get("process") if entry else None
        if process and process.is_alive():
            return True
        if entry:
            _cleanup_dead_worker(username, entry)
        return False


def reconcile_stale_scan_worker(username: str) -> dict[str, Any]:
    """Clear stale persisted worker state without starting replacement work."""
    data = load_shadow(username)
    if not data.get("active_scan_worker"):
        return data

    deadline = data.get("scan_worker_deadline_at")
    deadline_expired = False
    if deadline:
        try:
            parsed = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            deadline_expired = parsed <= datetime.now(timezone.utc)
        except Exception:
            deadline_expired = True

    if scan_worker_alive(username) and not deadline_expired:
        return data

    def clear_stale(current: dict) -> dict:
        if not current.get("active_scan_worker"):
            return current
        current["active_scan_worker"] = False
        current["scan_worker_started_at"] = None
        current["scan_worker_deadline_at"] = None
        current["scan_worker_pid"] = None
        current["scan_cancel_requested"] = True
        current["tick_in_progress"] = False
        current["primary_runtime_problem"] = "stale_scan_worker_cleared"
        append_log(current, "warn", "STALE_SCAN_WORKER_CLEARED", "stale_scan_worker_cleared")
        return current

    return update_shadow_state(username, clear_stale)
