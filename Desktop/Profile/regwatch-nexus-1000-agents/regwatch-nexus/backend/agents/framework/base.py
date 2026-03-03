"""
RegWatch Nexus — Agent Framework Base
All 1000+ agents inherit from AgentBase.
"""
from __future__ import annotations
import asyncio
import uuid
import time
import json
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  ENUMS
# ─────────────────────────────────────────────

class AgentTier(str, Enum):
    EXECUTIVE   = "executive"   # Meta-CEO, C-suite
    VP          = "vp"          # Vice Presidents
    DIRECTOR    = "director"    # Directors
    SENIOR      = "senior"      # Senior Agents
    JUNIOR      = "junior"      # Junior Agents
    INTERN      = "intern"      # Intern Agents (preprocessing only)


class AgentDivision(str, Enum):
    EXECUTIVE           = "executive"
    INTELLIGENCE        = "intelligence"
    OPERATIONS          = "operations"
    TECHNOLOGY          = "technology"
    PRODUCT             = "product"
    REVENUE             = "revenue"
    RISK                = "risk"
    CUSTOMER_SUCCESS    = "customer_success"
    GOVERNANCE          = "governance"


class TaskStatus(str, Enum):
    PENDING     = "pending"
    RUNNING     = "running"
    COMPLETED   = "completed"
    FAILED      = "failed"
    ESCALATED   = "escalated"
    CANCELLED   = "cancelled"


class EventType(str, Enum):
    TASK_COMPLETED          = "task_completed"
    TASK_FAILED             = "task_failed"
    LOW_CONFIDENCE          = "low_confidence"
    CONFLICT_DETECTED       = "conflict_detected"
    ESCALATION_REQUIRED     = "escalation_required"
    MEMORY_WRITTEN          = "memory_written"
    PEER_REQUEST            = "peer_request"
    HEARTBEAT               = "heartbeat"
    ALERT_PUBLISHED         = "alert_published"
    ANOMALY_DETECTED        = "anomaly_detected"
    HUMAN_REVIEW_REQUIRED   = "human_review_required"


class AutonomyLevel(int, Enum):
    L0 = 0  # Human-controlled
    L1 = 1  # AI-assisted
    L2 = 2  # AI executes, human reviews
    L3 = 3  # AI executes, human audits
    L4 = 4  # Fully autonomous within constraints


class MemoryScope(str, Enum):
    TASK_LOCAL      = "task_local"       # Agent's own task memory
    DEPARTMENT      = "department"        # Shared within division
    ENTERPRISE      = "enterprise"        # Read-heavy global KG
    EXECUTIVE       = "executive"         # C-level only
    AUDIT           = "audit"             # Immutable system-wide


# ─────────────────────────────────────────────
#  CORE DATA STRUCTURES
# ─────────────────────────────────────────────

@dataclass
class Task:
    task_id: str = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    title: str = ""
    description: str = ""
    task_type: str = ""
    priority: int = 5          # 1 (highest) – 10 (lowest)
    assigned_agent: str = ""
    parent_task_id: Optional[str] = None
    subtask_ids: list[str] = field(default_factory=list)
    required_memory_scope: MemoryScope = MemoryScope.TASK_LOCAL
    confidence_threshold: float = 0.75
    autonomy_level: AutonomyLevel = AutonomyLevel.L3
    deadline: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    confidence_score: float = 0.0
    reasoning_trace: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "task_type": self.task_type,
            "priority": self.priority,
            "assigned_agent": self.assigned_agent,
            "status": self.status.value,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AgentEvent:
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    event_type: EventType = EventType.HEARTBEAT
    source_agent: str = ""
    target_agent: Optional[str] = None   # None = broadcast
    related_task_id: Optional[str] = None
    confidence_score: float = 1.0
    payload: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "confidence_score": self.confidence_score,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class PeerRequest:
    """Structured peer-to-peer agent communication — no free text."""
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:10]}")
    requesting_agent: str = ""
    receiving_agent: str = ""
    task_context: dict = field(default_factory=dict)
    required_output_format: dict = field(default_factory=dict)  # JSON schema
    deadline_seconds: int = 30
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PeerResponse:
    request_id: str = ""
    responding_agent: str = ""
    structured_output: Any = None
    confidence_score: float = 1.0
    dependency_notes: list[str] = field(default_factory=list)
    latency_ms: int = 0


@dataclass
class AgentSpec:
    """Static definition of an agent — instantiated from registry."""
    agent_id: str
    agent_name: str
    tier: AgentTier
    division: AgentDivision
    parent_agent_id: Optional[str]
    autonomy_level: AutonomyLevel
    specialization: str
    capabilities: list[str]
    memory_scopes: list[MemoryScope]
    max_concurrent_tasks: int = 5
    confidence_threshold: float = 0.75
    escalation_agent_id: Optional[str] = None
    can_spawn_subtasks: bool = True
    model_preference: str = "claude-haiku-4-5-20251001"  # Default to fast model


# ─────────────────────────────────────────────
#  AGENT BASE CLASS
# ─────────────────────────────────────────────

class AgentBase:
    """
    Base class for all 1000+ RegWatch Nexus agents.
    Subclasses implement `execute_task()`.
    """

    def __init__(
        self,
        spec: AgentSpec,
        event_bus=None,
        task_queue=None,
        memory_store=None,
        anthropic_client=None,
    ):
        self.spec = spec
        self.agent_id = spec.agent_id
        self.agent_name = spec.agent_name
        self.tier = spec.tier
        self.division = spec.division

        # Infrastructure references (injected)
        self._event_bus = event_bus
        self._task_queue = task_queue
        self._memory = memory_store
        self._anthropic = anthropic_client

        # Runtime state
        self._active_tasks: dict[str, Task] = {}
        self._is_running = False
        self._heartbeat_interval = 30  # seconds
        self._stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "escalations": 0,
            "avg_confidence": 0.0,
            "uptime_start": time.time(),
        }

        logger.info(f"[{self.agent_id}] Initialized — {self.tier.value} / {self.division.value}")

    # ── Lifecycle ──────────────────────────────

    async def start(self):
        self._is_running = True
        await self._emit_event(EventType.HEARTBEAT, {"status": "started"})
        asyncio.create_task(self._heartbeat_loop())
        logger.info(f"[{self.agent_id}] Started")

    async def stop(self):
        self._is_running = False
        logger.info(f"[{self.agent_id}] Stopped")

    # ── Core Interface ─────────────────────────

    async def handle_task(self, task: Task) -> Task:
        """Accept a task, execute it, return updated task."""
        if len(self._active_tasks) >= self.spec.max_concurrent_tasks:
            task.status = TaskStatus.FAILED
            task.reasoning_trace.append("Agent at capacity — task rejected")
            return task

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc)
        self._active_tasks[task.task_id] = task

        try:
            task = await self.execute_task(task)

            if task.confidence_score < self.spec.confidence_threshold:
                await self._handle_low_confidence(task)
            else:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                self._stats["tasks_completed"] += 1
                await self._emit_event(
                    EventType.TASK_COMPLETED,
                    {"task_id": task.task_id, "confidence": task.confidence_score},
                    task_id=task.task_id
                )

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.reasoning_trace.append(f"Exception: {str(e)}")
            self._stats["tasks_failed"] += 1
            logger.exception(f"[{self.agent_id}] Task {task.task_id} failed: {e}")
            await self._emit_event(EventType.TASK_FAILED, {"error": str(e)}, task_id=task.task_id)

        finally:
            self._active_tasks.pop(task.task_id, None)

        return task

    async def execute_task(self, task: Task) -> Task:
        """
        Override in subclasses. Core task logic lives here.
        Must return the task with result + confidence_score set.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute_task()")

    # ── LLM Helper ─────────────────────────────

    async def llm_call(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        max_tokens: int = 2000,
        response_format: str = "text",  # "text" or "json"
    ) -> tuple[str, float]:
        """
        Call Anthropic Claude. Returns (response_text, confidence_score).
        Confidence is estimated from response completeness.
        """
        if not self._anthropic:
            raise RuntimeError(f"[{self.agent_id}] No Anthropic client available")

        used_model = model or self.spec.model_preference

        try:
            if response_format == "json":
                system_prompt += "\n\nRespond ONLY with a valid JSON object. No markdown, no explanation."

            response = await self._anthropic.messages.create(
                model=used_model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )

            text = response.content[0].text
            # Simple confidence: penalize very short / empty responses
            confidence = 0.95
            if len(text) < 20:
                confidence = 0.3
            elif response.stop_reason == "max_tokens":
                confidence = 0.6  # Truncated — penalise

            return text, confidence

        except Exception as e:
            logger.error(f"[{self.agent_id}] LLM call failed: {e}")
            raise

    async def llm_json(self, system: str, user: str, model=None, max_tokens=2000) -> tuple[dict, float]:
        """Call LLM and parse JSON response."""
        text, conf = await self.llm_call(system, user, model, max_tokens, "json")
        try:
            # Strip markdown fences if present
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(cleaned.split("\n")[1:-1])
            return json.loads(cleaned), conf
        except json.JSONDecodeError as e:
            logger.warning(f"[{self.agent_id}] JSON parse failed: {e}. Raw: {text[:200]}")
            return {}, 0.2

    # ── Memory Helpers ─────────────────────────

    async def memory_read(self, key: str, scope: MemoryScope = MemoryScope.TASK_LOCAL) -> Optional[Any]:
        if not self._memory:
            return None
        if scope not in self.spec.memory_scopes:
            logger.warning(f"[{self.agent_id}] Denied memory read at scope {scope}")
            return None
        return await self._memory.get(scope, self.division.value, key)

    async def memory_write(self, key: str, value: Any, scope: MemoryScope = MemoryScope.TASK_LOCAL, ttl: int = 3600):
        if not self._memory:
            return
        if scope not in self.spec.memory_scopes:
            logger.warning(f"[{self.agent_id}] Denied memory write at scope {scope}")
            return
        if scope == MemoryScope.AUDIT:
            logger.warning(f"[{self.agent_id}] Cannot write to AUDIT scope directly")
            return
        await self._memory.set(scope, self.division.value, key, value, ttl=ttl)
        await self._emit_event(EventType.MEMORY_WRITTEN, {"key": key, "scope": scope.value})

    # ── Communication ──────────────────────────

    async def peer_request(self, target_agent: str, context: dict, output_schema: dict, deadline: int = 30) -> PeerResponse:
        """Send structured request to peer agent."""
        req = PeerRequest(
            requesting_agent=self.agent_id,
            receiving_agent=target_agent,
            task_context=context,
            required_output_format=output_schema,
            deadline_seconds=deadline,
        )
        if not self._event_bus:
            return PeerResponse(request_id=req.request_id, confidence_score=0.0)
        return await self._event_bus.send_peer_request(req)

    async def escalate(self, task: Task, reason: str):
        """Escalate task to parent agent / human depending on autonomy level."""
        self._stats["escalations"] += 1
        task.status = TaskStatus.ESCALATED
        task.reasoning_trace.append(f"ESCALATED: {reason}")

        autonomy = self.spec.autonomy_level
        if autonomy <= AutonomyLevel.L2 or not self.spec.escalation_agent_id:
            # Escalate to human
            await self._emit_event(
                EventType.HUMAN_REVIEW_REQUIRED,
                {"task": task.to_dict(), "reason": reason},
                task_id=task.task_id
            )
            logger.warning(f"[{self.agent_id}] HUMAN ESCALATION: {reason}")
        else:
            await self._emit_event(
                EventType.ESCALATION_REQUIRED,
                {"escalate_to": self.spec.escalation_agent_id, "task": task.to_dict(), "reason": reason},
                task_id=task.task_id
            )

    # ── Internal Helpers ───────────────────────

    async def _handle_low_confidence(self, task: Task):
        conf = task.confidence_score
        if conf < 0.4:
            await self.escalate(task, f"Very low confidence: {conf:.2f}")
        elif conf < self.spec.confidence_threshold:
            await self._emit_event(
                EventType.LOW_CONFIDENCE,
                {"task_id": task.task_id, "confidence": conf, "threshold": self.spec.confidence_threshold},
                task_id=task.task_id
            )
            # Still mark completed — but flag it
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)
            self._stats["tasks_completed"] += 1

    async def _emit_event(self, event_type: EventType, payload: dict, task_id: Optional[str] = None):
        if not self._event_bus:
            return
        event = AgentEvent(
            event_type=event_type,
            source_agent=self.agent_id,
            related_task_id=task_id,
            payload=payload,
        )
        await self._event_bus.publish(event)

    async def _heartbeat_loop(self):
        while self._is_running:
            await asyncio.sleep(self._heartbeat_interval)
            await self._emit_event(EventType.HEARTBEAT, {
                "active_tasks": len(self._active_tasks),
                "completed": self._stats["tasks_completed"],
                "uptime_s": int(time.time() - self._stats["uptime_start"]),
            })

    def status_report(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "tier": self.tier.value,
            "division": self.division.value,
            "is_running": self._is_running,
            "active_tasks": len(self._active_tasks),
            **self._stats,
        }

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.agent_id} [{self.tier.value}]>"
