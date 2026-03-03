"""
RegWatch Nexus — Auth Routes
Optional user registration and login.
Anonymous use never requires hitting these endpoints.
"""
import hashlib
import os
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request
from jose import jwt
from supabase_client import supabase_service
from config import config

bp = Blueprint('auth', __name__)


def hash_password(password: str) -> str:
    """Simple password hashing. In production use bcrypt."""
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def create_jwt(user: dict) -> str:
    payload = {
        'sub': user['id'],
        'email': user['email'],
        'plan': user.get('plan', 'free'),
        'company_name': user.get('company_name', ''),
        'exp': datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


@bp.route('/register', methods=['POST'])
def register():
    """Create a free account. Email only required."""
    data = request.get_json() or {}
    email = (data.get('email') or '').lower().strip()
    password = data.get('password', '')

    if not email or '@' not in email:
        return jsonify({'error': 'Valid email required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    # Check if already registered
    existing = supabase_service.table('users').select('id').eq('email', email).execute()
    if existing.data:
        return jsonify({'error': 'Email already registered'}), 409

    user = {
        'email': email,
        'password_hash': hash_password(password),
        'plan': 'free',
        'full_name': data.get('full_name', ''),
        'company_name': data.get('company_name', ''),
        'saved_filters': data.get('saved_filters', {}),
        'watchlist': [],
        'notification_prefs': {'email_digest': 'weekly', 'real_time': False},
        'timezone': data.get('timezone', 'UTC'),
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    result = supabase_service.table('users').insert(user).execute()
    created = result.data[0]
    token = create_jwt(created)

    return jsonify({
        'token': token,
        'user': {
            'id': created['id'],
            'email': created['email'],
            'plan': created['plan'],
            'full_name': created.get('full_name', ''),
        }
    }), 201


@bp.route('/login', methods=['POST'])
def login():
    """Login with email and password."""
    data = request.get_json() or {}
    email = (data.get('email') or '').lower().strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    result = supabase_service.table('users').select('*').eq('email', email).single().execute()
    if not result.data:
        return jsonify({'error': 'Invalid credentials'}), 401

    user = result.data
    if not verify_password(password, user.get('password_hash', '')):
        return jsonify({'error': 'Invalid credentials'}), 401

    token = create_jwt(user)

    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'plan': user['plan'],
            'full_name': user.get('full_name', ''),
            'company_name': user.get('company_name', ''),
        }
    })


@bp.route('/profile', methods=['GET'])
def get_profile():
    """Get current user profile. Requires valid JWT."""
    from pipeline.plan_filter import get_user_from_request
    user_payload = get_user_from_request()
    if not user_payload:
        return jsonify({'error': 'Unauthorized'}), 401

    result = supabase_service.table('users').select('*').eq('id', user_payload['sub']).single().execute()
    if not result.data:
        return jsonify({'error': 'User not found'}), 404

    user = result.data
    # Never return password hash
    user.pop('password_hash', None)
    return jsonify({'user': user})


@bp.route('/profile', methods=['PUT'])
def update_profile():
    """Update user profile settings."""
    from pipeline.plan_filter import get_user_from_request
    user_payload = get_user_from_request()
    if not user_payload:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    allowed = ['full_name', 'company_name', 'timezone', 'notification_prefs',
               'saved_filters', 'watchlist']
    updates = {k: v for k, v in data.items() if k in allowed}

    result = supabase_service.table('users')\
        .update(updates).eq('id', user_payload['sub']).execute()
    return jsonify({'ok': True})


@bp.route('/logout', methods=['POST'])
def logout():
    """Client-side logout — just returns ok. JWT invalidation via expiry."""
    return jsonify({'ok': True})
