"""
RegWatch Nexus — Conflict Resolution System
When two agents produce disagreeing outputs, this system:
  1. Compares confidence scores
  2. Runs third-model arbitration
  3. Escalates to Risk Officer Agent
  4. Escalates to human if threshold breached

Used by: Any agent pair, automated after CONFLICT_DETECTED event.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from backend.agents.base_agent import BaseAgent
from backend.agents.communication.protocols import (
    AgentEvent, AgentTier, AutonomyLevel, ConflictResolution,
    Department, EventType, MemoryScope, TaskObject,
)
from backend.agents.communication.event_bus import event_bus
from backend.agents.communication.task_queue import task_registry

logger = logging.getLogger(__name__)


class ArbitrationAgent(BaseAgent):
    """
    Dedicated arbitration agent — resolves conflicts between any two agents.
    Uses a separate LLM call to evaluate both outputs independently.
    Does NOT have access to which agent produced which output until after decision.
    (Blind arbitration prevents bias toward senior agents.)
    """

    def __init__(self):
        super().__init__(
            agent_id       = "arbitration_engine",
            name           = "Conflict Arbitration Engine",
            tier           = AgentTier.DIRECTOR,
            department     = Department.RISK,
            reports_to     = "dir_risk_arbitration",
            autonomy_level = AutonomyLevel.L2_AI_EXECUTES_HUMAN_REVIEWS,
            model          = "claude-sonnet-4-20250514",  # higher capability for arbitration
        )
        # Subscribe to all conflict events
        event_bus.subscribe(EventType.CONFLICT_DETECTED, self._on_conflict)

    def describe(self) -> str:
        return "Blind arbitration: resolves output conflicts between any two agents without tier bias."

    async def execute_task(self, task: TaskObject) -> dict:
        """Arbitrate between two conflicting agent outputs."""
        output_a = task.input_data.get("output_a", {})
        output_b = task.input_data.get("output_b", {})
        confidence_a = task.input_data.get("confidence_a", 0.5)
        confidence_b = task.input_data.get("confidence_b", 0.5)
        context = task.input_data.get("context", "")

        system = """You are a neutral arbitration system for a regulatory intelligence platform.
Two independent AI agents have produced different outputs for the same task.
Your job: Determine which output is more accurate, complete, and reliable.
Rules:
- Evaluate outputs purely on their content quality, not on which agent produced them
- Consider: factual accuracy, completeness, regulatory precision, logical consistency
- You may synthesize the best elements of both outputs
- Provide a clear confidence score for your arbitration decision
- If both outputs are equally uncertain, recommend human review
Return structured JSON with your arbitration decision."""

        user = f"""TASK CONTEXT: {context}

OUTPUT A (confidence {confidence_a:.2f}):
{json.dumps(output_a, indent=2, default=str)[:1000]}

OUTPUT B (confidence {confidence_b:.2f}):
{json.dumps(output_b, indent=2, default=str)[:1000]}

Arbitrate. Which output is more reliable? Can they be synthesized?
Return: winner ("A"|"B"|"synthesis"), resolution_output, confidence, reasoning."""

        raw, confidence = await self._call_llm(system, user, max_tokens=2048)

        try:
            data = json.loads(raw) if raw.strip().startswith('{') else {}
            resolution = data.get("output", {})
        except Exception:
            resolution = {"raw": raw[:500]}

        # If arbitration confidence is still low → escalate to human
        human_required = confidence < 0.65

        # Log to audit
        await memory.audit_append(self.agent_id, "ARBITRATION_COMPLETED", {
            "context": context[:200],
            "confidence_a": confidence_a,
            "confidence_b": confidence_b,
            "arbitration_confidence": confidence,
            "human_required": human_required,
        })

        if human_required:
            await self._emit(EventType.HUMAN_REQUIRED, task.task_id, {
                "reason": f"Arbitration confidence {confidence:.2f} below 0.65 — human decision required",
                "conflict_context": context[:200],
                "resolution_draft": resolution,
            })

        return {
            "output":     {"resolution": resolution, "human_required": human_required},
            "confidence": confidence,
            "reasoning":  f"Arbitrated with {confidence:.2f} confidence. Human required: {human_required}",
        }

    async def _on_conflict(self, event: AgentEvent):
        """Auto-respond to conflict events by spawning an arbitration task."""
        task = TaskObject(
            title            = f"Arbitrate Conflict: {event.payload.get('context', event.event_id)[:50]}",
            description      = "Blind arbitration between two conflicting agent outputs",
            assigned_agent_id= self.agent_id,
            priority         = 2,
            department       = Department.RISK,
            input_data       = event.payload,
            confidence_threshold = 0.65,
        )
        await task_registry.submit_task(task)

    async def arbitrate_directly(
        self, agent_a_id: str, output_a: dict, confidence_a: float,
        agent_b_id: str, output_b: dict, confidence_b: float,
        context: str,
    ) -> ConflictResolution:
        """Direct API call for arbitration without task queue."""
        task = TaskObject(
            title            = f"Direct Arbitration — {context[:40]}",
            description      = "Synchronous arbitration request",
            assigned_agent_id= self.agent_id,
            priority         = 1,
            department       = Department.RISK,
            input_data       = {
                "output_a": output_a, "confidence_a": confidence_a,
                "output_b": output_b, "confidence_b": confidence_b,
                "context":  context,
            },
            confidence_threshold = 0.65,
        )
        result = await self.execute_task(task)
        return ConflictResolution(
            agent_a           = agent_a_id,
            agent_b           = agent_b_id,
            output_a          = output_a,
            output_b          = output_b,
            confidence_a      = confidence_a,
            confidence_b      = confidence_b,
            arbitrator_agent  = self.agent_id,
            resolution        = result.get("output", {}).get("resolution", {}),
            resolution_confidence = result.get("confidence", 0.0),
            human_escalated   = result.get("output", {}).get("human_required", False),
        )


class ConflictDetector:
    """
    Utility class. Call detect() when two agents complete related tasks.
    Emits CONFLICT_DETECTED event if their outputs diverge significantly.
    """

    DIVERGENCE_THRESHOLD = 0.25  # confidence delta > this → conflict

    @staticmethod
    async def detect(
        agent_a_id: str, output_a: dict, confidence_a: float,
        agent_b_id: str, output_b: dict, confidence_b: float,
        context: str,
    ) -> bool:
        """
        Returns True if conflict detected.
        Emits CONFLICT_DETECTED event automatically.
        """
        # Structural divergence check
        keys_a = set(output_a.keys())
        keys_b = set(output_b.keys())
        key_overlap = len(keys_a & keys_b) / max(len(keys_a | keys_b), 1)

        confidence_delta = abs(confidence_a - confidence_b)

        # Simple string similarity on JSON outputs
        str_a = json.dumps(output_a, sort_keys=True, default=str)
        str_b = json.dumps(output_b, sort_keys=True, default=str)
        common_chars = sum(1 for a, b in zip(str_a[:500], str_b[:500]) if a == b)
        str_similarity = common_chars / max(len(str_a[:500]), len(str_b[:500]), 1)

        is_conflict = (
            confidence_delta > ConflictDetector.DIVERGENCE_THRESHOLD or
            key_overlap < 0.5 or
            str_similarity < 0.3
        )

        if is_conflict:
            evt = AgentEvent(
                event_type     = EventType.CONFLICT_DETECTED,
                source_agent   = agent_a_id,
                confidence_score = min(confidence_a, confidence_b),
                payload        = {
                    "context":      context,
                    "agent_a":      agent_a_id,
                    "agent_b":      agent_b_id,
                    "output_a":     output_a,
                    "output_b":     output_b,
                    "confidence_a": confidence_a,
                    "confidence_b": confidence_b,
                    "confidence_delta": confidence_delta,
                    "str_similarity": str_similarity,
                },
            )
            await event_bus.publish(evt)
            logger.warning(
                f"[ConflictDetector] CONFLICT: {agent_a_id} vs {agent_b_id} "
                f"(Δconf={confidence_delta:.2f}, sim={str_similarity:.2f})"
            )

        return is_conflict


class EscalationRouter:
    """
    Determines where to route an escalation based on:
    - Source agent tier
    - Escalation count
    - Task department
    - Confidence level
    """

    ESCALATION_CHAIN = {
        AgentTier.INTERN:    AgentTier.JUNIOR,
        AgentTier.JUNIOR:    AgentTier.SENIOR,
        AgentTier.SENIOR:    AgentTier.DIRECTOR,
        AgentTier.DIRECTOR:  AgentTier.VP,
        AgentTier.VP:        AgentTier.C_SUITE,
        AgentTier.C_SUITE:   AgentTier.META_CEO,
        AgentTier.META_CEO:  None,  # → human
    }

    DEPT_RISK_ESCALATION = {
        Department.RISK:       "ai_cro_risk",
        Department.OPERATIONS: "ai_coo",
        Department.TECHNOLOGY: "ai_cto",
        Department.PRODUCT:    "ai_cpo",
        Department.REVENUE:    "ai_cro_revenue",
        Department.EXECUTIVE:  "meta_ceo",
        Department.AUDIT:      "sr_audit_chain",
    }

    @staticmethod
    def get_escalation_target(source_tier: AgentTier, department: Department,
                              escalation_count: int, reports_to: Optional[str]) -> tuple[str, bool]:
        """
        Returns (target_agent_id, requires_human).
        """
        requires_human = escalation_count >= 3

        if requires_human:
            return "meta_ceo", True

        # Use direct supervisor if available
        if reports_to:
            return reports_to, False

        # Fall back to department C-suite
        fallback = EscalationRouter.DEPT_RISK_ESCALATION.get(department, "meta_ceo")
        return fallback, False


# Global arbitration instance
arbitration_agent = ArbitrationAgent()
conflict_detector = ConflictDetector()
escalation_router = EscalationRouter()
