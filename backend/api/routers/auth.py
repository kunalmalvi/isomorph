from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.errors import Conflict, Unauthorized, ValidationFailed
from core.security import PasswordPolicyError, create_token, hash_password, verify_password
from database.models import User
from ..deps import api_rate_limit, auth_rate_limit, current_user, get_db
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash of a random password, verified when the account does not exist so timing does not reveal registered emails.
_DUMMY_HASH = hash_password(uuid.uuid4().hex + "x")


def _token(request: Request, user: User) -> TokenOut:
    s = request.app.state.settings
    return TokenOut(access_token=create_token(str(user.id), s.secret_key, s.access_token_ttl_seconds), expires_in=s.access_token_ttl_seconds)


@router.post("/register", response_model=TokenOut, status_code=201, dependencies=[Depends(auth_rate_limit)])
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    try:
        pw = hash_password(body.password)
    except PasswordPolicyError as e:
        raise ValidationFailed(str(e))
    user = User(email=email, display_name=body.display_name, password_hash=pw, is_active=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise Conflict("an account with this email already exists")
    return _token(request, user)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(auth_rate_limit)])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.strip().lower())).scalar_one_or_none()
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok or not user.is_active:
        raise Unauthorized("invalid email or password")
    return _token(request, user)


@router.get("/me", response_model=UserOut, dependencies=[Depends(api_rate_limit)])
def me(user: User = Depends(current_user)):
    return user
