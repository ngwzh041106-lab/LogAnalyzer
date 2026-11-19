import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.models.user import User
from app.core.private_settings import read_private, write_private, migrate_private

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("unused-dummy-password")
bearer = HTTPBearer(auto_error=False)
TOKEN_MINUTES = 60


def init_auth():
    with SessionLocal() as db:
        migrate_private(db)
    if not read_private().get("JWT_SECRET"):
        write_private({"JWT_SECRET": secrets.token_urlsafe(48)})


def signing_key(db):
    key = read_private().get("JWT_SECRET")
    if not key:
        raise HTTPException(503, "登入服務尚未初始化")
    return key


def create_token(user, db):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "ver": user.token_version,
                       "iat": now, "exp": now + timedelta(minutes=TOKEN_MINUTES)},
                      signing_key(db), algorithm="HS256")


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(401, "請登入，或登入已過期", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None:
        raise unauthorized
    try:
        claims = jwt.decode(credentials.credentials, signing_key(db), algorithms=["HS256"],
                            options={"require": ["sub", "exp", "iat", "ver"]})
        user = db.get(User, int(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized from None
    if not user or not user.active or claims["ver"] != user.token_version:
        raise unauthorized
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "此操作需要管理員權限")
    return user


def protect_api(request: Request, user: User = Depends(current_user)):
    # Preview can execute a shell command, so it is not a read-only operation.
    path = request.url.path.rstrip("/")
    read_only = request.method == "GET" and (
        path == "/api/health" or path == "/api/log-sources"
        or (path.startswith("/api/log-sources/") and path.split("/")[-1].isdigit())
        or path == "/api/summaries"
        or (path.startswith("/api/summaries/") and path.split("/")[-1].isdigit())
    )
    if not read_only and user.role != "admin":
        raise HTTPException(403, "此操作需要管理員權限")
