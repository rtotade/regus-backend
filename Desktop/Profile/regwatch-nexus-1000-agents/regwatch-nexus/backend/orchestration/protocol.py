"""
RegWatch Nexus — Agent Communication Protocol
All 1000+ agents speak this exact language. No free text in production.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional
from dataclasses import dataclass, field


# ── AUTONOMY LEVELS ────────────────────────────────────────────────
class AutonomyLevel(int, Enum):
    L0_HUMAN_CONTROLLED   = 0   # Human executes
    L1_AI_ASSISTED        = 1   # AI suggests, human decides
    L2_AI_EXECUTES_REVIEW = 2   # AI executes, human reviews output
    L3_AI_EXECUTES_AUDIT  = 3   # AI executes, human audits periodically
    L4_FULL_AUTONOMOUS    = 4   # Fully autonomous within constraints


# ── AGENT TIERS ────────────────────────────────────────────────────
class AgentTier(str, Enum):
    HUMAN          = "human"          # Board, CEO
    META_CEO       = "meta_ceo"       # Master Orchestrator
    C_SUITE        = "c_suite"        # COO, CTO, CPO, CRO×2
    VP             = "vp"             # VP layer (25)
    DIRECTOR       = "director"       # Director layer (100)
    SENIOR         = "senior"         # Senior agents (200)
    JUNIOR         = "junior"         # Junior agents (400)
    INTERN         = "intern"         # Intern agents (300)


# ── TASK STATUS ────────────────────────────────────────────────────
class TaskStatus(str, Enum):
    PENDING       = "pending"
    QUEUED        = "queued"
    IN_PROGRESS   = "in_progress"
    BLOCKED       = "blocked"
    ESCALATED     = "escalated"
    COMPLETED     = "completed"
    FAILED        = "failed"
    CANCELLED     = "cancelled"


# ── TASK PRIORITY ──────────────────────────────────────────────────
class TaskPriority(int, Enum):
    CRITICAL = 1
    HIGH     = 2
    MEDIUM   = 3
    LOW      = 4
    BACKLOG  = 5


# ── EVENT TYPES ────────────────────────────────────────────────────
class EventType(str, Enum):
    # Lifecycle
    TASK_CREATED       = "task_created"
    TASK_ASSIGNED      = "task_assigned"
    TASK_STARTED       = "task_started"
    TASK_COMPLETED     = "task_completed"
    TASK_FAILED        = "task_failed"
    TASK_CANCELLED     = "task_cancelled"
    # Intelligence
    INSIGHT_GENERATED  = "insight_generated"
    ALERT_DETECTED     = "alert_detected"
    PATTERN_FOUND      = "pattern_found"
    ANOMALY_DETECTED   = "anomaly_detected"
    # Quality
    LOW_CONFIDENCE     = "low_confidence"
    CONFLICT_DETECTED  = "conflict_detected"
    VALIDATION_FAILED  = "validation_failed"
    QUALITY_FLAG       = "quality_flag"
    # Escalation
    ESCALATION_REQUIRED = "escalation_required"
    HUMAN_REVIEW_NEEDED = "human_review_needed"
    THRESHOLD_BREACHED  = "threshold_breached"
    # System
    AGENT_HEALTH       = "agent_health"
    RATE_LIMIT_HIT     = "rate_limit_hit"
    DEPENDENCY_READY   = "dependency_ready"
    MEMORY_UPDATED     = "memory_updated"


# ── MEMORY SCOPE ───────────────────────────────────────────────────
class MemoryScope(str, Enum):
    TASK_LOCAL     = "task_local"      # This task only, auto-cleared
    AGENT_PRIVATE  = "agent_private"   # This agent only
    DEPARTMENT     = "department"      # Same dept agents
    ENTERPRISE_RO  = "enterprise_ro"   # Read from enterprise KB
    EXECUTIVE      = "executive"       # C-suite + above only
    AUDIT_IMMUTABLE = "audit_immutable" # Write-once, never deleted


# ── CORE DATA STRUCTURES ──────────────────────────────────────────

@dataclass
class Task:
    """The atomic unit of work. Every agent operates on Tasks."""
    task_id: str                        = field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    title: str                          = ""
    description: str                    = ""
    agent_type: str                     = ""          # Which agent class handles this
    assigned_agent_id: str              = ""          # Specific agent instance
    parent_task_id: Optional[str]       = None        # Decomposition chain
    child_task_ids: list[str]           = field(default_factory=list)
    priority: TaskPriority              = TaskPriority.MEDIUM
    status: TaskStatus                  = TaskStatus.PENDING
    autonomy_required: AutonomyLevel    = AutonomyLevel.L3_AI_EXECUTES_AUDIT
    confidence_threshold: float         = 0.75        # Below = escalate
    deadline: Optional[datetime]        = None
    context: dict[str, Any]             = field(default_factory=dict)
    required_memory_scopes: list[str]   = field(default_factory=list)
    output_format: str                  = "json"
    max_retries: int                    = 3
    retry_count: int                    = 0
    created_at: datetime                = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime]      = None
    completed_at: Optional[datetime]    = None
    result: Optional[dict]             = None
    error: Optional[str]               = None
    confidence_score: float             = 0.0
    reasoning_trace: list[str]          = field(default_factory=list)
    department: str                     = ""
    tags: list[str]                     = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "title": self.title,
            "description": self.description, "agent_type": self.agent_type,
            "assigned_agent_id": self.assigned_agent_id,
            "parent_task_id": self.parent_task_id,
            "priority": self.priority.value, "status": self.status.value,
            "confidence_threshold": self.confidence_threshold,
            "confidence_score": self.confidence_score,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "context": self.context, "result": self.result,
            "reasoning_trace": self.reasoning_trace,
            "department": self.department, "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AgentEvent:
    """All agent signals. Typed, structured, never free-text."""
    event_id: str               = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    event_type: EventType       = EventType.TASK_COMPLETED
    source_agent_id: str        = ""
    source_agent_tier: str      = ""
    related_task_id: str        = ""
    confidence_score: float     = 1.0
    payload: dict[str, Any]     = field(default_factory=dict)
    timestamp: datetime         = field(default_factory=datetime.utcnow)
    requires_ack: bool          = False
    escalation_chain: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source_agent_id": self.source_agent_id,
            "related_task_id": self.related_task_id,
            "confidence_score": self.confidence_score,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AgentRequest:
    """Peer-to-peer structured request. No free text."""
    request_id: str             = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    requesting_agent_id: str    = ""
    receiving_agent_id: str     = ""
    task_context: dict          = field(default_factory=dict)
    required_output_format: str = "json"
    deadline: Optional[datetime] = None
    priority: TaskPriority      = TaskPriority.MEDIUM
    timestamp: datetime         = field(default_factory=datetime.utcnow)


@dataclass
class AgentResponse:
    """Peer-to-peer structured response. Always typed."""
    request_id: str             = ""
    responding_agent_id: str    = ""
    structured_output: dict     = field(default_factory=dict)
    confidence_score: float     = 0.0
    dependency_notes: list[str] = field(default_factory=list)
    reasoning_trace: list[str]  = field(default_factory=list)
    timestamp: datetime         = field(default_factory=datetime.utcnow)
    success: bool               = True
    error: Optional[str]        = None


@dataclass
class EscalationPacket:
    """Triggered when confidence < threshold or conflict detected."""
    escalation_id: str          = field(default_factory=lambda: f"esc_{uuid.uuid4().hex[:12]}")
    triggering_agent_id: str    = ""
    triggering_task_id: str     = ""
    reason: str                 = ""
    confidence_score: float     = 0.0
    threshold_required: float   = 0.75
    context: dict               = field(default_factory=dict)
    recommended_action: str     = ""
    escalation_chain: list[str] = field(default_factory=list)  # Who reviewed it
    resolved: bool              = False
    resolution: Optional[str]  = None
    created_at: datetime        = field(default_factory=datetime.utcnow)
    requires_human: bool        = False
