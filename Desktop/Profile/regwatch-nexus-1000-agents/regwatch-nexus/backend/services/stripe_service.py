"""Stripe subscription management"""
from typing import Optional
import stripe
from backend.config import settings

if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_customer(email: str, name: Optional[str] = None) -> Optional[str]:
    if not settings.STRIPE_SECRET_KEY:
        return f"cus_test_{email.split('@')[0]}"
    try:
        customer = stripe.Customer.create(email=email, name=name or email)
        return customer.id
    except Exception as e:
        print(f"[STRIPE] Customer create error: {e}")
        return None


def create_checkout_session(customer_id: str, price_id: str, 
                             success_url: str, cancel_url: str) -> Optional[str]:
    if not settings.STRIPE_SECRET_KEY:
        return "https://checkout.stripe.com/test"
    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return session.url
    except Exception as e:
        print(f"[STRIPE] Checkout error: {e}")
        return None


def create_portal_session(customer_id: str, return_url: str) -> Optional[str]:
    if not settings.STRIPE_SECRET_KEY:
        return return_url
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id, return_url=return_url
        )
        return session.url
    except Exception as e:
        print(f"[STRIPE] Portal error: {e}")
        return None


def verify_webhook(payload: bytes, sig_header: str) -> Optional[dict]:
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"[STRIPE] Webhook verify error: {e}")
        return None


def get_plan_from_subscription(subscription_id: str) -> str:
    if not settings.STRIPE_SECRET_KEY or not subscription_id:
        return "free"
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        price_id = sub["items"]["data"][0]["price"]["id"]
        if price_id == settings.STRIPE_ENTERPRISE_PRICE_ID:
            return "enterprise"
        elif price_id == settings.STRIPE_PRO_PRICE_ID:
            return "pro"
        return "free"
    except Exception:
        return "free"
