from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class ReportAgent:
    def build(
        self,
        symbol: str,
        research: dict,
        valuation: dict,
        risk: dict,
        citations: list[dict],
        llm_meta: dict,
        extra_metrics: dict[str, Any] | None = None,
    ) -> dict:
        risk_flags = []
        risk_flags.extend(research.get("risk_flags", []))
        risk_flags.extend(risk.get("risk_flags", []))

        metrics = {
            **valuation.get("metrics", {}),
            "volatility_annualized": risk.get("volatility_annualized"),
            "max_drawdown": risk.get("max_drawdown"),
            **(extra_metrics or {}),
        }

        confidence, reliability = self._compute_confidence(
            research=research,
            valuation=valuation,
            risk=risk,
            citations=citations,
            llm_meta=llm_meta,
            metrics=metrics,
        )

        report = {
            "symbol": symbol.upper(),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "thesis": research.get("thesis", "Evidence-based thesis generated."),
            "key_points": research.get("key_points", []),
            "scenarios": valuation["scenarios"],
            "target_range": valuation["target_range"],
            "risk_flags": list(dict.fromkeys(risk_flags)),
            "confidence": round(confidence, 2),
            "reliability": reliability,
            "assumptions": {
                **valuation.get("assumptions", {}),
                "llm_model_used": llm_meta.get("model_used"),
            },
            "metrics": metrics,
            "deep_dive": research.get("deep_dive", {}),
            "narrative": "",
            "narrative_en": "",
            "narrative_zh": "",
            "citations": citations,
        }
        report["narrative_en"] = self._to_narrative_en(report)
        report["narrative_zh"] = self._to_narrative_zh(report)
        report["narrative"] = report["narrative_en"]
        return report

    def _compute_confidence(
        self,
        research: dict[str, Any],
        valuation: dict[str, Any],
        risk: dict[str, Any],
        citations: list[dict[str, Any]],
        llm_meta: dict[str, Any],
        metrics: dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        try:
            score = float(research.get("confidence", 0.6))
        except Exception:  # noqa: BLE001
            score = 0.6

        score = max(0.2, min(0.97, score))
        components: dict[str, float] = {}

        def add_component(name: str, delta: float) -> None:
            nonlocal score
            score += delta
            components[name] = round(delta, 4)

        scenarios = valuation.get("scenarios", {})
        base_case = scenarios.get("base")
        bull_case = scenarios.get("bull")
        bear_case = scenarios.get("bear")
        current_price = metrics.get("current_price")

        if not current_price or not base_case:
            # No usable market model means lower trust in estimate quality.
            add_component("missing_market_model", -0.18)

        if llm_meta.get("model_used") == "local_fallback":
            add_component("llm_local_fallback", -0.07)
        elif llm_meta.get("model_used"):
            add_component("llm_external_model", 0.03)

        vol = risk.get("volatility_annualized")
        if isinstance(vol, (int, float)):
            # Continuous penalty: avoids clustering confidence at one fixed value.
            vol_penalty = max(0.0, float(vol) - 0.2) * 0.2
            add_component("volatility_penalty", -min(vol_penalty, 0.18))

        max_dd = risk.get("max_drawdown")
        if isinstance(max_dd, (int, float)):
            dd_penalty = max(0.0, abs(float(max_dd)) - 0.25) * 0.12
            add_component("drawdown_penalty", -min(dd_penalty, 0.08))

        if isinstance(base_case, (int, float)) and isinstance(bull_case, (int, float)) and isinstance(bear_case, (int, float)):
            denom = abs(float(base_case)) if base_case else 0.0
            if denom > 0:
                spread_ratio = abs(float(bull_case) - float(bear_case)) / denom
                add_component("scenario_spread_penalty", -min(spread_ratio * 0.05, 0.1))
                if float(bull_case) > float(base_case) > float(bear_case):
                    add_component("scenario_order_reward", 0.03)
                else:
                    add_component("scenario_order_penalty", -0.08)

        if len(citations) < 2:
            add_component("citation_count_penalty", -0.06)
        else:
            add_component("citation_count_reward", min(0.03, 0.005 * len(citations)))
        unique_sources = len({c.get("source", "") for c in citations if c.get("source")})
        if unique_sources >= 3:
            add_component("source_diversity_reward", 0.03)
        elif unique_sources == 2:
            add_component("source_diversity_reward", 0.015)

        sec_source_count = sum(1 for c in citations if str(c.get("source", "")).startswith("sec_"))
        institutional_source_count = sum(
            1 for c in citations if str(c.get("source", "")).startswith("institutional_report")
        )
        news_source_count = sum(1 for c in citations if str(c.get("source", "")) == "news_search_brave")
        if sec_source_count >= 2:
            add_component("sec_evidence_reward", 0.04)
        elif sec_source_count == 0:
            add_component("sec_evidence_penalty", -0.08)

        if institutional_source_count >= 3:
            add_component("institutional_evidence_reward", 0.05)
        elif institutional_source_count >= 1:
            add_component("institutional_evidence_reward", 0.02)

        if institutional_source_count > 0 and sec_source_count > 0:
            add_component("cross_tier_evidence_reward", 0.02)
        if news_source_count >= 4 and news_source_count > (sec_source_count + institutional_source_count):
            add_component("news_dominance_penalty", -0.03)

        peers = research.get("deep_dive", {}).get("peer_positioning", {}).get("data", {}).get("peers", [])
        if isinstance(peers, list) and len(peers) >= 3:
            add_component("peer_coverage_reward", 0.02)

        if research.get("deep_dive"):
            add_component("deep_dive_reward", 0.03)

        data_quality = metrics.get("data_quality", {})
        bars_count = data_quality.get("bars_count")
        if isinstance(bars_count, int):
            if bars_count >= 252:
                add_component("bars_coverage_reward", 0.05)
            elif bars_count >= 120:
                add_component("bars_coverage_reward", 0.02)
            else:
                add_component("bars_coverage_penalty", -0.04)

        price_age_days = data_quality.get("price_age_days")
        if isinstance(price_age_days, int):
            if price_age_days <= 2:
                add_component("price_freshness_reward", 0.03)
            elif price_age_days <= 5:
                add_component("price_freshness_reward", 0.01)
            elif price_age_days >= 10:
                add_component("price_freshness_penalty", -0.05)

        crosscheck_diff_pct = data_quality.get("crosscheck_diff_pct")
        if isinstance(crosscheck_diff_pct, (int, float)):
            diff = abs(float(crosscheck_diff_pct))
            if diff <= 0.01:
                add_component("crosscheck_consistency_reward", 0.04)
            elif diff <= 0.03:
                add_component("crosscheck_consistency_reward", 0.02)
            elif diff >= 0.05:
                add_component("crosscheck_consistency_penalty", -0.06)

        final_score = round(max(0.2, min(0.97, score)), 2)
        reliability = {
            "score": final_score,
            "grade": self._grade(final_score),
            "trustworthy_for_decisions": final_score >= 0.9,
            "components": components,
            "note": "Score is a reliability heuristic, not probability of returns.",
        }
        return final_score, reliability

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 0.9:
            return "A"
        if score >= 0.8:
            return "B"
        if score >= 0.65:
            return "C"
        if score >= 0.5:
            return "D"
        return "E"

    def render_narratives(self, report: dict[str, Any]) -> tuple[str, str]:
        return self._to_narrative_en(report), self._to_narrative_zh(report)

    def _to_narrative_en(self, report: dict[str, Any]) -> str:
        symbol = report["symbol"]
        confidence = report.get("confidence", 0.0)
        reliability = report.get("reliability", {})
        scenarios = report.get("scenarios", {})
        target = report.get("target_range", {})
        metrics = report.get("metrics", {})
        technical = metrics.get("technical_profile", {})
        peers = metrics.get("peer_snapshot", {}).get("peers", [])
        deep = report.get("deep_dive", {})
        key_points = report.get("key_points", [])

        p1 = (
            f"{symbol} investment view: {report.get('thesis', '')} "
            f"Overall confidence is {confidence:.2f} on a 0 to 1 scale "
            f"(grade {reliability.get('grade', 'N/A')}, decision-trust flag: {reliability.get('trustworthy_for_decisions', False)})."
        )

        p2 = (
            f"Valuation summary: the base-case estimate is {scenarios.get('base')}, "
            f"with a bear-case of {scenarios.get('bear')} and bull-case of {scenarios.get('bull')}. "
            f"This implies a target range of {target.get('low')} to {target.get('high')} over the modeled horizon."
        )

        tech_bits = []
        if technical and "note" not in technical:
            tech_bits.append(
                f"price is {technical.get('current_price')}, with SMA50 at {technical.get('sma50')} "
                f"and SMA200 at {technical.get('sma200')}"
            )
            if technical.get("rsi14") is not None:
                tech_bits.append(f"RSI(14) is {technical.get('rsi14')}")
            if technical.get("ret_12m") is not None:
                tech_bits.append(f"12-month return is {technical.get('ret_12m')}")
            if technical.get("trend_signals"):
                tech_bits.append(f"trend signal: {', '.join(technical.get('trend_signals', []))}")
        elif technical.get("note"):
            tech_bits.append(technical["note"])
        p3 = "Technical context: " + "; ".join(tech_bits) + "." if tech_bits else "Technical context: unavailable."

        peer_text = "Peer positioning: no reliable peer comparison was available."
        if peers:
            top = sorted([p for p in peers if p.get("ret_12m") is not None], key=lambda x: x["ret_12m"], reverse=True)[:3]
            peer_str = ", ".join(f"{row['symbol']} ({row['ret_12m']})" for row in top)
            median_12m = metrics.get("peer_snapshot", {}).get("peer_median_12m")
            peer_text = (
                f"Peer positioning: highest trailing 12-month peer returns include {peer_str}. "
                f"The peer median 12-month return is {median_12m}."
            )

        risk_flags = report.get("risk_flags", [])
        p5 = (
            "Primary risks: " + "; ".join(risk_flags) + "."
            if risk_flags
            else "Primary risks: no specific red flags were detected by the current model."
        )

        watch_items = deep.get("watch_items", [])
        catalysts = deep.get("catalysts", [])
        p6 = ""
        if key_points:
            p6 += "Key points: " + "; ".join(key_points[:4]) + ". "
        if catalysts:
            p6 += "Catalysts to monitor: " + "; ".join(catalysts[:3]) + ". "
        if watch_items:
            p6 += "Next checkpoints: " + "; ".join(watch_items[:3]) + "."
        if not p6.strip():
            p6 = "No additional qualitative checkpoints were produced."

        return "\n\n".join([p1, p2, p3, peer_text, p5, p6])

    def _to_narrative_zh(self, report: dict[str, Any]) -> str:
        def zh(text: Any) -> str:
            if text is None:
                return ""
            s = str(text)
            table = {
                "analysis generated from SEC and market evidence.": "基于 SEC 与市场数据生成的分析结果。",
                "Macro slowdown could compress multiples.": "宏观增长放缓可能压缩估值倍数。",
                "Execution risk on guidance and margin targets.": "公司在业绩指引与利润率目标上存在执行风险。",
                "No extreme risk signal from price-only model.": "仅基于价格模型未发现极端风险信号。",
                "High annualized volatility": "年化波动率较高",
                "Deep historical drawdown": "历史回撤较深",
                "Insufficient price history": "价格历史不足",
                "medium-term trend above long-term trend": "中期趋势高于长期趋势",
                "medium-term trend below long-term trend": "中期趋势低于长期趋势",
                "RSI indicates overbought conditions": "RSI 显示可能处于超买区间",
                "RSI indicates oversold conditions": "RSI 显示可能处于超卖区间",
                "Data center demand and AI infrastructure cycle strength.": "数据中心需求与 AI 基础设施周期强度。",
                "Product roadmap execution in accelerators and software stack.": "加速芯片与软件生态路线图的执行情况。",
                "Large customer concentration and capex cadence changes.": "大客户集中度与资本开支节奏变化。",
                "Gross margin trend vs prior quarters.": "与前期相比的毛利率趋势。",
                "Inventory and receivables changes.": "库存与应收账款变化。",
                "Guidance revisions in subsequent filings/calls.": "后续财报或电话会中的业绩指引修订。",
                "Model fallback used. Summary: prioritize cited SEC facts, market trend, and volatility-aware bull/base/bear scenarios.": "当前使用本地回退模型；分析优先依据 SEC 引用事实、市场趋势与波动率情景。",
            }
            if s in table:
                return table[s]
            s = s.replace("analysis generated from SEC and market evidence.", "基于 SEC 与市场数据生成的分析结果。")
            s = s.replace("No extreme risk signal from price-only model.", "仅基于价格模型未发现极端风险信号。")
            s = s.replace("No extreme risk signal from price-only model", "仅基于价格模型未发现极端风险信号")
            return s

        symbol = report["symbol"]
        confidence = report.get("confidence", 0.0)
        reliability = report.get("reliability", {})
        scenarios = report.get("scenarios", {})
        target = report.get("target_range", {})
        metrics = report.get("metrics", {})
        technical = metrics.get("technical_profile", {})
        peers = metrics.get("peer_snapshot", {}).get("peers", [])
        deep = report.get("deep_dive", {})
        key_points = report.get("key_points", [])

        p1 = (
            f"{symbol} 投资观点：{zh(report.get('thesis', ''))} 当前综合置信度为 {confidence:.2f}（范围 0 到 1），"
            f"评级为 {reliability.get('grade', 'N/A')}，可用于关键决策标记为 {reliability.get('trustworthy_for_decisions', False)}。"
        )

        p2 = (
            f"估值结论：基准情景为 {scenarios.get('base')}，"
            f"悲观情景为 {scenarios.get('bear')}，乐观情景为 {scenarios.get('bull')}。"
            f"在当前模型假设下，目标区间约为 {target.get('low')} 至 {target.get('high')}。"
        )

        tech_bits: list[str] = []
        if technical and "note" not in technical:
            tech_bits.append(
                f"最新价格 {technical.get('current_price')}，SMA50 为 {technical.get('sma50')}，"
                f"SMA200 为 {technical.get('sma200')}"
            )
            if technical.get("rsi14") is not None:
                tech_bits.append(f"RSI(14) 为 {technical.get('rsi14')}")
            if technical.get("ret_12m") is not None:
                tech_bits.append(f"近 12 个月收益为 {technical.get('ret_12m')}")
            if technical.get("trend_signals"):
                trend_text = "；".join(zh(x) for x in technical.get("trend_signals", []))
                tech_bits.append(f"趋势信号：{trend_text}")
        elif technical.get("note"):
            tech_bits.append(zh(technical["note"]))
        p3 = "技术面： " + "；".join(tech_bits) + "。" if tech_bits else "技术面：当前暂无足够数据。"

        peer_text = "同业比较：暂无足够可靠的可比样本。"
        if peers:
            top = sorted([p for p in peers if p.get("ret_12m") is not None], key=lambda x: x["ret_12m"], reverse=True)[:3]
            peer_str = "，".join(f"{row['symbol']}（{row['ret_12m']}）" for row in top)
            median_12m = metrics.get("peer_snapshot", {}).get("peer_median_12m")
            peer_text = f"同业比较：近 12 个月表现靠前的可比标的包括 {peer_str}。可比组 12 个月收益中位数为 {median_12m}。"

        risk_flags = report.get("risk_flags", [])
        p5 = (
            "主要风险：" + "；".join(zh(r) for r in risk_flags) + "。"
            if risk_flags
            else "主要风险：当前模型未识别到明显异常风险。"
        )

        watch_items = deep.get("watch_items", [])
        catalysts = deep.get("catalysts", [])
        parts: list[str] = []
        if key_points:
            parts.append("关键信息：" + "；".join(zh(x) for x in key_points[:4]) + "。")
        if catalysts:
            parts.append("催化因素：" + "；".join(zh(x) for x in catalysts[:3]) + "。")
        if watch_items:
            parts.append("后续观察点：" + "；".join(zh(x) for x in watch_items[:3]) + "。")
        p6 = " ".join(parts) if parts else "暂无额外的定性观察点。"

        return "\n\n".join([p1, p2, p3, peer_text, p5, p6])
