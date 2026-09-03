from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    primaryProvider: str
    primaryModel: str
    autoRunTests: bool
    minimumConfidence: int
    sandboxGuardrails: bool


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    baseUrl: str | None
    createdAt: datetime


class SettingsResponse(BaseModel):
    settings: UserSettingOut
    credentials: list[CredentialOut] = Field(default_factory=list)


class PatchSettingsRequest(BaseModel):
    primaryProvider: str | None = None
    primaryModel: str | None = None
    autoRunTests: bool | None = None
    minimumConfidence: int | None = Field(default=None, ge=0, le=100)
    sandboxGuardrails: bool | None = None


class ModelOut(BaseModel):
    id: str
    provider: str
    model: str
    name: str
    free: bool
    configured: bool
    contextWindow: str
    description: str


class SetCredentialRequest(BaseModel):
    provider: str
    apiKey: str = Field(min_length=1)
    baseUrl: str | None = None
