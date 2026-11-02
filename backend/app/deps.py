"""Shared request dependencies: who is calling, and what they may do."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session, settings
from app.models import User
from app.security import decode_access_token

COOKIE_NAME = "aurum_session"


def current_user(request: Request, db: Session = Depends(get_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_access_token(token, settings.jwt_secret) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="Sign in required.")
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Sign in required.")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return user


def require_roles(*roles: str):
    """Allow only the listed roles. The role comes from the database."""

    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403, detail="You don't have access to this."
            )
        return user

    return checker