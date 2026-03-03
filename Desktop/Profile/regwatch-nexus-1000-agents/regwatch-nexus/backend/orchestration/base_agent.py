"""
Base Agent — The cognitive template for all 1000+ agents.
Every agent in the system inherits this. The pattern is identical
across tiers — only the LLM prompt, tools, and confidence thresholds differ.
"""
from __future__ import annotations
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Any
import anthropic

from backend.orchestration.protocol import (
    Task, AgentEvent, AgentRequest, AgentResponse, EscalationPacket,
    TaskStatus, EventType, AgentTier, MemoryScope, AutonomyLevel, TaskPriority
)
from backend.orchestration.memory import get_memory_store
from backend.orchestration.event_bus import get_event_bus
from backend.orchestration.task_queue import get_task_queue
from backend.config import settings

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base agent. Defines the invariant cognitive loop:
    
    PULL → REASON → ACT → VERIFY → EMIT → LOOP
    
    Subclasses implement: `_reason()` — the core intelligence.
    Everything else — memory access, event emission, escalation — is inherited.
    """

    # Override in subclasses
    AGENT_ID_PREFIX: str        = "agent"
    AGENT_TIER: AgentTier       = AgentTier.JUNIOR
    DEPARTMENT: str             = "general"
    AGENT_TYPE_KEY: str         = "base"     # Matches Task.agent_type
    HANDLES_TASK_TYPES: list[str] = []
    AUTONOMY_LEVEL: AutonomyLevel = AutonomyLevel.L3_AI_EXECUTES_AUDIT
    CONFIDENCE_THRESHOLD: float  = 0.75      # Below this → escalate
    ESCALATE_TO_TYPE: str        = ""        # Which agent type receives escalations
    MODEL: str                  = "claude-haiku-4-5-20251001"  # Interns/juniors get Haiku
    MAX_TOKENS: int             = 1500
    SYSTEM_PROMPT: str          = "You are a specialized AI agent."

    def __init__(self, instance_id: int = 0):
        self.instance_id = instance_id
        self.agent_id = f"{self.AGENT_ID_PREFIX}_{instance_id:04d}"
        self._memory = get_memory_store()
        self._event_bus = get_event_bus()
        self._task_queue = get_task_queue()
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._running = False
        self._current_task: Optional[Task] = None
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._avg_confidence = 0.0
        logger.info(f"Agent initialized: {self.agent_id} [{self.AGENT_TIER.value}]")

    # ── LIFECYCLE ──────────────────────────────────────────────────

    async def start(self):
        """Start the agent's main cognitive loop."""
        self._running = True
        logger.info(f"{self.agent_id} started")
        await self._emit(EventType.AGENT_HEALTH, {"status": "started", "agent_id": self.agent_id}, confidence=1.0)
        asyncio.create_task(self._cognitive_loop())

    async def stop(self):
        self._running = False
        logger.info(f"{self.agent_id} stopped")

    async def _cognitive_loop(self):
        """The infinite pull-reason-act loop."""
        while self._running:
            try:
                task = await self._task_queue.dequeue(self.AGENT_TYPE_KEY, timeout=2.0)
                if task:
                    await self._process(task)
                else:
                    await asyncio.sleep(0.1)  # Idle
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"{self.agent_id} loop error: {e}")
                await asyncio.sleep(1.0)

    async def _process(self, task: Task):
        """Process one task: reason → verify → emit → escalate if needed."""
        self._current_task = task
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()
        task.reasoning_trace.append(f"[{self.agent_id}] Starting task: {task.title}")

        start_t = time.monotonic()
        try:
            # Load memory context
            context = await self._load_context(task)

            # Core intelligence — implemented by each subclass
            result, confidence, trace = await self._reason(task, context)

            task.reasoning_trace.extend(trace)
            task.confidence_score = confidence

            if confidence < task.confidence_threshold:
                # Not confident enough — escalate
                await self._escalate(task, confidence, result)
            else:
                # Accept and complete
                await self._task_queue.complete(task.task_id, result, confidence)
                await self._store_result(task, result)
                await self._emit(EventType.TASK_COMPLETED, {
                    "task_id": task.task_id, "title": task.title,
                    "confidence": confidence,
                    "duration_ms": int((time.monotonic() - start_t) * 1000),
                }, confidence)
                self._tasks_completed += 1
                self._avg_confidence = (
                    (self._avg_confidence * (self._tasks_completed - 1) + confidence)
                    / self._tasks_completed
                )

        except Exception as e:
            logger.error(f"{self.agent_id} error on {task.task_id}: {e}")
            task.reasoning_trace.append(f"[ERROR] {str(e)}")
            await self._task_queue.fail(task.task_id, str(e))
            await self._emit(EventType.TASK_FAILED, {
                "task_id": task.task_id, "error": str(e)
            }, confidence=0.0)
            self._tasks_failed += 1
        finally:
            self._current_task = None

    @abstractmethod
    async def _reason(self, task: Task, context: dict) -> tuple[dict, float, list[str]]:
        """
        Core intelligence. Implemented by each specialized agent.
        Returns: (result_dict, confidence_float, reasoning_trace_list)
        """
        pass

    # ── LLM CALL ──────────────────────────────────────────────────

    async def _llm(self, prompt: str, system_override: str = None,
                   tools: list = None, max_tokens: int = None) -> tuple[str, float]:
        """Call LLM. Returns (response_text, estimated_confidence)."""
        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": self.MODEL,
            "max_tokens": max_tokens or self.MAX_TOKENS,
            "system": system_override or self.SYSTEM_PROMPT,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            resp = await self._client.messages.create(**kwargs)
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
            # Rough confidence from stop reason + length
            conf = 0.85 if resp.stop_reason == "end_turn" else 0.60
            return text, conf
        except anthropic.RateLimitError:
            await self._emit(EventType.RATE_LIMIT_HIT, {"agent_id": self.agent_id}, 1.0)
            await asyncio.sleep(5)
            raise
        except Exception as e:
            logger.error(f"{self.agent_id} LLM call failed: {e}")
            raise

    # ── MEMORY HELPERS ────────────────────────────────────────────

    async def _load_context(self, task: Task) -> dict:
        """Load relevant memory scopes into task context dict."""
        context = dict(task.context)
        for scope_str in task.required_memory_scopes:
            try:
                scope = MemoryScope(scope_str)
                if scope in [MemoryScope.TASK_LOCAL, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO]:
                    val = await self._memory.read(
                        f"context:{task.department}", scope, self.AGENT_TIER, self.agent_id
                    )
                    if val:
                        context[f"memory_{scope_str}"] = val
            except Exception:
                pass
        return context

    async def _store_result(self, task: Task, result: dict):
        """Write task result into appropriate memory scope."""
        key = f"result:{task.task_id}"
        await self._memory.write(
            key, result, MemoryScope.DEPARTMENT, self.AGENT_TIER, self.agent_id, ttl_seconds=86400
        )
        # Audit trail
        await self._memory.append_to_list(
            f"audit:{task.department}:{datetime.utcnow().strftime('%Y%m%d')}",
            {"task_id": task.task_id, "agent": self.agent_id,
             "confidence": task.confidence_score, "ts": datetime.utcnow().isoformat()},
            MemoryScope.AUDIT_IMMUTABLE, AgentTier.HUMAN, self.agent_id
        )

    # ── EMIT HELPERS ──────────────────────────────────────────────

    async def _emit(self, event_type: EventType, payload: dict, confidence: float = 1.0):
        event = AgentEvent(
            event_type=event_type,
            source_agent_id=self.agent_id,
            source_agent_tier=self.AGENT_TIER.value,
            related_task_id=self._current_task.task_id if self._current_task else "",
            confidence_score=confidence,
            payload=payload,
        )
        await self._event_bus.publish(event)

    # ── ESCALATION ────────────────────────────────────────────────

    async def _escalate(self, task: Task, confidence: float, partial_result: dict):
        """Hand off low-confidence task to higher-tier agent."""
        packet = EscalationPacket(
            triggering_agent_id=self.agent_id,
            triggering_task_id=task.task_id,
            reason=f"Confidence {confidence:.2f} below threshold {task.confidence_threshold}",
            confidence_score=confidence,
            threshold_required=task.confidence_threshold,
            context={"partial_result": partial_result, "task": task.to_dict()},
            recommended_action="Higher-tier agent review required",
            requires_human=(confidence < 0.4),
        )
        await self._emit(EventType.ESCALATION_REQUIRED, {
            "escalation": {
                "escalation_id": packet.escalation_id,
                "reason": packet.reason,
                "confidence": confidence,
                "requires_human": packet.requires_human,
            }
        }, confidence)

        if self.ESCALATE_TO_TYPE:
            await self._task_queue.escalate(
                task.task_id, packet.reason, self.ESCALATE_TO_TYPE
            )
        else:
            # No higher tier → fail gracefully
            await self._task_queue.fail(task.task_id, f"Cannot escalate: no tier above {self.AGENT_TIER.value}")

    # ── PEER REQUEST ──────────────────────────────────────────────

    async def _request_peer(self, target_type: str, context: dict,
                             output_format: str = "json") -> AgentResponse:
        """Structured peer-to-peer request. No free-text."""
        req = AgentRequest(
            requesting_agent_id=self.agent_id,
            receiving_agent_id=target_type,  # Queue-based, not instance-specific
            task_context=context,
            required_output_format=output_format,
        )
        # Create a new task for the peer
        peer_task = Task(
            title=f"Peer request from {self.agent_id}",
            description=f"Peer query: {context.get('query', '')}",
            agent_type=target_type,
            parent_task_id=self._current_task.task_id if self._current_task else None,
            context=context,
            priority=TaskPriority.HIGH,
        )
        await self._task_queue.enqueue(peer_task)
        # Simple wait-for-result (production: use futures + callbacks)
        for _ in range(30):
            await asyncio.sleep(0.5)
            t = self._task_queue.get_task(peer_task.task_id)
            if t and t.status == TaskStatus.COMPLETED:
                return AgentResponse(
                    request_id=req.request_id,
                    structured_output=t.result or {},
                    confidence_score=t.confidence_score,
                )
        return AgentResponse(request_id=req.request_id, success=False, error="Timeout")

    # ── STATUS ────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "tier": self.AGENT_TIER.value,
            "department": self.DEPARTMENT,
            "type": self.AGENT_TYPE_KEY,
            "running": self._running,
            "current_task": self._current_task.task_id if self._current_task else None,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "avg_confidence": round(self._avg_confidence, 3),
        }
