from fastapi import APIRouter, Depends

from core.auth import require_user
from core.config import DEFAULT_USER
from core.storage import load_shadow, load_settings
from services.summary_service import build_summary

router = APIRouter(prefix="/api", tags=["summary"])


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/summary")
def summary(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_summary(load_shadow(user), load_settings(user), user=user)
