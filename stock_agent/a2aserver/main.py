from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

app = FastAPI(title="Sample A2A Server", version="0.1.0")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("a2aserver")


class A2ARequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)


class A2AResponse(BaseModel):
    result: dict[str, Any]


def _authorized(authorization: str | None) -> bool:
    token = os.getenv("A2A_SERVER_BEARER_TOKEN", "").strip()
    if not token:
        return True
    if not authorization:
        return False
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return False
    return authorization[len(prefix) :].strip() == token


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invoke", response_model=A2AResponse)
async def invoke_agent(
    payload: A2ARequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> A2AResponse:
    client = request.client.host if request.client else "unknown"
    auth_present = bool(authorization)
    print(
        f"[a2aserver] inbound /invoke client={client} task_chars={len(payload.task)} auth_present={auth_present}",
        flush=True,
    )
    logger.info(
        "A2A server received client=%s task_chars=%d context_keys=%s auth_present=%s",
        client,
        len(payload.task),
        sorted(list(payload.context.keys())),
        auth_present,
    )

    if not _authorized(authorization):
        logger.warning("A2A server unauthorized request")
        raise HTTPException(status_code=401, detail="Unauthorized")

    ticker = str(payload.context.get("ticker", "UNKNOWN")).upper()
    horizon_days = int(payload.context.get("horizon_days", 90))
    focus = payload.context.get("focus", ["valuation_risk", "macro_risk"])

    risk_flags = [
        f"Monitor demand volatility for {ticker}",
        f"Re-check margin guidance within {horizon_days} days",
        "Watch macro rate sensitivity and sector rotation",
    ]

    response = {
        "agent": "sample-a2a-risk-agent",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "task": payload.task,
        "ticker": ticker,
        "horizon_days": horizon_days,
        "focus": focus,
        "risk_score": 0.42,
        "summary": (
            f"Moderate risk profile for {ticker}; maintain staged entries and "
            "monitor catalysts around earnings and macro data."
        ),
        "risk_flags": risk_flags,
    }

    print(f"[a2aserver] completed /invoke ticker={ticker} risk_score={response['risk_score']}", flush=True)
    logger.info("A2A server completed ticker=%s", ticker)
    return A2AResponse(result=response)
