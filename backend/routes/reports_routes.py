from __future__ import annotations

from fastapi import APIRouter, Depends

from core.auth import require_user
from core.config import DEFAULT_USER
from core.storage import load_settings, load_shadow
from services.eight_hour_report_service import (
    generate_eight_hour_report,
    history_eight_hour_reports,
    latest_eight_hour_report,
)


router = APIRouter(prefix="/api/reports", tags=["reports"])


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/eight-hour/latest")
def get_latest_eight_hour_report(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return latest_eight_hour_report(user, load_shadow(user), load_settings(user))


@router.get("/eight-hour/history")
def get_eight_hour_report_history(limit: int = 20, current_user: dict = Depends(require_user)):
    return history_eight_hour_reports(limit=limit)


@router.post("/eight-hour/generate")
def generate_eight_hour_report_endpoint(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    payload = payload if isinstance(payload, dict) else {}
    return generate_eight_hour_report(user, load_shadow(user), load_settings(user), force=bool(payload.get("force")))
