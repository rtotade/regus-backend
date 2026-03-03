import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_type: Mapped[str] = mapped_column(String(50))
    primary_country: Mapped[str] = mapped_column(String(10))
    active_countries: Mapped[list] = mapped_column(JSON, default=list)
    products: Mapped[list] = mapped_column(JSON, default=list)
    plan: Mapped[str] = mapped_column(String(20))
    api_key: Mapped[str] = mapped_column(String(64), unique=True)
    seats: Mapped[int] = mapped_column(Integer, default=1)
    health_score: Mapped[float] = mapped_column(Float, default=100.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
