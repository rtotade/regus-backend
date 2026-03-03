"""Agent 11 — Consulting Intelligence Synthesiser"""
import json
import logging
from datetime import datetime
import anthropic
from backend.database import AsyncSessionLocal
from backend.models.intelligence import ConsultingSynthesis
from backend.sources.consulting_sources import CONSULTING_SOURCES
from backend.config import settings

logger = logging.getLogger(__name__)


async def synthesise_consulting_intelligence():
    """Generate public summaries from consulting firm intelligence"""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY")
        return
    
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    async with AsyncSessionLocal() as db:
        for firm in CONSULTING_SOURCES[:10]:  # Process top 10 firms
            try:
                response = client.messages.create(
                    model=settings.ANTHROPIC_MODEL_HAIKU,
                    max_tokens=800,
                    messages=[{
                        "role": "user",
                        "content": f"""Based on known published research from {firm["name"]}, 
generate a current regulatory intelligence summary for the financial services sector.

Return JSON:
{{
  "topic": "Primary regulatory topic this firm is focusing on",
  "summary_public": "2-paragraph public summary of their regulatory insights (150 words)",
  "industry_tags": ["list", "of", "industries"],
  "geography_tags": ["list", "of", "countries"]
}}

Return ONLY valid JSON."""
                    }]
                )
                
                text = response.content[0].text.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                
                data = json.loads(text)
                
                synthesis = ConsultingSynthesis(
                    firm_slug=firm["slug"],
                    firm_name=firm["name"],
                    topic=data.get("topic", "Regulatory Compliance"),
                    summary_public=data.get("summary_public", ""),
                    industry_tags=data.get("industry_tags", []),
                    geography_tags=data.get("geography_tags", []),
                    published_at=datetime.utcnow(),
                )
                db.add(synthesis)
                
            except Exception as e:
                logger.error(f"Synthesis error for {firm['name']}: {e}")
        
        await db.commit()
        logger.info("Consulting synthesis complete")
