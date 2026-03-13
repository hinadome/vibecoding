import json
import logging
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.config import get_settings
from app.models import (
    A2AAgentCall,
    ChatTurn,
    MCPToolCall,
    ResearchRequest,
    ResearchResponse,
    RiskTolerance,
)
from app.services.a2a_client import A2AClient
from app.services.dev_log_sink import append_ab_metric
from app.services.file_parser import extract_text_from_upload
from app.services.mcp_client import MCPClient
from app.services.openai_client import OpenAICompatibleClient
from app.services.research_agent import DeepResearchAgent
from app.services.sec_ingestion import SecEdgarIngestionService
from app.services.vector_store import VectorRetriever
from app.services.web_search import WebSearcher

settings = get_settings()
logger = logging.getLogger("uvicorn.error")
MAX_UPLOAD_FILES = 5
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".txt", ".md", ".csv"}

app = FastAPI(
    title="Deep Research Stock Trading Assistant",
    version="0.1.0",
    description=(
        "FastAPI backend for stock deep research with web retrieval, "
        "vector retrieval, sentiment analysis, and markdown recommendations."
    ),
)

allow_credentials = settings.cors_allow_credentials
allow_origin_regex = settings.cors_origin_regex or None
if allow_origin_regex and settings.app_env != "dev":
    # Avoid credentialed requests when allowing broad regex origins in production.
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = DeepResearchAgent(
    web_searcher=WebSearcher(settings),
    vector_retriever=VectorRetriever(settings),
    llm_client=OpenAICompatibleClient(settings),
    mcp_client=MCPClient(settings),
    a2a_client=A2AClient(settings),
    sec_ingestor=SecEdgarIngestionService(settings),
)


@app.get("/health")
async def health() -> dict[str, str]:
    """
    Purpose: Return a simple liveness response for health checks.
    Args/Params:
    - None.
    Returns:
    - `dict[str, str]`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `health()`
    """
    return {"status": "ok"}


@app.get("/api/integrations/status")
async def integration_status() -> dict[str, object]:
    """
    Purpose: Return configured MCP servers and A2A agents visible to the backend.
    Args/Params:
    - None.
    Returns:
    - `dict[str, object]`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `integration_status()`
    """
    mcp = MCPClient(settings)
    a2a = A2AClient(settings)
    return {
        "mcp_servers": sorted(mcp.configured_servers().keys()),
        "a2a_agents": sorted(a2a.configured_agents().keys()),
    }


@app.post("/api/research", response_model=ResearchResponse)
async def run_research(req: ResearchRequest) -> ResearchResponse:
    """
    Purpose: Run a complete non-streaming research cycle and return final report JSON.
    Args/Params:
    - `req` (ResearchRequest): Input parameter used by this function.
    Returns:
    - `ResearchResponse`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `run_research(req=...)`
    """
    try:
        return await agent.run(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Research failed: {exc}") from exc


@app.post("/api/chat/stream")
async def stream_research(req: ResearchRequest) -> StreamingResponse:
    """
    Purpose: Stream research markdown chunks over SSE and send final metadata payload.
    Args/Params:
    - `req` (ResearchRequest): Input parameter used by this function.
    Returns:
    - `StreamingResponse`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `stream_research(req=...)`
    """
    logger.info(
        "Received /api/chat/stream request ticker=%s bypass_web_search=%s use_query_decomposition=%s use_primary_source_ingestion=%s use_financial_model_rebuild=%s use_advanced_financial_engine=%s use_structured_valuation=%s mcp_calls=%d a2a_calls=%d",
        req.ticker.upper(),
        req.bypass_web_search,
        req.use_query_decomposition,
        req.use_primary_source_ingestion,
        req.use_financial_model_rebuild,
        req.use_advanced_financial_engine,
        req.use_structured_valuation,
        len(req.mcp_calls),
        len(req.a2a_calls),
    )
    if settings.app_env == "dev":
        logger.info(
            "MCP payload details: %s",
            [
                {
                    "server": item.server,
                    "tool": item.tool,
                    "argument_keys": sorted(list(item.arguments.keys())),
                }
                for item in req.mcp_calls
            ],
        )
        logger.info(
            "A2A payload details: %s",
            [
                {
                    "agent": item.agent,
                    "task_chars": len(item.task),
                    "context_keys": sorted(list(item.context.keys())),
                }
                for item in req.a2a_calls
            ],
        )
    return _stream_research_response(req)


@app.post("/api/chat/stream/upload")
async def stream_research_with_upload(
    ticker: str = Form(...),
    market: str = Form("US"),
    question: str = Form(""),
    company_name: str = Form(""),
    horizon_days: int = Form(90),
    risk_tolerance: RiskTolerance = Form(RiskTolerance.moderate),
    bypass_web_search: bool = Form(True),
    use_query_decomposition: bool = Form(False),
    use_primary_source_ingestion: bool = Form(False),
    use_financial_model_rebuild: bool = Form(False),
    use_advanced_financial_engine: bool = Form(False),
    use_structured_valuation: bool = Form(False),
    financial_model_input: str = Form(""),
    advanced_financial_input: str = Form(""),
    valuation_input: str = Form(""),
    chat_history: str = Form("[]"),
    mcp_calls: str = Form("[]"),
    a2a_calls: str = Form("[]"),
    files: list[UploadFile] | None = File(default=None),
) -> StreamingResponse:
    """
    Purpose: Stream research while accepting file uploads and extracting PDF/text context.
    Args/Params:
    - `ticker` (str): Input parameter used by this function.
    - `market` (str): Input parameter used by this function.
    - `question` (str): Input parameter used by this function.
    - `company_name` (str): Input parameter used by this function.
    - `horizon_days` (int): Input parameter used by this function.
    - `risk_tolerance` (RiskTolerance): Input parameter used by this function.
    - `bypass_web_search` (bool): Input parameter used by this function.
    - `use_query_decomposition` (bool): Input parameter used by this function.
    - `use_primary_source_ingestion` (bool): Input parameter used by this function.
    - `use_financial_model_rebuild` (bool): Input parameter used by this function.
    - `use_advanced_financial_engine` (bool): Input parameter used by this function.
    - `use_structured_valuation` (bool): Input parameter used by this function.
    - `financial_model_input` (str): Input parameter used by this function.
    - `advanced_financial_input` (str): Input parameter used by this function.
    - `valuation_input` (str): Input parameter used by this function.
    - `chat_history` (str): Input parameter used by this function.
    - `mcp_calls` (str): Input parameter used by this function.
    - `a2a_calls` (str): Input parameter used by this function.
    - `files` (list[UploadFile] | None): Input parameter used by this function.
    Returns:
    - `StreamingResponse`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `stream_research_with_upload(ticker=..., market=..., question=..., company_name=...)`
    """
    if settings.app_env == "dev":
        logger.info(
            "Attachment processing started ticker=%s incoming_files=%d",
            ticker.upper(),
            len(files or []),
        )
    if files and len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum allowed is {MAX_UPLOAD_FILES}.",
        )

    attachment_texts: list[str] = []
    for file in files or []:
        try:
            extracted = await extract_text_from_upload(
                file=file,
                max_file_bytes=MAX_UPLOAD_BYTES,
                allowed_extensions=ALLOWED_UPLOAD_EXTENSIONS,
                debug_logging=settings.app_env == "dev",
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file '{file.filename}': {exc}",
            ) from exc
        if extracted:
            attachment_texts.append(f"[{file.filename}]\\n{extracted[:12000]}")
    if settings.app_env == "dev":
        logger.info(
            "Attachment processing completed ticker=%s accepted_files=%d attachment_blocks=%d total_attachment_chars=%d",
            ticker.upper(),
            len(files or []),
            len(attachment_texts),
            sum(len(item) for item in attachment_texts),
        )

    try:
        parsed_history = json.loads(chat_history)
        parsed_mcp_calls = json.loads(mcp_calls)
        parsed_a2a_calls = json.loads(a2a_calls)
        parsed_financial_model_input = (
            json.loads(financial_model_input)
            if financial_model_input and financial_model_input.strip()
            else None
        )
        parsed_advanced_financial_input = (
            json.loads(advanced_financial_input)
            if advanced_financial_input and advanced_financial_input.strip()
            else None
        )
        parsed_valuation_input = (
            json.loads(valuation_input) if valuation_input and valuation_input.strip() else None
        )
        history = [ChatTurn(**entry) for entry in parsed_history]
        mcp_items = [MCPToolCall(**entry) for entry in parsed_mcp_calls]
        a2a_items = [A2AAgentCall(**entry) for entry in parsed_a2a_calls]
        logger.info(
            "Received /api/chat/stream/upload request ticker=%s bypass_web_search=%s use_query_decomposition=%s use_primary_source_ingestion=%s use_financial_model_rebuild=%s use_advanced_financial_engine=%s use_structured_valuation=%s mcp_calls=%d a2a_calls=%d",
            ticker.upper(),
            bypass_web_search,
            use_query_decomposition,
            use_primary_source_ingestion,
            use_financial_model_rebuild,
            use_advanced_financial_engine,
            use_structured_valuation,
            len(mcp_items),
            len(a2a_items),
        )
        if settings.app_env == "dev":
            logger.info(
                "MCP payload details: %s",
                [
                    {
                        "server": item.server,
                        "tool": item.tool,
                        "argument_keys": sorted(list(item.arguments.keys())),
                    }
                    for item in mcp_items
                ],
            )
            logger.info(
                "A2A payload details: %s",
                [
                    {
                        "agent": item.agent,
                        "task_chars": len(item.task),
                        "context_keys": sorted(list(item.context.keys())),
                    }
                    for item in a2a_items
                ],
            )
        req = ResearchRequest(
            ticker=ticker,
            company_name=company_name or None,
            market=market,
            question=question or None,
            horizon_days=horizon_days,
            risk_tolerance=risk_tolerance,
            bypass_web_search=bypass_web_search,
            use_query_decomposition=use_query_decomposition,
            use_primary_source_ingestion=use_primary_source_ingestion,
            use_financial_model_rebuild=use_financial_model_rebuild,
            use_advanced_financial_engine=use_advanced_financial_engine,
            use_structured_valuation=use_structured_valuation,
            chat_history=history,
            attachment_texts=attachment_texts,
            mcp_calls=mcp_items,
            a2a_calls=a2a_items,
            financial_model_input=parsed_financial_model_input,
            advanced_financial_input=parsed_advanced_financial_input,
            valuation_input=parsed_valuation_input,
        )
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid upload payload: {exc}") from exc

    return _stream_research_response(req)


def _stream_research_response(req: ResearchRequest) -> StreamingResponse:
    """
    Purpose: Build an SSE response for chunked markdown generation and metadata events.
    Args/Params:
    - `req` (ResearchRequest): Input parameter used by this function.
    Returns:
    - `StreamingResponse`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `_stream_research_response(req=...)`
    """
    async def event_stream():
        """
        Purpose: Yield SSE events for markdown chunks, final metadata, and terminal status.
        Args/Params:
        - None.
        Returns:
        - `Any`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `event_stream()`
        """
        started = time.perf_counter()
        try:
            context = await agent.prepare_context(req)
            full_markdown: list[str] = []

            async for chunk in agent.generate_markdown_stream(req, context):
                full_markdown.append(chunk)
                payload = json.dumps({"content": chunk})
                yield f"event: chunk\ndata: {payload}\n\n"

            final_markdown = "".join(full_markdown)
            response = agent.build_response(req, context, final_markdown)
            yield f"event: meta\ndata: {json.dumps(response.model_dump())}\n\n"
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "AB_METRIC stream_total ticker=%s decomposition=%s bypass_web_search=%s output_chars=%d source_count=%d elapsed_ms=%d",
                req.ticker.upper(),
                req.use_query_decomposition,
                req.bypass_web_search,
                len(final_markdown),
                len(context.sources),
                elapsed_ms,
            )
            append_ab_metric(
                app_env=settings.app_env,
                event="stream_total",
                payload={
                    "ticker": req.ticker.upper(),
                    "decomposition": req.use_query_decomposition,
                    "bypass_web_search": req.bypass_web_search,
                    "output_chars": len(final_markdown),
                    "source_count": len(context.sources),
                    "elapsed_ms": elapsed_ms,
                },
            )
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:  # noqa: BLE001
            err = json.dumps({"message": f"Research failed: {exc}"})
            yield f"event: error\ndata: {err}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
