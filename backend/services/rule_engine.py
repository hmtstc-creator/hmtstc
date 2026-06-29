import json
import re
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.config import BASE_DIR
from core.storage import now_iso
from services.paper_lab_store import (
    build_paper_lab_status,
    paper_lab_rules_fingerprint,
    record_paper_lab_run,
)


RULE_STORE_FILE = BASE_DIR / "rule_store.json"
RULE_STORE_EXAMPLE_FILE = BASE_DIR / "rule_store.example.json"
RUNTIME_BACKUPS_DIR = BASE_DIR / "runtime_backups"
OWNER_RULE_USERNAME = "ahmet"
_RULE_STORE_STATUS_CACHE = {"at": 0.0, "payload": None}
_RULE_STORE_STATUS_CACHE_SECONDS = 300


VALID_RULE_TYPES = {"filter", "strategy"}
VALID_OPERATORS = {
    ">", ">=", "<", "<=", "==", "!=", "between", "in", "not_in", "exists", "truthy", "falsy"
}
VALID_TIMEFRAMES = {None, "", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "market", "signal"}
VALID_RISK_LEVELS = {"low", "medium", "high"}
VALID_STRATEGY_TYPES = {
    "trend", "pullback", "breakout", "momentum", "mean_reversion", "scalping", "custom"
}

SUPPORTED_METRICS = {
    "symbol", "price", "open", "high", "low", "close", "volume", "quote_volume", "volume_today",
    "trade_count", "spread", "spread_percent", "atr", "atr_percent", "volatility",
    "rsi", "rsi_15m", "rsi_1h", "rsi_4h", "ema_signal", "macd_signal", "volume_growth",
    "ema_9", "ema_20", "ema_50", "ema_100", "ema_200", "price_above_ema", "ema_alignment",
    "macd", "macd_signal_value", "macd_histogram", "volume_sma",
    "price_change_15m", "price_change_1h", "price_change_4h", "price_change_24h",
    "trend_direction", "trend_strength", "higher_high", "higher_low", "breakout_level",
    "pullback_distance", "momentum_score", "btc_trend", "btc_rsi", "btc_volatility",
    "eth_trend", "market_mode", "market_risk", "score", "filter_score", "liquidity_score",
    "volatility_score", "momentum_score", "trend_score", "spread_score", "data_quality_score",
    "volume_ratio", "market_confidence_score",
}


def _default_store() -> dict:
    return {
        "version": 1,
        "users": {},
    }


def _store_username(username: str | None) -> str:
    clean = str(username or "").strip()
    if clean.lower() == OWNER_RULE_USERNAME:
        return OWNER_RULE_USERNAME
    return clean


def _safe_load(path: Path, default_value: Any) -> Any:
    if not path.exists():
        if RULE_STORE_EXAMPLE_FILE.exists() and path == RULE_STORE_FILE:
            try:
                return json.loads(RULE_STORE_EXAMPLE_FILE.read_text(encoding="utf-8"))
            except Exception:
                return deepcopy(default_value)
        return deepcopy(default_value)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default_value)


def _safe_write(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load_rule_store() -> dict:
    store = _safe_load(RULE_STORE_FILE, _default_store())
    if not isinstance(store, dict):
        store = _default_store()
    store.setdefault("version", 1)
    store.setdefault("users", {})
    users = store.setdefault("users", {})
    for user_key in list(users.keys()):
        if str(user_key).strip().lower() == OWNER_RULE_USERNAME and user_key != OWNER_RULE_USERNAME:
            if OWNER_RULE_USERNAME not in users:
                users[OWNER_RULE_USERNAME] = users.pop(user_key)
            else:
                legacy_state = users.pop(user_key)
                if isinstance(legacy_state, dict):
                    owner_state = users.setdefault(OWNER_RULE_USERNAME, {})
                    if not owner_state.get("rules") and legacy_state.get("rules"):
                        owner_state["rules"] = legacy_state.get("rules")
                    if not owner_state.get("versions") and legacy_state.get("versions"):
                        owner_state["versions"] = legacy_state.get("versions")
    return store


def _count_rules_in_store_payload(store: Any) -> dict:
    users = store.get("users") if isinstance(store, dict) else {}
    total = 0
    filters = 0
    strategies = 0
    if isinstance(users, dict):
        for state in users.values():
            rules = state.get("rules") if isinstance(state, dict) else []
            if not isinstance(rules, list):
                continue
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                total += 1
                if rule.get("type") == "filter":
                    filters += 1
                elif rule.get("type") == "strategy":
                    strategies += 1
    return {"total": total, "filters": filters, "strategies": strategies}


def build_rule_store_status(username: str | None = None, *, deep: bool = False) -> dict:
    """Return rule-store health without expensive backup crawling by default.

    Dashboard bundle calls this function often. The previous implementation
    recursively scanned runtime_backups on every read, which can keep uvicorn
    worker threads hot. Deep backup inspection remains available only when
    explicitly requested by admin/debug flows.
    """
    store = load_rule_store()
    active_counts = _count_rules_in_store_payload(store)
    backup_best = {"path": None, "total": 0, "filters": 0, "strategies": 0}

    if deep:
        now = time.monotonic()
        cached = _RULE_STORE_STATUS_CACHE.get("payload")
        if cached and now - float(_RULE_STORE_STATUS_CACHE.get("at") or 0) < _RULE_STORE_STATUS_CACHE_SECONDS:
            payload = deepcopy(cached)
            payload["user"] = username
            return payload

        if RUNTIME_BACKUPS_DIR.exists():
            for path in RUNTIME_BACKUPS_DIR.rglob("*.json"):
                if "rule_store" not in path.name:
                    continue
                try:
                    counts = _count_rules_in_store_payload(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    continue
                if counts["total"] > backup_best["total"]:
                    backup_best = {
                        "path": str(path.relative_to(BASE_DIR)),
                        "total": counts["total"],
                        "filters": counts["filters"],
                        "strategies": counts["strategies"],
                    }

    empty_active_backup_available = bool(deep and active_counts["total"] == 0 and backup_best["total"] > 0)
    payload = {
        "status": "warning" if empty_active_backup_available or active_counts["total"] == 0 else "ok",
        "user": username,
        "file": "backend/rule_store.json",
        "active_total_rules": active_counts["total"],
        "active_filter_count": active_counts["filters"],
        "active_strategy_count": active_counts["strategies"],
        "backup_max_rule_count": backup_best["total"],
        "backup_max_filter_count": backup_best["filters"],
        "backup_max_strategy_count": backup_best["strategies"],
        "backup_candidate": backup_best["path"],
        "empty_active_backup_available": empty_active_backup_available,
        "backup_scan_deep": bool(deep),
        "message": "Aktif rule_store boş, yedekte kayıt bulundu." if empty_active_backup_available else "",
    }
    if deep:
        _RULE_STORE_STATUS_CACHE["at"] = time.monotonic()
        _RULE_STORE_STATUS_CACHE["payload"] = deepcopy(payload)
    return payload


def save_rule_store(store: dict):
    if not isinstance(store, dict):
        store = _default_store()
    store.setdefault("version", 1)
    store.setdefault("users", {})
    _safe_write(RULE_STORE_FILE, store)


def get_user_rule_state(username: str) -> dict:
    username = _store_username(username)
    store = load_rule_store()
    users = store.setdefault("users", {})
    user_state = users.setdefault(username, {})
    user_state.setdefault("rules", [])
    user_state.setdefault("activation_log", [])
    user_state.setdefault("versions", {})
    user_state.setdefault("selected_filter_ids", [])
    user_state.setdefault("selected_strategy_ids", [])
    user_state.setdefault("last_activation_at", None)
    return user_state


def persist_user_rule_state(username: str, user_state: dict):
    username = _store_username(username)
    store = load_rule_store()
    store.setdefault("users", {})[username] = user_state
    save_rule_store(store)


def _catalog_username(username: str | None = None) -> str:
    return OWNER_RULE_USERNAME


def _catalog_rule_state() -> dict:
    return get_user_rule_state(_catalog_username())


def _slug(value: str, fallback: str = "RULE") -> str:
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").strip().upper()).strip("_")
    return clean or fallback


def make_rule_id(rule_type: str, name: str) -> str:
    prefix = "FILTER" if rule_type == "filter" else "STRATEGY"
    return f"USER_{prefix}_{_slug(name, prefix)}"


def default_rule(rule_type: str = "filter") -> dict:
    if rule_type == "strategy":
        return {
            "id": make_rule_id("strategy", "New Strategy"),
            "type": "strategy",
            "name": "New Strategy",
            "description": "Güvenli HMTSTC Rule JSON strateji tanımı.",
            "enabled": True,
            "version": 1,
            "strategy_type": "momentum",
            "risk_level": "medium",
            "required_metrics": ["rsi", "ema_signal", "macd_signal", "volume_growth"],
            "conditions": [
                {"metric": "ema_signal", "operator": "==", "value": True},
                {"metric": "macd_signal", "operator": "==", "value": True},
                {"metric": "rsi", "operator": "between", "value": [50, 75], "timeframe": "15m"},
            ],
            "avoid_conditions": [],
            "entry_rules": [],
            "exit_rules": [],
            "metadata": {"source": "user_rule_editor"},
        }

    return {
        "id": make_rule_id("filter", "New Filter"),
        "type": "filter",
        "name": "New Filter",
        "description": "Güvenli HMTSTC Rule JSON filtre tanımı.",
        "enabled": True,
        "version": 1,
        "min_score": 65,
        "risk_level": "medium",
        "compatible_strategy_types": ["trend", "pullback", "momentum"],
        "required_metrics": ["quote_volume", "volatility", "rsi", "ema_signal"],
        "conditions": [
            {"metric": "quote_volume", "operator": ">=", "value": 5000000},
            {"metric": "volatility", "operator": ">=", "value": 0.4, "timeframe": "15m"},
            {"metric": "rsi", "operator": "between", "value": [40, 75], "timeframe": "15m"},
        ],
        "avoid_conditions": [
            {"metric": "spread_percent", "operator": ">", "value": 0.35},
        ],
        "score_rules": [],
        "metadata": {"source": "user_rule_editor"},
    }


def example_rules() -> dict:
    return {
        "filter": default_rule("filter"),
        "strategy": default_rule("strategy"),
        "notes": [
            "Bu format gerçek Python/JS kodu değildir; HMTSTC güvenli Rule JSON formatıdır.",
            "metric/operator/value alanları validation katmanından geçmeden Paper Lab'e alınmaz.",
        ],
    }


def _validate_condition(condition: dict, path: str) -> list[dict]:
    errors = []
    if not isinstance(condition, dict):
        return [{"path": path, "message": "Condition object olmalı."}]

    metric = condition.get("metric")
    operator = condition.get("operator")
    timeframe = condition.get("timeframe")

    if metric not in SUPPORTED_METRICS:
        errors.append({"path": f"{path}.metric", "message": f"Desteklenmeyen metric: {metric}"})
    if operator not in VALID_OPERATORS:
        errors.append({"path": f"{path}.operator", "message": f"Desteklenmeyen operator: {operator}"})
    if timeframe not in VALID_TIMEFRAMES:
        errors.append({"path": f"{path}.timeframe", "message": f"Desteklenmeyen timeframe: {timeframe}"})

    if operator == "between":
        value = condition.get("value")
        if not isinstance(value, list) or len(value) != 2:
            errors.append({"path": f"{path}.value", "message": "between operator için value iki elemanlı liste olmalı."})
    elif operator in {"in", "not_in"}:
        if not isinstance(condition.get("value"), list):
            errors.append({"path": f"{path}.value", "message": "in/not_in operator için value liste olmalı."})
    elif operator not in {"exists", "truthy", "falsy"} and "value" not in condition:
        errors.append({"path": f"{path}.value", "message": "Bu operator için value gerekli."})

    return errors


def validate_rule(rule: dict) -> dict:
    errors = []
    warnings = []

    if not isinstance(rule, dict):
        return {"valid": False, "errors": [{"path": "$", "message": "Rule JSON object olmalı."}], "warnings": []}

    rule_type = rule.get("type")
    if rule_type not in VALID_RULE_TYPES:
        errors.append({"path": "type", "message": "type filter veya strategy olmalı."})

    name = str(rule.get("name") or "").strip()
    if not name:
        errors.append({"path": "name", "message": "name zorunlu."})

    if not rule.get("id"):
        warnings.append({"path": "id", "message": "id boşsa kayıtta otomatik üretilecek."})

    try:
        version = int(rule.get("version", 1))
        if version < 1:
            errors.append({"path": "version", "message": "version 1 veya daha büyük olmalı."})
    except Exception:
        errors.append({"path": "version", "message": "version sayı olmalı."})

    risk_level = rule.get("risk_level", "medium")
    if risk_level not in VALID_RISK_LEVELS:
        errors.append({"path": "risk_level", "message": "risk_level low/medium/high olmalı."})

    if rule_type == "filter":
        try:
            min_score = float(rule.get("min_score", 65))
            if min_score < 0 or min_score > 100:
                errors.append({"path": "min_score", "message": "min_score 0-100 aralığında olmalı."})
        except Exception:
            errors.append({"path": "min_score", "message": "min_score sayı olmalı."})

        compatible = rule.get("compatible_strategy_types", [])
        if not isinstance(compatible, list) or not compatible:
            warnings.append({"path": "compatible_strategy_types", "message": "Uyumlu strateji tipleri boş; analyzer daha kısıtlı çalışır."})
        else:
            for item in compatible:
                if item not in VALID_STRATEGY_TYPES:
                    errors.append({"path": "compatible_strategy_types", "message": f"Desteklenmeyen strategy type: {item}"})

    if rule_type == "strategy":
        strategy_type = rule.get("strategy_type", "custom")
        if strategy_type not in VALID_STRATEGY_TYPES:
            errors.append({"path": "strategy_type", "message": "Desteklenmeyen strategy_type."})

    for section in ["conditions", "avoid_conditions", "score_rules", "entry_rules", "exit_rules"]:
        items = rule.get(section, [])
        if items is None:
            continue
        if not isinstance(items, list):
            errors.append({"path": section, "message": "Liste olmalı."})
            continue
        for index, condition in enumerate(items):
            errors.extend(_validate_condition(condition, f"{section}[{index}]"))

    if not rule.get("conditions") and rule_type in VALID_RULE_TYPES:
        warnings.append({"path": "conditions", "message": "conditions boş; rule çok gevşek çalışabilir."})

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def normalize_rule(rule: dict) -> dict:
    clean = deepcopy(rule or {})
    rule_type = clean.get("type") if clean.get("type") in VALID_RULE_TYPES else "filter"
    clean["type"] = rule_type
    clean["name"] = str(clean.get("name") or "Unnamed Rule").strip()
    clean["id"] = _slug(clean.get("id") or make_rule_id(rule_type, clean["name"]), make_rule_id(rule_type, clean["name"]))
    if not clean["id"].startswith("USER_"):
        clean["id"] = "USER_" + clean["id"]
    clean["enabled"] = bool(clean.get("enabled", True))
    clean["version"] = int(clean.get("version") or 1)
    clean.setdefault("description", "")
    clean.setdefault("risk_level", "medium")
    clean.setdefault("required_metrics", [])
    clean.setdefault("conditions", [])
    clean.setdefault("avoid_conditions", [])
    clean.setdefault("metadata", {})
    clean["updated_at"] = now_iso()
    clean.setdefault("created_at", clean["updated_at"])

    if rule_type == "filter":
        clean.setdefault("min_score", 65)
        clean.setdefault("compatible_strategy_types", ["trend", "pullback", "momentum"])
        clean.setdefault("score_rules", [])
    else:
        clean.setdefault("strategy_type", "custom")
        clean.setdefault("entry_rules", [])
        clean.setdefault("exit_rules", [])

    validation = validate_rule(clean)
    if not validation["valid"]:
        raise ValueError(json.dumps(validation["errors"], ensure_ascii=False))
    return clean


def list_rules(username: str, *, include_store_status: bool = True) -> dict:
    user_state = get_user_rule_state(username)
    catalog_state = _catalog_rule_state()
    rules = catalog_state.get("rules", []) or []
    filters = [item for item in rules if item.get("type") == "filter"]
    strategies = [item for item in rules if item.get("type") == "strategy"]
    return {
        "status": "ok",
        "catalog_owner": _catalog_username(username),
        "user": username,
        "rules": rules,
        "filters": filters,
        "strategies": strategies,
        "selected_filter_ids": user_state.get("selected_filter_ids", []),
        "selected_strategy_ids": user_state.get("selected_strategy_ids", []),
        "activation_log": (user_state.get("activation_log", []) or [])[-100:],
        "last_activation_at": user_state.get("last_activation_at"),
        "rule_store_status": build_rule_store_status(username, deep=False) if include_store_status else {"status": "skipped", "user": username, "backup_scan_deep": False},
    }


def _enabled_rule_ids(rules: list[dict], rule_type: str) -> list[str]:
    return [
        str(item.get("id"))
        for item in rules
        if item.get("type") == rule_type and item.get("enabled", True) and item.get("id")
    ]


def _clean_rule_selection(requested_ids, enabled_ids: list[str], label: str) -> list[str]:
    if not isinstance(requested_ids, list):
        raise ValueError(f"{label} secimi list olmalidir.")

    enabled_set = set(enabled_ids)
    clean = []
    for raw_id in requested_ids:
        item_id = str(raw_id or "").strip()
        if not item_id:
            continue
        if item_id not in enabled_set:
            raise ValueError(f"Secilen {label} bulunamadi: {item_id}")
        if item_id not in clean:
            clean.append(item_id)
    return clean


def save_rule_selection(username: str, selected_filter_ids: list[str], selected_strategy_ids: list[str]) -> dict:
    user_state = get_user_rule_state(username)
    all_rules = list_rules(username)
    rules = all_rules.get("rules", []) or []
    filter_ids = _enabled_rule_ids(rules, "filter")
    strategy_ids = _enabled_rule_ids(rules, "strategy")

    final_filter_ids = _clean_rule_selection(selected_filter_ids, filter_ids, "filtre")
    final_strategy_ids = _clean_rule_selection(selected_strategy_ids, strategy_ids, "strateji")

    user_state["selected_filter_ids"] = final_filter_ids
    user_state["selected_strategy_ids"] = final_strategy_ids
    user_state["last_selection_saved_at"] = now_iso()
    persist_user_rule_state(username, user_state)

    return {
        "status": "ok",
        "mode": "dashboard_active_selection",
        "selected_filter_ids": final_filter_ids,
        "selected_strategy_ids": final_strategy_ids,
        "saved_at": user_state["last_selection_saved_at"],
    }


def get_rule(username: str, rule_id: str) -> dict | None:
    clean_id = str(rule_id or "").strip()
    if not clean_id:
        return None
    for rule in list_rules(username).get("rules", []) or []:
        if str(rule.get("id") or "") == clean_id:
            return deepcopy(rule)
    return None


def save_rule(username: str, rule: dict) -> dict:
    clean = normalize_rule(rule)
    user_state = get_user_rule_state(username)
    rules = user_state.setdefault("rules", [])
    versions = user_state.setdefault("versions", {})
    replaced = False
    previous = None
    for index, existing in enumerate(rules):
        if existing.get("id") == clean.get("id"):
            previous = deepcopy(existing)
            clean.setdefault("created_at", existing.get("created_at") or now_iso())
            try:
                clean["version"] = max(int(existing.get("version") or 1) + 1, int(clean.get("version") or 1))
            except Exception:
                clean["version"] = int(existing.get("version") or 1) + 1
            rules[index] = clean
            replaced = True
            break
    if previous:
        history = versions.setdefault(clean["id"], [])
        previous["archived_at"] = now_iso()
        history.append(previous)
        versions[clean["id"]] = history[-25:]
    if not replaced:
        rules.append(clean)
    user_state["rules"] = rules
    user_state["versions"] = versions
    persist_user_rule_state(username, user_state)
    return {"status": "ok", "saved": clean, "created": not replaced, "previous_version_saved": bool(previous), "previous": previous}


def get_rule_versions(username: str, rule_id: str) -> dict:
    user_state = get_user_rule_state(username)
    versions = user_state.get("versions", {}).get(rule_id, [])
    current = next((item for item in user_state.get("rules", []) if item.get("id") == rule_id), None)
    return {"status": "ok", "rule_id": rule_id, "current": current, "versions": versions[-25:]}



def restore_rule_version(username: str, rule_id: str, archived_at: str | None = None, version: int | None = None) -> dict:
    user_state = get_user_rule_state(username)
    versions = user_state.setdefault("versions", {}).setdefault(rule_id, [])
    current = next((item for item in user_state.get("rules", []) if item.get("id") == rule_id), None)
    if not versions:
        raise ValueError("Bu rule için restore edilecek versiyon bulunamadı.")
    selected = None
    if archived_at:
        selected = next((item for item in versions if item.get("archived_at") == archived_at), None)
    if selected is None and version is not None:
        selected = next((item for item in reversed(versions) if int(item.get("version") or 0) == int(version)), None)
    if selected is None:
        selected = versions[-1]
    restored = deepcopy(selected)
    restored["restored_at"] = now_iso()
    restored["version"] = int((current or {}).get("version") or restored.get("version") or 1) + 1
    if current:
        archived_current = deepcopy(current)
        archived_current["archived_at"] = now_iso()
        versions.append(archived_current)
    rules = user_state.setdefault("rules", [])
    replaced = False
    for idx, item in enumerate(rules):
        if item.get("id") == rule_id:
            rules[idx] = restored
            replaced = True
            break
    if not replaced:
        rules.append(restored)
    user_state["versions"][rule_id] = versions[-25:]
    persist_user_rule_state(username, user_state)
    return {"status": "ok", "restored": restored, "previous_current_saved": bool(current)}


def export_rules(username: str) -> dict:
    payload = list_rules(username)
    return {"status": "ok", "exported_at": now_iso(), "rules": payload.get("rules", [])}


def import_rules(username: str, payload: dict, overwrite: bool = False) -> dict:
    incoming = payload.get("rules") if isinstance(payload, dict) else None
    if isinstance(payload, list):
        incoming = payload
    if not isinstance(incoming, list):
        raise ValueError("Import payload rules listesi içermeli.")
    user_state = get_user_rule_state(username)
    existing_ids = {item.get("id") for item in user_state.get("rules", [])}
    created = 0
    updated = 0
    imported = []
    for raw in incoming:
        clean = normalize_rule(raw)
        if clean.get("id") in existing_ids and not overwrite:
            clean["id"] = make_rule_id(clean.get("type"), f"{clean.get('name')} Import")
        result = save_rule(username, clean)
        imported.append(result.get("saved"))
        if result.get("created"):
            created += 1
        else:
            updated += 1
    return {"status": "ok", "created": created, "updated": updated, "rules": imported}


def delete_rule(username: str, rule_id: str) -> dict:
    user_state = get_user_rule_state(username)
    before = len(user_state.get("rules", []) or [])
    user_state["rules"] = [item for item in user_state.get("rules", []) if item.get("id") != rule_id]
    user_state["selected_filter_ids"] = [item for item in user_state.get("selected_filter_ids", []) if item != rule_id]
    user_state["selected_strategy_ids"] = [item for item in user_state.get("selected_strategy_ids", []) if item != rule_id]
    persist_user_rule_state(username, user_state)
    store = load_rule_store()
    for user_key, state in (store.get("users") or {}).items():
        if user_key == username or not isinstance(state, dict):
            continue
        state["selected_filter_ids"] = [item for item in state.get("selected_filter_ids", []) if item != rule_id]
        state["selected_strategy_ids"] = [item for item in state.get("selected_strategy_ids", []) if item != rule_id]
    save_rule_store(store)
    return {"status": "ok", "deleted": before - len(user_state["rules"])}


def _to_float(value, fallback=None):
    try:
        return float(value)
    except Exception:
        return fallback


def _metric_value(candidate: dict, metric: str):
    if metric in candidate:
        return candidate.get(metric)
    aliases = {
        "quote_volume": ["quoteVolume", "volume_today"],
        "price": ["close", "current", "entry"],
        "rsi": ["rsi_15m", "rsi_1h", "rsi_4h"],
        "price_above_ema": ["ema_signal"],
        "volume_ratio": ["volume_growth", "volumeGrowth"],
        "market_confidence_score": ["market_risk", "score"],
    }
    for alias in aliases.get(metric, []):
        if alias in candidate:
            return candidate.get(alias)
    return None


def _compare(actual, operator: str, expected):
    if operator == "exists":
        return actual is not None
    if operator == "truthy":
        return bool(actual)
    if operator == "falsy":
        return not bool(actual)
    if operator == "between":
        low, high = expected
        number = _to_float(actual)
        return number is not None and float(low) <= number <= float(high)
    if operator in {"in", "not_in"}:
        result = actual in expected
        return not result if operator == "not_in" else result

    left = _to_float(actual, actual)
    right = _to_float(expected, expected)
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    return False


def evaluate_rule(rule: dict, candidate: dict) -> dict:
    validation = validate_rule(rule)
    if not validation["valid"]:
        return {"passed": False, "reason": "rule_invalid", "validation": validation}

    failed = []
    for condition in rule.get("conditions", []) or []:
        metric = condition.get("metric")
        actual = _metric_value(candidate, metric)
        if not _compare(actual, condition.get("operator"), condition.get("value")):
            failed.append({"metric": metric, "reason": "condition_failed", "actual": actual, "expected": condition.get("value")})

    avoided = []
    for condition in rule.get("avoid_conditions", []) or []:
        metric = condition.get("metric")
        actual = _metric_value(candidate, metric)
        if _compare(actual, condition.get("operator"), condition.get("value")):
            avoided.append({"metric": metric, "reason": "avoid_condition_matched", "actual": actual, "expected": condition.get("value")})

    passed = not failed and not avoided
    reason = None
    if failed:
        reason = "conditions_not_met"
    if avoided:
        reason = "avoid_condition_matched"

    base_score = float(candidate.get("score") or 0)
    return {
        "passed": passed,
        "reason": reason,
        "failed": failed,
        "avoided": avoided,
        "rule_id": rule.get("id"),
        "rule_type": rule.get("type"),
        "score": round(base_score, 2),
    }


def analyze_compatibility(filter_rule: dict, strategy_rule: dict) -> dict:
    filter_validation = validate_rule(filter_rule)
    strategy_validation = validate_rule(strategy_rule)
    reasons = []
    warnings = []

    if not filter_validation["valid"]:
        reasons.append("filter_rule_invalid")
    if not strategy_validation["valid"]:
        reasons.append("strategy_rule_invalid")

    if filter_rule.get("type") != "filter":
        reasons.append("first_rule_not_filter")
    if strategy_rule.get("type") != "strategy":
        reasons.append("second_rule_not_strategy")

    strategy_type = strategy_rule.get("strategy_type", "custom")
    compatible_types = filter_rule.get("compatible_strategy_types", []) or []
    if compatible_types and strategy_type not in compatible_types and "custom" not in compatible_types:
        reasons.append("strategy_type_not_allowed_by_filter")

    filter_risk = filter_rule.get("risk_level", "medium")
    strategy_risk = strategy_rule.get("risk_level", "medium")
    if filter_risk == "low" and strategy_risk == "high":
        warnings.append("low_risk_filter_with_high_risk_strategy")

    filter_metrics = set(filter_rule.get("required_metrics", []) or [])
    strategy_metrics = set(strategy_rule.get("required_metrics", []) or [])
    unsupported = [m for m in sorted(filter_metrics | strategy_metrics) if m not in SUPPORTED_METRICS]
    if unsupported:
        reasons.append("unsupported_required_metrics")

    level = "primary"
    if warnings:
        level = "secondary"
    if reasons:
        level = "disabled"

    return {
        "accepted": len(reasons) == 0,
        "compatibility": level,
        "filter_id": filter_rule.get("id"),
        "strategy_id": strategy_rule.get("id"),
        "strategy_type": strategy_type,
        "reasons": reasons,
        "warnings": warnings,
    }


def get_active_rules(username: str) -> tuple[list[dict], list[dict]]:
    data = list_rules(username)
    selected_filters = set(data.get("selected_filter_ids", []) or [])
    selected_strategies = set(data.get("selected_strategy_ids", []) or [])

    filters = [item for item in data.get("filters", []) if item.get("enabled", True)]
    strategies = [item for item in data.get("strategies", []) if item.get("enabled", True)]

    filters = [item for item in filters if item.get("id") in selected_filters]
    strategies = [item for item in strategies if item.get("id") in selected_strategies]

    return filters, strategies


def get_enabled_rules(username: str) -> tuple[list[dict], list[dict]]:
    data = list_rules(username)
    filters = [item for item in data.get("filters", []) if item.get("enabled", True)]
    strategies = [item for item in data.get("strategies", []) if item.get("enabled", True)]
    return filters, strategies


def build_custom_models(username: str, *, use_active_selection: bool = False) -> tuple[list[dict], list[dict]]:
    filters, strategies = get_active_rules(username) if use_active_selection else get_enabled_rules(username)
    accepted = []
    logs = []

    for filter_rule in filters:
        for strategy_rule in strategies:
            analysis = analyze_compatibility(filter_rule, strategy_rule)

            log_item = {
                "time": now_iso(),
                "filter_id": filter_rule.get("id"),
                "strategy_id": strategy_rule.get("id"),
                "accepted": analysis["accepted"],
                "compatibility": analysis["compatibility"],
                "reasons": analysis["reasons"],
                "warnings": analysis["warnings"],
            }

            logs.append(log_item)

            if not analysis["accepted"]:
                continue

            model_id = f"{filter_rule.get('id')}__{strategy_rule.get('id')}"

            accepted.append({
                "model_id": model_id,
                "filter_id": filter_rule.get("id"),
                "filter_name": filter_rule.get("name"),
                "strategy_id": strategy_rule.get("id"),
                "strategy_name": strategy_rule.get("name"),
                "strategy_type": strategy_rule.get("strategy_type", "custom"),
                "compatibility": analysis["compatibility"],

                "wallet_start": 1000,
                "slot_size": 200,
                "max_slots": 5,
                "max_open_positions": 5,
                "take_profit_percent": 1.5,
                "stop_loss_percent": 2.0,

                "status": "active",
                "source": "user_rule",
                "filter_rule": deepcopy(filter_rule),
                "strategy_rule": deepcopy(strategy_rule),
            })

    return accepted, logs


def build_persistent_paper_lab_status(username: str) -> dict:
    filters, strategies = get_enabled_rules(username)
    filter_ids = [str(item.get("id")) for item in filters if item.get("id")]
    strategy_ids = [str(item.get("id")) for item in strategies if item.get("id")]
    return build_paper_lab_status(username, current_filter_ids=filter_ids, current_strategy_ids=strategy_ids)


def activate_paper_lab_rules(username: str, trigger: str = "manual") -> dict:
    started_at = now_iso()
    run_id = str(uuid4())
    final_filter_ids: list[str] = []
    final_strategy_ids: list[str] = []
    rules_fingerprint = paper_lab_rules_fingerprint(final_filter_ids, final_strategy_ids)

    try:
        user_state = get_user_rule_state(username)

        all_rules = list_rules(username)
        enabled_filter_ids = _enabled_rule_ids(all_rules.get("rules", []) or [], "filter")
        enabled_strategy_ids = _enabled_rule_ids(all_rules.get("rules", []) or [], "strategy")

        final_filter_ids = enabled_filter_ids
        final_strategy_ids = enabled_strategy_ids
        rules_fingerprint = paper_lab_rules_fingerprint(final_filter_ids, final_strategy_ids)

        if not final_filter_ids:
            raise ValueError("Paper Lab için en az 1 filtre seçilmelidir.")

        if not final_strategy_ids:
            raise ValueError("Paper Lab için en az 1 strateji seçilmelidir.")

        models, logs = build_custom_models(username)
        completed_at = now_iso()

        accepted_count = len([item for item in logs if item.get("accepted")])
        rejected_count = len([item for item in logs if not item.get("accepted")])
        candidate_count = len(final_filter_ids) * len(final_strategy_ids)
        persistent_run = record_paper_lab_run(username, {
            "run_id": run_id,
            "status": "completed",
            "started_at": started_at,
            "completed_at": completed_at,
            "filter_ids": final_filter_ids,
            "strategy_ids": final_strategy_ids,
            "filter_count": len(final_filter_ids),
            "strategy_count": len(final_strategy_ids),
            "candidate_count": candidate_count,
            "accepted_combinations": accepted_count,
            "rejected_combinations": rejected_count,
            "model_count": len(models),
            "trigger": trigger,
            "source": "all_enabled_rules",
            "rules_fingerprint": rules_fingerprint,
            "error_message": "",
            "results": [],
        })

        user_state = get_user_rule_state(username)

        activation_item = {
            "id": run_id,
            "time": completed_at,
            "mode": "paper_lab_independent",
            "paper_lab_filter_ids": final_filter_ids,
            "paper_lab_strategy_ids": final_strategy_ids,
            "paper_lab_candidate_count": candidate_count,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "model_count": len(models),
            "rules_fingerprint": rules_fingerprint,
            "logs": logs[-200:],
        }

        activation_log = user_state.setdefault("activation_log", [])
        activation_log.append(activation_item)

        user_state["activation_log"] = activation_log[-50:]
        user_state["last_activation_at"] = activation_item["time"]

        persist_user_rule_state(username, user_state)

        return {
            "status": "ok",
            "mode": activation_item["mode"],
            "paper_lab_filter_ids": final_filter_ids,
            "paper_lab_strategy_ids": final_strategy_ids,
            "paper_lab_candidate_count": activation_item["paper_lab_candidate_count"],
            "run_id": activation_item["id"],
            "started_at": started_at,
            "completed_at": activation_item["time"],
            "accepted_combinations": activation_item["accepted_count"],
            "rejected_combinations": activation_item["rejected_count"],
            "model_count": activation_item["model_count"],
            "rules_fingerprint": rules_fingerprint,
            "last_run": persistent_run,
            "paper_lab_status": build_persistent_paper_lab_status(username),
            "models": models,
            "activation": activation_item,
        }
    except Exception as error:
        completed_at = now_iso()
        error_message = str(error or "").strip()[:240]
        record_paper_lab_run(username, {
            "run_id": run_id,
            "status": "failed",
            "started_at": started_at,
            "completed_at": completed_at,
            "filter_ids": final_filter_ids,
            "strategy_ids": final_strategy_ids,
            "filter_count": len(final_filter_ids),
            "strategy_count": len(final_strategy_ids),
            "candidate_count": len(final_filter_ids) * len(final_strategy_ids),
            "accepted_combinations": 0,
            "rejected_combinations": 0,
            "model_count": 0,
            "trigger": trigger,
            "source": "all_enabled_rules",
            "rules_fingerprint": rules_fingerprint,
            "error_message": error_message,
            "results": [],
        })
        raise
