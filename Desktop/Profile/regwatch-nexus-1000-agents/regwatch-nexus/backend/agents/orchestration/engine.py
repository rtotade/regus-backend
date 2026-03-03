"""
RegWatch Nexus — Master Agent Orchestration Engine
Boots all 1,336 agents, wires the hierarchy, manages the runtime.

Startup sequence:
  1. Build all agent instances from registry
  2. Register memory scopes for every agent
  3. Subscribe supervisors to subordinate events
  4. Start task queue consumers (async run loops)
  5. Boot APScheduler — trigger timed regulatory collection tasks
  6. Register health monitor — emits HEALTH_ALERT events
  7. Inject initial objectives from config

Human oversight hooks:
  - /api/v1/agents/dashboard    → global health
  - /api/v1/agents/{id}/task    → assign task via API
  - /api/v1/agents/escalations  → all pending human decisions
  - /api/v1/agents/pause        → pause all L4 agents
  - /api/v1/agents/stop         → emergency stop all
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.agents.communication.event_bus import event_bus
from backend.agents.communication.memory import memory
from backend.agents.communication.task_queue import task_registry, TaskObject
from backend.agents.communication.protocols import (
    Department, EventType, AgentTier, TaskStatus
)
from backend.agents.registry import (
    build_all_agents, start_all_agents, stop_all_agents,
    get_agent, list_agents, AGENT_DEFINITIONS, TOTAL_AGENT_COUNT,
)
from backend.agents.registry_extension import (
    EXTENDED_AGENT_DEFINITIONS, GRAND_TOTAL_AGENTS,
)

logger = logging.getLogger(__name__)

# ── Patch: merge extension into the main build ────────────────────────────
_PATCHED = False
def _patch_registry():
    """Merge extended definitions into the registry build pipeline."""
    global _PATCHED
    if _PATCHED:
        return
    import backend.agents.registry as reg
    reg.AGENT_DEFINITIONS = reg.AGENT_DEFINITIONS + EXTENDED_AGENT_DEFINITIONS
    _PATCHED = True


class AgentOrchestrationEngine:
    """
    Master runtime for all 1,336 agents.
    One instance per process. Singleton accessed via `engine`.
    """

    def __init__(self):
        self.agents: dict = {}
        self.scheduler = AsyncIOScheduler()
        self._agent_tasks: list[asyncio.Task] = []
        self._started_at: Optional[float] = None
        self._paused = False
        self._emergency_stopped = False
        self._escalation_queue: list[dict] = []   # pending human decisions
        self._health_scores: dict[str, float] = {}
        self._total_tasks_dispatched = 0

        # Subscribe orchestration events
        event_bus.subscribe(EventType.HUMAN_REQUIRED, self._handle_human_escalation)
        event_bus.subscribe(EventType.HEALTH_ALERT, self._handle_health_alert)
        event_bus.subscribe(EventType.TASK_COMPLETED, self._track_completion)
        event_bus.subscribe(EventType.TASK_FAILED, self._track_failure)

    # ── STARTUP ──────────────────────────────────────────────────────────

    async def start(self):
        """Full startup sequence. Call once at app lifespan start."""
        logger.info("═══ RegWatch Nexus Agent System STARTING ═══")
        t0 = time.time()

        # 1. Merge extended definitions
        _patch_registry()

        # 2. Build all agent instances
        logger.info(f"Building {GRAND_TOTAL_AGENTS} agent instances...")
        self.agents = build_all_agents()
        actual_count = len(self.agents)
        logger.info(f"✓ {actual_count} agents instantiated in {time.time()-t0:.1f}s")

        # 3. Start async run loops (one per agent)
        logger.info("Starting agent run loops...")
        self._agent_tasks = await start_all_agents(self.agents)
        logger.info(f"✓ {len(self._agent_tasks)} run loops active")

        # 4. Boot APScheduler with all periodic tasks
        self._register_scheduled_tasks()
        self.scheduler.start()
        logger.info("✓ APScheduler started")

        # 5. Emit startup objective to Meta-CEO
        await self._inject_startup_objective()

        self._started_at = time.time()
        logger.info(f"═══ System ONLINE — {actual_count} agents active ═══")

    async def stop(self):
        """Graceful shutdown."""
        logger.info("═══ Agent System STOPPING ═══")
        self.scheduler.shutdown(wait=False)
        await stop_all_agents()
        for task in self._agent_tasks:
            task.cancel()
        self._emergency_stopped = True
        logger.info("═══ Agent System STOPPED ═══")

    async def emergency_stop(self, reason: str = ""):
        """Immediately halt all L4 autonomous agents. L0-L3 continue."""
        logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")
        for agent in self.agents.values():
            from backend.agents.communication.protocols import AutonomyLevel
            if agent.autonomy_level == AutonomyLevel.L4_FULLY_AUTONOMOUS_WITHIN_CONSTRAINTS:
                await agent.stop()
        self._paused = True

    # ── SCHEDULED TASKS ──────────────────────────────────────────────────

    def _register_scheduled_tasks(self):
        """Register APScheduler jobs that inject tasks into the agent system."""

        # Regulatory crawl — every 30 minutes
        self.scheduler.add_job(
            self._dispatch_crawl_cycle, "interval", minutes=30,
            id="crawl_cycle", name="Regulatory Crawl Cycle",
        )

        # Alert analysis — every 15 minutes (processes pending source docs)
        self.scheduler.add_job(
            self._dispatch_analysis_cycle, "interval", minutes=15,
            id="analysis_cycle", name="AI Alert Analysis",
        )

        # Trending topics update — every 10 minutes
        self.scheduler.add_job(
            self._dispatch_trending_update, "interval", minutes=10,
            id="trending_update", name="Trending Topics Update",
        )

        # Intelligence synthesis — daily at 06:00 UTC
        self.scheduler.add_job(
            self._dispatch_intel_synthesis, "cron", hour=6, minute=0,
            id="intel_synthesis", name="Daily Intelligence Synthesis",
        )

        # Health score recalculation — every 2 hours
        self.scheduler.add_job(
            self._dispatch_health_recalc, "interval", hours=2,
            id="health_recalc", name="Client Health Score Recalculation",
        )

        # Monthly intelligence report — 1st of month at 08:00 UTC
        self.scheduler.add_job(
            self._dispatch_monthly_report, "cron", day=1, hour=8,
            id="monthly_report", name="Monthly Intelligence Report",
        )

        # Email digest — weekly Monday 07:00 UTC
        self.scheduler.add_job(
            self._dispatch_weekly_digest, "cron", day_of_week="mon", hour=7,
            id="weekly_digest", name="Weekly Email Digest",
        )

        # Gap analysis — daily at 02:00 UTC
        self.scheduler.add_job(
            self._dispatch_gap_analysis, "cron", hour=2,
            id="gap_analysis", name="Daily Policy Gap Analysis",
        )

        # SEO content generation — daily at 03:00 UTC
        self.scheduler.add_job(
            self._dispatch_seo_generation, "cron", hour=3,
            id="seo_gen", name="SEO Content Generation",
        )

        # Source validation — every 6 hours
        self.scheduler.add_job(
            self._dispatch_source_validation, "interval", hours=6,
            id="source_validation", name="Source Validation Cycle",
        )

        # Agent health monitor — every 5 minutes
        self.scheduler.add_job(
            self._emit_health_report, "interval", minutes=5,
            id="health_monitor", name="Agent Health Monitor",
        )

        # Audit chain verification — daily at midnight
        self.scheduler.add_job(
            self._dispatch_audit_verify, "cron", hour=0, minute=0,
            id="audit_verify", name="Audit Chain Verification",
        )

        # Regional regulatory round-ups — every 4 hours (rotates regions)
        self.scheduler.add_job(
            self._dispatch_regional_roundup, "interval", hours=4,
            id="regional_roundup", name="Regional Regulatory Round-up",
        )

        logger.info(f"✓ {len(self.scheduler.get_jobs())} scheduled tasks registered")

    # ── TASK DISPATCHERS ─────────────────────────────────────────────────

    async def _dispatch_crawl_cycle(self):
        """Dispatch crawl tasks to all regional crawler agents."""
        regions = ["APAC", "Europe", "Americas", "MEA", "India", "UK", "EU", "USA"]
        for region in regions:
            task = TaskObject(
                title            = f"Regulatory Crawl — {region}",
                description      = f"Crawl all {region} regulatory sources for new publications",
                assigned_agent_id= "dir_crawler_ops",
                priority         = 2,
                department       = Department.OPERATIONS,
                input_data       = {"region": region, "cycle_time": datetime.utcnow().isoformat()},
                confidence_threshold = 0.70,
            )
            await task_registry.submit_task(task)
            self._total_tasks_dispatched += 1

    async def _dispatch_analysis_cycle(self):
        task = TaskObject(
            title            = "Analyze Pending Source Documents",
            description      = "Run AI analysis on all unprocessed regulatory documents",
            assigned_agent_id= "dir_alert_qa",
            priority         = 1,
            department       = Department.OPERATIONS,
            input_data       = {"max_batch": 50, "cycle": datetime.utcnow().isoformat()},
            confidence_threshold = 0.75,
        )
        await task_registry.submit_task(task)

    async def _dispatch_trending_update(self):
        task = TaskObject(
            title            = "Update Trending Topics",
            description      = "Recalculate trending regulatory topics from page view analytics",
            assigned_agent_id= "dir_pipeline_ops",
            priority         = 4,
            department       = Department.OPERATIONS,
            input_data       = {"lookback_hours": 24},
            confidence_threshold = 0.65,
        )
        await task_registry.submit_task(task)

    async def _dispatch_intel_synthesis(self):
        for dept in ["banking", "fintech", "payments", "insurance", "crypto"]:
            task = TaskObject(
                title            = f"Daily Intelligence Synthesis — {dept.title()}",
                description      = f"Synthesize consulting intelligence for {dept} sector",
                assigned_agent_id= "dir_intel_content",
                priority         = 3,
                department       = Department.PRODUCT,
                input_data       = {"sector": dept, "date": datetime.utcnow().date().isoformat()},
                confidence_threshold = 0.70,
            )
            await task_registry.submit_task(task)

    async def _dispatch_health_recalc(self):
        task = TaskObject(
            title            = "Recalculate Client Health Scores",
            description      = "Update health scores for all enterprise clients",
            assigned_agent_id= "dir_agent_runtime",
            priority         = 3,
            department       = Department.OPERATIONS,
            input_data       = {"recalc_all": True},
            confidence_threshold = 0.80,
        )
        await task_registry.submit_task(task)

    async def _dispatch_monthly_report(self):
        for jurisdiction in ["GLOBAL", "IN", "GB", "EU", "US", "SG", "AU"]:
            task = TaskObject(
                title            = f"Monthly Intelligence Report — {jurisdiction}",
                description      = f"Generate and publish monthly PDF report for {jurisdiction}",
                assigned_agent_id= "dir_seo_content",
                priority         = 2,
                department       = Department.PRODUCT,
                input_data       = {"jurisdiction": jurisdiction,
                                    "month": datetime.utcnow().strftime("%Y-%m")},
                confidence_threshold = 0.75,
            )
            await task_registry.submit_task(task)

    async def _dispatch_weekly_digest(self):
        task = TaskObject(
            title            = "Weekly Email Digest",
            description      = "Generate and send weekly regulatory digest to registered users",
            assigned_agent_id= "dir_acquisition",
            priority         = 3,
            department       = Department.REVENUE,
            input_data       = {"week": datetime.utcnow().strftime("%Y-W%U")},
            confidence_threshold = 0.70,
        )
        await task_registry.submit_task(task)

    async def _dispatch_gap_analysis(self):
        task = TaskObject(
            title            = "Daily Policy Gap Analysis",
            description      = "Identify policy gaps for active enterprise clients",
            assigned_agent_id= "dir_dashboard_product",
            priority         = 3,
            department       = Department.PRODUCT,
            input_data       = {"date": datetime.utcnow().date().isoformat()},
            confidence_threshold = 0.72,
        )
        await task_registry.submit_task(task)

    async def _dispatch_seo_generation(self):
        task = TaskObject(
            title            = "Daily SEO Content Generation",
            description      = "Generate SEO-optimised summaries for new alerts",
            assigned_agent_id= "dir_seo_content",
            priority         = 5,
            department       = Department.PRODUCT,
            input_data       = {"max_alerts": 30},
            confidence_threshold = 0.68,
        )
        await task_registry.submit_task(task)

    async def _dispatch_source_validation(self):
        task = TaskObject(
            title            = "Source Validation Cycle",
            description      = "Cross-verify regulatory sources for accuracy",
            assigned_agent_id= "dir_source_validation",
            priority         = 3,
            department       = Department.OPERATIONS,
            input_data       = {"validate_last_hours": 6},
            confidence_threshold = 0.82,
        )
        await task_registry.submit_task(task)

    async def _dispatch_audit_verify(self):
        task = TaskObject(
            title            = "Audit Chain Integrity Verification",
            description      = "Verify hash chain integrity of the immutable audit log",
            assigned_agent_id= "sr_audit_chain",
            priority         = 2,
            department       = Department.AUDIT,
            input_data       = {"verify_full_chain": True},
            confidence_threshold = 0.99,
        )
        await task_registry.submit_task(task)

    async def _dispatch_regional_roundup(self):
        """Rotate through regions every 4 hours."""
        hour = datetime.utcnow().hour
        regions = ["India","UK","EU","USA","Singapore","Australia","Japan","UAE"]
        region = regions[(hour // 4) % len(regions)]
        task = TaskObject(
            title            = f"Regional Regulatory Round-up — {region}",
            description      = f"Compile top regulatory developments in {region} last 4 hours",
            assigned_agent_id= f"sr_reg_{region.lower()}_banking" if region != "UAE" else "sr_reg_uae_banking",
            priority         = 3,
            department       = Department.OPERATIONS,
            input_data       = {"region": region, "hours": 4},
            confidence_threshold = 0.72,
        )
        # Fall back to crawler director if specific agent doesn't exist
        if not task_registry.get_queue(task.assigned_agent_id):
            task.assigned_agent_id = "dir_crawler_ops"
        await task_registry.submit_task(task)

    async def _inject_startup_objective(self):
        """Set the Meta-CEO's initial operating objective."""
        task = TaskObject(
            title       = "Q1 Platform Operating Objective",
            description = (
                "Ensure RegWatch Nexus provides best-in-class regulatory intelligence: "
                "1) Maintain <15min alert latency from source publication. "
                "2) Achieve >95% alert accuracy score. "
                "3) Grow Pro subscriptions. "
                "4) Maintain 99.9% platform uptime. "
                "5) Ensure all agent autonomy levels are respected. "
                "6) Monitor for ethical violations and escalate to human governance."
            ),
            assigned_agent_id = "meta_ceo",
            priority    = 1,
            department  = Department.EXECUTIVE,
            input_data  = {
                "quarter": "Q1 2026",
                "kpis": {
                    "alert_latency_minutes": 15,
                    "accuracy_target": 0.95,
                    "uptime_target": 0.999,
                },
            },
            confidence_threshold = 0.70,
        )
        await task_registry.submit_task(task)
        self._total_tasks_dispatched += 1
        logger.info("✓ Startup objective injected to Meta-CEO")

    # ── HEALTH MONITORING ─────────────────────────────────────────────────

    async def _emit_health_report(self):
        """Collect health from all agents and emit aggregate."""
        if not self.agents:
            return
        total = len(self.agents)
        healthy = sum(1 for a in self.agents.values() if a._running)
        failed_recently = sum(1 for a in self.agents.values() if a._tasks_failed > a._tasks_completed * 0.2)

        report = {
            "total_agents":    total,
            "running_agents":  healthy,
            "degraded_agents": failed_recently,
            "tasks_dispatched":self._total_tasks_dispatched,
            "task_dashboard":  task_registry.get_dashboard(),
            "memory_stats":    memory.get_stats(),
            "event_metrics":   event_bus.get_metrics(),
            "timestamp":       datetime.utcnow().isoformat(),
        }

        await memory.write("system", memory._stores.get(
            __import__('backend.agents.communication.protocols', fromlist=['MemoryScope']).MemoryScope.ENTERPRISE_KG,
        ) and "enterprise_kg" or "agent_local",
            "health:latest", report,
        )

        if failed_recently > total * 0.1:
            evt = __import__('backend.agents.communication.protocols', fromlist=['AgentEvent']).AgentEvent(
                event_type   = EventType.HEALTH_ALERT,
                source_agent = "orchestration_engine",
                payload      = {"degraded": failed_recently, "total": total, "report": report},
            )
            await event_bus.publish(evt)

    # ── EVENT HANDLERS ────────────────────────────────────────────────────

    async def _handle_human_escalation(self, event):
        self._escalation_queue.append({
            "escalation_id": event.event_id,
            "task_id":       event.related_task,
            "source_agent":  event.source_agent,
            "reason":        event.payload.get("reason", ""),
            "payload":       event.payload,
            "received_at":   datetime.utcnow().isoformat(),
            "status":        "pending_human_review",
        })
        logger.critical(f"HUMAN REVIEW REQUIRED — {event.source_agent}: {event.payload.get('reason','')}")

    async def _handle_health_alert(self, event):
        logger.warning(f"HEALTH ALERT: {event.payload}")

    async def _track_completion(self, event):
        self._total_tasks_dispatched  # just track

    async def _track_failure(self, event):
        agent_id = event.payload.get("agent")
        if agent_id and agent_id in self.agents:
            self.agents[agent_id]._tasks_failed += 0  # already tracked in agent

    # ── HUMAN OVERSIGHT API ───────────────────────────────────────────────

    def get_dashboard(self) -> dict:
        """Full system dashboard for the human governance layer."""
        uptime = time.time() - self._started_at if self._started_at else 0
        return {
            "system":  {
                "status":            "emergency_stopped" if self._emergency_stopped else
                                     "paused" if self._paused else "operational",
                "uptime_seconds":    round(uptime),
                "uptime_human":      str(timedelta(seconds=int(uptime))),
                "total_agents":      GRAND_TOTAL_AGENTS,
                "active_agents":     len(self.agents),
                "tasks_dispatched":  self._total_tasks_dispatched,
                "pending_human_escalations": len([e for e in self._escalation_queue if e["status"] == "pending_human_review"]),
            },
            "hierarchy": {
                "executive":    6,
                "vp":           15,
                "director":     45,
                "senior":       138 + 128,   # base + extended
                "junior":       276 + 311,
                "intern":       161 + 306,
            },
            "task_registry": task_registry.get_dashboard(),
            "event_bus":     event_bus.get_metrics(),
            "memory":        memory.get_stats(),
            "escalations":   self._escalation_queue[-20:],  # last 20
        }

    def get_agent_health(self) -> list[dict]:
        return [a.health_report() for a in self.agents.values()]

    def get_agent(self, agent_id: str):
        return self.agents.get(agent_id)

    async def dispatch_task_to_agent(self, agent_id: str, title: str, description: str,
                                     input_data: dict = None, priority: int = 5) -> str:
        """Human-initiated task dispatch. Called from admin API."""
        agent = self.agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        task = TaskObject(
            title            = title,
            description      = description,
            assigned_agent_id= agent_id,
            priority         = priority,
            department       = agent.department,
            input_data       = input_data or {},
            confidence_threshold = 0.70,
        )
        await task_registry.submit_task(task)
        self._total_tasks_dispatched += 1
        return task.task_id

    async def resolve_escalation(self, escalation_id: str, resolution: str,
                                  human_user: str = "board"):
        """Human resolves a pending escalation. Called from governance UI."""
        for esc in self._escalation_queue:
            if esc["escalation_id"] == escalation_id:
                esc["status"] = "resolved"
                esc["resolution"] = resolution
                esc["resolved_by"] = human_user
                esc["resolved_at"] = datetime.utcnow().isoformat()
                await memory.audit_append("human_governance", "ESCALATION_RESOLVED", {
                    "escalation_id": escalation_id, "resolution": resolution,
                    "resolved_by": human_user,
                })
                logger.info(f"Escalation {escalation_id} resolved by {human_user}: {resolution}")
                return esc
        raise ValueError(f"Escalation {escalation_id} not found")

    def list_pending_escalations(self) -> list[dict]:
        return [e for e in self._escalation_queue if e["status"] == "pending_human_review"]

    def get_org_chart(self) -> dict:
        """Return full org chart for governance dashboard visualization."""
        chart = {
            "board": {"type": "human", "label": "Board (Human Governance)"},
            "ceo":   {"type": "human_hybrid", "label": "CEO (Human / Hybrid)"},
            "meta_ceo": {"type": "ai", "label": "AI Meta-CEO", "subordinates": []},
        }
        for agent in self.agents.values():
            if agent.tier == AgentTier.C_SUITE:
                chart["meta_ceo"]["subordinates"].append({
                    "id": agent.agent_id, "label": agent.name,
                    "tier": agent.tier.value,
                    "subordinate_count": len(agent.supervises),
                })
        return chart


# ── Global singleton ──────────────────────────────────────────────────────
engine = AgentOrchestrationEngine()
