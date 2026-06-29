from __future__ import annotations

from copy import deepcopy

from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_user
from core.config import DEFAULT_COIN_FILTER, DEFAULT_USER
from core.storage import append_audit, load_settings, load_shadow, now_iso, save_settings, save_shadow
from services.settings_unit_service import calculate_risk_summary, normalize_settings_units, standard_error, standard_success, validate_normalized_settings
from services.settings_risk_service import build_real_readiness_impact, build_settings_rollback_preview, build_worst_case_risk_matrix
from services.rule_settings_governance_service import (
    build_risk_profile_audit,
    build_rule_settings_governance_quality,
    build_settings_governance_evidence,
    build_settings_impact_preview,
)


router = APIRouter(prefix="/api/settings", tags=["settings"])


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


def _settings_diff(before: dict, after: dict) -> list[dict]:
    changes = []
    for section in ["bot", "risk", "api", "coin_filter"]:
        b = before.get(section, {}) if isinstance(before.get(section), dict) else {}
        a = after.get(section, {}) if isinstance(after.get(section), dict) else {}
        for key in sorted(set(b.keys()) | set(a.keys())):
            if key in {"unit_schema", "risk_calculation"}:
                continue
            if b.get(key) != a.get(key):
                changes.append({"field": f"{section}.{key}", "before": b.get(key), "after": a.get(key)})
    return changes


def _record_settings_history(user: str, before: dict, after: dict, source: str, role: str = "user") -> list[dict]:
    data = load_shadow(user)
    history = data.setdefault("settings_history", [])
    changes = _settings_diff(before, after)
    if changes:
        item = {
            "time": now_iso(),
            "user": user,
            "source": source,
            "profile": (after.get("risk") or {}).get("profile"),
            "changes": changes,
            "before_snapshot": before,
            "after_snapshot": after,
            "risk_calculation": after.get("risk_calculation") or calculate_risk_summary(after),
            "real_readiness_impact": build_real_readiness_impact(after),
        }
        history.append(item)
        data["settings_history"] = history[-300:]
        append_audit(
            data,
            "settings.update",
            "ok",
            f"{len(changes)} settings alanı güncellendi.",
            meta={"category": "settings", "severity": "notice", "before": before, "after": after, "changes": changes, "page": "settings", "endpoint": "/api/settings", "role": role},
            user=user,
        )
        save_shadow(data, user)
    return changes


def _settings_store_echo_response(user: str, saved_settings: dict, **extra) -> dict:
    store_echo_settings = load_settings(user)
    coin_filter = saved_settings.get("coin_filter") if isinstance(saved_settings.get("coin_filter"), dict) else DEFAULT_COIN_FILTER
    store_echo = store_echo_settings.get("coin_filter") if isinstance(store_echo_settings.get("coin_filter"), dict) else DEFAULT_COIN_FILTER
    persisted_sections = ("api", "bot", "risk", "telegram", "coin_filter", "strategies", "current_strategy")
    persisted = all(store_echo_settings.get(key) == saved_settings.get(key) for key in persisted_sections)
    response = {
        "status": "saved",
        "ok": True,
        "saved": True,
        "persisted": persisted,
        "source": "settings_store",
        "user": user,
        "settings": saved_settings,
        "settings_store_echo": store_echo_settings,
        "coin_filter": coin_filter,
        "store_echo": store_echo,
        "refresh_echo": store_echo,
    }
    response.update(extra)
    return response


@router.get("")
def get_settings(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    settings["user"] = user
    return settings


@router.post("")
def update_settings(settings: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    before = load_settings(user)
    validation = validate_normalized_settings(settings)
    if not validation["valid"]:
        first = validation["errors"][0] if validation.get("errors") else {}
        raise HTTPException(
            status_code=400,
            detail=standard_error(
                "VALIDATION_ERROR",
                first.get("message") or "Settings doğrulaması başarısız.",
                field=first.get("field"),
                expected="Sayı, yüzde veya USDT alanı için geçerli değer",
                received=settings,
            ),
        )
    normalized = validation["normalized"]
    saved_settings = save_settings(normalized, user)
    changes = _record_settings_history(user, before, saved_settings, source="manual", role=str(current_user.get("role") or "user"))
    return _settings_store_echo_response(user, saved_settings, changes=changes, validation=validation)


@router.post("/preview")
def preview_settings(settings: dict, current_user: dict = Depends(require_user)):
    validation = validate_normalized_settings(settings)
    return {"status": "ok" if validation["valid"] else "blocked", **validation}


@router.get("/units")
def get_settings_units(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    return {"status": "ok", "user": user, "unit_schema": settings.get("unit_schema", {}), "risk_calculation": settings.get("risk_calculation") or calculate_risk_summary(settings)}


@router.get("/history")
def get_settings_history(limit: int = 100, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    items = data.get("settings_history", []) or []
    return {"status": "ok", "user": user, "count": len(items[-limit:]), "items": items[-limit:]}




@router.post("/risk-preview")
def preview_risk_impact(settings: dict, current_user: dict = Depends(require_user)):
    validation = validate_normalized_settings(settings)
    normalized = validation.get("normalized", settings)
    return {
        "status": "ok" if validation.get("valid") else "blocked",
        "valid": validation.get("valid"),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
        "normalized": normalized,
        "risk_calculation": normalized.get("risk_calculation") or calculate_risk_summary(normalized),
    }


@router.post("/risk-impact")
def preview_real_readiness_impact(settings: dict, current_user: dict = Depends(require_user)):
    validation = validate_normalized_settings(settings)
    normalized = validation.get("normalized", settings)
    return {
        "status": "ok" if validation.get("valid") else "blocked",
        "valid": validation.get("valid"),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
        "normalized": normalized,
        "worst_case_matrix": build_worst_case_risk_matrix(normalized),
        "real_readiness_impact": build_real_readiness_impact(normalized),
    }


@router.get("/risk-impact/current")
def get_current_real_readiness_impact(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    return {
        "status": "ok",
        "user": user,
        "worst_case_matrix": build_worst_case_risk_matrix(settings),
        "real_readiness_impact": build_real_readiness_impact(settings),
    }


@router.post("/rollback-preview")
def preview_settings_rollback(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    history = data.get("settings_history", []) or []
    index = payload.get("index")
    item = None
    if index is None:
        item = history[-1] if history else None
    else:
        try:
            idx = int(index)
            item = history[idx] if 0 <= idx < len(history) else None
        except Exception:
            item = None
    current = load_settings(user)
    preview = build_settings_rollback_preview(current, item)
    preview["user"] = user
    return preview


@router.post("/rollback")
def apply_settings_rollback(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    history = data.get("settings_history", []) or []
    index = payload.get("index")
    item = None
    if index is None:
        item = history[-1] if history else None
    else:
        try:
            idx = int(index)
            item = history[idx] if 0 <= idx < len(history) else None
        except Exception:
            item = None
    current = load_settings(user)
    preview = build_settings_rollback_preview(current, item)
    if preview.get("status") != "ok":
        raise HTTPException(status_code=400, detail=standard_error("ROLLBACK_PREVIEW_FAILED", preview.get("reason") or "Rollback preview üretilemedi."))
    target = preview.get("target_settings") or current
    validation = validate_normalized_settings(target)
    if not validation.get("valid"):
        first = (validation.get("errors") or [{}])[0]
        raise HTTPException(status_code=400, detail=standard_error("VALIDATION_ERROR", first.get("message") or "Rollback settings doğrulaması başarısız.", field=first.get("field")))
    saved = save_settings(validation.get("normalized"), user)
    changes = _record_settings_history(user, current, saved, source="rollback", role=str(current_user.get("role") or "user"))
    return _settings_store_echo_response(user, saved, changes=changes, rollback_preview=preview)




@router.post("/impact-preview")
def settings_impact_preview(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    current = load_settings(user)
    candidate = payload.get("settings") if isinstance(payload, dict) and "settings" in payload else payload
    return build_settings_impact_preview(current, candidate)


@router.get("/risk-profile/audit")
def risk_profile_audit(current_user: dict = Depends(require_user)):
    return build_risk_profile_audit(current_username(current_user))


@router.get("/governance/evidence")
def settings_governance_evidence(current_user: dict = Depends(require_user)):
    return build_settings_governance_evidence(current_username(current_user))


@router.get("/governance/quality")
def settings_governance_quality(current_user: dict = Depends(require_user)):
    return build_rule_settings_governance_quality(current_username(current_user))


@router.get("/coin-filter")
def get_coin_filter_settings(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    coin_filter = settings["coin_filter"]
    return {
        "status": "ok",
        "ok": True,
        "persisted": True,
        "source": "settings_store",
        "user": user,
        "coin_filter": coin_filter,
        "store_echo": coin_filter,
        "refresh_echo": coin_filter,
    }


@router.post("/coin-filter")
def update_coin_filter_settings(coin_filter: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    before = deepcopy(settings)
    settings["coin_filter"] = {**DEFAULT_COIN_FILTER, **(coin_filter or {})}
    saved_settings = save_settings(settings, user)
    _record_settings_history(user, before, saved_settings, source="coin_filter", role=str(current_user.get("role") or "user"))
    return _settings_store_echo_response(user, saved_settings)


@router.get("/strategies")
def get_strategy_settings(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    return {"status": "ok", "user": user, "current_strategy": settings.get("current_strategy"), "strategies": settings.get("strategies", [])}


@router.post("/strategies")
def update_strategy_settings(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    before = deepcopy(settings)
    if isinstance(payload.get("strategies"), list):
        settings["strategies"] = payload["strategies"]
    if payload.get("current_strategy"):
        settings["current_strategy"] = payload["current_strategy"]
    saved_settings = save_settings(settings, user)
    _record_settings_history(user, before, saved_settings, source="strategies", role=str(current_user.get("role") or "user"))
    return {"status": "saved", "user": user, "current_strategy": saved_settings.get("current_strategy"), "strategies": saved_settings.get("strategies", [])}


RISK_PROFILE_TEMPLATES = {
    "conservative": {
        "label": "Conservative",
        "bot": {"allocated_usdt": 1000, "usdt_per_position": 50, "max_open_positions": 10, "slot_count": 20},
        "risk": {"profile": "conservative", "daily_loss_limit": 15, "weekly_loss_limit": 45, "stop_loss": 0.55, "take_profit": 1.25, "risk_per_position_percent": 0.5, "max_portfolio_risk_percent": 3, "max_same_direction_positions": 2, "cooldown_minutes": 20},
    },
    "balanced": {
        "label": "Balanced",
        "bot": {"allocated_usdt": 1000, "usdt_per_position": 50, "max_open_positions": 20, "slot_count": 20},
        "risk": {"profile": "balanced", "daily_loss_limit": 30, "weekly_loss_limit": 90, "stop_loss": 0.75, "take_profit": 2, "risk_per_position_percent": 1, "max_portfolio_risk_percent": 5, "max_same_direction_positions": 3, "cooldown_minutes": 15},
    },
    "aggressive_scalper": {
        "label": "Aggressive Scalper",
        "bot": {"allocated_usdt": 1000, "usdt_per_position": 100, "max_open_positions": 10, "slot_count": 10},
        "risk": {"profile": "aggressive_scalper", "daily_loss_limit": 45, "weekly_loss_limit": 120, "stop_loss": 0.9, "take_profit": 1.8, "risk_per_position_percent": 1.5, "max_portfolio_risk_percent": 7, "max_same_direction_positions": 4, "cooldown_minutes": 10},
    },
    "shadow_only": {
        "label": "Shadow Only",
        "bot": {"allocated_usdt": 1000, "usdt_per_position": 50, "max_open_positions": 20, "slot_count": 20},
        "risk": {"profile": "shadow_only", "daily_loss_limit": 20, "weekly_loss_limit": 60, "stop_loss": 0.75, "take_profit": 2, "risk_per_position_percent": 1, "max_portfolio_risk_percent": 5, "max_same_direction_positions": 3, "cooldown_minutes": 15},
    },
}


@router.get("/risk-profiles")
def get_risk_profiles(current_user: dict = Depends(require_user)):
    return {"status": "ok", "profiles": RISK_PROFILE_TEMPLATES}


@router.post("/risk-profiles/{profile_id}")
def apply_risk_profile(profile_id: str, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    profile = RISK_PROFILE_TEMPLATES.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail=standard_error("NOT_FOUND", "Risk profili bulunamadı.", field="profile_id", received=profile_id))
    settings = load_settings(user)
    before = deepcopy(settings)
    settings.setdefault("bot", {}).update(profile.get("bot", {}))
    settings.setdefault("risk", {}).update(profile.get("risk", {}))
    settings["risk"]["profile"] = profile_id
    normalized = normalize_settings_units(settings)
    saved_settings = save_settings(normalized, user)
    changes = _record_settings_history(user, before, saved_settings, source=f"risk_profile:{profile_id}", role=str(current_user.get("role") or "user"))
    return _settings_store_echo_response(user, saved_settings, profile_id=profile_id, changes=changes)


@router.post("/validate")
def validate_settings_endpoint(settings: dict, current_user: dict = Depends(require_user)):
    return validate_normalized_settings(settings)
