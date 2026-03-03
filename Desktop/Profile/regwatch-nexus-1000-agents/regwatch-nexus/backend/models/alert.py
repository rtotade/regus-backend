import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    regulator: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    full_analysis: Mapped[str | None] = mapped_column(Text)
    recommended_actions: Mapped[dict | None] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    base_impact_score: Mapped[float] = mapped_column(Float, default=5.0)
    affected_sectors: Mapped[list] = mapped_column(JSON, default=list)
    topic_tags: Mapped[list] = mapped_column(JSON, default=list)
    regulatory_deadline: Mapped[str | None] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(Text)
    seo_meta: Mapped[dict | None] = mapped_column(JSON)
    cascade_predictions: Mapped[dict | None] = mapped_column(JSON)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index("ix_alerts_juris_sev", "jurisdiction", "severity"),)

class SourceDocument(Base):
    __tablename__ = "source_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[str] = mapped_column(String(30))
    source_name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text, unique=True)
    raw_content: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
