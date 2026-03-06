from __future__ import annotations

from datetime import datetime

import httpx

from app.config import Settings
from app.schemas import PriceBar


class MarketDataClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_price_series(self, symbol: str, limit: int = 400) -> tuple[list[PriceBar], str]:
        if self.settings.fmp_api_key:
            bars = await self._from_fmp(symbol, limit)
            if bars:
                return bars, "fmp"

        if self.settings.alpha_vantage_api_key:
            bars = await self._from_alpha_vantage(symbol)
            if bars:
                return bars, "alpha_vantage"

        bars = await self._from_stooq(symbol, limit)
        if bars:
            return bars, "stooq"

        return [], "none"

    async def get_stooq_reference_close(self, symbol: str) -> float | None:
        bars = await self._from_stooq(symbol, limit=10)
        if not bars:
            return None
        return float(bars[-1].close)

    async def _from_fmp(self, symbol: str, limit: int) -> list[PriceBar]:
        url = (
            f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
            f"?timeseries={limit}&apikey={self.settings.fmp_api_key}"
        )
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.get(url)
        if resp.status_code >= 400:
            return []

        data = resp.json()
        rows = data.get("historical", [])
        out: list[PriceBar] = []
        for row in rows:
            out.append(
                PriceBar(
                    date=datetime.fromisoformat(row["date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                )
            )
        return sorted(out, key=lambda x: x.date)

    async def _from_alpha_vantage(self, symbol: str) -> list[PriceBar]:
        url = (
            "https://www.alphavantage.co/query"
            f"?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=full&apikey={self.settings.alpha_vantage_api_key}"
        )
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.get(url)
        if resp.status_code >= 400:
            return []

        data = resp.json().get("Time Series (Daily)", {})
        out: list[PriceBar] = []
        for date_str, row in data.items():
            out.append(
                PriceBar(
                    date=datetime.fromisoformat(date_str),
                    open=float(row["1. open"]),
                    high=float(row["2. high"]),
                    low=float(row["3. low"]),
                    close=float(row["4. close"]),
                    volume=float(row.get("6. volume", 0.0)),
                )
            )
        return sorted(out, key=lambda x: x.date)

    async def _from_stooq(self, symbol: str, limit: int) -> list[PriceBar]:
        # Stooq provides daily CSV with no API key. US equities use "<symbol>.US".
        ticker = f"{symbol.lower()}.us"
        url = f"https://stooq.com/q/d/l/?s={ticker}&i=d"
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.get(url)
        if resp.status_code >= 400:
            return []

        lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
        if len(lines) < 2 or not lines[0].lower().startswith("date,open,high,low,close,volume"):
            return []

        out: list[PriceBar] = []
        for row in lines[1:]:
            parts = row.split(",")
            if len(parts) != 6:
                continue
            date_str, open_s, high_s, low_s, close_s, vol_s = parts
            if "N/D" in row:
                continue
            try:
                out.append(
                    PriceBar(
                        date=datetime.fromisoformat(date_str),
                        open=float(open_s),
                        high=float(high_s),
                        low=float(low_s),
                        close=float(close_s),
                        volume=float(vol_s),
                    )
                )
            except Exception:  # noqa: BLE001
                continue

        out = sorted(out, key=lambda x: x.date)
        if limit > 0 and len(out) > limit:
            out = out[-limit:]
        return out
