from __future__ import annotations

from datetime import datetime
from typing import Any

from infrastructure.runtime.bot_runtime_registry import (
    SCAN_STALE_THRESHOLD_SECONDS,
    TICK_STALE_THRESHOLD_SECONDS,
    is_bot_task_alive,
    snapshot_bot_task_registry,
)
from infrastructure.runtime.bot_runtime_flags import ENABLE_BACKGROUND_SCAN_WORKER


def _parse_iso(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _age_seconds(value: Any) -> int | None:
    stamp = _parse_iso(value)
    if not stamp:
        return None
    now = datetime.now(stamp.tzinfo)
    return max(0, int((now - stamp).total_seconds()))


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


def _threshold(settings: dict, key: str, default: int) -> int:
    bot = settings.get("bot") if isinstance(settings.get("bot"), dict) else {}
    try:
        return int(bot.get(key) or default)
    except Exception:
        return default


def build_bot_runtime_truth(data: dict, settings: dict, username: str | None = None) -> dict[str, Any]:
    tick_threshold = _threshold(settings, "tick_stale_threshold_seconds", TICK_STALE_THRESHOLD_SECONDS)
    scan_threshold = _threshold(settings, "scan_stale_threshold_seconds", SCAN_STALE_THRESHOLD_SECONDS)
    last_scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
    last_tick_age = _age_seconds(data.get("last_tick"))
    last_scan_age = _age_seconds(last_scan.get("time"))
    restore_started_at = data.get("last_runtime_restore_at")
    restore_age = _age_seconds(data.get("last_runtime_restore_at"))
    tick_fresh = last_tick_age is not None and last_tick_age <= tick_threshold
    scan_fresh = last_scan_age is not None and last_scan_age <= scan_threshold
    restore_first_tick_ok = bool(
        data.get("last_runtime_restore_first_tick_ok_at")
        or (restore_started_at and _after(data.get("last_tick"), restore_started_at))
    )
    startup_scan_grace = bool(restore_first_tick_ok and restore_age is not None and restore_age <= scan_threshold)
    scan_runtime_ready = bool(scan_fresh or startup_scan_grace)
    requested_running = bool(data.get("requested_running", data.get("bot_running", False)))
    registry = snapshot_bot_task_registry(username)
    task_exception = str(registry.get("bot_task_exception") or ((registry.get("user") or {}).get("bot_task_exception") or ""))
    task_alive = is_bot_task_alive(username)
    stored_engine_status = str(data.get("engine_status") or "")
    stored_problem = str(data.get("primary_runtime_problem") or "")

    if not ENABLE_BACKGROUND_SCAN_WORKER:
        engine_status = "running" if requested_running else "stopped"
        primary_problem = None if stored_problem in {"", "waiting_first_tick", "bot_loop_not_alive", "scan_stale", "bot_tick_stale"} else stored_problem
        effective_running = bool(requested_running and engine_status == "running")
        return {
            "requested_running": requested_running,
            "thread_alive": False,
            "loop_alive": False,
            "bot_running": effective_running,
            "engine_status": engine_status,
            "runtime_health_status": "ok",
            "last_tick_age_seconds": last_tick_age,
            "last_scan_age_seconds": last_scan_age,
            "restore_age_seconds": restore_age,
            "restore_first_tick_ok": restore_first_tick_ok,
            "startup_scan_grace": False,
            "tick_stale_threshold_seconds": tick_threshold,
            "scan_stale_threshold_seconds": scan_threshold,
            "restart_required": False,
            "primary_runtime_problem": primary_problem,
            "bot_task_running": False,
            "bot_task_started_at": registry.get("bot_task_started_at"),
            "bot_task_last_heartbeat_at": registry.get("bot_task_last_heartbeat_at"),
            "bot_task_exception": "",
            "runtime_mode": "heartbeat_only",
        }

    primary_problem = None
    waiting_first_tick = bool(
        requested_running
        and restore_age is not None
        and not restore_first_tick_ok
        and restore_age <= tick_threshold
    )
    restore_no_first_tick = bool(
        requested_running
        and restore_age is not None
        and not restore_first_tick_ok
        and restore_age > tick_threshold
    )

    if task_exception:
        engine_status = "failed"
        primary_problem = stored_problem or f"bot_loop_task_failed:{task_exception}"[:240]
    elif stored_engine_status == "failed" and stored_problem:
        engine_status = "failed"
        primary_problem = stored_problem
    elif restore_no_first_tick:
        engine_status = "failed"
        primary_problem = "restore_no_first_tick"
    elif not requested_running:
        engine_status = "stopped"
    elif waiting_first_tick:
        engine_status = "restoring"
        primary_problem = "waiting_first_tick"
    elif not task_alive:
        engine_status = "stale"
        primary_problem = "bot_loop_not_alive"
    elif not tick_fresh:
        engine_status = "stale"
        primary_problem = "bot_tick_stale"
    elif not scan_runtime_ready:
        engine_status = "stale"
        primary_problem = "scan_stale"
    else:
        engine_status = "running"

    loop_alive = bool(requested_running and task_alive and tick_fresh and scan_runtime_ready and restore_first_tick_ok and not task_exception)
    effective_bot_running = bool(requested_running and loop_alive and engine_status == "running")

    return {
        "requested_running": requested_running,
        "thread_alive": task_alive,
        "loop_alive": loop_alive,
        "bot_running": effective_bot_running,
        "engine_status": engine_status,
        "runtime_health_status": "degraded" if engine_status in {"stale", "failed"} else "ok",
        "last_tick_age_seconds": last_tick_age,
        "last_scan_age_seconds": last_scan_age,
        "restore_age_seconds": restore_age,
        "restore_first_tick_ok": restore_first_tick_ok,
        "startup_scan_grace": startup_scan_grace,
        "tick_stale_threshold_seconds": tick_threshold,
        "scan_stale_threshold_seconds": scan_threshold,
        "restart_required": bool(requested_running and engine_status in {"stale", "failed"}),
        "primary_runtime_problem": primary_problem,
        "bot_task_running": bool(registry.get("bot_task_running")),
        "bot_task_started_at": registry.get("bot_task_started_at"),
        "bot_task_last_heartbeat_at": registry.get("bot_task_last_heartbeat_at"),
        "bot_task_exception": task_exception,
    }
