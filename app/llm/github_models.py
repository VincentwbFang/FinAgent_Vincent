from __future__ import annotations

import httpx

from app.config import Settings
from app.llm.base import LLMProvider, RateLimitError


class GitHubModelsProvider(LLMProvider):
    name = "github"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.settings.github_token:
            raise ValueError("GITHUB_TOKEN not configured")

        headers = {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.github_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        # GitHub Models uses an OpenAI-compatible endpoint.
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post(
                "https://models.inference.ai.azure.com/chat/completions",
                headers=headers,
                json=payload,
            )
        if resp.status_code == 429:
            raise RateLimitError("GitHub models rate limit")
        resp.raise_for_status()

        data = resp.json()
        return data["choices"][0]["message"]["content"]
