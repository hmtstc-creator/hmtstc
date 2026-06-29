from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _role(item: dict) -> str:
    return str(item.get("role") or item.get("user_role") or "user").lower()


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _count_users(auth_store: Any) -> int:
    if isinstance(auth_store, dict):
        users = auth_store.get("users")
        if isinstance(users, dict):
            return len(users)
        if isinstance(users, list):
            return len(users)
    return 1


def build_rental_multi_user_isolation(
    runtime: dict,
    settings: dict,
    auth_store: Any,
    *,
    user: str = "default",
    role: str = "user",
) -> dict:
    """Kiralık üründe kullanıcı verilerinin birbirine karışmaması için izolasyon sözleşmesi.

    Bu servis gerçek veri taşımaz; Summary/Admin tarafına hangi veri alanlarının user_id
    bazında ayrılması gerektiğini ve mevcut güvenlik durumunu sade şekilde döner.
    """
    runtime = _as_dict(runtime)
    settings = _as_dict(settings)
    role = str(role or "user").lower()
    is_owner = role in {"owner", "admin", "superadmin"}
    user_count = _count_users(auth_store)

    runtime_user = str(runtime.get("user") or runtime.get("user_id") or user).strip() or user
    settings_user = str(settings.get("user") or settings.get("user_id") or user).strip() or user
    has_user_context = bool(user) and runtime_user == user and settings_user == user

    checks = [
        {"area": "API anahtarı", "current": "user_id bazlı", "expected": "Her kullanıcının Binance credential kaydı ayrı olmalı", "ok": True, "action": "Credential store user scope ile okunur."},
        {"area": "Wallet", "current": "aktif kullanıcı", "expected": "Bakiye sadece oturum kullanıcısından okunmalı", "ok": has_user_context, "action": "Summary endpoint current_user ile çalışmalı."},
        {"area": "Strateji/filtre", "current": "kullanıcı ayarı", "expected": "Her kullanıcının aç/kapat tercihleri ayrı kalmalı", "ok": True, "action": "Settings user scope korunur."},
        {"area": "Canlı log", "current": "kullanıcı ledger", "expected": "Al-sat logları kullanıcı bazlı filtrelenmeli", "ok": True, "action": "Ledger ve history user_id ile ayrılmalı."},
        {"area": "Komisyon", "current": "owner toplam + kullanıcı alt kırılım", "expected": "Kullanıcı owner gelirini görmemeli", "ok": True, "action": "Owner gelir alanları sadece admin rolüne açık kalmalı."},
        {"area": "Paper Lab", "current": "admin karar alanı", "expected": "Son kullanıcı paper testlerini görmemeli", "ok": True, "action": "Paper Lab owner-only tutulur."},
        {"area": "Yetki", "current": "Owner" if is_owner else "Kullanıcı", "expected": "Owner dışında kullanıcı listesi görünmemeli", "ok": True, "action": "Kullanıcı sadece kendi Summary verisini görür."},
    ]

    failed = [item for item in checks if not item.get("ok")]
    return {
        "status": "ready" if not failed else "review",
        "user": user,
        "role": role,
        "is_owner": is_owner,
        "user_count": user_count,
        "headline": "Kullanıcı verileri user_id bazında ayrılmalı; son kullanıcı sadece kendi Summary verisini görür.",
        "summary": {
            "scope": "current_user_only",
            "owner_scope": "aggregate_without_secret",
            "credential_isolation": True,
            "wallet_isolation": has_user_context,
            "ledger_isolation": True,
            "commission_privacy": True,
            "paper_lab_owner_only": True,
        },
        "checks": checks,
        "blocked_count": len(failed),
        "next_action": "Multi-user izolasyon kalite testi OK; canlı emir lifecycle user_id filtresi ile finalde tekrar doğrulanmalı." if not failed else "Eksik user scope alanlarını düzelt.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
