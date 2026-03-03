"""
RegWatch Nexus — Agent 04: Regulatory Analyst
Uses Claude Sonnet to analyse every raw regulatory document.
Produces structured alert with impact score, severity, actions.
BACKEND ONLY — never visible to any user.
"""
import json
import logging
from datetime import datetime, timezone
import anthropic
from supabase_client import supabase_service
from config import config

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

ANALYSIS_PROMPT = """You are a senior regulatory compliance expert analysing a regulatory document.

Regulatory Source: {source_name}
Jurisdiction: {jurisdiction}
Document Title: {title}
Document URL: {url}
Document Content:
{content}

Produce a structured JSON analysis with EXACTLY these fields:
{{
  "alert_title": "Clear, specific title under 120 chars describing what changed",
  "summary": "4-paragraph analysis: (1) What happened, (2) Who is affected and how, (3) Key requirements and deadlines, (4) Strategic implications",
  "full_analysis": "Detailed 800-word analysis covering: regulatory text breakdown, implementation requirements, enforcement risk, precedent context, cross-border implications",
  "severity": "critical|high|medium|info",
  "base_impact_score": 7.5,
  "affected_sectors": ["payments", "banking", "insurance", "capital_markets", "fintech", "nbfc"],
  "topic_tags": ["KYC", "AML", "reporting", "capital", "licensing"],
  "regulatory_deadline": "2025-12-31",
  "recommended_actions": [
    {{
      "action": "Review and update KYC procedures",
      "owner_team": "Compliance",
      "priority": "critical",
      "estimated_weeks": 4
    }}
  ],
  "financial_exposure_usd": 500000,
  "engineering_change_required": true,
  "cascade_risk": "medium",
  "related_regulations": ["Basel III", "PSD2"],
  "is_new_regulation": true
}}

Severity guide:
- critical: immediate action required, significant penalties, < 90 day deadline
- high: action required within 6 months, material compliance impact
- medium: action required within 12 months, operational adjustments
- info: monitoring only, no immediate action

base_impact_score: 1-10 float. 9-10 = industry-wide crisis. 7-8 = major change. 5-6 = significant. 3-4 = moderate. 1-2 = minor.

Return ONLY valid JSON. No markdown. No explanation."""


def analyse_pending_documents():
    """Process all unanalysed source documents. Called by scheduler every 35 min."""
    pending = supabase_service.table('source_documents')\
        .select('*')\
        .eq('processed', False)\
        .limit(50)\
        .execute()

    if not pending.data:
        logger.info("[Agent 04] No pending documents.")
        return 0

    processed = 0
    for doc in pending.data:
        try:
            analyse_document(doc)
            processed += 1
        except Exception as e:
            logger.error(f"[Agent 04] Failed to analyse {doc['id']}: {e}")
            # Mark as failed so we don't retry endlessly
            supabase_service.table('source_documents')\
                .update({'processed': True, 'process_error': str(e)})\
                .eq('id', doc['id'])\
                .execute()

    logger.info(f"[Agent 04] Analysed {processed} documents.")
    return processed


def analyse_document(doc: dict):
    """Analyse a single document using Claude and create an alert."""
    content = doc.get('raw_content', '') or doc.get('title', '')
    if len(content) < 50:
        # Too little content to analyse — mark as processed and skip
        supabase_service.table('source_documents')\
            .update({'processed': True})\
            .eq('id', doc['id'])\
            .execute()
        return

    prompt = ANALYSIS_PROMPT.format(
        source_name=doc['source_name'],
        jurisdiction=doc.get('jurisdiction', 'GLOBAL'),
        title=doc.get('title', ''),
        url=doc.get('url', ''),
        content=content[:4000],  # Claude context limit guard
    )

    response = client.messages.create(
        model=config.ANTHROPIC_MODEL_STANDARD,
        max_tokens=2000,
        messages=[{'role': 'user', 'content': prompt}]
    )

    raw_json = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw_json.startswith('```'):
        raw_json = raw_json.split('\n', 1)[1].rsplit('```', 1)[0]

    analysis = json.loads(raw_json)

    # Validate required fields
    if not analysis.get('alert_title') or not analysis.get('summary'):
        raise ValueError("Analysis missing required fields")

    # Create alert record
    alert = {
        'source_document_id': doc['id'],
        'regulator': doc.get('regulator', doc['source_name']),
        'jurisdiction': doc.get('jurisdiction', 'GLOBAL'),
        'source_url': doc.get('url', ''),
        'title': analysis['alert_title'],
        'summary': analysis['summary'],
        'full_analysis': analysis.get('full_analysis', ''),
        'severity': analysis.get('severity', 'medium'),
        'base_impact_score': float(analysis.get('base_impact_score', 5.0)),
        'affected_sectors': analysis.get('affected_sectors', []),
        'topic_tags': analysis.get('topic_tags', []),
        'regulatory_deadline': analysis.get('regulatory_deadline'),
        'recommended_actions': analysis.get('recommended_actions', []),
        'financial_exposure_usd': analysis.get('financial_exposure_usd'),
        'engineering_change_required': analysis.get('engineering_change_required', False),
        'cascade_risk': analysis.get('cascade_risk', 'low'),
        'related_regulations': analysis.get('related_regulations', []),
        'is_new_regulation': analysis.get('is_new_regulation', True),
        'validation_status': 'pending',
        'published_at': doc.get('published_at', datetime.now(timezone.utc).isoformat()),
        'view_count': 0,
    }

    supabase_service.table('alerts').insert(alert).execute()

    # Mark source document as processed
    supabase_service.table('source_documents')\
        .update({'processed': True})\
        .eq('id', doc['id'])\
        .execute()

    logger.info(f"[Agent 04] Alert created: {alert['title'][:60]} | Score: {alert['base_impact_score']}")
