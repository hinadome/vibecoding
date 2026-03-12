"""ChromaDB Vector Database Provider.

Implements ``VectorDatabaseProvider`` using ChromaDB as a local fallback.

This provider uses a dedicated single-threaded executor for all database
operations to satisfy SQLite's threading model (avoiding the *"objects
created in a thread can only be used in that same thread"* error).
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional
from loguru import logger
import chromadb
from src.interfaces import VectorDatabaseProvider, Document, SearchResult


class LocalChromaProvider(VectorDatabaseProvider):
    """Local, file-based ChromaDB vector database provider.

    Uses a dedicated worker thread (single-thread executor) to ensure
    all SQLite interactions happen on the same thread, regardless of
    which thread pool ``asyncio.to_thread`` uses.
    """

    def __init__(self, path: str = "./chroma_data"):
        self._path = path
        self._client: chromadb.ClientAPI | None = None
        # Single-threaded executor to isolate SQLite connection
        self._executor = ThreadPoolExecutor(max_workers=1)

    def _get_client(self) -> chromadb.ClientAPI:
        """Lazily initialize the ChromaDB client on the worker thread."""
        if self._client is None:
            logger.info("Initialising ChromaDB PersistentClient at '{}'.", self._path)
            self._client = chromadb.PersistentClient(path=self._path)
        return self._client

    def _ensure_collection(self, collection_name: str) -> chromadb.Collection:
        """Get or create a collection on the worker thread."""
        client = self._get_client()
        return client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def _sync_store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        """Synchronous part of the store operation."""
        if not documents:
            return True
            
        collection = self._ensure_collection(collection_name)
        
        ids = [doc.id for doc in documents]
        texts = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )
        return True

    def _sync_search(self, collection_name: str, query_vector: List[float], top_k: int, filters: Optional[Dict]) -> List[SearchResult]:
        """Synchronous part of the search operation."""
        client = self._get_client()
        try:
            collection = client.get_collection(name=collection_name)
        except ValueError:
            return []
            
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=filters,
            include=['documents', 'metadatas', 'distances']
        )
        
        search_results = []
        if not results['ids'] or not results['ids'][0]:
            return search_results
            
        for i in range(len(results['ids'][0])):
            doc_id = results['ids'][0][i]
            content = results['documents'][0][i] if results['documents'] else ""
            metadata = results['metadatas'][0][i] if results['metadatas'] else {}
            distance = results['distances'][0][i] if results['distances'] else 0.0
            score = 1.0 - distance
            
            doc = Document(
                id=str(doc_id),
                content=content,
                metadata=metadata
            )
            search_results.append(SearchResult(document=doc, score=score))
            
        return search_results

    def store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        """Submit the store operation to the dedicated worker thread."""
        future = self._executor.submit(self._sync_store, collection_name, documents, embeddings)
        return future.result()

    def search(self, collection_name: str, query: str, query_vector: List[float], top_k: int = 5, filters: Optional[Dict] = None) -> List[SearchResult]:
        """Submit the search operation to the dedicated worker thread."""
        future = self._executor.submit(self._sync_search, collection_name, query_vector, top_k, filters)
        return future.result()

