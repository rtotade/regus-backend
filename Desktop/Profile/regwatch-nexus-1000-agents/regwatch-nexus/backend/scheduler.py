"""APScheduler — orchestrates all 22 backend agents"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import asyncio
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def run_agent(agent_module: str, func_name: str, **kwargs):
    try:
        module = __import__(f"backend.agents.{agent_module}", fromlist=[func_name])
        func = getattr(module, func_name)
        await func(**kwargs)
    except Exception as e:
        logger.error(f"Agent {agent_module}.{func_name} failed: {e}")


async def start_scheduler():
    # Agent 01: Regulatory Crawler — every 30 min
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_01_regulatory", "crawl_all_regulators")),
        IntervalTrigger(minutes=30), id="regulatory_crawler", replace_existing=True)
    
    # Agent 02: Consulting Crawler — nightly
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_02_consulting", "crawl_consulting_firms")),
        CronTrigger(hour=2, minute=0), id="consulting_crawler", replace_existing=True)
    
    # Agent 03: Bank Crawler — every 6 hours
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_03_banks", "crawl_bank_research")),
        IntervalTrigger(hours=6), id="bank_crawler", replace_existing=True)
    
    # Agent 04+05: Analyse & Validate — every 35 min
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_04_analyst", "process_pending_documents")),
        IntervalTrigger(minutes=35), id="analyst", replace_existing=True)
    
    # Agent 09: Health Score — daily
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_09_health", "recalculate_all_health_scores")),
        CronTrigger(hour=6, minute=0), id="health_score", replace_existing=True)
    
    # Agent 11: Consulting Synthesis — monthly
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_11_synthesis", "synthesise_consulting_intelligence")),
        CronTrigger(day=1, hour=3, minute=0), id="consulting_synthesis", replace_existing=True)
    
    # Agent 14: Report Generator — 1st of month
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_14_reports", "generate_monthly_reports")),
        CronTrigger(day=1, hour=4, minute=0), id="report_gen", replace_existing=True)
    
    # Agent 17: Quality Monitor — daily
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_17_quality", "run_quality_checks")),
        CronTrigger(hour=5, minute=0), id="quality_monitor", replace_existing=True)
    
    # Agent 22: Trending Topics — every 15 min
    scheduler.add_job(lambda: asyncio.create_task(
        run_agent("agent_22_trending", "update_trending_topics")),
        IntervalTrigger(minutes=15), id="trending", replace_existing=True)
    
    scheduler.start()
    logger.info("Scheduler started with all agents")


async def stop_scheduler():
    scheduler.shutdown(wait=False)
