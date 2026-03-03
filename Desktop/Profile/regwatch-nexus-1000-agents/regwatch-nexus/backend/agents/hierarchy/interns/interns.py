"""
Intern Agent Layer — 219 Preprocessing and Logging Agents.
Never make decisions. Preprocess, summarize, log, verify.
These are the workhorses — highest volume, lowest cost.
Use Haiku with minimal tokens.
"""
import json, logging, re
from backend.orchestration.base_agent import BaseAgent
from backend.orchestration.protocol import Task, AgentTier, AutonomyLevel

logger = logging.getLogger(__name__)


class InternAgent(BaseAgent):
    """
    Intern agents: pure data work, no decisions.
    They preprocess inputs for higher agents and log outputs.
    Never escalate to human — always complete or flag to junior layer.
    """
    AGENT_TIER           = AgentTier.INTERN
    AUTONOMY_LEVEL       = AutonomyLevel.L3_AI_EXECUTES_AUDIT
    CONFIDENCE_THRESHOLD = 0.55  # Lower bar — preprocessing work
    ESCALATE_TO_TYPE     = "jnr_tech_log_analyzer"
    MODEL                = "claude-haiku-4-5-20251001"
    MAX_TOKENS           = 800   # Short tasks only

    async def _reason(self, task: Task, context: dict) -> tuple[dict, float, list[str]]:
        trace = [f"[{self.agent_id}] Preprocessing: {task.title}"]
        prompt = f"""Role: {self.SYSTEM_PROMPT}
Input: {task.description}
Data: {json.dumps(context, default=str)[:800]}

Process this data. Return JSON: {"result": "...", "flags": [], "confidence": 0.0}
JSON only, no commentary."""
        resp, conf = await self._llm(prompt)
        try:
            result = json.loads(resp)
        except Exception:
            result = {"result": resp[:400], "flags": ["parse_error"]}
            conf *= 0.5
        return result, result.get("confidence", conf), trace


def create_intern_class(type_key, dept, responsibility):
    return type(
        f"Intern_{type_key}",
        (InternAgent,),
        {
            "AGENT_ID_PREFIX": type_key,
            "AGENT_TYPE_KEY":  type_key,
            "DEPARTMENT":      dept,
            "SYSTEM_PROMPT":   f"Preprocessing specialist: {responsibility}",
        }
    )

_INTERN_DEFINITIONS = [
    ("int_html_stripper", "operations", "Strip HTML from crawled pages, extract clean text"),
    ("int_pdf_extractor", "operations", "Extract text from regulatory PDF documents"),
    ("int_table_extractor", "operations", "Extract tables from PDFs and HTML into structured JSON"),
    ("int_charset_normalizer", "operations", "Normalize character encodings to UTF-8"),
    ("int_whitespace_cleaner", "operations", "Clean whitespace, remove boilerplate, normalize text"),
    ("int_language_detector", "operations", "Detect language of source documents for routing"),
    ("int_length_calculator", "operations", "Calculate word/token counts for all source documents"),
    ("int_dedup_hasher", "operations", "Hash document content for deduplication comparison"),
    ("int_url_normalizer", "operations", "Normalize URLs: remove tracking params, standardize format"),
    ("int_date_parser", "operations", "Parse dates from multiple formats across locales"),
    ("int_currency_parser", "operations", "Parse currency amounts, normalize to USD equivalent"),
    ("int_entity_extractor_basic", "operations", "Extract basic named entities: org names, dates, amounts"),
    ("int_regex_extractor", "operations", "Apply regex patterns to extract structured fields"),
    ("int_line_splitter", "operations", "Split documents into logical sections"),
    ("int_section_identifier", "operations", "Identify document sections: preamble, operative, annexes"),
    ("int_acronym_expander", "operations", "Expand regulatory acronyms using standard glossary"),
    ("int_footnote_extractor", "operations", "Extract and link footnotes from regulatory documents"),
    ("int_attachment_handler", "operations", "Identify and log document attachments and annexures"),
    ("int_rss_parser", "operations", "Parse RSS/Atom feeds from regulatory publishers"),
    ("int_json_validator", "operations", "Validate all JSON outputs against expected schemas"),
    ("int_xml_parser", "operations", "Parse XML documents from regulatory APIs"),
    ("int_csv_processor", "operations", "Process CSV data files from regulatory bodies"),
    ("int_excel_processor", "operations", "Process Excel data files from financial regulators"),
    ("int_word_processor", "operations", "Process Word documents from regulatory bodies"),
    ("int_encoding_fixer", "operations", "Fix broken character encoding in scraped content"),
    ("int_mime_classifier", "operations", "Classify MIME types of downloaded documents"),
    ("int_page_counter", "operations", "Count pages in multi-page regulatory documents"),
    ("int_ocr_preprocessor", "operations", "Pre-process scanned PDFs before OCR"),
    ("int_image_describer", "operations", "Describe regulatory diagrams and charts in text"),
    ("int_link_checker", "operations", "Check all external links in regulatory documents"),
    ("int_broken_link_reporter", "operations", "Report broken source links for manual review"),
    ("int_canonical_setter", "operations", "Set canonical URLs for all alert pages"),
    ("int_slug_generator", "operations", "Generate URL slugs for all alert pages"),
    ("int_content_hasher", "operations", "Hash final content for change detection"),
    ("int_diff_calculator", "operations", "Calculate diffs when regulations are amended"),
    ("int_version_labeler", "operations", "Label document versions for amendment tracking"),
    ("int_source_ranker", "operations", "Rank source credibility based on publisher type"),
    ("int_freshness_checker", "operations", "Check if cached regulatory content needs refresh"),
    ("int_crawl_rate_limiter", "operations", "Enforce polite crawl rates per domain"),
    ("int_robots_checker", "operations", "Check robots.txt before crawling"),
    ("int_sitemap_parser", "operations", "Parse sitemaps to discover regulatory documents"),
    ("int_feed_aggregator", "operations", "Aggregate multiple feeds from same regulator"),
    ("int_batch_chunker", "operations", "Chunk large documents into LLM-compatible sizes"),
    ("int_token_estimator", "operations", "Estimate token counts before LLM API calls"),
    ("int_context_builder", "operations", "Build context packages for senior agents"),
    ("int_memory_summarizer", "operations", "Summarize memory entries to reduce context length"),
    ("int_embedding_calculator", "operations", "Calculate text embeddings for semantic search"),
    ("int_similarity_scorer", "operations", "Score document similarity for dedup and related alerts"),
    ("int_keyword_extractor", "operations", "Extract keywords using TF-IDF from document corpus"),
    ("int_category_mapper", "operations", "Map documents to taxonomy categories"),
    ("int_priority_estimator", "operations", "Pre-estimate alert priority before senior analysis"),
    ("int_sector_classifier", "operations", "Classify documents by affected sector"),
    ("int_jurisdiction_mapper", "operations", "Map source URL to jurisdiction code"),
    ("int_regulator_identifier", "operations", "Identify publishing regulator from source domain"),
    ("int_doc_type_classifier", "operations", "Classify document type: consultation/final rule/guidance"),
    ("int_urgency_classifier", "operations", "Classify urgency: immediate/near-term/long-term"),
    ("int_action_classifier", "operations", "Classify whether alert requires compliance action"),
    ("int_threshold_extractor", "operations", "Extract regulatory thresholds and limits"),
    ("int_deadline_classifier", "operations", "Classify deadline type: hard/soft/implementation"),
    ("int_penalty_extractor", "operations", "Extract penalty amounts and conditions"),
    ("int_scope_extractor", "operations", "Extract regulatory scope: which entities must comply"),
    ("int_exemption_extractor", "operations", "Extract regulatory exemptions and carve-outs"),
    ("int_definition_extractor", "operations", "Extract defined terms from regulatory documents"),
    ("int_cross_ref_extractor", "operations", "Extract cross-references to other regulations"),
    ("int_contact_extractor", "operations", "Extract regulatory contact information"),
    ("int_consultation_tracker", "operations", "Track open consultation periods and deadlines"),
    ("int_comment_extractor", "operations", "Extract public comment highlights from consultations"),
    ("int_amend_tracker", "operations", "Track amendments to existing regulations"),
    ("int_repeal_detector", "operations", "Detect when regulations are repealed or replaced"),
    ("int_consolidation_tracker", "operations", "Track regulation consolidations and mergers"),
    ("int_gazette_parser", "operations", "Parse government gazette publications"),
    ("int_hansard_parser", "operations", "Parse parliamentary Hansard for regulatory debates"),
    ("int_eu_oj_parser", "operations", "Parse EU Official Journal publications"),
    ("int_fr_parser", "operations", "Parse US Federal Register publications"),
    ("int_task_logger", "operations", "Log all task creations, completions, and failures"),
    ("int_event_logger", "operations", "Log all agent events to immutable audit store"),
    ("int_agent_logger", "operations", "Log agent lifecycle events: start, stop, errors"),
    ("int_api_logger", "operations", "Log all API requests: endpoint, user, response time"),
    ("int_error_logger", "operations", "Log all errors with full stack traces"),
    ("int_access_logger", "operations", "Log all user data access for GDPR compliance"),
    ("int_auth_logger", "operations", "Log all authentication events: login, logout, failures"),
    ("int_payment_logger", "operations", "Log all payment events: charges, refunds, disputes"),
    ("int_webhook_logger", "operations", "Log all incoming and outgoing webhooks"),
    ("int_email_logger", "operations", "Log all outbound emails for compliance purposes"),
    ("int_push_logger", "operations", "Log all push notification sends and deliveries"),
    ("int_search_logger", "operations", "Log all search queries for analytics"),
    ("int_alert_view_logger", "operations", "Log all alert page views with session context"),
    ("int_intel_view_logger", "operations", "Log all intelligence page views"),
    ("int_upgrade_logger", "operations", "Log all upgrade attempts and Stripe checkout events"),
    ("int_download_logger", "operations", "Log all PDF report downloads"),
    ("int_api_usage_logger", "operations", "Log all external API calls by agent type"),
    ("int_cost_logger", "operations", "Log all LLM API costs by agent and task"),
    ("int_perf_logger", "operations", "Log agent performance metrics: time, tokens, confidence"),
    ("int_escalation_logger", "operations", "Log all escalations with full context"),
    ("int_conflict_logger", "operations", "Log all agent conflicts requiring arbitration"),
    ("int_memory_access_logger", "operations", "Log all memory reads/writes for access auditing"),
    ("int_schema_change_logger", "operations", "Log all database schema changes"),
    ("int_config_change_logger", "operations", "Log all configuration changes"),
    ("int_deploy_logger", "operations", "Log all deployment events with version and diff"),
    ("int_incident_logger", "operations", "Log all operational incidents with timeline"),
    ("int_recovery_logger", "operations", "Log all recovery actions during incidents"),
    ("int_sla_logger", "operations", "Log SLA measurements for each service"),
    ("int_health_logger", "operations", "Log periodic health check results"),
    ("int_capacity_logger", "operations", "Log capacity utilization metrics hourly"),
    ("int_alert_quality_logger", "operations", "Log alert quality scores for trending analysis"),
    ("int_validation_logger", "operations", "Log validation pass/fail results by agent"),
    ("int_crawl_logger", "operations", "Log crawl attempts, successes, failures per source"),
    ("int_parse_logger", "operations", "Log parse success rates per document type"),
    ("int_dedup_logger", "operations", "Log deduplication decisions for audit"),
    ("int_publish_logger", "operations", "Log alert publication events with timestamp"),
    ("int_content_mod_logger", "operations", "Log all content moderation decisions"),
    ("int_fraud_event_logger", "operations", "Log all fraud detection events and actions"),
    ("int_dispute_logger", "operations", "Log customer disputes and resolutions"),
    ("int_gdpr_event_logger", "operations", "Log all GDPR-relevant data events"),
    ("int_consent_logger", "operations", "Log user consent changes with timestamp"),
    ("int_erasure_logger", "operations", "Log data erasure completions for GDPR compliance"),
    ("int_privacy_breach_logger", "operations", "Log privacy breaches with regulatory notification status"),
    ("int_security_event_logger", "operations", "Log security events: failed auth, port scans, etc."),
    ("int_vulnerability_logger", "operations", "Log discovered vulnerabilities and remediation status"),
    ("int_audit_trail_integrity", "operations", "Verify audit trail hash chain integrity"),
    ("int_log_archiver", "operations", "Archive old logs to S3 Glacier for retention"),
    ("int_log_compressor", "operations", "Compress logs for storage efficiency"),
    ("int_log_searchindexer", "operations", "Index log entries for fast search"),
    ("int_anomaly_pre_detector", "operations", "Pre-detect log anomalies before senior review"),
    ("int_pattern_counter", "operations", "Count patterns in logs for statistical reporting"),
    ("int_metric_aggregator", "operations", "Aggregate raw metrics into time-series summaries"),
    ("int_report_data_collector", "operations", "Collect raw data for scheduled reports"),
    ("int_dashboard_data_prep", "operations", "Prepare data for dashboard widgets"),
    ("int_kpi_calculator_basic", "operations", "Calculate basic KPI values from raw data"),
    ("int_alert_counter", "operations", "Count alerts by type, jurisdiction, severity daily"),
    ("int_user_counter", "operations", "Count active users by plan and period"),
    ("int_revenue_aggregator", "operations", "Aggregate daily revenue from Stripe events"),
    ("int_churn_identifier", "operations", "Identify churned subscriptions for reporting"),
    ("int_mrr_calculator", "operations", "Calculate MRR from current subscription data"),
    ("int_csat_aggregator", "operations", "Aggregate CSAT scores from feedback submissions"),
    ("int_nps_aggregator", "operations", "Aggregate NPS responses by segment"),
    ("int_ticket_counter", "operations", "Count support tickets by category and status"),
    ("int_response_timer", "operations", "Measure support response times vs SLA"),
    ("int_uptime_recorder", "operations", "Record uptime measurements per service endpoint"),
    ("int_latency_recorder", "operations", "Record API response time percentiles"),
    ("int_throughput_recorder", "operations", "Record agent task throughput by hour"),
    ("int_error_rate_tracker", "operations", "Track error rates by endpoint and agent type"),
    ("int_token_counter_total", "operations", "Count total tokens consumed across all agents"),
    ("int_cost_aggregator_ai", "operations", "Aggregate AI API costs by department"),
    ("int_storage_tracker", "operations", "Track storage usage by S3 bucket and type"),
    ("int_memory_summarizer2", "operations", "Condense long task histories for senior agents"),
    ("int_context_compressor", "operations", "Compress context windows without losing key facts"),
    ("int_key_point_extractor", "operations", "Extract key points from long regulatory documents"),
    ("int_bullet_summarizer", "operations", "Convert prose summaries to concise bullet points"),
    ("int_exec_summary_writer", "operations", "Write 2-sentence executive summaries of alerts"),
    ("int_detail_summarizer", "operations", "Summarize detailed regulatory requirements"),
    ("int_comparison_summarizer", "operations", "Summarize differences between two versions of a regulation"),
    ("int_consultation_summarizer", "operations", "Summarize consultation responses and themes"),
    ("int_market_reaction_summarizer", "operations", "Summarize industry and analyst reactions to regulations"),
    ("int_impact_summarizer", "operations", "Summarize financial and operational impact estimates"),
    ("int_timeline_summarizer", "operations", "Summarize regulatory implementation timeline"),
    ("int_obligation_summarizer", "operations", "Summarize compliance obligations from regulations"),
    ("int_exception_summarizer", "operations", "Summarize exceptions and carve-outs in regulations"),
    ("int_penalty_summarizer", "operations", "Summarize penalty regime for non-compliance"),
    ("int_action_summarizer", "operations", "Summarize required actions for compliance"),
    ("int_digest_assembler", "operations", "Assemble daily digest from processed alert summaries"),
    ("int_trend_aggregator", "operations", "Aggregate trending signals for trending agent"),
    ("int_intel_brief_writer", "operations", "Write brief intelligence summaries for daily briefing"),
    ("int_report_section_writer", "operations", "Write data-driven sections of monthly reports"),
    ("int_weekly_roundup", "operations", "Compile weekly regulatory roundup for newsletter"),
    ("int_country_briefer", "operations", "Write country-specific regulatory briefings"),
    ("int_sector_briefer", "operations", "Write sector-specific regulatory briefings"),
    ("int_regulator_profiler", "operations", "Maintain profiles of key regulatory bodies"),
    ("int_enforcement_tracker", "operations", "Track enforcement actions and fine amounts"),
    ("int_consultation_tracker2", "operations", "Track open regulatory consultations and close dates"),
    ("int_enforcement_summarizer", "operations", "Summarize enforcement action patterns and trends"),
    ("int_faq_writer", "operations", "Write FAQ answers for regulatory updates"),
    ("int_explainer_writer", "operations", "Write plain-English explainers for complex regulations"),
    ("int_checklist_writer", "operations", "Convert regulatory requirements into compliance checklists"),
    ("int_template_filler", "operations", "Fill document templates with regulatory data"),
    ("int_form_extractor", "operations", "Extract and catalogue regulatory filing forms"),
    ("int_filing_guide_writer", "operations", "Write filing guides for regulatory forms"),
    ("int_calendar_entry_writer", "operations", "Write compliance calendar entries from alert data"),
    ("int_reminder_writer", "operations", "Write deadline reminder notifications"),
    ("int_pre_categorizer", "operations", "Pre-categorize alerts before senior review"),
    ("int_tag_suggester", "operations", "Suggest topic tags for senior agent approval"),
    ("int_severity_pre_scorer", "operations", "Pre-score severity before senior validation"),
    ("int_impact_pre_scorer", "operations", "Pre-score impact before senior validation"),
    ("int_sector_pre_tagger", "operations", "Pre-tag sectors before senior validation"),
    ("int_seo_title_generator", "operations", "Generate SEO title options for senior selection"),
    ("int_meta_desc_generator", "operations", "Generate meta description options"),
    ("int_social_copy_generator", "operations", "Generate social share copy for alert pages"),
    ("int_email_subject_generator", "operations", "Generate email subject line options"),
    ("int_push_title_generator", "operations", "Generate push notification title options"),
    ("int_headline_ranker", "operations", "Rank headline options by clarity and SEO"),
    ("int_readability_scorer", "operations", "Calculate Flesch-Kincaid readability scores"),
    ("int_word_count_enforcer", "operations", "Enforce word count limits on summaries"),
    ("int_duplicate_phrase_detector", "operations", "Detect repeated phrases in AI-generated content"),
    ("int_passive_voice_detector", "operations", "Flag excessive passive voice in regulatory summaries"),
    ("int_jargon_scorer", "operations", "Score technical jargon density for readability"),
    ("int_source_verifier", "operations", "Verify source URL is still accessible"),
    ("int_publication_date_verifier", "operations", "Verify publication dates against source"),
    ("int_regulator_name_verifier", "operations", "Verify regulator names against master list"),
    ("int_jurisdiction_verifier", "operations", "Verify jurisdiction codes against ISO standard"),
    ("int_link_validator", "operations", "Validate all hyperlinks in published alerts"),
    ("int_citation_formatter", "operations", "Format regulatory citations consistently"),
    ("int_doc_formatter", "operations", "Apply consistent formatting to processed documents"),
    ("int_content_classifier", "operations", "Classify content type: rule/guidance/enforcement"),
    ("int_alert_status_checker", "operations", "Check if published alerts need status updates"),
    ("int_stale_content_detector", "operations", "Detect stale content that needs updating"),
    ("int_change_notifier", "operations", "Notify when regulations are amended or superseded"),
    ("int_sunset_tracker", "operations", "Track regulations approaching sunset dates"),
    ("int_transition_tracker", "operations", "Track regulatory transition period progress"),
    ("int_cascade_pre_analyzer", "operations", "Pre-analyze cascade effects before full analysis"),
    ("int_dependency_mapper", "operations", "Map regulatory dependencies and cross-references"),
    ("int_impact_cross_checker", "operations", "Cross-check impact scores for consistency"),
    ("int_tag_deduplicator", "operations", "Remove duplicate tags from alert records"),
    ("int_schema_enforcer", "operations", "Enforce data schema consistency across all records"),
    ("int_null_filler", "operations", "Fill null fields with defaults where appropriate"),
    ("int_format_standardizer", "operations", "Standardize date/currency formats across records"),
    ("int_batch_validator", "operations", "Validate batches of records before database insert"),
    ("int_integrity_checker", "operations", "Check referential integrity of database records"),
    ("int_orphan_detector", "operations", "Detect orphaned records with no parent alert"),
    ("int_archive_preparer", "operations", "Prepare old records for cold storage archiving"),
]

INTERN_REGISTRY: dict[str, type] = {
    type_key: create_intern_class(type_key, dept, resp)
    for type_key, dept, resp in _INTERN_DEFINITIONS
}
print(f"Intern agents registered: {len(INTERN_REGISTRY)}")
