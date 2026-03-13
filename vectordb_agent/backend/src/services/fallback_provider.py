"""Fallback Vector Database Provider.

Wraps a *primary* and a *fallback* ``VectorDatabaseProvider`` so that
store operations are replicated to both, while search operations
automatically degrade to the fallback when the primary fails or
returns empty results.
"""

from typing import List, Dict, Optional
from loguru import logger
from src.interfaces import VectorDatabaseProvider, Document, SearchResult

class FallbackVectorDatabaseProvider(VectorDatabaseProvider):
    """A provider that attempts to use a primary database, and falls back to a secondary database."""
    def __init__(self, primary: VectorDatabaseProvider, fallback: VectorDatabaseProvider):
        self.primary = primary
        self.fallback = fallback

    def store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        # Store in both to ensure fallback is always up to date
        primary_success = False
        try:
            primary_success = self.primary.store(collection_name, documents, embeddings)
        except Exception as e:
            logger.error("Primary DB store failed: {}", e)
            
        fallback_success = False
        try:
            fallback_success = self.fallback.store(collection_name, documents, embeddings)
        except Exception as e:
            logger.error("Fallback DB store failed: {}", e)
            
        return primary_success or fallback_success

    def search(self, collection_name: str, query: str, query_vector: List[float], top_k: int = 5, filters: Optional[Dict] = None) -> List[SearchResult]:
        try:
            results = self.primary.search(collection_name, query, query_vector, top_k, filters)
            if results:
                return results
        except Exception as e:
            logger.error("Primary DB search failed: {}", e)

        logger.info("Falling back to secondary DB...")
        try:
            return self.fallback.search(collection_name, query, query_vector, top_k, filters)
        except Exception as e:
            logger.error("Fallback DB search failed: {}", e)
            return []
