from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import os

JWT_SECRET    = os.getenv("JWT_SECRET", "change-this-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE    = 60 * 24

_USERS = {
    "admin":     {"password": "adminpass",  "role": "Admin",     "user_id": 1},
    "assistant": {"password": "assistpass", "role": "Assistant", "user_id": 2},
}

# HTTPBearer makes Swagger show the Authorize button (Bearer token input)
_bearer = HTTPBearer(auto_error=True)


class AuthUser(BaseModel):
    user_id: int
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


def create_token(username: str) -> str:
    u = _USERS[username]
    payload = {
        "sub":     username,
        "role":    u["role"],
        "user_id": u["user_id"],
        "exp":     datetime.utcnow() + timedelta(minutes=JWT_EXPIRE),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def authenticate(username: str, password: str) -> dict:
    user = _USERS.get(username)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer)
) -> AuthUser:
    """
    FastAPI dependency — works with both:
      - Swagger UI Authorize button (Bearer token)
      - React client (Authorization: Bearer <token> header)
    """
    try:
        data = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return AuthUser(user_id=int(data["user_id"]), role=data["role"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")