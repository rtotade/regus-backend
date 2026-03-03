"""
RegWatch Nexus — APScheduler
Manages all 22 backend agent schedules. BACKEND ONLY.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone='UTC')


def start_scheduler():
    """Register all agent jobs and start the scheduler."""
    from agents.agent_01_regulatory_crawler import crawl_all_regulators
    from agents.agent_04_regulatory_analyst import analyse_pending_documents
    from agents.agent_05_validator import validate_pending_alerts
    from agents.agent_07_dispatch import dispatch_new_alerts
    from agents.agent_21_22 import generate_seo_for_pending, update_trending_topics

    # Agent 01: Regulatory Crawler — every 30 min
    scheduler.add_job(
        crawl_all_regulators,
        IntervalTrigger(minutes=30),
        id='agent_01',
        name='Regulatory Crawler',
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Agent 04: Regulatory Analyst — every 35 min (after crawl)
    scheduler.add_job(
        analyse_pending_documents,
        IntervalTrigger(minutes=35),
        id='agent_04',
        name='Regulatory Analyst',
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Agent 05: Validator — every 40 min
    scheduler.add_job(
        validate_pending_alerts,
        IntervalTrigger(minutes=40),
        id='agent_05',
        name='5-Layer Validator',
        replace_existing=True,
    )

    # Agent 07: Dispatch — every 45 min
    scheduler.add_job(
        dispatch_new_alerts,
        IntervalTrigger(minutes=45),
        id='agent_07',
        name='Alert Dispatch',
        replace_existing=True,
    )

    # Agent 21: SEO generation — every hour
    scheduler.add_job(
        generate_seo_for_pending,
        IntervalTrigger(hours=1),
        id='agent_21',
        name='SEO Intelligence',
        replace_existing=True,
    )

    # Agent 22: Trending topics — every 15 min
    scheduler.add_job(
        update_trending_topics,
        IntervalTrigger(minutes=15),
        id='agent_22',
        name='Trending Topics',
        replace_existing=True,
    )

    scheduler.start()
    logger.info("[Scheduler] All agents registered and running.")

    return scheduler
