"""
Central Task Queue — Priority-ordered, agent-typed work queue.
Every unit of work flows through here. No direct agent-to-agent calls
bypassing the queue (except approved peer requests).
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from collections import defaultdict
from typing import Optional
from backend.orchestration.protocol import Task, TaskStatus, TaskPriority, AgentTier

logger = logging.getLogger(__name__)


class TaskQueue:
    """
    Multi-priority queue for all 1000+ agent tasks.
    Agents pull from their own type queue.
    """

    def __init__(self):
        # Separate queue per agent_type, each sorted by priority
        self._queues: dict[str, asyncio.PriorityQueue] = {}
        self._all_tasks: dict[str, Task] = {}     # task_id → Task
        self._completed: list[str] = []
        self._failed: list[str] = []
        self._escalated: list[str] = []
        self._lock = asyncio.Lock()
        self._stats = defaultdict(int)

    def _get_queue(self, agent_type: str) -> asyncio.PriorityQueue:
        if agent_type not in self._queues:
            self._queues[agent_type] = asyncio.PriorityQueue()
        return self._queues[agent_type]

    async def enqueue(self, task: Task) -> str:
        """Add a task to the appropriate agent-type queue."""
        task.status = TaskStatus.QUEUED
        async with self._lock:
            self._all_tasks[task.task_id] = task
        # Priority queue sorts by (priority_int, timestamp)
        q = self._get_queue(task.agent_type)
        sort_key = (task.priority.value, task.created_at.timestamp())
        await q.put((sort_key, task.task_id))
        self._stats["enqueued"] += 1
        logger.debug(f"Queued {task.task_id} → {task.agent_type} [{task.priority.name}]")
        return task.task_id

    async def dequeue(self, agent_type: str, timeout: float = 1.0) -> Optional[Task]:
        """Pull next task for an agent type. Non-blocking with timeout."""
        q = self._get_queue(agent_type)
        try:
            _, task_id = await asyncio.wait_for(q.get(), timeout=timeout)
            task = self._all_tasks.get(task_id)
            if task:
                task.status = TaskStatus.IN_PROGRESS
                task.started_at = datetime.utcnow()
                self._stats["dequeued"] += 1
            return task
        except asyncio.TimeoutError:
            return None

    async def complete(self, task_id: str, result: dict, confidence: float):
        """Mark task done with result and confidence score."""
        async with self._lock:
            task = self._all_tasks.get(task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.confidence_score = confidence
                task.completed_at = datetime.utcnow()
                self._completed.append(task_id)
                self._stats["completed"] += 1

    async def fail(self, task_id: str, error: str, retry: bool = True):
        """Mark task failed. Retry if within max_retries."""
        async with self._lock:
            task = self._all_tasks.get(task_id)
            if not task:
                return
            task.retry_count += 1
            if retry and task.retry_count <= task.max_retries:
                task.status = TaskStatus.QUEUED
                q = self._get_queue(task.agent_type)
                sort_key = (task.priority.value, task.created_at.timestamp())
                await q.put((sort_key, task_id))
                self._stats["retried"] += 1
                logger.warning(f"Task {task_id} failed, retry {task.retry_count}/{task.max_retries}")
            else:
                task.status = TaskStatus.FAILED
                task.error = error
                self._failed.append(task_id)
                self._stats["failed"] += 1

    async def escalate(self, task_id: str, reason: str, escalate_to: str):
        """Escalate blocked/low-confidence task up the hierarchy."""
        async with self._lock:
            task = self._all_tasks.get(task_id)
            if task:
                task.status = TaskStatus.ESCALATED
                task.context["escalation_reason"] = reason
                task.context["escalated_to"] = escalate_to
                self._escalated.append(task_id)
                self._stats["escalated"] += 1
        # Re-queue to the higher agent
        if task:
            task.agent_type = escalate_to
            task.status = TaskStatus.QUEUED
            q = self._get_queue(escalate_to)
            await q.put(((TaskPriority.HIGH.value, task.created_at.timestamp()), task_id))

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._all_tasks.get(task_id)

    def get_queue_depths(self) -> dict[str, int]:
        return {at: q.qsize() for at, q in self._queues.items()}

    def get_stats(self) -> dict:
        return {
            **self._stats,
            "total_tracked": len(self._all_tasks),
            "pending_escalated": len(self._escalated),
            "queue_depths": self.get_queue_depths(),
        }

    def get_all_escalated(self) -> list[Task]:
        return [self._all_tasks[tid] for tid in self._escalated
                if tid in self._all_tasks]


_task_queue: TaskQueue | None = None

def get_task_queue() -> TaskQueue:
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue
