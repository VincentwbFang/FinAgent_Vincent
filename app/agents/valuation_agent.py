from __future__ import annotations

from statistics import mean

from app.schemas import PriceBar


class ValuationAgent:
    def run(self, bars: list[PriceBar], horizon_days: int) -> dict:
        if len(bars) < 30:
            return {
                "scenarios": {"bull": 0.0, "base": 0.0, "bear": 0.0},
                "target_range": {"low": 0.0, "high": 0.0},
                "assumptions": {"note": "Insufficient price history"},
                "metrics": {},
            }

        closes = [b.close for b in bars]
        current = closes[-1]
        lookback = min(252, len(closes) - 1)
        past = closes[-lookback - 1]
        if past <= 0:
            growth = 0.0
        else:
            growth = current / past - 1

        daily_returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1] > 0]
        drift_daily = mean(daily_returns[-lookback:]) if daily_returns else 0.0
        annualized_drift = drift_daily * 252

        horizon_years = horizon_days / 365
        base = current * (1 + annualized_drift * horizon_years)
        bull = base * 1.2
        bear = base * 0.8

        low = min(bull, base, bear)
        high = max(bull, base, bear)

        return {
            "scenarios": {"bull": round(bull, 2), "base": round(base, 2), "bear": round(bear, 2)},
            "target_range": {"low": round(low, 2), "high": round(high, 2)},
            "assumptions": {
                "horizon_days": horizon_days,
                "lookback_days": lookback,
                "price_growth_lookback": round(growth, 4),
                "annualized_drift": round(annualized_drift, 4),
            },
            "metrics": {
                "current_price": round(current, 2),
                "returns_sample": len(daily_returns),
            },
        }
