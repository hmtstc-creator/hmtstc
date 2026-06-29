from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from core.auth import require_owner, require_user
from core.config import DEFAULT_USER
from core.storage import append_audit, clear_audit, get_audit, load_shadow, save_shadow
from services.revision_17_service import build_audit_forensic_report, build_security_trading_audit_report
from services.audit_forensics_service import (
    audit_export_manifest,
    build_audit_forensics_final_report,
    enrich_audit_chain,
    security_trading_timeline,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])


ALLOWED_EXPORT_FORMATS = {"csv", "json"}


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


def _txt(value: Any) -> str:
    return "" if value is None else str(value)


def _match(item: dict, category=None, severity=None, action=None, result=None, username=None, date_from=None, date_to=None, query=None) -> bool:
    if category and category != "all" and str(item.get("category")) != category:
        return False
    if severity and severity != "all" and str(item.get("severity")) != severity:
        return False
    if action and action.lower() not in str(item.get("action") or "").lower():
        return False
    if result and result != "all" and str(item.get("result")) != result:
        return False
    if username and username != "all" and str(item.get("user")) != username:
        return False
    hay = " ".join(_txt(item.get(k)).lower() for k in ["action", "result", "message", "user", "role", "page", "endpoint", "category", "severity", "request_id", "correlation_id", "subject"])
    if query and query.lower() not in hay:
        return False
    t = str(item.get("time") or item.get("created_at") or "")
    if date_from and t < date_from:
        return False
    if date_to and t > date_to:
        return False
    return True


def _filtered_items(data: dict, limit: int, **filters) -> list[dict]:
    items = get_audit(data, limit=max(min(limit * 5, 5000), 1000))
    filtered = [item for item in items if _match(item, **filters)]
    return filtered[-limit:]


def _filters_dict(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v not in (None, "", "all")}


def _summary(items: list[dict]) -> dict:
    categories: dict[str, int] = {}
    severities: dict[str, int] = {}
    results: dict[str, int] = {}
    users: dict[str, int] = {}
    for item in items:
        categories[str(item.get("category") or "system")] = categories.get(str(item.get("category") or "system"), 0) + 1
        severities[str(item.get("severity") or "info")] = severities.get(str(item.get("severity") or "info"), 0) + 1
        results[str(item.get("result") or "ok")] = results.get(str(item.get("result") or "ok"), 0) + 1
        users[str(item.get("user") or "-")] = users.get(str(item.get("user") or "-"), 0) + 1
    return {
        "critical": len([x for x in items if x.get("severity") in {"critical", "blocked"}]),
        "security": len([x for x in items if x.get("category") == "security"]),
        "trading": len([x for x in items if x.get("category") == "trading"]),
        "settings": len([x for x in items if x.get("category") == "settings"]),
        "categories": categories,
        "severities": severities,
        "results": results,
        "users": users,
    }


@router.get("")
def list_audit(
    limit: int = Query(200, ge=1, le=2000),
    category: str | None = None,
    severity: str | None = None,
    action: str | None = None,
    result: str | None = None,
    username: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    query: str | None = None,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    data = load_shadow(user)
    items = _filtered_items(data, limit, category=category, severity=severity, action=action, result=result, username=username, date_from=date_from, date_to=date_to, query=query)
    chained = enrich_audit_chain(items)
    return {"status": "ok", "user": user, "count": len(chained), "summary": _summary(chained), "items": chained}


@router.get("/summary")
def audit_summary(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    items = get_audit(data, limit=2000)
    final = build_audit_forensics_final_report(data)
    return {"status": "ok", "user": user, "count": len(items), "summary": _summary(items), "forensic": build_audit_forensic_report(data), "forensics_final": final}


@router.get("/security-trading")
def audit_security_trading(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    report = build_security_trading_audit_report(data)
    report["timeline"] = security_trading_timeline(get_audit(data, limit=2000))
    return report


@router.get("/forensics")
def audit_forensics(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = build_audit_forensics_final_report(data)
    payload["user"] = user
    return payload


@router.get("/timeline")
def audit_timeline(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = security_trading_timeline(get_audit(data, limit=2000))
    payload["user"] = user
    return payload


@router.post("")
def create_audit(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = payload or {}
    data = load_shadow(user)
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    meta = {
        **meta,
        "page": payload.get("page") or meta.get("page"),
        "endpoint": payload.get("endpoint") or meta.get("endpoint"),
        "role": current_user.get("role") or payload.get("role") or meta.get("role"),
        "category": payload.get("category") or meta.get("category"),
        "severity": payload.get("severity") or meta.get("severity"),
        "before": payload.get("before", meta.get("before")),
        "after": payload.get("after", meta.get("after")),
        "request_id": payload.get("request_id") or meta.get("request_id"),
        "correlation_id": payload.get("correlation_id") or meta.get("correlation_id"),
    }
    item = append_audit(
        data,
        action=payload.get("action", "ui_action"),
        result=payload.get("result", "ok"),
        message=payload.get("message", ""),
        meta=meta,
        user=user,
    )
    save_shadow(data, user)
    return {"status": "ok", "user": user, "item": item}


@router.delete("")
def delete_audit(confirm: str | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    if confirm != "CLEAR_AUDIT":
        append_audit(data, "audit.clear.blocked", "blocked", "Audit clear confirmation eksik.", meta={"category": "security", "severity": "blocked", "endpoint": "/api/audit", "role": current_user.get("role")}, user=user)
        save_shadow(data, user)
        return {"status": "blocked", "message": "Audit temizlemek için confirm=CLEAR_AUDIT gerekli."}
    before_items = get_audit(data, limit=5000)
    manifest = audit_export_manifest(before_items, "json", {"clear_requested_by": user})
    ledger = data.setdefault("audit_clear_ledger", [])
    ledger.append({"time": datetime.utcnow().isoformat() + "Z", "user": user, "role": current_user.get("role"), "cleared_count": len(before_items), "manifest": manifest})
    data["audit_clear_ledger"] = ledger[-100:]
    cleared = clear_audit(data)
    append_audit(
        data,
        "audit.clear",
        "ok",
        f"{cleared} audit kaydı temizlendi.",
        meta={"category": "security", "severity": "critical", "endpoint": "/api/audit", "role": current_user.get("role"), "before": {"count": cleared, "manifest": manifest}, "after": {"count": 1}},
        user=user,
    )
    save_shadow(data, user)
    return {"status": "ok", "user": user, "cleared": cleared}


@router.get("/export")
def export_audit(
    format: str = "csv",
    limit: int = Query(1000, ge=1, le=5000),
    category: str | None = None,
    severity: str | None = None,
    result: str | None = None,
    username: str | None = None,
    query: str | None = None,
    current_user: dict = Depends(require_owner),
):
    user = current_username(current_user)
    data = load_shadow(user)
    fmt = str(format or "csv").lower()
    if fmt not in ALLOWED_EXPORT_FORMATS:
        fmt = "csv"
    items = _filtered_items(data, limit, category=category, severity=severity, result=result, username=username, query=query)
    manifest = audit_export_manifest(items, fmt, _filters_dict(category=category, severity=severity, result=result, username=username, query=query))
    chained_items = enrich_audit_chain(items)
    if fmt == "json":
        return {"status": "ok", "user": user, "format": "json", "items": chained_items, "count": len(chained_items), "manifest": manifest, "exported_at": manifest["exported_at"]}

    columns = ["time", "user", "role", "category", "severity", "action", "result", "page", "endpoint", "message", "request_id", "correlation_id"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for item in chained_items:
        writer.writerow({col: item.get(col, "") for col in columns})
    return {"status": "ok", "user": user, "format": "csv", "csv": output.getvalue(), "count": len(chained_items), "manifest": manifest, "exported_at": manifest["exported_at"]}


# --- Level1 Rev50 Audit Forensics Final endpoints ---
from services.observability_audit_logs_final_service import (
    build_audit_search_final,
    build_audit_retention_report,
    build_audit_tamper_warning_report,
    build_logs_operational_summary,
)


@router.get("/search-final")
def audit_search_final(
    query: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    result: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    payload = build_audit_search_final(load_shadow(user), query=query, category=category, severity=severity, result=result, limit=limit)
    payload["user"] = user
    return payload


@router.get("/retention")
def audit_retention(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_audit_retention_report(load_shadow(user))
    payload["user"] = user
    return payload


@router.get("/tamper-warning")
def audit_tamper_warning(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_audit_tamper_warning_report(load_shadow(user))
    payload["user"] = user
    return payload


@router.get("/logs-operational-summary")
def audit_logs_operational_summary(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_logs_operational_summary(load_shadow(user))
    payload["user"] = user
    return payload
