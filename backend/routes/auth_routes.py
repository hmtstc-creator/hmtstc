from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from core.auth import (
    AuthStoreWriteError,
    authenticate_user,
    auth_store_lock,
    bootstrap_owner,
    create_user_record,
    effective_role,
    hash_password,
    public_auth_snapshot,
    read_auth_store,
    require_owner,
    require_user,
    write_auth_store,
)

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)


@router.post("/login")
def login(payload: dict):
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "").strip()

    if not username or not password:
        return {
            "status": "error",
            "authenticated": False,
            "message": "Kullanıcı adı ve şifre gerekli.",
        }

    try:
        with auth_store_lock():
            store = read_auth_store()
            users = store.setdefault("users", {})

            if not users:
                user_record = bootstrap_owner(username, password)
                return public_auth_snapshot(user_record, authenticated=True, bootstrap=True)

            user_record = authenticate_user(username, password)
    except AuthStoreWriteError:
        return JSONResponse(
            status_code=503,
            content={
                "authenticated": False,
                "status": "auth_store_error",
                "message": "Oturum başlatılamadı. Lütfen tekrar deneyin.",
            },
        )

    if not user_record:
        return {
            "status": "error",
            "authenticated": False,
            "message": "Kullanıcı adı veya şifre hatalı.",
        }

    return public_auth_snapshot(user_record, authenticated=True, bootstrap=False)


@router.post("/register")
def register(payload: dict, current_user: dict = Depends(require_owner)):
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "").strip()
    role = effective_role(username, str(payload.get("role") or "user").strip().lower())

    if not username or not password:
        return {
            "status": "error",
            "created": False,
            "message": "Kullanıcı adı ve şifre gerekli.",
        }

    with auth_store_lock():
        store = read_auth_store()
        users = store.setdefault("users", {})

        if username in users:
            return {
                "status": "error",
                "created": False,
                "message": "Bu kullanıcı zaten var.",
            }

        user_record = create_user_record(username, password, role=role)
        users[username] = user_record
        write_auth_store(store)

    return {
        "status": "created",
        "created": True,
        "username": username,
        "role": role,
        "created_by": current_user.get("username"),
    }


@router.get("/me")
def me(current_user: dict = Depends(require_user)):
    return {
        "status": "ok",
        "authenticated": True,
        "username": current_user.get("username"),
        "role": current_user.get("role", "user"),
        "created_at": current_user.get("created_at"),
        "last_login_at": current_user.get("last_login_at"),
        "active": current_user.get("active", True),
        "force_password_change": current_user.get("force_password_change", False),
    }


@router.post("/logout")
def logout(current_user: dict = Depends(require_user)):
    username = current_user.get("username")

    with auth_store_lock():
        store = read_auth_store()
        users = store.setdefault("users", {})

        if username in users:
            users[username]["token"] = None
            write_auth_store(store)

    return {
        "status": "ok",
        "logged_out": True,
    }


@router.post("/change-password")
def change_password(payload: dict, current_user: dict = Depends(require_user)):
    current_password = str(payload.get("current_password") or "").strip()
    new_password = str(payload.get("new_password") or "").strip()

    if not new_password or len(new_password) < 6:
        return {
            "status": "error",
            "changed": False,
            "message": "Yeni şifre en az 6 karakter olmalı.",
        }

    username = current_user.get("username")
    with auth_store_lock():
        store = read_auth_store()
        users = store.setdefault("users", {})
        record = users.get(username)

        if not record:
            return {"status": "error", "changed": False, "message": "Kullanıcı bulunamadı."}

        # Owner tarafından resetlenen hesaplarda current_password zorunlu değildir.
        if not record.get("force_password_change"):
            from core.auth import verify_password
            if not verify_password(current_password, str(record.get("salt") or ""), str(record.get("password_hash") or "")):
                return {"status": "error", "changed": False, "message": "Mevcut şifre hatalı."}

        salt = str(record.get("salt") or "")
        if not salt:
            from secrets import token_hex
            salt = token_hex(16)
            record["salt"] = salt

        record["password_hash"] = hash_password(new_password, salt)
        record["force_password_change"] = False
        users[username] = record
        write_auth_store(store)

    return {"status": "ok", "changed": True}
