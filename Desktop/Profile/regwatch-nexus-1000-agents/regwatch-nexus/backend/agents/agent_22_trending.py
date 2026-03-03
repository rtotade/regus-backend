"""Agent 22 — Trending Topics Engine"""
import logging
from datetime import datetime, timedelta
from backend.database import AsyncSessionLocal
from backend.models.intelligence import PageView, TrendingTopic
from backend.models.alert import Alert
from sqlalchemy import select, func, desc
from sqlalchemy.dialects.postgresql import insert

logger = logging.getLogger(__name__)


async def update_trending_topics():
    """Update trending topics based on recent page views"""
    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(hours=24)
        
        # Get most viewed alerts in last 24h
        trending_q = await db.execute(
            select(
                PageView.alert_id,
                PageView.jurisdiction,
                func.count(PageView.id).filter(PageView.viewed_at >= hour_ago).label("count_1h"),
                func.count(PageView.id).label("count_24h"),
            )
            .where(
                PageView.viewed_at >= day_ago,
                PageView.alert_id.isnot(None)
            )
            .group_by(PageView.alert_id, PageView.jurisdiction)
            .order_by(desc("count_24h"))
            .limit(20)
        )
        
        rows = trending_q.fetchall()
        
        for row in rows:
            alert_result = await db.execute(
                select(Alert.topic_tags, Alert.title)
                .where(Alert.id == row.alert_id)
            )
            alert = alert_result.first()
            if not alert or not alert.topic_tags:
                continue
            
            for topic in (alert.topic_tags or [])[:3]:
                # Calculate trending score (recency-weighted)
                score = (row.count_1h * 3.0) + row.count_24h
                
                existing = await db.execute(
                    select(TrendingTopic).where(
                        TrendingTopic.topic == topic,
                        TrendingTopic.jurisdiction == (row.jurisdiction or "GLOBAL")
                    )
                )
                tt = existing.scalar_one_or_none()
                
                if tt:
                    tt.view_count_1h = row.count_1h
                    tt.view_count_24h = row.count_24h
                    tt.trending_score = score
                    tt.updated_at = now
                else:
                    tt = TrendingTopic(
                        topic=topic,
                        jurisdiction=row.jurisdiction or "GLOBAL",
                        view_count_1h=row.count_1h,
                        view_count_24h=row.count_24h,
                        trending_score=score,
                    )
                    db.add(tt)
        
        await db.commit()
        logger.info(f"Trending topics updated: {len(rows)} patterns processed")
