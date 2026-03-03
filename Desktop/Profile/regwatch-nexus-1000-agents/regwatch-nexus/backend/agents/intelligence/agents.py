"""
RegWatch Nexus — Intelligence Division Agents

The engine room of RegWatch Nexus.
Implements 6 tiers of intelligence processing:

  Intern:   Document crawlers, text extractors, format parsers
  Junior:   Jurisdiction classifiers, date extractors, dedup
  Senior:   Deep content analysts, impact scorers, sector mappers
  Director: Domain orchestrators (India, UK/EU, US, APAC, etc.)
  VP:       Division heads (Crawling, Analysis, Synthesis, QA)
  CSO:      Chief Intelligence Officer
"""
from __future__ import annotations
import asyncio
import json
import re
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from ..framework.base import (
    AgentBase, AgentSpec, Task, TaskStatus,
    MemoryScope, EventType, AutonomyLevel
)
from ..framework.communication import AuditLogger

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# INTERN LAYER — Specialised crawling workers
# ─────────────────────────────────────────────

class RegulatoryDocumentCrawler(AgentBase):
    """
    AGT-INT-INT-001 to AGT-INT-INT-150 (when specialization = Regulatory Document Crawler)

    Fetches a single URL and extracts raw text content.
    No LLM calls — pure I/O.
    """

    async def execute_task(self, task: Task) -> Task:
        url = task.metadata.get("url")
        if not url:
            task.reasoning_trace.append("No URL provided")
            task.confidence_score = 0.0
            return task

        task.reasoning_trace.append(f"Crawling: {url}")

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "RegWatch-Bot/7.0 (+https://regwatchnexus.com/bot)"
                })
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            raw_text = resp.text

            task.result = {
                "url": url,
                "status_code": resp.status_code,
                "content_type": content_type,
                "raw_text": raw_text[:50_000],  # cap at 50k chars
                "content_length": len(raw_text),
                "crawled_at": datetime.now(timezone.utc).isoformat(),
            }
            task.confidence_score = 0.95
            task.reasoning_trace.append(f"Crawled OK: {len(raw_text):,} chars")

        except httpx.TimeoutException:
            task.reasoning_trace.append(f"Timeout fetching {url}")
            task.confidence_score = 0.1
            task.result = {"error": "timeout", "url": url}

        except httpx.HTTPStatusError as e:
            task.reasoning_trace.append(f"HTTP {e.response.status_code} for {url}")
            task.confidence_score = 0.1
            task.result = {"error": f"http_{e.response.status_code}", "url": url}

        except Exception as e:
            task.reasoning_trace.append(f"Crawl exception: {str(e)[:100]}")
            task.confidence_score = 0.05
            task.result = {"error": str(e), "url": url}

        return task


class DuplicateDetector(AgentBase):
    """
    Checks if an alert title+content has already been processed.
    Uses simple hash-based deduplication (swap for vector similarity in prod).
    """

    async def execute_task(self, task: Task) -> Task:
        title = task.metadata.get("title", "")
        content = task.metadata.get("content", "")
        source_url = task.metadata.get("source_url", "")

        # Hash-based check
        import hashlib
        content_hash = hashlib.md5(f"{title}{content[:500]}".encode()).hexdigest()

        cached = await self.memory_read(f"dedup:{content_hash}", MemoryScope.DEPARTMENT)
        is_duplicate = cached is not None

        if not is_duplicate:
            await self.memory_write(
                f"dedup:{content_hash}",
                {"url": source_url, "title": title[:100]},
                MemoryScope.DEPARTMENT,
                ttl=86400 * 30,  # 30 days
            )

        task.result = {"is_duplicate": is_duplicate, "content_hash": content_hash}
        task.confidence_score = 0.99
        task.reasoning_trace.append(f"Duplicate check: {'DUPLICATE' if is_duplicate else 'NEW'}")
        return task


class LanguageDetector(AgentBase):
    """Detect the language of regulatory text for translation routing."""

    LANG_PATTERNS = {
        "en": re.compile(r'\b(the|and|of|to|in|regulatory|compliance|financial)\b', re.I),
        "hi": re.compile(r'[\u0900-\u097F]'),
        "ar": re.compile(r'[\u0600-\u06FF]'),
        "de": re.compile(r'\b(und|die|der|das|Regulierung|Compliance)\b'),
        "fr": re.compile(r'\b(et|le|la|les|réglementation|conformité)\b'),
        "zh": re.compile(r'[\u4e00-\u9fff]'),
        "ja": re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]'),
    }

    async def execute_task(self, task: Task) -> Task:
        text = task.metadata.get("text", "")
        scores = {}
        for lang, pattern in self.LANG_PATTERNS.items():
            matches = len(pattern.findall(text[:2000]))
            scores[lang] = matches

        detected = max(scores, key=scores.get) if scores else "en"
        task.result = {"language": detected, "scores": scores}
        task.confidence_score = 0.88
        task.reasoning_trace.append(f"Language detected: {detected}")
        return task


class JurisdictionClassifier(AgentBase):
    """Classify which jurisdiction(s) a regulatory document belongs to."""

    JURISDICTION_SIGNALS = {
        "IN": ["RBI", "SEBI", "IRDAI", "India", "rupee", "INR", "DPDP", "PFRDA", "MCA"],
        "GB": ["FCA", "PRA", "Bank of England", "United Kingdom", "UK", "sterling", "GBP", "Consumer Duty"],
        "US": ["SEC", "CFTC", "Federal Reserve", "OCC", "CFPB", "FDIC", "United States", "USD"],
        "EU": ["EBA", "ECB", "ESMA", "EIOPA", "European Union", "euro", "DORA", "MiCA", "GDPR"],
        "SG": ["MAS", "Singapore", "SGD", "Monetary Authority of Singapore"],
        "HK": ["HKMA", "Hong Kong", "SFC", "HKD"],
        "AU": ["APRA", "ASIC", "Australia", "AUD"],
        "AE": ["CBUAE", "SCA", "FSRA", "UAE", "Abu Dhabi", "Dubai", "ADGM", "DIFC"],
        "CA": ["OSFI", "Canada", "CAD", "Canadian"],
        "JP": ["FSA", "Japan", "JPY", "Bank of Japan"],
        "ZA": ["SARB", "FSCA", "South Africa", "ZAR"],
        "NG": ["CBN", "SEC", "Nigeria", "naira"],
        "BR": ["BCB", "CVM", "Brazil", "BRL", "Banco Central"],
        "GLOBAL": ["BIS", "FATF", "IOSCO", "FSB", "Basel", "G20", "IMF"],
    }

    async def execute_task(self, task: Task) -> Task:
        text = task.metadata.get("text", "")[:5000]
        title = task.metadata.get("title", "")

        combined = f"{title} {text}"
        scores = {}
        for jurisdiction, signals in self.JURISDICTION_SIGNALS.items():
            score = sum(1 for s in signals if s.lower() in combined.lower())
            if score > 0:
                scores[jurisdiction] = score

        if not scores:
            detected = "GLOBAL"
            conf = 0.5
        else:
            primary = max(scores, key=scores.get)
            detected = primary
            conf = min(0.95, 0.5 + scores[primary] * 0.1)

        task.result = {
            "primary_jurisdiction": detected,
            "all_jurisdictions": list(scores.keys()),
            "scores": scores,
        }
        task.confidence_score = conf
        task.reasoning_trace.append(f"Jurisdiction: {detected} (conf={conf:.2f})")
        return task


# ─────────────────────────────────────────────
# JUNIOR LAYER — Structured extraction
# ─────────────────────────────────────────────

class DeadlineExtractor(AgentBase):
    """Extract regulatory deadlines from document text using LLM."""

    async def execute_task(self, task: Task) -> Task:
        text = task.metadata.get("text", "")[:8000]
        title = task.metadata.get("title", "")

        result, conf = await self.llm_json(
            system="""You are a regulatory deadline extraction specialist.
Extract all compliance deadlines from regulatory text.
Return ONLY dates that represent action required by financial firms.
Be precise about the date format.""",
            user=f"""TITLE: {title}

TEXT: {text}

Extract all regulatory deadlines:
{{
  "deadlines": [
    {{
      "date": "DD MONTH YYYY",
      "description": "What must be completed by this date",
      "obligation_type": "mandatory|advisory|consultation_close",
      "urgency": "critical|high|medium|low"
    }}
  ],
  "primary_deadline": "DD MONTH YYYY or null",
  "has_deadlines": true/false
}}""",
        )

        task.result = result
        task.confidence_score = conf
        task.reasoning_trace.append(f"Extracted {len((result or {}).get('deadlines', []))} deadlines")
        return task


class TopicTagExtractor(AgentBase):
    """Extract topic tags for alert categorisation."""

    KNOWN_TOPICS = [
        "KYC", "AML", "BSA", "FATF", "Sanctions", "PEP", "CTF",
        "Capital", "Basel III", "Basel IV", "CRR", "CRD",
        "Liquidity", "LCR", "NSFR", "Stress Testing", "ILAAP", "ICAAP",
        "Consumer Duty", "Consumer Protection", "Conduct",
        "ESG", "Climate Risk", "Sustainable Finance", "TCFD",
        "GDPR", "DPDP", "Data Privacy", "DORA", "ICT Risk",
        "Crypto", "DeFi", "Stablecoin", "CBDC", "DPT", "MiCA",
        "Open Banking", "PSD2", "API Standards",
        "Payments", "Instant Payments", "SWIFT",
        "Fintech", "Regtech", "Suptech",
        "Market Abuse", "Insider Trading", "MiFID", "EMIR",
        "Insurance", "Solvency II", "IAIS",
        "Pension", "Retirement", "IORP",
        "AI Risk", "Model Risk", "Algorithmic Trading",
        "Systemic Risk", "SIFI", "GSIB", "Recovery Resolution",
    ]

    async def execute_task(self, task: Task) -> Task:
        text = task.metadata.get("text", "")[:3000]
        title = task.metadata.get("title", "")
        combined = f"{title} {text}"

        # Fast pattern matching (no LLM needed for this)
        matched = []
        for tag in self.KNOWN_TOPICS:
            if tag.lower() in combined.lower():
                matched.append(tag)

        # LLM for additional tags not in the known list
        if len(matched) < 3:
            result, conf = await self.llm_json(
                system="Extract 3-8 topic tags for this regulatory alert. Use standard regulatory terminology.",
                user=f"TITLE: {title}\n\nCONTENT: {text[:2000]}\n\nReturn: {{\"tags\": [\"tag1\", \"tag2\", ...]}}",
            )
            llm_tags = (result or {}).get("tags", [])
            matched.extend([t for t in llm_tags if t not in matched])

        task.result = {"topic_tags": matched[:10]}
        task.confidence_score = 0.88
        task.reasoning_trace.append(f"Extracted {len(matched)} topic tags")
        return task


class SectorMapper(AgentBase):
    """Map regulatory content to affected financial sectors."""

    SECTOR_MAP = {
        "Banking": ["bank", "lending", "credit", "deposit", "overdraft", "mortgage", "loan"],
        "Investment": ["asset management", "fund", "UCITS", "AIF", "portfolio", "securities", "MiFID"],
        "Insurance": ["insurer", "underwriting", "premium", "solvency", "IAIS", "actuarial"],
        "Payments": ["payment", "PSP", "e-money", "acquiring", "clearing", "settlement"],
        "Fintech": ["fintech", "regtech", "neobank", "digital bank", "challenger", "startup"],
        "Crypto": ["crypto", "blockchain", "token", "DeFi", "exchange", "wallet", "NFT", "CBDC"],
        "Capital Markets": ["exchange", "broker", "dealer", "trading", "derivatives", "futures"],
        "Consumer Finance": ["consumer credit", "BNPL", "car finance", "personal loan"],
        "Pension": ["pension", "retirement", "occupational", "SIPP", "DC", "DB"],
        "Wealth Management": ["wealth", "HNW", "discretionary", "advisory", "private banking"],
    }

    async def execute_task(self, task: Task) -> Task:
        text = (task.metadata.get("text", "") + " " + task.metadata.get("title", "")).lower()

        sectors = []
        for sector, keywords in self.SECTOR_MAP.items():
            if any(kw.lower() in text for kw in keywords):
                sectors.append(sector)

        task.result = {"affected_sectors": sectors or ["Financial Services"]}
        task.confidence_score = 0.85
        task.reasoning_trace.append(f"Sectors: {sectors}")
        return task


# ─────────────────────────────────────────────
# SENIOR LAYER — Deep LLM analysis
# ─────────────────────────────────────────────

class RegulatoryAnalyst(AgentBase):
    """
    Senior regulatory analyst — produces full alert analysis.
    Powers: alert summary, full_analysis, recommended_actions.
    This is the primary content generation agent.
    """

    ANALYST_SYSTEM = """You are a senior regulatory analyst at RegWatch Nexus.

You specialise in translating complex regulatory documents into actionable intelligence for compliance teams, fintechs, and banks.

Your analysis must be:
1. ACCURATE — only state what the document actually says
2. ACTIONABLE — include specific steps compliance teams must take
3. PROPORTIONATE — severity reflects actual regulatory risk
4. STRUCTURED — use consistent output format

Severity guide:
- critical: >90 days compliance timeline or existential risk
- high: 90-180 day timeline, significant operational change required
- medium: 6-12 months, moderate adaptation
- info: guidance only, no hard deadlines

Impact score (0-10): reflects compliance burden × jurisdiction breadth × sector coverage"""

    async def execute_task(self, task: Task) -> Task:
        raw_text = task.metadata.get("raw_text", "")[:15000]
        title = task.metadata.get("title", raw_text[:100])
        jurisdiction = task.metadata.get("jurisdiction", "GLOBAL")
        source_url = task.metadata.get("source_url", "")
        regulator = task.metadata.get("regulator", "Unknown Regulator")

        task.reasoning_trace.append(f"Analysing: {title[:80]}...")

        result, conf = await self.llm_json(
            system=self.ANALYST_SYSTEM,
            user=f"""Analyse this regulatory document and produce structured intelligence.

REGULATOR: {regulator}
JURISDICTION: {jurisdiction}
SOURCE: {source_url}
TITLE: {title}

DOCUMENT:
{raw_text}

Return JSON:
{{
  "title": "Clear, professional title (max 120 chars)",
  "summary": "3-4 paragraph public summary. Explain what changed, who is affected, what the timeline is.",
  "full_analysis": "8-10 paragraph deep analysis covering: regulatory context, technical requirements, implementation challenges, sector-specific impacts, comparison with existing rules, enforcement approach, strategic implications.",
  "severity": "critical|high|medium|info",
  "base_impact_score": 7.5,
  "affected_sectors": ["Banking", "Fintech"],
  "topic_tags": ["KYC", "AML"],
  "regulatory_deadline": "DD MONTH YYYY or null",
  "recommended_actions": {{
    "immediate_0_30_days": ["Action 1", "Action 2"],
    "short_term_31_90_days": ["Action 3"],
    "medium_term_91_180_days": ["Action 4"],
    "ongoing": ["Action 5"]
  }},
  "cascade_predictions": [
    {{"jurisdiction": "XX", "prediction": "...", "probability": 0.7}}
  ],
  "seo_meta": {{
    "meta_title": "...",
    "meta_description": "...",
    "h1": "..."
  }},
  "confidence_notes": "Any limitations in the analysis"
}}""",
            model="claude-sonnet-4-6",
            max_tokens=4000,
        )

        if not result:
            task.reasoning_trace.append("Analysis failed — empty LLM response")
            task.confidence_score = 0.2
            return task

        task.result = result
        task.confidence_score = conf
        task.reasoning_trace.append(f"Analysis complete: severity={result.get('severity')}, score={result.get('base_impact_score')}")

        # Cache in department memory for synthesis
        if result.get("title"):
            await self.memory_write(
                f"alert_analysis:{task.task_id}",
                {"title": result["title"], "severity": result.get("severity"), "jurisdiction": jurisdiction},
                MemoryScope.DEPARTMENT,
                ttl=3600 * 48,
            )

        return task


class ImpactScorer(AgentBase):
    """
    Calculates personalised impact scores for Pro clients.
    Takes base analysis + client profile → personalised score.
    """

    async def execute_task(self, task: Task) -> Task:
        alert_data = task.metadata.get("alert_data", {})
        client_profile = task.metadata.get("client_profile", {})

        base_score = float(alert_data.get("base_impact_score", 5.0))
        client_country = client_profile.get("primary_country", "")
        client_sectors = client_profile.get("products", [])
        client_jurisdictions = client_profile.get("active_countries", [])

        # Jurisdiction overlap boost
        alert_jurisdiction = alert_data.get("jurisdiction", "")
        if alert_jurisdiction in client_jurisdictions or alert_jurisdiction == client_country:
            jurisdiction_multiplier = 1.3
        else:
            jurisdiction_multiplier = 0.7

        # Sector overlap boost
        affected_sectors = alert_data.get("affected_sectors", [])
        sector_overlap = len(set(client_sectors) & set(affected_sectors))
        sector_multiplier = 1.0 + (sector_overlap * 0.15)

        personalised_score = min(10.0, base_score * jurisdiction_multiplier * sector_multiplier)

        result, conf = await self.llm_json(
            system="You are a compliance impact analyst. Calculate financial and operational exposure.",
            user=f"""Alert: {alert_data.get('title')}
Base score: {base_score}
Client sectors: {client_sectors}
Client jurisdictions: {client_jurisdictions}
Affected sectors: {affected_sectors}

Return:
{{
  "client_impact_score": {personalised_score:.1f},
  "financial_exposure_gbp": 0,
  "engineering_weeks_estimate": 0,
  "key_gaps": ["Gap 1", "Gap 2"],
  "personalised_summary": "How this specifically affects this client type"
}}""",
        )

        task.result = result or {
            "client_impact_score": round(personalised_score, 1),
            "financial_exposure_gbp": 0,
            "engineering_weeks_estimate": 0,
            "key_gaps": [],
            "personalised_summary": "Impact assessment pending full analysis",
        }
        task.confidence_score = conf
        return task


class CrossAlertSynthesizer(AgentBase):
    """
    Identifies patterns and relationships across multiple recent alerts.
    Used by VP Knowledge Synthesis to produce insight synthesis.
    """

    async def execute_task(self, task: Task) -> Task:
        alerts = task.metadata.get("alerts", [])  # list of alert dicts
        jurisdiction_filter = task.metadata.get("jurisdiction", "")
        topic_filter = task.metadata.get("topic", "")

        if len(alerts) < 2:
            task.result = {"patterns": [], "synthesis": "Insufficient data for synthesis"}
            task.confidence_score = 0.3
            return task

        # Build context
        alert_summaries = []
        for a in alerts[:20]:  # Cap at 20
            alert_summaries.append(f"- [{a.get('jurisdiction')}] {a.get('title')}: {a.get('summary', '')[:200]}")

        synthesis, conf = await self.llm_json(
            system="""You are a regulatory intelligence synthesizer.
Identify patterns, correlations, and strategic trends across multiple regulatory developments.
Focus on: regulatory convergence, enforcement waves, sector-specific tightening, geographic spread.""",
            user=f"""Synthesise these {len(alerts)} recent regulatory developments:

{chr(10).join(alert_summaries)}

JURISDICTION FOCUS: {jurisdiction_filter or 'Global'}
TOPIC FOCUS: {topic_filter or 'All topics'}

Return:
{{
  "key_themes": ["Theme 1", "Theme 2"],
  "regulatory_convergence": "Are jurisdictions aligning? How?",
  "enforcement_signals": "What enforcement patterns are emerging?",
  "geographic_spread": "How is this spreading across jurisdictions?",
  "sector_implications": {{"Banking": "...", "Fintech": "..."}},
  "predictions": [
    {{"jurisdiction": "XX", "prediction": "...", "probability": 0.75, "timeframe": "Q1 2026"}}
  ],
  "synthesis_narrative": "500-word synthesis for intelligence report",
  "confidence": 0.85
}}""",
            model="claude-sonnet-4-6",
            max_tokens=2000,
        )

        task.result = synthesis
        task.confidence_score = (synthesis or {}).get("confidence", conf)
        task.reasoning_trace.append(f"Synthesised {len(alerts)} alerts — {len((synthesis or {}).get('key_themes', []))} themes found")
        return task


# ─────────────────────────────────────────────
# DIRECTOR LAYER — Domain orchestrators
# ─────────────────────────────────────────────

class RegionDirector(AgentBase):
    """
    Director-tier agent overseeing all crawling + analysis for a geographic region.
    E.g., AGT-INT-DIR-001 (India), AGT-INT-DIR-002 (UK/EU), etc.

    Responsibilities:
    1. Schedule crawl tasks for all sources in region
    2. Route raw content to appropriate interns
    3. Orchestrate analysis pipeline for completed crawls
    4. Report region health to VP
    """

    async def execute_task(self, task: Task) -> Task:
        if task.task_type == "orchestrate_region_crawl":
            return await self._orchestrate_crawl(task)
        elif task.task_type == "region_health_report":
            return await self._health_report(task)
        elif task.task_type == "prioritise_sources":
            return await self._prioritise_sources(task)
        else:
            task.reasoning_trace.append(f"Unknown task type: {task.task_type}")
            task.confidence_score = 0.3
            return task

    async def _orchestrate_crawl(self, task: Task) -> Task:
        sources = task.metadata.get("sources", [])
        region = task.metadata.get("region", "GLOBAL")

        task.reasoning_trace.append(f"Orchestrating crawl for {region}: {len(sources)} sources")

        # Spawn intern tasks for each source
        spawned = 0
        for source in sources:
            crawl_task = Task(
                title=f"Crawl: {source.get('name', source.get('url', 'unknown'))}",
                task_type="crawl_url",
                priority=source.get("priority", 5),
                assigned_agent=f"AGT-INT-INT-{(spawned % 150) + 1:03d}",  # Round-robin across interns
                parent_task_id=task.task_id,
                metadata={
                    "url": source.get("url"),
                    "regulator": source.get("name"),
                    "jurisdiction": source.get("jurisdiction", region),
                    "source_type": source.get("type", "webpage"),
                }
            )
            if self._task_queue:
                await self._task_queue.enqueue(crawl_task)
            spawned += 1

        task.result = {"spawned_crawl_tasks": spawned, "region": region}
        task.confidence_score = 0.92
        task.reasoning_trace.append(f"Spawned {spawned} crawl tasks")
        return task

    async def _health_report(self, task: Task) -> Task:
        region = task.metadata.get("region", "UNKNOWN")
        ctx = await self.memory_read(f"crawl_results_{region}", MemoryScope.DEPARTMENT)

        task.result = {
            "region": region,
            "last_crawl": ctx.get("timestamp") if ctx else None,
            "sources_ok": ctx.get("ok", 0) if ctx else 0,
            "sources_failed": ctx.get("failed", 0) if ctx else 0,
            "alerts_generated": ctx.get("alerts", 0) if ctx else 0,
        }
        task.confidence_score = 0.90
        return task

    async def _prioritise_sources(self, task: Task) -> Task:
        sources = task.metadata.get("sources", [])
        result, conf = await self.llm_json(
            system="You are a regulatory source prioritisation expert. Rank sources by: alert frequency, regulatory significance, update velocity, sector coverage.",
            user=f"""Prioritise these {len(sources)} regulatory sources for crawling frequency:

SOURCES: {json.dumps(sources[:30])}

Return:
{{
  "high_frequency": ["source_id list — crawl every 4h"],
  "medium_frequency": ["source_id list — crawl every 12h"],
  "low_frequency": ["source_id list — crawl daily"],
  "reasoning": "..."
}}"""
        )
        task.result = result
        task.confidence_score = conf
        return task


# ─────────────────────────────────────────────
# VP LAYER — Division head orchestrators
# ─────────────────────────────────────────────

class VPRegulatoryIntelligence(AgentBase):
    """
    VP overseeing the entire regulatory intelligence pipeline.
    Coordinates 5 Director-level crawl region agents.
    """

    async def execute_task(self, task: Task) -> Task:
        if task.task_type == "daily_intelligence_cycle":
            return await self._run_daily_cycle(task)
        elif task.task_type == "intelligence_briefing":
            return await self._produce_briefing(task)
        else:
            task.reasoning_trace.append(f"VP delegating task: {task.task_type}")
            task.confidence_score = 0.5
            return task

    async def _run_daily_cycle(self, task: Task) -> Task:
        """Orchestrate the complete daily intelligence gathering cycle."""
        task.reasoning_trace.append("Starting daily intelligence cycle")

        # Import sources from the sources config
        from ...sources.regulatory_sources import REGULATORY_SOURCES
        # Group by region
        regions = {}
        for src in REGULATORY_SOURCES:
            region = src.get("jurisdiction", "GLOBAL")
            regions.setdefault(region, []).append(src)

        # Spawn regional orchestration tasks
        spawned = 0
        director_region_map = {
            "IN": "AGT-INT-DIR-001",
            "GB": "AGT-INT-DIR-002",
            "EU": "AGT-INT-DIR-002",
            "US": "AGT-INT-DIR-003",
            "SG": "AGT-INT-DIR-004",
            "HK": "AGT-INT-DIR-004",
            "AU": "AGT-INT-DIR-004",
        }

        for jurisdiction, sources in regions.items():
            director_id = director_region_map.get(jurisdiction, "AGT-INT-DIR-005")
            regional_task = Task(
                title=f"Crawl cycle: {jurisdiction} ({len(sources)} sources)",
                task_type="orchestrate_region_crawl",
                priority=3,
                assigned_agent=director_id,
                parent_task_id=task.task_id,
                metadata={"sources": sources, "region": jurisdiction}
            )
            if self._task_queue:
                await self._task_queue.enqueue(regional_task)
            spawned += 1

        task.result = {"cycle": "daily", "regions_dispatched": spawned}
        task.confidence_score = 0.93
        task.reasoning_trace.append(f"Daily cycle dispatched to {spawned} regional directors")
        return task

    async def _produce_briefing(self, task: Task) -> Task:
        """Generate intelligence briefing for CSO / executive layer."""
        ctx = await self.memory_read("daily_intelligence_summary", MemoryScope.DEPARTMENT)

        briefing, conf = await self.llm_json(
            system="Generate executive intelligence briefing. Focus on highest-impact developments.",
            user=f"""AVAILABLE CONTEXT: {json.dumps(ctx or {})}
PERIOD: {task.metadata.get('period', 'today')}

Return:
{{
  "total_alerts_processed": 0,
  "critical_count": 0,
  "high_count": 0,
  "top_3_alerts": [
    {{"title": "...", "jurisdiction": "...", "severity": "...", "impact_score": 0.0}}
  ],
  "key_themes": ["..."],
  "coverage_gaps": ["..."],
  "quality_score": 0.90
}}"""
        )
        task.result = briefing
        task.confidence_score = conf
        return task


class VPAlertAnalysis(AgentBase):
    """
    VP overseeing all alert analysis — from raw text to published intelligence.
    Manages 3 Director agents: Impact Analysis, Compliance Analysis, Timeline Analysis.
    """

    async def execute_task(self, task: Task) -> Task:
        if task.task_type == "analyse_document":
            return await self._route_to_analyst(task)
        elif task.task_type == "quality_gate":
            return await self._quality_gate(task)
        else:
            task.confidence_score = 0.5
            return task

    async def _route_to_analyst(self, task: Task) -> Task:
        """Route a raw document to the appropriate analyst chain."""
        raw_text = task.metadata.get("raw_text", "")
        jurisdiction = task.metadata.get("jurisdiction", "GLOBAL")

        # Phase 1: Spawn intern tasks (jurisdiction, topic, sector)
        analysis_task = Task(
            title=f"Analyse: {task.metadata.get('title', 'Document')[:80]}",
            task_type="deep_regulatory_analysis",
            priority=2,
            assigned_agent="AGT-INT-SEN-001",  # Lead analyst
            parent_task_id=task.task_id,
            metadata=task.metadata,
        )
        if self._task_queue:
            await self._task_queue.enqueue(analysis_task)

        task.result = {"routed_to_analysis": True, "analysis_task": analysis_task.task_id}
        task.confidence_score = 0.90
        return task

    async def _quality_gate(self, task: Task) -> Task:
        """Validate alert quality before publication."""
        alert = task.metadata.get("alert", {})

        issues = []
        if not alert.get("title"):
            issues.append("Missing title")
        if not alert.get("summary") or len(alert.get("summary", "")) < 100:
            issues.append("Summary too short")
        if not alert.get("severity"):
            issues.append("Missing severity")
        if not alert.get("jurisdiction"):
            issues.append("Missing jurisdiction")
        if not alert.get("regulator"):
            issues.append("Missing regulator")

        passes = len(issues) == 0
        task.result = {
            "passes_quality_gate": passes,
            "issues": issues,
            "alert_id": alert.get("id"),
        }
        task.confidence_score = 0.99  # deterministic rule-based check
        task.reasoning_trace.append(f"Quality gate: {'PASS' if passes else 'FAIL'} — {issues}")
        return task
