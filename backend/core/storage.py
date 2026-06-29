import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.settings_unit_service import normalize_settings_units
from services.real_trade_state_service import ensure_real_trade_state

from core.config import (
    DEFAULT_COIN_FILTER,
    DEFAULT_SHADOW_STATE,
    DEFAULT_STRATEGIES,
    DEFAULT_USER,
    SETTINGS_FILE,
    SHADOW_FILE,
    SHADOW_LOCK,
)


HISTORY_LIMIT = 5000
LOG_LIMIT = 3000
PERFORMANCE_LIMIT = 5000
AUDIT_LIMIT = 1000


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _parse_dt(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _seconds_between(start, end) -> int:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)

    if not start_dt or not end_dt:
        return 0

    return max(int((end_dt - start_dt).total_seconds()), 0)


def _format_duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}g {hours}s {minutes}dk"
    if hours > 0:
        return f"{hours}s {minutes}dk"
    return f"{minutes}dk"


def sync_last_scan_state(data: dict, scan: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    safe_scan = scan if isinstance(scan, dict) else {}
    data["last_scan"] = safe_scan
    data["last_scan_time"] = safe_scan.get("time")
    return safe_scan


def read_json_file(path, default_value: Any):
    path = Path(path)

    if not path.exists():
        example_path = path.with_name(f"{path.stem}.example{path.suffix}")
        if example_path.exists():
            try:
                with example_path.open("r", encoding="utf-8") as file:
                    return json.load(file)
            except Exception:
                return deepcopy(default_value)
        return deepcopy(default_value)

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return deepcopy(default_value)


def write_json_file(path, data: Any):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(path.suffix + ".tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    temp_file.replace(path)


def normalize_strategy_list(strategies):
    cleaned = []

    if isinstance(strategies, list):
        for item in strategies:
            if not isinstance(item, dict):
                continue

            name = str(item.get("name") or "").strip()
            if not name:
                continue

            cleaned.append({
                "name": name,
                "active": bool(item.get("active", True)),
                "type": item.get("type", ""),
                "description": item.get("description", "")
            })

    if not cleaned:
        cleaned = deepcopy(DEFAULT_STRATEGIES)

    existing_names = {item["name"] for item in cleaned}

    for default_strategy in DEFAULT_STRATEGIES:
        if default_strategy["name"] not in existing_names:
            cleaned.append(deepcopy(default_strategy))

    return cleaned


def normalize_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        settings = {}

    settings.setdefault("api", {
        "mode": "shadow",
        "binance_status": "mock",
        "api_key_saved": False
    })

    settings.setdefault("bot", {
        "default_mode": "shadow",
        "max_open_positions": 5,
        "usdt_per_position": 200,
        "allocated_usdt": 1000
    })

    settings.setdefault("risk", {
        "profile": "balanced",
        "daily_loss_limit": "30 USDT",
        "weekly_loss_limit": "90 USDT",
        "stop_loss": "0.75%",
        "take_profit": "2%",
        "max_portfolio_risk_percent": 5,
        "risk_per_position_percent": 1,
        "dynamic_position_size": False,
        "volatility_stop_enabled": False,
        "max_same_direction_positions": 3,
        "max_slippage_percent": 0.35,
        "max_spread_percent": 0.35
    })

    settings.setdefault("telegram", {
        "enabled": False,
        "chat_id_saved": False
    })

    risk = settings.setdefault("risk", {})
    risk.setdefault("profile", "balanced")
    risk.setdefault("weekly_loss_limit", "90 USDT")
    risk.setdefault("max_slippage_percent", 0.35)
    risk.setdefault("max_spread_percent", 0.35)

    bot = settings.setdefault("bot", {})

    try:
        bot["max_open_positions"] = max(1, int(bot.get("max_open_positions", 5)))
    except (TypeError, ValueError):
        bot["max_open_positions"] = 5

    try:
        bot["usdt_per_position"] = max(1, float(bot.get("usdt_per_position", 200)))
    except (TypeError, ValueError):
        bot["usdt_per_position"] = 200

    try:
        bot["allocated_usdt"] = max(
            bot["usdt_per_position"],
            float(bot.get("allocated_usdt", 1000))
        )
    except (TypeError, ValueError):
        bot["allocated_usdt"] = max(bot["usdt_per_position"], 1000)

    settings["api"]["mode"] = "shadow"
    bot["default_mode"] = "shadow"

    # Revizyon_13: merkezi birim normalizasyonu.
    # Kullanıcı 0,75 yazarsa yüzde alanında 0.75% kabul edilir;
    # para alanlarında çıplak sayı USDT olarak yorumlanır.
    settings = normalize_settings_units(settings)
    bot = settings.setdefault("bot", {})
    risk = settings.setdefault("risk", {})

    coin_filter = settings.get("coin_filter")
    if not isinstance(coin_filter, dict):
        coin_filter = {}
    settings["coin_filter"] = {
        **DEFAULT_COIN_FILTER,
        **coin_filter
    }

    settings["strategies"] = normalize_strategy_list(settings.get("strategies"))

    strategy_names = [item["name"] for item in settings["strategies"]]
    current_strategy = settings.get("current_strategy")

    current_item = next(
        (item for item in settings["strategies"] if item.get("name") == current_strategy),
        None
    )

    if not current_item or current_item.get("active") is False:
        first_active = next(
            (item["name"] for item in settings["strategies"] if item.get("active") is not False),
            None
        )

        if first_active:
            settings["current_strategy"] = first_active
        elif strategy_names:
            settings["strategies"][0]["active"] = True
            settings["current_strategy"] = strategy_names[0]

    return settings


def normalize_trade_record(position: dict, status: str = "open") -> dict:
    if not isinstance(position, dict):
        position = {}

    normalized = deepcopy(position)
    now = now_iso()

    normalized["id"] = str(normalized.get("id") or normalized.get("trade_id") or uuid4())
    normalized["trade_id"] = normalized["id"]
    normalized["mode"] = "shadow"

    symbol = str(normalized.get("symbol") or "").strip().upper()
    normalized["symbol"] = symbol

    entry = _safe_float(normalized.get("entry"), _safe_float(normalized.get("entry_price")))
    exit_price = _safe_float(normalized.get("exit"), _safe_float(normalized.get("exit_price")))
    current = _safe_float(normalized.get("current"), exit_price or entry)
    quantity = _safe_float(normalized.get("quantity"))
    usdt_size = _safe_float(normalized.get("usdt_size"))

    if quantity <= 0 and entry > 0 and usdt_size > 0:
        quantity = round(usdt_size / entry, 8)

    if usdt_size <= 0 and entry > 0 and quantity > 0:
        usdt_size = round(entry * quantity, 4)

    if status == "closed" and exit_price <= 0:
        exit_price = current or entry

    pnl_price = exit_price if status == "closed" and exit_price > 0 else current
    pnl = _safe_float(normalized.get("pnl"))
    if entry > 0 and quantity > 0 and pnl_price > 0:
        pnl = round((pnl_price - entry) * quantity, 4)

    pnl_percent = 0.0
    if entry > 0 and pnl_price > 0:
        pnl_percent = round(((pnl_price - entry) / entry) * 100, 4)

    entry_time = normalized.get("entry_time") or normalized.get("opened_at") or normalized.get("created_at") or now
    exit_time = normalized.get("exit_time") or normalized.get("closed_at")
    if status == "closed" and not exit_time:
        exit_time = now

    holding_seconds = _seconds_between(entry_time, exit_time or now)

    normalized.update({
        "entry": entry,
        "current": current,
        "quantity": quantity,
        "usdt_size": usdt_size,
        "pnl": pnl,
        "pnl_percent": pnl_percent,
        "entry_time": entry_time,
        "status": status,
        "holding_seconds": holding_seconds,
        "holding_text": _format_duration(holding_seconds),
        "entry_price_source": normalized.get("entry_price_source") or "legacy_or_scan",
        "last_price_source": normalized.get("last_price_source") or normalized.get("entry_price_source") or "legacy_or_scan",
        "entry_signal": normalized.get("entry_signal") if isinstance(normalized.get("entry_signal"), dict) else {},
        "settings_snapshot": normalized.get("settings_snapshot") if isinstance(normalized.get("settings_snapshot"), dict) else {},
        "scan_id": normalized.get("scan_id"),
        "strategy": normalized.get("strategy") or "-",
        "score": _safe_float(normalized.get("score")),
    })

    if status == "closed":
        normalized["exit"] = exit_price
        normalized["exit_time"] = exit_time
        normalized["exit_price_source"] = normalized.get("exit_price_source") or normalized.get("last_price_source") or "legacy_or_runtime"
        normalized["reason"] = normalized.get("reason") or normalized.get("close_reason") or "closed"

    return normalized


def normalize_shadow_state(data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}

    normalized = deepcopy(DEFAULT_SHADOW_STATE)
    normalized.update(data)

    settings_snapshot = normalized.get("settings") if isinstance(normalized.get("settings"), dict) else {}
    normalized["settings"] = normalize_settings(settings_snapshot) if settings_snapshot else {}
    normalized["settings_source"] = "settings_store_mirror"
    normalized.setdefault("settings_updated_at", None)

    normalized["mode"] = "shadow"
    normalized.setdefault("engine_status", "stopped")
    normalized.setdefault("bot_running", False)
    normalized["requested_running"] = bool(normalized.get("requested_running", normalized.get("bot_running", False)))
    normalized["tick_in_progress"] = bool(normalized.get("tick_in_progress", False))
    normalized["active_scan_worker"] = bool(normalized.get("active_scan_worker", False))
    normalized["scan_worker_started_at"] = normalized.get("scan_worker_started_at")
    normalized["scan_worker_deadline_at"] = normalized.get("scan_worker_deadline_at")
    normalized["scan_cancel_requested"] = bool(normalized.get("scan_cancel_requested", False))
    normalized["scan_worker_generation"] = max(0, _safe_int(normalized.get("scan_worker_generation"), 0))
    normalized["last_tick_started_at"] = normalized.get("last_tick_started_at")
    normalized["last_tick_finished_at"] = normalized.get("last_tick_finished_at")
    normalized["next_tick_not_before"] = normalized.get("next_tick_not_before")
    normalized["bot_loop_backoff_seconds"] = max(60, _safe_int(normalized.get("bot_loop_backoff_seconds"), 60))
    normalized.setdefault("bot_started_at", None)
    normalized.setdefault("bot_stopped_at", None)
    normalized.setdefault("last_tick", None)
    normalized.setdefault("last_updated_at", None)
    normalized.setdefault("last_calculation_at", None)
    normalized.setdefault("stop_reason", None)

    open_positions = normalized.get("open_positions", [])
    history = normalized.get("history", [])

    normalized["open_positions"] = [
        normalize_trade_record(position, "open")
        for position in open_positions
        if isinstance(position, dict)
    ]
    normalized["history"] = [
        normalize_trade_record(position, "closed")
        for position in history
        if isinstance(position, dict)
    ][-HISTORY_LIMIT:]

    logs = normalized.get("logs", [])
    normalized["logs"] = logs[-LOG_LIMIT:] if isinstance(logs, list) else []

    points = normalized.get("performance_points", [])
    normalized["performance_points"] = points[-PERFORMANCE_LIMIT:] if isinstance(points, list) else []

    last_scan = normalized.get("last_scan") if isinstance(normalized.get("last_scan"), dict) else {}
    scan_history = normalized.get("scan_history") if isinstance(normalized.get("scan_history"), list) else []
    latest_history_scan = scan_history[-1] if scan_history and isinstance(scan_history[-1], dict) else {}

    # Older normalization dropped the expanded scan contract from last_scan
    # while scan_history retained it. Repair only a missing pipeline from an
    # equal or newer history record; never overwrite an existing scan contract.
    last_scan_time = _parse_dt(last_scan.get("time"))
    history_scan_time = _parse_dt(latest_history_scan.get("time"))
    history_is_current = bool(
        latest_history_scan
        and latest_history_scan.get("pipeline")
        and not last_scan.get("pipeline")
        and (
            not last_scan_time
            or (
                history_scan_time
                and history_scan_time.replace(tzinfo=None) >= last_scan_time.replace(tzinfo=None)
            )
        )
    )
    if history_is_current:
        last_scan = dict(last_scan)
        for key in (
            "mode",
            "test_scan",
            "eligible_universe_count",
            "universe_total_seen",
            "universe_rejected_count",
            "universe_rejection_breakdown",
            "universe_rejection_breakdown_unique",
            "pipeline",
        ):
            if key in latest_history_scan:
                last_scan[key] = latest_history_scan.get(key)

    scan_diagnostics = last_scan.get("scan_diagnostics", {}) if isinstance(last_scan.get("scan_diagnostics", {}), dict) else {}
    filter_rejection_counts = last_scan.get("filter_rejection_counts")
    if not isinstance(filter_rejection_counts, dict):
        filter_rejection_counts = scan_diagnostics.get("filter_rejection_counts", {}) if isinstance(scan_diagnostics.get("filter_rejection_counts"), dict) else {}
    filter_rejection_counts_cumulative = last_scan.get("filter_rejection_counts_cumulative")
    if not isinstance(filter_rejection_counts_cumulative, dict):
        filter_rejection_counts_cumulative = scan_diagnostics.get("filter_rejection_counts_cumulative", {}) if isinstance(scan_diagnostics.get("filter_rejection_counts_cumulative"), dict) else {}

    volume_rejection_diagnostics = last_scan.get("volume_rejection_diagnostics")
    if not isinstance(volume_rejection_diagnostics, dict):
        volume_rejection_diagnostics = scan_diagnostics.get("volume_rejection_diagnostics", {}) if isinstance(scan_diagnostics.get("volume_rejection_diagnostics"), dict) else {}

    liquidity_rejection_diagnostics = last_scan.get("liquidity_rejection_diagnostics")
    if not isinstance(liquidity_rejection_diagnostics, dict):
        liquidity_rejection_diagnostics = scan_diagnostics.get("liquidity_rejection_diagnostics", {}) if isinstance(scan_diagnostics.get("liquidity_rejection_diagnostics"), dict) else {}

    normalized["last_scan"] = {
        "status": last_scan.get("status", "idle"),
        "live": bool(last_scan.get("live", False)),
        "source": last_scan.get("source", "binance"),
        "mode": last_scan.get("mode"),
        "test_scan": bool(last_scan.get("test_scan", False)),
        "time": last_scan.get("time"),
        "scan_id": last_scan.get("scan_id"),
        "scanned": _safe_int(last_scan.get("scanned"), 0),
        "eligible_universe_count": _safe_int(last_scan.get("eligible_universe_count"), 0),
        "universe_total_seen": _safe_int(last_scan.get("universe_total_seen"), last_scan.get("scanned", 0)),
        "universe_rejected_count": _safe_int(last_scan.get("universe_rejected_count"), 0),
        "universe_rejection_breakdown": last_scan.get("universe_rejection_breakdown", {}) if isinstance(last_scan.get("universe_rejection_breakdown", {}), dict) else {},
        "universe_rejection_breakdown_unique": last_scan.get("universe_rejection_breakdown_unique", {}) if isinstance(last_scan.get("universe_rejection_breakdown_unique", {}), dict) else {},
        "candidates_count": _safe_int(last_scan.get("candidates_count"), 0),
        "passed": _safe_int(last_scan.get("passed"), last_scan.get("candidates_count", 0)),
        "rejected_count": _safe_int(last_scan.get("rejected_count"), 0),
        "top_rejection_reason": last_scan.get("top_rejection_reason"),
        "rejection_breakdown": last_scan.get("rejection_breakdown", {}) if isinstance(last_scan.get("rejection_breakdown", {}), dict) else {},
        "rejection_summary": last_scan.get("rejection_summary") if isinstance(last_scan.get("rejection_summary"), dict) else {},
        "filter_rejection_counts": filter_rejection_counts,
        "filter_rejection_counts_cumulative": filter_rejection_counts_cumulative,
        "volume_rejection_diagnostics": volume_rejection_diagnostics,
        "liquidity_rejection_diagnostics": liquidity_rejection_diagnostics,
        "candidates": last_scan.get("candidates", []) if isinstance(last_scan.get("candidates", []), list) else [],
        "scan_rows": last_scan.get("scan_rows", []) if isinstance(last_scan.get("scan_rows", []), list) else [],
        "candidate_handoff": last_scan.get("candidate_handoff", {}) if isinstance(last_scan.get("candidate_handoff", {}), dict) else {},
        "strategy_runtime": last_scan.get("strategy_runtime", {}) if isinstance(last_scan.get("strategy_runtime", {}), dict) else {},
        "karabasan_runtime": last_scan.get("karabasan_runtime", {}) if isinstance(last_scan.get("karabasan_runtime", {}), dict) else {},
        "scan_diagnostics": scan_diagnostics,
        "scan_trace": last_scan.get("scan_trace", {}) if isinstance(last_scan.get("scan_trace", {}), dict) else {},
        "pipeline": last_scan.get("pipeline", {}) if isinstance(last_scan.get("pipeline", {}), dict) else {},
        "settings_snapshot": last_scan.get("settings_snapshot", {}) if isinstance(last_scan.get("settings_snapshot", {}), dict) else {},
        "coin_filter_settings_used": last_scan.get("coin_filter_settings_used", scan_diagnostics.get("coin_filter_settings_used", {})) if isinstance(last_scan.get("coin_filter_settings_used", scan_diagnostics.get("coin_filter_settings_used", {})), dict) else {},
        "settings_used": last_scan.get("settings_used", last_scan.get("coin_filter_settings_used", {})) if isinstance(last_scan.get("settings_used", last_scan.get("coin_filter_settings_used", {})), dict) else {},
        "settings_changed_since_scan": bool(last_scan.get("settings_changed_since_scan", False)),
        "error": last_scan.get("error")
    }
    normalized["last_scan_time"] = normalized.get("last_scan_time") or normalized["last_scan"].get("time")

    audit = normalized.get("audit", [])
    normalized["audit"] = audit[-AUDIT_LIMIT:] if isinstance(audit, list) else []

    settings_history = normalized.get("settings_history", [])
    normalized["settings_history"] = settings_history[-300:] if isinstance(settings_history, list) else []

    bot_loop_traces = normalized.get("bot_loop_traces", [])
    normalized["bot_loop_traces"] = bot_loop_traces[-250:] if isinstance(bot_loop_traces, list) else []

    # Revizyon_14: gerçek para runtime state, Paper/Shadow verisinden ayrıştırılmış şekilde
    # shadow_store içinde güvenli alt namespace olarak tutulur. Runtime dosyası Git/ZIP dışındadır.
    normalized["real_trade"] = ensure_real_trade_state(normalized)

    return normalized


def get_user_container(raw_data: dict) -> dict:
    if not isinstance(raw_data, dict):
        return {"users": {DEFAULT_USER: {}}}

    if isinstance(raw_data.get("users"), dict):
        raw_data.setdefault("users", {})
        raw_data["users"].setdefault(DEFAULT_USER, {})
        return raw_data

    return {
        "users": {
            DEFAULT_USER: raw_data
        }
    }


def canonical_settings_mirror(settings: dict) -> dict:
    """Copy an already canonical settings_store value without re-normalizing metadata."""
    if not isinstance(settings, dict):
        return normalize_settings({})
    mirrored = deepcopy(settings)
    coin_filter = mirrored.get("coin_filter")
    mirrored["coin_filter"] = {
        **DEFAULT_COIN_FILTER,
        **(coin_filter if isinstance(coin_filter, dict) else {}),
    }
    return mirrored


def sync_settings_state(data: dict, settings: dict) -> bool:
    """Mirror canonical settings_store values into shadow state for runtime diagnostics.

    The trading scanner reads settings from settings_store. Operators, dashboard
    bundle hydration and audits sometimes inspect shadow_store. This function keeps
    that runtime mirror deterministic without making shadow_store the source of
    truth.
    """
    if not isinstance(data, dict):
        return False
    normalized_settings = canonical_settings_mirror(settings)
    if data.get("settings") == normalized_settings and data.get("settings_source") == "settings_store_mirror":
        return False
    data["settings"] = normalized_settings
    data["settings_source"] = "settings_store_mirror"
    data["settings_updated_at"] = now_iso()
    return True


def build_persisted_scan_settings_contract(settings: dict) -> dict:
    """Build the stable settings subset persisted with every last_scan record."""
    canonical = canonical_settings_mirror(settings)
    coin_filter = deepcopy(canonical["coin_filter"])
    bot = canonical.get("bot") if isinstance(canonical.get("bot"), dict) else {}
    return {
        "source": "settings_store",
        "coin_filter": coin_filter,
        "coin_filter_effective": deepcopy(coin_filter),
        "bot": {
            "scan_limit": bot.get("scan_limit"),
            "scan_deep_analysis_limit": bot.get("scan_deep_analysis_limit"),
        },
    }


def ensure_last_scan_settings_contract(data: dict, settings: dict) -> bool:
    if not isinstance(data, dict):
        return False
    last_scan = data.get("last_scan")
    if not isinstance(last_scan, dict):
        return False
    canonical_snapshot = build_persisted_scan_settings_contract(settings)
    existing_snapshot = last_scan.get("settings_snapshot")
    snapshot = existing_snapshot if isinstance(existing_snapshot, dict) and existing_snapshot.get("coin_filter") else canonical_snapshot
    existing_used = last_scan.get("coin_filter_settings_used")
    if isinstance(existing_used, dict) and existing_used:
        used = existing_used
    else:
        snapshot_used = snapshot.get("coin_filter_effective") if isinstance(snapshot.get("coin_filter_effective"), dict) else snapshot.get("coin_filter")
        used = deepcopy(snapshot_used if isinstance(snapshot_used, dict) else canonical_snapshot["coin_filter_effective"])
    changed = last_scan.get("settings_snapshot") != snapshot or last_scan.get("coin_filter_settings_used") != used
    last_scan["settings_snapshot"] = deepcopy(snapshot)
    last_scan["coin_filter_settings_used"] = deepcopy(used)
    diagnostics = last_scan.get("scan_diagnostics") if isinstance(last_scan.get("scan_diagnostics"), dict) else {}
    diagnostics["coin_filter_settings_used"] = deepcopy(used)
    diagnostics["settings_source"] = "settings_store"
    last_scan["scan_diagnostics"] = diagnostics
    data["last_scan"] = last_scan
    return changed


def save_shadow_settings_snapshot(user: str, settings: dict) -> dict:
    normalized_settings = canonical_settings_mirror(settings)
    user_key = user or DEFAULT_USER
    with SHADOW_LOCK:
        raw_data = read_json_file(SHADOW_FILE, {})
        container = get_user_container(raw_data)
        user_shadow = container["users"].get(user_key)
        if not isinstance(user_shadow, dict):
            user_shadow = deepcopy(container["users"].get(DEFAULT_USER, {}))
        if not isinstance(user_shadow, dict):
            user_shadow = {}
        user_shadow["settings"] = normalized_settings
        user_shadow["settings_source"] = "settings_store_mirror"
        user_shadow["settings_updated_at"] = now_iso()
        container["users"][user_key] = normalize_shadow_state(user_shadow)
        write_json_file(SHADOW_FILE, container)
    return normalized_settings


def load_settings(user: str = DEFAULT_USER) -> dict:
    raw_data = read_json_file(SETTINGS_FILE, {})
    container = get_user_container(raw_data)

    user_key = user or DEFAULT_USER
    user_settings = container["users"].get(user_key)

    if not isinstance(user_settings, dict):
        user_settings = deepcopy(container["users"].get(DEFAULT_USER, {}))

    return normalize_settings(user_settings)


def save_settings(settings: dict, user: str = DEFAULT_USER) -> dict:
    raw_data = read_json_file(SETTINGS_FILE, {})
    container = get_user_container(raw_data)

    user_key = user or DEFAULT_USER
    container["users"][user_key] = normalize_settings(settings)

    write_json_file(SETTINGS_FILE, container)

    try:
        save_shadow_settings_snapshot(user_key, container["users"][user_key])
    except Exception:
        pass

    return container["users"][user_key]


def load_shadow(user: str = DEFAULT_USER) -> dict:
    with SHADOW_LOCK:
        raw_data = read_json_file(SHADOW_FILE, {})
        container = get_user_container(raw_data)

        user_key = user or DEFAULT_USER
        user_shadow = container["users"].get(user_key)

        if not isinstance(user_shadow, dict):
            user_shadow = deepcopy(container["users"].get(DEFAULT_USER, {}))

        normalized = normalize_shadow_state(user_shadow)
        sync_settings_state(normalized, load_settings(user_key))
        ensure_last_scan_settings_contract(normalized, normalized["settings"])
        return normalized


def save_shadow(data: dict, user: str = DEFAULT_USER) -> dict:
    with SHADOW_LOCK:
        raw_data = read_json_file(SHADOW_FILE, {})
        container = get_user_container(raw_data)

        user_key = user or DEFAULT_USER
        normalized = normalize_shadow_state(data)
        canonical_settings = load_settings(user_key)
        sync_settings_state(normalized, canonical_settings)
        ensure_last_scan_settings_contract(normalized, canonical_settings)
        container["users"][user_key] = normalized

        write_json_file(SHADOW_FILE, container)

        return container["users"][user_key]


def update_shadow_state(user: str, updater) -> dict:
    """Apply one read-check-write mutation while holding the shadow store lock."""
    with SHADOW_LOCK:
        raw_data = read_json_file(SHADOW_FILE, {})
        container = get_user_container(raw_data)
        user_key = user or DEFAULT_USER
        current = normalize_shadow_state(container["users"].get(user_key, {}))
        canonical_settings = load_settings(user_key)
        sync_settings_state(current, canonical_settings)
        updated = updater(current)
        if isinstance(updated, dict):
            current = updated
        current = normalize_shadow_state(current)
        sync_settings_state(current, canonical_settings)
        ensure_last_scan_settings_contract(current, canonical_settings)
        container["users"][user_key] = current
        write_json_file(SHADOW_FILE, container)
        return container["users"][user_key]


def _backup_dir() -> Path:
    backup_dir = SETTINGS_FILE.parent / "runtime_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def _safe_backup_user(user: str = DEFAULT_USER) -> str:
    return str(user or DEFAULT_USER).replace("/", "_").replace("\\", "_").replace("..", "_")


def archive_shadow_state(data: dict, user: str = DEFAULT_USER, reason: str = "manual") -> str:
    backup_dir = _backup_dir()
    safe_user = _safe_backup_user(user)
    safe_reason = str(reason or "manual").replace("/", "_").replace("\\", "_").replace("..", "_")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"shadow-{safe_user}-{safe_reason}-{timestamp}.json"

    payload = {
        "user": safe_user,
        "reason": safe_reason,
        "created_at": now_iso(),
        "shadow": normalize_shadow_state(data)
    }

    write_json_file(backup_path, payload)
    return str(backup_path)


def list_shadow_archives(user: str = DEFAULT_USER, limit: int = 20) -> list[dict]:
    safe_user = _safe_backup_user(user)
    files = sorted(
        _backup_dir().glob(f"shadow-{safe_user}-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True
    )

    archives = []
    for path in files[:max(1, min(int(limit or 20), 100))]:
        payload = read_json_file(path, {})
        shadow = payload.get("shadow", {}) if isinstance(payload, dict) else {}
        archives.append({
            "backup_id": path.name,
            "path": str(path),
            "created_at": payload.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            "reason": payload.get("reason", "unknown") if isinstance(payload, dict) else "unknown",
            "size_bytes": path.stat().st_size,
            "preview": {
                "bot_running": bool(shadow.get("bot_running")),
                "open_positions_count": len(shadow.get("open_positions", []) or []),
                "history_count": len(shadow.get("history", []) or []),
                "last_tick": shadow.get("last_tick"),
                "wallet_value": shadow.get("wallet_value"),
            }
        })

    return archives


def restore_shadow_archive(backup_id: str, user: str = DEFAULT_USER) -> dict:
    safe_user = _safe_backup_user(user)
    backup_name = Path(str(backup_id or "")).name

    if not backup_name.startswith(f"shadow-{safe_user}-") or not backup_name.endswith(".json"):
        raise ValueError("Geçersiz backup id.")

    backup_path = _backup_dir() / backup_name
    if not backup_path.exists():
        raise FileNotFoundError("Backup dosyası bulunamadı.")

    payload = read_json_file(backup_path, {})
    shadow = payload.get("shadow") if isinstance(payload, dict) else None
    if not isinstance(shadow, dict):
        raise ValueError("Backup içeriği geçerli değil.")

    restored = normalize_shadow_state(shadow)
    save_shadow(restored, user)
    return restored


def append_log(data: dict, level: str, message: str, event: str = "system") -> dict:
    logs = data.setdefault("logs", [])

    logs.append({
        "level": level,
        "event": event,
        "time": now_iso(),
        "message": message
    })

    data["logs"] = logs[-LOG_LIMIT:]

    return data


def _audit_category(action_text: str, meta: dict) -> str:
    category = meta.get("category")
    if category:
        return str(category)
    lowered = action_text.lower()
    if "settings" in lowered:
        return "settings"
    if "strategy" in lowered:
        return "strategy"
    if "filter" in lowered:
        return "filter"
    if "rule" in lowered:
        return "rule"
    if "risk" in lowered:
        return "risk"
    if "paper" in lowered:
        return "paper_lab"
    if "recommend" in lowered:
        return "recommendation"
    if "approval" in lowered:
        return "approval"
    if "restore" in lowered:
        return "restore"
    if "backup" in lowered:
        return "backup"
    if "user" in lowered:
        return "user"
    if "package" in lowered:
        return "package"
    if "bot" in lowered or "trade" in lowered or "model" in lowered or "emergency" in lowered:
        return "trading"
    return "security" if str(meta.get("result") or "").lower() in {"error", "blocked"} else "system"


def _audit_severity(action_text: str, result: str, category: str, meta: dict) -> str:
    explicit = meta.get("severity")
    if explicit:
        return str(explicit)
    lowered = action_text.lower()
    if str(result).lower() in {"blocked", "forbidden", "denied"}:
        return "blocked"
    if "emergency" in lowered or "real_approval" in lowered or "audit_clear" in lowered:
        return "critical"
    if "delete" in lowered or "restore" in lowered or category in {"backup", "restore"}:
        return "warning"
    if category in {"settings", "rule", "strategy", "filter", "risk", "user", "package"}:
        return "notice"
    return "info"


def append_audit(data: dict, action: str, result: str = "ok", message: str = "", meta: dict | None = None, user: str | None = None) -> dict:
    if not isinstance(data, dict):
        data = {}
    items = data.setdefault("audit", [])
    meta = meta if isinstance(meta, dict) else {}
    action_text = str(action or "unknown")
    result_text = str(result or "ok")
    category = _audit_category(action_text, {**meta, "result": result_text})
    severity = _audit_severity(action_text, result_text, category, meta)
    request_id = str(meta.get("request_id") or uuid4())
    item = {
        "time": now_iso(),
        "created_at": now_iso(),
        "user": user or data.get("user") or DEFAULT_USER,
        "role": meta.get("role") or data.get("role") or "user",
        "action": action_text,
        "category": category,
        "severity": severity,
        "page": meta.get("page"),
        "endpoint": meta.get("endpoint"),
        "result": result_text,
        "message": str(message or ""),
        "before": meta.get("before"),
        "after": meta.get("after"),
        "risk_level": meta.get("risk_level"),
        "subject": meta.get("subject") or meta.get("model_id") or meta.get("rule_id") or meta.get("symbol"),
        "request_id": request_id,
        "correlation_id": str(meta.get("correlation_id") or request_id),
        "ip": meta.get("ip"),
        "user_agent": meta.get("user_agent"),
        "meta": meta,
    }
    items.append(item)
    data["audit"] = items[-AUDIT_LIMIT:]
    return item

def get_audit(data: dict, limit: int = 200) -> list[dict]:
    if not isinstance(data, dict):
        return []
    try:
        limit = max(1, min(int(limit), AUDIT_LIMIT))
    except Exception:
        limit = 200
    return list(data.get("audit", []) or [])[-limit:]


def clear_audit(data: dict) -> int:
    if not isinstance(data, dict):
        return 0
    count = len(data.get("audit", []) or [])
    data["audit"] = []
    return count
