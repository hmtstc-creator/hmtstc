from __future__ import annotations

import hashlib
import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.config import BASE_DIR


PAPER_LAB_STORE_FILE = BASE_DIR / "paper_lab_store.json"
PAPER_LAB_STORE_VERSION = 1
MAX_RUNS_PER_USER = 20
_STORE_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store() -> dict[str, Any]:
    return {
        "version": PAPER_LAB_STORE_VERSION,
        "updated_at": None,
        "users": {},
    }


def _clean_username(username: str | None) -> str:
    return str(username or "default").strip() or "default"


def _clean_id_list(value: Any) -> list[str]:
    clean: list[str] = []
    for raw_id in value if isinstance(value, list) else []:
        item_id = str(raw_id or "").strip()
        if item_id and item_id not in clean:
            clean.append(item_id)
    return clean


def paper_lab_rules_fingerprint(filter_ids: list[str] | None, strategy_ids: list[str] | None) -> str:
    payload = {
        "filters": sorted(_clean_id_list(filter_ids)),
        "strategies": sorted(_clean_id_list(strategy_ids)),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _parse_run_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def normalize_paper_lab_run(run: Any) -> dict[str, Any]:
    source = run if isinstance(run, dict) else {}
    filter_ids = _clean_id_list(source.get("filter_ids") or source.get("paper_lab_filter_ids"))
    strategy_ids = _clean_id_list(source.get("strategy_ids") or source.get("paper_lab_strategy_ids"))
    started_at = str(source.get("started_at") or _now_iso())
    completed_at = str(source.get("completed_at") or started_at)
    status = str(source.get("status") or "completed").strip() or "completed"
    fingerprint = str(source.get("rules_fingerprint") or paper_lab_rules_fingerprint(filter_ids, strategy_ids))

    return {
        "run_id": str(source.get("run_id") or source.get("id") or f"plab_{uuid4().hex}"),
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "filter_ids": filter_ids,
        "strategy_ids": strategy_ids,
        "filter_count": _to_int(source.get("filter_count") if source.get("filter_count") is not None else len(filter_ids)),
        "strategy_count": _to_int(source.get("strategy_count") if source.get("strategy_count") is not None else len(strategy_ids)),
        "candidate_count": _to_int(source.get("candidate_count") or source.get("paper_lab_candidate_count")),
        "accepted_combinations": _to_int(source.get("accepted_combinations") or source.get("accepted_count")),
        "rejected_combinations": _to_int(source.get("rejected_combinations") or source.get("rejected_count")),
        "model_count": _to_int(source.get("model_count")),
        "trigger": str(source.get("trigger") or "manual"),
        "source": str(source.get("source") or "all_enabled_rules"),
        "rules_fingerprint": fingerprint,
        "error_message": str(source.get("error_message") or ""),
        "results": source.get("results") if isinstance(source.get("results"), list) else [],
    }


def normalize_paper_lab_store(data: Any) -> dict[str, Any]:
    store = deepcopy(data) if isinstance(data, dict) else _empty_store()
    store["version"] = PAPER_LAB_STORE_VERSION
    store.setdefault("updated_at", None)
    users = store.get("users") if isinstance(store.get("users"), dict) else {}
    normalized_users: dict[str, Any] = {}

    for username, raw_state in users.items():
        clean_username = _clean_username(username)
        state = raw_state if isinstance(raw_state, dict) else {}
        raw_runs = state.get("runs") if isinstance(state.get("runs"), list) else []
        runs = [normalize_paper_lab_run(item) for item in raw_runs][-MAX_RUNS_PER_USER:]
        last_run_id = str(state.get("last_run_id") or (runs[-1]["run_id"] if runs else ""))
        normalized_users[clean_username] = {
            "last_run_id": last_run_id,
            "runs": runs,
        }

    store["users"] = normalized_users
    return store


def _backup_corrupt_store(path: Path) -> None:
    if not path.exists():
        return
    backup_path = path.with_name(f"{path.name}.corrupt.{uuid4().hex}.bak")
    try:
        os.replace(path, backup_path)
    except Exception:
        pass


def load_paper_lab_store() -> dict[str, Any]:
    with _STORE_LOCK:
        if not PAPER_LAB_STORE_FILE.exists():
            return _empty_store()
        try:
            return normalize_paper_lab_store(json.loads(PAPER_LAB_STORE_FILE.read_text(encoding="utf-8")))
        except Exception:
            _backup_corrupt_store(PAPER_LAB_STORE_FILE)
            return _empty_store()


def save_paper_lab_store(data: dict[str, Any]) -> dict[str, Any]:
    with _STORE_LOCK:
        store = normalize_paper_lab_store(data)
        store["updated_at"] = _now_iso()
        PAPER_LAB_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = PAPER_LAB_STORE_FILE.with_name(f"{PAPER_LAB_STORE_FILE.name}.{uuid4().hex}.tmp")
        try:
            tmp_path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp_path, PAPER_LAB_STORE_FILE)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
        return store


def record_paper_lab_run(username: str, run_summary: dict[str, Any]) -> dict[str, Any]:
    clean_username = _clean_username(username)
    with _STORE_LOCK:
        store = load_paper_lab_store()
        user_state = store.setdefault("users", {}).setdefault(clean_username, {"last_run_id": "", "runs": []})
        runs = user_state.setdefault("runs", [])
        run = normalize_paper_lab_run(run_summary)
        runs.append(run)
        user_state["runs"] = runs[-MAX_RUNS_PER_USER:]
        user_state["last_run_id"] = run["run_id"]
        save_paper_lab_store(store)
        return run


def list_paper_lab_runs(username: str, limit: int = MAX_RUNS_PER_USER) -> list[dict[str, Any]]:
    clean_username = _clean_username(username)
    store = load_paper_lab_store()
    state = (store.get("users") or {}).get(clean_username) or {}
    runs = state.get("runs") if isinstance(state.get("runs"), list) else []
    return deepcopy(runs[-max(1, int(limit or MAX_RUNS_PER_USER)):])


def get_last_paper_lab_run(username: str) -> dict[str, Any] | None:
    runs = list_paper_lab_runs(username, limit=1)
    return runs[-1] if runs else None


def get_latest_paper_lab_run_any_user() -> dict[str, Any] | None:
    store = load_paper_lab_store()
    users = store.get("users") if isinstance(store.get("users"), dict) else {}
    latest_run: dict[str, Any] | None = None
    latest_stamp: datetime | None = None

    for username, state in users.items():
        if not isinstance(state, dict):
            continue
        runs = state.get("runs") if isinstance(state.get("runs"), list) else []
        for raw_run in runs:
            run = normalize_paper_lab_run(raw_run)
            stamp = _parse_run_time(run.get("completed_at") or run.get("started_at"))
            if stamp is None:
                continue
            if latest_stamp is None or stamp > latest_stamp:
                latest_stamp = stamp
                latest_run = deepcopy(run)
                latest_run["username"] = str(username)

    return latest_run


def build_paper_lab_status(username: str, current_filter_ids: list[str] | None = None, current_strategy_ids: list[str] | None = None) -> dict[str, Any]:
    filter_ids = _clean_id_list(current_filter_ids)
    strategy_ids = _clean_id_list(current_strategy_ids)
    fingerprint = paper_lab_rules_fingerprint(filter_ids, strategy_ids)
    runs = list_paper_lab_runs(username, limit=MAX_RUNS_PER_USER)
    last_run = runs[-1] if runs else None

    return {
        "status": "ok",
        "last_run": last_run or {},
        "runs": runs,
        "store_persistent": True,
        "rules_fingerprint": fingerprint,
        "last_run_matches_current_rules": bool(last_run and last_run.get("rules_fingerprint") == fingerprint),
    }
