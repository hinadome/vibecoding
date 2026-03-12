"""Qdrant Vector Database Provider.

Implements ``VectorDatabaseProvider`` using the ``qdrant-client`` SDK (v1.17+).
Supports local in-memory or file-based persistence.
"""

import uuid
from typing import List, Dict, Optional
from loguru import logger
from qdrant_client import QdrantClient, models
from src.interfaces import VectorDatabaseProvider, Document, SearchResult


def _deterministic_uuid(name: str) -> str:
    """Generate a deterministic UUID-5 from an arbitrary string.

    Qdrant requires point IDs to be either integers or valid UUIDs.
    We hash the document ``name`` (e.g. ``filename_chunkIndex``) into
    a reproducible UUID so upserts are idempotent.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


class LocalQdrantProvider(VectorDatabaseProvider):
    """Local, in-memory or file-based Qdrant vector database provider.

    Args:
        path:      ``":memory:"`` for ephemeral storage, or a filesystem
                   path (e.g. ``"./qdrant_data"``) for persistent storage.
        dimension: Size of the embedding vectors (default 384 for
                   ``all-MiniLM-L6-v2``).
    """

    def __init__(self, path: str = ":memory:", dimension: int = 384):
        if path == ":memory:":
            self.client = QdrantClient(location=":memory:")
        else:
            self.client = QdrantClient(path=path)
        self.dimension = dimension

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_collection(self, collection_name: str) -> None:
        """Create the collection if it does not already exist."""
        if not self.client.collection_exists(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self.dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection '{}'.", collection_name)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def store(
        self,
        collection_name: str,
        documents: List[Document],
        embeddings: List[List[float]],
    ) -> bool:
        """Upsert documents and their embeddings into a Qdrant collection."""
        if not documents:
            return True

        self._ensure_collection(collection_name)

        points = [
            models.PointStruct(
                id=_deterministic_uuid(doc.id),
                vector=emb,
                payload={"content": doc.content, **doc.metadata},
            )
            for doc, emb in zip(documents, embeddings)
        ]

        self.client.upsert(collection_name=collection_name, points=points)
        logger.debug("Upserted {} points into '{}'.", len(points), collection_name)
        return True

    def search(
        self,
        collection_name: str,
        query: str,
        query_vector: List[float],
        top_k: int = 5,
        filters: Optional[Dict] = None,
    ) -> List[SearchResult]:
        """Search the collection using ``query_points`` (qdrant-client ≥ 1.17)."""
        if not self.client.collection_exists(collection_name):
            return []

        # Build optional filter
        query_filter = None
        if filters:
            conditions = [
                models.FieldCondition(
                    key=k, match=models.MatchValue(value=v)
                )
                for k, v in filters.items()
            ]
            query_filter = models.Filter(must=conditions)

        response = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

        search_results: List[SearchResult] = []
        for scored_point in response.points:
            payload = dict(scored_point.payload or {})
            content = payload.pop("content", "")

            doc = Document(
                id=str(scored_point.id),
                content=content,
                metadata=payload,
            )
            search_results.append(
                SearchResult(document=doc, score=scored_point.score)
            )

        return search_results

