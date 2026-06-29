from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.storage import append_audit, load_settings, load_shadow, now_iso, save_settings, save_shadow

DEFAULT_STRATEGIES = [
    {"id": "choch_scalper", "name": "Yön değişimi", "description": "Fiyat yön değiştirince fırsat arar.", "enabled": True, "mode": "paper_live", "risk_level": "medium"},
    {"id": "imbalance_fill", "name": "Boşluk fırsatı", "description": "Fiyat boşluğu doldurur mu izler.", "enabled": False, "mode": "paper", "risk_level": "medium"},
]

DEFAULT_FILTERS = [
    {"id": "spread_guard", "name": "Al-sat farkı güvenliği", "description": "Pahalı girişleri engeller.", "enabled": True, "protects_against": "Kötü giriş fiyatı"},
    {"id": "volume_guard", "name": "Hacim kontrolü", "description": "Hareket güçlü mü bakar.", "enabled": True, "protects_against": "Zayıf hacim"},
]


def _canonical_id(value: Any, item_type: str) -> str | None:
    text = str(value or "").strip().lower()
    if item_type == "strategy":
        if "choch" in text or "yön değiş" in text or "yon degis" in text:
            return "choch_scalper"
        if "imbalance" in text or "boşluk" in text or "bosluk" in text:
            return "imbalance_fill"
    else:
        if "spread" in text or "al-sat" in text or "al sat" in text:
            return "spread_guard"
        if "volume" in text or "hacim" in text:
            return "volume_guard"
    return None


def _clean_id(value: Any, fallback: str, item_type: str = "strategy") -> str:
    canonical = _canonical_id(value, item_type)
    if canonical:
        return canonical
    text = str(value or "").strip()
    if text:
        return text
    return fallback


def _normalize_item(item: Any, index: int, item_type: str) -> dict:
    source = item if isinstance(item, dict) else {"name": str(item or "")}
    fallback_id = f"{item_type}_{index + 1}"
    item_id = _clean_id(source.get("id") or source.get("name") or source.get("title"), fallback_id, item_type)
    name = str(source.get("name") or source.get("title") or item_id).strip() or item_id
    description = str(source.get("description") or source.get("summary") or source.get("note") or "").strip()
    if not description:
        description = "Botun fırsat arama fikri." if item_type == "strategy" else "Kötü işlemi engelleyen kontrol."
    enabled = source.get("enabled")
    if enabled is None:
        enabled = source.get("active")
    if enabled is None:
        enabled = source.get("is_active")
    if enabled is None:
        status = str(source.get("status") or "").lower()
        enabled = status not in {"disabled", "off", "passive", "kapalı"}
    return {
        **source,
        "id": item_id,
        "name": name,
        "description": description,
        "enabled": bool(enabled),
    }


def _load_items(settings: dict, item_type: str) -> list[dict]:
    key = "strategies" if item_type == "strategy" else "filters"
    fallback = DEFAULT_STRATEGIES if item_type == "strategy" else DEFAULT_FILTERS
    source = settings.get(key)
    if not isinstance(source, list) or not source:
        source = deepcopy(fallback)
    return [_normalize_item(item, idx, item_type) for idx, item in enumerate(source)]


def _selected_ids(items: list[dict]) -> list[str]:
    return [str(item.get("id")) for item in items if item.get("enabled")]


def _append_missing_selected(items: list[dict], selected_ids: list[str], item_type: str) -> list[dict]:
    existing = {str(item.get("id")) for item in items}
    defaults = DEFAULT_STRATEGIES if item_type == "strategy" else DEFAULT_FILTERS
    by_id = {str(item.get("id")): item for item in defaults}
    result = list(items)
    for selected_id in [str(v) for v in selected_ids]:
        if selected_id in existing:
            continue
        default_item = deepcopy(by_id.get(selected_id) or {"id": selected_id, "name": selected_id, "description": "Kullanıcı seçimi.", "enabled": True})
        result.append(_normalize_item(default_item, len(result), item_type))
        existing.add(selected_id)
    return result


def _merge_selected(items: list[dict], selected_ids: list[str]) -> list[dict]:
    selected = {str(v) for v in selected_ids}
    return [{**item, "enabled": str(item.get("id")) in selected} for item in items]


def _persist_shadow_rules(user: str, strategies: list[dict], filters: list[dict]) -> dict:
    shadow = load_shadow(user)
    rules = shadow.get("rules") if isinstance(shadow.get("rules"), dict) else {}
    rules["strategies"] = strategies
    rules["filters"] = filters
    rules["selected_strategy_ids"] = _selected_ids(strategies)
    rules["selected_filter_ids"] = _selected_ids(filters)
    rules["updated_at"] = now_iso()
    shadow["rules"] = rules
    append_audit(
        shadow,
        "strategy_filter.toggles",
        "ok",
        "Strateji ve filtre seçimleri güncellendi.",
        meta={
            "category": "settings",
            "severity": "notice",
            "active_strategy_ids": rules["selected_strategy_ids"],
            "active_filter_ids": rules["selected_filter_ids"],
        },
        user=user,
    )
    return save_shadow(shadow, user)


def get_strategy_filter_toggles(user: str) -> dict:
    settings = load_settings(user)
    strategies = _load_items(settings, "strategy")
    filters = _load_items(settings, "filter")
    selected_strategy_ids = settings.get("selected_strategy_ids")
    selected_filter_ids = settings.get("selected_filter_ids")
    if isinstance(selected_strategy_ids, list):
        strategies = _merge_selected(strategies, [str(v) for v in selected_strategy_ids])
    if isinstance(selected_filter_ids, list):
        filters = _merge_selected(filters, [str(v) for v in selected_filter_ids])
    return {
        "status": "ok",
        "user": user,
        "strategies": strategies,
        "filters": filters,
        "selected_strategy_ids": _selected_ids(strategies),
        "selected_filter_ids": _selected_ids(filters),
        "active_strategy_count": len(_selected_ids(strategies)),
        "active_filter_count": len(_selected_ids(filters)),
    }


def save_strategy_filter_toggles(user: str, payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    settings = load_settings(user)
    before = deepcopy(settings)
    strategies = _load_items(settings, "strategy")
    filters = _load_items(settings, "filter")
    if isinstance(payload.get("strategies"), list):
        incoming = [_normalize_item(item, idx, "strategy") for idx, item in enumerate(payload.get("strategies") or [])]
        if incoming:
            strategies = incoming
    if isinstance(payload.get("filters"), list):
        incoming = [_normalize_item(item, idx, "filter") for idx, item in enumerate(payload.get("filters") or [])]
        if incoming:
            filters = incoming
    if isinstance(payload.get("selected_strategy_ids"), list):
        selected = [str(v) for v in payload.get("selected_strategy_ids")]
        strategies = _append_missing_selected(strategies, selected, "strategy")
        strategies = _merge_selected(strategies, selected)
    if isinstance(payload.get("selected_filter_ids"), list):
        selected = [str(v) for v in payload.get("selected_filter_ids")]
        filters = _append_missing_selected(filters, selected, "filter")
        filters = _merge_selected(filters, selected)
    settings["strategies"] = strategies
    settings["filters"] = filters
    settings["selected_strategy_ids"] = _selected_ids(strategies)
    settings["selected_filter_ids"] = _selected_ids(filters)
    settings["strategy_filter_updated_at"] = now_iso()
    saved_settings = save_settings(settings, user)
    _persist_shadow_rules(user, strategies, filters)
    return {
        "status": "saved",
        "ok": True,
        "user": user,
        "strategies": strategies,
        "filters": filters,
        "selected_strategy_ids": settings["selected_strategy_ids"],
        "selected_filter_ids": settings["selected_filter_ids"],
        "active_strategy_count": len(settings["selected_strategy_ids"]),
        "active_filter_count": len(settings["selected_filter_ids"]),
        "changed": before.get("selected_strategy_ids") != settings["selected_strategy_ids"] or before.get("selected_filter_ids") != settings["selected_filter_ids"],
        "settings": saved_settings,
    }
