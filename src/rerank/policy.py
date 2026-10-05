"""Sliding-window local-timeout policy for optional cloud L2 fallback."""

from __future__ import annotations

import threading
import time
from collections import deque


class TimeoutWindow:
    def __init__(self, span: int = 5, threshold: int = 3, ttl_s: int = 600):
        if span < 1 or not 1 <= threshold <= span or ttl_s < 0:
            raise ValueError("require span >= threshold >= 1 and ttl_s >= 0")
        self.span = span
        self.threshold = threshold
        self.ttl_s = ttl_s
        self._windows: dict[str, deque[bool]] = {}
        self._last_activity: dict[str, float] = {}
        self._lock = threading.Lock()

    def record(self, session_id: str, timed_out: bool) -> None:
        now = time.time()
        with self._lock:
            last = self._last_activity.get(session_id)
            if last is not None and now - last > self.ttl_s:
                self._windows.pop(session_id, None)
            window = self._windows.setdefault(session_id, deque(maxlen=self.span))
            window.append(bool(timed_out))
            self._last_activity[session_id] = now

    def should_downgrade(self, session_id: str) -> bool:
        now = time.time()
        with self._lock:
            last = self._last_activity.get(session_id)
            if last is None or now - last > self.ttl_s:
                return False
            return sum(self._windows.get(session_id, ())) >= self.threshold
