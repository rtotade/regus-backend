"""
RegWatch Nexus — Distributed Event Bus
Agents emit events here. Subscribers react asynchronously.
Redis Pub/Sub in production. In-process asyncio for local dev.
"""
from __future__ import annotations
import asyncio
import json
import logging
from collections import defaultdict
from typing import Callable, Awaitable
from backend.agents.communication.protocols import AgentEvent, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """
    Central signaling system. All agents publish here.
    Supervisors subscribe to events from their subordinates.
    Audit agent subscribes to ALL events.
    """
    def __init__(self):
        self._subscribers: dict[EventType, list[Callable]] = defaultdict(list)
        self._wildcard: list[Callable] = []    # subscribe to everything
        self._history: list[AgentEvent] = []   # last 10k events in memory
        self._max_history = 10_000
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: Callable[[AgentEvent], Awaitable[None]]):
        self._subscribers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__qualname__} to {event_type.value}")

    def subscribe_all(self, handler: Callable[[AgentEvent], Awaitable[None]]):
        """Subscribe to every event — used by Audit and Meta-CEO monitor."""
        self._wildcard.append(handler)

    async def publish(self, event: AgentEvent):
        async with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        handlers = self._subscribers.get(event.event_type, []) + self._wildcard
        if handlers:
            await asyncio.gather(
                *[self._safe_call(h, event) for h in handlers],
                return_exceptions=True
            )

    async def _safe_call(self, handler: Callable, event: AgentEvent):
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Event handler {handler.__qualname__} failed: {e}")

    def get_history(self, agent_id: str = None, event_type: EventType = None,
                    limit: int = 100) -> list[AgentEvent]:
        results = self._history
        if agent_id:
            results = [e for e in results if e.source_agent == agent_id]
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        return results[-limit:]

    def get_metrics(self) -> dict:
        type_counts = defaultdict(int)
        for e in self._history:
            type_counts[e.event_type.value] += 1
        return {"total_events": len(self._history), "by_type": dict(type_counts)}


# Global singleton — imported by all agents
event_bus = EventBus()
