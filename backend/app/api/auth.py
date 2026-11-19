from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import current_user, require_admin, password_hash, DUMMY_HASH, create_token
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["登入與帳號"])


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "viewer"] = "viewer"


class UserUpdate(BaseModel):
    role: Literal["admin", "viewer"]
    active: bool


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


def public_user(user):
    return {"id": user.id, "username": user.username, "role": user.role, "active": user.active}


@router.post("/login")
def login(payload: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    valid = password_hash.verify(payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        raise HTTPException(401, "帳號或密碼錯誤，或帳號已停用")
    return {"access_token": create_token(user, db), "token_type": "bearer", "user": public_user(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return public_user(user)


@router.post("/logout")
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.token_version += 1
    db.commit()
    return {"status": "ok"}


@router.put("/password")
def change_password(payload: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not password_hash.verify(payload.old_password, user.password_hash):
        raise HTTPException(400, "原密碼錯誤")
    user.password_hash = password_hash.hash(payload.new_password)
    user.token_version += 1
    db.commit()
    return {"status": "ok"}


@router.get("/users", dependencies=[Depends(require_admin)])
def users(db: Session = Depends(get_db)):
    return [public_user(user) for user in db.scalars(select(User).order_by(User.id))]


@router.post("/users", status_code=201, dependencies=[Depends(require_admin)])
def create_user(payload: NewUser, db: Session = Depends(get_db)):
    user = User(username=payload.username, password_hash=password_hash.hash(payload.password), role=payload.role)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "帳號已存在") from None
    return public_user(user)


@router.put("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(400, "不能變更自己的角色或停用自己")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "找不到帳號")
    user.role, user.active = payload.role, payload.active
    user.token_version += 1
    db.commit()
    return public_user(user)
