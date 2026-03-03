"""Compliance actions management"""
from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.database import get_db
from backend.models.user import User
from backend.models.action import ComplianceAction
from backend.api.deps import require_pro

router = APIRouter()


class ActionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    owner_team: Optional[str] = None
    assignee: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


@router.get("/")
async def list_actions(
    status: Optional[str] = None,
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    q = select(ComplianceAction).where(
        ComplianceAction.client_id == user.client_id
    ).order_by(desc(ComplianceAction.created_at))
    if status:
        q = q.where(ComplianceAction.status == status)
    result = await db.execute(q)
    actions = result.scalars().all()
    return [{"id": a.id, "alert_id": a.alert_id, "title": a.title,
             "description": a.description, "owner_team": a.owner_team,
             "assignee": a.assignee, "status": a.status, "priority": a.priority,
             "due_date": a.due_date.isoformat() if a.due_date else None,
             "notes": a.notes,
             "created_at": a.created_at.isoformat()} for a in actions]


@router.patch("/{action_id}")
async def update_action(
    action_id: str, req: ActionUpdate,
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ComplianceAction).where(
            ComplianceAction.id == action_id,
            ComplianceAction.client_id == user.client_id,
        ))
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(action, field, value)
    return {"ok": True, "id": action_id}
