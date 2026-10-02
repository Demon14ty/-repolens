"""A tiny, short-lived, in-process cache of analyses.

This is NOT durable storage. On Vercel each function instance has its own
memory, instances are recycled at any time, and two requests may land on
different instances. The cache only saves repeated GitHub downloads when a
follow-up request (a question, an AI explanation) happens to reach a warm
instance; every caller must cope with a miss by re-running the analysis.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from models.repo_models import RepoAnalysis

TTL_SECONDS = 15 * 60
MAX_ENTRIES = 8  # each analysis holds at most ~1.5 MB of downloaded text


@dataclass
class CachedAnalysis:
    analysis: RepoAnalysis
    tree_truncated: bool
    created: float


class AnalysisCache:
    def __init__(self, ttl: float = TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._items: OrderedDict[str, CachedAnalysis] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> CachedAnalysis | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            if time.monotonic() - item.created > self.ttl:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return item

    def put(self, key: str, analysis: RepoAnalysis, tree_truncated: bool) -> CachedAnalysis:
        item = CachedAnalysis(analysis=analysis, tree_truncated=tree_truncated, created=time.monotonic())
        with self._lock:
            self._items[key] = item
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
        return item

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
