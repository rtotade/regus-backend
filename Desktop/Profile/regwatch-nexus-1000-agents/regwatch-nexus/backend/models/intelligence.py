import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class ConsultingSynthesis(Base):
    __tablename__ = "consulting_synthesis"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    firm_slug: Mapped[str] = mapped_column(String(100), index=True)
    firm_name: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(200))
    summary_public: Mapped[str] = mapped_column(Text)
    full_synthesis: Mapped[str | None] = mapped_column(Text)
    industry_tags: Mapped[list] = mapped_column(JSON, default=list)
    geography_tags: Mapped[list] = mapped_column(JSON, default=list)
    source_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class TrendingTopic(Base):
    __tablename__ = "trending_topics"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic: Mapped[str] = mapped_column(String(200))
    jurisdiction: Mapped[str] = mapped_column(String(10), default="GLOBAL")
    view_count_1h: Mapped[int] = mapped_column(Integer, default=0)
    view_count_24h: Mapped[int] = mapped_column(Integer, default=0)
    trending_score: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PageView(Base):
    __tablename__ = "page_views"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str | None] = mapped_column(String(36))
    page_type: Mapped[str] = mapped_column(String(50))
    jurisdiction: Mapped[str | None] = mapped_column(String(10))
    user_id: Mapped[str | None] = mapped_column(String(36))
    session_id: Mapped[str | None] = mapped_column(String(100))
    viewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
