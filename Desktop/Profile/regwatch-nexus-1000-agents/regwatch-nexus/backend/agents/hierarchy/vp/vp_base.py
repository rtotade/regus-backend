"""
VP Agent Base — 25 VP agents across 5 departments.
VPs receive workstreams from C-suite and decompose into Director tasks.
"""
import json
import logging
from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.protocol import (
    Task, AgentTier, AutonomyLevel, TaskPriority, MemoryScope
)
from backend.orchestration.task_queue import get_task_queue

logger = logging.getLogger(__name__)


class VPAgent(BaseAgent):
    AGENT_TIER           = AgentTier.VP
    AUTONOMY_LEVEL       = AutonomyLevel.L3_AI_EXECUTES_AUDIT
    CONFIDENCE_THRESHOLD = 0.75
    MODEL                = "claude-sonnet-4-6"
    MAX_TOKENS           = 3000
    DIRECTOR_AGENTS: list[str] = []  # Override per VP

    async def _reason(self, task: Task, context: dict) -> tuple[dict, float, list[str]]:
        trace = [f"[{self.agent_id}] Planning workstream: {task.title}"]

        prompt = f"""
WORKSTREAM: {task.title}
OBJECTIVE: {task.description}
CONTEXT: {json.dumps(context, default=str)[:2000]}
DEPARTMENT: {self.DEPARTMENT}
DIRECTOR_AGENTS_AVAILABLE: {self.DIRECTOR_AGENTS}

Break this workstream into director-level task groups (3-8 tasks per director).
Return structured JSON:
{{
  "plan": "...",
  "director_tasks": [{{"director_agent": "...", "title": "...", "deliverables": [...], "priority": "..."}}],
  "timeline_days": 0,
  "success_metrics": [...],
  "blockers": [...],
  "confidence": 0.0-1.0
}}
"""
        resp, conf = await self._llm(prompt)
        try:
            result = json.loads(resp)
        except Exception:
            result = {"raw": resp[:800], "parse_error": True}
            conf *= 0.7

        for dt in result.get("director_tasks", []):
            dir_type = dt.get("director_agent", "")
            if dir_type in self.DIRECTOR_AGENTS:
                sub = Task(
                    title=dt.get("title", "Director Task"),
                    description=str(dt.get("deliverables", [])),
                    agent_type=dir_type,
                    parent_task_id=task.task_id,
                    priority={"high": TaskPriority.HIGH, "medium": TaskPriority.MEDIUM,
                              "low": TaskPriority.LOW, "critical": TaskPriority.CRITICAL}.get(
                                  dt.get("priority", "medium"), TaskPriority.MEDIUM),
                    department=self.DEPARTMENT,
                    context={"vp_plan": task.title},
                )
                await get_task_queue().enqueue(sub)
                trace.append(f"[{self.agent_id}] → {dir_type}: {dt.get('title', '')[:50]}")

        return result, result.get("confidence", conf), trace


# ── OPERATIONS VPs (5) ────────────────────────────────────────────

class VPOpsAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_ops"
    AGENT_TYPE_KEY  = "vp_ops"
    DEPARTMENT      = "operations"
    DIRECTOR_AGENTS = ["dir_pipeline", "dir_monitoring", "dir_incident", "dir_capacity"]
    SYSTEM_PROMPT   = "You are the VP Operations of RegWatch Nexus. Plan operational workstreams for directors. Respond in JSON only."

class VPDataOpsAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_data_ops"
    AGENT_TYPE_KEY  = "vp_data_ops"
    DEPARTMENT      = "operations"
    DIRECTOR_AGENTS = ["dir_data_pipeline", "dir_data_quality", "dir_data_storage", "dir_etl"]
    SYSTEM_PROMPT   = "You are the VP Data Operations. Plan data pipeline workstreams. Respond in JSON only."

class VPInfrastructureAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_infrastructure"
    AGENT_TYPE_KEY  = "vp_infrastructure"
    DEPARTMENT      = "operations"
    DIRECTOR_AGENTS = ["dir_cloud", "dir_database", "dir_networking", "dir_devops"]
    SYSTEM_PROMPT   = "You are VP Infrastructure. Plan cloud/infra workstreams. Respond in JSON only."

class VPQualityAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_quality"
    AGENT_TYPE_KEY  = "vp_quality"
    DEPARTMENT      = "operations"
    DIRECTOR_AGENTS = ["dir_qa", "dir_validation", "dir_testing", "dir_benchmarking"]
    SYSTEM_PROMPT   = "You are VP Quality. Plan QA/validation workstreams. Respond in JSON only."

class VPSupportAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_support"
    AGENT_TYPE_KEY  = "vp_support"
    DEPARTMENT      = "operations"
    DIRECTOR_AGENTS = ["dir_customer_support", "dir_docs", "dir_onboarding"]
    SYSTEM_PROMPT   = "You are VP Support. Plan customer support workstreams. Respond in JSON only."

# ── TECHNOLOGY VPs (5) ────────────────────────────────────────────

class VPEngineeringAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_engineering"
    AGENT_TYPE_KEY  = "vp_engineering"
    DEPARTMENT      = "technology"
    DIRECTOR_AGENTS = ["dir_backend", "dir_frontend", "dir_api", "dir_integrations"]
    SYSTEM_PROMPT   = "You are VP Engineering. Plan backend/frontend workstreams. Respond in JSON only."

class VPAIMLAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_ai_ml"
    AGENT_TYPE_KEY  = "vp_ai_ml"
    DEPARTMENT      = "technology"
    DIRECTOR_AGENTS = ["dir_agent_design", "dir_model_ops", "dir_prompt_eng", "dir_evals"]
    SYSTEM_PROMPT   = "You are VP AI/ML. Plan AI agent and ML workstreams. Respond in JSON only."

class VPSecurityAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_security"
    AGENT_TYPE_KEY  = "vp_security"
    DEPARTMENT      = "technology"
    CONFIDENCE_THRESHOLD = 0.85
    DIRECTOR_AGENTS = ["dir_appsec", "dir_infosec", "dir_auth", "dir_pen_testing"]
    SYSTEM_PROMPT   = "You are VP Security. Plan security workstreams with high standards. Respond in JSON only."

class VPPlatformAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_platform"
    AGENT_TYPE_KEY  = "vp_platform"
    DEPARTMENT      = "technology"
    DIRECTOR_AGENTS = ["dir_platform_arch", "dir_search", "dir_notifications", "dir_analytics"]
    SYSTEM_PROMPT   = "You are VP Platform. Plan platform scalability workstreams. Respond in JSON only."

class VPMobileAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_mobile"
    AGENT_TYPE_KEY  = "vp_mobile"
    DEPARTMENT      = "technology"
    DIRECTOR_AGENTS = ["dir_ios", "dir_android", "dir_mobile_ux", "dir_push"]
    SYSTEM_PROMPT   = "You are VP Mobile. Plan iOS/Android workstreams. Respond in JSON only."

# ── PRODUCT VPs (5) ───────────────────────────────────────────────

class VPProductAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_product"
    AGENT_TYPE_KEY  = "vp_product"
    DEPARTMENT      = "product"
    DIRECTOR_AGENTS = ["dir_product_strategy", "dir_features", "dir_roadmap", "dir_prd"]
    SYSTEM_PROMPT   = "You are VP Product. Plan product strategy workstreams. Respond in JSON only."

class VPContentAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_content"
    AGENT_TYPE_KEY  = "vp_content"
    DEPARTMENT      = "product"
    DIRECTOR_AGENTS = ["dir_editorial", "dir_regulatory_content", "dir_seo", "dir_translations"]
    SYSTEM_PROMPT   = "You are VP Content. Plan content strategy workstreams. Respond in JSON only."

class VPUXAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_ux"
    AGENT_TYPE_KEY  = "vp_ux"
    DEPARTMENT      = "product"
    DIRECTOR_AGENTS = ["dir_design", "dir_research", "dir_accessibility", "dir_design_system"]
    SYSTEM_PROMPT   = "You are VP UX. Plan user experience workstreams. Respond in JSON only."

class VPGrowthProductAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_growth_product"
    AGENT_TYPE_KEY  = "vp_growth_product"
    DEPARTMENT      = "product"
    DIRECTOR_AGENTS = ["dir_activation", "dir_retention", "dir_referral", "dir_freemium"]
    SYSTEM_PROMPT   = "You are VP Growth (Product). Plan product-led growth workstreams. Respond in JSON only."

class VPPartnershipsAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_partnerships"
    AGENT_TYPE_KEY  = "vp_partnerships"
    DEPARTMENT      = "product"
    DIRECTOR_AGENTS = ["dir_data_partnerships", "dir_api_partners", "dir_white_label", "dir_integrations_biz"]
    SYSTEM_PROMPT   = "You are VP Partnerships. Plan data/API partnership workstreams. Respond in JSON only."

# ── REVENUE VPs (5) ───────────────────────────────────────────────

class VPGrowthAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_growth"
    AGENT_TYPE_KEY  = "vp_growth"
    DEPARTMENT      = "revenue"
    DIRECTOR_AGENTS = ["dir_acquisition", "dir_conversion", "dir_ab_testing", "dir_funnels"]
    SYSTEM_PROMPT   = "You are VP Growth (Revenue). Plan subscriber acquisition workstreams. Respond in JSON only."

class VPSalesAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_sales"
    AGENT_TYPE_KEY  = "vp_sales"
    DEPARTMENT      = "revenue"
    DIRECTOR_AGENTS = ["dir_enterprise_sales", "dir_smb_sales", "dir_sales_ops", "dir_demos"]
    SYSTEM_PROMPT   = "You are VP Sales. Plan enterprise/SMB sales workstreams. Respond in JSON only."

class VPMarketingAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_marketing"
    AGENT_TYPE_KEY  = "vp_marketing"
    DEPARTMENT      = "revenue"
    DIRECTOR_AGENTS = ["dir_content_marketing", "dir_email_marketing", "dir_social", "dir_paid", "dir_brand"]
    SYSTEM_PROMPT   = "You are VP Marketing. Plan marketing channel workstreams. Respond in JSON only."

class VPCustomerSuccessAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_customer_success"
    AGENT_TYPE_KEY  = "vp_customer_success"
    DEPARTMENT      = "revenue"
    DIRECTOR_AGENTS = ["dir_onboarding_success", "dir_renewal", "dir_expansion", "dir_nps"]
    SYSTEM_PROMPT   = "You are VP Customer Success. Plan retention/expansion workstreams. Respond in JSON only."

class VPPricingAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_pricing"
    AGENT_TYPE_KEY  = "vp_pricing"
    DEPARTMENT      = "revenue"
    DIRECTOR_AGENTS = ["dir_pricing_analysis", "dir_packaging", "dir_monetization"]
    SYSTEM_PROMPT   = "You are VP Pricing. Plan pricing strategy workstreams. Respond in JSON only."

# ── RISK VPs (5) ──────────────────────────────────────────────────

class VPComplianceAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_compliance"
    AGENT_TYPE_KEY  = "vp_compliance"
    DEPARTMENT      = "risk"
    CONFIDENCE_THRESHOLD = 0.90
    DIRECTOR_AGENTS = ["dir_regulatory_compliance", "dir_data_privacy", "dir_gdpr", "dir_licensing"]
    SYSTEM_PROMPT   = "You are VP Compliance. Plan regulatory compliance workstreams. High standards required. Respond in JSON only."

class VPEthicsAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_ethics"
    AGENT_TYPE_KEY  = "vp_ethics"
    DEPARTMENT      = "risk"
    CONFIDENCE_THRESHOLD = 0.90
    DIRECTOR_AGENTS = ["dir_ai_ethics", "dir_bias_detection", "dir_fairness", "dir_transparency"]
    SYSTEM_PROMPT   = "You are VP AI Ethics. Plan AI ethics and fairness workstreams. Respond in JSON only."

class VPLegalAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_legal"
    AGENT_TYPE_KEY  = "vp_legal"
    DEPARTMENT      = "risk"
    CONFIDENCE_THRESHOLD = 0.90
    ESCALATE_TO_TYPE = "cro_risk_agent"
    DIRECTOR_AGENTS = ["dir_contracts", "dir_ip", "dir_employment_law", "dir_dispute"]
    SYSTEM_PROMPT   = "You are VP Legal. Plan legal review workstreams. Any uncertain legal question escalates. Respond in JSON only."

class VPAuditAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_audit"
    AGENT_TYPE_KEY  = "vp_audit"
    DEPARTMENT      = "risk"
    DIRECTOR_AGENTS = ["dir_internal_audit", "dir_financial_audit", "dir_ai_audit", "dir_vendor_audit"]
    SYSTEM_PROMPT   = "You are VP Internal Audit. Plan audit and assurance workstreams. Respond in JSON only."

class VPTrustSafetyAgent(VPAgent):
    AGENT_ID_PREFIX = "vp_trust_safety"
    AGENT_TYPE_KEY  = "vp_trust_safety"
    DEPARTMENT      = "risk"
    DIRECTOR_AGENTS = ["dir_content_moderation", "dir_abuse_prevention", "dir_fraud_detection"]
    SYSTEM_PROMPT   = "You are VP Trust & Safety. Plan content safety workstreams. Respond in JSON only."
