"""
Memory Management — Role-based access, layered storage.
Agents cannot read memory they have no clearance for.
"""
from __future__ import annotations
import json
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional
from backend.orchestration.protocol import MemoryScope, AgentTier


class MemoryAccessError(PermissionError):
    pass


# Clearance map: what each tier can read/write
TIER_CLEARANCES = {
    AgentTier.INTERN:   [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE],
    AgentTier.JUNIOR:   [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT],
    AgentTier.SENIOR:   [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO],
    AgentTier.DIRECTOR: [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO],
    AgentTier.VP:       [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO],
    AgentTier.C_SUITE:  [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO, MemoryScope.EXECUTIVE],
    AgentTier.META_CEO: [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO, MemoryScope.EXECUTIVE],
    AgentTier.HUMAN:    [s for s in MemoryScope],  # Humans can see everything
}

WRITE_CLEARANCES = {
    AgentTier.INTERN:   [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE],
    AgentTier.JUNIOR:   [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT],
    AgentTier.SENIOR:   [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT],
    AgentTier.DIRECTOR: [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO],
    AgentTier.VP:       [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO],
    AgentTier.C_SUITE:  [MemoryScope.TASK_LOCAL, MemoryScope.AGENT_PRIVATE, MemoryScope.DEPARTMENT, MemoryScope.ENTERPRISE_RO, MemoryScope.EXECUTIVE],
    AgentTier.META_CEO: [s for s in MemoryScope if s != MemoryScope.AUDIT_IMMUTABLE],
    AgentTier.HUMAN:    [s for s in MemoryScope],
}


class MemoryStore:
    """In-process memory store. Production: back with Redis + PostgreSQL."""
    
    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {
            scope.value: {} for scope in MemoryScope
        }
        self._audit_log: list[dict] = []
        self._lock = asyncio.Lock()

    def _check_read(self, tier: AgentTier, scope: MemoryScope):
        if scope not in TIER_CLEARANCES.get(tier, []):
            raise MemoryAccessError(f"{tier.value} cannot read from {scope.value}")

    def _check_write(self, tier: AgentTier, scope: MemoryScope):
        if scope == MemoryScope.AUDIT_IMMUTABLE and tier != AgentTier.HUMAN:
            raise MemoryAccessError("AUDIT_IMMUTABLE is write-once by system only")
        if scope not in WRITE_CLEARANCES.get(tier, []):
            raise MemoryAccessError(f"{tier.value} cannot write to {scope.value}")

    async def read(self, key: str, scope: MemoryScope, tier: AgentTier,
                   agent_id: str = "") -> Optional[Any]:
        self._check_read(tier, scope)
        async with self._lock:
            ns = self._store[scope.value]
            # Department-scoped keys are prefixed by dept
            entry = ns.get(key)
            if entry:
                entry["last_read"] = datetime.utcnow().isoformat()
                entry["read_count"] = entry.get("read_count", 0) + 1
            return entry["value"] if entry else None

    async def write(self, key: str, value: Any, scope: MemoryScope,
                    tier: AgentTier, agent_id: str = "", ttl_seconds: int = 0):
        self._check_write(tier, scope)
        async with self._lock:
            entry = {
                "value": value, "written_by": agent_id,
                "written_at": datetime.utcnow().isoformat(),
                "read_count": 0,
                "expires_at": (datetime.utcnow() + timedelta(seconds=ttl_seconds)).isoformat()
                              if ttl_seconds else None,
            }
            if scope == MemoryScope.AUDIT_IMMUTABLE:
                # Compute hash for integrity verification
                entry["hash"] = hashlib.sha256(
                    json.dumps(value, sort_keys=True, default=str).encode()
                ).hexdigest()
            self._store[scope.value][key] = entry
        self._audit_log.append({
            "op": "write", "key": key, "scope": scope.value,
            "agent_id": agent_id, "tier": tier.value,
            "ts": datetime.utcnow().isoformat(),
        })

    async def search(self, pattern: str, scope: MemoryScope,
                     tier: AgentTier) -> list[dict]:
        self._check_read(tier, scope)
        async with self._lock:
            results = []
            for key, entry in self._store[scope.value].items():
                if pattern.lower() in key.lower():
                    results.append({"key": key, "value": entry["value"],
                                    "written_by": entry.get("written_by"),
                                    "written_at": entry.get("written_at")})
            return results

    async def append_to_list(self, key: str, item: Any, scope: MemoryScope,
                              tier: AgentTier, agent_id: str = "", max_len: int = 1000):
        self._check_write(tier, scope)
        async with self._lock:
            ns = self._store[scope.value]
            existing = ns.get(key, {"value": []})
            lst = existing.get("value", [])
            lst.append(item)
            if len(lst) > max_len:
                lst = lst[-max_len:]
            ns[key] = {**existing, "value": lst,
                       "written_by": agent_id,
                       "written_at": datetime.utcnow().isoformat()}

    def export_audit_log(self) -> list[dict]:
        return list(self._audit_log)

    def get_stats(self) -> dict:
        return {
            scope: len(entries)
            for scope, entries in self._store.items()
        }


# Singleton — shared across all agents in the process
_memory_store: Optional[MemoryStore] = None

def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store
