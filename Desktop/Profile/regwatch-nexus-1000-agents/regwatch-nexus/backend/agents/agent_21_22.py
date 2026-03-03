"""
RegWatch Nexus — Agent 21: SEO Intelligence
Generates SEO metadata for every published alert. BACKEND ONLY.
"""
import json
import logging
import anthropic
from supabase_client import supabase_service
from config import config

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def generate_seo_for_pending():
    """Generate SEO meta for all alerts missing it."""
    alerts = supabase_service.table('alerts')\
        .select('id, title, summary, regulator, jurisdiction, severity, topic_tags')\
        .eq('validation_status', 'approved')\
        .is_('seo_meta', 'null')\
        .limit(50)\
        .execute()

    for alert in alerts.data:
        try:
            seo = generate_seo_for_alert(alert)
            supabase_service.table('alerts')\
                .update({'seo_meta': seo})\
                .eq('id', alert['id'])\
                .execute()
        except Exception as e:
            logger.error(f"[Agent 21] SEO generation failed for {alert['id']}: {e}")


def generate_seo_for_alert(alert: dict) -> dict:
    """Use Claude Haiku (fast+cheap) to generate SEO metadata."""
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL_FAST,
        max_tokens=800,
        messages=[{'role': 'user', 'content': f"""Generate SEO metadata for this regulatory alert page.
Return ONLY a valid JSON object with exactly these keys:
- "meta_title": SEO title under 60 chars including regulator name
- "meta_description": 155 char search snippet
- "og_title": Open Graph title (slightly more descriptive than meta_title)
- "faq": Array of 3 objects with "question" and "answer" keys
- "related_searches": Array of 5 search phrases

Alert title: {alert['title']}
Regulator: {alert['regulator']}
Jurisdiction: {alert['jurisdiction']}
Summary: {str(alert.get('summary', ''))[:400]}

Return ONLY valid JSON. No markdown."""}]
    )
    raw = response.content[0].text.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]
    return json.loads(raw)


"""
RegWatch Nexus — Agent 22: Trending Topics
Tracks public engagement and surfaces trending intelligence. BACKEND ONLY.
"""

def update_trending_topics():
    """Recalculate trending topics from page view data. Runs every 15 min."""
    try:
        # Aggregate page views by topic_tag for different time windows
        # In production this would use a proper analytics query
        # Simplified implementation using view_count from alerts table

        results = supabase_service.table('alerts')\
            .select('jurisdiction, affected_sectors, topic_tags, view_count, severity')\
            .eq('validation_status', 'approved')\
            .order('view_count', desc=True)\
            .limit(200)\
            .execute()

        topic_counts = {}
        for alert in results.data:
            jurisdiction = alert.get('jurisdiction', 'GLOBAL')
            for tag in (alert.get('topic_tags') or []):
                key = f"{jurisdiction}:{tag}"
                topic_counts[key] = topic_counts.get(key, 0) + (alert.get('view_count') or 0)

        # Upsert trending topics
        for key, count in sorted(topic_counts.items(), key=lambda x: -x[1])[:50]:
            jurisdiction, topic = key.split(':', 1)
            supabase_service.table('trending_topics').upsert({
                'topic': topic,
                'jurisdiction': jurisdiction,
                'view_count_24h': count,
                'trending_score': float(count),
            }, on_conflict='topic,jurisdiction').execute()

        logger.info(f"[Agent 22] Updated {len(topic_counts)} trending topics.")
    except Exception as e:
        logger.error(f"[Agent 22] Trending update failed: {e}")


def track_page_view(alert_id: str, jurisdiction: str, sector: str, session_id: str):
    """Record a page view for trending analysis."""
    try:
        # Increment view count on alert
        supabase_service.rpc('increment_view_count', {'alert_id': alert_id}).execute()

        # Log page view event
        supabase_service.table('page_views').insert({
            'alert_id': alert_id,
            'page_type': 'alert',
            'jurisdiction': jurisdiction,
            'sector': sector,
            'session_id': session_id,
        }).execute()
    except Exception as e:
        logger.warning(f"[Agent 22] View tracking failed: {e}")
