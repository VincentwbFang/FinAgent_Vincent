from __future__ import annotations

import math
from statistics import mean

from app.schemas import PriceBar


class RiskAgent:
    def run(self, bars: list[PriceBar]) -> dict:
        if len(bars) < 30:
            return {"volatility_annualized": None, "max_drawdown": None, "risk_flags": ["Insufficient price history"]}

        closes = [b.close for b in bars]
        returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1] > 0]
        avg = mean(returns)
        variance = mean([(r - avg) ** 2 for r in returns]) if returns else 0.0
        volatility = math.sqrt(variance) * math.sqrt(252)

        peak = closes[0]
        max_dd = 0.0
        for px in closes:
            peak = max(peak, px)
            if peak > 0:
                dd = (px - peak) / peak
                max_dd = min(max_dd, dd)

        flags: list[str] = []
        if volatility > 0.45:
            flags.append("High annualized volatility")
        if max_dd < -0.35:
            flags.append("Deep historical drawdown")
        if not flags:
            flags.append("No extreme risk signal from price-only model")

        return {
            "volatility_annualized": round(volatility, 4),
            "max_drawdown": round(max_dd, 4),
            "risk_flags": flags,
        }
