"""
Director Layer — 100 Director Agents.
Directors receive tasks from VPs and decompose into Senior Agent work.
All use Haiku — cost-efficient mid-tier reasoning.
"""
import json
import logging
from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.protocol import (
    Task, AgentTier, AutonomyLevel, TaskPriority
)
from backend.orchestration.task_queue import get_task_queue

logger = logging.getLogger(__name__)

DIRECTOR_SENIOR_MAP = {
    # Each director has 2-4 senior agent types it dispatches to
    "dir_pipeline":            ["snr_pipeline_analyst", "snr_scheduler", "snr_throughput"],
    "dir_monitoring":          ["snr_sys_monitor", "snr_agent_health", "snr_alert_ops"],
    "dir_incident":            ["snr_incident_coordinator", "snr_postmortem"],
    "dir_capacity":            ["snr_capacity_analyst", "snr_cost_optimizer"],
    "dir_data_pipeline":       ["snr_crawler_ops", "snr_parser", "snr_dedup"],
    "dir_data_quality":        ["snr_quality_scorer", "snr_fact_checker", "snr_schema_validator"],
    "dir_data_storage":        ["snr_db_ops", "snr_s3_ops", "snr_cache_ops"],
    "dir_etl":                 ["snr_etl_designer", "snr_transformer"],
    "dir_cloud":               ["snr_aws_ops", "snr_terraform", "snr_cost_aws"],
    "dir_database":            ["snr_dba", "snr_query_optimizer"],
    "dir_networking":          ["snr_network_ops", "snr_cdn_ops"],
    "dir_devops":              ["snr_cicd", "snr_docker_ops", "snr_deploy"],
    "dir_qa":                  ["snr_qa_lead", "snr_test_writer"],
    "dir_validation":          ["snr_content_validator", "snr_accuracy_reviewer"],
    "dir_testing":             ["snr_test_architect", "snr_load_tester"],
    "dir_benchmarking":        ["snr_benchmark_analyst", "snr_comparison"],
    "dir_customer_support":    ["snr_support_lead", "snr_ticket_router"],
    "dir_docs":                ["snr_tech_writer", "snr_api_doc_writer"],
    "dir_onboarding":          ["snr_onboarding_designer", "snr_activation_analyst"],
    "dir_sre":                 ["snr_sre_lead", "snr_runbook_writer"],
    "dir_backend":             ["snr_backend_dev", "snr_api_dev", "snr_db_dev"],
    "dir_frontend":            ["snr_frontend_dev", "snr_css_specialist"],
    "dir_api":                 ["snr_api_designer", "snr_openapi_writer"],
    "dir_integrations":        ["snr_stripe_dev", "snr_sendgrid_dev", "snr_aws_dev"],
    "dir_agent_design":        ["snr_agent_architect", "snr_prompt_designer"],
    "dir_model_ops":           ["snr_model_selector", "snr_cost_analyst_ai"],
    "dir_prompt_eng":          ["snr_prompt_engineer", "snr_few_shot_designer"],
    "dir_evals":               ["snr_eval_designer", "snr_eval_runner"],
    "dir_appsec":              ["snr_appsec_analyst", "snr_vuln_scanner"],
    "dir_infosec":             ["snr_infosec_analyst", "snr_key_manager"],
    "dir_auth":                ["snr_auth_dev", "snr_oauth_specialist"],
    "dir_pen_testing":         ["snr_pen_tester", "snr_bug_bounty"],
    "dir_platform_arch":       ["snr_architect", "snr_system_designer"],
    "dir_search":              ["snr_search_engineer", "snr_relevance_tuner"],
    "dir_notifications":       ["snr_notif_engineer", "snr_digest_designer"],
    "dir_analytics":           ["snr_analytics_engineer", "snr_dashboard_builder"],
    "dir_ios":                 ["snr_ios_dev", "snr_app_store_ops"],
    "dir_android":             ["snr_android_dev", "snr_play_store_ops"],
    "dir_mobile_ux":           ["snr_mobile_ux_designer", "snr_performance_mobile"],
    "dir_push":                ["snr_push_engineer", "snr_notification_analyst"],
    "dir_product_strategy":    ["snr_product_strategist", "snr_competitive_analyst"],
    "dir_features":            ["snr_feature_pm", "snr_spec_writer"],
    "dir_roadmap":             ["snr_roadmap_planner", "snr_milestone_tracker"],
    "dir_prd":                 ["snr_prd_writer", "snr_requirements_analyst"],
    "dir_editorial":           ["snr_editorial_lead", "snr_copy_editor"],
    "dir_regulatory_content":  ["snr_reg_writer", "snr_citation_checker"],
    "dir_seo":                 ["snr_seo_analyst", "snr_technical_seo"],
    "dir_translations":        ["snr_translator_coord", "snr_terminology_manager"],
    "dir_design":              ["snr_visual_designer", "snr_ui_designer"],
    "dir_research":            ["snr_ux_researcher", "snr_insight_analyst"],
    "dir_accessibility":       ["snr_a11y_specialist", "snr_wcag_auditor"],
    "dir_design_system":       ["snr_design_system_lead", "snr_token_manager"],
    "dir_activation":          ["snr_activation_pm", "snr_onboarding_analyst"],
    "dir_retention":           ["snr_retention_analyst", "snr_churn_modeler"],
    "dir_referral":            ["snr_referral_pm", "snr_viral_analyst"],
    "dir_freemium":            ["snr_freemium_analyst", "snr_upgrade_optimizer"],
    "dir_data_partnerships":   ["snr_partnership_analyst", "snr_data_licensor"],
    "dir_api_partners":        ["snr_partner_dev", "snr_devrel"],
    "dir_white_label":         ["snr_white_label_pm", "snr_client_success"],
    "dir_integrations_biz":    ["snr_biz_integrations_dev", "snr_slack_developer"],
    "dir_acquisition":         ["snr_growth_analyst", "snr_channel_analyst"],
    "dir_conversion":          ["snr_conversion_analyst", "snr_landing_page_opt"],
    "dir_ab_testing":          ["snr_experiment_designer", "snr_stats_analyst"],
    "dir_funnels":             ["snr_funnel_analyst", "snr_cohort_analyst"],
    "dir_enterprise_sales":    ["snr_enterprise_ae", "snr_rfp_responder"],
    "dir_smb_sales":           ["snr_smb_ae", "snr_trial_converter"],
    "dir_sales_ops":           ["snr_crm_manager", "snr_pipeline_analyst_sales"],
    "dir_demos":               ["snr_demo_specialist", "snr_roi_modeler"],
    "dir_content_marketing":   ["snr_blog_writer", "snr_report_writer_mkt"],
    "dir_email_marketing":     ["snr_email_strategist", "snr_drip_designer"],
    "dir_social":              ["snr_social_manager", "snr_community_manager"],
    "dir_paid":                ["snr_paid_specialist", "snr_bid_manager"],
    "dir_brand":               ["snr_brand_strategist", "snr_pr_writer"],
    "dir_onboarding_success":  ["snr_cs_onboarding", "snr_success_analyst"],
    "dir_renewal":             ["snr_renewal_manager", "snr_churn_rescuer"],
    "dir_expansion":           ["snr_expansion_ae", "snr_upsell_analyst"],
    "dir_nps":                 ["snr_nps_analyst", "snr_feedback_analyst"],
    "dir_pricing_analysis":    ["snr_pricing_analyst", "snr_competitive_pricer"],
    "dir_packaging":           ["snr_packaging_pm", "snr_bundle_analyst"],
    "dir_monetization":        ["snr_monetization_analyst", "snr_api_pricer"],
    "dir_regulatory_compliance":["snr_compliance_analyst", "snr_reg_tracker"],
    "dir_data_privacy":        ["snr_privacy_analyst", "snr_data_mapper"],
    "dir_gdpr":                ["snr_gdpr_specialist", "snr_dpia_writer"],
    "dir_licensing":           ["snr_licensing_analyst", "snr_oss_reviewer"],
    "dir_ai_ethics":           ["snr_ethics_reviewer", "snr_harm_analyst"],
    "dir_bias_detection":      ["snr_bias_auditor", "snr_fairness_tester"],
    "dir_fairness":            ["snr_fairness_analyst", "snr_score_auditor"],
    "dir_transparency":        ["snr_transparency_writer", "snr_explainability"],
    "dir_contracts":           ["snr_contract_reviewer", "snr_terms_writer"],
    "dir_ip":                  ["snr_ip_analyst", "snr_oss_auditor"],
    "dir_employment_law":      ["snr_employment_analyst"],
    "dir_dispute":             ["snr_dispute_coordinator", "snr_resolution_writer"],
    "dir_internal_audit":      ["snr_internal_auditor", "snr_process_reviewer"],
    "dir_financial_audit":     ["snr_financial_auditor", "snr_recon_analyst"],
    "dir_ai_audit":            ["snr_ai_auditor", "snr_agent_reviewer"],
    "dir_vendor_audit":        ["snr_vendor_reviewer", "snr_cost_auditor"],
    "dir_content_moderation":  ["snr_content_moderator", "snr_harmful_content"],
    "dir_abuse_prevention":    ["snr_abuse_analyst", "snr_rate_limit_designer"],
    "dir_fraud_detection":     ["snr_fraud_analyst", "snr_chargeback_handler"],
    "dir_crisis_management":   ["snr_crisis_coordinator", "snr_comms_writer"],
}


class DirectorAgent(BaseAgent):
    """All 100 director agents share this base. Parametrized at instantiation."""
    AGENT_TIER           = AgentTier.DIRECTOR
    AUTONOMY_LEVEL       = AutonomyLevel.L3_AI_EXECUTES_AUDIT
    CONFIDENCE_THRESHOLD = 0.72
    MODEL                = "claude-haiku-4-5-20251001"
    MAX_TOKENS           = 2000

    async def _reason(self, task: Task, context: dict) -> tuple[dict, float, list[str]]:
        trace = [f"[{self.agent_id}] Breaking down: {task.title}"]
        senior_agents = DIRECTOR_SENIOR_MAP.get(self.AGENT_TYPE_KEY, [])

        prompt = f"""TASK: {task.title}
DESCRIPTION: {task.description}
DEPARTMENT: {self.DEPARTMENT}
SENIOR_AGENTS: {senior_agents}

Decompose into atomic senior-agent tasks (2-5 tasks).
Return JSON:
{{"task_breakdown": [{{"senior_agent": "...", "title": "...", "instructions": "...", "expected_output": "..."}}], "dependencies": [], "confidence": 0.0}}
Output JSON only, no commentary."""
        resp, conf = await self._llm(prompt)
        try:
            result = json.loads(resp)
        except Exception:
            result = {"raw": resp[:500], "parse_error": True}
            conf *= 0.65

        for st in result.get("task_breakdown", []):
            snr_type = st.get("senior_agent", "")
            if snr_type in senior_agents:
                sub = Task(
                    title=st.get("title", "Senior Task"),
                    description=st.get("instructions", ""),
                    agent_type=snr_type,
                    parent_task_id=task.task_id,
                    priority=task.priority,
                    department=self.DEPARTMENT,
                    context={"director_task": task.title,
                             "expected_output": st.get("expected_output", "")},
                )
                await get_task_queue().enqueue(sub)
                trace.append(f"[{self.agent_id}] → {snr_type}")

        return result, result.get("confidence", conf), trace



def create_director_class(type_key: str, dept: str, name: str, responsibility: str):
    """Factory: creates a named Director class parametrized by type/dept."""
    return type(
        f"Director_{type_key}",
        (DirectorAgent,),
        {
            "AGENT_ID_PREFIX":    type_key,
            "AGENT_TYPE_KEY":     type_key,
            "DEPARTMENT":         dept,
            "ESCALATE_TO_TYPE":   f"vp_{dept}",  # Approximate escalation target
            "SYSTEM_PROMPT":      f"You are a Director agent: {name}. {responsibility} Respond in JSON only.",
        }
    )

# Generate all 100 director classes
_DIRECTOR_DEFINITIONS = [
    ("dir_pipeline", "operations", "Pipeline Orchestration Director", "Manage agent pipeline scheduling, throughput, and bottleneck resolution."),
    ("dir_monitoring", "operations", "System Monitoring Director", "Monitor all 1000 agents. Detect failures, latency spikes, and cascade issues."),
    ("dir_incident", "operations", "Incident Response Director", "Coordinate incident response when platform components fail or degrade."),
    ("dir_capacity", "operations", "Capacity Planning Director", "Plan compute capacity for crawl bursts, regulatory storms, and growth."),
    ("dir_data_pipeline", "operations", "Data Pipeline Director", "Orchestrate data ingestion from 160+ regulatory sources and 100+ firms."),
    ("dir_data_quality", "operations", "Data Quality Director", "Enforce data quality standards across all ingested regulatory content."),
    ("dir_data_storage", "operations", "Data Storage Director", "Manage PostgreSQL schemas, S3 buckets, and Redis cache layers."),
    ("dir_etl", "operations", "ETL Director", "Design and maintain extract-transform-load pipelines for source documents."),
    ("dir_cloud", "operations", "Cloud Infrastructure Director", "Manage AWS ECS, RDS, ElastiCache, and CloudFormation stacks."),
    ("dir_database", "operations", "Database Operations Director", "PostgreSQL performance tuning, index optimization, vacuum scheduling."),
    ("dir_networking", "operations", "Network Director", "VPC design, security groups, CDN configuration, DNS management."),
    ("dir_devops", "operations", "DevOps Director", "CI/CD pipelines, Docker builds, deployment automation, rollbacks."),
    ("dir_qa", "operations", "QA Director", "End-to-end test strategy, test automation coverage, regression management."),
    ("dir_validation", "operations", "Content Validation Director", "Validate all AI-generated content before publication. Accuracy standards."),
    ("dir_testing", "operations", "Software Testing Director", "Unit, integration, and load testing frameworks and coverage targets."),
    ("dir_benchmarking", "operations", "Benchmarking Director", "Benchmark AI agents against human expert outputs. Track quality drift."),
    ("dir_customer_support", "operations", "Customer Support Director", "Support ticket triage, escalation paths, knowledge base management."),
    ("dir_docs", "operations", "Documentation Director", "API docs, user guides, developer docs, agent capability documentation."),
    ("dir_onboarding", "operations", "Onboarding Director", "User activation flows, guided tours, first-value milestones."),
    ("dir_sre", "operations", "SRE Director", "SLA management, error budgets, reliability engineering practices."),
    ("dir_backend", "technology", "Backend Engineering Director", "FastAPI services, async patterns, endpoint performance, Python 3.12."),
    ("dir_frontend", "technology", "Frontend Engineering Director", "HTML/CSS/JS pages, performance optimization, browser compatibility."),
    ("dir_api", "technology", "API Design Director", "REST API design, versioning, rate limiting, OpenAPI documentation."),
    ("dir_integrations", "technology", "Integrations Director", "Stripe, SendGrid, AWS, Expo push, third-party API integrations."),
    ("dir_agent_design", "technology", "Agent Architecture Director", "AI agent design patterns, prompt engineering, capability boundaries."),
    ("dir_model_ops", "technology", "Model Operations Director", "LLM selection by tier, cost optimization, model version management."),
    ("dir_prompt_eng", "technology", "Prompt Engineering Director", "System prompt design, few-shot examples, output format enforcement."),
    ("dir_evals", "technology", "AI Evaluations Director", "Automated evals for all 1000 agents. Accuracy, consistency, safety."),
    ("dir_appsec", "technology", "Application Security Director", "OWASP compliance, SQL injection prevention, API auth security."),
    ("dir_infosec", "technology", "Information Security Director", "Data encryption, key management, security policies, SOC2 readiness."),
    ("dir_auth", "technology", "Auth Systems Director", "JWT implementation, OAuth flows, session management, MFA."),
    ("dir_pen_testing", "technology", "Penetration Testing Director", "Quarterly pen tests, vulnerability disclosure, bug bounty program."),
    ("dir_platform_arch", "technology", "Platform Architecture Director", "System architecture, service boundaries, data flow design."),
    ("dir_search", "technology", "Search Director", "Full-text search, semantic search, pg_trgm optimization, relevance tuning."),
    ("dir_notifications", "technology", "Notification Systems Director", "Push notifications, email digests, Slack webhooks, alert delivery."),
    ("dir_analytics", "technology", "Analytics Platform Director", "Usage analytics, conversion tracking, agent performance dashboards."),
    ("dir_ios", "technology", "iOS Engineering Director", "React Native iOS, App Store compliance, TestFlight, push certs."),
    ("dir_android", "technology", "Android Engineering Director", "React Native Android, Play Store, APK signing, Android-specific UX."),
    ("dir_mobile_ux", "technology", "Mobile UX Director", "Mobile interaction patterns, gesture design, performance on older devices."),
    ("dir_push", "technology", "Push Notification Director", "Expo push, APNs/FCM, notification personalization, delivery rates."),
    ("dir_product_strategy", "product", "Product Strategy Director", "Product vision alignment, competitive positioning, feature prioritization."),
    ("dir_features", "product", "Feature Development Director", "Feature specs, acceptance criteria, product requirement documents."),
    ("dir_roadmap", "product", "Product Roadmap Director", "Quarterly roadmap planning, dependency mapping, milestone tracking."),
    ("dir_prd", "product", "Product Requirements Director", "PRD templates, requirements gathering, stakeholder sign-off."),
    ("dir_editorial", "product", "Editorial Director", "Alert writing standards, summary quality, analyst report style guide."),
    ("dir_regulatory_content", "product", "Regulatory Content Director", "Source accuracy, regulatory citation standards, legal content review."),
    ("dir_seo", "product", "SEO Director", "On-page SEO, technical SEO, alert page ranking, structured data."),
    ("dir_translations", "product", "Localisation Director", "Multi-language support, regulatory terminology translation accuracy."),
    ("dir_design", "product", "Design Director", "Visual design system, component library, brand consistency."),
    ("dir_research", "product", "User Research Director", "User interviews, usability tests, insights synthesis, persona refinement."),
    ("dir_accessibility", "product", "Accessibility Director", "WCAG 2.2 compliance, screen reader testing, keyboard navigation."),
    ("dir_design_system", "product", "Design System Director", "Component documentation, design tokens, Figma/code sync."),
    ("dir_activation", "product", "User Activation Director", "Onboarding flows, activation rate optimization, first-value delivery."),
    ("dir_retention", "product", "Retention Director", "Churn analysis, engagement features, notification personalization."),
    ("dir_referral", "product", "Referral Director", "Referral program design, viral mechanics, sharing features."),
    ("dir_freemium", "product", "Freemium Strategy Director", "Free/pro conversion optimization, gating strategy, upgrade triggers."),
    ("dir_data_partnerships", "product", "Data Partnerships Director", "Regulatory data licensing, academic institution partnerships."),
    ("dir_api_partners", "product", "API Partner Director", "Developer API, partner integrations, webhook marketplace."),
    ("dir_white_label", "product", "White-Label Director", "White-label product offering for compliance consultancies."),
    ("dir_integrations_biz", "product", "Business Integrations Director", "Slack, Teams, Salesforce, Jira, and compliance platform integrations."),
    ("dir_acquisition", "revenue", "Acquisition Director", "SEO traffic, paid acquisition, partnership channels, lead generation."),
    ("dir_conversion", "revenue", "Conversion Director", "Free-to-paid conversion, pricing page optimization, CTA testing."),
    ("dir_ab_testing", "revenue", "A/B Testing Director", "Experiment framework, statistical significance, test roadmap."),
    ("dir_funnels", "revenue", "Funnel Analytics Director", "Funnel analysis, drop-off identification, cohort tracking."),
    ("dir_enterprise_sales", "revenue", "Enterprise Sales Director", "Enterprise deal structure, RFP responses, procurement navigation."),
    ("dir_smb_sales", "revenue", "SMB Sales Director", "Self-serve sales, product demos, trial-to-paid conversion."),
    ("dir_sales_ops", "revenue", "Sales Operations Director", "CRM management, pipeline forecasting, commission structures."),
    ("dir_demos", "revenue", "Demo Director", "Demo environment, sales deck, ROI calculator, case studies."),
    ("dir_content_marketing", "revenue", "Content Marketing Director", "Blog, white papers, regulatory reports, thought leadership."),
    ("dir_email_marketing", "revenue", "Email Marketing Director", "Drip campaigns, digest newsletters, re-engagement campaigns."),
    ("dir_social", "revenue", "Social Media Director", "LinkedIn, Twitter/X, industry forums, community building."),
    ("dir_paid", "revenue", "Paid Advertising Director", "Google Ads, LinkedIn Ads, retargeting, CAC optimization."),
    ("dir_brand", "revenue", "Brand Director", "Brand positioning, voice, visual identity, PR."),
    ("dir_onboarding_success", "revenue", "Onboarding Success Director", "Day-1 success calls, onboarding completion rates, early engagement."),
    ("dir_renewal", "revenue", "Renewal Director", "Annual renewal management, churn risk scoring, retention playbooks."),
    ("dir_expansion", "revenue", "Expansion Revenue Director", "Upsell/cross-sell, seat expansion, enterprise tier upgrades."),
    ("dir_nps", "revenue", "NPS Director", "Net Promoter Score tracking, detractor rescue, promoter activation."),
    ("dir_pricing_analysis", "revenue", "Pricing Analysis Director", "Competitive pricing analysis, willingness-to-pay research."),
    ("dir_packaging", "revenue", "Packaging Director", "Plan bundling, feature packaging, trial offer design."),
    ("dir_monetization", "revenue", "Monetization Director", "New revenue stream identification, API pricing, data licensing."),
    ("dir_regulatory_compliance", "risk", "Regulatory Compliance Director", "Ensure RegWatch itself complies with financial data regulations."),
    ("dir_data_privacy", "risk", "Data Privacy Director", "User data handling, data minimization, retention policies."),
    ("dir_gdpr", "risk", "GDPR Director", "GDPR compliance, DPIAs, right-to-erasure processes, DPA register."),
    ("dir_licensing", "risk", "Licensing Director", "Software licensing, content licensing, API data licensing agreements."),
    ("dir_ai_ethics", "risk", "AI Ethics Director", "Bias audits, harm prevention, ethical guidelines for all AI outputs."),
    ("dir_bias_detection", "risk", "Bias Detection Director", "Monitor AI outputs for regulatory bias, geographic bias, source bias."),
    ("dir_fairness", "risk", "Algorithmic Fairness Director", "Ensure alert scoring is fair across jurisdictions and regulator types."),
    ("dir_transparency", "risk", "AI Transparency Director", "Explainability of AI decisions, disclosure of AI-generated content."),
    ("dir_contracts", "risk", "Contracts Director", "Vendor contracts, customer agreements, SLAs, renewal terms."),
    ("dir_ip", "risk", "IP Director", "Trademark, copyright, trade secrets, open-source license compliance."),
    ("dir_employment_law", "risk", "Employment Law Director", "AI agent employment classification, contractor laws, AI liability."),
    ("dir_dispute", "risk", "Dispute Resolution Director", "Customer disputes, data accuracy claims, regulatory notification disputes."),
    ("dir_internal_audit", "risk", "Internal Audit Director", "Quarterly AI agent audit, process compliance, corrective actions."),
    ("dir_financial_audit", "risk", "Financial Audit Director", "Revenue recognition, subscription accounting, Stripe reconciliation."),
    ("dir_ai_audit", "risk", "AI Systems Audit Director", "Audit all 1000 agents quarterly. Output quality, decision trace review."),
    ("dir_vendor_audit", "risk", "Vendor Audit Director", "Anthropic API usage, AWS costs, Stripe fees, third-party audit."),
    ("dir_content_moderation", "risk", "Content Moderation Director", "Ensure AI outputs don't contain harmful, biased, or misleading content."),
    ("dir_abuse_prevention", "risk", "Abuse Prevention Director", "API abuse, scraping, account sharing, rate limit evasion detection."),
    ("dir_fraud_detection", "risk", "Fraud Detection Director", "Subscription fraud, chargebacks, fake accounts, payment fraud."),
    ("dir_crisis_management", "risk", "Crisis Management Director", "Crisis response playbooks, communication templates, escalation paths."),
]

DIRECTOR_REGISTRY: dict[str, type] = {
    type_key: create_director_class(type_key, dept, name, resp)
    for type_key, dept, name, resp in _DIRECTOR_DEFINITIONS
}

def get_director_class(type_key: str) -> type:
    return DIRECTOR_REGISTRY.get(type_key, DirectorAgent)
