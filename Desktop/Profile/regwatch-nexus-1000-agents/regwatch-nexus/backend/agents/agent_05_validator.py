"""
RegWatch Nexus — Agent 05: 5-Layer Validator
Validates alerts before they go public. BACKEND ONLY.
"""
import logging
from supabase_client import supabase_service

logger = logging.getLogger(__name__)


def validate_pending_alerts():
    """Validate all pending alerts. Called by scheduler every 40 min."""
    pending = supabase_service.table('alerts')\
        .select('*')\
        .eq('validation_status', 'pending')\
        .limit(100)\
        .execute()

    approved = 0
    for alert in pending.data:
        try:
            result = validate_alert(alert)
            if result == 'approved':
                approved += 1
        except Exception as e:
            logger.error(f"[Agent 05] Validation error for {alert['id']}: {e}")

    logger.info(f"[Agent 05] Validated batch. {approved} approved.")
    return approved


def validate_alert(alert: dict) -> str:
    """Run 5-layer validation. Returns 'approved', 'review', or 'rejected'."""

    # L1: Schema validation
    required_fields = ['title', 'summary', 'severity', 'base_impact_score', 'jurisdiction']
    for field in required_fields:
        if not alert.get(field):
            update_status(alert['id'], 'rejected', f'Missing required field: {field}')
            return 'rejected'

    # L2: Content quality check
    if len(alert.get('summary', '')) < 100:
        update_status(alert['id'], 'rejected', 'Summary too short — likely parsing error')
        return 'rejected'

    if alert.get('base_impact_score', 0) < 1 or alert.get('base_impact_score', 0) > 10:
        update_status(alert['id'], 'rejected', 'Impact score out of range')
        return 'rejected'

    # L3: Severity calibration
    score = float(alert.get('base_impact_score', 5))
    severity = alert.get('severity', 'medium')
    severity_score_map = {
        'critical': (7.5, 10),
        'high': (5.5, 8.5),
        'medium': (3.0, 7.0),
        'info': (1.0, 5.0),
    }
    expected_range = severity_score_map.get(severity, (1, 10))
    if not (expected_range[0] <= score <= expected_range[1]):
        # Recalibrate severity based on score
        if score >= 8.0:
            severity = 'critical'
        elif score >= 6.0:
            severity = 'high'
        elif score >= 3.5:
            severity = 'medium'
        else:
            severity = 'info'
        supabase_service.table('alerts')\
            .update({'severity': severity})\
            .eq('id', alert['id'])\
            .execute()

    # L4: Human review gate for critical/very high impact
    if score >= 8.5:
        update_status(alert['id'], 'human_review', 'High impact score — requires manual review')
        # In production: send to ops Slack channel
        logger.warning(f"[Agent 05] HUMAN REVIEW REQUIRED: {alert['title'][:60]} | Score: {score}")
        return 'review'

    # L5: Auto-approve
    update_status(alert['id'], 'approved', '')
    return 'approved'


def update_status(alert_id: str, status: str, reason: str):
    supabase_service.table('alerts')\
        .update({'validation_status': status, 'validation_reason': reason})\
        .eq('id', alert_id)\
        .execute()
