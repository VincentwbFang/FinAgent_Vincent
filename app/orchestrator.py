from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.agents import ReportAgent, ResearchAgent, RiskAgent, ValuationAgent
from app.config import Settings
from app.llm import LLMRouter
from app.quota import QuotaManager
from app.storage import Storage
from app.tools import (
    MacroClient,
    MarketDataClient,
    SearchClient,
    SecClient,
    compute_peer_snapshot,
    compute_technical_profile,
    select_top_correlated_peers,
)


class Orchestrator:
    def __init__(self, settings: Settings, storage: Storage):
        self.settings = settings
        self.storage = storage
        self.quota = QuotaManager(settings.llm_limits)
        self.llm_router = LLMRouter(settings, self.quota)

        self.sec = SecClient(settings)
        self.market = MarketDataClient(settings)
        self.macro = MacroClient(settings)
        self.search = SearchClient(settings)

        self.research_agent = ResearchAgent(self.llm_router)
        self.valuation_agent = ValuationAgent()
        self.risk_agent = RiskAgent()
        self.report_agent = ReportAgent()

    async def run_job(self, job_id: str, request_payload: dict[str, Any]) -> None:
        symbol = request_payload["symbol"].upper()
        include_macro = bool(request_payload.get("include_macro", True))
        horizon_days = int(request_payload.get("horizon_days", 365))
        depth = str(request_payload.get("depth", "standard"))

        try:
            self.storage.update_job(job_id, status="running", progress=5)
            company = await self.sec.resolve_symbol(symbol)
            if not company:
                company = {"symbol": symbol, "cik": "", "title": symbol}

            self.storage.update_job(job_id, status="running", progress=15)
            if company.get("cik"):
                submissions_task = self.sec.get_submissions(company["cik"])
                facts_task = self.sec.get_company_facts(company["cik"])
            else:
                submissions_task = asyncio.sleep(0, result={})
                facts_task = asyncio.sleep(0, result={})
            market_task = self.market.get_price_series(symbol)
            macro_task = self.macro.get_blended_macro() if include_macro else asyncio.sleep(0, result={})
            news_task = self.search.search_company_news(symbol, company_name=company.get("title"), count=5)

            submissions, company_facts, market_data, macro_data, news = await asyncio.gather(
                submissions_task,
                facts_task,
                market_task,
                macro_task,
                news_task,
                return_exceptions=True,
            )

            if isinstance(submissions, Exception):
                submissions = {}
            if isinstance(company_facts, Exception):
                company_facts = {}
            if isinstance(market_data, Exception):
                bars, market_provider = [], "none"
            else:
                bars, market_provider = market_data
            if isinstance(macro_data, Exception):
                macro_data = {}
            if isinstance(news, Exception):
                news = []

            self.storage.update_job(job_id, status="running", progress=45)
            kpis = self.sec.extract_latest_kpis(company_facts)
            filings = self.sec.recent_10k_10q(submissions)
            technical_profile = compute_technical_profile(bars)
            peer_snapshot: dict[str, Any] = {}
            if depth == "deep":
                peer_prices = await self._fetch_peer_prices(self._peer_universe(symbol))
                chosen_peers = select_top_correlated_peers(target_bars=bars, peer_prices=peer_prices, max_peers=5)
                selected_prices = {peer: peer_prices[peer] for peer in chosen_peers if peer in peer_prices}
                peer_snapshot = compute_peer_snapshot(selected_prices)
                peer_snapshot["selection_basis"] = "top_correlation_12m"

            research, llm_meta = await self.research_agent.run(
                symbol=symbol,
                company_name=company.get("title", symbol),
                filings=filings,
                kpis=kpis,
                news=news,
                depth=depth,
                technical_profile=technical_profile,
                peer_snapshot=peer_snapshot,
                macro_data=macro_data if include_macro else {},
            )

            self.storage.update_job(job_id, status="running", progress=70)
            valuation = self.valuation_agent.run(bars=bars, horizon_days=horizon_days)
            risk = self.risk_agent.run(bars=bars)
            crosscheck_close: float | None = None
            if market_provider != "none":
                try:
                    crosscheck_close = await self.market.get_stooq_reference_close(symbol)
                except Exception:  # noqa: BLE001
                    crosscheck_close = None

            latest_price_date = bars[-1].date if bars else None
            price_age_days: int | None = None
            if latest_price_date is not None:
                now_date = datetime.now(timezone.utc).date()
                price_age_days = max(0, (now_date - latest_price_date.date()).days)

            crosscheck_diff_pct: float | None = None
            if bars and crosscheck_close and bars[-1].close != 0:
                crosscheck_diff_pct = (bars[-1].close - crosscheck_close) / bars[-1].close

            extra_metrics: dict[str, Any] = {
                "technical_profile": technical_profile,
                "data_quality": {
                    "bars_count": len(bars),
                    "market_provider": market_provider,
                    "latest_price_date": latest_price_date.isoformat() if latest_price_date else None,
                    "price_age_days": price_age_days,
                    "crosscheck_provider": "stooq",
                    "crosscheck_close": round(crosscheck_close, 4) if isinstance(crosscheck_close, float) else None,
                    "crosscheck_diff_pct": round(crosscheck_diff_pct, 4) if isinstance(crosscheck_diff_pct, float) else None,
                },
            }
            if include_macro and macro_data:
                extra_metrics["macro"] = macro_data
            if peer_snapshot:
                extra_metrics["peer_snapshot"] = peer_snapshot

            citations: list[dict[str, str]] = []
            if company.get("cik"):
                citations.append(
                    {
                        "source": "sec_submissions",
                        "url": f"https://data.sec.gov/submissions/CIK{company['cik']}.json",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                citations.append(
                    {
                        "source": "sec_companyfacts",
                        "url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company['cik']}.json",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            if market_provider == "fmp":
                citations.append(
                    {
                        "source": "market_data_fmp",
                        "url": "https://financialmodelingprep.com/developer/docs/",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            elif market_provider == "alpha_vantage":
                citations.append(
                    {
                        "source": "market_data_alpha_vantage",
                        "url": "https://www.alphavantage.co/documentation/",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            elif market_provider == "stooq":
                citations.append(
                    {
                        "source": "market_data_stooq",
                        "url": "https://stooq.com/db/h/",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            for n in news:
                citations.append(
                    {
                        "source": "news_search_brave",
                        "url": n.get("url", ""),
                        "retrieved_at": n.get("retrieved_at", datetime.now(timezone.utc).isoformat()),
                    }
                )

            report = self.report_agent.build(
                symbol=symbol,
                research=research,
                valuation=valuation,
                risk=risk,
                citations=citations,
                llm_meta=llm_meta,
                extra_metrics=extra_metrics,
            )

            narrative_en, narrative_zh = self.report_agent.render_narratives(report)
            report["narrative_en"] = narrative_en
            report["narrative_zh"] = narrative_zh
            report["narrative"] = narrative_en

            self.storage.save_report(job_id, report)
            self.storage.update_job(job_id, status="done", progress=100)
        except Exception as exc:  # noqa: BLE001
            self.storage.update_job(job_id, status="failed", progress=100, error=str(exc))

    @staticmethod
    def _peer_universe(symbol: str) -> list[str]:
        universe = [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "GOOGL",
            "META",
            "TSLA",
            "AVGO",
            "AMD",
            "QCOM",
            "INTC",
            "TSM",
            "JPM",
            "XOM",
            "UNH",
            "JNJ",
            "WMT",
            "COST",
            "KO",
            "PEP",
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
        ]
        return [ticker for ticker in universe if ticker != symbol]

    async def _fetch_peer_prices(self, peers: list[str]) -> dict[str, Any]:
        tasks = [self.market.get_price_series(peer) for peer in peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: dict[str, Any] = {}
        for peer, result in zip(peers, results):
            if isinstance(result, Exception):
                continue
            bars, _provider = result
            out[peer] = bars
        return out
