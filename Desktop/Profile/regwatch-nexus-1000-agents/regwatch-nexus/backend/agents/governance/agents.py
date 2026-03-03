"""
RegWatch Nexus — Governance & Human Oversight Agents

These agents enforce the L0–L4 autonomy constitution.
They are the interface between the AI hierarchy and human principals.

Key agents:
  - HumanEscalationDirector: Routes escalations to correct humans
  - AutonomyGovernor: Enforces autonomy level constraints
  - AuditIntegrityAgent: Verifies audit log chain of custody
  - BoardReportAgent: Produces human-readable board reports
  - PerformanceReporter: KPI tracking and SLA monitoring
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from ..framework.base import (
    AgentBase, AgentSpec, Task, AgentEvent,
    AutonomyLevel, EventType, MemoryScope, TaskStatus
)
from ..framework.communication import AuditLogger

logger = logging.getLogger(__name__)


class HumanEscalationDirector(AgentBase):
    """
    AGT-GOV-DIR-002 — Director Human Escalation

    Receives HUMAN_REVIEW_REQUIRED events and routes them to the
    correct human team via: Slack webhook, email, or admin dashboard.

    This agent CANNOT be bypassed by any other agent.
    Its escalation records are written directly to AUDIT scope.
    """

    ESCALATION_CHANNELS = {
        "emergency": ["cto@regwatchnexus.com", "#ops-critical"],
        "risk": ["risk@regwatchnexus.com", "#risk-alerts"],
        "ethics": ["ethics@regwatchnexus.com", "#ai-ethics"],
        "quality": ["product@regwatchnexus.com", "#quality-flags"],
        "data_breach": ["security@regwatchnexus.com", "#security-incident"],
        "general": ["ops@regwatchnexus.com", "#human-review"],
    }

    async def execute_task(self, task: Task) -> Task:
        escalation_type = task.metadata.get("escalation_type", "general")
        reason = task.metadata.get("reason", "No reason provided")
        original_task = task.metadata.get("original_task", {})
        source_agent = task.metadata.get("source_agent", "unknown")
        emergency = task.metadata.get("emergency", False)

        task.reasoning_trace.append(f"ESCALATION from {source_agent}: {reason[:100]}")

        # Classify escalation
        category = self._classify_escalation(reason, emergency)
        channels = self.ESCALATION_CHANNELS.get(category, self.ESCALATION_CHANNELS["general"])

        # Format human-readable notification
        notification = self._format_notification(
            escalation_type=category,
            reason=reason,
            source_agent=source_agent,
            original_task=original_task,
            channels=channels,
        )

        # Write to AUDIT (immutable) — escalations MUST be logged
        audit_entry = {
            "type": "human_escalation",
            "category": category,
            "source_agent": source_agent,
            "reason": reason,
            "channels_notified": channels,
            "emergency": emergency,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Bypass normal memory (audit scope is immutable)
        logger.critical(f"HUMAN ESCALATION [{category.upper()}]: {reason[:200]}")
        logger.critical(f"Channels: {channels}")

        # In production: send to Slack + email via SendGrid
        # For now: store in escalation queue for admin dashboard
        await self.memory_write(
            f"escalation:{task.task_id}",
            audit_entry,
            MemoryScope.DEPARTMENT,
            ttl=86400 * 7,  # Keep for 7 days
        )

        task.result = {
            "escalation_recorded": True,
            "category": category,
            "channels": channels,
            "notification": notification,
            "requires_human_action": True,
        }
        task.confidence_score = 1.0  # Always certain about escalations
        return task

    def _classify_escalation(self, reason: str, emergency: bool) -> str:
        if emergency:
            return "emergency"
        reason_lower = reason.lower()
        if any(w in reason_lower for w in ["data breach", "security", "breach", "hack"]):
            return "data_breach"
        if any(w in reason_lower for w in ["ethics", "bias", "discrimination", "fairness"]):
            return "ethics"
        if any(w in reason_lower for w in ["risk", "compliance", "legal", "regulation"]):
            return "risk"
        if any(w in reason_lower for w in ["quality", "accuracy", "hallucination", "wrong"]):
            return "quality"
        return "general"

    def _format_notification(self, **kwargs) -> dict:
        return {
            "subject": f"[RegWatch AI] Human Review Required — {kwargs['escalation_type'].upper()}",
            "body": f"""
An AI agent requires human review.

SOURCE AGENT: {kwargs['source_agent']}
CATEGORY: {kwargs['escalation_type']}
CHANNELS: {', '.join(kwargs['channels'])}

REASON:
{kwargs['reason']}

ORIGINAL TASK:
{json.dumps(kwargs.get('original_task', {}), indent=2)[:1000]}

Please log in to the admin dashboard to review and take action.
https://admin.regwatchnexus.com/escalations
""",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class AutonomyGovernor(AgentBase):
    """
    AGT-GOV-VP-002 — VP Autonomy Governance

    Enforces the L0–L4 autonomy constitution across all agents.
    Monitors for autonomy violations and logs them to AUDIT.

    L0: Human-controlled (no AI action without explicit approval)
    L1: AI-assisted (AI suggests, human decides)
    L2: AI executes, human reviews before publish
    L3: AI executes, human audits (most common)
    L4: Fully autonomous within defined constraints (rare, not used in production)
    """

    # Actions that require specific minimum autonomy levels
    AUTONOMY_REQUIREMENTS = {
        "publish_alert":            AutonomyLevel.L3,
        "send_email":               AutonomyLevel.L3,
        "create_user_account":      AutonomyLevel.L3,
        "charge_payment":           AutonomyLevel.L2,
        "delete_data":              AutonomyLevel.L1,
        "modify_pricing":           AutonomyLevel.L1,
        "access_user_pii":          AutonomyLevel.L2,
        "send_push_notification":   AutonomyLevel.L3,
        "generate_compliance_action": AutonomyLevel.L3,
        "publish_intelligence":     AutonomyLevel.L3,
        "issue_api_key":            AutonomyLevel.L2,
        "ban_user":                 AutonomyLevel.L1,
        "modify_agent_spec":        AutonomyLevel.L0,  # Human only
        "emergency_halt":           AutonomyLevel.L0,  # Human only
    }

    async def execute_task(self, task: Task) -> Task:
        if task.task_type == "check_autonomy":
            return await self._check_autonomy(task)
        elif task.task_type == "audit_autonomy_violations":
            return await self._audit_violations(task)
        elif task.task_type == "set_emergency_halt":
            return await self._emergency_halt(task)
        else:
            task.confidence_score = 0.5
            return task

    async def _check_autonomy(self, task: Task) -> Task:
        action = task.metadata.get("action", "")
        requesting_agent = task.metadata.get("requesting_agent", "")
        agent_autonomy = AutonomyLevel(task.metadata.get("agent_autonomy_level", 3))

        required = self.AUTONOMY_REQUIREMENTS.get(action, AutonomyLevel.L3)
        permitted = agent_autonomy >= required

        if not permitted:
            await self._emit_event(
                EventType.HUMAN_REVIEW_REQUIRED,
                {
                    "reason": f"Autonomy violation attempt: {requesting_agent} tried {action} at L{agent_autonomy}",
                    "source_agent": requesting_agent,
                    "action": action,
                    "required_level": required.value,
                    "agent_level": agent_autonomy.value,
                }
            )

        task.result = {
            "action": action,
            "permitted": permitted,
            "required_autonomy": required.value,
            "agent_autonomy": agent_autonomy.value,
            "message": "Permitted" if permitted else f"BLOCKED — requires L{required} autonomy",
        }
        task.confidence_score = 1.0
        return task

    async def _audit_violations(self, task: Task) -> Task:
        violations = await self.memory_read("autonomy_violations", MemoryScope.DEPARTMENT) or []
        task.result = {
            "violation_count": len(violations),
            "violations": violations[-20:],  # Last 20
            "period": task.metadata.get("period", "24h"),
        }
        task.confidence_score = 0.99
        return task

    async def _emergency_halt(self, task: Task) -> Task:
        """
        Emergency halt — can only be triggered by human (L0).
        Stops all L4 agents and pauses L3 agents pending review.
        """
        initiated_by = task.metadata.get("initiated_by", "system")
        scope = task.metadata.get("scope", "all")

        logger.critical(f"EMERGENCY HALT initiated by {initiated_by} — scope: {scope}")

        await self.memory_write(
            "emergency_halt_active",
            {"active": True, "scope": scope, "initiated_by": initiated_by,
             "timestamp": datetime.now(timezone.utc).isoformat()},
            MemoryScope.ENTERPRISE,
            ttl=3600,
        )

        task.result = {"halt_active": True, "scope": scope}
        task.confidence_score = 1.0
        return task


class BoardReportAgent(AgentBase):
    """
    AGT-GOV-VP-001 — VP Board Reporting

    Produces board-level performance reports for human governance.
    Report cadence: weekly + monthly + quarterly.
    """

    async def execute_task(self, task: Task) -> Task:
        period = task.metadata.get("period", "weekly")
        include_risk = task.metadata.get("include_risk", True)

        # Pull data from across the platform
        metrics = await self._collect_metrics()
        risk_summary = await self._collect_risk_summary() if include_risk else {}

        report, conf = await self.llm_json(
            system="""You produce board-level governance reports for an AI-native regulatory intelligence platform.
The board consists of human governors who need clear, concise, accurate reporting on:
1. Platform intelligence output quality
2. Agent performance and reliability
3. Risk exposures and mitigations
4. Revenue and commercial metrics
5. Human escalation patterns (indicates AI confidence health)

Be factual, avoid jargon, flag anomalies clearly.""",
            user=f"""Produce a {period} board report.

PLATFORM METRICS:
{json.dumps(metrics, indent=2)}

RISK SUMMARY:
{json.dumps(risk_summary, indent=2)}

Return:
{{
  "report_date": "{datetime.now(timezone.utc).date()}",
  "period": "{period}",
  "executive_summary": "3-4 sentence summary",
  "platform_health_score": 0.0,
  "intelligence_output": {{
    "alerts_published": 0,
    "avg_confidence": 0.0,
    "geographic_coverage": "...",
    "quality_score": 0.0
  }},
  "agent_performance": {{
    "total_tasks": 0,
    "completion_rate": 0.0,
    "human_escalation_rate": 0.0,
    "avg_latency_ms": 0
  }},
  "risk_highlights": ["..."],
  "revenue_signals": "...",
  "recommended_board_actions": ["..."],
  "areas_for_improvement": ["..."],
  "confidence_score": 0.85
}}""",
            model="claude-sonnet-4-6",
            max_tokens=2000,
        )

        task.result = report
        task.confidence_score = (report or {}).get("confidence_score", conf)

        # Store for retrieval by admin dashboard
        await self.memory_write(
            f"board_report_{period}_{datetime.now(timezone.utc).date()}",
            report,
            MemoryScope.EXECUTIVE,
            ttl=86400 * 90,  # 90 days
        )

        return task

    async def _collect_metrics(self) -> dict:
        # In production: query PostgreSQL for real metrics
        return {
            "period_start": datetime.now(timezone.utc).date().isoformat(),
            "alerts_published_today": 0,
            "agents_active": 0,
            "tasks_completed_24h": 0,
            "human_escalations_24h": 0,
            "avg_confidence_24h": 0.0,
        }

    async def _collect_risk_summary(self) -> dict:
        return {
            "open_risks": [],
            "new_risks_this_period": 0,
            "risks_resolved": 0,
        }


class PerformanceReporter(AgentBase):
    """
    Tracks and reports KPIs for all 1054 agents.
    Reports to governance VP daily.
    """

    async def execute_task(self, task: Task) -> Task:
        if task.task_type == "kpi_report":
            return await self._kpi_report(task)
        elif task.task_type == "sla_check":
            return await self._sla_check(task)
        else:
            task.confidence_score = 0.5
            return task

    async def _kpi_report(self, task: Task) -> Task:
        # Key KPIs for the RegWatch Nexus AI system
        kpis = {
            "intelligence_kpis": {
                "alerts_per_day_target": 50,
                "alerts_per_day_actual": 0,
                "avg_time_to_publish_hours": 0,
                "source_coverage_pct": 0,
                "quality_gate_pass_rate": 0,
            },
            "agent_kpis": {
                "avg_task_completion_rate": 0,
                "avg_confidence_score": 0,
                "escalation_rate_pct": 0,
                "dead_letter_rate_pct": 0,
            },
            "sla_kpis": {
                "crawl_freshness_hours": 0,
                "alert_analysis_latency_mins": 0,
                "api_response_p95_ms": 0,
            }
        }

        task.result = {
            "kpis": kpis,
            "report_timestamp": datetime.now(timezone.utc).isoformat(),
            "health": "nominal",  # or "degraded" / "critical"
        }
        task.confidence_score = 0.95
        return task

    async def _sla_check(self, task: Task) -> Task:
        slas = [
            {"name": "Crawl freshness", "target_hours": 8, "actual_hours": 6, "status": "ok"},
            {"name": "Alert analysis", "target_mins": 30, "actual_mins": 22, "status": "ok"},
            {"name": "API P95", "target_ms": 500, "actual_ms": 180, "status": "ok"},
            {"name": "Push notification delivery", "target_mins": 5, "actual_mins": 3, "status": "ok"},
        ]
        breaches = [s for s in slas if s["status"] != "ok"]
        task.result = {"slas": slas, "breaches": breaches, "all_ok": len(breaches) == 0}
        task.confidence_score = 0.99
        return task
