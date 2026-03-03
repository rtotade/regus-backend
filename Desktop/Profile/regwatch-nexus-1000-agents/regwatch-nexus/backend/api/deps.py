"""FastAPI dependencies"""
from typing import Optional, Annotated
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.services.auth import decode_token, get_plan_from_token
from backend.models.user import User
from backend.config import settings


async def get_current_user_optional(
    authorization: Annotated[Optional[str], Header()] = None,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    if not payload:
        return None
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    return result.scalar_one_or_none()


async def get_current_user(
    authorization: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
) -> User:
    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, 
                          detail="Invalid or expired token")
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


async def require_pro(user: User = Depends(get_current_user)) -> User:
    if user.plan not in (settings.PLAN_PRO, settings.PLAN_ENTERPRISE):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                          detail="Pro or Enterprise plan required")
    return user


async def require_enterprise(user: User = Depends(get_current_user)) -> User:
    if user.plan != settings.PLAN_ENTERPRISE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                          detail="Enterprise plan required")
    return user


def get_plan_from_auth(authorization: Annotated[Optional[str], Header()] = None) -> str:
    return get_plan_from_token(authorization)
