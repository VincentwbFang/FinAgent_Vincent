from __future__ import annotations

import json
from typing import Any

from app.config import Settings
from app.llm.base import LLMProvider, RateLimitError
from app.llm.github_models import GitHubModelsProvider
from app.llm.groq import GroqProvider
from app.llm.huggingface import HuggingFaceProvider
from app.llm.openrouter import OpenRouterProvider
from app.quota import QuotaManager


class LocalFallbackProvider(LLMProvider):
    name = "local_fallback"

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        # Deterministic fallback keeps local runs functional without any cloud key.
        return (
            "Model fallback used. Summary: prioritize cited SEC facts, market trend, "
            "and volatility-aware bull/base/bear scenarios."
        )


class LLMRouter:
    def __init__(self, settings: Settings, quota_manager: QuotaManager):
        self.settings = settings
        self.quota_manager = quota_manager
        self.providers: list[LLMProvider] = [
            GroqProvider(settings),
            OpenRouterProvider(settings),
            GitHubModelsProvider(settings),
            HuggingFaceProvider(settings),
            LocalFallbackProvider(),
        ]

    async def complete(self, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, Any]]:
        attempts: list[dict[str, str]] = []
        for provider in self.providers:
            if provider.name != "local_fallback" and not self.quota_manager.allow(provider.name):
                attempts.append({"provider": provider.name, "status": "quota_blocked"})
                continue
            try:
                text = await provider.complete(system_prompt, user_prompt)
                meta = {"model_used": provider.name, "attempts": attempts}
                return text, meta
            except (ValueError, RateLimitError) as exc:
                attempts.append({"provider": provider.name, "status": str(exc)})
                continue
            except Exception as exc:  # noqa: BLE001
                attempts.append({"provider": provider.name, "status": f"error:{type(exc).__name__}"})
                continue

        return json.dumps({"summary": "No provider available."}), {"model_used": "none", "attempts": attempts}
