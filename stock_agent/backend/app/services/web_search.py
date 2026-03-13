from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import List

import httpx

from app.config import Settings
from app.models import Source

logger = logging.getLogger("uvicorn.error")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearcher:
    def __init__(self, settings: Settings) -> None:
        """
        Purpose: Store provider config used by all web-search strategies.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `settings` (Settings): Input parameter used by this function.
        Returns:
        - `None`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `__init__(settings=...)`
        """
        self.settings = settings

    async def search(self, query: str, limit: int = 6) -> List[Source]:
        """
        Purpose: Run provider-specific search and normalize deduplicated Source objects.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `query` (str): Input parameter used by this function.
        - `limit` (int): Input parameter used by this function.
        Returns:
        - `List[Source]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `search(query=..., limit=...)`
        """
        started = time.perf_counter()
        provider = "duckduckgo"
        if self.settings.exa_api_key:
            provider = "exa"
        elif self.settings.tavily_api_key:
            provider = "tavily"
        elif self.settings.serper_api_key:
            provider = "serper"
        if self.settings.app_env == "dev":
            logger.info(
                "Web search request provider=%s limit=%d query=%s",
                provider,
                limit,
                query[:180],
            )
        if self.settings.exa_api_key:
            results = await self._search_exa(query, limit)
        elif self.settings.tavily_api_key:
            results = await self._search_tavily(query, limit)
        elif self.settings.serper_api_key:
            results = await self._search_serper(query, limit)
        else:
            results = await self._search_duckduckgo(query, limit)

        unique_urls: set[str] = set()
        sources: List[Source] = []
        for result in results:
            if not result.url or result.url in unique_urls:
                continue
            unique_urls.add(result.url)
            sources.append(
                Source(
                    title=result.title.strip() or "Untitled",
                    url=result.url,
                    snippet=result.snippet.strip(),
                    source_type="web",
                )
            )
        if self.settings.app_env == "dev":
            logger.info(
                "Web search completed provider=%s deduped_sources=%d elapsed_ms=%d",
                provider,
                len(sources),
                int((time.perf_counter() - started) * 1000),
            )
        return sources

    async def _search_exa(self, query: str, limit: int) -> List[SearchResult]:
        """
        Purpose: Query Exa search endpoint and map response into SearchResult records.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `query` (str): Input parameter used by this function.
        - `limit` (int): Input parameter used by this function.
        Returns:
        - `List[SearchResult]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_search_exa(query=..., limit=...)`
        """
        headers = {
            "x-api-key": self.settings.exa_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "numResults": limit,
            "contents": {"text": {"maxCharacters": 1200}},
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.exa.ai/search",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        results: List[SearchResult] = []
        for item in data.get("results", []):
            text = str(item.get("text", "") or "")
            snippet = text[:400] if text else str(item.get("highlights", "") or "")
            results.append(
                SearchResult(
                    title=str(item.get("title", "") or ""),
                    url=str(item.get("url", "") or ""),
                    snippet=snippet,
                )
            )
        return results[:limit]

    async def _search_tavily(self, query: str, limit: int) -> List[SearchResult]:
        """
        Purpose: Query Tavily and map its response format into SearchResult records.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `query` (str): Input parameter used by this function.
        - `limit` (int): Input parameter used by this function.
        Returns:
        - `List[SearchResult]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_search_tavily(query=..., limit=...)`
        """
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": limit,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()

        results: List[SearchResult] = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                )
            )
        return results

    async def _search_serper(self, query: str, limit: int) -> List[SearchResult]:
        """
        Purpose: Query Serper Google API and map organic results into SearchResult.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `query` (str): Input parameter used by this function.
        - `limit` (int): Input parameter used by this function.
        Returns:
        - `List[SearchResult]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_search_serper(query=..., limit=...)`
        """
        headers = {
            "X-API-KEY": self.settings.serper_api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": query, "num": limit},
            )
            response.raise_for_status()
            data = response.json()

        results: List[SearchResult] = []
        for item in data.get("organic", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                )
            )
        return results

    async def _search_duckduckgo(self, query: str, limit: int) -> List[SearchResult]:
        """
        Purpose: Fallback search using DuckDuckGo Instant Answer + related topics.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `query` (str): Input parameter used by this function.
        - `limit` (int): Input parameter used by this function.
        Returns:
        - `List[SearchResult]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_search_duckduckgo(query=..., limit=...)`
        """
        params = {
            "q": query,
            "format": "json",
            "no_redirect": 1,
            "no_html": 1,
            "skip_disambig": 1,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://api.duckduckgo.com/", params=params)
            response.raise_for_status()
            data = response.json()

        results: List[SearchResult] = []
        if data.get("AbstractURL"):
            results.append(
                SearchResult(
                    title=data.get("Heading", query),
                    url=data.get("AbstractURL", ""),
                    snippet=data.get("AbstractText", ""),
                )
            )

        for topic in data.get("RelatedTopics", []):
            if len(results) >= limit:
                break
            if "Text" in topic and "FirstURL" in topic:
                results.append(
                    SearchResult(
                        title=topic.get("Text", "").split(" - ")[0],
                        url=topic.get("FirstURL", ""),
                        snippet=topic.get("Text", ""),
                    )
                )
            elif "Topics" in topic:
                for nested in topic.get("Topics", []):
                    if len(results) >= limit:
                        break
                    if "Text" in nested and "FirstURL" in nested:
                        results.append(
                            SearchResult(
                                title=nested.get("Text", "").split(" - ")[0],
                                url=nested.get("FirstURL", ""),
                                snippet=nested.get("Text", ""),
                            )
                        )
        return results[:limit]
