from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from app.config import Settings


class SearchClient:
    INSTITUTION_DOMAIN_WEIGHTS: dict[str, float] = {
        # Investment banks / broker research
        "jpmorganchase.com": 0.86,
        "morganstanley.com": 0.86,
        "goldmansachs.com": 0.86,
        "ubs.com": 0.84,
        "barclays.com": 0.83,
        # Asset managers
        "blackrock.com": 0.85,
        "vanguard.com": 0.83,
        "fidelity.com": 0.83,
        "pimco.com": 0.83,
        # Ratings / market intelligence
        "spglobal.com": 0.85,
        "fitchratings.com": 0.85,
        "moodys.com": 0.85,
        "morningstar.com": 0.8,
        # Official macro institutions
        "federalreserve.gov": 0.85,
        "bis.org": 0.84,
        "imf.org": 0.83,
        "worldbank.org": 0.8,
    }

    def __init__(self, settings: Settings):
        self.settings = settings

    async def search_company_news(self, symbol: str, company_name: str | None = None, count: int = 5) -> list[dict]:
        query = symbol if not company_name else f"{symbol} {company_name} earnings guidance risk"
        rows = await self._search_brave(query=query, count=count)
        out: list[dict] = []
        for item in rows[:count]:
            out.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "description": item.get("description", ""),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return out

    async def search_institutional_reports(
        self,
        symbol: str,
        company_name: str | None = None,
        count: int = 6,
        depth: str = "standard",
    ) -> list[dict]:
        if not self.settings.brave_api_key:
            return []

        queries = self._institutional_queries(symbol=symbol, company_name=company_name, depth=depth)
        per_query_count = min(20, max(8, count * 2))
        tasks = [self._search_brave(query=q, count=per_query_count) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        dedup: dict[str, dict] = {}
        for rows in results:
            if isinstance(rows, Exception):
                continue
            for item in rows:
                url = str(item.get("url", "")).strip()
                if not url or url in dedup:
                    continue
                dedup[url] = item

        ranked: list[dict] = []
        for item in dedup.values():
            url = str(item.get("url", "")).strip()
            domain = self._extract_domain(url)
            trusted_domain, domain_weight = self._trusted_domain_weight(domain)
            if not trusted_domain:
                continue
            quality = self._quality_score(item=item, base_weight=domain_weight)
            ranked.append(
                {
                    "title": item.get("title"),
                    "url": url,
                    "description": item.get("description", ""),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "source_type": "institutional_report",
                    "institution_domain": trusted_domain,
                    "source_quality": round(quality, 3),
                }
            )

        ranked.sort(key=lambda row: (row.get("source_quality", 0.0), row.get("title", "")), reverse=True)
        return ranked[:count]

    async def _search_brave(self, query: str, count: int) -> list[dict]:
        if not self.settings.brave_api_key:
            return []

        headers = {"Accept": "application/json", "X-Subscription-Token": self.settings.brave_api_key}
        params = {"q": query, "count": min(max(count, 1), 20)}

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.get("https://api.search.brave.com/res/v1/web/search", headers=headers, params=params)

        if resp.status_code >= 400:
            return []

        payload = resp.json()
        return payload.get("web", {}).get("results", [])

    def _institutional_queries(self, symbol: str, company_name: str | None, depth: str) -> list[str]:
        company_chunk = symbol if not company_name else f"{symbol} {company_name}"
        top_domains = [
            "jpmorganchase.com",
            "morganstanley.com",
            "goldmansachs.com",
            "blackrock.com",
            "spglobal.com",
            "fitchratings.com",
            "moodys.com",
            "morningstar.com",
        ]
        domain_hint = "(" + " OR ".join(f"site:{d}" for d in top_domains) + ")"
        queries = [
            f"{company_chunk} equity research report outlook {domain_hint}",
            f"{company_chunk} earnings guidance analyst report {domain_hint}",
            f"{symbol} credit rating outlook report {domain_hint}",
        ]
        if depth == "deep":
            macro_hint = "(site:federalreserve.gov OR site:bis.org OR site:imf.org OR site:worldbank.org)"
            queries.append(f"{company_chunk} sector outlook financial institution report {macro_hint}")
        return queries

    @staticmethod
    def _extract_domain(url: str) -> str:
        if not url:
            return ""
        try:
            host = urlparse(url).netloc.lower()
        except Exception:  # noqa: BLE001
            return ""
        return host[4:] if host.startswith("www.") else host

    def _trusted_domain_weight(self, domain: str) -> tuple[str, float]:
        if not domain:
            return "", 0.0
        for trusted_domain, weight in self.INSTITUTION_DOMAIN_WEIGHTS.items():
            if domain == trusted_domain or domain.endswith(f".{trusted_domain}"):
                return trusted_domain, weight
        return "", 0.0

    @staticmethod
    def _quality_score(item: dict, base_weight: float) -> float:
        title = str(item.get("title", "")).lower()
        description = str(item.get("description", "")).lower()
        url = str(item.get("url", "")).lower()
        text = f"{title} {description}"

        boost = 0.0
        for keyword in ["research", "report", "outlook", "analysis", "earnings", "rating", "forecast"]:
            if keyword in text:
                boost += 0.015
        if ".pdf" in url:
            boost += 0.05
        if "press release" in text:
            boost -= 0.03

        return max(0.5, min(0.99, base_weight + boost))
