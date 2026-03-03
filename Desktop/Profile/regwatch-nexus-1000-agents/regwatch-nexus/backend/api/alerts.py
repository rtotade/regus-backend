"""Alerts — additional Pro endpoints"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.database import get_db
from backend.models.user import User
from backend.models.action import ImpactReport
from backend.api.deps import require_pro

router = APIRouter()


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(ImpactReport)
        .where(ImpactReport.alert_id == alert_id,
               ImpactReport.client_id == user.client_id)
        .values(acknowledged=True)
    )
    return {"ok": True}
