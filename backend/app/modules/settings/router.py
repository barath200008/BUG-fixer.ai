from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.middleware.auth import AuthUser, require_auth
from app.db.session import get_db
from app.modules.settings.schemas import (
    ModelOut,
    PatchSettingsRequest,
    SetCredentialRequest,
    SettingsResponse,
)
from app.modules.settings.service import get_models, get_settings, set_credential, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings_(
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    return await get_settings(db, current_user.id)


@router.patch("", response_model=SettingsResponse)
async def patch_settings_(
    payload: PatchSettingsRequest,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await update_settings(db, current_user.id, payload.model_dump(exclude_unset=True))
    return await get_settings(db, current_user.id)


@router.get("/models", response_model=list[ModelOut])
async def get_models_(current_user: AuthUser = Depends(require_auth)):
    return get_models()


@router.post("/credentials", status_code=204)
async def post_credential_(
    payload: SetCredentialRequest,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    await set_credential(db, current_user.id, payload.provider, payload.apiKey, payload.baseUrl)
