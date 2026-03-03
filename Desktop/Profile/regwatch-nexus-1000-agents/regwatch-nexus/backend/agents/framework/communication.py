"""
RegWatch Nexus — Agent Communication Infrastructure

Components:
  1. EventBus      — broadcast + targeted agent events
  2. TaskQueue     — priority-ordered task dispatch
  3. ConflictArbiter — multi-agent disagreement resolution
  4. AuditLogger   — immutable chain-of-custody log
"""
from __future__ import annotations
import asyncio
import uuid
import json
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable, Optional
from .base import (
    Task, AgentEvent, PeerRequest, PeerResponse,
    EventType, TaskStatus, AutonomyLevel
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  EVENT BUS
# ─────────────────────────────────────────────

class EventBus:
    """
    Central publish/subscribe event bus for agent signaling.
    Supports broadcast (target=None) and targeted delivery.
    Backed by asyncio queues — Redis adapter swappable in prod.
    """

    def __init__(self):
        # subscriber_id → asyncio.Queue
        self._subscribers: dict[str, asyncio.Queue] = {}
        # event_type → list of subscriber_ids
        self._topic_subs: dict[str, set[str]] = defaultdict(set)
        # Pending peer-request futures: request_id → Future
        self._peer_futures: dict[str, asyncio.Future] = {}
        self._event_history: list[AgentEvent] = []  # last 10k events in-mem
        self._max_history = 10_000
        self._stats = {"published": 0, "delivered": 0}

    # ── Subscription ───────────────────────────

    def subscribe(self, subscriber_id: str, event_types: list[EventType] = None) -> asyncio.Queue:
        """Register an agent to receive events. Returns its queue."""
        if subscriber_id not in self._subscribers:
            self._subscribers[subscriber_id] = asyncio.Queue(maxsize=500)
        if event_types:
            for et in event_types:
                self._topic_subs[et.value].add(subscriber_id)
        else:
            # Subscribe to all
            self._topic_subs["*"].add(subscriber_id)
        return self._subscribers[subscriber_id]

    def unsubscribe(self, subscriber_id: str):
        self._subscribers.pop(subscriber_id, None)
        for topic_subs in self._topic_subs.values():
            topic_subs.discard(subscriber_id)

    # ── Publishing ─────────────────────────────

    async def publish(self, event: AgentEvent):
        """Publish event to target agent or all subscribers."""
        self._stats["published"] += 1

        # History
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # Audit log (non-blocking)
        asyncio.create_task(AuditLogger.log_event(event))

        # Targeted delivery
        if event.target_agent and event.target_agent in self._subscribers:
            await self._deliver(event.target_agent, event)
            return

        # Broadcast to topic subscribers + wildcard subscribers
        targets = (
            self._topic_subs.get(event.event_type.value, set()) |
            self._topic_subs.get("*", set())
        )
        for sid in targets:
            if sid != event.source_agent:  # Don't echo back
                await self._deliver(sid, event)

    async def _deliver(self, subscriber_id: str, event: AgentEvent):
        q = self._subscribers.get(subscriber_id)
        if q:
            try:
                q.put_nowait(event)
                self._stats["delivered"] += 1
            except asyncio.QueueFull:
                logger.warning(f"EventBus: Queue full for {subscriber_id} — dropping event {event.event_id}")

    # ── Peer Requests ──────────────────────────

    async def send_peer_request(self, req: PeerRequest, timeout: int = 30) -> PeerResponse:
        """
        Send structured peer request and await structured response.
        Times out after `timeout` seconds.
        """
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._peer_futures[req.request_id] = future

        # Wrap in event
        await self.publish(AgentEvent(
            event_type=EventType.PEER_REQUEST,
            source_agent=req.requesting_agent,
            target_agent=req.receiving_agent,
            payload={"request": req.__dict__},
        ))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Peer request {req.request_id} timed out")
            return PeerResponse(
                request_id=req.request_id,
                responding_agent="timeout",
                confidence_score=0.0,
                dependency_notes=["Request timed out"],
            )
        finally:
            self._peer_futures.pop(req.request_id, None)

    def resolve_peer_request(self, response: PeerResponse):
        """Called by receiving agent to resolve a pending peer request."""
        future = self._peer_futures.get(response.request_id)
        if future and not future.done():
            future.set_result(response)

    def stats(self) -> dict:
        return {**self._stats, "subscribers": len(self._subscribers)}


# ─────────────────────────────────────────────
#  TASK QUEUE
# ─────────────────────────────────────────────

class TaskQueue:
    """
    Priority-ordered task dispatch system.
    Priority 1 = highest urgency. 10 = background.
    Supports agent-level routing + deadletter queue.
    """

    def __init__(self):
        # PriorityQueue entries: (priority, sequence, task)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._sequence = 0  # Tiebreaker (FIFO within priority)

        # Per-agent queues for direct assignment
        self._agent_queues: dict[str, asyncio.Queue] = {}

        # Dead-letter queue (failed tasks that exhausted retries)
        self._dead_letter: list[Task] = []

        # All tasks for lookup
        self._all_tasks: dict[str, Task] = {}
        self._stats = {"enqueued": 0, "dispatched": 0, "dead_lettered": 0}

    def register_agent(self, agent_id: str) -> asyncio.Queue:
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = asyncio.Queue(maxsize=200)
        return self._agent_queues[agent_id]

    async def enqueue(self, task: Task):
        """Add task to the queue. Routed to agent queue if assigned."""
        self._all_tasks[task.task_id] = task
        self._stats["enqueued"] += 1

        if task.assigned_agent and task.assigned_agent in self._agent_queues:
            await self._agent_queues[task.assigned_agent].put(task)
        else:
            self._sequence += 1
            await self._queue.put((task.priority, self._sequence, task))

        logger.debug(f"TaskQueue: Enqueued {task.task_id} (p={task.priority}, agent={task.assigned_agent})")

    async def dequeue(self, agent_id: Optional[str] = None) -> Task:
        """Get next task. Agent-specific queue takes priority."""
        if agent_id and agent_id in self._agent_queues:
            aq = self._agent_queues[agent_id]
            if not aq.empty():
                self._stats["dispatched"] += 1
                return await aq.get()

        # Fall through to global priority queue
        _, _, task = await self._queue.get()
        self._stats["dispatched"] += 1
        return task

    async def dead_letter(self, task: Task):
        task.status = TaskStatus.FAILED
        self._dead_letter.append(task)
        self._stats["dead_lettered"] += 1
        logger.error(f"TaskQueue: Dead-lettered {task.task_id} — {task.reasoning_trace[-1] if task.reasoning_trace else 'no trace'}")

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._all_tasks.get(task_id)

    def stats(self) -> dict:
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
            "dead_letter_count": len(self._dead_letter),
        }


# ─────────────────────────────────────────────
#  CONFLICT ARBITER
# ─────────────────────────────────────────────

class ConflictArbiter:
    """
    Resolves disagreements between peer agents.
    Protocol:
      1. Compare confidence scores
      2. If tied → third-model arbitration
      3. If confidence < 0.5 → escalate to Risk Officer
      4. If human threshold breached → HUMAN_REVIEW_REQUIRED
    """

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._risk_agent_id = "AGT-RISK-DIR-001"  # Risk Director
        self._human_confidence_threshold = 0.4

    async def arbitrate(
        self,
        task: Task,
        response_a: dict,
        response_b: dict,
        agent_a: str,
        agent_b: str,
    ) -> dict:
        """
        Resolve two conflicting agent outputs.
        Returns winning response dict.
        """
        conf_a = response_a.get("confidence_score", 0.5)
        conf_b = response_b.get("confidence_score", 0.5)

        # Step 1: Simple confidence comparison
        if abs(conf_a - conf_b) > 0.15:
            winner = response_a if conf_a > conf_b else response_b
            winning_agent = agent_a if conf_a > conf_b else agent_b
            logger.info(f"Conflict resolved by confidence: {winning_agent} wins ({max(conf_a, conf_b):.2f})")
            winner["_arbiter"] = "confidence_comparison"
            return winner

        # Step 2: Emit conflict for third-model arbitration
        await self._event_bus.publish(AgentEvent(
            event_type=EventType.CONFLICT_DETECTED,
            source_agent="conflict_arbiter",
            payload={
                "task_id": task.task_id,
                "agent_a": agent_a,
                "agent_b": agent_b,
                "conf_a": conf_a,
                "conf_b": conf_b,
                "response_a": response_a,
                "response_b": response_b,
            }
        ))

        # Step 3: Low joint confidence → escalate
        avg_conf = (conf_a + conf_b) / 2
        if avg_conf < self._human_confidence_threshold:
            await self._event_bus.publish(AgentEvent(
                event_type=EventType.HUMAN_REVIEW_REQUIRED,
                source_agent="conflict_arbiter",
                payload={"task_id": task.task_id, "reason": f"Conflict unresolvable, avg_conf={avg_conf:.2f}"}
            ))
            # Return higher-confidence option with flag
            result = response_a if conf_a >= conf_b else response_b
            result["_arbiter"] = "human_required"
            result["_human_review"] = True
            return result

        # Default: higher confidence wins
        result = response_a if conf_a >= conf_b else response_b
        result["_arbiter"] = "default_higher_conf"
        return result


# ─────────────────────────────────────────────
#  AUDIT LOGGER (Immutable)
# ─────────────────────────────────────────────

class AuditLogger:
    """
    Immutable audit trail for all agent actions.
    Written to append-only log + database (async).
    Cannot be modified by any agent (even executives).
    """
    _log_file = "/var/log/regwatch/audit.jsonl"
    _db_queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)
    _buffer: list[dict] = []
    _flush_threshold = 100

    @classmethod
    async def log_event(cls, event: AgentEvent):
        entry = {
            "audit_id": f"aud_{uuid.uuid4().hex[:12]}",
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "source_agent": event.source_agent,
            "target_agent": event.target_agent,
            "task_id": event.related_task_id,
            "confidence": event.confidence_score,
            "payload_keys": list(event.payload.keys()),
            "timestamp": event.timestamp.isoformat(),
        }
        cls._buffer.append(entry)
        if len(cls._buffer) >= cls._flush_threshold:
            await cls._flush()

    @classmethod
    async def log_task(cls, task: Task, agent_id: str, action: str):
        entry = {
            "audit_id": f"aud_{uuid.uuid4().hex[:12]}",
            "action": action,
            "agent_id": agent_id,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status.value,
            "confidence": task.confidence_score,
            "reasoning_steps": len(task.reasoning_trace),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        cls._buffer.append(entry)

    @classmethod
    async def _flush(cls):
        if not cls._buffer:
            return
        batch = cls._buffer.copy()
        cls._buffer.clear()
        # In production: write to DB via async pg connection
        # For now: log to stdout
        for entry in batch:
            logger.debug(f"AUDIT: {json.dumps(entry)}")

    @classmethod
    async def get_task_chain(cls, task_id: str) -> list[dict]:
        """Return full audit chain for a task."""
        return [e for e in cls._buffer if e.get("task_id") == task_id]


# ─────────────────────────────────────────────
#  ORCHESTRATION DISPATCHER
# ─────────────────────────────────────────────

class Dispatcher:
    """
    Routes tasks from the queue to registered agent handlers.
    The dispatcher runs the main event loop that keeps agents fed.
    """

    def __init__(self, task_queue: TaskQueue, event_bus: EventBus):
        self._task_queue = task_queue
        self._event_bus = event_bus
        self._agent_handlers: dict[str, Callable] = {}
        self._is_running = False

    def register_agent(self, agent_id: str, handler: Callable[[Task], Awaitable[Task]]):
        """Register an agent's handle_task method."""
        self._agent_handlers[agent_id] = handler
        self._task_queue.register_agent(agent_id)
        logger.debug(f"Dispatcher: Registered agent {agent_id}")

    async def dispatch_loop(self):
        """Main dispatch loop — runs continuously."""
        self._is_running = True
        logger.info("Dispatcher: Main loop started")
        while self._is_running:
            try:
                task = await asyncio.wait_for(
                    self._task_queue.dequeue(), timeout=1.0
                )
                if task.assigned_agent in self._agent_handlers:
                    asyncio.create_task(self._dispatch_one(task))
                else:
                    logger.warning(f"Dispatcher: No handler for agent {task.assigned_agent}")
                    await self._task_queue.dead_letter(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.exception(f"Dispatcher loop error: {e}")

    async def _dispatch_one(self, task: Task):
        handler = self._agent_handlers.get(task.assigned_agent)
        if not handler:
            return
        try:
            start = time.time()
            result_task = await handler(task)
            latency = int((time.time() - start) * 1000)
            await AuditLogger.log_task(result_task, task.assigned_agent, "completed")
            logger.debug(f"Dispatcher: {task.task_id} completed in {latency}ms")
        except Exception as e:
            logger.exception(f"Dispatcher: Task {task.task_id} dispatch failed: {e}")
            task.retry_count += 1
            if task.retry_count >= task.max_retries:
                await self._task_queue.dead_letter(task)
            else:
                task.status = TaskStatus.PENDING
                await self._task_queue.enqueue(task)

    def stop(self):
        self._is_running = False
