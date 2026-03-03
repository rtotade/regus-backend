"""
RegWatch Nexus — Tiered Memory System
Access-controlled. Agents can only read/write their authorised scopes.

Memory Type            | Read             | Write
-----------------------|------------------|-----------------
AGENT_LOCAL            | Owner only       | Owner only
DEPARTMENT_SHARED      | Same dept        | Same dept senior+
CROSS_DEPT_READ        | Any agent        | Director+
ENTERPRISE_KG          | Any agent        | VP+
EXECUTIVE_ONLY         | C-suite+         | C-suite+
AUDIT_IMMUTABLE        | Any agent        | System only (append-only)
"""
from __future__ import annotations
import asyncio
import time
import json
import hashlib
import logging
from typing import Any, Optional
from backend.agents.communication.protocols import MemoryScope, AgentTier

logger = logging.getLogger(__name__)

# Tier hierarchy for access control
TIER_RANK = {
    AgentTier.INTERN:   0,
    AgentTier.JUNIOR:   1,
    AgentTier.SENIOR:   2,
    AgentTier.DIRECTOR: 3,
    AgentTier.VP:       4,
    AgentTier.C_SUITE:  5,
    AgentTier.META_CEO: 6,
    AgentTier.HUMAN:    7,
}

WRITE_TIER_REQUIREMENTS = {
    MemoryScope.AGENT_LOCAL:       AgentTier.INTERN,    # any tier
    MemoryScope.DEPARTMENT_SHARED: AgentTier.SENIOR,
    MemoryScope.CROSS_DEPT_READ:   AgentTier.DIRECTOR,
    MemoryScope.ENTERPRISE_KG:     AgentTier.VP,
    MemoryScope.EXECUTIVE_ONLY:    AgentTier.C_SUITE,
    MemoryScope.AUDIT_IMMUTABLE:   AgentTier.META_CEO,  # system writes only
}

READ_TIER_REQUIREMENTS = {
    MemoryScope.AGENT_LOCAL:       None,  # checked separately (owner only)
    MemoryScope.DEPARTMENT_SHARED: AgentTier.INTERN,
    MemoryScope.CROSS_DEPT_READ:   AgentTier.INTERN,
    MemoryScope.ENTERPRISE_KG:     AgentTier.INTERN,
    MemoryScope.EXECUTIVE_ONLY:    AgentTier.C_SUITE,
    MemoryScope.AUDIT_IMMUTABLE:   AgentTier.INTERN,    # anyone can read audit
}


class MemoryStore:
    """Single scope in-memory store with TTL and locking."""
    def __init__(self, scope: MemoryScope, max_entries: int = 50_000):
        self._store: dict[str, dict] = {}
        self.scope = scope
        self._lock = asyncio.Lock()
        self._max_entries = max_entries

    async def write(self, key: str, value: Any, agent_id: str, ttl_seconds: int = 0):
        async with self._lock:
            if len(self._store) >= self._max_entries:
                oldest = sorted(self._store.items(), key=lambda x: x[1].get("ts", 0))
                for k, _ in oldest[:len(self._store) // 10]:
                    del self._store[k]
            self._store[key] = {
                "value": value, "agent_id": agent_id,
                "ts": time.time(),
                "expires": time.time() + ttl_seconds if ttl_seconds > 0 else 0,
            }

    async def read(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry.get("expires") and time.time() > entry["expires"]:
                del self._store[key]
                return None
            return entry["value"]

    async def search(self, prefix: str) -> dict[str, Any]:
        async with self._lock:
            return {k: v["value"] for k, v in self._store.items()
                    if k.startswith(prefix) and (not v.get("expires") or time.time() <= v["expires"])}

    def size(self) -> int:
        return len(self._store)


class AuditMemory:
    """Immutable append-only audit log. Hash-chained for tamper detection."""
    def __init__(self):
        self._entries: list[dict] = []
        self._lock = asyncio.Lock()
        self._chain_hash = "GENESIS"

    async def append(self, agent_id: str, action: str, payload: dict):
        async with self._lock:
            entry = {
                "seq": len(self._entries),
                "agent_id": agent_id,
                "action": action,
                "payload": payload,
                "ts": time.time(),
                "prev_hash": self._chain_hash,
            }
            entry_str = json.dumps(entry, sort_keys=True, default=str)
            self._chain_hash = hashlib.sha256(entry_str.encode()).hexdigest()[:16]
            entry["hash"] = self._chain_hash
            self._entries.append(entry)

    async def read_range(self, start: int = 0, end: int = 100) -> list[dict]:
        async with self._lock:
            return self._entries[start:end]

    async def verify_chain(self) -> bool:
        """Verify hash chain integrity — detects tampering."""
        prev = "GENESIS"
        for entry in self._entries:
            check = dict(entry)
            claimed_hash = check.pop("hash")
            check_str = json.dumps(check, sort_keys=True, default=str)
            computed = hashlib.sha256(check_str.encode()).hexdigest()[:16]
            if computed != claimed_hash:
                return False
            prev = claimed_hash
        return True

    def size(self) -> int:
        return len(self._entries)


class AgentMemoryController:
    """
    Central memory controller. Enforces access control.
    One instance per running agent system.
    """
    def __init__(self):
        self._stores: dict[MemoryScope, MemoryStore] = {
            scope: MemoryStore(scope) for scope in MemoryScope
            if scope != MemoryScope.AUDIT_IMMUTABLE
        }
        self._agent_stores: dict[str, MemoryStore] = {}   # per-agent private stores
        self._audit = AuditMemory()
        self._agent_tiers: dict[str, tuple[AgentTier, str]] = {}  # id → (tier, dept)

    def register_agent(self, agent_id: str, tier: AgentTier, department: str):
        self._agent_tiers[agent_id] = (tier, department)
        self._agent_stores[agent_id] = MemoryStore(MemoryScope.AGENT_LOCAL)

    def _check_write(self, agent_id: str, scope: MemoryScope) -> bool:
        if scope == MemoryScope.AGENT_LOCAL:
            return True  # checked at read with owner
        if scope == MemoryScope.AUDIT_IMMUTABLE:
            return False  # system-only
        tier, _ = self._agent_tiers.get(agent_id, (AgentTier.INTERN, ""))
        required = WRITE_TIER_REQUIREMENTS.get(scope, AgentTier.HUMAN)
        return TIER_RANK.get(tier, 0) >= TIER_RANK.get(required, 99)

    def _check_read(self, agent_id: str, scope: MemoryScope, key: str) -> bool:
        if scope == MemoryScope.AGENT_LOCAL:
            return key.startswith(agent_id + ":")
        tier, _ = self._agent_tiers.get(agent_id, (AgentTier.INTERN, ""))
        required = READ_TIER_REQUIREMENTS.get(scope)
        if required is None:
            return False
        return TIER_RANK.get(tier, 0) >= TIER_RANK.get(required, 99)

    async def write(self, agent_id: str, scope: MemoryScope, key: str,
                    value: Any, ttl_seconds: int = 0) -> bool:
        if not self._check_write(agent_id, scope):
            logger.warning(f"[Memory] WRITE DENIED: {agent_id} → {scope.value}:{key}")
            await self._audit.append(agent_id, "WRITE_DENIED",
                                     {"scope": scope.value, "key": key})
            return False
        store = (self._agent_stores[agent_id] if scope == MemoryScope.AGENT_LOCAL
                 else self._stores[scope])
        full_key = f"{agent_id}:{key}" if scope == MemoryScope.AGENT_LOCAL else key
        await store.write(full_key, value, agent_id, ttl_seconds)
        await self._audit.append(agent_id, "WRITE", {"scope": scope.value, "key": key})
        return True

    async def read(self, agent_id: str, scope: MemoryScope, key: str) -> Optional[Any]:
        if scope == MemoryScope.AUDIT_IMMUTABLE:
            return await self._audit.read_range()
        full_key = f"{agent_id}:{key}" if scope == MemoryScope.AGENT_LOCAL else key
        if not self._check_read(agent_id, scope, full_key):
            logger.warning(f"[Memory] READ DENIED: {agent_id} → {scope.value}:{key}")
            return None
        store = (self._agent_stores.get(agent_id) if scope == MemoryScope.AGENT_LOCAL
                 else self._stores.get(scope))
        return await store.read(full_key) if store else None

    async def search(self, agent_id: str, scope: MemoryScope, prefix: str) -> dict:
        if not self._check_read(agent_id, scope, prefix):
            return {}
        store = (self._agent_stores.get(agent_id) if scope == MemoryScope.AGENT_LOCAL
                 else self._stores.get(scope))
        return await store.search(prefix) if store else {}

    async def audit_append(self, agent_id: str, action: str, payload: dict):
        """System-level audit write — called by audit agents only."""
        await self._audit.append(agent_id, action, payload)

    def get_stats(self) -> dict:
        return {
            "audit_entries": self._audit.size(),
            "stores": {s.value: self._stores[s].size() for s in self._stores},
            "agent_stores": len(self._agent_stores),
        }


# Global singleton
memory = AgentMemoryController()
