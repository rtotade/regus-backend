"""Agent 14 — Monthly Intelligence Report Generator"""
import logging
from datetime import datetime, timedelta
import anthropic
from backend.database import AsyncSessionLocal
from backend.models.alert import Alert
from backend.models.report import Report
from backend.models.user import User
from backend.services.storage import upload_pdf
from backend.config import settings
from sqlalchemy import select, desc

logger = logging.getLogger(__name__)


async def generate_monthly_reports():
    """Generate monthly intelligence reports for Pro/Enterprise users"""
    if not settings.ANTHROPIC_API_KEY:
        return
    
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    # Get last month's alerts
    last_month = datetime.utcnow() - timedelta(days=30)
    async with AsyncSessionLocal() as db:
        alerts_result = await db.execute(
            select(Alert)
            .where(Alert.published_at >= last_month, Alert.is_published == True)
            .order_by(desc(Alert.base_impact_score))
            .limit(50)
        )
        alerts = alerts_result.scalars().all()
        
        if not alerts:
            return
        
        alert_context = "\n\n".join([
            f"[{a.severity.upper()}] {a.regulator} ({a.jurisdiction}): {a.title}"
            for a in alerts[:20]
        ])
        
        try:
            response = client.messages.create(
                model=settings.ANTHROPIC_MODEL_SONNET,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": f"""Generate a monthly regulatory intelligence report summary based on these alerts:

{alert_context}

Write a 300-word executive summary covering:
1. Top 3 regulatory themes this month
2. Most impactful jurisdictions  
3. Key deadlines coming up
4. Strategic outlook for next 30 days

Write for a compliance professional. No AI terminology."""
                }]
            )
            
            summary = response.content[0].text
            month_str = datetime.utcnow().strftime("%B %Y")
            
            report = Report(
                title=f"Regulatory Intelligence Report — {month_str}",
                report_type="monthly",
                summary_public=summary[:500],
                is_public_summary=True,
            )
            db.add(report)
            await db.commit()
            
            logger.info(f"Monthly report generated for {month_str}")
        
        except Exception as e:
            logger.error(f"Report generation error: {e}")
