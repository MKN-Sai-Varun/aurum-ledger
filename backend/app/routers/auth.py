from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record
from app.db import get_session, settings
from app.deps import COOKIE_NAME, current_user
from app.models import User
from app.ratelimit import LoginLimiter
from app.security import (
    TOKEN_MINUTES,
    create_access_token,
    verify_password,
    waste_verify_time,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = LoginLimiter()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: str


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_session),
):
    username = body.username.strip().lower()
    address = request.client.host if request.client else "unknown"
    key = f"{username}|{address}"

    if limiter.is_blocked(key):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again in a few minutes.",
            headers={"Retry-After": "900"},
        )

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        waste_verify_time(body.password)
        password_ok = False
    else:
        password_ok = verify_password(body.password, user.password_hash)

    if user is None or not user.is_active or not password_ok:
        limiter.record_failure(key)
        record(db, user.id if user else None, "login.failed", "user",
               user.id if user else None, f"username={username[:50]}")
        db.commit()
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    limiter.reset(key)
    record(db, user.id, "login.success", "user", user.id)
    db.commit()

    token = create_access_token(user.id, user.role, settings.jwt_secret)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=TOKEN_MINUTES * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/",
    )
    return user


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")