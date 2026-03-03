"""Reports — public summaries + Pro PDF access"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.database import get_db
from backend.models.report import Report
from backend.models.user import User
from backend.api.deps import get_current_user_optional, require_pro
from backend.services.storage import get_presigned_url

router = APIRouter()


@router.get("/")
async def list_reports(
    jurisdiction: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    q = select(Report).order_by(desc(Report.created_at)).limit(20)
    if jurisdiction:
        q = q.where(Report.jurisdiction == jurisdiction.upper())
    result = await db.execute(q)
    reports = result.scalars().all()
    
    plan = user.plan if user else "anonymous"
    is_pro = plan in ("pro", "enterprise")
    
    return [{
        "id": r.id, "title": r.title, "report_type": r.report_type,
        "jurisdiction": r.jurisdiction,
        "summary_public": r.summary_public,
        "has_pdf": bool(r.s3_key),
        "pdf_available": is_pro and bool(r.s3_key),
        "created_at": r.created_at.isoformat(),
    } for r in reports]


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report or not report.s3_key:
        raise HTTPException(status_code=404, detail="Report not found")
    
    url = get_presigned_url(report.s3_key)
    return {"download_url": url, "expires_in": 3600}
