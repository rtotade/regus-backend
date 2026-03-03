"""Configuration — reads from environment variables"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "RegWatch Nexus"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-32chars+")
    ALLOWED_ORIGINS: List[str] = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/regwatch")
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL_SONNET: str = "claude-sonnet-4-20250514"
    ANTHROPIC_MODEL_HAIKU: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_MODEL_OPUS: str = "claude-opus-4-20250514"

    # JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "jwt-secret-change-me")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24 * 7  # 7 days

    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRO_PRICE_ID: str = os.getenv("STRIPE_PRO_PRICE_ID", "")
    STRIPE_ENTERPRISE_PRICE_ID: str = os.getenv("STRIPE_ENTERPRISE_PRICE_ID", "")

    # SendGrid
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = os.getenv("SENDGRID_FROM_EMAIL", "alerts@regwatchnexus.com")
    SENDGRID_FROM_NAME: str = "RegWatch Nexus"

    # AWS
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "regwatch-reports")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")

    # Expo Push (Mobile)
    EXPO_ACCESS_TOKEN: str = os.getenv("EXPO_ACCESS_TOKEN", "")

    # Slack (internal ops only)
    SLACK_OPS_WEBHOOK: str = os.getenv("SLACK_OPS_WEBHOOK", "")

    # Crawl settings
    CRAWL_INTERVAL_MINUTES: int = 30
    CRAWL_TIMEOUT_SECONDS: int = 30
    MAX_CONCURRENT_CRAWLERS: int = 10

    # Rate limits
    PUBLIC_RATE_LIMIT: str = "100/minute"
    AUTH_RATE_LIMIT: str = "10/minute"
    COUNSEL_RATE_LIMIT_PRO: int = 50   # queries/month
    COUNSEL_RATE_LIMIT_ENT: int = 9999

    # Plan names
    PLAN_ANONYMOUS: str = "anonymous"
    PLAN_FREE: str = "free"
    PLAN_PRO: str = "pro"
    PLAN_ENTERPRISE: str = "enterprise"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
