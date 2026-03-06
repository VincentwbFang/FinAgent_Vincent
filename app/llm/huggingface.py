from __future__ import annotations

import httpx

from app.config import Settings
from app.llm.base import LLMProvider, RateLimitError


class HuggingFaceProvider(LLMProvider):
    name = "huggingface"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if not self.settings.hf_token:
            raise ValueError("HF_TOKEN not configured")

        headers = {
            "Authorization": f"Bearer {self.settings.hf_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.hf_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post("https://router.huggingface.co/v1/chat/completions", headers=headers, json=payload)
        if resp.status_code == 429:
            raise RateLimitError("HuggingFace rate limit")
        resp.raise_for_status()

        data = resp.json()
        return data["choices"][0]["message"]["content"]
