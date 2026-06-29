from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
import hashlib
import hmac
import os
import json


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")



def _stable_payload_hash(payload: dict, user: str | None = None, role: str | None = None, preview_id: str | None = None) -> str:
    safe = {
        "symbol": str((payload or {}).get("symbol") or "").upper().strip(),
        "side": str((payload or {}).get("side") or "").upper().strip(),
        "quote_order_qty": str((payload or {}).get("quote_order_qty") or ""),
        "user": str(user or (payload or {}).get("user") or ""),
        "role": str(role or (payload or {}).get("role") or ""),
        "preview_id": str(preview_id or (payload or {}).get("preview_id") or ""),
    }
    raw = json.dumps(safe, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _confirmation_secret() -> bytes:
    """Return the dedicated confirmation-token HMAC secret.

    Rev49 hardening deliberately avoids reusing exchange trading credentials.
    Trading API secrets must never be reused for local confirmation tokens.
    Production-like modes require CONFIRMATION_TOKEN_SECRET or WEBHOOK_SECRET.
    Local/offline quality checks may use a non-trading development fallback.
    """
    value = os.getenv("CONFIRMATION_TOKEN_SECRET") or os.getenv("WEBHOOK_SECRET")
    env_name = str(os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("HMTSTC_ENV") or "").lower()
    offline_quality = os.getenv("HMTSTC_OFFLINE_QUALITY_CHECK", "").lower() in {"1", "true", "yes"}
    prod_like = (env_name in {"prod", "production", "live"} or os.getenv("REAL_TRADING_ENABLED", "").lower() == "true") and not offline_quality
    if not value and prod_like:
        raise RuntimeError("CONFIRMATION_TOKEN_SECRET is required for production/live confirmation tokens.")
    if not value:
        value = "hmtstc-local-confirmation-dev-only"
    return str(value).encode("utf-8")


def _token_mac(token_id: str, payload_hash: str) -> str:
    raw = f"{token_id}:{payload_hash}".encode("utf-8")
    return hmac.new(_confirmation_secret(), raw, hashlib.sha256).hexdigest()[:8]


def default_real_trade_state() -> dict:
    return {
        "enabled": False,
        "dry_run": True,
        "owner_unlocked": False,
        "unlock_expires_at": None,
        "last_unlock_by": None,
        "last_unlock_at": None,
        "pilot": {
            "active": False,
            "started_at": None,
            "expires_at": None,
            "orders_count": 0,
            "daily_loss": 0,
            "locked_after_finish": True,
        },
        "positions": [],
        "orders": [],
        "daily_pnl": 0,
        "weekly_pnl": 0,
        "emergency_lock": False,
        "manual_attention_required": False,
        "confirmation_tokens": [],
        "last_readiness": None,
    }


def ensure_real_trade_state(data: dict) -> dict:
    if not isinstance(data, dict):
        data = {}
    state = data.setdefault("real_trade", {})
    defaults = default_real_trade_state()
    for key, value in defaults.items():
        if key not in state:
            state[key] = value
    state.setdefault("pilot", {}).update({k: state.get("pilot", {}).get(k, v) for k, v in defaults["pilot"].items()})
    if not isinstance(state.get("positions"), list):
        state["positions"] = []
    if not isinstance(state.get("orders"), list):
        state["orders"] = []
    if not isinstance(state.get("confirmation_tokens"), list):
        state["confirmation_tokens"] = []
    state["orders"] = state["orders"][-500:]
    state["positions"] = state["positions"][-300:]
    state["confirmation_tokens"] = state["confirmation_tokens"][-50:]
    return state


def is_unlock_valid(state: dict) -> bool:
    if not state.get("owner_unlocked"):
        return False
    expires = state.get("unlock_expires_at")
    if not expires:
        return False
    try:
        dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
        return datetime.now(dt.tzinfo) < dt
    except Exception:
        return False


def lock_real_trading(state: dict, reason: str = "manual_lock") -> dict:
    state["owner_unlocked"] = False
    state["unlock_expires_at"] = None
    state["lock_reason"] = reason
    state["locked_at"] = now_iso()
    state.setdefault("pilot", {})["active"] = False
    return state


def unlock_real_trading(state: dict, user: str, minutes: int = 30) -> dict:
    minutes = max(1, min(int(minutes or 30), 120))
    expires = datetime.now() + timedelta(minutes=minutes)
    state["owner_unlocked"] = True
    state["last_unlock_by"] = user
    state["last_unlock_at"] = now_iso()
    state["unlock_expires_at"] = expires.isoformat(timespec="seconds")
    state["lock_reason"] = None
    return state


def create_confirmation_token(state: dict, payload: dict, ttl_seconds: int = 60, user: str | None = None, role: str | None = None, preview_id: str | None = None) -> dict:
    expires = datetime.now() + timedelta(seconds=max(10, min(int(ttl_seconds or 60), 300)))
    token_id = uuid4().hex
    effective_preview_id = preview_id or str((payload or {}).get("preview_id") or f"preview_{uuid4().hex}")
    payload_hash = _stable_payload_hash(payload, user=user, role=role, preview_id=effective_preview_id)
    token = f"confirm_{token_id}.{_token_mac(token_id, payload_hash)}"
    item = {
        "token": token,
        "token_id": token_id,
        "preview_id": effective_preview_id,
        "payload_hash": payload_hash,
        "created_at": now_iso(),
        "expires_at": expires.isoformat(timespec="seconds"),
        "created_by": user,
        "role": role,
        "used": False,
        "payload": payload,
    }
    state.setdefault("confirmation_tokens", []).append(item)
    state["confirmation_tokens"] = state["confirmation_tokens"][-50:]
    return item


def consume_confirmation_token(state: dict, token: str, payload: dict, user: str | None = None, role: str | None = None, preview_id: str | None = None) -> dict:
    now = datetime.now()
    for item in state.get("confirmation_tokens", []) or []:
        if item.get("token") != token:
            continue
        if item.get("used"):
            return {"ok": False, "reason": "confirmation_token_used"}
        try:
            expires = datetime.fromisoformat(str(item.get("expires_at")).replace("Z", "+00:00"))
            if now >= expires.replace(tzinfo=None):
                return {"ok": False, "reason": "confirmation_token_expired"}
        except Exception:
            return {"ok": False, "reason": "confirmation_token_invalid_expiry"}
        token_id = str(item.get("token_id") or "")
        payload_hash = str(item.get("payload_hash") or "")
        if token_id and payload_hash:
            expected_token = f"confirm_{token_id}.{_token_mac(token_id, payload_hash)}"
            if token != expected_token:
                return {"ok": False, "reason": "confirmation_token_hmac_mismatch"}
            effective_preview_id = preview_id or item.get("preview_id")
            actual_hash = _stable_payload_hash(payload, user=user or item.get("created_by"), role=role or item.get("role"), preview_id=effective_preview_id)
            if actual_hash != payload_hash:
                return {"ok": False, "reason": "confirmation_token_payload_hash_mismatch"}
            if item.get("created_by") and user and item.get("created_by") != user:
                return {"ok": False, "reason": "confirmation_token_user_mismatch"}
            if item.get("preview_id") and preview_id and item.get("preview_id") != preview_id:
                return {"ok": False, "reason": "confirmation_token_preview_mismatch"}
        else:
            expected = item.get("payload") or {}
            for key in ["symbol", "side", "quote_order_qty"]:
                if str(expected.get(key)) != str(payload.get(key)):
                    return {"ok": False, "reason": "confirmation_token_payload_mismatch"}
        item["used"] = True
        item["used_at"] = now_iso()
        return {"ok": True, "token": token, "preview_id": item.get("preview_id"), "payload_hash": item.get("payload_hash")}
    return {"ok": False, "reason": "confirmation_token_not_found"}


def append_real_order(state: dict, order: dict) -> dict:
    orders = state.setdefault("orders", [])
    orders.append(order)
    state["orders"] = orders[-500:]
    return order


def append_real_position(state: dict, position: dict) -> dict:
    positions = state.setdefault("positions", [])
    positions.append(position)
    state["positions"] = positions[-300:]
    return position


def open_real_positions(state: dict) -> list[dict]:
    open_statuses = {"submitted", "acknowledged", "partially_filled", "filled", "open", "closing", "closing_requested", "closing_submitted", "closing_partially_filled", "manual_attention_required", "orphan_detected"}
    return [p for p in state.get("positions", []) or [] if str(p.get("status") or "").lower() in open_statuses]
