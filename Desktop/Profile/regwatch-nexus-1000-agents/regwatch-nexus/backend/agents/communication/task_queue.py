"""
RegWatch Nexus — Central Task Queue
Priority queue. Tasks assigned by Meta-CEO / C-suite downward.
Agents pull from their assigned queue; supervisors monitor all.
"""
from __future__ import annotations
import asyncio
import heapq
import logging
from typing import Optional
from backend.agents.communication.protocols import (
    TaskObject, TaskStatus, AgentTier, Department
)

logger = logging.getLogger(__name__)


class AgentTaskQueue:
    """
    Priority queue per agent. Lower priority number = higher urgency.
    Thread-safe via asyncio.Lock.
    """
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._heap: list[tuple[int, str, TaskObject]] = []   # (priority, task_id, task)
        self._tasks: dict[str, TaskObject] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(0)               # released on enqueue

    async def enqueue(self, task: TaskObject):
        async with self._lock:
            heapq.heappush(self._heap, (task.priority, task.task_id, task))
            self._tasks[task.task_id] = task
            task.status = TaskStatus.QUEUED
        self._semaphore.release()
        logger.info(f"[Queue:{self.agent_id}] Enqueued {task.task_id} (P{task.priority})")

    async def dequeue(self, timeout: float = 30.0) -> Optional[TaskObject]:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        async with self._lock:
            if self._heap:
                _, _, task = heapq.heappop(self._heap)
                task.status = TaskStatus.ASSIGNED
                return task
        return None

    async def get_status(self, task_id: str) -> Optional[TaskStatus]:
        return self._tasks.get(task_id, {}).status if task_id in self._tasks else None

    async def update_status(self, task_id: str, status: TaskStatus, output: dict = None):
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                if output:
                    self._tasks[task_id].output_data.update(output)

    def queue_depth(self) -> int:
        return len(self._heap)

    def pending_tasks(self) -> list[TaskObject]:
        return [t for _, _, t in self._heap]


class GlobalTaskRegistry:
    """
    Registry of all tasks across the system.
    Meta-CEO uses this for global visibility and rebalancing.
    """
    def __init__(self):
        self._tasks: dict[str, TaskObject] = {}
        self._agent_queues: dict[str, AgentTaskQueue] = {}
        self._lock = asyncio.Lock()

    def register_queue(self, agent_id: str) -> AgentTaskQueue:
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = AgentTaskQueue(agent_id)
        return self._agent_queues[agent_id]

    def get_queue(self, agent_id: str) -> Optional[AgentTaskQueue]:
        return self._agent_queues.get(agent_id)

    async def submit_task(self, task: TaskObject) -> bool:
        queue = self._agent_queues.get(task.assigned_agent_id)
        if not queue:
            logger.error(f"No queue for agent {task.assigned_agent_id}")
            return False
        async with self._lock:
            self._tasks[task.task_id] = task
        await queue.enqueue(task)
        return True

    async def get_task(self, task_id: str) -> Optional[TaskObject]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def update_task(self, task: TaskObject):
        async with self._lock:
            self._tasks[task.task_id] = task

    def get_dashboard(self) -> dict:
        from collections import Counter
        statuses = Counter(t.status.value for t in self._tasks.values())
        by_dept = Counter(t.department.value for t in self._tasks.values())
        return {
            "total_tasks": len(self._tasks),
            "by_status": dict(statuses),
            "by_department": dict(by_dept),
            "queue_depths": {aid: q.queue_depth() for aid, q in self._agent_queues.items()},
        }


# Global singletons
task_registry = GlobalTaskRegistry()
