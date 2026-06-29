from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from infrastructure.runtime.bot_runtime_registry import mark_bot_task_exception, mark_bot_task_started, register_bot_task_thread


class RuntimeScheduler:
    """Small single-process scheduler wrapper for the existing bot loop.

    Rev59 goal: no import-time runtime side effects. The scheduler starts only
    during FastAPI lifespan/startup and can be stopped in tests/shutdown.
    """

    def __init__(self, target: Callable[[], None], name: str = "hmtstc-bot-loop"):
        self._target = target
        self._name = name
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._lock = threading.Lock()

    @property
    def started(self) -> bool:
        return self._started

    def start(self) -> bool:
        with self._lock:
            if self._started:
                return False
            self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
            register_bot_task_thread(self._thread)
            self._started = True
            self._thread.start()
            return True

    def _run(self) -> None:
        mark_bot_task_started()
        try:
            self._target()
        except Exception as exc:
            mark_bot_task_exception(exc)
            raise
        finally:
            with self._lock:
                self._started = False
                register_bot_task_thread(None)

    def is_alive(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive())


def sleep_seconds(seconds: int) -> None:
    time.sleep(seconds)
