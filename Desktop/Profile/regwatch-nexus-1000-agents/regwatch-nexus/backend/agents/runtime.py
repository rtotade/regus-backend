"""
RegWatch Nexus — Agent Runtime & Factory

Boots the complete 1054-agent hierarchy.
Wires up: EventBus, TaskQueue, MemoryStore, Dispatcher.
Provides the entry point for the Meta-CEO to start work.

Usage:
    runtime = AgentRuntime()
    await runtime.start()
    result = await runtime.submit_objective("Expand coverage to LATAM regulators")
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional, Type

from .framework.base import (
    AgentBase, AgentSpec, Task, AgentTier, AgentDivision
)
from .framework.communication import EventBus, TaskQueue, Dispatcher, AuditLogger
from .framework.memory import MemoryStore, MemoryManager

from .registry import build_all_specs, TOTAL_AGENT_COUNT
from .executive.meta_ceo import MetaCEO

# Division-specific agent classes
from .intelligence.agents import (
    RegulatoryDocumentCrawler, DuplicateDetector, LanguageDetector,
    JurisdictionClassifier, DeadlineExtractor, TopicTagExtractor,
    SectorMapper, RegulatoryAnalyst, ImpactScorer,
    CrossAlertSynthesizer, RegionDirector, VPRegulatoryIntelligence,
    VPAlertAnalysis,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  AGENT CLASS REGISTRY
#  Maps specialization patterns → concrete classes
# ─────────────────────────────────────────────

def _get_agent_class(spec: AgentSpec) -> Type[AgentBase]:
    """
    Determine the concrete implementation class for an agent.
    Falls back to a GenericAgent for standard tier behaviour.
    """
    sid = spec.specialization.lower()
    aid = spec.agent_id

    # Executive
    if aid == "AGT-EXEC-CEO-001":
        return MetaCEO

    # Intelligence division — by specialization
    if spec.division == AgentDivision.INTELLIGENCE:
        if spec.tier == AgentTier.INTERN:
            if "crawler" in sid or "crawl" in sid:
                return RegulatoryDocumentCrawler
            elif "duplicate" in sid:
                return DuplicateDetector
            elif "language" in sid:
                return LanguageDetector
            elif "jurisdiction" in sid:
                return JurisdictionClassifier
            else:
                return InternAgent

        elif spec.tier == AgentTier.JUNIOR:
            if "deadline" in sid or "date" in sid:
                return DeadlineExtractor
            elif "topic" in sid or "tag" in sid:
                return TopicTagExtractor
            elif "sector" in sid:
                return SectorMapper
            else:
                return JuniorAgent

        elif spec.tier == AgentTier.SENIOR:
            if "analysis" in sid or "analyst" in sid:
                return RegulatoryAnalyst
            elif "impact" in sid:
                return ImpactScorer
            elif "synthesis" in sid:
                return CrossAlertSynthesizer
            else:
                return SeniorAgent

        elif spec.tier == AgentTier.DIRECTOR:
            if "crawl" in sid or "source" in sid:
                return RegionDirector
            elif "analysis" in sid or "compliance" in sid:
                return VPAlertAnalysis
            else:
                return DirectorAgent

        elif spec.tier == AgentTier.VP:
            if "crawl" in sid:
                return VPRegulatoryIntelligence
            elif "analysis" in sid:
                return VPAlertAnalysis
            else:
                return VPAgent

    # All other divisions — tier-appropriate generic agents
    tier_class_map = {
        AgentTier.INTERN:    InternAgent,
        AgentTier.JUNIOR:    JuniorAgent,
        AgentTier.SENIOR:    SeniorAgent,
        AgentTier.DIRECTOR:  DirectorAgent,
        AgentTier.VP:        VPAgent,
        AgentTier.EXECUTIVE: ExecutiveAgent,
    }
    return tier_class_map.get(spec.tier, JuniorAgent)


# ─────────────────────────────────────────────
#  GENERIC TIER IMPLEMENTATIONS
#  Used by non-intelligence agents
# ─────────────────────────────────────────────

class GenericAgent(AgentBase):
    """Base for all generic-tier agents."""

    def _get_tier_system_prompt(self) -> str:
        return f"""You are {self.agent_name}, a {self.tier.value}-tier agent in the {self.division.value} division of RegWatch Nexus.

Your specialization: {self.spec.specialization}

Execute tasks professionally and return structured JSON results.
Always include a confidence_score in your output.
Escalate immediately if task requires human judgment."""

    async def execute_task(self, task: Task) -> Task:
        result, conf = await self.llm_json(
            system=self._get_tier_system_prompt(),
            user=f"""TASK: {task.title}
DESCRIPTION: {task.description}
CONTEXT: {str(task.metadata)[:2000]}

Execute this task and return structured JSON with your result and a confidence_score (0.0-1.0).""",
        )
        task.result = result
        task.confidence_score = result.get("confidence_score", conf) if isinstance(result, dict) else conf
        task.reasoning_trace.append(f"Executed by {self.agent_id}")
        return task


class InternAgent(GenericAgent):
    """Intern-tier: preprocessing only, no high-impact decisions."""

    def _get_tier_system_prompt(self) -> str:
        return f"""You are {self.agent_name}, an AI intern in RegWatch Nexus.
Specialization: {self.spec.specialization}

Your role is PREPROCESSING ONLY:
- Clean and standardize data
- Extract structured fields from unstructured content
- Summarize content for senior agents
- Flag anomalies
- Do NOT make decisions — only prepare data

Return structured JSON. Never make regulatory conclusions."""


class JuniorAgent(GenericAgent):
    """Junior-tier: structured execution from clear instructions."""

    def _get_tier_system_prompt(self) -> str:
        return f"""You are {self.agent_name}, a junior agent in the {self.division.value} division.
Specialization: {self.spec.specialization}

Execute structured tasks with clear inputs and outputs.
Do NOT improvise — follow specifications exactly.
Escalate if task is ambiguous."""


class SeniorAgent(GenericAgent):
    """Senior-tier: complex reasoning within bounded domain."""

    def _get_tier_system_prompt(self) -> str:
        return f"""You are {self.agent_name}, a senior specialist in RegWatch Nexus {self.division.value} division.
Specialization: {self.spec.specialization}

You handle COMPLEX REASONING tasks requiring:
- Domain expertise and judgment
- Multi-step analysis
- Synthesis of multiple inputs
- Risk-calibrated recommendations

Always justify your reasoning. Flag low-confidence findings."""


class DirectorAgent(GenericAgent):
    """Director-tier: task breakdown and team orchestration."""

    def _get_tier_system_prompt(self) -> str:
        return f"""You are {self.agent_name}, a director in RegWatch Nexus.
Division: {self.division.value}
Specialization: {self.spec.specialization}

You ORCHESTRATE subordinate agents. Your job is to:
1. Break incoming tasks into atomic subtasks
2. Assign subtasks to appropriate junior/senior agents
3. Aggregate and QA results
4. Escalate conflicts or low-confidence items to your VP

Return structured subtask plans and results."""

    async def execute_task(self, task: Task) -> Task:
        """Directors decompose tasks and spawn subtasks."""
        if task.task_type.startswith("orchestrate_"):
            return await self._orchestrate(task)
        return await super().execute_task(task)

    async def _orchestrate(self, task: Task) -> Task:
        """Decompose a director-level task into sub-tasks."""
        result, conf = await self.llm_json(
            system=self._get_tier_system_prompt(),
            user=f"""ORCHESTRATION TASK: {task.title}
DESCRIPTION: {task.description}
CONTEXT: {str(task.metadata)[:2000]}

Break this into 3-8 atomic subtasks for junior/senior agents.
Return:
{{
  "subtasks": [
    {{
      "title": "...",
      "task_type": "...",
      "assigned_tier": "junior|senior",
      "description": "...",
      "priority": 3
    }}
  ],
  "orchestration_plan": "...",
  "confidence_score": 0.85
}}""",
        )

        subtasks = (result or {}).get("subtasks", [])
        for i, st in enumerate(subtasks):
            sub = Task(
                title=st["title"],
                task_type=st.get("task_type", "execute"),
                priority=st.get("priority", 5),
                description=st.get("description", ""),
                parent_task_id=task.task_id,
                assigned_agent="",  # Dispatcher will route by tier
                metadata=task.metadata,
            )
            task.subtask_ids.append(sub.task_id)
            if self._task_queue:
                await self._task_queue.enqueue(sub)

        task.result = {"subtasks_spawned": len(subtasks), "plan": (result or {}).get("orchestration_plan")}
        task.confidence_score = (result or {}).get("confidence_score", conf)
        return task


class VPAgent(GenericAgent):
    """VP-tier: planning, prioritisation, division coordination."""

    def _get_tier_system_prompt(self) -> str:
        return f"""You are {self.agent_name}, VP of {self.division.value} at RegWatch Nexus.
Specialization: {self.spec.specialization}

You translate C-suite directives into concrete initiatives.
Your outputs become task assignments for Director agents.
Think strategically and operationally."""


class ExecutiveAgent(GenericAgent):
    """C-suite tier: strategic domain oversight."""

    def _get_tier_system_prompt(self) -> str:
        return f"""You are {self.agent_name}, a C-suite executive AI agent at RegWatch Nexus.
Division: {self.division.value}
Specialization: {self.spec.specialization}

You operate at the strategic layer:
1. Set divisional direction aligned with Meta-CEO objectives
2. Allocate VP-level resources
3. Report to Meta-CEO with confidence scores
4. Escalate to human layer when appropriate

Confidence thresholds: escalate to human if confidence < 0.5"""


# ─────────────────────────────────────────────
#  RUNTIME
# ─────────────────────────────────────────────

class AgentRuntime:
    """
    Boots and orchestrates the complete 1054-agent hierarchy.

    Architecture:
    - Single EventBus (pub/sub for all inter-agent signalling)
    - Single TaskQueue (priority-ordered global + per-agent queues)
    - Single MemoryStore (tiered access-controlled memory)
    - Dispatcher (routes tasks to registered agents)
    - 1054 agent instances (instantiated from registry)
    """

    def __init__(self, anthropic_client=None, db_session=None):
        self._anthropic = anthropic_client
        self._db = db_session

        # Core infrastructure
        self.event_bus = EventBus()
        self.task_queue = TaskQueue()
        self.memory = MemoryStore()
        self.dispatcher = Dispatcher(self.task_queue, self.event_bus)

        # Agent registry
        self._specs: dict[str, AgentSpec] = {}
        self._agents: dict[str, AgentBase] = {}
        self._is_running = False

        logger.info("AgentRuntime: Initializing...")

    async def boot(self):
        """
        Full cold boot of all 1054 agents.
        In production, agents are loaded lazily by tier.
        In development, we boot executive + director tiers eagerly.
        """
        logger.info(f"AgentRuntime: Loading registry ({TOTAL_AGENT_COUNT} agents)...")
        self._specs = build_all_specs()

        # Boot order: Executive → VP → Director (always eager)
        # Senior/Junior/Intern: lazy (instantiated on first task)
        eager_tiers = {AgentTier.EXECUTIVE, AgentTier.VP, AgentTier.DIRECTOR}
        lazy_count = 0

        for agent_id, spec in self._specs.items():
            if spec.tier in eager_tiers:
                agent = self._instantiate(spec)
                await agent.start()
                self.dispatcher.register_agent(agent_id, agent.handle_task)
            else:
                lazy_count += 1

        eager = len(self._agents)
        logger.info(f"AgentRuntime: {eager} agents booted eagerly, {lazy_count} registered for lazy init")

        # Start dispatcher
        asyncio.create_task(self.dispatcher.dispatch_loop())
        self._is_running = True
        logger.info("AgentRuntime: ONLINE — all systems go")

    def _instantiate(self, spec: AgentSpec) -> AgentBase:
        """Create agent instance from spec."""
        AgentClass = _get_agent_class(spec)
        agent = AgentClass(
            spec=spec,
            event_bus=self.event_bus,
            task_queue=self.task_queue,
            memory_store=self.memory,
            anthropic_client=self._anthropic,
        )
        self._agents[spec.agent_id] = agent
        return agent

    def get_or_create_agent(self, agent_id: str) -> Optional[AgentBase]:
        """Lazy agent creation for junior/intern tier."""
        if agent_id in self._agents:
            return self._agents[agent_id]
        spec = self._specs.get(agent_id)
        if not spec:
            return None
        agent = self._instantiate(spec)
        # Register with dispatcher (lazy)
        self.dispatcher.register_agent(agent_id, agent.handle_task)
        return agent

    # ── Human Entry Points ──────────────────────

    async def submit_objective(self, objective: str, quarter: str = "Q1 2026") -> dict:
        """
        Human CEO submits a strategic objective.
        Returns initiative breakdown.
        """
        meta_ceo: MetaCEO = self._agents.get("AGT-EXEC-CEO-001")
        if not meta_ceo:
            raise RuntimeError("Meta-CEO not booted")
        result = await meta_ceo.receive_strategic_objective(objective, quarter)
        return result.result or {}

    async def submit_task(self, task: Task) -> str:
        """Submit any task directly to the queue. Returns task_id."""
        await self.task_queue.enqueue(task)
        return task.task_id

    async def get_global_status(self) -> dict:
        """Return platform-wide health status."""
        meta_ceo: MetaCEO = self._agents.get("AGT-EXEC-CEO-001")
        if not meta_ceo:
            return {"error": "Meta-CEO not available"}

        health_task = Task(
            task_type="global_health_check",
            title="Global Health Check",
            assigned_agent="AGT-EXEC-CEO-001",
            priority=1,
        )
        result = await meta_ceo.handle_task(health_task)
        return result.result or {}

    def get_agent_status_all(self) -> list[dict]:
        """Status report for all booted agents."""
        return [agent.status_report() for agent in self._agents.values()]

    def get_agent(self, agent_id: str) -> Optional[AgentBase]:
        return self.get_or_create_agent(agent_id)

    @property
    def total_agents(self) -> int:
        return TOTAL_AGENT_COUNT

    @property
    def booted_agents(self) -> int:
        return len(self._agents)

    async def shutdown(self):
        """Graceful shutdown."""
        self.dispatcher.stop()
        for agent in self._agents.values():
            await agent.stop()
        self._is_running = False
        logger.info("AgentRuntime: Shutdown complete")


# ─────────────────────────────────────────────
#  SINGLETON
# ─────────────────────────────────────────────

_runtime_instance: Optional[AgentRuntime] = None


def get_runtime() -> AgentRuntime:
    global _runtime_instance
    if _runtime_instance is None:
        raise RuntimeError("AgentRuntime not initialized. Call init_runtime() first.")
    return _runtime_instance


async def init_runtime(anthropic_client=None, db_session=None) -> AgentRuntime:
    """Initialize and boot the complete agent runtime."""
    global _runtime_instance
    if _runtime_instance is None:
        _runtime_instance = AgentRuntime(anthropic_client, db_session)
        await _runtime_instance.boot()
    return _runtime_instance
