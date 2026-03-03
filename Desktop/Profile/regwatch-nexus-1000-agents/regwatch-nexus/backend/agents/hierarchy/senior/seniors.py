"""
Senior Agent Layer — 200 Senior Specialists.
Each is a domain expert. Uses Haiku for execution.
Receives atomic tasks from Directors. Executes with deep domain knowledge.
Dispatches execution sub-tasks to Junior agents.
"""
import json, logging, re
from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.protocol import Task, AgentTier, AutonomyLevel, TaskPriority
from backend.orchestration.task_queue import get_task_queue

logger = logging.getLogger(__name__)


class SeniorAgent(BaseAgent):
    """All 200 senior agents share this execution pattern."""
    AGENT_TIER           = AgentTier.SENIOR
    AUTONOMY_LEVEL       = AutonomyLevel.L3_AI_EXECUTES_AUDIT
    CONFIDENCE_THRESHOLD = 0.70
    MODEL                = "claude-haiku-4-5-20251001"
    MAX_TOKENS           = 2500
    JUNIOR_AGENTS: list[str] = []

    async def _reason(self, task: Task, context: dict) -> tuple[dict, float, list[str]]:
        trace = [f"[{self.agent_id}] Executing: {task.title}"]

        prompt = f"""You are a senior specialist: {self.SYSTEM_PROMPT}

TASK: {task.title}
INSTRUCTIONS: {task.description}
EXPECTED_OUTPUT: {context.get('expected_output', 'structured analysis')}
CONTEXT: {json.dumps(context, default=str)[:1500]}

Perform this task with domain expertise. Return JSON:
{"analysis": "...", "findings": [...], "recommendations": [...], "action_items": [...], "confidence": 0.0, "flags": []}
JSON only."""

        resp, conf = await self._llm(prompt)
        try:
            result = json.loads(resp)
        except Exception:
            m = re.search(r'\{.*\}', resp, re.DOTALL)
            result = json.loads(m.group()) if m else {"analysis": resp[:800], "parse_error": True}
            conf *= 0.65

        # Dispatch execution tasks to juniors if needed
        if self.JUNIOR_AGENTS and result.get("action_items"):
            for i, action in enumerate(result["action_items"][:3]):
                jtype = self.JUNIOR_AGENTS[i % len(self.JUNIOR_AGENTS)]
                jsub = Task(
                    title=str(action)[:80],
                    description=str(action),
                    agent_type=jtype,
                    parent_task_id=task.task_id,
                    priority=task.priority,
                    department=self.DEPARTMENT,
                    context={"senior_context": task.title},
                )
                await get_task_queue().enqueue(jsub)
                trace.append(f"[{self.agent_id}] → junior {jtype}: {str(action)[:40]}")

        return result, result.get("confidence", conf), trace


def create_senior_class(type_key: str, dept: str, responsibility: str, juniors: list = None):
    return type(
        f"Senior_{type_key}",
        (SeniorAgent,),
        {
            "AGENT_ID_PREFIX": type_key,
            "AGENT_TYPE_KEY":  type_key,
            "DEPARTMENT":      dept,
            "ESCALATE_TO_TYPE": f"dir_{dept.split('_')[0]}",
            "JUNIOR_AGENTS":   juniors or [],
            "SYSTEM_PROMPT":   f"Senior specialist in {responsibility}. Execute tasks with depth and precision.",
        }
    )


_SENIOR_DEFINITIONS = [
    ("snr_pipeline_analyst", "operations", "Pipeline performance analysis and throughput optimization"),
    ("snr_scheduler", "operations", "Agent task scheduling, cron jobs, APScheduler management"),
    ("snr_throughput", "operations", "Throughput bottleneck identification and resolution"),
    ("snr_sys_monitor", "operations", "System-level monitoring: CPU, memory, disk, network"),
    ("snr_agent_health", "operations", "Monitor health of all 1000 agents. Detect stalled/failed agents"),
    ("snr_alert_ops", "operations", "Operational alerting on system metrics and thresholds"),
    ("snr_incident_coordinator", "operations", "P1/P2 incident coordination, runbook execution"),
    ("snr_postmortem", "operations", "Post-incident analysis, root cause identification, prevention"),
    ("snr_capacity_analyst", "operations", "Capacity modeling for compute, storage, API quotas"),
    ("snr_cost_optimizer", "operations", "Cloud cost analysis, RI recommendations, waste identification"),
    ("snr_crawler_ops", "operations", "Web crawler management for 160+ regulatory sources"),
    ("snr_parser", "operations", "Document parsing: PDF, HTML, XML, RSS regulatory sources"),
    ("snr_dedup", "operations", "Deduplication of regulatory alerts across overlapping sources"),
    ("snr_quality_scorer", "operations", "Score alert quality: accuracy, completeness, relevance"),
    ("snr_fact_checker", "operations", "Cross-reference regulatory facts against authoritative sources"),
    ("snr_schema_validator", "operations", "Validate all data against defined schemas before DB write"),
    ("snr_db_ops", "operations", "PostgreSQL operations: backups, vacuum, replication health"),
    ("snr_s3_ops", "operations", "AWS S3 lifecycle management, bucket policies, access logs"),
    ("snr_cache_ops", "operations", "Redis cache hit rate optimization, key expiry management"),
    ("snr_etl_designer", "operations", "ETL pipeline design for new regulatory source types"),
    ("snr_transformer", "operations", "Data transformation rules: normalize regulatory data formats"),
    ("snr_aws_ops", "operations", "AWS infrastructure operations and cost management"),
    ("snr_terraform", "operations", "Terraform IaC management, state management, drift detection"),
    ("snr_cost_aws", "operations", "AWS cost optimization and RI/SP purchasing decisions"),
    ("snr_dba", "operations", "Database administration, schema migrations, performance"),
    ("snr_query_optimizer", "operations", "PostgreSQL query optimization, index strategy, EXPLAIN ANALYZE"),
    ("snr_network_ops", "operations", "Network routing, security groups, firewall rules"),
    ("snr_cdn_ops", "operations", "CDN configuration, cache rules, edge performance"),
    ("snr_cicd", "operations", "CI/CD pipeline management, GitHub Actions, deployment gates"),
    ("snr_docker_ops", "operations", "Docker image optimization, multi-stage builds, ECR management"),
    ("snr_deploy", "operations", "Deployment orchestration, blue/green, canary releases"),
    ("snr_qa_lead", "operations", "QA strategy, test plan creation, coverage requirements"),
    ("snr_test_writer", "operations", "Automated test case authoring, pytest, test data management"),
    ("snr_content_validator", "operations", "Validate AI-generated regulatory content before publish"),
    ("snr_accuracy_reviewer", "operations", "Cross-check regulatory summaries against source documents"),
    ("snr_test_architect", "operations", "Test architecture: unit/integration/e2e/load/chaos"),
    ("snr_load_tester", "operations", "Load testing with Locust/k6, bottleneck identification"),
    ("snr_benchmark_analyst", "operations", "AI output benchmarking vs expert baseline performance"),
    ("snr_comparison", "operations", "Comparative analysis of agent output vs human expert"),
    ("snr_sre_lead", "operations", "SRE practices, error budget management, SLA tracking"),
    ("snr_support_lead", "technology", "Customer support team lead, escalation handling"),
    ("snr_ticket_router", "technology", "Support ticket classification and routing to right team"),
    ("snr_tech_writer", "technology", "Technical documentation, API guides, developer resources"),
    ("snr_api_doc_writer", "technology", "OpenAPI spec writing, endpoint documentation, examples"),
    ("snr_onboarding_designer", "technology", "Onboarding flow design, activation checkpoint mapping"),
    ("snr_activation_analyst", "technology", "Activation funnel analysis, drop-off identification"),
    ("snr_runbook_writer", "technology", "Operational runbook creation for all failure scenarios"),
    ("snr_backend_dev", "technology", "FastAPI backend development, async patterns, performance"),
    ("snr_api_dev", "technology", "REST API endpoint development, request/response design"),
    ("snr_db_dev", "technology", "Database model development, migration scripts, SQLAlchemy"),
    ("snr_frontend_dev", "technology", "HTML/CSS/JS frontend development, page optimization"),
    ("snr_css_specialist", "technology", "CSS design systems, animation, responsive design"),
    ("snr_api_designer", "technology", "REST API design principles, versioning, backward compat"),
    ("snr_openapi_writer", "technology", "OpenAPI/Swagger specification writing and maintenance"),
    ("snr_stripe_dev", "technology", "Stripe integration: subscriptions, webhooks, billing portal"),
    ("snr_sendgrid_dev", "technology", "SendGrid integration: transactional emails, templates"),
    ("snr_aws_dev", "technology", "AWS SDK integration, boto3, service configurations"),
    ("snr_agent_architect", "technology", "AI agent architecture design, communication patterns"),
    ("snr_prompt_designer", "technology", "System prompt design for specialized agents"),
    ("snr_model_selector", "technology", "LLM model selection by task type and cost efficiency"),
    ("snr_cost_analyst_ai", "technology", "AI API cost analysis, token optimization, ROI calculation"),
    ("snr_prompt_engineer", "technology", "Advanced prompt engineering, chain-of-thought, few-shot"),
    ("snr_few_shot_designer", "technology", "Few-shot example design for consistent agent outputs"),
    ("snr_eval_designer", "technology", "Evaluation framework design, rubric creation, test cases"),
    ("snr_eval_runner", "technology", "Automated eval execution, regression detection, reporting"),
    ("snr_appsec_analyst", "technology", "Application security review, OWASP Top 10 mitigation"),
    ("snr_vuln_scanner", "technology", "Automated vulnerability scanning, CVE monitoring"),
    ("snr_infosec_analyst", "technology", "Information security policy, threat modeling, controls"),
    ("snr_key_manager", "technology", "AWS KMS, secret rotation, credential management"),
    ("snr_auth_dev", "technology", "JWT auth implementation, refresh token flow, session mgmt"),
    ("snr_oauth_specialist", "technology", "OAuth 2.0, PKCE, authorization code flow implementation"),
    ("snr_pen_tester", "technology", "Penetration testing execution, finding documentation"),
    ("snr_bug_bounty", "technology", "Bug bounty program management, severity classification"),
    ("snr_architect", "technology", "System architecture review, service boundary design"),
    ("snr_system_designer", "technology", "System design for scale, partitioning, consistency models"),
    ("snr_search_engineer", "technology", "Full-text search implementation, pg_trgm, ranking tuning"),
    ("snr_relevance_tuner", "technology", "Search relevance optimization, A/B testing results"),
    ("snr_notif_engineer", "technology", "Push notification pipeline, APNs/FCM, delivery rates"),
    ("snr_digest_designer", "technology", "Email digest template design, personalization logic"),
    ("snr_analytics_engineer", "technology", "Event tracking, data warehouse, analytics pipeline"),
    ("snr_dashboard_builder", "product", "Analytics dashboard design and implementation"),
    ("snr_ios_dev", "product", "React Native iOS development, native modules"),
    ("snr_app_store_ops", "product", "App Store Connect, review guidelines, metadata"),
    ("snr_android_dev", "product", "React Native Android, ProGuard, Play Store ops"),
    ("snr_play_store_ops", "product", "Google Play Console, release tracks, store listing"),
    ("snr_mobile_ux_designer", "product", "Mobile UX patterns, gesture design, touch targets"),
    ("snr_performance_mobile", "product", "React Native performance, JS bridge optimization"),
    ("snr_push_engineer", "product", "Expo push, token management, notification batching"),
    ("snr_notification_analyst", "product", "Push notification engagement rates, A/B testing"),
    ("snr_product_strategist", "product", "Product strategy development, OKR alignment, positioning"),
    ("snr_competitive_analyst", "product", "Competitive intelligence, feature gap analysis"),
    ("snr_feature_pm", "product", "Feature project management, sprint planning, delivery"),
    ("snr_spec_writer", "product", "Product specification writing, acceptance criteria"),
    ("snr_roadmap_planner", "product", "Quarterly roadmap planning, dependency sequencing"),
    ("snr_milestone_tracker", "product", "Milestone tracking, status reporting, risk flags"),
    ("snr_prd_writer", "product", "Product requirement documents, user story format"),
    ("snr_requirements_analyst", "product", "Requirements gathering, stakeholder interview synthesis"),
    ("snr_editorial_lead", "product", "Editorial standards, tone, regulatory writing quality"),
    ("snr_copy_editor", "product", "Proofreading, fact-checking, style guide enforcement"),
    ("snr_reg_writer", "product", "Regulatory alert authoring, technical accuracy"),
    ("snr_citation_checker", "product", "Verify regulatory citations, source links, publication dates"),
    ("snr_seo_analyst", "product", "Keyword research, content SEO, ranking analysis"),
    ("snr_technical_seo", "product", "Technical SEO: sitemaps, schema markup, Core Web Vitals"),
    ("snr_translator_coord", "product", "Translation project coordination, vendor management"),
    ("snr_terminology_manager", "product", "Regulatory terminology glossary, consistency enforcement"),
    ("snr_visual_designer", "product", "Visual design: typography, color, layout composition"),
    ("snr_ui_designer", "product", "UI component design, interaction patterns, prototyping"),
    ("snr_ux_researcher", "product", "User research: interviews, surveys, usability studies"),
    ("snr_insight_analyst", "product", "Research insight synthesis, behavioral pattern identification"),
    ("snr_a11y_specialist", "product", "WCAG 2.2 implementation, screen reader testing, audits"),
    ("snr_wcag_auditor", "product", "WCAG compliance auditing, accessibility report writing"),
    ("snr_design_system_lead", "product", "Design system governance, component library management"),
    ("snr_token_manager", "product", "Design token management, Figma/CSS sync"),
    ("snr_activation_pm", "product", "Activation PM: first-value milestones, Aha moment design"),
    ("snr_onboarding_analyst", "product", "Onboarding funnel analysis, drop-off investigation"),
    ("snr_retention_analyst", "product", "Cohort retention analysis, engagement scoring"),
    ("snr_churn_modeler", "product", "Churn prediction model, risk scoring, trigger design"),
    ("snr_referral_pm", "product", "Referral program management, incentive design"),
    ("snr_viral_analyst", "product", "Viral coefficient analysis, k-factor optimization"),
    ("snr_freemium_analyst", "product", "Freemium conversion analysis, upgrade moment mapping"),
    ("snr_upgrade_optimizer", "revenue", "Upgrade CTA optimization, pricing page conversion"),
    ("snr_partnership_analyst", "revenue", "Data partnership opportunity analysis and structuring"),
    ("snr_data_licensor", "revenue", "Data licensing deal terms, API data agreements"),
    ("snr_partner_dev", "revenue", "API partner technical integration support"),
    ("snr_devrel", "revenue", "Developer relations, SDK maintenance, developer docs"),
    ("snr_white_label_pm", "revenue", "White-label product management, client customization"),
    ("snr_client_success", "revenue", "Enterprise client success management"),
    ("snr_biz_integrations_dev", "revenue", "Slack/Teams/Salesforce integration development"),
    ("snr_slack_developer", "revenue", "Slack app development, slash commands, block kit"),
    ("snr_growth_analyst", "revenue", "Growth loop identification, acquisition channel analysis"),
    ("snr_channel_analyst", "revenue", "Marketing channel attribution, ROAS by channel"),
    ("snr_conversion_analyst", "revenue", "Conversion rate optimization, landing page analysis"),
    ("snr_landing_page_opt", "revenue", "Landing page A/B testing, copy and design optimization"),
    ("snr_experiment_designer", "revenue", "Experiment design: hypothesis, metrics, sample size"),
    ("snr_stats_analyst", "revenue", "Statistical analysis of experiments, significance testing"),
    ("snr_funnel_analyst", "revenue", "Marketing/product funnel analysis, stage conversion"),
    ("snr_cohort_analyst", "revenue", "Cohort analysis, LTV modeling, payback period calculation"),
    ("snr_enterprise_ae", "revenue", "Enterprise account executive: large deal management"),
    ("snr_rfp_responder", "revenue", "RFP response writing, compliance section completion"),
    ("snr_smb_ae", "revenue", "SMB account executive: self-serve deal support"),
    ("snr_trial_converter", "revenue", "Trial-to-paid conversion optimization, outreach"),
    ("snr_crm_manager", "revenue", "CRM data hygiene, pipeline management, forecasting"),
    ("snr_pipeline_analyst_sales", "revenue", "Sales pipeline health analysis, deal velocity tracking"),
    ("snr_demo_specialist", "revenue", "Product demo delivery, objection handling scripts"),
    ("snr_roi_modeler", "revenue", "Customer ROI calculator, business case development"),
    ("snr_blog_writer", "revenue", "Regulatory thought leadership blog content"),
    ("snr_report_writer_mkt", "revenue", "Marketing reports: industry trends, regulatory outlook"),
    ("snr_email_strategist", "revenue", "Email strategy: segmentation, cadence, template design"),
    ("snr_drip_designer", "revenue", "Drip campaign design, behavioral trigger mapping"),
    ("snr_social_manager", "revenue", "Social media content planning and publishing"),
    ("snr_community_manager", "revenue", "Community building, LinkedIn groups, forum engagement"),
    ("snr_paid_specialist", "revenue", "Paid acquisition: Google, LinkedIn, programmatic"),
    ("snr_bid_manager", "revenue", "Bid management, keyword strategy, quality score"),
    ("snr_brand_strategist", "revenue", "Brand positioning, voice, visual identity guidelines"),
    ("snr_pr_writer", "revenue", "Press releases, media pitches, analyst relations"),
    ("snr_cs_onboarding", "revenue", "Customer success onboarding for Pro/Enterprise"),
    ("snr_success_analyst", "revenue", "Customer success metrics: health scores, QBR prep"),
    ("snr_renewal_manager", "revenue", "Annual renewal workflow, QBR delivery, extension terms"),
    ("snr_churn_rescuer", "revenue", "At-risk customer intervention, cancellation win-back"),
    ("snr_expansion_ae", "revenue", "Expansion revenue: upsell opportunities, seat additions"),
    ("snr_upsell_analyst", "risk", "Upsell pattern analysis, product-led expansion signals"),
    ("snr_nps_analyst", "risk", "NPS survey analysis, detractor/promoter segmentation"),
    ("snr_feedback_analyst", "risk", "User feedback synthesis, feature request prioritization"),
    ("snr_pricing_analyst", "risk", "Pricing sensitivity analysis, win/loss attribution"),
    ("snr_competitive_pricer", "risk", "Competitive pricing benchmarking, price adjustment models"),
    ("snr_packaging_pm", "risk", "Subscription packaging PM: plan features, limits"),
    ("snr_bundle_analyst", "risk", "Bundle analysis: feature combinations, willingness to pay"),
    ("snr_monetization_analyst", "risk", "New monetization stream analysis: API, data, white-label"),
    ("snr_api_pricer", "risk", "API usage pricing models, metered billing design"),
    ("snr_compliance_analyst", "risk", "Regulatory compliance analysis for RegWatch itself"),
    ("snr_reg_tracker", "risk", "Track regulatory changes affecting the platform"),
    ("snr_privacy_analyst", "risk", "Data privacy impact analysis for new features"),
    ("snr_data_mapper", "risk", "Data flow mapping, PII identification, data inventory"),
    ("snr_gdpr_specialist", "risk", "GDPR technical implementation: consent, erasure, portability"),
    ("snr_dpia_writer", "risk", "Data Protection Impact Assessment documentation"),
    ("snr_licensing_analyst", "risk", "Software and content licensing review and management"),
    ("snr_oss_reviewer", "risk", "Open-source license compliance, copyleft risk assessment"),
    ("snr_ethics_reviewer", "risk", "AI output ethics review: potential harms, bias flags"),
    ("snr_harm_analyst", "risk", "Potential harm analysis for new AI capabilities"),
    ("snr_bias_auditor", "risk", "Systematic bias audit of regulatory alert scoring"),
    ("snr_fairness_tester", "risk", "Algorithmic fairness testing across geographic regions"),
    ("snr_fairness_analyst", "risk", "Fairness metric analysis, disparity measurement"),
    ("snr_score_auditor", "risk", "Impact score auditing: methodology review, calibration"),
    ("snr_transparency_writer", "risk", "AI transparency documentation, model cards, disclosure"),
    ("snr_explainability", "risk", "Model explainability, decision trace documentation"),
    ("snr_contract_reviewer", "risk", "Contract review: SaaS agreements, data processing terms"),
    ("snr_terms_writer", "risk", "Terms of service, privacy policy, DPA drafting"),
    ("snr_ip_analyst", "risk", "IP risk analysis, patent landscape, freedom to operate"),
    ("snr_oss_auditor", "risk", "Open-source dependency audit, vulnerability scanning"),
    ("snr_employment_analyst", "risk", "AI employment law: agent liability, automation regulations"),
    ("snr_dispute_coordinator", "risk", "Customer dispute coordination, factual corrections"),
    ("snr_resolution_writer", "risk", "Dispute resolution documentation, response templates"),
    ("snr_internal_auditor", "risk", "Internal audit execution: process, controls, gaps"),
    ("snr_process_reviewer", "risk", "Business process review for compliance gaps"),
    ("snr_financial_auditor", "risk", "Revenue audit, subscription accounting, tax compliance"),
    ("snr_recon_analyst", "risk", "Stripe-to-database reconciliation, revenue recognition"),
    ("snr_ai_auditor", "risk", "AI agent output audit: quality, safety, accuracy"),
    ("snr_agent_reviewer", "risk", "Review AI agent decision traces for compliance"),
    ("snr_vendor_reviewer", "risk", "Vendor risk assessment: Anthropic, AWS, Stripe, SendGrid"),
    ("snr_cost_auditor", "risk", "Third-party cost audit, contract terms, overcharges"),
]

SENIOR_REGISTRY: dict[str, type] = {
    type_key: create_senior_class(type_key, dept, resp)
    for type_key, dept, resp in _SENIOR_DEFINITIONS
}
print(f"Senior agents registered: {len(SENIOR_REGISTRY)}")
