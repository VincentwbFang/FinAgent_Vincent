from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import Settings


class SearchClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def search_company_news(self, symbol: str, company_name: str | None = None, count: int = 5) -> list[dict]:
        if not self.settings.brave_api_key:
            return []

        query = symbol if not company_name else f"{symbol} {company_name} earnings guidance risk"
        headers = {"Accept": "application/json", "X-Subscription-Token": self.settings.brave_api_key}
        params = {"q": query, "count": min(count, 10)}

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)

        if resp.status_code >= 400:
            return []

        payload = resp.json()
        out = []
        for item in payload.get("web", {}).get("results", [])[:count]:
            out.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "description": item.get("description", ""),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return out
