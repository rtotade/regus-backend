"""
RegWatch Nexus — Agent Communication Protocol Standard
All inter-agent communication is structured. No free-text in production.

Task Object    → Unit of work flowing down the hierarchy
Event          → Signal flowing in any direction
Request        → Peer-to-peer structured query
Response       → Structured answer to Request
EscalationCall → Triggers upward chain review
"""
from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field


class AgentTier(str, Enum):
    """Hierarchy levels — determines memory scope and autonomy ceiling"""
    INTERN    = "intern"      # L0–L1: preprocess, log, format
    JUNIOR    = "junior"      # L1–L2: structured execution
    SENIOR    = "senior"      # L2–L3: reasoning tasks
    DIRECTOR  = "director"    # L3: task decomposition
    VP        = "vp"          # L3: planning + prioritisation
    C_SUITE   = "c_suite"     # L3–L4: domain orchestration
    META_CEO  = "meta_ceo"    # L4 within constraints: global alignment
    HUMAN     = "human"       # L4+: governance, capital, ethics override


class Department(str, Enum):
    OPERATIONS = "operations"
    TECHNOLOGY = "technology"
    PRODUCT    = "product"
    REVENUE    = "revenue"
    RISK       = "risk"
    AUDIT      = "audit"
    EXECUTIVE  = "executive"


class TaskStatus(str, Enum):
    QUEUED      = "queued"
    ASSIGNED    = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED     = "blocked"
    REVIEW      = "review"          # awaiting human/senior review
    COMPLETED   = "completed"
    FAILED      = "failed"
    ESCALATED   = "escalated"


class EventType(str, Enum):
    TASK_ASSIGNED       = "TASK_ASSIGNED"
    TASK_STARTED        = "TASK_STARTED"
    TASK_COMPLETED      = "TASK_COMPLETED"
    TASK_FAILED         = "TASK_FAILED"
    LOW_CONFIDENCE      = "LOW_CONFIDENCE"
    CONFLICT_DETECTED   = "CONFLICT_DETECTED"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"
    HUMAN_REQUIRED      = "HUMAN_REQUIRED"
    ANOMALY_DETECTED    = "ANOMALY_DETECTED"
    MEMORY_WRITTEN      = "MEMORY_WRITTEN"
    PEER_REQUEST        = "PEER_REQUEST"
    PEER_RESPONSE       = "PEER_RESPONSE"
    AUDIT_ENTRY         = "AUDIT_ENTRY"
    HEALTH_ALERT        = "HEALTH_ALERT"
    INITIATIVE_CREATED  = "INITIATIVE_CREATED"
    OBJECTIVE_SET       = "OBJECTIVE_SET"


class MemoryScope(str, Enum):
    AGENT_LOCAL      = "agent_local"       # only the owning agent
    DEPARTMENT_SHARED= "department_shared" # same department agents
    CROSS_DEPT_READ  = "cross_dept_read"   # read-only cross-dept
    ENTERPRISE_KG    = "enterprise_kg"     # enterprise knowledge graph (read-heavy)
    EXECUTIVE_ONLY   = "executive_only"    # C-suite and above
    AUDIT_IMMUTABLE  = "audit_immutable"   # immutable, system-wide


class AutonomyLevel(int, Enum):
    L0_HUMAN_CONTROLLED  = 0
    L1_AI_ASSISTED       = 1
    L2_AI_EXECUTES_HUMAN_REVIEWS = 2
    L3_AI_EXECUTES_HUMAN_AUDITS  = 3
    L4_FULLY_AUTONOMOUS_WITHIN_CONSTRAINTS = 4


@dataclass
class TaskObject:
    """Central unit of work. Flows top-down through the hierarchy."""
    task_id:              str            = field(default_factory=lambda: f"T-{uuid.uuid4().hex[:10].upper()}")
    title:                str            = ""
    description:          str            = ""
    priority:             int            = 5            # 1 (highest) – 10 (lowest)
    assigned_agent_id:    str            = ""
    parent_task_id:       Optional[str]  = None
    child_task_ids:       list[str]      = field(default_factory=list)
    required_memory_scope:MemoryScope    = MemoryScope.AGENT_LOCAL
    confidence_threshold: float          = 0.75         # escalate if result below this
    autonomy_ceiling:     AutonomyLevel  = AutonomyLevel.L3_AI_EXECUTES_HUMAN_AUDITS
    status:               TaskStatus     = TaskStatus.QUEUED
    department:           Department     = Department.OPERATIONS
    input_data:           dict           = field(default_factory=dict)
    output_data:          dict           = field(default_factory=dict)
    reasoning_trace:      list[str]      = field(default_factory=list)
    confidence_score:     float          = 0.0
    deadline:             Optional[str]  = None
    created_at:           str            = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at:           Optional[str]  = None
    completed_at:         Optional[str]  = None
    assigned_tier:        AgentTier      = AgentTier.JUNIOR
    escalation_count:     int            = 0
    audit_trail:          list[dict]     = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: (v.value if isinstance(v, Enum) else v) 
                for k, v in self.__dict__.items()}

    def add_trace(self, agent_id: str, action: str, detail: str = ""):
        self.reasoning_trace.append({
            "agent": agent_id, "action": action,
            "detail": detail, "ts": datetime.utcnow().isoformat()
        })

    def record_audit(self, agent_id: str, action: str, before: dict = None, after: dict = None):
        self.audit_trail.append({
            "agent": agent_id, "action": action,
            "before": before, "after": after,
            "ts": datetime.utcnow().isoformat()
        })


@dataclass
class AgentEvent:
    """Signal emitted by an agent onto the event bus."""
    event_id:      str       = field(default_factory=lambda: f"E-{uuid.uuid4().hex[:8].upper()}")
    event_type:    EventType = EventType.TASK_COMPLETED
    source_agent:  str       = ""
    related_task:  Optional[str] = None
    confidence_score: float  = 1.0
    payload:       dict      = field(default_factory=dict)
    timestamp:     str       = field(default_factory=lambda: datetime.utcnow().isoformat())
    requires_ack:  bool      = False


@dataclass
class PeerRequest:
    """Structured peer-to-peer request between agents at same or adjacent tiers."""
    request_id:          str      = field(default_factory=lambda: f"R-{uuid.uuid4().hex[:8].upper()}")
    requesting_agent_id: str      = ""
    receiving_agent_id:  str      = ""
    task_context:        str      = ""
    required_output_format: dict  = field(default_factory=dict)
    deadline:            Optional[str] = None
    payload:             dict     = field(default_factory=dict)
    created_at:          str      = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class PeerResponse:
    """Structured response to a PeerRequest. No free text — must be structured."""
    response_id:      str   = field(default_factory=lambda: f"RS-{uuid.uuid4().hex[:8].upper()}")
    request_id:       str   = ""
    source_agent_id:  str   = ""
    structured_output:dict  = field(default_factory=dict)
    confidence_score: float = 0.0
    dependency_notes: list[str] = field(default_factory=list)
    completed_at:     str   = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class EscalationCall:
    """Triggered when confidence < threshold or conflict detected."""
    escalation_id:   str    = field(default_factory=lambda: f"ESC-{uuid.uuid4().hex[:8].upper()}")
    from_agent_id:   str    = ""
    to_agent_id:     str    = ""       # immediate superior
    task_id:         str    = ""
    reason:          str    = ""
    confidence_achieved: float = 0.0
    confidence_required: float = 0.75
    conflicting_outputs: list  = field(default_factory=list)
    human_required:  bool   = False    # True = route to human governance layer
    created_at:      str    = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ConflictResolution:
    """Arbitration result when two agents disagree."""
    conflict_id:      str   = field(default_factory=lambda: f"CR-{uuid.uuid4().hex[:8].upper()}")
    agent_a:          str   = ""
    agent_b:          str   = ""
    output_a:         dict  = field(default_factory=dict)
    output_b:         dict  = field(default_factory=dict)
    confidence_a:     float = 0.0
    confidence_b:     float = 0.0
    arbitrator_agent: str   = ""
    resolution:       dict  = field(default_factory=dict)
    resolution_confidence: float = 0.0
    human_escalated:  bool  = False
    resolved_at:      str   = field(default_factory=lambda: datetime.utcnow().isoformat())
