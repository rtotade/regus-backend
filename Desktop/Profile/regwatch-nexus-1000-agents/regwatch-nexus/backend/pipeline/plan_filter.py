"""
RegWatch Nexus — Plan Filter & JWT Auth
Access control applied at the API response layer. NEVER at the DB layer.
"""
import os
from functools import wraps
from flask import request, jsonify, g
from jose import jwt, JWTError
from config import config


def get_plan_from_request() -> str:
    """Extract plan from JWT Authorization header. Returns 'anonymous' if absent."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return 'anonymous'
    token = auth[7:]
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        return payload.get('plan', 'free')
    except JWTError:
        return 'anonymous'


def get_user_from_request() -> dict | None:
    """Extract full user payload from JWT. Returns None if absent/invalid."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except JWTError:
        return None


def require_plan(*plans):
    """Decorator: require one of the listed plans to access the endpoint."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_user_from_request()
            plan = user.get('plan', 'anonymous') if user else 'anonymous'
            if plan not in plans:
                return jsonify({
                    'error': 'Upgrade required',
                    'required_plans': list(plans),
                    'current_plan': plan,
                    'upgrade_url': '/pricing',
                }), 403
            g.user = user
            g.plan = plan
            return f(*args, **kwargs)
        return decorated
    return decorator


def apply_plan_filter(data: dict, plan: str) -> dict:
    """
    Strip Pro-only fields from alert data for non-Pro users.
    Called just before serialising the API response.
    """
    if plan in ('pro', 'enterprise'):
        return data

    restricted = ['full_analysis', 'recommended_actions', 'financial_exposure_usd',
                  'engineering_weeks', 'cascade_risk_score']

    filtered = {k: v for k, v in data.items() if k not in restricted}

    if plan in ('anonymous', 'free'):
        filtered['_pro_fields_available'] = True
        filtered['_upgrade_url'] = '/pricing'

    return filtered


def apply_plan_filter_list(items: list, plan: str) -> list:
    """Apply plan filter to a list of alert dicts."""
    return [apply_plan_filter(item, plan) for item in items]
