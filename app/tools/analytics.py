from __future__ import annotations

import math
from statistics import mean, median
from typing import Iterable

from app.schemas import PriceBar


def _safe_return(new: float, old: float) -> float | None:
    if old == 0:
        return None
    return new / old - 1


def _window_return(closes: list[float], lookback: int) -> float | None:
    if len(closes) <= lookback:
        return None
    return _safe_return(closes[-1], closes[-lookback - 1])


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return mean(closes[-period:])


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for i in range(len(closes) - period, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))

    avg_gain = mean(gains)
    avg_loss = mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_technical_profile(bars: list[PriceBar]) -> dict:
    if len(bars) < 30:
        return {"note": "Insufficient bars for technical profile"}

    closes = [b.close for b in bars]
    returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1] > 0]

    peak = closes[0]
    max_dd = 0.0
    for px in closes:
        peak = max(peak, px)
        dd = (px - peak) / peak if peak else 0.0
        max_dd = min(max_dd, dd)

    variance = mean([(r - mean(returns)) ** 2 for r in returns]) if returns else 0.0
    annual_vol = math.sqrt(variance) * math.sqrt(252)

    profile = {
        "current_price": round(closes[-1], 2),
        "sma20": round(_sma(closes, 20), 2) if _sma(closes, 20) is not None else None,
        "sma50": round(_sma(closes, 50), 2) if _sma(closes, 50) is not None else None,
        "sma200": round(_sma(closes, 200), 2) if _sma(closes, 200) is not None else None,
        "rsi14": round(_rsi(closes, 14), 2) if _rsi(closes, 14) is not None else None,
        "ret_1m": _window_return(closes, 21),
        "ret_3m": _window_return(closes, 63),
        "ret_6m": _window_return(closes, 126),
        "ret_12m": _window_return(closes, 252),
        "volatility_annualized": round(annual_vol, 4),
        "max_drawdown": round(max_dd, 4),
    }

    for key in ["ret_1m", "ret_3m", "ret_6m", "ret_12m"]:
        if profile[key] is not None:
            profile[key] = round(float(profile[key]), 4)

    trend_signals: list[str] = []
    if profile.get("sma50") and profile.get("sma200"):
        if profile["sma50"] > profile["sma200"]:
            trend_signals.append("medium-term trend above long-term trend")
        else:
            trend_signals.append("medium-term trend below long-term trend")
    if profile.get("rsi14") is not None:
        if profile["rsi14"] > 70:
            trend_signals.append("RSI indicates overbought conditions")
        elif profile["rsi14"] < 30:
            trend_signals.append("RSI indicates oversold conditions")

    profile["trend_signals"] = trend_signals
    return profile


def compute_peer_snapshot(peer_prices: dict[str, list[PriceBar]]) -> dict:
    rows: list[dict] = []
    for symbol, bars in peer_prices.items():
        if len(bars) < 30:
            continue
        closes = [b.close for b in bars]
        ret_12m = _window_return(closes, 252)
        rows.append(
            {
                "symbol": symbol,
                "last": round(closes[-1], 2),
                "ret_12m": round(ret_12m, 4) if ret_12m is not None else None,
            }
        )

    valid = [r["ret_12m"] for r in rows if r["ret_12m"] is not None]
    med = median(valid) if valid else None
    out = {
        "peers": rows,
        "peer_median_12m": round(med, 4) if med is not None else None,
    }
    return out


def aligned_returns(bars: list[PriceBar], lookback: int = 252) -> list[float]:
    if len(bars) < 3:
        return []
    closes = [b.close for b in bars][-lookback:]
    out: list[float] = []
    for i in range(1, len(closes)):
        old = closes[i - 1]
        new = closes[i]
        if old > 0:
            out.append(new / old - 1)
    return out


def correlation(x: Iterable[float], y: Iterable[float]) -> float | None:
    xv = list(x)
    yv = list(y)
    n = min(len(xv), len(yv))
    if n < 20:
        return None

    xv = xv[-n:]
    yv = yv[-n:]
    mx = mean(xv)
    my = mean(yv)
    cov = sum((a - mx) * (b - my) for a, b in zip(xv, yv)) / n
    vx = sum((a - mx) ** 2 for a in xv) / n
    vy = sum((b - my) ** 2 for b in yv) / n
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def select_top_correlated_peers(
    target_bars: list[PriceBar],
    peer_prices: dict[str, list[PriceBar]],
    max_peers: int = 5,
) -> list[str]:
    target_r = aligned_returns(target_bars)
    ranked: list[tuple[str, float]] = []
    for symbol, bars in peer_prices.items():
        peer_r = aligned_returns(bars)
        corr = correlation(target_r, peer_r)
        if corr is None:
            continue
        ranked.append((symbol, corr))

    ranked.sort(key=lambda item: item[1], reverse=True)
    return [symbol for symbol, _ in ranked[:max_peers]]
