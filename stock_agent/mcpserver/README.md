# Sample MCP Server

This is a local sample MCP server you can use to test backend MCP integration.

## Endpoints
- `GET /health`
- `POST /mcp` (JSON-RPC)

## Supported JSON-RPC methods
- `tools/list`
- `tools/call`

## Sample tools
- `get_earnings_calendar`
- `get_company_snapshot`
- `get_news_sentiment`

## Run
```bash
cd /Users/hinadome/code/agents.md/mcpserver
pip install -e .
uvicorn main:app --reload --host 0.0.0.0 --port 9001
```

## Optional auth
Set bearer token:
```bash
export MCP_SERVER_BEARER_TOKEN=my-token
```
Then backend should call with matching bearer token.

## Test (tools/list)
```bash
curl -s http://localhost:9001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Test (tools/call)
```bash
curl -s http://localhost:9001/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_company_snapshot","arguments":{"ticker":"NVDA","company_name":"NVIDIA"}}}'
```

## Backend config example
In `backend/.env`:
```env
MCP_SERVERS_JSON={"market-mcp":{"url":"http://localhost:9001/mcp","bearer_token":""}}
```

Then from frontend MCP builder, set:
- server: `market-mcp`
- tool: `get_company_snapshot`
- arguments JSON: `{"ticker":"NVDA","company_name":"NVIDIA"}`
