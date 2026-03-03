import uuid
from datetime import datetime, date
from sqlalchemy import String, Text, Float, Date, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class ImpactReport(Base):
    __tablename__ = "impact_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str] = mapped_column(String(36), nullable=False)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    client_impact_score: Mapped[float] = mapped_column(Float)
    financial_exposure: Mapped[float | None] = mapped_column(Float)
    engineering_weeks: Mapped[float | None] = mapped_column(Float)
    internal_deadline: Mapped[date | None] = mapped_column(Date)
    personalised_summary: Mapped[str | None] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ComplianceAction(Base):
    __tablename__ = "compliance_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str] = mapped_column(String(36), nullable=False)
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_team: Mapped[str | None] = mapped_column(String(100))
    assignee: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="todo")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PolicyGap(Base):
    __tablename__ = "policy_gaps"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    client_id: Mapped[str] = mapped_column(String(36), nullable=False)
    alert_id: Mapped[str | None] = mapped_column(String(36))
    policy_name: Mapped[str] = mapped_column(String(200))
    gaps_found: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
