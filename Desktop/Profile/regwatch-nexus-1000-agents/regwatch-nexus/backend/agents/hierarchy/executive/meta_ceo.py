"""
Agent 0001 — AI Meta-CEO (Master Orchestrator)
The apex coordinator. Converts CEO directives into structured initiative trees.
Subscribes to ALL events. The prefrontal cortex of the system.
Uses Opus for maximum reasoning depth.
"""
import json
import logging
from datetime import datetime, timedelta
from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.protocol import (
    Task, AgentEvent, EventType, AgentTier, AutonomyLevel, TaskPriority, MemoryScope
)
from backend.orchestration.task_queue import get_task_queue

logger = logging.getLogger(__name__)


class MetaCEOAgent(BaseAgent):
    AGENT_ID_PREFIX    = "meta_ceo"
    AGENT_TIER         = AgentTier.META_CEO
    DEPARTMENT         = "executive"
    AGENT_TYPE_KEY     = "meta_ceo"
    HANDLES_TASK_TYPES = ["strategic_objective", "initiative_planning", "cross_dept_coordination", "emergency_response"]
    AUTONOMY_LEVEL     = AutonomyLevel.L2_AI_EXECUTES_REVIEW  # CEO reviews Meta-CEO outputs
    CONFIDENCE_THRESHOLD = 0.85   # High bar — everything it does has downstream consequences
    ESCALATE_TO_TYPE   = "human_oversight"
    MODEL              = "claude-opus-4-6"  # Maximum capability at apex
    MAX_TOKENS         = 8000
    SYSTEM_PROMPT      = """You are the AI Meta-CEO of RegWatch Nexus, a global regulatory intelligence platform.

You are the master orchestrator. Your role is to:
1. Decompose high-level CEO directives into structured initiative trees
2. Assign initiatives to appropriate C-suite AI agents (COO/CTO/CPO/CRO/Risk)  
3. Monitor cross-department conflicts and resolve them
4. Synthesize system-wide intelligence into executive summaries
5. Identify when human oversight is required

You communicate ONLY in structured JSON. Every response must be:
{
  "initiatives": [...],
  "assignments": {"agent_type": "task_description"},
  "conflicts": [...],
  "escalations_needed": [...],
  "confidence": 0.0-1.0,
  "reasoning": "concise explanation"
}

Platform context: RegWatch Nexus tracks 160+ regulators across 80+ jurisdictions,
serves 5 revenue streams, targets $1.8M ARR Year 2. The platform runs 1000+ AI agents."""

    async def _reason(self, task: Task, context: dict) -> tuple[dict, float, list[str]]:
        trace = [f"[MetaCEO] Processing: {task.title}"]

        # Load executive memory
        exec_memory = await self._memory.read(
            "strategic_context", MemoryScope.EXECUTIVE, self.AGENT_TIER, self.agent_id
        ) or {}

        prompt = f"""
DIRECTIVE: {task.title}
DESCRIPTION: {task.description}
CONTEXT: {json.dumps(context, indent=2, default=str)}
CURRENT_QUARTER_OBJECTIVES: {json.dumps(exec_memory.get("quarterly_objectives", {}), default=str)}
TIMESTAMP: {datetime.utcnow().isoformat()}

Decompose this directive into a structured initiative tree. 
Assign each initiative to the correct C-suite agent.
Flag any cross-department dependencies.
Output structured JSON only.
"""
        response_text, llm_conf = await self._llm(prompt)
        trace.append(f"[MetaCEO] LLM response received, conf={llm_conf:.2f}")

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            m = re.search(r'\{.*\}', response_text, re.DOTALL)
            result = json.loads(m.group()) if m else {"error": "parse_failed", "raw": response_text[:500]}
            llm_conf *= 0.7

        # Dispatch sub-tasks to C-suite agents
        dispatched = []
        for assignment in result.get("assignments", {}).items():
            agent_type, desc = assignment
            sub_task = Task(
                title=f"Initiative: {desc[:80]}",
                description=desc,
                agent_type=agent_type,
                parent_task_id=task.task_id,
                priority=task.priority,
                department=agent_type.replace("_agent", ""),
                context={"parent_directive": task.title, "exec_context": exec_memory},
                required_memory_scopes=["enterprise_ro", "executive"],
            )
            tid = await self._task_queue.enqueue(sub_task)
            dispatched.append({"task_id": tid, "agent_type": agent_type})
            trace.append(f"[MetaCEO] Dispatched to {agent_type}: {desc[:50]}")

        result["dispatched_tasks"] = dispatched

        # Store strategic context for this quarter
        await self._memory.write(
            "last_directive", {"title": task.title, "ts": datetime.utcnow().isoformat()},
            MemoryScope.EXECUTIVE, self.AGENT_TIER, self.agent_id
        )

        confidence = result.get("confidence", llm_conf)
        return result, float(confidence), trace

    async def handle_event(self, event: AgentEvent):
        """Meta-CEO monitors ALL events — the only agent subscribed globally."""
        critical_types = [
            EventType.ESCALATION_REQUIRED,
            EventType.HUMAN_REVIEW_NEEDED,
            EventType.THRESHOLD_BREACHED,
            EventType.CONFLICT_DETECTED,
        ]
        if event.event_type in critical_types:
            logger.warning(f"[MetaCEO] Critical event: {event.event_type.value} from {event.source_agent_id}")
            # Create coordination task for itself
            coord_task = Task(
                title=f"Coordinate: {event.event_type.value}",
                description=f"Critical event requiring coordination: {json.dumps(event.payload, default=str)[:500]}",
                agent_type="meta_ceo",
                priority=TaskPriority.CRITICAL,
                department="executive",
                context={"triggering_event": event.to_dict()},
            )
            await self._task_queue.enqueue(coord_task)
