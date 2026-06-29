from __future__ import annotations

from typing import Any, Dict, Protocol

from core.storage import load_settings, load_shadow, save_settings, save_shadow


class StateRepository(Protocol):
    def load_shadow(self, user: str) -> Dict[str, Any]: ...
    def save_shadow(self, data: Dict[str, Any], user: str) -> None: ...
    def load_settings(self, user: str) -> Dict[str, Any]: ...
    def save_settings(self, settings: Dict[str, Any], user: str) -> None: ...


class JsonStateRepository:
    """Repository façade over the current JSON store.

    This keeps Rev59 behavior identical while creating a clean replacement seam
    for SQLite/Postgres. Services can be migrated one domain at a time without
    touching route code or changing payloads.
    """

    backend = "json-file"

    def load_shadow(self, user: str) -> Dict[str, Any]:
        return load_shadow(user)

    def save_shadow(self, data: Dict[str, Any], user: str) -> None:
        save_shadow(data, user)

    def load_settings(self, user: str) -> Dict[str, Any]:
        return load_settings(user)

    def save_settings(self, settings: Dict[str, Any], user: str) -> None:
        save_settings(settings, user)


def get_state_repository() -> StateRepository:
    return JsonStateRepository()
