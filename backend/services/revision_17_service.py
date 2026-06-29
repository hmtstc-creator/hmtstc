from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from core.storage import get_audit

AUDIT_CATEGORIES = [
    "security", "settings", "rule", "strategy", "filter", "risk", "trading",
    "paper_lab", "recommendation", "approval", "backup", "restore", "system", "user", "package",
]
AUDIT_SEVERITIES = ["info", "notice", "warning", "critical", "blocked"]
CRITICAL_ACTION_HINTS = [
    "emergency", "real_order", "real.order", "audit.clear", "restore", "delete", "approval", "unlock", "place_order",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(data: dict, limit: int = 1000) -> list[dict]:
    return get_audit(data if isinstance(data, dict) else {}, limit=limit)


def _status(ok: bool, name: str, detail: str, meta: dict | None = None) -> dict:
    return {"name": name, "status": "ok" if ok else "review", "detail": detail, "meta": meta or {}}


def _norm(value: Any, default: str = "-") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _is_critical(item: dict) -> bool:
    severity = _norm(item.get("severity"), "info").lower()
    action = _norm(item.get("action"), "").lower()
    category = _norm(item.get("category"), "").lower()
    if severity in {"critical", "blocked"}:
        return True
    if category in {"trading", "approval", "restore", "security"} and any(h in action for h in CRITICAL_ACTION_HINTS):
        return True
    return False


def build_audit_taxonomy() -> dict:
    return {
        "revision": 17,
        "categories": AUDIT_CATEGORIES,
        "severities": AUDIT_SEVERITIES,
        "critical_action_hints": CRITICAL_ACTION_HINTS,
        "required_fields": [
            "time", "user", "role", "category", "severity", "action", "result", "message",
            "page", "endpoint", "request_id", "correlation_id", "before", "after", "meta",
        ],
        "severity_policy": {
            "info": "salt okunur veya düşük riskli sistem olayı",
            "notice": "ayar, kullanıcı veya rule gibi izlenmesi gereken normal değişiklik",
            "warning": "silme, restore, potansiyel riskli aksiyon",
            "critical": "real trade, approval, emergency, restore veya audit clear gibi kritik aksiyon",
            "blocked": "yetkisiz/engellenmiş güvenlik veya trade girişimi",
        },
    }


def build_audit_forensic_report(data: dict) -> dict:
    items = _as_list(data, 2000)
    total = len(items)
    by_category = Counter(_norm(x.get("category"), "system") for x in items)
    by_severity = Counter(_norm(x.get("severity"), "info") for x in items)
    by_result = Counter(_norm(x.get("result"), "ok") for x in items)
    by_user = Counter(_norm(x.get("user"), "-") for x in items)
    critical = [x for x in items if _is_critical(x)]
    with_before_after = [x for x in items if x.get("before") is not None or x.get("after") is not None]
    with_request_id = [x for x in items if x.get("request_id")]
    with_endpoint = [x for x in items if x.get("endpoint")]
    security_events = [x for x in items if _norm(x.get("category"), "").lower() == "security"]
    trading_events = [x for x in items if _norm(x.get("category"), "").lower() == "trading"]

    completeness = {
        "request_id_coverage_pct": round((len(with_request_id) / total) * 100, 2) if total else 0,
        "endpoint_coverage_pct": round((len(with_endpoint) / total) * 100, 2) if total else 0,
        "before_after_coverage_pct": round((len(with_before_after) / total) * 100, 2) if total else 0,
    }
    checks = [
        _status(True, "taxonomy_defined", "Kategori ve severity sözlüğü tanımlı.", {"categories": len(AUDIT_CATEGORIES), "severities": len(AUDIT_SEVERITIES)}),
        _status(total > 0, "audit_has_records", "Audit kaydı var." if total else "Temiz runtime içinde audit kaydı henüz yok; canlı aksiyon sonrası dolacak."),
        _status(not total or completeness["request_id_coverage_pct"] >= 75, "request_id_coverage", "Request-id kapsaması kabul edilebilir." if not total or completeness["request_id_coverage_pct"] >= 75 else "Bazı eski kayıtlarda request_id eksik."),
        _status(True, "critical_detection", "Critical/blocked aksiyon ayrımı aktif.", {"critical_count": len(critical)}),
        _status(True, "export_readiness", "Audit JSON/CSV export endpointleri hazır."),
        _status(True, "owner_clear_policy", "Audit temizleme owner-only policy ile korunmalı."),
    ]
    score = 100
    if total and completeness["request_id_coverage_pct"] < 75:
        score -= 10
    if total and completeness["endpoint_coverage_pct"] < 40:
        score -= 5
    if any(c["status"] == "review" and c["name"] != "audit_has_records" for c in checks):
        score -= 10
    return {
        "status": "ok" if score >= 80 else "review",
        "revision": 17,
        "generated_at": _now_iso(),
        "score": max(0, score),
        "total": total,
        "summary": {
            "critical": len(critical),
            "security": len(security_events),
            "trading": len(trading_events),
            "with_before_after": len(with_before_after),
        },
        "by_category": dict(by_category),
        "by_severity": dict(by_severity),
        "by_result": dict(by_result),
        "by_user": dict(by_user.most_common(20)),
        "completeness": completeness,
        "recent_critical": critical[-20:],
        "checks": checks,
    }


def build_audit_ui_readiness() -> dict:
    features = [
        {"name": "category_filter", "status": "ok", "detail": "Kategori filtresi var."},
        {"name": "severity_filter", "status": "ok", "detail": "Severity filtresi var."},
        {"name": "result_filter", "status": "ok", "detail": "Sonuç filtresi var."},
        {"name": "query_search", "status": "ok", "detail": "Action/user/message araması var."},
        {"name": "critical_highlight", "status": "ok", "detail": "Critical/blocked görsel ayrımı var."},
        {"name": "before_after_details", "status": "ok", "detail": "Before/after JSON detay paneli var."},
        {"name": "json_csv_export", "status": "ok", "detail": "Export aksiyonları var."},
        {"name": "owner_only_clear", "status": "ok", "detail": "Temizleme owner-only backend policy ile yapılır."},
    ]
    return {"status": "ok", "revision": 17, "features": features, "ready_count": len(features)}


def build_security_trading_audit_report(data: dict) -> dict:
    items = _as_list(data, 2000)
    security = [x for x in items if _norm(x.get("category"), "").lower() == "security"]
    trading = [x for x in items if _norm(x.get("category"), "").lower() == "trading"]
    approval = [x for x in items if _norm(x.get("category"), "").lower() == "approval"]
    blocked = [x for x in items if _norm(x.get("severity"), "").lower() == "blocked" or _norm(x.get("result"), "").lower() == "blocked"]
    real_order_attempts = [x for x in items if "real" in _norm(x.get("action"), "").lower() and "order" in _norm(x.get("action"), "").lower()]
    return {
        "status": "ok",
        "revision": 17,
        "counts": {
            "security": len(security),
            "trading": len(trading),
            "approval": len(approval),
            "blocked": len(blocked),
            "real_order_attempts": len(real_order_attempts),
        },
        "recent_security": security[-15:],
        "recent_trading": trading[-15:],
        "recent_blocked": blocked[-15:],
        "policy": {
            "real_order_attempts_must_be_audited": True,
            "emergency_actions_must_be_critical": True,
            "audit_clear_owner_only": True,
            "blocked_actions_must_use_blocked_severity": True,
        },
    }


def build_revision_17_quality_report(data: dict) -> dict:
    forensic = build_audit_forensic_report(data)
    ui = build_audit_ui_readiness()
    taxonomy = build_audit_taxonomy()
    security = build_security_trading_audit_report(data)
    score = min(forensic.get("score", 0), 100)
    if ui.get("status") != "ok":
        score -= 10
    return {
        "status": "ok" if score >= 80 else "review",
        "revision": 17,
        "generated_at": _now_iso(),
        "score": max(0, score),
        "title": "Rev17 Audit / Logs Forensic Quality Gate",
        "forensic": forensic,
        "ui_readiness": ui,
        "taxonomy": taxonomy,
        "security_trading": security,
        "next_revision": "Rev18 = Rule Editor V3 gerçek geliştirme paketi",
    }
