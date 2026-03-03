"""Authentication service — JWT + password hashing"""
import uuid
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import jwt, JWTError
from backend.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str, email: str, plan: str, client_id: Optional[str] = None) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "plan": plan,
        "client_id": client_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRY_HOURS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def get_plan_from_token(auth_header: Optional[str]) -> str:
    if not auth_header or not auth_header.startswith("Bearer "):
        return settings.PLAN_ANONYMOUS
    token = auth_header.replace("Bearer ", "")
    payload = decode_token(token)
    if not payload:
        return settings.PLAN_ANONYMOUS
    return payload.get("plan", settings.PLAN_FREE)


def get_user_id_from_token(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.replace("Bearer ", "")
    payload = decode_token(token)
    return payload.get("sub") if payload else None
