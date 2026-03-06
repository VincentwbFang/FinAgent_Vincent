from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.config import Settings


class MacroClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def get_blended_macro(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        cpi = await self.get_bls_latest_cpi()
        if cpi is not None:
            data["cpi_latest"] = cpi
        gdp = await self.get_bea_latest_gdp_growth()
        if gdp is not None:
            data["gdp_growth_latest"] = gdp
        return data

    async def get_bls_latest_cpi(self) -> float | None:
        # CPI-U (all items): CUUR0000SA0
        payload: dict[str, Any] = {
            "seriesid": ["CUUR0000SA0"],
            "startyear": str(datetime.now().year - 2),
            "endyear": str(datetime.now().year),
        }
        if self.settings.bls_api_key:
            payload["registrationkey"] = self.settings.bls_api_key

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.post("https://api.bls.gov/publicAPI/v2/timeseries/data/", json=payload)

        if resp.status_code >= 400:
            return None
        data = resp.json()
        try:
            points = data["Results"]["series"][0]["data"]
            latest = next((p for p in points if p.get("period", "").startswith("M")), None)
            return float(latest["value"]) if latest else None
        except Exception:  # noqa: BLE001
            return None

    async def get_bea_latest_gdp_growth(self) -> float | None:
        if not self.settings.bea_api_key:
            return None

        url = (
            "https://apps.bea.gov/api/data"
            f"?UserID={self.settings.bea_api_key}&method=GetData&datasetname=NIPA"
            "&TableName=T10101&Frequency=Q&Year=X&ResultFormat=JSON"
        )
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            resp = await client.get(url)

        if resp.status_code >= 400:
            return None
        payload = resp.json()
        try:
            rows = payload["BEAAPI"]["Results"]["Data"]
            gdp_rows = [r for r in rows if r.get("LineDescription") == "Gross domestic product"]
            if len(gdp_rows) < 2:
                return None
            latest = float(gdp_rows[0]["DataValue"].replace(",", ""))
            prior = float(gdp_rows[1]["DataValue"].replace(",", ""))
            if prior == 0:
                return None
            return (latest - prior) / prior
        except Exception:  # noqa: BLE001
            return None
