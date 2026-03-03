"""Ask Intelligence — natural language compliance search (Pro+)"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.database import get_db
from backend.models.user import User
from backend.models.alert import Alert
from backend.api.deps import require_pro
from backend.config import settings
import anthropic

router = APIRouter()


class CounselRequest(BaseModel):
    question: str
    jurisdiction: str = "GLOBAL"


@router.post("/ask")
async def ask_intelligence(
    req: CounselRequest,
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    # Rate limit check
    limit = (settings.COUNSEL_RATE_LIMIT_ENT if user.plan == "enterprise"
             else settings.COUNSEL_RATE_LIMIT_PRO)
    if user.counsel_queries_this_month >= limit:
        raise HTTPException(status_code=429, 
                          detail=f"Monthly query limit ({limit}) reached")
    
    # Fetch recent relevant alerts as context
    context_alerts = await db.execute(
        select(Alert).where(
            Alert.is_published == True,
            Alert.jurisdiction.in_([req.jurisdiction, "GLOBAL"]) if req.jurisdiction != "GLOBAL"
            else Alert.is_published == True
        ).order_by(desc(Alert.published_at)).limit(20)
    )
    alerts = context_alerts.scalars().all()
    
    alert_context = "\n\n".join([
        f"[{a.severity.upper()}] {a.regulator} ({a.jurisdiction}): {a.title}\n{a.summary[:300]}"
        for a in alerts
    ])
    
    model = (settings.ANTHROPIC_MODEL_OPUS if user.plan == "enterprise"
             else settings.ANTHROPIC_MODEL_SONNET)
    
    if not settings.ANTHROPIC_API_KEY:
        return {"answer": "Compliance Intelligence is processing your query. Please configure ANTHROPIC_API_KEY.",
                "sources": [], "queries_remaining": limit - user.counsel_queries_this_month - 1}
    
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system="""You are a compliance intelligence assistant. Answer questions about regulatory 
requirements using the provided alert context. Be precise, cite specific regulations, 
and focus on actionable guidance. Do NOT use AI terminology in your response.""",
        messages=[{
            "role": "user",
            "content": f"""Recent regulatory intelligence context:
{alert_context}

Question: {req.question}

Provide a clear, cited answer. Format as: 1) Direct answer 2) Key regulations involved 
3) Recommended actions. Keep it under 400 words."""
        }]
    )
    
    user.counsel_queries_this_month += 1
    
    return {
        "answer": response.content[0].text,
        "sources": [{"regulator": a.regulator, "title": a.title, "id": a.id} for a in alerts[:3]],
        "queries_remaining": limit - user.counsel_queries_this_month,
    }
