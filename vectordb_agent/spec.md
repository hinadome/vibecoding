# Search Agent Specification

## 1. Overview
This document outlines the architecture, specifications, and considerations for the "Search Agent," an application designed to ingest various file types into a vector database, perform powerful hybrid searches (vector + text/context), and expose its functionalities to other agents via the Model Context Protocol (MCP) and a dedicated Agent-to-Agent (2A2) remote endpoint.

The system is separated into a Python-based backend (FastAPI) and a Next.js (React) frontend.

## 2. Architecture

### 2.1 High-Level Architecture
- **Frontend**: Next.js (React) with TailwindCSS. Provides a rich, dynamic, and visually appealing dashboard for users to upload files, control chunking/embedding hyper-parameters, and perform searches manually.
- **Backend**: Python (FastAPI). Chosen for its extensive AI/ML ecosystem, asynchronous capabilities, and robust schema validation (Pydantic).
- **Vector Database**: **Qdrant** (Primary, default) with **ChromaDB** (Fallback, default). Which database serves as primary or fallback is configurable via `PRIMARY_DB` and `FALLBACK_DB` environment variables. Qdrant natively supports both dense vectors (for semantic search) and sparse vectors or payload indexing (for exact keyword/context search). ChromaDB is initialised concurrently to act as a highly-available local fallback.
- **Agent Protocols**: 
  - **MCP**: Built with the official `mcp` SDK, exposing an SSE (Server-Sent Events) endpoint.
  - **2A2**: A REST API endpoint (`/api/v1/agent/2a2`) designed for structured peer-to-peer agent tasking.

### 2.2 Core Components & Modularity
The backend will strictly adhere to abstract interfaces to ensure modularity. 
1. `VectorDatabaseProvider`: Interface for vector operations.
2. `DocumentProcessor`: Interface for extracting text from raw bytes (PDF, images, etc.).
3. `Chunker`: Interface for splitting text (e.g., recursive character, semantic).
4. `Embedder`: Interface for generating vector embeddings (e.g., SentenceTransformers, OpenAI).

## 3. Detailed Specifications (Functions)

### 3.1 Backend Interfaces
```python
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
        pass

class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        pass

class VectorDatabaseProvider(ABC):
    @abstractmethod
    def store(self, collection_name: str, documents: List[Document], embeddings: List[List[float]]) -> bool:
        pass

    @abstractmethod
    def search(self, collection_name: str, query: str, query_vector: List[float], top_k: int = 5, filters: Optional[Dict] = None) -> List[SearchResult]:
        pass
```

### 3.2 Key Endpoints

#### Human/Frontend Endpoints
- **`POST /api/v1/ingest`**
  - **Input**: `multipart/form-data` (file, chunk_size, chunk_overlap, embedder_type).
  - **Action**: Parses file via `DocumentProcessor`, chunks via `Chunker`, embeds via `Embedder`, and stores in `VectorDatabaseProvider`.
  - **Output**: JSON containing ingestion stats (e.g., ingested 50 chunks).

- **`POST /api/v1/search`**
  - **Input**: `{ query: str, filters: dict, limit: int, search_type: str ("vector", "text", "hybrid") }`
  - **Action**: Generates embedding for the query and retrieves results using the configured primary vector database (Qdrant or ChromaDB), with automatic fallback to the secondary.
  - **Output**: List of `SearchResult`.

#### Agent Endpoints
- **`GET /mcp/sse` & `POST /mcp/messages`**
  - Standard Model Context Protocol Server-Sent Events endpoints.
  - Exposes tools: `search_knowledge(query, filters)`, `ingest_url(url)`.
- **`POST /api/v1/agent/2a2`**
  - **Input**: `{ source_agent_id: str, task: str, payload: dict }`
  - **Action**: General communication endpoint. Can execute custom macro-tasks or sub-agent routines.

## 4. Considerations

- **Modular Design**: By strictly typing interfaces (`Chunker`, `Embedder`), the system can start with local models (e.g., HuggingFace embeddings via `sentence-transformers`) and easily swap to paid APIs (OpenAI) via config without changing the core business logic.
- **Hybrid Search**: Semantic search often fails on exact keyword matching (like retrieving specific IDs or names). Qdrant's ability to combine dense embeddings with payload filtering or sparse vectors handles this smoothly.
- **Frontend Aesthetics**: The Next.js frontend must prioritize visual excellence—employing smooth animations, intuitive sliders for hyper-parameters, and a modern dark/light aesthetic (e.g., using pure CSS or requested Tailwind).
- **Asynchronous Processing**: Ingestion of large PDFs or Images can block the event loop. Ingestion routes should offload heavy OCR/PDF parsing and embedding to a background thread (`asyncio.to_thread` or Celery in the future).
- **Configuration & Security**: The system utilises `pydantic-settings` to manage environment variables gracefully (`API_HOST`, `CORS_ORIGINS`, `PRIMARY_DB`, `FALLBACK_DB`, `EMBEDDER_MODEL`). The Next.js frontend relies on `NEXT_PUBLIC_API_URL` to query the production/remote backend.
- **Observability**: Built-in Python `print()` statements are avoided in favour of `loguru`, offering robust, thread-safe, and structured logging for complex Multi-Agent operations.
- **Database Switching**: The `PRIMARY_DB` and `FALLBACK_DB` environment variables (accepted values: `qdrant`, `chroma`) allow operators to swap which database serves as primary or fallback without touching code. The `FallbackVectorDatabaseProvider` replicates writes to both and degrades search to the fallback automatically.
- **SQLite Thread-Safety**: Since local vector databases often rely on SQLite for metadata, which restricts cross-thread connection usage, the system implements a unified safety strategy:
  - Both **ChromaDB** and **Qdrant** are managed via dedicated single-threaded executors (`ThreadPoolExecutor(max_workers=1)`). This ensures the underlying client connection is always created and used on a single, consistent worker thread, providing perfect stability for both in-memory and persistent storage modes across FastAPI's parallel request threads.
- **Qdrant Compatibility**: The backend targets `qdrant-client` ≥ 1.17, using `query_points()` (not the removed `search()`) and deterministic UUID-5 point IDs.
