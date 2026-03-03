"""Agent 09 — Compliance Health Score Engine"""
import logging
from backend.database import AsyncSessionLocal
from backend.models.client import Client
from backend.models.action import ComplianceAction
from sqlalchemy import select, func
from datetime import date

logger = logging.getLogger(__name__)

async def recalculate_all_health_scores():
    """Recalculate health scores for all Pro/Enterprise clients"""
    async with AsyncSessionLocal() as db:
        clients = await db.execute(
            select(Client).where(Client.is_active == True, 
                                Client.plan.in_(["pro", "enterprise"])))
        
        for client in clients.scalars().all():
            score = 100.0
            today = date.today()
            
            # Deduct for open critical actions
            critical_open = await db.execute(
                select(func.count(ComplianceAction.id)).where(
                    ComplianceAction.client_id == client.id,
                    ComplianceAction.priority == "critical",
                    ComplianceAction.status != "done",
                ))
            score -= (critical_open.scalar() or 0) * 15
            
            # Deduct for open high actions
            high_open = await db.execute(
                select(func.count(ComplianceAction.id)).where(
                    ComplianceAction.client_id == client.id,
                    ComplianceAction.priority == "high",
                    ComplianceAction.status != "done",
                ))
            score -= (high_open.scalar() or 0) * 8
            
            # Deduct for overdue actions
            overdue = await db.execute(
                select(func.count(ComplianceAction.id)).where(
                    ComplianceAction.client_id == client.id,
                    ComplianceAction.due_date < today,
                    ComplianceAction.status != "done",
                ))
            score -= (overdue.scalar() or 0) * 10
            
            client.health_score = max(0.0, min(100.0, score))
        
        await db.commit()
        logger.info("Health scores recalculated")
