"""
RegWatch Nexus — Agent 07: Alert Dispatch
Sends personalised alerts to Registered+ users. BACKEND ONLY.
"""
import logging
import json
from config import config
from supabase_client import supabase_service
from integrations.sendgrid_client import send_alert_email

logger = logging.getLogger(__name__)


def dispatch_new_alerts():
    """Find approved alerts not yet dispatched and notify eligible users."""
    # Get newly approved alerts (last run)
    alerts = supabase_service.table('alerts')\
        .select('*')\
        .eq('validation_status', 'approved')\
        .eq('dispatched', False)\
        .order('published_at', desc=True)\
        .limit(50)\
        .execute()

    for alert in alerts.data:
        try:
            dispatch_alert(alert)
            supabase_service.table('alerts')\
                .update({'dispatched': True})\
                .eq('id', alert['id'])\
                .execute()
        except Exception as e:
            logger.error(f"[Agent 07] Dispatch failed for {alert['id']}: {e}")


def dispatch_alert(alert: dict):
    """Send alert to all users who should receive it."""
    # Get users with matching watchlist/saved filters
    users = supabase_service.table('users')\
        .select('*')\
        .in_('plan', ['free', 'pro', 'enterprise'])\
        .execute()

    for user in users.data:
        if should_notify_user(user, alert):
            send_alert_email(user['email'], alert, user.get('plan', 'free'))


def should_notify_user(user: dict, alert: dict) -> bool:
    """Check if user's watchlist/filters match this alert."""
    prefs = user.get('notification_prefs') or {}
    watchlist = user.get('watchlist') or []
    saved_filters = user.get('saved_filters') or {}

    # Free users: only weekly digest, no real-time
    if user.get('plan') == 'free':
        return False  # handled by weekly digest agent

    # Pro/Enterprise: check if alert matches any watchlist or filter
    if alert.get('regulator') in watchlist:
        return True
    if alert.get('jurisdiction') in (saved_filters.get('countries') or []):
        return True
    if any(s in (alert.get('affected_sectors') or []) for s in (saved_filters.get('sectors') or [])):
        return True

    # Always notify Pro/Enterprise of critical alerts in any country they care about
    if alert.get('severity') == 'critical':
        return True

    return False
