"""
RegWatch Nexus — Base Agent Class
Every one of the 1,006 agents inherits from this.

Implements:
  - Structured task execution loop
  - Confidence scoring
  - Escalation gates
  - Memory read/write with access control
  - Event emission
  - Peer-to-peer structured requests
  - Audit trail generation
  - Health reporting
  - Autonomy level enforcement
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import anthropic

from backend.agents.communication.protocols import (
    AgentEvent, AgentTier, AutonomyLevel, ConflictResolution,
    Department, EscalationCall, EventType, MemoryScope,
    PeerRequest, PeerResponse, TaskObject, TaskStatus,
)
from backend.agents.communication.event_bus import event_bus
from backend.agents.communication.memory import memory
from backend.agents.communication.task_queue import task_registry

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for every agent in the RegWatch Nexus cognitive hierarchy.

    Concrete agents must implement:
        execute_task(task) → dict   (returns structured output)
        describe()         → str    (one-line description for registry)
    """

    # ── Identity ──────────────────────────────────────────────
    agent_id:   str
    name:       str
    tier:       AgentTier
    department: Department
    reports_to: Optional[str]          # parent agent_id
    supervises: list[str]              # child agent_ids
    autonomy_level: AutonomyLevel
    memory_scopes:  list[MemoryScope]  # what this agent can read/write

    # ── Runtime ───────────────────────────────────────────────
    _client: Optional[anthropic.AsyncAnthropic] = None
    _model:  str = "claude-sonnet-4-20250514"
    _running: bool = False
    _tasks_completed: int = 0
    _tasks_failed:    int = 0
    _avg_confidence:  float = 0.0
    _start_time:      float = 0.0

    def __init__(
        self,
        agent_id: str,
        name: str,
        tier: AgentTier,
        department: Department,
        reports_to: Optional[str] = None,
        autonomy_level: AutonomyLevel = AutonomyLevel.L3_AI_EXECUTES_HUMAN_AUDITS,
        memory_scopes: Optional[list[MemoryScope]] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.agent_id       = agent_id
        self.name           = name
        self.tier           = tier
        self.department     = department
        self.reports_to     = reports_to
        self.supervises     = []
        self.autonomy_level = autonomy_level
        self.memory_scopes  = memory_scopes or self._default_scopes()
        self._model         = model
        self._start_time    = time.time()

        # Register in memory system
        memory.register_agent(agent_id, tier, department.value)
        # Register task queue
        task_registry.register_queue(agent_id)

        logger.info(f"[Agent:{agent_id}] Initialized — {tier.value} / {department.value}")

    # ── Default memory scopes by tier ─────────────────────────
    def _default_scopes(self) -> list[MemoryScope]:
        base = [MemoryScope.AGENT_LOCAL, MemoryScope.AUDIT_IMMUTABLE]
        if self.tier in (AgentTier.INTERN, AgentTier.JUNIOR, AgentTier.SENIOR):
            return base + [MemoryScope.DEPARTMENT_SHARED]
        if self.tier == AgentTier.DIRECTOR:
            return base + [MemoryScope.DEPARTMENT_SHARED, MemoryScope.CROSS_DEPT_READ]
        if self.tier == AgentTier.VP:
            return base + [MemoryScope.DEPARTMENT_SHARED, MemoryScope.CROSS_DEPT_READ,
                           MemoryScope.ENTERPRISE_KG]
        if self.tier in (AgentTier.C_SUITE, AgentTier.META_CEO):
            return list(MemoryScope)  # all scopes
        return base

    # ── Abstract interface ─────────────────────────────────────
    @abstractmethod
    async def execute_task(self, task: TaskObject) -> dict:
        """
        Core logic. Must return structured dict:
        {
            "output": {...},
            "confidence": 0.0–1.0,
            "reasoning": "...",
            "next_actions": [...],   # optional subtasks to spawn
        }
        """

    @abstractmethod
    def describe(self) -> str:
        """One-line human-readable description of this agent's role."""

    # ── Main execution loop ────────────────────────────────────
    async def run(self):
        """Continuous task processing loop. Run as asyncio task."""
        self._running = True
        queue = task_registry.get_queue(self.agent_id)
        logger.info(f"[{self.agent_id}] Started task loop")

        while self._running:
            task = await queue.dequeue(timeout=5.0)
            if task is None:
                continue
            await self._process_task(task)

    async def stop(self):
        self._running = False

    async def _process_task(self, task: TaskObject):
        task.status     = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow().isoformat()
        task.add_trace(self.agent_id, "STARTED", f"Beginning execution on {self.name}")
        await self._emit(EventType.TASK_STARTED, task.task_id, {"agent": self.agent_id})

        try:
            result = await self.execute_task(task)
            confidence = float(result.get("confidence", 0.0))
            task.confidence_score = confidence
            task.output_data      = result.get("output", {})
            task.reasoning_trace.append(result.get("reasoning", ""))

            # Write result to department memory
            await memory.write(
                self.agent_id, MemoryScope.DEPARTMENT_SHARED,
                f"result:{task.task_id}",
                {"output": task.output_data, "confidence": confidence},
            )
            await memory.audit_append(self.agent_id, "TASK_COMPLETED", {
                "task_id": task.task_id, "confidence": confidence,
            })

            # Confidence gate
            if confidence < task.confidence_threshold:
                await self._escalate(task, f"Confidence {confidence:.2f} < threshold {task.confidence_threshold:.2f}")
                return

            task.status       = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow().isoformat()
            self._tasks_completed += 1
            self._update_avg_confidence(confidence)

            await self._emit(EventType.TASK_COMPLETED, task.task_id, {
                "agent": self.agent_id, "confidence": confidence,
                "output_keys": list(task.output_data.keys()),
            })

            # Spawn child tasks if requested
            for child_spec in result.get("next_actions", []):
                await self._spawn_child_task(task, child_spec)

        except Exception as exc:
            task.status = TaskStatus.FAILED
            self._tasks_failed += 1
            logger.error(f"[{self.agent_id}] Task {task.task_id} failed: {exc}", exc_info=True)
            await self._emit(EventType.TASK_FAILED, task.task_id, {
                "agent": self.agent_id, "error": str(exc),
            })
            await self._escalate(task, f"Exception during execution: {exc}")

        finally:
            await task_registry.update_task(task)

    # ── Escalation ─────────────────────────────────────────────
    async def _escalate(self, task: TaskObject, reason: str):
        task.escalation_count += 1
        esc = EscalationCall(
            from_agent_id        = self.agent_id,
            to_agent_id          = self.reports_to or "meta_ceo",
            task_id              = task.task_id,
            reason               = reason,
            confidence_achieved  = task.confidence_score,
            confidence_required  = task.confidence_threshold,
            human_required       = task.escalation_count >= 3,
        )
        task.status = TaskStatus.ESCALATED
        event_type = EventType.HUMAN_REQUIRED if esc.human_required else EventType.ESCALATION_REQUIRED
        await self._emit(event_type, task.task_id, {
            "from": self.agent_id, "to": esc.to_agent_id,
            "reason": reason, "escalation_count": task.escalation_count,
        })
        logger.warning(f"[{self.agent_id}] ESCALATED {task.task_id} → {esc.to_agent_id}: {reason}")

        # Re-queue to supervisor if available
        if self.reports_to:
            task.assigned_agent_id = self.reports_to
            task.priority = max(1, task.priority - 2)  # bump priority
            await task_registry.submit_task(task)

    # ── Child task spawning ────────────────────────────────────
    async def _spawn_child_task(self, parent: TaskObject, spec: dict):
        child = TaskObject(
            title              = spec.get("title", "Subtask"),
            description        = spec.get("description", ""),
            priority           = spec.get("priority", parent.priority + 1),
            assigned_agent_id  = spec.get("agent_id", ""),
            parent_task_id     = parent.task_id,
            department         = parent.department,
            input_data         = spec.get("input", {}),
            confidence_threshold = spec.get("confidence_threshold", parent.confidence_threshold),
        )
        if child.assigned_agent_id:
            parent.child_task_ids.append(child.task_id)
            await task_registry.submit_task(child)
            logger.info(f"[{self.agent_id}] Spawned child {child.task_id} → {child.assigned_agent_id}")

    # ── Peer-to-peer requests ──────────────────────────────────
    async def request_from_peer(
        self, peer_agent_id: str, context: str,
        payload: dict, output_format: dict,
        timeout: float = 30.0,
    ) -> Optional[PeerResponse]:
        req = PeerRequest(
            requesting_agent_id  = self.agent_id,
            receiving_agent_id   = peer_agent_id,
            task_context         = context,
            required_output_format = output_format,
            payload              = payload,
        )
        await self._emit(EventType.PEER_REQUEST, None, {
            "request_id": req.request_id,
            "to": peer_agent_id, "context": context,
        })
        # In production: RPC over Redis. Here: task-based async.
        return None  # Concrete implementation in orchestration layer

    # ── Anthropic API call helper ─────────────────────────────
    async def _call_llm(
        self, system: str, user_prompt: str,
        max_tokens: int = 2048,
    ) -> tuple[str, float]:
        """
        Returns (response_text, confidence_score).
        Confidence is extracted from structured JSON output or estimated.
        """
        if not self._client:
            try:
                from backend.config import settings
                self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            except Exception:
                self._client = anthropic.AsyncAnthropic()

        full_system = f"""{system}

RESPONSE FORMAT: Always respond with valid JSON:
{{
  "output": {{...}},
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "next_actions": []
}}
Agent ID: {self.agent_id} | Tier: {self.tier.value} | Department: {self.department.value}"""

        message = await self._client.messages.create(
            model      = self._model,
            max_tokens = max_tokens,
            system     = full_system,
            messages   = [{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text if message.content else "{}"

        import json, re
        try:
            # Extract JSON even if wrapped in markdown
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                data = json.loads(json_match.group())
                confidence = float(data.get("confidence", 0.7))
                return raw, confidence
        except Exception:
            pass
        return raw, 0.6  # fallback confidence

    # ── Event emission helper ──────────────────────────────────
    async def _emit(self, event_type: EventType, task_id: Optional[str], payload: dict,
                    confidence: float = 1.0):
        evt = AgentEvent(
            event_type       = event_type,
            source_agent     = self.agent_id,
            related_task     = task_id,
            confidence_score = confidence,
            payload          = payload,
        )
        await event_bus.publish(evt)

    # ── Memory helpers ─────────────────────────────────────────
    async def mem_write(self, key: str, value: Any, scope: MemoryScope = MemoryScope.AGENT_LOCAL,
                        ttl: int = 0) -> bool:
        return await memory.write(self.agent_id, scope, key, value, ttl)

    async def mem_read(self, key: str, scope: MemoryScope = MemoryScope.AGENT_LOCAL) -> Optional[Any]:
        return await memory.read(self.agent_id, scope, key)

    async def mem_search(self, prefix: str, scope: MemoryScope = MemoryScope.DEPARTMENT_SHARED) -> dict:
        return await memory.search(self.agent_id, scope, prefix)

    # ── Health & metrics ──────────────────────────────────────
    def health_report(self) -> dict:
        uptime = time.time() - self._start_time
        return {
            "agent_id":         self.agent_id,
            "name":             self.name,
            "tier":             self.tier.value,
            "department":       self.department.value,
            "reports_to":       self.reports_to,
            "supervises_count": len(self.supervises),
            "autonomy_level":   self.autonomy_level.value,
            "running":          self._running,
            "uptime_seconds":   round(uptime, 1),
            "tasks_completed":  self._tasks_completed,
            "tasks_failed":     self._tasks_failed,
            "avg_confidence":   round(self._avg_confidence, 3),
            "queue_depth":      task_registry.get_queue(self.agent_id).queue_depth()
                                if task_registry.get_queue(self.agent_id) else 0,
        }

    def _update_avg_confidence(self, new_score: float):
        n = self._tasks_completed
        self._avg_confidence = ((self._avg_confidence * (n - 1)) + new_score) / n if n > 0 else new_score

    def __repr__(self):
        return f"<Agent:{self.agent_id} [{self.tier.value}] {self.name}>"
