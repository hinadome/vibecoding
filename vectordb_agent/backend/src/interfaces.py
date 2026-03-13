from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class Document(BaseModel):
    id: str
    content: str
    metadata: Dict[str, Any]

class SearchResult(BaseModel):
    document: Document
    score: float

class Chunker(ABC):
    @abstractmethod
    def chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """Splits text into smaller chunks."""
        pass

class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Converts strings into semantic vectors."""
        pass

class DocumentProcessor(ABC):
    @abstractmethod
    def process_bytes(self, content: bytes, filename: str) -> str:
        """Extracts text from raw file bytes (e.g. PDF, Word, Image)."""
        pass

class VectorDatabaseProvider(ABC):
    @abstractmethod
    def store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        """Stores documents and their embeddings in the vector database."""
        pass

    @abstractmethod
    def search(self, collection_name: str, query: str, query_vector: List[float], top_k: int = 5, filters: Optional[Dict] = None) -> List[SearchResult]:
        """Searches the database using a vector and optional metadata filters."""
        pass
