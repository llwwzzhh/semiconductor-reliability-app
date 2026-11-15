"""认证路由：注册、登录、当前用户与配额。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_optional_user, quota_key, quota_snapshot
from ..models import User
from ..schemas import LoginRequest, MeResponse, RegisterRequest, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter()


def _token_response(response: Response, db: Session, user: User, request_key: str) -> TokenResponse:
    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        quota=quota_snapshot(db, request_key, user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册，请直接登录")

    username = payload.username.strip() or payload.email.split("@")[0]
    user = User(email=payload.email, username=username, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(response, db, user, f"user:{user.id}")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或口令不正确")
    return _token_response(response, db, user, f"user:{user.id}")


@router.get("/me", response_model=MeResponse)
def me(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """当前登录状态与今日配额；未登录也会返回匿名配额。"""
    request_key = quota_key(request, user)
    return MeResponse(
        authenticated=user is not None,
        user=UserOut.model_validate(user) if user else None,
        quota=quota_snapshot(db, request_key, user),
    )


@router.post("/logout")
def logout():
    """令牌为无状态 JWT，退出登录由客户端丢弃令牌完成。"""
    return {"ok": True}
