from fastapi import APIRouter, Depends

from core.auth import require_user
from core.config import DEFAULT_USER
from core.storage import load_settings, load_shadow, save_shadow
from services.agent_service import (
    build_agent_report,
    build_agent_status,
    chat_with_agent,
)
from services.ai_analyst_safe_mode_service import (
    build_ai_safe_mode_policy,
    build_ai_suggestion,
    build_paper_queue,
    build_prompt_log_report,
    enqueue_paper_suggestion,
)


router = APIRouter(
    prefix="/api/agent",
    tags=["agent"],
)


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


@router.get("/status")
def agent_status(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)

    result = build_agent_status(data, settings)
    result["user"] = user

    return result


@router.get("/report")
def agent_report(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)

    result = build_agent_report(data, settings, persist=False)
    result["user"] = user

    return result


@router.post("/report")
def create_agent_report(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)

    result = build_agent_report(data, settings, persist=True)
    save_shadow(data, user)

    result["user"] = user

    return result


@router.get("/chat")
def agent_chat_history(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    messages = data.get("agent_chat", [])

    if not isinstance(messages, list):
        messages = []

    return {
        "status": "ok",
        "user": user,
        "messages": messages[-30:],
    }


@router.post("/chat")
def agent_chat(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    message = str(payload.get("message") or "").strip()

    data = load_shadow(user)
    settings = load_settings(user)

    result = chat_with_agent(data, settings, message)
    save_shadow(data, user)

    result["user"] = user

    return result

@router.get("/safe-mode")
def agent_safe_mode_policy(current_user: dict = Depends(require_user)):
    payload = build_ai_safe_mode_policy()
    payload["user"] = current_username(current_user)
    return payload


@router.post("/suggestions")
def agent_suggestions(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    role = str(current_user.get("role") or "user")
    message = str(payload.get("message") or payload.get("prompt") or "").strip()
    data = load_shadow(user)
    data["username"] = user
    settings = load_settings(user)

    result = build_ai_suggestion(data, settings, message, user=user, role=role)
    save_shadow(data, user)
    result["user"] = user
    return result


@router.get("/paper-queue")
def agent_paper_queue(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = build_paper_queue(data, limit=limit)
    payload["user"] = user
    return payload


@router.post("/paper-queue")
def create_agent_paper_queue_item(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    role = str(current_user.get("role") or "user")
    message = str(payload.get("message") or payload.get("prompt") or "").strip()
    data = load_shadow(user)
    data["username"] = user
    settings = load_settings(user)

    result = enqueue_paper_suggestion(data, settings, message, user=user, role=role)
    save_shadow(data, user)
    result["user"] = user
    return result


@router.get("/prompt-log")
def agent_prompt_log(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = build_prompt_log_report(data, limit=limit)
    payload["user"] = user
    return payload
