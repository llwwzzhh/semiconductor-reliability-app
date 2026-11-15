"""认证依赖与每日配额控制。"""

from __future__ import annotations

import hashlib
from datetime import date

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ANONYMOUS_DAILY_QUOTA, FREE_DAILY_QUOTA
from .database import get_db
from .models import DailyUsage, User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """仅接受 Authorization: Bearer 令牌，避免基于 Cookie 的 CSRF 面。"""
    if credentials is None:
        return None
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登录后才能访问该功能",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def quota_key(request: Request, user: User | None) -> str:
    """登录用户按账号计配额，匿名用户按 IP 哈希计配额（不落盘明文 IP）。"""
    if user is not None:
        return f"user:{user.id}"
    client_ip = request.client.host if request.client else "unknown"
    digest = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]
    return f"ip:{digest}"


def _today() -> date:
    return date.today()


def usage_count(db: Session, key: str) -> int:
    row = db.execute(
        select(DailyUsage).where(DailyUsage.quota_key == key, DailyUsage.usage_date == _today())
    ).scalar_one_or_none()
    return row.count if row else 0


def quota_snapshot(db: Session, key: str, user: User | None) -> dict[str, object]:
    limit = None if (user is not None and user.is_premium) else (FREE_DAILY_QUOTA if user else ANONYMOUS_DAILY_QUOTA)
    used = usage_count(db, key)
    return {
        "daily_limit": limit,
        "used": used,
        "remaining": None if limit is None else max(limit - used, 0),
        "unlimited": limit is None,
        "tier": "premium" if user is not None and user.is_premium else ("free" if user else "anonymous"),
    }


def enforce_quota(db: Session, key: str, user: User | None) -> dict[str, object]:
    snapshot = quota_snapshot(db, key, user)
    limit = snapshot["daily_limit"]
    if limit is not None and snapshot["used"] >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"今日免费计算次数已用完（{limit} 次/天）。"
                "登录后可获得更高额度，升级专业版可无限使用。"
            ),
        )
    return snapshot


def record_usage(db: Session, key: str) -> None:
    row = db.execute(
        select(DailyUsage).where(DailyUsage.quota_key == key, DailyUsage.usage_date == _today())
    ).scalar_one_or_none()
    if row is None:
        db.add(DailyUsage(quota_key=key, usage_date=_today(), count=1))
    else:
        row.count += 1
    db.commit()
