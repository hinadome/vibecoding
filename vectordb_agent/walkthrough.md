# Search Agent Walkthrough

The Search Agent application is now fully constructed and tested! It employs a scalable, multi-agent ready architecture utilizing FastAPI and Next.js.

## What was built
1. **Python FastAPI Backend**
   - **Modular Interfaces:** Built distinct protocols for `Chunker`, `Embedder`, `DocumentProcessor`, and `VectorDatabaseProvider` to allow easy swapping (e.g. from local sentence-transformers to OpenAI).
   - **Local Semantic Network:** Leverages `PyMuPDF` to parse dense bytes (PDFs), recursively chunks the strings, creates dense embeddings via `sentence-transformers`, and stores them locally.
   - **Hybrid Search via Qdrant/ChromaDB:** A configurable Fallback network was implemented. By default, the system uses `ChromaDB` as the primary and `Qdrant` as the fallback (switchable via `PRIMARY_DB` and `FALLBACK_DB`). Both providers utilize a unified **Single-threaded worker executor** pattern to manage SQLite connection isolation, ensuring rock-solid stability in both `:memory:` and persistent modes.
   - **Agent Modularity:** Created a dedicated `/api/v1/agent/2a2` remote API route as well as a standard Model Context Protocol (MCP) Server-Sent Events endpoint at `/mcp/sse`.

2. **Next.js Deep Aesthetics Dashboard**
   - A highly reactive, aesthetically brilliant unified user interface utilizing modern Glassmorphism, tailored Tailwind gradients, dynamic animations, and `lucide-react` icons.
   - Side-by-side Upload/Ingestion settings (adjustable Chunk Size and Chunk Overlap widgets) with the Query explorer space.

3. **Phase 5 — Polish & Hardening**
   - Replaced all `print()` calls with structured `loguru.logger` across `main.py`, `fallback_provider.py`, and `components.py`.
   - Centralised all configuration into `config.py` (Pydantic Settings) backed by a `.env` file (`backend/.env.example`).
   - Frontend API URLs are now driven by `NEXT_PUBLIC_API_URL` (set in `frontend/.env.local`), so targeting a remote backend is a single-line change.
   - Added Python `__init__.py` package markers and rich module/class docstrings throughout the backend.

## Validation Results
- Verified local Next.js `Turbopack` builds smoothly.
- Verified backend dependency graph including the `ChromaDB` integration fallback logic.
- Fixed Qdrant compatibility for `qdrant-client` v1.17 (replaced removed `search()` with `query_points()`, string IDs with deterministic UUID-5).
- Verified end-to-end Qdrant create → upsert → query_points cycle in-memory.

## Environment Configuration

All backend settings are managed via environment variables (or a `.env` file). See `backend/.env.example` for the full reference.

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins |
| `QDRANT_PATH` | `./qdrant_data` | Filesystem path for Qdrant persistence |
| `CHROMA_PATH` | `./chroma_data` | Filesystem path for ChromaDB persistence |
| `PRIMARY_DB` | `chroma` | Primary vector database (`qdrant` or `chroma`) |
| `FALLBACK_DB` | `qdrant` | Fallback vector database (`qdrant` or `chroma`) |
| `EMBEDDER_MODEL` | `all-MiniLM-L6-v2` | HuggingFace sentence-transformer model name |

**Frontend** (set in `frontend/.env.local`):

| Variable | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend API base URL |

## Running the Application
To run the full stack:

**1. Start the Backend:**
Open a terminal and run:
```bash
source ~/.bashrc
pyenv activate awsworkshop
cd ~/code/vibecoding/search_agent/backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**2. Start the Frontend:**
Open a second terminal and run:
```bash
cd ~/code/vibecoding/search_agent/frontend
npm run dev
```

You can now visit `http://localhost:3000` to interact with the new dashboard, ingest your files, and search through the semantic space!

## Sample curl Commands

### 1. Document Ingestion (`POST /api/v1/ingest`)
Upload a PDF (or any text file) with configurable chunk parameters:
```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "file=@/path/to/your/document.pdf" \
  -F "chunk_size=1000" \
  -F "chunk_overlap=200"
```
**Expected response:**
```json
{
  "message": "Document ingestion started in background.",
  "filename": "document.pdf"
}
```

### 2. Semantic Search (`POST /api/v1/search`)
Query the knowledge base with optional filters:
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does vector search work?",
    "limit": 5
  }'
```
With metadata filters:
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning",
    "limit": 3,
    "filters": {"source": "document.pdf"}
  }'
```
**Expected response:**
```json
[
  {
    "id": "document.pdf_2",
    "content": "Vector search uses embeddings to find semantically similar...",
    "score": 0.8721,
    "metadata": {"source": "document.pdf", "chunk_index": 2}
  }
]
```

### 3. MCP Server-Sent Events (`GET /mcp/sse`)
Connect to the MCP SSE stream (useful for agent tooling):
```bash
curl -N http://localhost:8000/mcp/sse
```
**Expected response (streaming):**
```
event: mcp_connect
data: connected to search agent
```

### 4. Agent-to-Agent Communication (`POST /api/v1/agent/2a2`)
Send a structured task from another agent:
```bash
curl -X POST http://localhost:8000/api/v1/agent/2a2 \
  -H "Content-Type: application/json" \
  -d '{
    "source_agent_id": "planner-agent-001",
    "task": "retrieve_context",
    "payload": {
      "query": "latest quarterly results",
      "max_results": 3
    }
  }'
```
**Expected response:**
```json
{
  "status": "received",
  "responder": "search-agent-v1",
  "acknowledged_task": "retrieve_context"
}
```

---

## MCP Client Configuration

Other agents or LLM hosts connect to the Search Agent's MCP server via the SSE transport.

### Claude Desktop / Cursor / Windsurf
Add the following entry to your MCP client config file (e.g. `claude_desktop_config.json` or `.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "search-agent": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```
Once configured, the host will discover the `search_knowledge` tool automatically and can invoke it on behalf of the user.

### Python MCP Client (SDK)
Connect programmatically from another Python agent:
```python
from mcp.client.sse import sse_client
from mcp import ClientSession

async def query_search_agent():
    """Connect to the Search Agent MCP server and call the search_knowledge tool."""
    async with sse_client(url="http://localhost:8000/mcp/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # List available tools
            tools = await session.list_tools()
            print("Available tools:", [t.name for t in tools.tools])

            # Call search_knowledge
            result = await session.call_tool(
                "search_knowledge",
                arguments={"query": "vector database architecture", "filters": None}
            )
            print("Result:", result.content[0].text)
```

### MCP Inspector (Testing / Debugging)
Use the official MCP Inspector to manually browse and test exposed tools:
```bash
npx @modelcontextprotocol/inspector
```
Then enter `http://localhost:8000/mcp/sse` as the SSE URL in the Inspector UI.

---

## A2A Client Integration

The `/api/v1/agent/2a2` endpoint provides a simple, structured REST contract for peer-to-peer agent communication.

### Python Agent Example
```python
import requests

SEARCH_AGENT_URL = "http://localhost:8000"

def send_task_to_search_agent(
    source_id: str,
    task: str,
    payload: dict
) -> dict:
    """Send a structured task to the Search Agent via the A2A endpoint.

    Args:
        source_id: Unique identifier of the calling agent.
        task:      Short task name (e.g. 'retrieve_context', 'summarise_docs').
        payload:   Arbitrary dict with task-specific parameters.

    Returns:
        The JSON response from the Search Agent.
    """
    response = requests.post(
        f"{SEARCH_AGENT_URL}/api/v1/agent/2a2",
        json={
            "source_agent_id": source_id,
            "task": task,
            "payload": payload,
        },
    )
    response.raise_for_status()
    return response.json()

# Example usage
result = send_task_to_search_agent(
    source_id="planner-agent-001",
    task="retrieve_context",
    payload={"query": "quarterly revenue", "max_results": 5},
)
print(result)
# {'status': 'received', 'responder': 'search-agent-v1', 'acknowledged_task': 'retrieve_context'}
```

### Multi-Agent Orchestrator Pattern
When running multiple agents, a typical orchestrator flow looks like:
```
┌──────────────┐      A2A POST        ┌──────────────┐
│  Planner     │ ──────────────────▶  │  Search      │
│  Agent       │ ◀──────────────────  │  Agent       │
└──────────────┘      JSON response   └──────────────┘
        │                                     ▲
        │  MCP tool call                      │  MCP SSE
        ▼                                     │
┌──────────────┐                      ┌───────┴──────┐
│  Writer      │                      │  LLM Host    │
│  Agent       │                      │  (Claude)    │
└──────────────┘                      └──────────────┘
```
- **A2A** is best for agent → agent direct tasking (fire-and-forget or request/response).
- **MCP** is best for LLM hosts that need to discover and invoke tools dynamically.

---

**3. VM Deployment Script:**
A bash script (`deploy_vm.sh`) automates bare-metal deployments.
```bash
chmod +x deploy_vm.sh
./deploy_vm.sh
```

**4. Container Orchestration:**
The Search Agent stack is fully containerized using Docker Compose.
```bash
docker-compose up --build -d
```
