from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    pass


class RateLimitError(LLMError):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError
