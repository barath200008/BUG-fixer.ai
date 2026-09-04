"""Mirrors: backend/src/modules/ai/providers/base.provider.ts"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ChatRequest:
    model: str
    system: str
    user: str
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 6000
    temperature: float = 0.1


class AIProvider(ABC):
    @abstractmethod
    async def chat(self, request: ChatRequest) -> str: ...
