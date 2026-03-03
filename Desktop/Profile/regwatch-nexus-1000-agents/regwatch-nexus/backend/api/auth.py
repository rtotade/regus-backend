"""Auth routes — register, login, token refresh"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models.user import User
from backend.services.auth import hash_password, verify_password, create_token
from backend.services.email import send_welcome_email
from backend.services.stripe_service import create_customer
from backend.api.deps import get_current_user
import secrets

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    company_type: Optional[str] = None
    timezone: Optional[str] = None
    saved_filters: Optional[dict] = None
    notification_prefs: Optional[dict] = None
    expo_push_token: Optional[str] = None


@router.post("/register")
async def register(
    req: RegisterRequest, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
        plan="free",
    )
    db.add(user)
    await db.flush()
    
    # Create Stripe customer in background
    bg.add_task(send_welcome_email, req.email, req.full_name or "")
    
    token = create_token(user.id, user.email, user.plan)
    return {"token": token, "user": {"id": user.id, "email": user.email,
            "plan": user.plan, "full_name": user.full_name}}


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    
    user.last_login = datetime.utcnow()
    token = create_token(user.id, user.email, user.plan, user.client_id)
    return {"token": token, "user": {"id": user.id, "email": user.email,
            "plan": user.plan, "full_name": user.full_name,
            "company_name": user.company_name}}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "email": user.email, "plan": user.plan,
        "full_name": user.full_name, "company_name": user.company_name,
        "company_type": user.company_type, "saved_filters": user.saved_filters,
        "watchlist": user.watchlist, "notification_prefs": user.notification_prefs,
        "timezone": user.timezone, "created_at": user.created_at.isoformat(),
    }


@router.patch("/me")
async def update_me(
    req: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    return {"ok": True}


@router.post("/checkout")
async def create_checkout(
    plan_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.stripe_service import create_checkout_session
    from backend.config import settings
    
    if not user.stripe_customer_id:
        customer_id = create_customer(user.email, user.full_name)
        user.stripe_customer_id = customer_id
    
    price_id = (settings.STRIPE_ENTERPRISE_PRICE_ID if plan_name == "enterprise" 
                else settings.STRIPE_PRO_PRICE_ID)
    
    url = create_checkout_session(
        user.stripe_customer_id, price_id,
        success_url="https://app.regwatchnexus.com/dashboard?upgraded=1",
        cancel_url="https://app.regwatchnexus.com/pricing",
    )
    return {"checkout_url": url}


@router.post("/portal")
async def billing_portal(user: User = Depends(get_current_user)):
    from backend.services.stripe_service import create_portal_session
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account")
    url = create_portal_session(user.stripe_customer_id,
                                "https://app.regwatchnexus.com/account")
    return {"portal_url": url}
