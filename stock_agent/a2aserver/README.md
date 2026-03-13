# Sample A2A Server

This is a local sample A2A server you can use to test backend A2A integration.

## Endpoints
- `GET /health`
- `POST /invoke`

## Run
```bash
cd /Users/hinadome/code/agents.md/a2aserver
pip install -e .
uvicorn main:app --reload --host 0.0.0.0 --port 9101
```

## Optional auth
Set bearer token:
```bash
export A2A_SERVER_BEARER_TOKEN=my-token
```
Then backend should call with matching bearer token.

## Test with curl
```bash
curl -i --http1.1 http://127.0.0.1:9101/invoke \
  -H 'Content-Type: application/json' \
  -d '{"task":"Assess downside risk for NVDA","context":{"ticker":"NVDA","horizon_days":90,"focus":["valuation_risk","macro_risk"]}}'
```

## Backend config example
In `backend/.env`:
```env
A2A_AGENTS_JSON={"risk-agent":{"url":"http://127.0.0.1:9101/invoke","bearer_token":""}}
```

Then from frontend A2A builder, set:
- agent: `risk-agent`
- task: `Assess downside risk for NVDA next 90 days`
- context JSON: `{"ticker":"NVDA","horizon_days":90,"focus":["valuation_risk","macro_risk"]}`
