"""
RegWatch Nexus — Agent System Admin API
Human governance interface for the 1,336-agent system.

All routes require admin key authentication.
This is the human-in-the-loop control plane.

Endpoints:
  GET  /api/v1/agents/dashboard           — Full system status
  GET  /api/v1/agents/                    — List all agents (with filters)
  GET  /api/v1/agents/{id}                — Single agent health
  POST /api/v1/agents/{id}/task           — Dispatch task to specific agent
  GET  /api/v1/agents/escalations         — Pending human decisions
  POST /api/v1/agents/escalations/{id}/resolve — Resolve an escalation
  GET  /api/v1/agents/org-chart           — Full org chart
  POST /api/v1/agents/emergency-stop      — Emergency halt all L4 agents
  POST /api/v1/agents/resume              — Resume from pause
  GET  /api/v1/agents/metrics             — Event bus + task metrics
  GET  /api/v1/agents/memory/stats        — Memory system stats
  GET  /api/v1/agents/audit               — Audit chain entries
  POST /api/v1/agents/objective           — Inject new objective to Meta-CEO
  GET  /api/v1/agents/hierarchy           — Visual hierarchy with counts
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["Agent System — Admin"])

# ── Auth ─────────────────────────────────────────────────────────
ADMIN_KEY_HEADER = APIKeyHeader(name="X-Admin-Key", auto_error=True)

async def require_admin(api_key: str = Security(ADMIN_KEY_HEADER)):
    from backend.config import settings
    if api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return api_key


# ── Request/Response Models ───────────────────────────────────────
class TaskDispatchRequest(BaseModel):
    title:       str
    description: str
    input_data:  dict = {}
    priority:    int  = 5

class ObjectiveRequest(BaseModel):
    title:       str
    description: str
    quarter:     str = "Q1 2026"
    kpis:        dict = {}

class EscalationResolutionRequest(BaseModel):
    resolution:  str
    human_user:  str = "board"


# ── Routes ────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(_: str = Depends(require_admin)):
    """
    Complete system dashboard for human governance layer.
    Shows: system status, all agents, task queue, memory stats, escalations.
    """
    from backend.agents.orchestration.engine import engine
    return engine.get_dashboard()


@router.get("/")
async def list_agents(
    department: Optional[str] = None,
    tier:       Optional[str] = None,
    _: str = Depends(require_admin),
):
    """List all agents with optional filters."""
    from backend.agents.registry import list_agents as _list
    return {"agents": _list(department=department, tier=tier)}


@router.get("/hierarchy")
async def get_hierarchy(_: str = Depends(require_admin)):
    """Full org chart with counts per tier."""
    return {
        "hierarchy": {
            "human_layer": {
                "board": {"count": 1, "type": "human_governance"},
                "ceo":   {"count": 1, "type": "human_hybrid"},
            },
            "ai_executive": {
                "meta_ceo": {"count": 1, "autonomy": "L4", "model": "claude-opus-4-6"},
            },
            "ai_functional": {
                "c_suite":  {"count": 5,   "autonomy": "L3", "model": "claude-sonnet"},
                "vp":       {"count": 15,  "autonomy": "L3", "model": "claude-haiku"},
                "director": {"count": 45,  "autonomy": "L3", "model": "claude-haiku"},
                "senior":   {"count": 266, "autonomy": "L2", "model": "claude-haiku"},
                "junior":   {"count": 587, "autonomy": "L2", "model": "claude-haiku"},
                "intern":   {"count": 467, "autonomy": "L1", "model": "claude-haiku"},
            },
            "total":        1336,
            "communication": {
                "protocol":     "structured_task_objects",
                "event_bus":    "redis_pubsub",
                "memory":       "tiered_access_controlled",
                "no_free_chat": True,
            },
        }
    }


@router.get("/org-chart")
async def get_org_chart(_: str = Depends(require_admin)):
    """Full org chart for governance visualization."""
    from backend.agents.orchestration.engine import engine
    return engine.get_org_chart()


@router.get("/escalations")
async def get_escalations(_: str = Depends(require_admin)):
    """All pending human decisions. These require board/CEO action."""
    from backend.agents.orchestration.engine import engine
    return {
        "pending": engine.list_pending_escalations(),
        "total_escalations": len(engine._escalation_queue),
    }


@router.post("/escalations/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: str,
    body: EscalationResolutionRequest,
    _: str = Depends(require_admin),
):
    """Human resolves a pending escalation."""
    from backend.agents.orchestration.engine import engine
    result = await engine.resolve_escalation(
        escalation_id, body.resolution, body.human_user
    )
    return {"resolved": result}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, _: str = Depends(require_admin)):
    """Get health and status of a specific agent."""
    from backend.agents.orchestration.engine import engine
    agent = engine.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {
        "health":     agent.health_report(),
        "describes":  agent.describe(),
        "supervises": agent.supervises,
        "reports_to": agent.reports_to,
    }


@router.post("/{agent_id}/task")
async def dispatch_task(
    agent_id: str,
    body: TaskDispatchRequest,
    _: str = Depends(require_admin),
):
    """Human-initiated task dispatch to any specific agent."""
    from backend.agents.orchestration.engine import engine
    agent = engine.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    task_id = await engine.dispatch_task_to_agent(
        agent_id    = agent_id,
        title       = body.title,
        description = body.description,
        input_data  = body.input_data,
        priority    = body.priority,
    )
    return {"task_id": task_id, "agent_id": agent_id, "status": "queued"}


@router.post("/objective")
async def inject_objective(
    body: ObjectiveRequest,
    _: str = Depends(require_admin),
):
    """CEO/Board injects a new strategic objective to the Meta-CEO."""
    from backend.agents.orchestration.engine import engine
    task_id = await engine.dispatch_task_to_agent(
        agent_id    = "meta_ceo",
        title       = body.title,
        description = body.description,
        input_data  = {"quarter": body.quarter, "kpis": body.kpis},
        priority    = 1,
    )
    return {
        "task_id": task_id,
        "message": f"Objective dispatched to Meta-CEO. Initiatives will cascade through {1336} agents.",
    }


@router.post("/emergency-stop")
async def emergency_stop(
    reason: str = "Human governance override",
    _: str = Depends(require_admin),
):
    """
    Emergency halt of all L4 autonomous agents.
    L0-L3 agents continue normal operation.
    Use when: unexpected behavior, ethical violation, data breach.
    """
    from backend.agents.orchestration.engine import engine
    await engine.emergency_stop(reason)
    return {
        "status": "emergency_stop_activated",
        "reason": reason,
        "l4_agents_stopped": True,
        "l0_l3_agents": "still_operational",
        "message": "All L4 autonomous agents halted. Human oversight required to resume.",
    }


@router.post("/resume")
async def resume_from_pause(_: str = Depends(require_admin)):
    """Resume normal operation after emergency stop or pause."""
    from backend.agents.orchestration.engine import engine
    engine._paused = False
    engine._emergency_stopped = False
    return {"status": "resumed", "message": "Agent system resumed normal operation"}


@router.get("/metrics")
async def get_metrics(_: str = Depends(require_admin)):
    """Event bus and task metrics."""
    from backend.agents.communication.event_bus import event_bus
    from backend.agents.communication.task_queue import task_registry
    return {
        "event_bus":    event_bus.get_metrics(),
        "task_registry": task_registry.get_dashboard(),
    }


@router.get("/memory/stats")
async def get_memory_stats(_: str = Depends(require_admin)):
    """Memory system statistics across all tiers."""
    from backend.agents.communication.memory import memory
    return memory.get_stats()


@router.get("/audit/entries")
async def get_audit_entries(
    start: int = 0,
    end:   int = 100,
    _: str = Depends(require_admin),
):
    """Read immutable audit log entries."""
    from backend.agents.communication.memory import memory
    entries = await memory._audit.read_range(start, end)
    verified = await memory._audit.verify_chain()
    return {
        "entries":         entries,
        "chain_verified":  verified,
        "total_entries":   memory._audit.size(),
    }


@router.get("/scheduled/jobs")
async def get_scheduled_jobs(_: str = Depends(require_admin)):
    """List all APScheduler jobs and next run times."""
    from backend.agents.orchestration.engine import engine
    jobs = []
    for job in engine.scheduler.get_jobs():
        jobs.append({
            "id":        job.id,
            "name":      job.name,
            "next_run":  str(job.next_run_time),
            "trigger":   str(job.trigger),
        })
    return {"scheduled_jobs": jobs, "count": len(jobs)}
