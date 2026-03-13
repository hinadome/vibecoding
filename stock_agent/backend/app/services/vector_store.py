from __future__ import annotations

import logging
import time
from typing import Any
from typing import List

import httpx

from app.config import Settings
from app.models import Source

logger = logging.getLogger("uvicorn.error")


class VectorRetriever:
    def __init__(self, settings: Settings) -> None:
        """
        Purpose: Store vector database settings used for semantic retrieval.
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

    @property
    def is_enabled(self) -> bool:
        """
        Purpose: Check whether vector retrieval can run with current configuration.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `bool`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `is_enabled()`
        """
        return bool(self.settings.qdrant_url and self.settings.qdrant_collection)

    async def search(self, vector: List[float], limit: int = 4) -> List[Source]:
        """
        Purpose: Search Qdrant for nearest documents and map them to Source objects.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `vector` (List[float]): Input parameter used by this function.
        - `limit` (int): Input parameter used by this function.
        Returns:
        - `List[Source]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `search(vector=..., limit=...)`
        """
        if not vector or not self.is_enabled:
            if self.settings.app_env == "dev":
                logger.info(
                    "Vector search skipped enabled=%s vector_dims=%d",
                    self.is_enabled,
                    len(vector),
                )
            return []
        started = time.perf_counter()
        if self.settings.app_env == "dev":
            logger.info(
                "Vector search request qdrant=%s collection=%s limit=%d vector_dims=%d",
                self.settings.qdrant_url,
                self.settings.qdrant_collection,
                limit,
                len(vector),
            )

        headers = {"Content-Type": "application/json"}
        if self.settings.qdrant_api_key:
            headers["api-key"] = self.settings.qdrant_api_key

        data = await self._search_points(vector=vector, limit=limit, headers=headers)

        sources: List[Source] = []
        for point in self._extract_points_from_response(data):
            payload = point.get("payload", {})
            sources.append(
                Source(
                    title=str(payload.get("title", "Vector document")),
                    url=str(payload.get("url", "vector://local")),
                    snippet=str(payload.get("text", ""))[:500],
                    source_type="vector",
                )
            )
        if self.settings.app_env == "dev":
            logger.info(
                "Vector search completed results=%d elapsed_ms=%d",
                len(sources),
                int((time.perf_counter() - started) * 1000),
            )
        return sources

    async def _search_points(
        self,
        vector: List[float],
        limit: int,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """
        Purpose: Search points using legacy endpoint and fallback to query endpoint.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `vector` (List[float]): Input parameter used by this function.
        - `limit` (int): Input parameter used by this function.
        - `headers` (dict[str, str]): Input parameter used by this function.
        Returns:
        - `dict[str, Any]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_search_points(vector=..., limit=..., headers=...)`
        """
        base = f"{self.settings.qdrant_url.rstrip('/')}/collections/{self.settings.qdrant_collection}/points"
        search_payload = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
        }
        query_payload = {
            "query": vector,
            "limit": limit,
            "with_payload": True,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                response = await client.post(
                    f"{base}/search",
                    headers=headers,
                    json=search_payload,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (404, 405):
                    raise
                # Fallback for Qdrant versions/environments using query endpoint.
                response = await client.post(
                    f"{base}/query",
                    headers=headers,
                    json=query_payload,
                )
                response.raise_for_status()
                return response.json()

    @staticmethod
    def _extract_points_from_response(data: dict[str, Any]) -> List[dict[str, Any]]:
        """
        Purpose: Normalize Qdrant search/query response formats into a points list.
        Args/Params:
        - `data` (dict[str, Any]): Input parameter used by this function.
        Returns:
        - `List[dict[str, Any]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_extract_points_from_response(data=...)`
        """
        result = data.get("result", [])
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            points = result.get("points", [])
            if isinstance(points, list):
                return [item for item in points if isinstance(item, dict)]
        return []

    async def upsert_points(self, points: List[dict]) -> int:
        """
        Purpose: Upsert vector points into Qdrant collection and return ingested count.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `points` (List[dict]): Input parameter used by this function.
        Returns:
        - `int`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `upsert_points(points=...)`
        """
        if not points or not self.is_enabled:
            if self.settings.app_env == "dev":
                logger.info(
                    "Vector upsert skipped enabled=%s points=%d",
                    self.is_enabled,
                    len(points),
                )
            return 0

        headers = {"Content-Type": "application/json"}
        if self.settings.qdrant_api_key:
            headers["api-key"] = self.settings.qdrant_api_key

        url = (
            f"{self.settings.qdrant_url.rstrip('/')}/collections/"
            f"{self.settings.qdrant_collection}/points"
        )
        payload = {"points": points}

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(url, headers=headers, json=payload)
            response.raise_for_status()

        if self.settings.app_env == "dev":
            logger.info(
                "Vector upsert completed points=%d elapsed_ms=%d",
                len(points),
                int((time.perf_counter() - started) * 1000),
            )
        return len(points)
