import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(300))
    report_type: Mapped[str] = mapped_column(String(50))
    client_id: Mapped[str | None] = mapped_column(String(36))
    jurisdiction: Mapped[str | None] = mapped_column(String(10))
    summary_public: Mapped[str] = mapped_column(Text)
    s3_key: Mapped[str | None] = mapped_column(String(500))
    is_public_summary: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class QualityFlag(Base):
    __tablename__ = "quality_flags"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id: Mapped[str | None] = mapped_column(String(36))
    flag_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
