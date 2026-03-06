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
        try:
            payload = json.loads(user_prompt)
        except Exception:  # noqa: BLE001
            payload = {}

        symbol = str(payload.get("symbol", "UNKNOWN")).upper()
        company_name = str(payload.get("company_name", symbol))
        filings = payload.get("filings", []) if isinstance(payload.get("filings"), list) else []
        kpis = payload.get("kpis", {}) if isinstance(payload.get("kpis"), dict) else {}
        technical = payload.get("technical_profile", {}) if isinstance(payload.get("technical_profile"), dict) else {}
        peer_snapshot = payload.get("peer_snapshot", {}) if isinstance(payload.get("peer_snapshot"), dict) else {}
        macro_data = payload.get("macro_data", {}) if isinstance(payload.get("macro_data"), dict) else {}
        institutional_reports = (
            payload.get("institutional_reports", []) if isinstance(payload.get("institutional_reports"), list) else []
        )
        depth = str(payload.get("depth", "standard"))

        key_points: list[str] = []
        risk_flags: list[str] = []
        confidence = 0.58

        if filings:
            filing_labels = [str(row.get("form", "")) for row in filings if isinstance(row, dict) and row.get("form")]
            if filing_labels:
                key_points.append(f"SEC filing coverage: {', '.join(filing_labels[:4])}.")
                confidence += 0.06
        else:
            risk_flags.append("No recent SEC filings were included.")
            confidence -= 0.07

        revenue = kpis.get("Revenue")
        net_income = kpis.get("NetIncome")
        if isinstance(revenue, (int, float)):
            key_points.append(f"Latest reported revenue reference is {round(float(revenue), 2)}.")
            confidence += 0.03
        if isinstance(net_income, (int, float)):
            key_points.append(f"Latest reported net income reference is {round(float(net_income), 2)}.")

        current_price = technical.get("current_price")
        ret_12m = technical.get("ret_12m")
        if isinstance(current_price, (int, float)):
            key_points.append(f"Current market price context is {round(float(current_price), 2)}.")
            confidence += 0.04
        else:
            risk_flags.append("Technical price profile is unavailable.")
            confidence -= 0.12

        if isinstance(ret_12m, (int, float)):
            key_points.append(f"Trailing 12-month return signal is {round(float(ret_12m), 4)}.")
            if ret_12m < -0.2:
                risk_flags.append("Negative 12-month momentum trend.")
            elif ret_12m > 0.2:
                key_points.append("Momentum trend is positive over the last 12 months.")

        peers = peer_snapshot.get("peers", []) if isinstance(peer_snapshot, dict) else []
        if isinstance(peers, list) and peers:
            top_peers = [str(row.get("symbol", "")) for row in peers[:3] if isinstance(row, dict) and row.get("symbol")]
            if top_peers:
                key_points.append(f"Peer context considered: {', '.join(top_peers)}.")
                confidence += 0.02

        if institutional_reports:
            domains = []
            for row in institutional_reports[:5]:
                if not isinstance(row, dict):
                    continue
                d = row.get("institution_domain")
                if d:
                    domains.append(str(d))
            if domains:
                key_points.append(f"Institutional report references: {', '.join(domains[:3])}.")
            confidence += 0.05
        else:
            risk_flags.append("Institutional report coverage was limited.")
            confidence -= 0.05

        if macro_data:
            macro_keys = [k for k, v in macro_data.items() if v is not None]
            if macro_keys:
                key_points.append(f"Macro signals included: {', '.join(macro_keys[:3])}.")

        rsi = technical.get("rsi14")
        if isinstance(rsi, (int, float)):
            if rsi > 70:
                risk_flags.append("RSI indicates overbought conditions.")
            elif rsi < 30:
                risk_flags.append("RSI indicates oversold conditions.")

        trend_signals = technical.get("trend_signals", []) if isinstance(technical, dict) else []
        if isinstance(trend_signals, list):
            for sig in trend_signals[:2]:
                if sig:
                    key_points.append(str(sig))

        if not key_points:
            key_points = [
                "Fallback analysis used due unavailable cloud model.",
                "Prioritized available SEC filings, market trend signals, and risk checks.",
            ]
        if not risk_flags:
            risk_flags = ["No extreme risk flag from fallback model."]

        thesis = (
            f"{company_name} ({symbol}) shows a mixed risk/reward setup based on available regulatory and market evidence."
        )
        if isinstance(ret_12m, (int, float)) and ret_12m > 0.2:
            thesis = f"{company_name} ({symbol}) maintains constructive momentum, but valuation and execution risks remain."
        elif isinstance(ret_12m, (int, float)) and ret_12m < -0.2:
            thesis = f"{company_name} ({symbol}) faces weak momentum and requires stronger fundamental confirmation."

        deep_dive = {}
        if depth == "deep":
            deep_dive = {
                "business_quality": "Assessment based on latest reported KPIs and filing cadence.",
                "growth_profitability": {
                    "revenue_latest": revenue,
                    "net_income_latest": net_income,
                },
                "technical_view": {
                    "summary": "Fallback technical summary from available price bars.",
                    "profile": technical,
                },
                "peer_positioning": {
                    "summary": "Fallback peer comparison from available peer snapshot.",
                    "data": peer_snapshot,
                },
                "catalysts": [
                    "Next earnings release and guidance revision.",
                    "Margin and demand trends in upcoming filing updates.",
                ],
                "bear_case": "Execution misses and valuation compression drive downside.",
                "bull_case": "Sustained demand and stable margins support upside.",
                "watch_items": [
                    "Revenue growth versus prior periods.",
                    "Operating leverage and margin trend.",
                ],
            }

        confidence = max(0.3, min(0.82, confidence))
        result: dict[str, Any] = {
            "thesis": thesis,
            "key_points": key_points[:8],
            "risk_flags": list(dict.fromkeys(risk_flags))[:8],
            "confidence": round(confidence, 2),
        }
        if depth == "deep":
            result["deep_dive"] = deep_dive
        return json.dumps(result, ensure_ascii=True)


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
