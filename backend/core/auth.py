import hashlib
import hmac
import json
import os
import secrets
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, status

AUTH_FILE = Path(__file__).resolve().parents[1] / "auth_store.json"
_AUTH_STORE_LOCK = threading.RLock()
SUPER_ADMIN_USERNAME = "ahmet"  # username alanı "ahmet" olmalı (quotes/placeholder olmadan)
ADMIN_USERNAMES = {"admin"}


class AuthStoreWriteError(RuntimeError):
    pass


@contextmanager
def auth_store_lock():
    with _AUTH_STORE_LOCK:
        yield


def normalize_username(username: str | None) -> str:
    return str(username or "").strip().lower()


def is_platform_owner_username(username: str | None) -> bool:
    return normalize_username(username) == SUPER_ADMIN_USERNAME


def is_platform_admin_username(username: str | None) -> bool:
    return normalize_username(username) in ADMIN_USERNAMES


def effective_role(username: str | None, role: str | None = None) -> str:
    if is_platform_owner_username(username):
        return "owner"
    if is_platform_admin_username(username):
        return "admin"
    clean_role = str(role or "user").strip().lower()
    if clean_role == "admin":
        return "admin"
    return "user"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_auth_store() -> dict[str, Any]:
    with _AUTH_STORE_LOCK:
        if not AUTH_FILE.exists():
            return {"users": {}}

        try:
            with AUTH_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception:
            return {"users": {}}

        if not isinstance(data, dict):
            data = {}

        if not isinstance(data.get("users"), dict):
            data["users"] = {}

        return data


def write_auth_store(data: dict[str, Any]) -> None:
    with _AUTH_STORE_LOCK:
        AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = AUTH_FILE.with_name(
            f"{AUTH_FILE.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        )

        try:
            with temp_file.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)

            os.replace(temp_file, AUTH_FILE)
        except Exception as error:
            raise AuthStoreWriteError("auth_store yazılamadı") from error
        finally:
            try:
                if temp_file.exists():
                    temp_file.unlink(missing_ok=True)
            except Exception:
                pass


def hash_password(password: str, salt: str) -> str:
    raw = f"{salt}:{password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    calculated = hash_password(password, salt)
    return hmac.compare_digest(calculated, str(password_hash or ""))


def make_token(username: str) -> str:
    random_part = secrets.token_urlsafe(48)
    raw = f"{username}:{random_part}:{now_iso()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_user_record(username: str, password: str, role: str = "user") -> dict[str, Any]:
    salt = secrets.token_hex(16)
    clean_role = effective_role(username, role)

    return {
        "username": username,
        "salt": salt,
        "password_hash": hash_password(password, salt),
        "created_at": now_iso(),
        "last_login_at": None,
        "token": None,
        "role": clean_role,
        "active": True,
        "force_password_change": False,
    }


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    with _AUTH_STORE_LOCK:
        store = read_auth_store()
        users = store.setdefault("users", {})
        user_record = users.get(username)

        if not user_record:
            return None

        if user_record.get("active") is False and not is_platform_owner_username(username):
            return None

        if not verify_password(
            password,
            str(user_record.get("salt") or ""),
            str(user_record.get("password_hash") or ""),
        ):
            return None

        token = make_token(username)
        user_record["token"] = token
        user_record["last_login_at"] = now_iso()
        user_record["role"] = effective_role(username, user_record.get("role"))
        if is_platform_owner_username(username):
            user_record["active"] = True
            user_record["package"] = "owner"
        users[username] = user_record
        write_auth_store(store)

        return user_record


def bootstrap_owner(username: str, password: str) -> dict[str, Any]:
    with _AUTH_STORE_LOCK:
        store = read_auth_store()
        users = store.setdefault("users", {})

        if users:
            raise ValueError("Auth store boş değil; bootstrap yapılamaz.")

        user_record = create_user_record(SUPER_ADMIN_USERNAME, password, role="owner")
        user_record["token"] = make_token(SUPER_ADMIN_USERNAME)
        user_record["last_login_at"] = now_iso()
        users[SUPER_ADMIN_USERNAME] = user_record
        write_auth_store(store)

        return user_record


def extract_bearer_token(authorization: str | None) -> str:
    value = str(authorization or "").strip()

    if not value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token gerekli.",
        )

    parts = value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization formatı Bearer <token> olmalı.",
        )

    return parts[1].strip()


def require_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = extract_bearer_token(authorization)
    store = read_auth_store()

    for username, user_record in store.get("users", {}).items():
        stored_token = str(user_record.get("token") or "")

        if stored_token and hmac.compare_digest(stored_token, token):
            return {
                "username": username,
                "role": effective_role(username, user_record.get("role")),
                "created_at": user_record.get("created_at"),
                "last_login_at": user_record.get("last_login_at"),
                "active": user_record.get("active", True),
                "force_password_change": user_record.get("force_password_change", False),
            }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token geçersiz veya oturum kapatılmış.",
    )


def require_owner(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = require_user(authorization=authorization)

    if user.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için owner yetkisi gerekli.",
        )

    return user


def require_admin(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = require_user(authorization=authorization)

    if user.get("role") not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için admin veya owner yetkisi gerekli.",
        )

    return user


def public_auth_snapshot(user_record: dict[str, Any], authenticated: bool = True, bootstrap: bool = False) -> dict[str, Any]:
    return {
        "status": "ok",
        "authenticated": authenticated,
        "bootstrap": bootstrap,
        "username": user_record.get("username"),
        "token": user_record.get("token"),
        "role": effective_role(user_record.get("username"), user_record.get("role")),
        "created_at": user_record.get("created_at"),
        "last_login_at": user_record.get("last_login_at"),
        "active": user_record.get("active", True),
        "force_password_change": user_record.get("force_password_change", False),
    }
