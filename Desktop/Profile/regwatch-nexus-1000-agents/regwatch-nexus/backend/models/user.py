import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(20), default="free")
    company_name: Mapped[str | None] = mapped_column(String(200))
    company_type: Mapped[str | None] = mapped_column(String(50))
    saved_filters: Mapped[dict] = mapped_column(JSON, default=dict)
    watchlist: Mapped[list] = mapped_column(JSON, default=list)
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    expo_push_token: Mapped[str | None] = mapped_column(String(200))
    counsel_queries_this_month: Mapped[int] = mapped_column(Integer, default=0)
    client_id: Mapped[str | None] = mapped_column(String(36))
