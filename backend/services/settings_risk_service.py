from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.settings_unit_service import calculate_risk_summary, normalize_settings_units, validate_normalized_settings


def _as_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value if value is not None else fallback)
    except Exception:
        return fallback


def _as_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(round(float(value if value is not None else fallback)))
    except Exception:
        return fallback


def build_worst_case_risk_matrix(settings: dict | None) -> dict:
    normalized = normalize_settings_units(settings or {})
    calc = calculate_risk_summary(normalized)
    bot = normalized.get("bot") or {}
    risk = normalized.get("risk") or {}
    capital = _as_float(calc.get("capital_usdt"), 1000)
    slot_size = _as_float(calc.get("slot_size_usdt"), 50)
    stop_pct = _as_float(calc.get("effective_stop_loss_percent"), 0.75)
    max_open = max(1, _as_int(calc.get("max_open_positions"), 1))
    same_direction = max(1, _as_int(risk.get("max_same_direction_positions"), 1))
    daily_loss = _as_float(calc.get("daily_loss_limit_usdt"), 0)
    weekly_loss = _as_float(calc.get("weekly_loss_limit_usdt"), 0)
    slot_risk = round(slot_size * (stop_pct / 100), 6)
    scenarios = [
        {"name": "single_stop", "label": "Tek pozisyon stop", "positions": 1},
        {"name": "same_direction_stop", "label": "Aynı yön pozisyon stop", "positions": min(same_direction, max_open)},
        {"name": "max_open_stop", "label": "Tüm açık pozisyonlar stop", "positions": max_open},
    ]
    enriched = []
    for item in scenarios:
        loss = round(slot_risk * item["positions"], 6)
        enriched.append({
            **item,
            "loss_usdt": loss,
            "capital_pct": round((loss / capital) * 100, 6) if capital > 0 else 0,
            "daily_limit_usage_pct": round((loss / daily_loss) * 100, 6) if daily_loss > 0 else 0,
            "weekly_limit_usage_pct": round((loss / weekly_loss) * 100, 6) if weekly_loss > 0 else 0,
            "status": "blocked" if (daily_loss > 0 and loss > daily_loss) else ("review" if daily_loss > 0 and loss > daily_loss * 0.7 else "ok"),
        })
    return {
        "status": "ok" if all(x["status"] == "ok" for x in enriched) else "review",
        "summary": calc,
        "scenarios": enriched,
        "notes": [
            "Worst-case hesapları normalize edilmiş yüzde ve USDT alanlarından üretilir.",
            "Real readiness sadece matematiksel risk uygunluğunu gösterir; gerçek emir için safety/unlock/pilot kapıları ayrıca gerekir.",
        ],
    }


def build_real_readiness_impact(settings: dict | None) -> dict:
    normalized = normalize_settings_units(settings or {})
    validation = validate_normalized_settings(normalized)
    calc = normalized.get("risk_calculation") or calculate_risk_summary(normalized)
    blockers = []
    warnings = []
    if not validation.get("valid"):
        blockers.extend([e.get("message") for e in validation.get("errors", []) if e.get("message")])
    if calc.get("real_trade_readiness") == "blocked":
        blockers.append("Risk/sermaye ilişkisi gerçek trade için uygun değil.")
    if _as_float(calc.get("max_concurrent_risk_usdt"), 0) > _as_float(calc.get("daily_loss_limit_usdt"), 0):
        blockers.append("Maksimum eşzamanlı risk günlük zarar limitini aşıyor.")
    if _as_float(calc.get("deployed_capacity_percent"), 0) > 100:
        warnings.append("Açık pozisyon kapasitesi sermayenin tamamını aşabilir.")
    if _as_float(calc.get("risk_reward_ratio"), 0) < 1:
        warnings.append("Risk/ödül oranı 1 altında; scalping için dikkatli izlenmeli.")
    if _as_float(calc.get("effective_stop_loss_percent"), 0) > 2.5:
        warnings.append("Stop loss değeri vur-kaç spot yapı için geniş görünüyor.")
    status = "blocked" if blockers else ("review" if warnings else "ok")
    return {
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "risk_calculation": calc,
        "effective_limits": {
            "capital_usdt": calc.get("capital_usdt"),
            "slot_size_usdt": calc.get("slot_size_usdt"),
            "max_open_positions": calc.get("max_open_positions"),
            "stop_loss_percent": calc.get("effective_stop_loss_percent"),
            "daily_loss_limit_usdt": calc.get("daily_loss_limit_usdt"),
            "weekly_loss_limit_usdt": calc.get("weekly_loss_limit_usdt"),
        },
        "real_trade_policy": {
            "auto_enable": False,
            "requires_owner_unlock": True,
            "requires_safety_review": True,
            "requires_pilot_mode": True,
        },
    }


def build_settings_change_diff(before: dict | None, after: dict | None) -> list[dict]:
    before = before or {}
    after = after or {}
    changes: list[dict] = []
    for section in ["bot", "risk", "api", "coin_filter"]:
        b = before.get(section, {}) if isinstance(before.get(section), dict) else {}
        a = after.get(section, {}) if isinstance(after.get(section), dict) else {}
        for key in sorted(set(b.keys()) | set(a.keys())):
            if key in {"unit_schema", "risk_calculation"}:
                continue
            if b.get(key) != a.get(key):
                changes.append({"field": f"{section}.{key}", "before": b.get(key), "after": a.get(key)})
    return changes


def build_settings_rollback_preview(current_settings: dict, history_item: dict | None) -> dict:
    if not history_item:
        return {"status": "blocked", "reason": "Settings history kaydı bulunamadı."}
    before_snapshot = history_item.get("before_snapshot")
    if not isinstance(before_snapshot, dict):
        before_snapshot = deepcopy(current_settings)
        for change in history_item.get("changes", []) or []:
            field = str(change.get("field") or "")
            parts = field.split(".")
            if len(parts) != 2:
                continue
            section, key = parts
            before_snapshot.setdefault(section, {})[key] = change.get("before")
    normalized = normalize_settings_units(before_snapshot)
    return {
        "status": "ok",
        "history_time": history_item.get("time"),
        "source": history_item.get("source"),
        "target_settings": normalized,
        "changes_to_apply": build_settings_change_diff(current_settings, normalized),
        "risk_calculation": normalized.get("risk_calculation") or calculate_risk_summary(normalized),
        "real_readiness_impact": build_real_readiness_impact(normalized),
        "policy": "Rollback doğrudan geçmişe dönmez; önce preview üretir, onay sonrası yeni settings kaydı olarak uygulanır.",
    }
