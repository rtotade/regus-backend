"""Internal admin routes — protected by admin key"""
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from backend.database import get_db
from backend.models.alert import Alert, SourceDocument
from backend.models.user import User
from backend.config import settings

router = APIRouter()


def require_admin(x_admin_key: Optional[str] = Header(None)):
    if x_admin_key != settings.SECRET_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/stats", dependencies=[Depends(require_admin)])
async def admin_stats(db: AsyncSession = Depends(get_db)):
    total_alerts = await db.execute(select(func.count(Alert.id)))
    total_users = await db.execute(select(func.count(User.id)))
    pro_users = await db.execute(
        select(func.count(User.id)).where(User.plan.in_(["pro", "enterprise"])))
    unprocessed = await db.execute(
        select(func.count(SourceDocument.id)).where(SourceDocument.processed == False))
    return {
        "total_alerts": total_alerts.scalar() or 0,
        "total_users": total_users.scalar() or 0,
        "pro_users": pro_users.scalar() or 0,
        "unprocessed_docs": unprocessed.scalar() or 0,
    }


@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(
    page: int = Query(1, ge=1), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(User).order_by(desc(User.created_at)).offset((page-1)*50).limit(50))
    users = result.scalars().all()
    return [{"id": u.id, "email": u.email, "plan": u.plan,
             "company_name": u.company_name, "created_at": u.created_at.isoformat()}
            for u in users]
