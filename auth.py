# auth.py
# Handles: API Key authentication + session token generation

import os
import uuid
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey_change_in_production_123!")
ALGORITHM = "HS256"
SESSION_EXPIRE_MINUTES = 60

# Simple hardcoded API keys (in production, store hashed in DB)
VALID_API_KEYS = {
    "demo-key-123": "demo_user",
    "test-key-456": "test_user",
}

# FastAPI security scheme — expects header:  X-API-Key: demo-key-123
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


# ─────────────────────────────────────────
# STEP 1: Validate API Key → return username
# ─────────────────────────────────────────
def validate_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Check if the provided API key is valid.
    Returns the username associated with the key.
    Raises 403 if invalid.
    """
    if api_key not in VALID_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key. Use X-API-Key header with a valid key.",
        )
    return VALID_API_KEYS[api_key]


# ─────────────────────────────────────────
# STEP 2: Create a JWT session token
# ─────────────────────────────────────────
def create_session_token(username: str) -> dict:
    """
    Creates a JWT token for the session.
    Returns token + session metadata.
    """
    session_id = str(uuid.uuid4())
    expire = datetime.utcnow() + timedelta(minutes=SESSION_EXPIRE_MINUTES)

    payload = {
        "sub": username,
        "session_id": session_id,
        "exp": expire,
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "session_id": session_id,
        "username": username,
        "token": token,
        "expires_at": expire.isoformat(),
    }


# ─────────────────────────────────────────
# STEP 3: Decode/verify JWT token
# ─────────────────────────────────────────
def decode_session_token(token: str) -> dict:
    """
    Decodes and validates a JWT token.
    Returns the payload dict or raises 401.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )
