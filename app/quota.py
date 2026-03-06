from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from app.config import ProviderLimits


class QuotaManager:
    def __init__(self, limits: dict[str, ProviderLimits]):
        self.limits = limits
        self._minute_windows: dict[str, deque[datetime]] = defaultdict(deque)
        self._day_windows: dict[str, deque[datetime]] = defaultdict(deque)

    def allow(self, provider: str) -> bool:
        limit = self.limits.get(provider)
        if not limit:
            return True

        now = datetime.now(timezone.utc)
        minute_cutoff = now - timedelta(minutes=1)
        day_cutoff = now - timedelta(days=1)

        minute_q = self._minute_windows[provider]
        day_q = self._day_windows[provider]

        while minute_q and minute_q[0] < minute_cutoff:
            minute_q.popleft()
        while day_q and day_q[0] < day_cutoff:
            day_q.popleft()

        if len(minute_q) >= limit.per_minute:
            return False
        if len(day_q) >= limit.per_day:
            return False

        minute_q.append(now)
        day_q.append(now)
        return True
