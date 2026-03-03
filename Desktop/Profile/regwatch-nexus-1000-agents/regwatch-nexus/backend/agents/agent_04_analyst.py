"""Agent 04+05 — Regulatory Analyst + Validator"""
import json
import logging
from datetime import datetime
from typing import Optional
import anthropic
from backend.database import AsyncSessionLocal
from backend.models.alert import Alert, SourceDocument
from backend.config import settings
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ANALYST_PROMPT = """You are a regulatory intelligence analyst. Analyse this regulatory document and extract structured intelligence.

Document:
{content}

Return a JSON object with EXACTLY these fields:
{{
  "title": "Clear title for this regulatory alert (max 200 chars)",
  "summary": "4-paragraph summary: 1) What changed, 2) Who is affected, 3) Key requirements, 4) Timeline",
  "full_analysis": "Detailed 800-word analysis covering: regulatory context, compliance requirements, technical changes needed, business impact, and strategic implications",
  "severity": "critical|high|medium|info",
  "base_impact_score": <number 1-10>,
  "affected_sectors": ["list", "of", "sectors"],
  "topic_tags": ["list", "of", "topic", "tags"],
  "regulatory_deadline": "YYYY-MM-DD or null",
  "recommended_actions": {{
    "immediate": ["action1", "action2"],
    "within_30_days": ["action1", "action2"],
    "within_90_days": ["action1"]
  }},
  "jurisdiction": "2-letter ISO code",
  "regulator": "Regulator name",
  "is_regulatory": true|false,
  "confidence_score": <number 0-1>
}}

Severity guide: critical=major rule change with <90 days, high=significant change 90-180 days, medium=notable change >180 days, info=guidance/consultation only.
Return ONLY valid JSON. No markdown, no explanation."""


async def analyse_document(doc: SourceDocument) -> Optional[dict]:
    """Analyse a single source document using Claude"""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("No ANTHROPIC_API_KEY — skipping analysis")
        return None
    
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    try:
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL_SONNET,
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": ANALYST_PROMPT.format(content=doc.raw_content[:4000])
            }]
        )
        
        text = response.content[0].text.strip()
        # Remove markdown code blocks if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        return json.loads(text)
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for doc {doc.id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Analysis error for doc {doc.id}: {e}")
        return None


def validate_analysis(analysis: dict) -> tuple[bool, float]:
    """5-layer validation"""
    score = 0.0
    
    # L1: Schema validation
    required = ["title", "summary", "severity", "base_impact_score", 
                "jurisdiction", "regulator", "is_regulatory"]
    if all(k in analysis for k in required):
        score += 0.2
    else:
        return False, 0.0
    
    # L2: Content quality
    if len(analysis.get("summary", "")) > 100:
        score += 0.2
    
    # L3: Severity calibration
    if analysis.get("severity") in ("critical", "high", "medium", "info"):
        score += 0.2
    
    # L4: Impact score range
    impact = analysis.get("base_impact_score", 0)
    if 1 <= impact <= 10:
        score += 0.2
    
    # L5: Regulatory flag
    if analysis.get("is_regulatory", False):
        score += 0.2
    
    return score >= 0.6, score


async def process_pending_documents():
    """Process all unanalysed source documents"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SourceDocument)
            .where(SourceDocument.processed == False,
                   SourceDocument.processing_attempts < 3)
            .limit(50)
        )
        docs = result.scalars().all()
        
        logger.info(f"Processing {len(docs)} pending documents")
        
        for doc in docs:
            doc.processing_attempts += 1
            
            analysis = await analyse_document(doc)
            
            if not analysis:
                doc.error_message = "Analysis returned None"
                continue
            
            is_valid, val_score = validate_analysis(analysis)
            
            if not is_valid:
                doc.error_message = f"Validation failed (score: {val_score:.2f})"
                doc.processed = True  # Don't retry invalid docs
                continue
            
            # Create alert from analysis
            if analysis.get("is_regulatory", False):
                alert = Alert(
                    regulator=analysis.get("regulator", doc.source_name),
                    jurisdiction=analysis.get("jurisdiction", "XX"),
                    title=analysis.get("title", ""),
                    summary=analysis.get("summary", ""),
                    full_analysis=analysis.get("full_analysis"),
                    recommended_actions=analysis.get("recommended_actions"),
                    severity=analysis.get("severity", "info"),
                    base_impact_score=float(analysis.get("base_impact_score", 5.0)),
                    affected_sectors=analysis.get("affected_sectors", []),
                    topic_tags=analysis.get("topic_tags", []),
                    regulatory_deadline=analysis.get("regulatory_deadline"),
                    source_url=doc.url,
                    validated=True,
                    validation_score=val_score,
                    is_published=True,
                )
                db.add(alert)
            
            doc.processed = True
            doc.processed_at = datetime.utcnow()
        
        await db.commit()
        logger.info("Document processing complete")
