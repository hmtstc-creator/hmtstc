from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def _as_list(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _rule_item(item: dict, fallback_type: str, index: int) -> dict:
    rule_id = str(item.get("id") or item.get("key") or item.get("name") or f"{fallback_type}_{index + 1}").strip()
    name = str(item.get("name") or item.get("label") or rule_id).strip()
    enabled = item.get("enabled", item.get("active", True)) is not False
    return {
        "id": rule_id,
        "name": name,
        "type": fallback_type,
        "enabled": enabled,
        "status": "active" if enabled else "passive",
        "description": item.get("description") or item.get("note") or item.get("summary") or "Owner tarafından yönetilen kural.",
        "user_can_toggle": item.get("user_can_toggle", True) is not False,
        "admin_can_edit": True,
        "paper_lab_ready": True,
    }


def _collect_settings_rules(settings: dict) -> tuple[list[dict], list[dict]]:
    strategies = _as_list(settings.get("strategies"))
    filters = _as_list(settings.get("filters")) or _as_list(settings.get("risk_filters"))

    if not strategies:
        current = settings.get("current_strategy") or "trend_follow"
        strategies = [
            {"id": str(current), "name": "Aktif strateji", "enabled": True, "description": "Kullanıcıya açılmış canlı strateji."}
        ]
    if not filters:
        filters = [
            {"id": "risk_guard", "name": "Risk filtresi", "enabled": True, "description": "Riskli işlemleri engeller."},
            {"id": "market_confidence", "name": "Piyasa güven filtresi", "enabled": True, "description": "Otomatik mod güven skorunu kontrol eder."},
        ]
    return (
        [_rule_item(item, "strategy", idx) for idx, item in enumerate(strategies)],
        [_rule_item(item, "filter", idx) for idx, item in enumerate(filters)],
    )


def build_rental_admin_strategy_filter_management(settings: dict, *, role: str = "user", user: str = "default") -> dict:
    """Owner için kalıcı strateji/filtre yönetim sözleşmesi.

    Son kullanıcı sadece kendisine açılan kuralı aç/kapat yapar.
    Owner ise ekle/düzenle/pasife al işlemlerini kalıcı ayara bağlar.
    """
    settings = deepcopy(settings or {})
    role = str(role or "user").lower()
    is_owner = role in {"owner", "admin", "superadmin"}
    strategies, filters = _collect_settings_rules(settings)
    editable_total = len(strategies) + len(filters)
    active_total = len([x for x in strategies + filters if x.get("enabled")])

    actions = [
        {"key": "add_strategy", "label": "Strateji ekle", "owner_only": True, "status": "ready" if is_owner else "locked"},
        {"key": "edit_strategy", "label": "Strateji düzenle", "owner_only": True, "status": "ready" if is_owner else "locked"},
        {"key": "disable_strategy", "label": "Stratejiyi pasife al", "owner_only": True, "status": "ready" if is_owner else "locked"},
        {"key": "add_filter", "label": "Filtre ekle", "owner_only": True, "status": "ready" if is_owner else "locked"},
        {"key": "edit_filter", "label": "Filtre düzenle", "owner_only": True, "status": "ready" if is_owner else "locked"},
        {"key": "disable_filter", "label": "Filtreyi pasife al", "owner_only": True, "status": "ready" if is_owner else "locked"},
        {"key": "assign_to_user", "label": "Kullanıcıya aç/kapat yetkisi ver", "owner_only": True, "status": "ready" if is_owner else "locked"},
        {"key": "send_to_paper_lab", "label": "Paper Lab kombinasyon testine gönder", "owner_only": True, "status": "ready" if is_owner else "locked"},
    ]

    checks = [
        {"area": "Yetki", "current": "Owner" if is_owner else "Kullanıcı", "expected": "Yönetim sadece owner tarafında olmalı", "ok": is_owner},
        {"area": "Stratejiler", "current": f"{len(strategies)} kayıt", "expected": "En az 1 strateji tanımlı", "ok": len(strategies) > 0},
        {"area": "Filtreler", "current": f"{len(filters)} kayıt", "expected": "En az 1 filtre tanımlı", "ok": len(filters) > 0},
        {"area": "Canlı kullanıcı", "current": "Aç/kapat", "expected": "Son kullanıcı düzenleme yapmaz", "ok": True},
        {"area": "Paper Lab", "current": "Admin karar alanı", "expected": "Kombinasyon testi admin’de kalmalı", "ok": True},
    ]

    return {
        "status": "ok",
        "user": user,
        "role": role,
        "is_owner": is_owner,
        "headline": "Strateji/filtre yönetimi owner tarafında kalıcıdır." if is_owner else "Strateji/filtre düzenleme owner alanıdır.",
        "summary": {
            "strategy_count": len(strategies),
            "filter_count": len(filters),
            "active_count": active_total,
            "editable_count": editable_total if is_owner else 0,
            "user_permission": "toggle_only",
            "admin_permission": "create_edit_disable_assign_paper_lab",
        },
        "strategies": strategies,
        "filters": filters,
        "actions": actions,
        "checks": checks,
        "next_action": "Owner yeni strateji/filtre ekleyebilir veya pasife alabilir." if is_owner else "Kullanıcı sadece Summary’de aç/kapat yapar.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
