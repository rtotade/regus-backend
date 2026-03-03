"""
Event Bus — Agent signaling system.
Publish-subscribe with typed events, no free-text broadcasting.
"""
from __future__ import annotations
import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Callable, Awaitable
from backend.orchestration.protocol import AgentEvent, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """
    Central event bus. Agents subscribe to event types.
    All events are typed AgentEvent objects — never raw strings.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._event_log: list[dict] = []
        self._event_counts: dict[str, int] = defaultdict(int)

    def subscribe(self, event_type: EventType, handler: Callable[[AgentEvent], Awaitable[None]],
                  agent_id: str = ""):
        key = event_type.value
        self._subscribers[key].append(handler)
        logger.debug(f"Agent {agent_id} subscribed to {key}")

    def subscribe_all(self, handler: Callable[[AgentEvent], Awaitable[None]]):
        """Subscribe to every event type — used by Audit and Meta-CEO agents."""
        for et in EventType:
            self._subscribers[et.value].append(handler)

    async def publish(self, event: AgentEvent):
        """Broadcast a typed event to all subscribers of that type."""
        key = event.event_type.value
        self._event_counts[key] += 1
        self._event_log.append(event.to_dict())
        if len(self._event_log) > 50_000:
            self._event_log = self._event_log[-50_000:]

        handlers = self._subscribers.get(key, [])
        if handlers:
            await asyncio.gather(
                *[self._safe_call(h, event) for h in handlers],
                return_exceptions=True,
            )

    async def _safe_call(self, handler: Callable, event: AgentEvent):
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"EventBus handler error on {event.event_type}: {e}")

    def get_recent_events(self, event_type: str = None, limit: int = 100) -> list[dict]:
        if event_type:
            return [e for e in self._event_log[-5000:] if e["event_type"] == event_type][-limit:]
        return self._event_log[-limit:]

    def get_stats(self) -> dict:
        return {
            "total_events": len(self._event_log),
            "by_type": dict(self._event_counts),
        }


# Singleton
_event_bus: EventBus | None = None

def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
