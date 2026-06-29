from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


TICK_STALE_THRESHOLD_SECONDS = 180
SCAN_STALE_THRESHOLD_SECONDS = 300
BOT_TASK_HEARTBEAT_STALE_SECONDS = 90

_LOCK = threading.RLock()
_TASK_THREAD: threading.Thread | None = None
_REGISTRY: dict[str, Any] = {
    "bot_task_running": False,
    "bot_task_started_at": None,
    "bot_task_last_heartbeat_at": None,
    "bot_task_exception": "",
    "users": {},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _fresh_timestamp(value: Any, threshold_seconds: int) -> bool:
    stamp = _parse_iso(value)
    if not stamp:
        return False
    return max(0, int((datetime.now(stamp.tzinfo) - stamp).total_seconds())) <= threshold_seconds


def register_bot_task_thread(thread: threading.Thread | None) -> None:
    global _TASK_THREAD
    with _LOCK:
        _TASK_THREAD = thread


def mark_bot_task_started() -> dict[str, Any]:
    with _LOCK:
        _REGISTRY["bot_task_running"] = True
        _REGISTRY["bot_task_started_at"] = _REGISTRY.get("bot_task_started_at") or _now_iso()
        _REGISTRY["bot_task_last_heartbeat_at"] = _now_iso()
        _REGISTRY["bot_task_exception"] = ""
        return snapshot_bot_task_registry()


def mark_bot_task_heartbeat(username: str | None = None) -> dict[str, Any]:
    with _LOCK:
        _REGISTRY["bot_task_last_heartbeat_at"] = _now_iso()
        if username:
            user_state = _REGISTRY.setdefault("users", {}).setdefault(str(username), {})
            user_state["loop_alive"] = True
            user_state["bot_task_last_heartbeat_at"] = _REGISTRY["bot_task_last_heartbeat_at"]
            user_state["bot_task_exception"] = ""
        return snapshot_bot_task_registry()


def mark_bot_task_exception(error: Exception | str, username: str | None = None) -> dict[str, Any]:
    text = str(error or "")[:240]
    with _LOCK:
        _REGISTRY["bot_task_running"] = False
        _REGISTRY["bot_task_exception"] = text
        _REGISTRY["bot_task_last_heartbeat_at"] = _now_iso()
        if username:
            user_state = _REGISTRY.setdefault("users", {}).setdefault(str(username), {})
            user_state["loop_alive"] = False
            user_state["bot_task_exception"] = text
        return snapshot_bot_task_registry()


def mark_user_bot_requested(username: str, requested: bool) -> dict[str, Any]:
    with _LOCK:
        user_state = _REGISTRY.setdefault("users", {}).setdefault(str(username), {})
        user_state["requested_running"] = bool(requested)
        user_state["bot_task_requested_at"] = _now_iso()
        if not requested:
            user_state["loop_alive"] = False
            user_state["bot_task_stopped_at"] = user_state["bot_task_requested_at"]
        return snapshot_bot_task_registry()


def snapshot_bot_task_registry(username: str | None = None) -> dict[str, Any]:
    state = deepcopy(_REGISTRY)
    if username:
        state["user"] = deepcopy((_REGISTRY.get("users") or {}).get(str(username), {}))
    return state


def is_bot_task_alive(username: str | None = None) -> bool:
    with _LOCK:
        if not bool(_REGISTRY.get("bot_task_running")):
            return False
        if not (_TASK_THREAD and _TASK_THREAD.is_alive()):
            return False
        if not _fresh_timestamp(_REGISTRY.get("bot_task_last_heartbeat_at"), BOT_TASK_HEARTBEAT_STALE_SECONDS):
            return False
        if username:
            user_state = (_REGISTRY.get("users") or {}).get(str(username), {})
            if user_state.get("bot_task_exception"):
                return False
        return True
