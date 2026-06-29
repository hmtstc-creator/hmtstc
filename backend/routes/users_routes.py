from fastapi import APIRouter, Depends, HTTPException

from services.package_service import PACKAGE_TEMPLATES, normalize_package, package_limits

from services.user_api_secret_layer_service import (
    build_user_api_secret_layer_quality,
    build_user_api_secret_summary,
    clear_user_api_connection,
    set_user_api_connection,
)

from core.auth import (
    create_user_record,
    effective_role,
    hash_password,
    read_auth_store,
    require_owner,
    require_user,
    write_auth_store,
)

router = APIRouter(prefix="/api/users", tags=["users"])


def public_user(username: str, record: dict) -> dict:
    role = effective_role(username, record.get("role"))
    return {
        "username": username,
        "role": role,
        "active": record.get("active", True),
        "created_at": record.get("created_at"),
        "last_login_at": record.get("last_login_at"),
        "force_password_change": record.get("force_password_change", False),
        "package": normalize_package(record.get("package", "owner" if role == "owner" else "demo"), role),
    }


@router.get("")
def list_users(current_user: dict = Depends(require_owner)):
    store = read_auth_store()
    users = store.setdefault("users", {})
    return {
        "status": "ok",
        "users": [public_user(username, record) for username, record in users.items()],
    }


@router.post("")
def create_user(payload: dict, current_user: dict = Depends(require_owner)):
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "").strip()
    role = str(payload.get("role") or "user").strip().lower()

    if not username or not password:
        raise HTTPException(status_code=400, detail="Kullanıcı adı ve şifre gerekli.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Şifre en az 6 karakter olmalı.")

    role = effective_role(username, role)

    store = read_auth_store()
    users = store.setdefault("users", {})

    if username in users:
        raise HTTPException(status_code=400, detail="Bu kullanıcı zaten var.")

    record = create_user_record(username, password, role=role)
    record["force_password_change"] = True
    record["package"] = "owner" if role == "owner" else str(payload.get("package") or "demo")
    users[username] = record
    write_auth_store(store)

    return {"status": "ok", "created": True, "user": public_user(username, record)}


@router.post("/{username}/reset-password")
def reset_password(username: str, payload: dict, current_user: dict = Depends(require_owner)):
    password = str(payload.get("password") or "").strip()
    if not password:
        raise HTTPException(status_code=400, detail="Yeni şifre gerekli.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Yeni şifre en az 6 karakter olmalı.")

    store = read_auth_store()
    users = store.setdefault("users", {})
    record = users.get(username)
    if not record:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")

    salt = str(record.get("salt") or "")
    if not salt:
        from secrets import token_hex
        salt = token_hex(16)
        record["salt"] = salt

    record["password_hash"] = hash_password(password, salt)
    record["token"] = None
    record["force_password_change"] = True
    users[username] = record
    write_auth_store(store)

    return {"status": "ok", "reset": True, "user": public_user(username, record)}


@router.post("/{username}/active")
def set_active(username: str, payload: dict, current_user: dict = Depends(require_owner)):
    active = bool(payload.get("active", True))
    store = read_auth_store()
    users = store.setdefault("users", {})
    record = users.get(username)
    if not record:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if username == current_user.get("username") and not active:
        raise HTTPException(status_code=400, detail="Kendi hesabını pasif yapamazsın.")
    record["active"] = active
    if not active:
        record["token"] = None
    users[username] = record
    write_auth_store(store)
    return {"status": "ok", "user": public_user(username, record)}


@router.get("/packages")
def list_packages(current_user: dict = Depends(require_owner)):
    return {"status": "ok", "packages": PACKAGE_TEMPLATES}


@router.post("/{username}/package")
def set_user_package(username: str, payload: dict, current_user: dict = Depends(require_owner)):
    package_id = str((payload or {}).get("package") or "demo")
    store = read_auth_store()
    users = store.setdefault("users", {})
    record = users.get(username)
    if not record:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if record.get("role") == "owner" and package_id != "owner":
        raise HTTPException(status_code=400, detail="Owner kullanıcının paketi düşürülemez.")
    if package_id not in PACKAGE_TEMPLATES:
        raise HTTPException(status_code=400, detail="Geçersiz paket.")
    record["package"] = package_id
    users[username] = record
    write_auth_store(store)
    return {"status": "ok", "user": public_user(username, record)}


@router.get("/me/package")
def my_package(current_user: dict = Depends(require_owner)):
    # Owner-only route by design for tenant/package administration.
    store = read_auth_store()
    username = current_user.get("username")
    record = (store.get("users") or {}).get(username, {})
    return {"status": "ok", "package": package_limits(record.get("package", "owner"), record.get("role", "owner"))}

@router.get("/me/api-connection")
def my_api_connection(current_user: dict = Depends(require_user)):
    username = current_user.get("username")
    store = read_auth_store()
    return {"status": "ok", "api_connection": build_user_api_secret_summary(store, username)}


@router.post("/me/api-connection")
def save_my_api_connection(payload: dict, current_user: dict = Depends(require_user)):
    username = current_user.get("username")
    store = read_auth_store()
    try:
        result = set_user_api_connection(store, username, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    if result.get("status") != "ok":
        raise HTTPException(status_code=400, detail=result.get("errors", []))
    write_auth_store(store)
    return result


@router.delete("/me/api-connection")
def delete_my_api_connection(current_user: dict = Depends(require_user)):
    username = current_user.get("username")
    store = read_auth_store()
    try:
        result = clear_user_api_connection(store, username)
    except KeyError:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    write_auth_store(store)
    return result


@router.get("/quality/api-secret-layer")
def user_api_secret_layer_quality(current_user: dict = Depends(require_owner)):
    return build_user_api_secret_layer_quality(read_auth_store())
