"""
C-Suite AI Agents: COO, CTO, CPO, CRO (Revenue), CRO (Risk)
5 agents at the apex of each functional domain.
Each orchestrates their VP layer.
Uses Sonnet (strong reasoning, not burning Opus budget).
"""
import json
import logging
from datetime import datetime
from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.protocol import (
    Task, AgentTier, AutonomyLevel, TaskPriority, MemoryScope
)
from backend.orchestration.task_queue import get_task_queue

logger = logging.getLogger(__name__)


# ── SHARED BASE FOR ALL C-SUITE ───────────────────────────────────

class CSuiteAgent(BaseAgent):
    AGENT_TIER           = AgentTier.C_SUITE
    AUTONOMY_LEVEL       = AutonomyLevel.L3_AI_EXECUTES_AUDIT
    CONFIDENCE_THRESHOLD = 0.80
    ESCALATE_TO_TYPE     = "meta_ceo"
    MODEL                = "claude-sonnet-4-6"
    MAX_TOKENS           = 4000
    VP_AGENTS: list[str] = []  # Override: list of VP agent types to dispatch to

    async def _reason(self, task: Task, context: dict) -> tuple[dict, float, list[str]]:
        trace = [f"[{self.agent_id}] Domain planning: {task.title}"]
        prompt = f"""
TASK: {task.title}
DESCRIPTION: {task.description}
CONTEXT: {json.dumps(context, default=str)[:3000]}
YOUR_DOMAIN: {self.DEPARTMENT}
VP_AGENTS_AVAILABLE: {self.VP_AGENTS}

Break this into VP-level workstreams. Assign each workstream to the correct VP agent.
Return structured JSON:
{{
  "domain_strategy": "...",
  "workstreams": [{{"vp_agent": "...", "title": "...", "objective": "...", "priority": "high|medium|low"}}],
  "dependencies": [...],
  "kpis": [...],
  "risks": [...],
  "confidence": 0.0-1.0
}}
"""
        resp, conf = await self._llm(prompt)
        trace.append(f"[{self.agent_id}] LLM plan generated, conf={conf:.2f}")

        try:
            result = json.loads(resp)
        except Exception:
            result = {"raw": resp[:1000], "parse_error": True}
            conf *= 0.75

        # Dispatch to VP agents
        for ws in result.get("workstreams", []):
            vp_type = ws.get("vp_agent", "")
            if vp_type in self.VP_AGENTS:
                sub = Task(
                    title=ws.get("title", "VP Task")[:100],
                    description=ws.get("objective", "")[:500],
                    agent_type=vp_type,
                    parent_task_id=task.task_id,
                    priority={"high": TaskPriority.HIGH, "medium": TaskPriority.MEDIUM,
                              "low": TaskPriority.LOW}.get(ws.get("priority", "medium"), TaskPriority.MEDIUM),
                    department=self.DEPARTMENT,
                    context={"c_suite_directive": task.title},
                    required_memory_scopes=["enterprise_ro"],
                )
                await get_task_queue().enqueue(sub)
                trace.append(f"[{self.agent_id}] → dispatched to {vp_type}")

        return result, result.get("confidence", conf), trace


# ── 5 C-SUITE SPECIALIZATIONS ────────────────────────────────────

class AICOOAgent(CSuiteAgent):
    AGENT_ID_PREFIX  = "coo"
    AGENT_TYPE_KEY   = "coo_agent"
    DEPARTMENT       = "operations"
    VP_AGENTS        = ["vp_ops", "vp_data_ops", "vp_infrastructure", "vp_quality", "vp_support"]
    SYSTEM_PROMPT    = """You are the AI Chief Operating Officer of RegWatch Nexus.
Domain: Operational excellence — agent pipeline health, data flow reliability, infrastructure uptime,
quality control, support operations.
Respond only in structured JSON with domain strategy, VP workstreams, and KPIs."""

class AICTOAgent(CSuiteAgent):
    AGENT_ID_PREFIX  = "cto"
    AGENT_TYPE_KEY   = "cto_agent"
    DEPARTMENT       = "technology"
    VP_AGENTS        = ["vp_engineering", "vp_ai_ml", "vp_security", "vp_platform", "vp_mobile"]
    SYSTEM_PROMPT    = """You are the AI Chief Technology Officer of RegWatch Nexus.
Domain: Technology strategy — backend engineering, AI/ML pipeline, security, platform reliability, mobile.
Respond only in structured JSON with technical workstreams and architecture decisions."""

class AICPOAgent(CSuiteAgent):
    AGENT_ID_PREFIX  = "cpo"
    AGENT_TYPE_KEY   = "cpo_agent"
    DEPARTMENT       = "product"
    VP_AGENTS        = ["vp_product", "vp_content", "vp_ux", "vp_growth_product", "vp_partnerships"]
    SYSTEM_PROMPT    = """You are the AI Chief Product Officer of RegWatch Nexus.
Domain: Product strategy — alert quality, intelligence depth, UX, feature roadmap, content partnerships.
Respond only in structured JSON with product workstreams and user impact metrics."""

class AICRORevenueAgent(CSuiteAgent):
    AGENT_ID_PREFIX  = "cro_revenue"
    AGENT_TYPE_KEY   = "cro_revenue_agent"
    DEPARTMENT       = "revenue"
    VP_AGENTS        = ["vp_growth", "vp_sales", "vp_marketing", "vp_customer_success", "vp_pricing"]
    SYSTEM_PROMPT    = """You are the AI Chief Revenue Officer of RegWatch Nexus.
Domain: Revenue generation — subscription growth, enterprise sales, marketing campaigns, retention.
Target: $1.8M ARR Year 2 across 5 revenue streams.
Respond only in structured JSON with revenue workstreams and ARR impact estimates."""

class AICRORiskAgent(CSuiteAgent):
    AGENT_ID_PREFIX  = "cro_risk"
    AGENT_TYPE_KEY   = "cro_risk_agent"
    DEPARTMENT       = "risk"
    VP_AGENTS        = ["vp_compliance", "vp_ethics", "vp_legal", "vp_audit", "vp_trust_safety"]
    CONFIDENCE_THRESHOLD = 0.90  # Risk decisions need higher confidence
    SYSTEM_PROMPT    = """You are the AI Chief Risk Officer of RegWatch Nexus.
Domain: Enterprise risk — regulatory compliance, AI ethics, legal review, audit, trust & safety.
You have veto power over any action that creates material legal or reputational risk.
Respond only in structured JSON with risk assessments and go/no-go decisions."""
