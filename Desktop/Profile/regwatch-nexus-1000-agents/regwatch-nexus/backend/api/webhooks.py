"""Stripe webhook handler"""
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Depends
from backend.database import get_db
from backend.models.user import User
from backend.services.stripe_service import verify_webhook
import stripe

router = APIRouter()


@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    
    event = verify_webhook(payload, sig_header)
    if not event:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event_type = event["type"]
    data = event["data"]["object"]
    
    if event_type == "checkout.session.completed":
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        if customer_id:
            result = await db.execute(
                select(User).where(User.stripe_customer_id == customer_id))
            user = result.scalar_one_or_none()
            if user:
                user.stripe_subscription_id = subscription_id
                user.plan = "pro"  # Default; refined by subscription event
                await db.commit()
    
    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        from backend.services.stripe_service import get_plan_from_subscription
        subscription_id = data.get("id")
        customer_id = data.get("customer")
        status = data.get("status")
        
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id))
        user = result.scalar_one_or_none()
        if user:
            if status == "active":
                user.plan = get_plan_from_subscription(subscription_id)
            elif status in ("canceled", "unpaid", "past_due"):
                user.plan = "free"
            await db.commit()
    
    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id))
        user = result.scalar_one_or_none()
        if user:
            user.plan = "free"
            user.stripe_subscription_id = None
            await db.commit()
    
    return {"ok": True}
