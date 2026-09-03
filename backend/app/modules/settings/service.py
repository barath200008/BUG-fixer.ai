"""User AI-provider/model preference + credential management.

This is what makes "sign in once, use the chosen model everywhere" work:
UserSetting.primaryProvider/primaryModel is read by both the copilot chat
service and the bug-diagnosis service, so whatever the user picks in the
Model Selector modal is what Workspace chat, AI Fix generation, and the
AI Fix History pipeline all use.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors.app_error import AppError
from app.core.security import encrypt_secret
from app.models.enums import Provider
from app.models.settings import ProviderCredential, UserSetting
from app.modules.ai.catalog import list_models, resolve_default


async def get_or_create_user_setting(db: AsyncSession, user_id: str) -> UserSetting:
    stmt = select(UserSetting).where(UserSetting.userId == user_id)
    setting = (await db.execute(stmt)).scalar_one_or_none()
    if setting is not None:
        return setting

    default_provider, default_model = resolve_default()
    setting = UserSetting(
        userId=user_id,
        primaryProvider=Provider(default_provider),
        primaryModel=default_model,
    )
    db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting


async def get_settings(db: AsyncSession, user_id: str) -> dict:
    setting = await get_or_create_user_setting(db, user_id)
    creds_stmt = select(ProviderCredential).where(ProviderCredential.userId == user_id)
    credentials = (await db.execute(creds_stmt)).scalars().all()
    return {"settings": setting, "credentials": credentials}


async def update_settings(db: AsyncSession, user_id: str, patch: dict) -> UserSetting:
    setting = await get_or_create_user_setting(db, user_id)

    if patch.get("primaryProvider") is not None:
        try:
            setting.primaryProvider = Provider(patch["primaryProvider"])
        except ValueError:
            raise AppError(400, "INVALID_PROVIDER", f"Unknown provider: {patch['primaryProvider']}")
    if patch.get("primaryModel") is not None:
        setting.primaryModel = patch["primaryModel"]
    if patch.get("autoRunTests") is not None:
        setting.autoRunTests = patch["autoRunTests"]
    if patch.get("minimumConfidence") is not None:
        setting.minimumConfidence = patch["minimumConfidence"]
    if patch.get("sandboxGuardrails") is not None:
        setting.sandboxGuardrails = patch["sandboxGuardrails"]

    await db.commit()
    await db.refresh(setting)
    return setting


def get_models() -> list[dict]:
    return list_models()


async def set_credential(db: AsyncSession, user_id: str, provider: str, api_key: str, base_url: str | None) -> ProviderCredential:
    try:
        provider_enum = Provider(provider)
    except ValueError:
        raise AppError(400, "INVALID_PROVIDER", f"Unknown provider: {provider}")

    stmt = select(ProviderCredential).where(
        ProviderCredential.userId == user_id, ProviderCredential.provider == provider_enum
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    encrypted = encrypt_secret(api_key)

    if existing:
        existing.encryptedKey = encrypted
        existing.baseUrl = base_url
        await db.commit()
        await db.refresh(existing)
        return existing

    cred = ProviderCredential(userId=user_id, provider=provider_enum, encryptedKey=encrypted, baseUrl=base_url)
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    return cred
