from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_providers import provider_status
from database.models import User, UserSettings
from intelligence.schemas import ScoreWeights
from ..deps import current_user, get_db
from ..schemas import SettingsPatch, WeightsPatch

router = APIRouter(prefix="/settings", tags=["settings"])


def _row(db: Session, user: User) -> UserSettings:
    row = db.execute(select(UserSettings).where(UserSettings.user_id == user.id)).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user.id, weights=None, preferences={})
        db.add(row)
        db.flush()
    return row


def _out(row: UserSettings, request: Request) -> dict:
    return {"weights": row.weights or ScoreWeights().to_dict(), "weights_are_default": row.weights is None,
            "preferences": row.preferences or {}, "default_provider": request.app.state.settings.ai_provider}


@router.get("")
def get_settings(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = _row(db, user)
    db.commit()
    return _out(row, request)


@router.patch("")
def patch_settings(body: SettingsPatch, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = _row(db, user)
    if body.preferences is not None:
        row.preferences = {**(row.preferences or {}), **body.preferences}
    db.commit()
    return _out(row, request)


@router.get("/providers")
def get_providers(request: Request, user: User = Depends(current_user)):
    """Which AI providers are configured. Key values are never returned."""
    return {"providers": provider_status(request.app.state.settings)}


@router.patch("/weights")
def patch_weights(body: WeightsPatch, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = _row(db, user)
    row.weights = body.weights.model_dump()
    db.commit()
    return _out(row, request)
