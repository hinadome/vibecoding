from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

app = FastAPI(title="Sample MCP Server", version="0.1.0")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mcpserver")


class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: Any = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


def _authorized(authorization: str | None) -> bool:
    token = os.getenv("MCP_SERVER_BEARER_TOKEN", "").strip()
    if not token:
        return True
    if not authorization:
        return False
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return False
    return authorization[len(prefix) :].strip() == token


def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": code, "message": message},
    }


def _tool_get_earnings_calendar(arguments: dict[str, Any]) -> dict[str, Any]:
    ticker = str(arguments.get("ticker", "UNKNOWN")).upper()
    start = date.today()
    return {
        "ticker": ticker,
        "events": [
            {
                "event": "Earnings Call",
                "date": (start + timedelta(days=21)).isoformat(),
                "fiscal_quarter": "Q1",
            },
            {
                "event": "Product Update",
                "date": (start + timedelta(days=38)).isoformat(),
                "fiscal_quarter": "Q1",
            },
        ],
    }


def _tool_get_company_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    ticker = str(arguments.get("ticker", "UNKNOWN")).upper()
    name = str(arguments.get("company_name", ticker))
    return {
        "ticker": ticker,
        "company_name": name,
        "metrics": {
            "revenue_growth_yoy_pct": 18.4,
            "gross_margin_pct": 63.2,
            "operating_margin_pct": 29.7,
            "debt_to_equity": 0.41,
        },
        "summary": f"{name} shows strong profitability and moderate leverage.",
    }


def _tool_get_news_sentiment(arguments: dict[str, Any]) -> dict[str, Any]:
    ticker = str(arguments.get("ticker", "UNKNOWN")).upper()
    lookback_days = int(arguments.get("lookback_days", 14))
    return {
        "ticker": ticker,
        "lookback_days": lookback_days,
        "sentiment_score": 0.31,
        "positive_mentions": 42,
        "negative_mentions": 18,
        "highlights": [
            "Analyst upgrades increased across major brokers.",
            "Supply-chain constraints remain a medium-term risk.",
        ],
    }


TOOLS: dict[str, Any] = {
    "get_earnings_calendar": _tool_get_earnings_calendar,
    "get_company_snapshot": _tool_get_company_snapshot,
    "get_news_sentiment": _tool_get_news_sentiment,
}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    payload: JsonRpcRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    client = request.client.host if request.client else "unknown"
    auth_present = bool(authorization)
    print(
        f"[mcpserver] inbound /mcp client={client} method={payload.method} id={payload.id} auth_present={auth_present}",
        flush=True,
    )
    logger.info(
        "MCP server received client=%s method=%s id=%s auth_present=%s",
        client,
        payload.method,
        str(payload.id),
        auth_present,
    )
    if not _authorized(authorization):
        logger.warning("MCP server unauthorized request method=%s", payload.method)
        raise HTTPException(status_code=401, detail="Unauthorized")

    if payload.method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": payload.id,
            "result": {
                "tools": [
                    {"name": name, "description": f"Sample tool: {name}"}
                    for name in TOOLS.keys()
                ]
            },
        }

    if payload.method != "tools/call":
        logger.info("MCP server method not found method=%s", payload.method)
        return _rpc_error(payload.id, -32601, f"Method not found: {payload.method}")

    name = str(payload.params.get("name", "")).strip()
    arguments = payload.params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _rpc_error(payload.id, -32602, "Invalid arguments: must be object")

    tool = TOOLS.get(name)
    if not tool:
        logger.warning("MCP server tool not found name=%s", name)
        return _rpc_error(payload.id, -32601, f"Tool not found: {name}")
    logger.info(
        "MCP server executing tool name=%s argument_keys=%s",
        name,
        list(arguments.keys()),
    )
    print(
        f"[mcpserver] executing tool={name} argument_keys={list(arguments.keys())}",
        flush=True,
    )

    try:
        result = tool(arguments)
    except Exception as exc:  # noqa: BLE001
        logger.exception("MCP server tool execution failed name=%s", name)
        return _rpc_error(payload.id, -32000, f"Tool execution failed: {exc}")
    logger.info("MCP server tool completed name=%s", name)
    print(f"[mcpserver] completed tool={name}", flush=True)

    return {
        "jsonrpc": "2.0",
        "id": payload.id,
        "result": result,
    }
