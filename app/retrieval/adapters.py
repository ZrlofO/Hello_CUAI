from __future__ import annotations

from typing import Callable, Iterable, List

from .models import SearchResult


class LegacyJobSearchAdapter:
    """Adapts the existing server scraping functions without importing server.py."""

    def __init__(self, source_name: str, fetcher: Callable[[str, int], Iterable[dict]]):
        self.source_name = source_name
        self.fetcher = fetcher

    def search(self, query: str, limit: int) -> List[SearchResult]:
        results: List[SearchResult] = []
        for item in self.fetcher(query, limit) or []:
            url = str(item.get("url", ""))
            if not url.lower().startswith(("http://", "https://")):
                continue
            results.append(
                SearchResult(
                    source_name=self.source_name,
                    title=str(item.get("title", "채용 공고")),
                    url=url,
                    snippet=str(item.get("reason", "")),
                    publisher=str(item.get("company", "")) or None,
                    query=query,
                )
            )
        return results
