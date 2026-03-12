import uuid
import threading
from typing import List, Dict, Optional
from loguru import logger
from qdrant_client import QdrantClient, models
from src.interfaces import VectorDatabaseProvider, Document, SearchResult

def _deterministic_uuid(name: str) -> str:
    """
    Converts a string (like a filename or chunk ID) into a valid UUID-5.
    
    WHY: Qdrant requires IDs to be UUIDs or Integers. Using a deterministic 
    UUID ensures that if you ingest the same file twice, it overwrites 
    the old data (idempotency) instead of creating duplicates.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))

class LocalQdrantProvider(VectorDatabaseProvider):
    """
    A local Qdrant provider that handles thread-safety for SQLite-based storage.
    
    SQLite (which Qdrant uses for local metadata storage) forbids sharing 
    connections across threads. We solve this by giving every thread its 
    own private instance of the QdrantClient.
    """

    def __init__(self, path: str = ":memory:", dimension: int = 384):
        self._path = path
        self._dimension = dimension
        
        # THREAD-LOCAL STORAGE:
        # This object acts like a dictionary that is unique to the current thread.
        # Data stored here is invisible to other threads.
        self._thread_local = threading.local()

    def _get_client(self) -> QdrantClient:
        """
        Lazily initializes the Qdrant client for the current thread.
        
        This is the most critical part: 
        1. If the Main Thread calls this, it gets Client A.
        2. If Worker Thread 1 calls this, it gets Client B.
        Because Client B is created *inside* Worker Thread 1, SQLite is happy.
        """
        if not hasattr(self._thread_local, "client"):
            thread_name = threading.current_thread().name
            logger.debug("Establishing new Qdrant connection for thread: {}", thread_name)
            
            # Choose between in-memory (ephemeral) or disk-based (persistent)
            if self._path == ":memory:":
                self._thread_local.client = QdrantClient(location=":memory:")
            else:
                self._thread_local.client = QdrantClient(path=self._path)
                
        return self._thread_local.client

    def _ensure_collection(self, collection_name: str) -> None:
        """
        Verifies the collection exists before we try to write to it.
        Uses Cosine Similarity as the default distance metric.
        """
        client = self._get_client()
        if not client.collection_exists(collection_name):
            logger.info("Collection '{}' not found. Creating new collection...", collection_name)
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=self._dimension,
                    distance=models.Distance.COSINE,
                ),
            )

    def store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        """
        Upserts (Updates or Inserts) document points into the database.
        
        Args:
            collection_name: Target collection.
            documents: List of Document objects containing text and metadata.
            embeddings: List of numerical vectors corresponding to the documents.
        """
        try:
            if not documents:
                return True

            # 1. Ensure the collection exists on the current thread's client
            self._ensure_collection(collection_name)
            client = self._get_client()

            # 2. Map documents to Qdrant's PointStruct format
            points = [
                models.PointStruct(
                    id=_deterministic_uuid(doc.id), # Ensures no duplicates
                    vector=emb,
                    payload={
                        "content": doc.content, # We store the text in the payload
                        **doc.metadata          # We unpack user metadata into the payload
                    },
                )
                for doc, emb in zip(documents, embeddings)
            ]

            # 3. Perform the bulk upsert
            client.upsert(collection_name=collection_name, points=points)
            logger.debug("Successfully stored {} points in thread {}.", 
                         len(points), threading.current_thread().name)
            return True
        except Exception as e:
            # We catch all errors and log them via Loguru for debugging
            logger.error("Local Qdrant Store Failed (Thread {}): {}", 
                         threading.current_thread().name, e)
            return False

    def search(self, collection_name: str, query: str, query_vector: List[float], 
               top_k: int = 5, filters: Optional[Dict] = None) -> List[SearchResult]:
        """
        Performs a vector similarity search.
        
        Returns:
            A list of SearchResult objects containing the document and its similarity score.
        """
        try:
            client = self._get_client()
            if not client.collection_exists(collection_name):
                return []

            # 1. Convert simple dict filters into Qdrant's Filter/MatchValue objects
            query_filter = None
            if filters:
                conditions = [
                    models.FieldCondition(key=k, match=models.MatchValue(value=v))
                    for k, v in filters.items()
                ]
                query_filter = models.Filter(must=conditions)

            # 2. Execute the vector search
            response = client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True, # Ensure we get the text content back
            )

            # 3. Parse points back into our standardized SearchResult interface
            results = []
            for point in response.points:
                payload = dict(point.payload or {})
                # Extract content from payload; if missing, default to empty string
                content = payload.pop("content", "")
                
                doc = Document(id=str(point.id), content=content, metadata=payload)
                results.append(SearchResult(document=doc, score=point.score))
                
            return results
        except Exception as e:
            logger.error("Local Qdrant Search Failed (Thread {}): {}", 
                         threading.current_thread().name, e)
            return []
