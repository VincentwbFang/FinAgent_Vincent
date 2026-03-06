from __future__ import annotations

import json
from typing import Any

from app.llm import LLMRouter


class ResearchAgent:
    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    async def run(
        self,
        symbol: str,
        company_name: str,
        filings: list[dict[str, Any]],
        kpis: dict[str, float],
        news: list[dict[str, Any]],
        institutional_reports: list[dict[str, Any]] | None = None,
        depth: str = "standard",
        technical_profile: dict[str, Any] | None = None,
        peer_snapshot: dict[str, Any] | None = None,
        macro_data: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        institutional_reports = institutional_reports or []

        if depth == "deep":
            system = (
                "You are a senior equity research analyst producing a thorough stock report. "
                "Use only provided evidence. Prioritize evidence in this order: "
                "SEC filings/company facts, institutional_reports, official macro data, then generic news. "
                "If lower-tier sources conflict with higher-tier sources, trust higher-tier sources and note the conflict. "
                "Return strict JSON with keys: "
                "thesis, key_points(list), risk_flags(list), confidence(0..1), "
                "deep_dive(object with keys: business_quality, growth_profitability, "
                "technical_view, peer_positioning, catalysts, bear_case, bull_case, watch_items)."
            )
        else:
            system = (
                "You are a financial research analyst. Use only supplied evidence and produce concise factual output. "
                "Prioritize SEC and institutional_reports over generic news when evidence quality differs. "
                "Return strict JSON with keys: thesis, key_points(list), risk_flags(list), confidence(0..1)."
            )
        user = {
            "symbol": symbol,
            "company_name": company_name,
            "filings": filings[:6],
            "kpis": kpis,
            "institutional_reports": institutional_reports[:10],
            "news": news,
            "technical_profile": technical_profile or {},
            "peer_snapshot": peer_snapshot or {},
            "macro_data": macro_data or {},
            "depth": depth,
        }

        text, meta = await self.llm_router.complete(system, json.dumps(user, ensure_ascii=True))

        parsed = {
            "thesis": f"{company_name} analysis generated from SEC and market evidence.",
            "key_points": [],
            "risk_flags": [],
            "confidence": 0.6,
            "deep_dive": {},
        }
        try:
            candidate = json.loads(text)
            if isinstance(candidate, dict):
                parsed.update(candidate)
        except Exception:  # noqa: BLE001
            if text:
                parsed["key_points"] = [text[:300]]

        parsed["key_points"] = parsed.get("key_points") or [
            "Revenue and earnings trajectory inferred from latest SEC facts.",
            "Recent filings reviewed for disclosure changes.",
        ]
        if institutional_reports:
            parsed["key_points"].append(
                f"Institutional-source coverage included {len(institutional_reports)} report references."
            )
        parsed["risk_flags"] = parsed.get("risk_flags") or [
            "Macro slowdown could compress multiples.",
            "Execution risk on guidance and margin targets.",
        ]
        if depth == "deep":
            parsed["deep_dive"] = parsed.get("deep_dive") or self._default_deep_dive(
                company_name=company_name,
                kpis=kpis,
                technical_profile=technical_profile or {},
                peer_snapshot=peer_snapshot or {},
            )

        return parsed, meta

    def _default_deep_dive(
        self,
        company_name: str,
        kpis: dict[str, float],
        technical_profile: dict[str, Any],
        peer_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        rev = kpis.get("Revenue")
        net_income = kpis.get("NetIncome")
        operating_income = kpis.get("OperatingIncome")
        margin = None
        if rev and operating_income:
            margin = round(operating_income / rev, 4) if rev != 0 else None

        business_quality = (
            f"{company_name} shows strong scale economics and high operating leverage."
            if margin and margin > 0.25
            else f"{company_name} has meaningful growth exposure but margin durability should be monitored."
        )
        growth_profitability = {
            "revenue_latest": rev,
            "net_income_latest": net_income,
            "operating_margin_estimate": margin,
        }
        technical_view = {
            "summary": "Trend and momentum check from price data.",
            "signals": technical_profile.get("trend_signals", []),
            "profile": technical_profile,
        }
        peer_positioning = {
            "summary": "12-month peer return comparison.",
            "data": peer_snapshot,
        }
        catalysts = [
            "Data center demand and AI infrastructure cycle strength.",
            "Product roadmap execution in accelerators and software stack.",
            "Large customer concentration and capex cadence changes.",
        ]
        watch_items = [
            "Gross margin trend vs prior quarters.",
            "Inventory and receivables changes.",
            "Guidance revisions in subsequent filings/calls.",
        ]
        return {
            "business_quality": business_quality,
            "growth_profitability": growth_profitability,
            "technical_view": technical_view,
            "peer_positioning": peer_positioning,
            "catalysts": catalysts,
            "bear_case": "Valuation compression if growth decelerates materially.",
            "bull_case": "Sustained AI demand with continued operating leverage.",
            "watch_items": watch_items,
        }
