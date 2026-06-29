from fastapi import APIRouter, Depends

from core.auth import require_user
from core.config import DEFAULT_USER
from core.storage import load_shadow, load_settings
from services.observability_service import (
    build_deploy_report,
    build_endpoint_error_report,
    build_latency_report,
    build_observability_summary,
    build_stale_report,
)

router = APIRouter(prefix="/api/observability", tags=["observability"])


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/summary")
def observability_summary(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    payload = build_observability_summary(data, settings)
    payload["user"] = user
    return payload


@router.get("/latency")
def observability_latency(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_latency_report(load_shadow(user))


@router.get("/endpoint-errors")
def observability_endpoint_errors(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_endpoint_error_report(load_shadow(user))


@router.get("/stale")
def observability_stale(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_stale_report(load_shadow(user), load_settings(user))


@router.get("/deploy")
def observability_deploy(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_deploy_report(load_shadow(user))


# --- Level1 Rev50 Observability Final endpoints ---
from services.observability_audit_logs_final_service import (
    build_observability_final_report,
    build_observability_trend,
    build_observability_alerts,
    build_logs_operational_summary,
)


@router.get("/trend")
def observability_trend(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_observability_trend(load_shadow(user), load_settings(user))


@router.get("/alerts")
def observability_alerts(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_observability_alerts(load_shadow(user), load_settings(user))


@router.get("/final")
def observability_final(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_observability_final_report(load_shadow(user), load_settings(user))
    payload["user"] = user
    return payload


@router.get("/logs-summary")
def observability_logs_summary(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = build_logs_operational_summary(load_shadow(user))
    payload["user"] = user
    return payload
