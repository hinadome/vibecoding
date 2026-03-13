import asyncio
from typing import Optional, Dict, Any, List
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from src.interfaces import VectorDatabaseProvider
from src.services.components import LocalSentenceEmbedder
from pydantic import BaseModel

class SearchQuery(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None

class IngestRequest(BaseModel):
    url: str

class MCPAgentServer:
    def __init__(self, vector_db: VectorDatabaseProvider, embedder: LocalSentenceEmbedder):
        self.vector_db = vector_db
        self.embedder = embedder
        self.server = Server("search-agent-mcp")
        self.setup_handlers()

    def setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [
                Tool(
                    name="search_knowledge",
                    description="Search the agent's knowledge base using semantic and keyword search.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query"},
                            "filters": {"type": "object", "description": "Optional metadata filters", "additionalProperties": True}
                        },
                        "required": ["query"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
            if name == "search_knowledge":
                query = arguments.get("query")
                filters = arguments.get("filters")
                
                # We need to run embedding in a separate thread to not block the event loop
                query_vector = await asyncio.to_thread(self.embedder.embed, [query])
                results = await asyncio.to_thread(
                    self.vector_db.search,
                    collection_name="knowledge",
                    query=query,
                    query_vector=query_vector[0],
                    top_k=5,
                    filters=filters
                )
                
                if not results:
                    return [TextContent(type="text", text="No relevant knowledge found.")]
                    
                response_text = "Search Results:\n"
                for i, res in enumerate(results):
                    response_text += f"{i+1}. [Score: {res.score:.3f}]\n{res.document.content}\n\n"
                    
                return [TextContent(type="text", text=response_text)]
                
            raise ValueError(f"Unknown tool: {name}")

    async def create_sse_transport(self, receive_queue, send_queue):
        transport = SseServerTransport("http://localhost:8000/mcp/messages")
        
        # In a real ASGI server we bridge ASGI request/response cleanly.
        # mcp SDK often handles this internally using its standard transports.
        # This acts as the handler for the transport.
        return transport
