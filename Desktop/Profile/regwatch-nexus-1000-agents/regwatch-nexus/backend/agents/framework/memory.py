"""
RegWatch Nexus — Agent Memory Architecture

Five access-controlled memory layers:
  TASK_LOCAL   — per-agent scratchpad (ephemeral)
  DEPARTMENT   — shared within division
  ENTERPRISE   — global knowledge graph (read-heavy)
  EXECUTIVE    — C-level agents only
  AUDIT        — immutable, append-only (system-wide)

Production backend: Redis (short-term) + PostgreSQL (long-term) + Pinecone (vector)
Development: in-memory dicts
"""
from __future__ import annotations
import asyncio
import json
import time
import logging
import hashlib
from typing import Any, Optional
from dataclasses import dataclass, field
from .base import MemoryScope, AgentTier

logger = logging.getLogger(__name__)


# Access control matrix: tier → allowed scopes
MEMORY_ACCESS_RULES: dict[AgentTier, list[MemoryScope]] = {
    AgentTier.INTERN:    [MemoryScope.TASK_LOCAL],
    AgentTier.JUNIOR:    [MemoryScope.TASK_LOCAL, MemoryScope.DEPARTMENT],
    AgentTier.SENIOR:    [MemoryScope.TASK_LOCAL, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE],
    AgentTier.DIRECTOR:  [MemoryScope.TASK_LOCAL, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE],
    AgentTier.VP:        [MemoryScope.TASK_LOCAL, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE, MemoryScope.EXECUTIVE],
    AgentTier.EXECUTIVE: [MemoryScope.TASK_LOCAL, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE, MemoryScope.EXECUTIVE],
}


@dataclass
class MemoryEntry:
    key: str
    value: Any
    scope: MemoryScope
    namespace: str  # division name or "global"
    agent_id: str
    ttl: int  # seconds, 0 = permanent
    created_at: float = field(default_factory=time.time)
    access_count: int = 0

    def is_expired(self) -> bool:
        if self.ttl == 0:
            return False
        return time.time() > self.created_at + self.ttl

    def to_context(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "age_seconds": int(time.time() - self.created_at),
            "scope": self.scope.value,
        }


class MemoryStore:
    """
    Layered memory store for the entire agent hierarchy.
    Thread-safe asyncio implementation.
    Production adapters: swap _store with Redis/PostgreSQL clients.
    """

    def __init__(self):
        # scope → namespace → key → MemoryEntry
        self._store: dict[str, dict[str, dict[str, MemoryEntry]]] = {
            scope.value: {} for scope in MemoryScope
        }
        self._lock = asyncio.Lock()
        self._vector_index: dict[str, list] = {}  # key → embedding vector
        self._stats = {
            "reads": 0,
            "writes": 0,
            "cache_hits": 0,
            "evictions": 0,
        }
        # Start background eviction
        asyncio.create_task(self._eviction_loop())

    # ── Read ───────────────────────────────────

    async def get(
        self,
        scope: MemoryScope,
        namespace: str,
        key: str,
        agent_tier: Optional[AgentTier] = None,
    ) -> Optional[Any]:
        """Get value from memory. Returns None if not found or expired."""
        if agent_tier and not self._check_access(agent_tier, scope):
            logger.warning(f"Memory ACCESS DENIED: tier={agent_tier} scope={scope}")
            return None

        async with self._lock:
            self._stats["reads"] += 1
            scope_store = self._store.get(scope.value, {})
            ns_store = scope_store.get(namespace, {})
            entry = ns_store.get(key)

            if entry is None:
                # Try global namespace for ENTERPRISE scope
                if scope == MemoryScope.ENTERPRISE:
                    entry = scope_store.get("global", {}).get(key)
                if entry is None:
                    return None

            if entry.is_expired():
                await self._evict(scope, namespace, key)
                return None

            entry.access_count += 1
            self._stats["cache_hits"] += 1
            return entry.value

    async def get_many(
        self,
        scope: MemoryScope,
        namespace: str,
        prefix: str = "",
        limit: int = 50,
    ) -> list[MemoryEntry]:
        """Get all entries matching a key prefix."""
        async with self._lock:
            scope_store = self._store.get(scope.value, {})
            ns_store = scope_store.get(namespace, {})
            results = []
            for key, entry in ns_store.items():
                if key.startswith(prefix) and not entry.is_expired():
                    results.append(entry)
                    if len(results) >= limit:
                        break
            return results

    # ── Write ──────────────────────────────────

    async def set(
        self,
        scope: MemoryScope,
        namespace: str,
        key: str,
        value: Any,
        agent_id: str = "system",
        ttl: int = 3600,
        agent_tier: Optional[AgentTier] = None,
    ):
        """Write value to memory layer."""
        if scope == MemoryScope.AUDIT:
            raise PermissionError("AUDIT scope is immutable — use AuditLogger")

        if agent_tier and not self._check_access(agent_tier, scope):
            raise PermissionError(f"Tier {agent_tier} cannot write to scope {scope}")

        async with self._lock:
            self._stats["writes"] += 1
            scope_store = self._store.setdefault(scope.value, {})
            ns_store = scope_store.setdefault(namespace, {})
            ns_store[key] = MemoryEntry(
                key=key,
                value=value,
                scope=scope,
                namespace=namespace,
                agent_id=agent_id,
                ttl=ttl,
            )

    async def delete(self, scope: MemoryScope, namespace: str, key: str):
        if scope == MemoryScope.AUDIT:
            raise PermissionError("Cannot delete from AUDIT scope")
        async with self._lock:
            self._store.get(scope.value, {}).get(namespace, {}).pop(key, None)

    # ── Enterprise Knowledge Graph ──────────────

    async def knowledge_graph_upsert(self, entity_type: str, entity_id: str, data: dict):
        """
        Write to Enterprise Knowledge Graph (global, long-lived).
        Used by Intelligence agents for regulatory entity knowledge.
        """
        key = f"kg:{entity_type}:{entity_id}"
        await self.set(
            MemoryScope.ENTERPRISE,
            "global",
            key,
            data,
            agent_id="system",
            ttl=0,  # permanent
        )

    async def knowledge_graph_get(self, entity_type: str, entity_id: str) -> Optional[dict]:
        key = f"kg:{entity_type}:{entity_id}"
        return await self.get(MemoryScope.ENTERPRISE, "global", key)

    async def knowledge_graph_search(self, entity_type: str, limit: int = 20) -> list[MemoryEntry]:
        prefix = f"kg:{entity_type}:"
        return await self.get_many(MemoryScope.ENTERPRISE, "global", prefix, limit)

    # ── Context Summarization ──────────────────

    async def summarize_department_context(
        self,
        division: str,
        topic: str,
        limit: int = 20,
    ) -> str:
        """
        Summarize department memory into a context string for LLM consumption.
        Used by Director+ agents to build context for their reports.
        """
        entries = await self.get_many(MemoryScope.DEPARTMENT, division, topic, limit)
        if not entries:
            return f"No department memory for {division}/{topic}"
        lines = []
        for e in entries:
            val = e.value if isinstance(e.value, str) else json.dumps(e.value)[:200]
            lines.append(f"[{e.key}] {val}")
        return "\n".join(lines)

    # ── Executive Briefing ─────────────────────

    async def get_executive_briefing(self, topic: str) -> Optional[dict]:
        """C-level access to strategic memory."""
        return await self.get(MemoryScope.EXECUTIVE, "global", f"brief:{topic}")

    async def set_executive_briefing(self, topic: str, brief: dict, agent_id: str):
        await self.set(MemoryScope.EXECUTIVE, "global", f"brief:{topic}", brief, agent_id, ttl=86400)

    # ── Access Control ─────────────────────────

    @staticmethod
    def _check_access(tier: AgentTier, scope: MemoryScope) -> bool:
        allowed = MEMORY_ACCESS_RULES.get(tier, [])
        return scope in allowed

    def allowed_scopes_for_tier(self, tier: AgentTier) -> list[MemoryScope]:
        return MEMORY_ACCESS_RULES.get(tier, [])

    # ── Eviction ──────────────────────────────

    async def _evict(self, scope: MemoryScope, namespace: str, key: str):
        self._store.get(scope.value, {}).get(namespace, {}).pop(key, None)
        self._stats["evictions"] += 1

    async def _eviction_loop(self):
        """Background TTL eviction every 60 seconds."""
        while True:
            await asyncio.sleep(60)
            async with self._lock:
                for scope_val, namespaces in self._store.items():
                    for ns, entries in namespaces.items():
                        expired_keys = [k for k, e in entries.items() if e.is_expired()]
                        for k in expired_keys:
                            del entries[k]
                            self._stats["evictions"] += 1

    def stats(self) -> dict:
        sizes = {}
        for scope_val, namespaces in self._store.items():
            total = sum(len(ns) for ns in namespaces.values())
            sizes[scope_val] = total
        return {**self._stats, "sizes": sizes}


# ─────────────────────────────────────────────
#  WORKING MEMORY (per-task context window)
# ─────────────────────────────────────────────

class WorkingMemory:
    """
    Ephemeral per-task context window.
    Helps agents maintain reasoning state within a single task.
    Auto-discarded when task completes.
    """

    def __init__(self, task_id: str, max_tokens: int = 4000):
        self.task_id = task_id
        self._max_tokens = max_tokens
        self._segments: list[dict] = []
        self._token_estimate = 0

    def add(self, role: str, content: str, metadata: dict = None):
        tokens = len(content) // 4  # rough estimate
        if self._token_estimate + tokens > self._max_tokens:
            # Drop oldest non-system segment
            for i, seg in enumerate(self._segments):
                if seg["role"] != "system":
                    self._token_estimate -= len(seg["content"]) // 4
                    self._segments.pop(i)
                    break

        self._segments.append({
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })
        self._token_estimate += tokens

    def to_messages(self) -> list[dict]:
        """Format as Anthropic messages list."""
        return [{"role": s["role"], "content": s["content"]} for s in self._segments]

    def to_context_string(self) -> str:
        """Format as a single context string for injection."""
        lines = []
        for s in self._segments:
            lines.append(f"[{s['role'].upper()}]: {s['content']}")
        return "\n\n".join(lines)

    def clear(self):
        self._segments.clear()
        self._token_estimate = 0

    @property
    def size(self) -> int:
        return len(self._segments)


# ─────────────────────────────────────────────
#  MEMORY MANAGER (singleton per process)
# ─────────────────────────────────────────────

class MemoryManager:
    """
    Singleton manager coordinating all memory operations.
    Provides working memory lifecycle management.
    """

    _instance: Optional[MemoryManager] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._store = MemoryStore()
            cls._instance._working_memories: dict[str, WorkingMemory] = {}
        return cls._instance

    @property
    def store(self) -> MemoryStore:
        return self._store

    def get_working_memory(self, task_id: str, max_tokens: int = 4000) -> WorkingMemory:
        if task_id not in self._working_memories:
            self._working_memories[task_id] = WorkingMemory(task_id, max_tokens)
        return self._working_memories[task_id]

    def release_working_memory(self, task_id: str):
        self._working_memories.pop(task_id, None)

    async def cross_department_broadcast(
        self,
        division: str,
        key: str,
        value: Any,
        agent_id: str,
        ttl: int = 7200,
    ):
        """Write to department scope, visible to all agents in division."""
        await self._store.set(
            MemoryScope.DEPARTMENT, division, key, value, agent_id, ttl
        )

    def stats(self) -> dict:
        return {
            "memory_store": self._store.stats(),
            "working_memories_active": len(self._working_memories),
        }
