# Deep Research Stock Assistant Backend (FastAPI)

## Features
- Deep market/company research using web search providers (Exa, Tavily, Serper, DuckDuckGo fallback)
- Optional vector retrieval from Qdrant
- Automatic vector ingestion of retrieved web evidence and uploaded document text
- Sentiment analysis for market and social trend signals
- OpenAI-compatible LLM summarization into markdown recommendations

## Setup
1. Create environment variables:
   ```bash
   cp .env.example .env
   ```
2. Install dependencies:
   ```bash
   pip install -e .
   ```
3. Run API server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## API
- `GET /health`
- `GET /api/integrations/status` (lists configured MCP servers and A2A agents)
- `POST /api/research`
- `POST /api/chat/stream` (SSE streaming chunks + final metadata event)
- `POST /api/chat/stream/upload` (multipart upload + SSE stream; PDF files are converted to text)

### Upload Limits
- Max files per request: `5`
- Max size per file: `5MB`
- Allowed extensions: `.pdf`, `.txt`, `.md`, `.csv`

### Example Request
```json
{
  "ticker": "AAPL",
  "company_name": "Apple",
  "market": "US",
  "question": "Is the next 6-month trend bullish?",
  "horizon_days": 180,
  "risk_tolerance": "moderate",
  "mcp_calls": [
    {
      "server": "market-mcp",
      "tool": "get_earnings_calendar",
      "arguments": {"ticker": "AAPL"}
    }
  ],
  "a2a_calls": [
    {
      "agent": "risk-agent",
      "task": "Assess downside catalysts for next quarter",
      "context": {"ticker": "AAPL"}
    }
  ]
}
```
