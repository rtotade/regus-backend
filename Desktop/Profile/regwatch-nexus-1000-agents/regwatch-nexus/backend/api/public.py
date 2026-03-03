"""Public API routes — no authentication required"""
from typing import Optional, Annotated
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, update
from backend.database import get_db
from backend.models.alert import Alert
from backend.models.intelligence import TrendingTopic, PageView, ConsultingSynthesis
from backend.services.plan_filter import filter_alert, filter_synthesis
from backend.api.deps import get_plan_from_auth
import uuid

router = APIRouter()


def alert_to_dict(alert: Alert) -> dict:
    return {
        "id": alert.id, "regulator": alert.regulator,
        "jurisdiction": alert.jurisdiction, "title": alert.title,
        "summary": alert.summary, "full_analysis": alert.full_analysis,
        "recommended_actions": alert.recommended_actions,
        "severity": alert.severity, "base_impact_score": alert.base_impact_score,
        "affected_sectors": alert.affected_sectors, "topic_tags": alert.topic_tags,
        "regulatory_deadline": alert.regulatory_deadline,
        "source_url": alert.source_url, "seo_meta": alert.seo_meta,
        "cascade_predictions": alert.cascade_predictions,
        "view_count": alert.view_count,
        "published_at": alert.published_at.isoformat() if alert.published_at else None,
    }


@router.get("/alerts")
async def list_alerts(
    country: Optional[str] = Query(None, description="ISO country code e.g. IN, GB, US"),
    sector: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    plan: str = Depends(get_plan_from_auth),
    db: AsyncSession = Depends(get_db),
):
    q = select(Alert).where(Alert.is_published == True)
    if country:
        q = q.where(Alert.jurisdiction == country.upper())
    if severity:
        q = q.where(Alert.severity == severity.lower())
    q = q.order_by(desc(Alert.published_at))
    q = q.offset((page - 1) * per_page).limit(per_page)
    
    result = await db.execute(q)
    alerts = result.scalars().all()
    
    count_q = select(func.count(Alert.id)).where(Alert.is_published == True)
    if country:
        count_q = count_q.where(Alert.jurisdiction == country.upper())
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0
    
    return {
        "alerts": [filter_alert(alert_to_dict(a), plan) for a in alerts],
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/alerts/{alert_id}")
async def get_alert(
    alert_id: str, request: Request,
    plan: str = Depends(get_plan_from_auth),
    db: AsyncSession = Depends(get_db),
    x_session_id: Annotated[Optional[str], Header()] = None,
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Increment view count
    await db.execute(update(Alert).where(Alert.id == alert_id).values(
        view_count=Alert.view_count + 1))
    
    # Track page view for trending
    pv = PageView(
        alert_id=alert_id, page_type="alert",
        jurisdiction=alert.jurisdiction,
        session_id=x_session_id or str(uuid.uuid4()),
    )
    db.add(pv)
    
    # Related alerts
    related_q = select(Alert).where(
        Alert.jurisdiction == alert.jurisdiction,
        Alert.id != alert_id,
        Alert.is_published == True
    ).order_by(desc(Alert.published_at)).limit(5)
    related_result = await db.execute(related_q)
    related = related_result.scalars().all()
    
    return {
        "alert": filter_alert(alert_to_dict(alert), plan),
        "related": [{"id": r.id, "title": r.title, "severity": r.severity,
                     "regulator": r.regulator, "published_at": r.published_at.isoformat()} 
                    for r in related],
        "user_plan": plan,
    }


@router.get("/trending")
async def get_trending(
    country: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(TrendingTopic).order_by(desc(TrendingTopic.trending_score)).limit(10)
    result = await db.execute(q)
    topics = result.scalars().all()
    return [{"topic": t.topic, "jurisdiction": t.jurisdiction,
             "trending_score": t.trending_score, "view_count_24h": t.view_count_24h}
            for t in topics]


@router.get("/intelligence")
async def list_intelligence(
    industry: Optional[str] = Query(None),
    firm: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    plan: str = Depends(get_plan_from_auth),
    db: AsyncSession = Depends(get_db),
):
    q = select(ConsultingSynthesis).order_by(desc(ConsultingSynthesis.published_at))
    if firm:
        q = q.where(ConsultingSynthesis.firm_slug == firm.lower())
    q = q.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    items = result.scalars().all()
    
    return {
        "intelligence": [filter_synthesis({
            "id": i.id, "firm_slug": i.firm_slug, "firm_name": i.firm_name,
            "topic": i.topic, "summary_public": i.summary_public,
            "full_synthesis": i.full_synthesis,
            "industry_tags": i.industry_tags, "geography_tags": i.geography_tags,
            "source_url": i.source_url,
            "published_at": i.published_at.isoformat() if i.published_at else None,
        }, plan) for i in items],
        "page": page,
    }


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Platform stats for homepage display"""
    from datetime import datetime, timedelta
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    alerts_today = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.published_at >= today, Alert.is_published == True))
    total_alerts = await db.execute(
        select(func.count(Alert.id)).where(Alert.is_published == True))
    
    return {
        "alerts_today": alerts_today.scalar() or 0,
        "total_alerts": total_alerts.scalar() or 0,
        "countries_covered": 80,
        "sources_monitored": 210,
        "last_updated_mins_ago": 4,
    }


@router.get("/search")
async def search(
    q: str = Query(..., min_length=2),
    country: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    plan: str = Depends(get_plan_from_auth),
    db: AsyncSession = Depends(get_db),
):
    query = select(Alert).where(
        Alert.is_published == True,
        Alert.title.ilike(f"%{q}%")
    ).order_by(desc(Alert.published_at)).offset((page-1)*20).limit(20)
    
    if country:
        query = query.where(Alert.jurisdiction == country.upper())
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    return {
        "results": [filter_alert(alert_to_dict(a), plan) for a in alerts],
        "query": q, "page": page,
    }


@router.post("/track")
async def track_view(
    request: Request, db: AsyncSession = Depends(get_db),
    x_session_id: Annotated[Optional[str], Header()] = None,
):
    body = await request.json()
    pv = PageView(
        alert_id=body.get("alert_id"),
        page_type=body.get("page_type", "page"),
        jurisdiction=body.get("jurisdiction"),
        session_id=x_session_id or str(uuid.uuid4()),
    )
    db.add(pv)
    return {"ok": True}
