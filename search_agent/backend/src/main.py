"""Search Agent Backend — FastAPI Application Entry Point.

This module bootstraps the FastAPI application, wires all service
dependencies together using centralised configuration, and exposes
REST, MCP-SSE, and Agent-to-Agent (A2A) endpoints.
"""

import os
import asyncio
from loguru import logger
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from src.config import settings
from src.interfaces import Document
from src.services.components import LocalSentenceEmbedder, RecursiveCharacterChunker, PDFDocumentProcessor
from src.services.qdrant_provider import LocalQdrantProvider
from src.services.chroma_provider import LocalChromaProvider
from src.services.fallback_provider import FallbackVectorDatabaseProvider
from src.services.mcp_server import MCPAgentServer

app = FastAPI(title=settings.api_title)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global services dependency graph — all paths/models driven by config.py
# ---------------------------------------------------------------------------
_providers = {
    "qdrant": LocalQdrantProvider(path=settings.qdrant_path),
    "chroma": LocalChromaProvider(path=settings.chroma_path),
}

_primary = _providers.get(settings.primary_db)
_fallback = _providers.get(settings.fallback_db)

if _primary is None:
    raise ValueError(f"Unknown PRIMARY_DB value: '{settings.primary_db}'. Use 'qdrant' or 'chroma'.")
if _fallback is None:
    raise ValueError(f"Unknown FALLBACK_DB value: '{settings.fallback_db}'. Use 'qdrant' or 'chroma'.")

db_provider = FallbackVectorDatabaseProvider(primary=_primary, fallback=_fallback)
logger.info("Vector DB: primary={}, fallback={}", _primary, _fallback)

embedder = LocalSentenceEmbedder(model_name=settings.embedder_model)
chunker = RecursiveCharacterChunker()
pdf_processor = PDFDocumentProcessor()
mcp_server_instance = MCPAgentServer(db_provider, embedder)

logger.info(f"Service dependency graph initialised ( {settings.primary_db} → {settings.fallback_db} fallback).")

class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    filters: Optional[Dict[str, Any]] = None

class SearchResultResponse(BaseModel):
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]

class A2ATaskRequest(BaseModel):
    source_agent_id: str
    task: str
    payload: Dict[str, Any]

@app.on_event("startup")
async def startup_event():
    """Create persistent data directories on first boot."""
    os.makedirs(settings.qdrant_path, exist_ok=True)
    os.makedirs(settings.chroma_path, exist_ok=True)
    logger.info("Startup complete — data directories ready.")

@app.post("/api/v1/ingest")
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200)
):
    """Human/Frontend Endpoint: Uploads a file, extracts text, chunks, embeds, and stores.

    The heavy CPU-bound work (parsing, chunking, embedding) is offloaded
    to a background task via ``asyncio.to_thread`` so the event loop stays
    responsive for other API calls.
    """
    contents = await file.read()
    filename = file.filename
    logger.info("Received file '{}' for ingestion (chunk_size={}, overlap={}).", filename, chunk_size, chunk_overlap)

    async def process_file():
        text = await asyncio.to_thread(pdf_processor.process_bytes, contents, filename)
        if not text:
            logger.warning("No text extracted from '{}'. Skipping.", filename)
            return

        chunks = await asyncio.to_thread(chunker.chunk, text, chunk_size, chunk_overlap)
        embeddings = await asyncio.to_thread(embedder.embed, chunks)

        docs = [
            Document(id=f"{filename}_{i}", content=chunk, metadata={"source": filename, "chunk_index": i})
            for i, chunk in enumerate(chunks)
        ]

        await asyncio.to_thread(db_provider.store, "knowledge", docs, embeddings)
        logger.success("Ingested {} chunks from '{}' into Vector DB.", len(chunks), filename)

    background_tasks.add_task(process_file)
    return {"message": "Document ingestion started in background.", "filename": filename}

@app.post("/api/v1/search", response_model=List[SearchResultResponse])
async def search_knowledge(request: SearchRequest):
    """Human/Frontend Endpoint: Searches the vector DB."""
    query_vector = await asyncio.to_thread(embedder.embed, [request.query])
    if not query_vector:
        raise HTTPException(status_code=500, detail="Failed to embed query")
        
    results = await asyncio.to_thread(
        db_provider.search,
        collection_name="knowledge",
        query=request.query,
        query_vector=query_vector[0],
        top_k=request.limit,
        filters=request.filters
    )
    
    return [
        SearchResultResponse(
            id=res.document.id,
            content=res.document.content,
            score=res.score,
            metadata=res.document.metadata
        )
        for res in results
    ]

# Agent Endpoints
@app.get("/mcp/sse")
async def mcp_sse():
    """MCP Server-Sent Events human-readable transport endpoint."""
    async def event_publisher():
        # A simple placeholder. The official mcp Python SDK expects standard starlette/fastapi SSE handling.
        # This will be refined as the mcp protocol solidifies standard Python Server transports.
        yield {"event": "mcp_connect", "data": "connected to search agent"}
        
    return EventSourceResponse(event_publisher())

@app.post("/api/v1/agent/2a2")
async def remote_agent_task(request: A2ATaskRequest):
    """Agent-to-Agent standard point for other systems to dynamically request complex operations."""
    # Custom business logic for agent-to-agent talk
    return {
        "status": "received", 
        "responder": "search-agent-v1",
        "acknowledged_task": request.task
    }
