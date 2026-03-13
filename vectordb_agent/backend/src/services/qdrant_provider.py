"""Qdrant Vector Database Provider.

Implements ``VectorDatabaseProvider`` using the Qdrant local storage engine.
This provider utilizes a dedicated single-threaded executor to ensure that 
all SQLite-based interactions happen on a single background worker thread, 
ensuring full compatibility with SQLite's thread-affinity model and providing 
connection consistency across parallel FastAPI worker threads.
"""

import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional
from loguru import logger
from qdrant_client import QdrantClient, models
from src.interfaces import VectorDatabaseProvider, Document, SearchResult


def _deterministic_uuid(name: str) -> str:
    """
    Generate a deterministic UUID-5 from a string identifier.
    
    Qdrant requires point IDs to be valid UUIDs or integers. Using UUID-5 
    allows us to map arbitrary document IDs (like filenames) to a stable 
    UUID, ensuring idempotent upserts.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


class LocalQdrantProvider(VectorDatabaseProvider):
    """
    Enhanced Local Qdrant Provider with serialized worker-thread execution.
    
    Architecture:
        This provider maintains a private `ThreadPoolExecutor` with a single 
        worker. All calls to the Qdrant client are dispatched to this dedicated 
        thread. This architectural pattern resolves two critical issues:
        1. **SQLite Thread Isolation**: Ensures the client is created and used 
           on the same thread.
        2. **Connection Consistency**: Guarantees that in-memory collections 
           or persistent locks are shared correctly across the application lifetime.
    """

    def __init__(self, path: str = ":memory:", dimension: int = 384):
        self._path = path
        self._dimension = dimension
        self._client: QdrantClient | None = None
        # Use a single-threaded executor to isolate all DB operations
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="QdrantWorker")

    def _get_client(self) -> QdrantClient:
        """
        Lazily initialize the Qdrant client within the dedicated worker thread.
        """
        if self._client is None:
            logger.debug("Initialising Qdrant local client at '{}'.", self._path)
            if self._path == ":memory:":
                self._client = QdrantClient(location=":memory:")
            else:
                self._client = QdrantClient(path=self._path)
        return self._client

    def _ensure_collection(self, collection_name: str) -> None:
        """
        Internal helper to create a collection if it does not exist.
        """
        client = self._get_client()
        if not client.collection_exists(collection_name):
            logger.info("Creating new Qdrant collection: '{}'", collection_name)
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self._dimension,
                    distance=models.Distance.COSINE,
                ),
            )

    def _sync_store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        """
        Synchronous core of the store operation.
        """
        try:
            if not documents:
                return True

            self._ensure_collection(collection_name)
            client = self._get_client()

            points = [
                models.PointStruct(
                    id=_deterministic_uuid(doc.id),
                    vector=emb,
                    payload={"content": doc.content, **doc.metadata},
                )
                for doc, emb in zip(documents, embeddings)
            ]

            client.upsert(collection_name=collection_name, points=points)
            logger.debug("Qdrant: Upserted {} points to '{}'.", len(points), collection_name)
            return True
        except Exception as e:
            logger.error("Qdrant Store Error: {}", e)
            return False

    def _sync_search(
        self, 
        collection_name: str, 
        query_vector: List[float], 
        top_k: int, 
        filters: Optional[Dict]
    ) -> List[SearchResult]:
        """
        Synchronous core of the search operation.
        """
        try:
            client = self._get_client()
            if not client.collection_exists(collection_name):
                return []

            query_filter = None
            if filters:
                conditions = [
                    models.FieldCondition(key=k, match=models.MatchValue(value=v))
                    for k, v in filters.items()
                ]
                query_filter = models.Filter(must=conditions)

            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )

            results = []
            for point in response.points:
                payload = dict(point.payload or {})
                content = payload.pop("content", "")
                doc = Document(id=str(point.id), content=content, metadata=payload)
                results.append(SearchResult(document=doc, score=point.score))
                
            return results
        except Exception as e:
            logger.error("Qdrant Search Error: {}", e)
            return []

    # -------------------------------------------------------------------------
    # Public Interface (VectorDatabaseProvider)
    # -------------------------------------------------------------------------

    def store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        """
        Dispatches the store request to the dedicated Qdrant worker thread.
        """
        future = self._executor.submit(self._sync_store, collection_name, documents, embeddings)
        return future.result()

    def search(
        self, 
        collection_name: str, 
        query: str, 
        query_vector: List[float], 
        top_k: int = 5, 
        filters: Optional[Dict] = None
    ) -> List[SearchResult]:
        """
        Dispatches the search request to the dedicated Qdrant worker thread.
        """
        future = self._executor.submit(self._sync_search, collection_name, query_vector, top_k, filters)
        return future.result()

