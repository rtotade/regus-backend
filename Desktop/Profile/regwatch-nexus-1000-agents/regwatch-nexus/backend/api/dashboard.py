"""Pro+ dashboard routes"""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from backend.database import get_db
from backend.models.user import User
from backend.models.client import Client
from backend.models.action import ComplianceAction, ImpactReport
from backend.api.deps import require_pro
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/summary")
async def get_dashboard_summary(
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    client_id = user.client_id
    
    # Get compliance actions summary
    open_actions = await db.execute(
        select(func.count(ComplianceAction.id)).where(
            ComplianceAction.client_id == client_id,
            ComplianceAction.status != "done",
        ))
    
    critical_open = await db.execute(
        select(func.count(ComplianceAction.id)).where(
            ComplianceAction.client_id == client_id,
            ComplianceAction.priority == "critical",
            ComplianceAction.status != "done",
        ))
    
    # Get recent impact reports
    recent_impacts = await db.execute(
        select(ImpactReport)
        .where(ImpactReport.client_id == client_id)
        .order_by(desc(ImpactReport.created_at))
        .limit(10)
    )
    
    # Get client health score
    client_result = await db.execute(select(Client).where(Client.id == client_id))
    client = client_result.scalar_one_or_none()
    health_score = client.health_score if client else 100.0
    
    # Upcoming deadlines
    upcoming = await db.execute(
        select(ComplianceAction)
        .where(
            ComplianceAction.client_id == client_id,
            ComplianceAction.due_date >= datetime.utcnow().date(),
            ComplianceAction.status != "done",
        )
        .order_by(ComplianceAction.due_date)
        .limit(5)
    )
    
    return {
        "health_score": health_score,
        "open_actions": open_actions.scalar() or 0,
        "critical_open": critical_open.scalar() or 0,
        "upcoming_deadlines": [
            {"id": a.id, "title": a.title, "due_date": a.due_date.isoformat(),
             "priority": a.priority}
            for a in upcoming.scalars().all()
        ],
        "recent_alerts": [
            {"alert_id": r.alert_id, "score": r.client_impact_score,
             "financial_exposure": r.financial_exposure,
             "acknowledged": r.acknowledged}
            for r in recent_impacts.scalars().all()
        ],
    }
