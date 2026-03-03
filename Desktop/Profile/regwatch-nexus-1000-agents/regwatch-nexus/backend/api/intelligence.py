"""Intelligence routes"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.database import get_db
from backend.models.intelligence import ConsultingSynthesis
from backend.api.deps import get_plan_from_auth

router = APIRouter()


@router.get("/firms")
async def list_firms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ConsultingSynthesis.firm_slug, ConsultingSynthesis.firm_name)
        .distinct().order_by(ConsultingSynthesis.firm_name)
    )
    return [{"slug": r[0], "name": r[1]} for r in result.fetchall()]
