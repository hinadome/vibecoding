# Search Agent Backend

## Overview
A scalable FastAPI Python application that implements core Search Agent functions. It provides modular ingestion processes for documents (incorporating PyMuPDF), text chunking, and semantic embedding. Data is persistently stored in local vector databases.

## Features
- **Fallback Architecture:** Leverages *LocalQdrantProvider* as the primary source of truth, gracefully falling back to *LocalChromaProvider* if Qdrant operations fail.
- **REST Endpoints:** Open APIs for ingestion (`/api/v1/ingest`) and advanced querying (`/api/v1/search`).
- **Agent Interoperability:** Implements both a dedicated `/api/v1/agent/2a2` inter-agent endpoint and an in-development generic `/mcp/sse` Server-Sent Events service based on Anthropics' Model Context Protocol.

## Setup & Execution

### Pre-requisites
- Python 3.11+
- `pyenv` and virtualenv are heavily recommended.

### Installation
1. Move to backend directory and load environment:
   ```bash
   cd backend
   source ~/.bashrc
   pyenv activate awsworkshop
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running Locally
To run the server with auto-reload:
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The API docs (Swagger) will be available at [http://localhost:8000/docs](http://localhost:8000/docs).
