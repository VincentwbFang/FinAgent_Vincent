from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings


class SecClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.headers = {
            "User-Agent": settings.sec_user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        self._fallback_symbol_map = {
            "NVDA": {"symbol": "NVDA", "cik": "0001045810", "title": "NVIDIA CORP"},
            "AAPL": {"symbol": "AAPL", "cik": "0000320193", "title": "Apple Inc."},
            "MSFT": {"symbol": "MSFT", "cik": "0000789019", "title": "MICROSOFT CORP"},
            "AMZN": {"symbol": "AMZN", "cik": "0001018724", "title": "AMAZON COM INC"},
            "GOOGL": {"symbol": "GOOGL", "cik": "0001652044", "title": "Alphabet Inc."},
            "META": {"symbol": "META", "cik": "0001326801", "title": "Meta Platforms, Inc."},
        }

    async def resolve_symbol(self, symbol: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, headers=self.headers) as client:
                resp = await client.get("https://www.sec.gov/files/company_tickers.json")
                resp.raise_for_status()
                data = resp.json()

            for row in data.values():
                if row["ticker"].upper() == symbol.upper():
                    cik = str(row["cik_str"]).zfill(10)
                    return {"symbol": symbol.upper(), "cik": cik, "title": row["title"]}
            return self.fallback_company(symbol)
        except Exception:  # noqa: BLE001
            return self.fallback_company(symbol)

    def fallback_company(self, symbol: str) -> dict[str, Any] | None:
        return self._fallback_symbol_map.get(symbol.upper())

    async def get_submissions(self, cik: str) -> dict[str, Any]:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, headers=self.headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def get_company_facts(self, cik: str) -> dict[str, Any]:
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, headers=self.headers) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def extract_latest_kpis(company_facts: dict[str, Any]) -> dict[str, float]:
        # Uses common US-GAAP tags if present.
        tags = {
            "Revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
            "NetIncome": ["NetIncomeLoss"],
            "OperatingIncome": ["OperatingIncomeLoss"],
            "Assets": ["Assets"],
            "Liabilities": ["Liabilities"],
        }
        us_gaap = company_facts.get("facts", {}).get("us-gaap", {})
        out: dict[str, float] = {}

        for key, candidates in tags.items():
            value = None
            for tag in candidates:
                node = us_gaap.get(tag)
                if not node:
                    continue
                units = node.get("units", {})
                for unit_rows in units.values():
                    if not unit_rows:
                        continue
                    # Prefer most recent by end date.
                    latest = sorted(
                        unit_rows,
                        key=lambda x: x.get("end", "1970-01-01"),
                        reverse=True,
                    )[0]
                    if latest.get("val") is not None:
                        value = float(latest["val"])
                        break
                if value is not None:
                    break
            if value is not None:
                out[key] = value

        return out

    @staticmethod
    def recent_10k_10q(submissions: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        out = []
        for idx, form in enumerate(forms):
            if form not in {"10-K", "10-Q", "8-K"}:
                continue
            accession = accession_numbers[idx].replace("-", "")
            cik = str(submissions.get("cik", "")).zfill(10)
            doc = primary_docs[idx]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{doc}"
            out.append(
                {
                    "form": form,
                    "filing_date": filing_dates[idx],
                    "accession": accession_numbers[idx],
                    "url": url,
                }
            )
            if len(out) >= limit:
                break
        return out


def clean_text(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
