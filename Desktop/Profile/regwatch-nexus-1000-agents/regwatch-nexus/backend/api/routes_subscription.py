"""
RegWatch Nexus — Subscription Routes (Stripe)
Handles plan upgrades, webhooks, and billing portal.
"""
import stripe
import json
import logging
from flask import Blueprint, jsonify, request
from supabase_client import supabase_service
from pipeline.plan_filter import get_user_from_request
from config import config

bp = Blueprint('subscription', __name__)
logger = logging.getLogger(__name__)
stripe.api_key = config.STRIPE_SECRET_KEY


@bp.route('/checkout', methods=['POST'])
def create_checkout():
    """Create a Stripe checkout session for plan upgrade."""
    user_payload = get_user_from_request()
    if not user_payload:
        return jsonify({'error': 'Login required to upgrade'}), 401

    data = request.get_json() or {}
    plan = data.get('plan', 'pro')
    success_url = data.get('success_url', f"{config.ALLOWED_ORIGIN}/dashboard?upgraded=1")
    cancel_url = data.get('cancel_url', f"{config.ALLOWED_ORIGIN}/pricing")

    price_id = config.STRIPE_PRO_PRICE_ID if plan == 'pro' else config.STRIPE_ENTERPRISE_PRICE_ID

    # Get or create Stripe customer
    user = supabase_service.table('users').select('*').eq('id', user_payload['sub']).single().execute().data

    if user.get('stripe_customer_id'):
        customer_id = user['stripe_customer_id']
    else:
        customer = stripe.Customer.create(
            email=user['email'],
            metadata={'user_id': user['id'], 'plan': plan}
        )
        customer_id = customer.id
        supabase_service.table('users')\
            .update({'stripe_customer_id': customer_id})\
            .eq('id', user['id'])\
            .execute()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=['card'],
        mode='subscription',
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'user_id': user['id'], 'plan': plan},
        subscription_data={
            'metadata': {'user_id': user['id'], 'plan': plan}
        }
    )

    return jsonify({'checkout_url': session.url, 'session_id': session.id})


@bp.route('/portal', methods=['POST'])
def billing_portal():
    """Redirect to Stripe customer portal for managing subscription."""
    user_payload = get_user_from_request()
    if not user_payload:
        return jsonify({'error': 'Login required'}), 401

    user = supabase_service.table('users').select('stripe_customer_id')\
        .eq('id', user_payload['sub']).single().execute().data

    if not user or not user.get('stripe_customer_id'):
        return jsonify({'error': 'No active subscription found'}), 404

    session = stripe.billing_portal.Session.create(
        customer=user['stripe_customer_id'],
        return_url=f"{config.ALLOWED_ORIGIN}/dashboard",
    )
    return jsonify({'portal_url': session.url})


@bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events — updates user plan on payment events."""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, config.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400

    event_type = event['type']
    logger.info(f"[Stripe Webhook] Event: {event_type}")

    if event_type == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata'].get('user_id')
        plan = session['metadata'].get('plan', 'pro')
        if user_id:
            supabase_service.table('users')\
                .update({
                    'plan': plan,
                    'stripe_subscription_id': session.get('subscription'),
                })\
                .eq('id', user_id)\
                .execute()
            logger.info(f"[Stripe] User {user_id} upgraded to {plan}")

    elif event_type in ('customer.subscription.deleted', 'customer.subscription.paused'):
        sub = event['data']['object']
        customer_id = sub['customer']
        supabase_service.table('users')\
            .update({'plan': 'free'})\
            .eq('stripe_customer_id', customer_id)\
            .execute()
        logger.info(f"[Stripe] Subscription cancelled for customer {customer_id}")

    elif event_type == 'invoice.payment_failed':
        sub = event['data']['object']
        customer_id = sub['customer']
        # Don't immediately downgrade — Stripe retries for 3 days
        logger.warning(f"[Stripe] Payment failed for customer {customer_id}")

    return jsonify({'received': True})


@bp.route('/plans', methods=['GET'])
def get_plans():
    """Return available plans and pricing. Public."""
    return jsonify({
        'plans': [
            {
                'id': 'free',
                'name': 'Registered Free',
                'price_usd': 0,
                'billing': 'free',
                'features': [
                    'Full alert feed browsing',
                    'Save up to 5 filter profiles',
                    'Weekly email digest',
                    'Watchlist of 5 regulators',
                ]
            },
            {
                'id': 'pro',
                'name': 'Pro',
                'price_usd': 299,
                'billing': 'monthly',
                'stripe_price_id': config.STRIPE_PRO_PRICE_ID,
                'features': [
                    'Full alert analysis & recommended actions',
                    'Personalised compliance dashboard',
                    'Health score tracking',
                    'Real-time push alerts',
                    'Gap analysis for 10 policies',
                    'Ask Intelligence (50 queries/month)',
                    'Full consulting firm briefings',
                    'Monthly intelligence report PDF',
                    'API access (5,000 calls/day)',
                ]
            },
            {
                'id': 'enterprise',
                'name': 'Enterprise',
                'price_usd': None,
                'billing': 'custom',
                'features': [
                    'Everything in Pro',
                    'Multi-country compartmentalised workspace',
                    'Unlimited team seats',
                    'Monthly board pack reports',
                    'Unlimited Ask Intelligence',
                    'Jira / ServiceNow integration',
                    'SSO login',
                    'White-label license',
                    'Dedicated analyst',
                    'Unlimited API access',
                ]
            }
        ]
    })
