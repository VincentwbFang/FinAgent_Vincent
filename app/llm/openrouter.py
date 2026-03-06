from __future__ import annotations

import httpx

from app.config import Settings
from app.llm.base import LLMProvider, RateLimitError


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        if resp.status_code == 429:
            raise RateLimitError("OpenRouter rate limit")
        resp.raise_for_status()

        data = resp.json()
        return data["choices"][0]["message"]["content"]
