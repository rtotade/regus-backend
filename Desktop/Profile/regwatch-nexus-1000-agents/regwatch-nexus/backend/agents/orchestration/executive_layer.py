"""
RegWatch Nexus — Executive AI Layer
Level 1: Meta-CEO (Master Orchestrator)
Level 2: C-Suite (COO, CTO, CPO, CRO-Revenue, CRO-Risk)

These agents operate at L3–L4 autonomy.
They decompose strategic objectives into initiatives and assign to VP layer.
They subscribe to ALL events from their subordinate chains.
They escalate to human governance when:
  - Confidence < 0.60
  - Escalation count >= 3
  - Ethical boundary triggered
  - Financial exposure > defined threshold
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from backend.agents.base_agent import BaseAgent
from backend.agents.communication.protocols import (
    AgentEvent, AgentTier, AutonomyLevel, Department,
    EventType, MemoryScope, TaskObject, TaskStatus,
)
from backend.agents.communication.event_bus import event_bus
from backend.agents.communication.task_queue import task_registry

logger = logging.getLogger(__name__)


class MetaCEOAgent(BaseAgent):
    """
    Agent ID: meta_ceo
    The master orchestrator. Converts CEO/Board objectives into
    initiatives, allocates them across C-suite, monitors global health,
    and enforces the autonomy constitution.

    Subscribes to ALL events system-wide.
    Only agent that can directly address the human governance layer.
    """

    C_SUITE_IDS = ["ai_coo", "ai_cto", "ai_cpo", "ai_cro_revenue", "ai_cro_risk"]

    def __init__(self):
        super().__init__(
            agent_id       = "meta_ceo",
            name           = "AI Meta-CEO — Master Orchestrator",
            tier           = AgentTier.META_CEO,
            department     = Department.EXECUTIVE,
            reports_to     = None,   # reports to human CEO
            autonomy_level = AutonomyLevel.L4_FULLY_AUTONOMOUS_WITHIN_CONSTRAINTS,
            memory_scopes  = list(MemoryScope),
            model          = "claude-opus-4-6",  # highest capability model
        )
        self.supervises = self.C_SUITE_IDS
        # Subscribe to all events for global monitoring
        event_bus.subscribe_all(self._monitor_event)
        self._initiative_counter = 0
        self._human_escalations = []

    def describe(self) -> str:
        return "Converts CEO objectives into initiatives. Allocates work across C-suite. Monitors global health."

    async def execute_task(self, task: TaskObject) -> dict:
        system = """You are the AI Meta-CEO of RegWatch Nexus, a global regulatory intelligence platform.
Your role: Decompose strategic objectives into concrete initiatives.
Allocate initiatives across: COO (operations), CTO (technology), CPO (product), CRO-Revenue (growth), CRO-Risk (risk management).
For each initiative produce: title, description, owning C-suite agent, priority (1-10), success metrics, deadline.
Consider: regulatory coverage, platform stability, revenue growth, risk management, ethical compliance."""

        user = f"""OBJECTIVE: {task.title}
DETAIL: {task.description}
INPUT: {json.dumps(task.input_data, indent=2)}

Decompose into 8-15 specific initiatives. Assign each to the appropriate C-suite agent.
Return JSON with initiatives array."""

        raw, confidence = await self._call_llm(system, user, max_tokens=4096)

        # Parse and spawn initiatives as tasks to C-suite
        next_actions = []
        try:
            data = json.loads(raw) if raw.startswith('{') else {}
            initiatives = data.get("output", {}).get("initiatives", [])
            for init in initiatives[:15]:
                c_suite_id = init.get("owner", "ai_coo")
                if c_suite_id in self.C_SUITE_IDS:
                    next_actions.append({
                        "title":       init.get("title", "Initiative"),
                        "description": init.get("description", ""),
                        "agent_id":    c_suite_id,
                        "priority":    init.get("priority", 5),
                        "input":       {"metrics": init.get("metrics", [])},
                    })
                    self._initiative_counter += 1
        except Exception as e:
            logger.warning(f"[meta_ceo] Initiative parsing failed: {e}")

        await self.mem_write("last_objective", task.title, MemoryScope.EXECUTIVE_ONLY)
        await self.mem_write(
            f"initiative_count:{task.task_id}",
            len(next_actions),
            MemoryScope.ENTERPRISE_KG,
        )

        return {
            "output":       {"initiatives_created": len(next_actions), "raw_plan": raw[:500]},
            "confidence":   confidence,
            "reasoning":    f"Decomposed objective into {len(next_actions)} initiatives across C-suite",
            "next_actions": next_actions,
        }

    async def _monitor_event(self, event: AgentEvent):
        """React to critical events from anywhere in the hierarchy."""
        if event.event_type == EventType.HUMAN_REQUIRED:
            self._human_escalations.append(event)
            await self._notify_human_governance(event)

        elif event.event_type == EventType.ANOMALY_DETECTED:
            logger.critical(f"[meta_ceo] ANOMALY from {event.source_agent}: {event.payload}")
            # Trigger risk review
            task = TaskObject(
                title            = f"Investigate Anomaly: {event.payload.get('description', 'Unknown')}",
                description      = f"Anomaly detected by {event.source_agent}",
                assigned_agent_id= "ai_cro_risk",
                priority         = 1,
                department       = Department.RISK,
                input_data       = event.payload,
                confidence_threshold = 0.85,
            )
            await task_registry.submit_task(task)

        elif event.event_type == EventType.HEALTH_ALERT:
            logger.warning(f"[meta_ceo] HEALTH ALERT: {event.payload}")

    async def _notify_human_governance(self, event: AgentEvent):
        """Route to human oversight. In production: Slack/PagerDuty/email."""
        await self.mem_write(
            f"human_escalation:{event.event_id}",
            {"event": event.event_type.value, "source": event.source_agent,
             "payload": event.payload, "requires_human": True},
            MemoryScope.EXECUTIVE_ONLY,
        )
        logger.critical(f"[meta_ceo] HUMAN GOVERNANCE REQUIRED — {event.event_type.value}: {event.payload}")

    def get_dashboard(self) -> dict:
        return {
            "agent": self.agent_id,
            "initiatives_launched": self._initiative_counter,
            "human_escalations": len(self._human_escalations),
            "health": self.health_report(),
            "global_task_dashboard": task_registry.get_dashboard(),
        }


# ══════════════════════════════════════════════════════
# C-SUITE AGENTS (Level 2 of the AI hierarchy)
# ══════════════════════════════════════════════════════

class COOAgent(BaseAgent):
    """
    AI Chief Operating Officer
    Owns: Platform operations, agent infrastructure, data pipelines,
          quality control, SLA monitoring, incident response.
    Reports to: Meta-CEO
    Supervises: VP Operations, VP Quality, VP Infrastructure
    """
    VP_IDS = ["vp_ops", "vp_quality", "vp_infrastructure"]

    def __init__(self):
        super().__init__(
            agent_id       = "ai_coo",
            name           = "AI COO — Chief Operating Officer",
            tier           = AgentTier.C_SUITE,
            department     = Department.OPERATIONS,
            reports_to     = "meta_ceo",
            autonomy_level = AutonomyLevel.L3_AI_EXECUTES_HUMAN_AUDITS,
            model          = "claude-sonnet-4-20250514",
        )
        self.supervises = self.VP_IDS
        event_bus.subscribe(EventType.HEALTH_ALERT, self._handle_health_alert)
        event_bus.subscribe(EventType.TASK_FAILED, self._handle_task_failure)

    def describe(self) -> str:
        return "Owns platform operations, agent infra, data pipelines, SLA monitoring, incident response."

    async def execute_task(self, task: TaskObject) -> dict:
        system = """You are the AI COO of RegWatch Nexus.
Convert operational initiatives into concrete department plans.
Focus on: crawler uptime, agent health, data pipeline SLAs, alert latency, cost efficiency.
Break initiatives into tasks for: VP Operations, VP Quality, VP Infrastructure."""

        user = f"INITIATIVE: {task.title}\nDETAIL: {task.description}\nINPUT: {json.dumps(task.input_data)}"
        raw, confidence = await self._call_llm(system, user, max_tokens=2048)

        next_actions = []
        for vp_id in self.VP_IDS:
            next_actions.append({
                "title":       f"[OPS] {task.title} — {vp_id.replace('_',' ').upper()} workstream",
                "description": task.description,
                "agent_id":    vp_id,
                "priority":    task.priority,
                "input":       task.input_data,
            })

        return {"output": {"plan": raw[:300]}, "confidence": confidence,
                "reasoning": "Distributed to VP layer", "next_actions": next_actions}

    async def _handle_health_alert(self, event: AgentEvent):
        logger.warning(f"[ai_coo] Health alert: {event.payload}")

    async def _handle_task_failure(self, event: AgentEvent):
        if event.payload.get("department") == Department.OPERATIONS.value:
            logger.error(f"[ai_coo] Ops task failed: {event.payload}")


class CTOAgent(BaseAgent):
    """
    AI Chief Technology Officer
    Owns: Backend engineering, AI model selection, API reliability,
          security posture, database performance, mobile platform.
    Supervises: VP Engineering, VP Security, VP Data Engineering
    """
    VP_IDS = ["vp_engineering", "vp_security", "vp_data_engineering"]

    def __init__(self):
        super().__init__(
            agent_id       = "ai_cto",
            name           = "AI CTO — Chief Technology Officer",
            tier           = AgentTier.C_SUITE,
            department     = Department.TECHNOLOGY,
            reports_to     = "meta_ceo",
            autonomy_level = AutonomyLevel.L3_AI_EXECUTES_HUMAN_AUDITS,
            model          = "claude-sonnet-4-20250514",
        )
        self.supervises = self.VP_IDS

    def describe(self) -> str:
        return "Owns backend engineering, AI stack, API reliability, security, database performance."

    async def execute_task(self, task: TaskObject) -> dict:
        system = """You are the AI CTO of RegWatch Nexus.
Convert technology initiatives into engineering plans.
Focus on: system reliability, AI agent performance, API latency, database indexes,
security patches, mobile app stability, cloud cost optimisation."""

        user = f"INITIATIVE: {task.title}\nDETAIL: {task.description}"
        raw, confidence = await self._call_llm(system, user, max_tokens=2048)

        next_actions = [{"title": f"[TECH] {task.title}", "description": task.description,
                         "agent_id": vp_id, "priority": task.priority, "input": task.input_data}
                        for vp_id in self.VP_IDS]

        return {"output": {"tech_plan": raw[:300]}, "confidence": confidence,
                "reasoning": "Tech initiative decomposed to VP layer", "next_actions": next_actions}


class CPOAgent(BaseAgent):
    """
    AI Chief Product Officer
    Owns: Feature roadmap, UX quality, alert relevance scoring,
          intelligence feed curation, subscription experience.
    Supervises: VP Product, VP UX, VP Content Strategy
    """
    VP_IDS = ["vp_product", "vp_ux", "vp_content"]

    def __init__(self):
        super().__init__(
            agent_id       = "ai_cpo",
            name           = "AI CPO — Chief Product Officer",
            tier           = AgentTier.C_SUITE,
            department     = Department.PRODUCT,
            reports_to     = "meta_ceo",
            autonomy_level = AutonomyLevel.L3_AI_EXECUTES_HUMAN_AUDITS,
            model          = "claude-sonnet-4-20250514",
        )
        self.supervises = self.VP_IDS

    def describe(self) -> str:
        return "Owns feature roadmap, alert relevance, UX quality, intelligence curation, subscription experience."

    async def execute_task(self, task: TaskObject) -> dict:
        system = """You are the AI CPO of RegWatch Nexus.
Convert product initiatives into feature and content plans.
Focus on: user engagement, alert quality, subscription conversion, mobile experience,
intelligence depth, regulator coverage gaps."""

        user = f"INITIATIVE: {task.title}\nDETAIL: {task.description}"
        raw, confidence = await self._call_llm(system, user, max_tokens=2048)

        next_actions = [{"title": f"[PROD] {task.title}", "description": task.description,
                         "agent_id": vp_id, "priority": task.priority, "input": task.input_data}
                        for vp_id in self.VP_IDS]

        return {"output": {"product_plan": raw[:300]}, "confidence": confidence,
                "reasoning": "Product initiative distributed to VP layer", "next_actions": next_actions}


class CRORevenueAgent(BaseAgent):
    """
    AI Chief Revenue Officer
    Owns: Subscription growth, enterprise sales, API monetisation,
          pricing strategy, churn reduction, partner ecosystem.
    Supervises: VP Growth, VP Enterprise Sales, VP Partnerships
    """
    VP_IDS = ["vp_growth", "vp_enterprise_sales", "vp_partnerships"]

    def __init__(self):
        super().__init__(
            agent_id       = "ai_cro_revenue",
            name           = "AI CRO — Chief Revenue Officer",
            tier           = AgentTier.C_SUITE,
            department     = Department.REVENUE,
            reports_to     = "meta_ceo",
            autonomy_level = AutonomyLevel.L3_AI_EXECUTES_HUMAN_AUDITS,
            model          = "claude-sonnet-4-20250514",
        )
        self.supervises = self.VP_IDS

    def describe(self) -> str:
        return "Owns subscription growth, enterprise sales, API monetisation, pricing strategy, partnerships."

    async def execute_task(self, task: TaskObject) -> dict:
        system = """You are the AI CRO of RegWatch Nexus.
Convert revenue initiatives into sales and growth execution plans.
Focus on: Pro subscription conversion, enterprise pipeline, API revenue, churn signals, pricing optimisation."""

        user = f"INITIATIVE: {task.title}\nDETAIL: {task.description}"
        raw, confidence = await self._call_llm(system, user, max_tokens=2048)

        next_actions = [{"title": f"[REV] {task.title}", "description": task.description,
                         "agent_id": vp_id, "priority": task.priority, "input": task.input_data}
                        for vp_id in self.VP_IDS]

        return {"output": {"revenue_plan": raw[:300]}, "confidence": confidence,
                "reasoning": "Revenue initiative distributed", "next_actions": next_actions}


class CROComplianceRiskAgent(BaseAgent):
    """
    AI Chief Risk Officer
    Owns: Regulatory compliance of the platform itself, data privacy,
          content accuracy governance, ethical AI oversight, security risk.
    Supervises: VP Ethics, VP Legal Risk, VP Data Privacy
    """
    VP_IDS = ["vp_ethics", "vp_legal_risk", "vp_data_privacy"]

    def __init__(self):
        super().__init__(
            agent_id       = "ai_cro_risk",
            name           = "AI CRO — Chief Risk Officer",
            tier           = AgentTier.C_SUITE,
            department     = Department.RISK,
            reports_to     = "meta_ceo",
            autonomy_level = AutonomyLevel.L2_AI_EXECUTES_HUMAN_REVIEWS,  # risk is more conservative
            model          = "claude-sonnet-4-20250514",
        )
        self.supervises = self.VP_IDS
        event_bus.subscribe(EventType.CONFLICT_DETECTED, self._handle_conflict)
        event_bus.subscribe(EventType.ESCALATION_REQUIRED, self._handle_escalation)

    def describe(self) -> str:
        return "Owns platform compliance, data privacy, content accuracy governance, ethical AI oversight."

    async def execute_task(self, task: TaskObject) -> dict:
        system = """You are the AI Chief Risk Officer of RegWatch Nexus.
Evaluate risk initiatives and produce risk management plans.
Focus on: data privacy compliance, AI accuracy standards, content liability, security posture,
escalation thresholds, human oversight requirements."""

        user = f"INITIATIVE: {task.title}\nDETAIL: {task.description}"
        raw, confidence = await self._call_llm(system, user, max_tokens=2048)

        next_actions = [{"title": f"[RISK] {task.title}", "description": task.description,
                         "agent_id": vp_id, "priority": task.priority, "input": task.input_data}
                        for vp_id in self.VP_IDS]

        return {"output": {"risk_assessment": raw[:300]}, "confidence": confidence,
                "reasoning": "Risk initiative assessed and distributed", "next_actions": next_actions}

    async def _handle_conflict(self, event: AgentEvent):
        logger.warning(f"[ai_cro_risk] Conflict detected: {event.payload}")
        # Spawn arbitration task
        task = TaskObject(
            title            = "Arbitrate Agent Conflict",
            description      = f"Conflict between agents: {event.payload}",
            assigned_agent_id= "dir_risk_arbitration",
            priority         = 2,
            department       = Department.RISK,
            input_data       = event.payload,
            confidence_threshold = 0.80,
        )
        await task_registry.submit_task(task)

    async def _handle_escalation(self, event: AgentEvent):
        escalation_count = event.payload.get("escalation_count", 0)
        if escalation_count >= 3:
            await self._emit(EventType.HUMAN_REQUIRED, event.related_task, {
                "reason": "3+ escalations — human governance required",
                "original_escalation": event.payload,
            })
