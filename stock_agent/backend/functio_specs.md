# Backend Functional Specs

## Implemented Functionalities
- FastAPI service for deep-research stock assistant.
- Environment-driven configuration via `.env`:
  - OpenAI-compatible API key
  - chat model
  - embedding model
  - web-search provider keys
  - vector DB connection settings
  - MCP server registry (`MCP_SERVERS_JSON`)
  - A2A agent registry (`A2A_AGENTS_JSON`)
- CORS-enabled API server for frontend integration.
- Health endpoint:
  - `GET /health`
- Integration introspection endpoint:
  - `GET /api/integrations/status`
  - returns configured MCP server and A2A agent names
- Non-streaming research endpoint:
  - `POST /api/research`
  - returns full markdown report + signals + sources
- Streaming research endpoint (SSE):
  - `POST /api/chat/stream`
  - emits `chunk`, `meta`, `done`, and `error` events
- Multipart streaming endpoint with file upload:
  - `POST /api/chat/stream/upload`
  - parses form fields + files
  - converts PDF files to text before prompting LLM
  - validates upload guardrails:
    - maximum 5 files per request
    - maximum 5MB per file
    - allowed extensions: `.pdf`, `.txt`, `.md`, `.csv`
- File text extraction service:
  - PDF via `pypdf` page extraction
  - text-like files via byte decode fallback
- Deep research pipeline orchestration:
  - market/social query generation
  - optional primary-source ingestion from SEC/EDGAR via `use_primary_source_ingestion`
  - web retrieval (Exa/Tavily/Serper/DuckDuckGo fallback)
  - optional web bypass via `bypass_web_search`
  - optional query decomposition via `use_query_decomposition`
  - optional financial model rebuild via `use_financial_model_rebuild`
  - optional structured valuation via `use_structured_valuation`
  - optional vector retrieval (Qdrant)
  - source deduplication
  - signal computation
  - markdown synthesis through OpenAI-compatible model
  - system prompt loaded from `backend/system_prompt.md` (cached)
  - optional structured valuation summary returned in response metadata (`valuation`)
- Multi-turn context support:
  - accepts `chat_history`
  - includes recent turns in prompt construction
- MCP integration support:
  - accepts `mcp_calls` in request payload
  - performs JSON-RPC `tools/call` against configured MCP servers
  - injects MCP results into prompt context
  - logs configured MCP servers, request dispatch, and skip reasons in dev mode
- A2A integration support:
  - accepts `a2a_calls` in request payload
  - invokes external agents over HTTP
  - injects A2A results into prompt context
  - logs configured A2A agents, request dispatch, and skip reasons in dev mode
- Attachment context support:
  - accepts extracted attachment text list
  - injects document text into prompt context
  - truncates extracted text per attachment before prompt injection
- Vector persistence support:
  - stores SEC/EDGAR primary-source evidence into vector DB when configured
  - stores web-search evidence into vector DB when configured
  - stores uploaded attachment text into vector DB when configured
  - stores MCP/A2A external context text into vector DB when configured
- Sentiment and confidence analytics:
  - market sentiment signal
  - social sentiment signal
  - research confidence signal based on source breadth
- Scenario analytics module:
  - dedicated base/bull/bear scenario scoring
  - risk-profile-aware weighting (conservative/moderate/aggressive)
  - weighted recommendation (`Buy`/`Hold`/`Sell`) and confidence
  - scenario summary injected into prompt context
  - scenario weighted score included in response signals
- Financial model rebuild module (separate opt-in path):
  - dedicated service for lightweight 3-statement checks and forecasting
  - validates accounting identity (`assets = liabilities + equity`) per historical period
  - builds base/bull/bear forward projections (revenue, net income, free cash flow)
  - computes weighted model score, recommendation, and confidence
  - injects financial-model summary into prompt context
  - adds `Financial model weighted score` signal to response metadata
- Advanced financial engine module (separate opt-in path):
  - activated by `use_advanced_financial_engine`
  - uses linked schedules per forecast period:
    - revenue drivers (`volume`, `price`, `other_revenue`)
    - margin/opex assumptions
    - working-capital schedule (`AR`, `Inventory`, `AP` via day assumptions)
    - capex/depreciation schedule
    - debt/interest schedule
    - tax schedule
    - retained earnings roll-forward
    - cash roll-forward
    - balance-sheet check per forecast period (`balance_check_gap`)
  - can run from `advanced_financial_input` directly or fallback-convert from basic `financial_model_input`
- Structured valuation module (separate opt-in path):
  - runs DCF + relative valuation (`P/E`, `EV/EBITDA`, `P/FCF`, `EV/FCF`) on top of forecasted financial model outputs
  - computes blended target price and upside/downside vs current price
  - computes bull/base/bear implied targets and scenario-weighted target by risk profile
  - produces sensitivity grid (WACC x terminal growth) for implied price range
  - injects valuation assumptions/results into prompt context
  - adds `Structured valuation upside (%)` signal to response metadata
- Deterministic fallback markdown generation when LLM is unavailable/fails.

## Execution Order (Current Logic)
1. Parse request and normalize context (`ticker`, `question`, `chat_history`, attachments, MCP/A2A).
2. If attachments exist, convert to text (PDF->text) and ingest attachment text into vector DB.
3. If `use_primary_source_ingestion=true`, fetch SEC/EDGAR primary filings and ingest them into vector DB.
4. If `bypass_web_search=false`, execute market + social web queries.
5. If web search executed, dedupe results and ingest web sources into vector DB.
6. If `use_query_decomposition=true` and web search is enabled, run professional multi-dimension sub-query retrieval:
   - mandate_screening
   - business_industry
   - core_documents
   - historical_financials
   - sentiment
   - valuation
   - catalysts_risks
   - thesis_testing
   - portfolio_fit
7. Ingest decomposition retrieval sources into vector DB.
8. Execute external integration calls (MCP/A2A) and collect context snippets.
9. Ingest MCP/A2A context snippets into vector DB.
10. Build vector search query text:
   - `"{ticker} {company_name} {question}".strip()`
11. Create embedding from that query text and execute vector search in Qdrant.
12. Merge retrieved evidence and compute sentiment/confidence signals.
13. Run scenario module (bull/base/bear scoring + weighted recommendation) and add scenario context/signal.
14. If `use_financial_model_rebuild=true`, run selected financial module:
   - advanced engine when `use_advanced_financial_engine=true`
   - legacy lightweight engine otherwise
15. If `use_structured_valuation=true`, run structured valuation module (DCF + multi-comps + sensitivity + scenario-weighted target) and append valuation context/signal.
16. Call LLM and return markdown + metadata (or fallback markdown on LLM failure).

## MCP Augmentation Flow
1. Frontend sends `mcp_calls` in request payload.
2. Backend validates `mcp_calls` into structured items:
   - `server`
   - `tool`
   - `arguments`
3. During context preparation, backend dispatches MCP calls (`tools/call`) to configured MCP servers.
4. Each MCP response is converted into a compact text block:
   - format: `MCP {server}/{tool}: <result_json_excerpt>`
5. MCP text blocks are appended to `external_contexts`.
6. Prompt builder injects `external_contexts` into:
   - `External MCP/A2A context` section.
7. LLM chat completion consumes this enriched prompt, so MCP output directly augments recommendation quality.

### MCP Runtime Notes
- `MCP_SERVERS_JSON` maps server aliases to HTTP endpoints.
- If server alias is missing, backend logs skip and no MCP HTTP request is made.
- MCP transport uses JSON-RPC method `tools/call`.
- If `MCP_SERVERS_JSON` is declared multiple times in `.env`, last value wins.

### A2A Runtime Notes
- `A2A_AGENTS_JSON` maps agent aliases to HTTP endpoints.
- If agent alias is missing, backend logs skip and no A2A HTTP request is made.
- If `A2A_AGENTS_JSON` is declared multiple times in `.env`, last value wins.

## Dev Debug Logging
- API entry logs include:
  - ticker
  - bypass_web_search
  - `mcp_calls`/`a2a_calls` counts
  - MCP/A2A payload detail summaries
- Attachment logs include:
  - file count, filename, extension, size
  - extracted text size
- Search/vector/LLM logs include:
  - provider selection and query execution
  - vector search/upsert details
  - embedding/chat request timings
  - `AB_METRIC context_build` with stage counts/latencies
  - `AB_METRIC stream_total` with end-to-end response latency

## System Prompt Management
- System prompt source file:
  - `backend/system_prompt.md`
- Runtime behavior:
  - backend loads system prompt from file at runtime
  - file content is cached in-process (`lru_cache`) to avoid repeated disk reads
  - if file is missing, unreadable, or empty, backend falls back to built-in default prompt
- LLM request composition:
  - system message uses loaded prompt content
  - user message uses assembled research context (sources, signals, attachments, MCP/A2A, decomposition blocks)

## Conversation Memory Model (Current)
- Memory ownership:
  - frontend owns chat memory state
  - backend is stateless per request (no server-side conversation/session persistence)
- Conversation tracking key model:
  - backend does not receive or maintain a persistent conversation key/id
  - request context is derived from `chat_history` content order only
- Backend memory input:
  - receives `chat_history` as part of `ResearchRequest`
  - validates each turn via `ChatTurn` schema (`role`, `content`)
- Prompt usage:
  - backend uses most recent 12 turns: `req.chat_history[-12:]`
  - formatted into prompt section: `Recent chat history`
- Reset behavior:
  - when frontend sends empty/new `chat_history`, backend treats it as new conversation context
- Persistence notes:
  - current backend does not store conversation history in DB/vector store as chat transcript memory
  - vector DB is used for retrieval evidence (attachments/search/MCP/A2A text), not direct turn-by-turn chat log storage

## A/B Metrics and Dev Sink
- Dev sink file:
  - `backend/ab_metrics.log`
  - format: JSONL (one JSON record per line)
  - active only when `APP_ENV=dev`
  - auto-rotation enabled at 50MB with up to 3 backups:
    - `ab_metrics.log.1`, `ab_metrics.log.2`, `ab_metrics.log.3`
- Events written:
  - `context_build`
  - `stream_total`
- `context_build` payload fields:
  - `ticker`, `decomposition`, `bypass_web_search`, `primary_source_ingestion`, `structured_valuation`
  - `sources_total`, `sec_sources`, `web_sources`, `social_sources`, `decomposition_sources`, `vector_sources`, `external_contexts`
  - `points_attachment`, `points_sec`, `points_web`, `points_external`
  - `latency_total_ms`, `latency_attachment_ms`, `latency_sec_ms`, `latency_web_ms`, `latency_decomposition_ms`, `latency_external_ms`, `latency_vector_ms`
- `stream_total` payload fields:
  - `ticker`, `decomposition`, `bypass_web_search`
  - `output_chars`, `source_count`, `elapsed_ms`
- Additional dev payload sink:
  - `backend/debug_payload.txt` (LLM/embedding outbound request metadata in dev mode)
  - auto-rotation enabled at 50MB with up to 3 backups:
    - `debug_payload.txt.1`, `debug_payload.txt.2`, `debug_payload.txt.3`

## Query Decomposition ON vs OFF
- OFF (`use_query_decomposition=false`):
  - Runs baseline market/social queries only.
  - `decomposition_sources=0`.
  - No decomposition evidence block is appended to prompt context.
- ON (`use_query_decomposition=true`):
  - Runs additional professional-style sub-query retrieval over:
    - mandate_screening
    - business_industry
    - core_documents
    - historical_financials
    - sentiment
    - valuation
    - catalysts_risks
    - thesis_testing
    - portfolio_fit
  - Deduped decomposition sources are merged into main evidence and inserted into vector DB.
  - Decomposition evidence blocks include per-dimension objective, query count, and retrieved sources.
  - Decomposition evidence blocks are added to prompt context.
  - `decomposition_sources` indicates how many deduped sources came from decomposition retrieval.

## Primary Source Ingestion (SEC/EDGAR)
- Activation:
  - request field `use_primary_source_ingestion` (default: `false`)
- Behavior:
  - resolves ticker -> CIK using SEC company ticker map
  - fetches recent canonical filings (`10-K`, `10-Q`, `8-K`, `DEF 14A`, `20-F`, `6-K`)
  - builds filing archive URLs and extracts normalized snippet text
  - validates accession/doc fields before URL construction
  - de-duplicates filings by accession number
  - bounded retry/backoff for transient SEC errors (`429`, `5xx`, network errors)
  - ticker map cache with TTL to reduce repeated SEC map fetches
  - filing snippet extraction prioritizes key sections (business, risk factors, MD&A)
  - injects filings as `source_type=sec_filing`
  - ingests fetched primary-source evidence into vector DB before vector search
- Configuration:
  - `SEC_USER_AGENT` (required/recommended for SEC access policy compliance)
  - `SEC_MAX_FILINGS` (default: 4)
  - `SEC_REQUEST_RETRIES` (default: 2)
  - `SEC_RETRY_BACKOFF_MS` (default: 400)
  - `SEC_TICKER_CACHE_TTL_SEC` (default: 21600)
  - `SEC_FILING_EXCERPT_CHARS` (default: 900)
- Service:
  - `backend/app/services/sec_ingestion.py`

### Step-by-Step Runtime Flow (When `use_primary_source_ingestion=true`)
1. Frontend sends `use_primary_source_ingestion=true` in JSON or multipart request.
2. FastAPI parses the flag into `ResearchRequest.use_primary_source_ingestion`.
3. In `DeepResearchAgent.prepare_context`, backend checks the flag and starts SEC ingestion stage.
4. SEC ingestion service resolves ticker to CIK using SEC company ticker map (`company_tickers.json`) with TTL cache.
5. Backend fetches SEC submissions JSON (`data.sec.gov/submissions/CIK{cik}.json`).
6. Backend filters recent canonical forms (`10-K`, `10-Q`, `8-K`, `DEF 14A`, `20-F`, `6-K`) up to `SEC_MAX_FILINGS`.
7. For each filing, backend validates accession/document safety, builds archive URL, fetches filing text, and extracts normalized snippet.
8. Backend converts each filing into `Source` entries with `source_type="sec_filing"` and merges into `all_sources`.
9. If vector DB is enabled, backend embeds SEC snippets and upserts them into vector store before vector search stage.
10. Backend continues normal pipeline (optional web/decomposition, MCP/A2A, then embedding query + vector retrieval).
11. Final LLM prompt includes SEC filings in evidence block, and response `sources` also includes these `sec_filing` entries.

### Runtime Logs You Should See (Dev)
- `SEC ingestion completed ticker=... cik=... filings=... elapsed_ms=...`
- `Primary source ingestion completed ticker=... sources=... points=... elapsed_ms=...`
- `AB_METRIC context_build ... primary_source_ingestion=true ... sec_sources=... points_sec=...`

### Failure Behavior
- If CIK cannot be resolved or SEC request fails, backend logs warning and continues pipeline without failing whole request.
- SEC request retries/backoff apply for transient errors (`429`, `5xx`, network errors).

### One-Command SEC Verification
- Prints only SEC source titles/URLs from a live request:
```bash
curl -s http://localhost:8000/api/research \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"NVDA","company_name":"NVIDIA","question":"Show latest SEC primary sources","use_primary_source_ingestion":true,"bypass_web_search":true}' \
| jq -r '([.sources[]? | select(.source_type=="sec_filing") | "\(.title)\n\(.url)\n"] | if length==0 then "NO_SEC_SOURCES_FOUND" else .[] end)'
```

## Scenario Module
- Service:
  - `backend/app/services/scenario_analyzer.py`
- Inputs:
  - `risk_tolerance`
  - computed signals (`Market sentiment`, `Social sentiment`, `Research confidence`)
  - source count (evidence breadth adjustment)
- Outputs:
  - scenario scores: `bull_score`, `base_score`, `bear_score`
  - scenario weights: `bull_weight`, `base_weight`, `bear_weight`
  - `weighted_score`
  - recommendation: `Buy`/`Hold`/`Sell`
  - `confidence_pct`
  - rationale text
- Integration behavior:
  - executed during context preparation
  - added to prompt section: `Scenario analysis`
  - added to API response signals as `Scenario weighted score`
  - fallback markdown recommendation prioritizes scenario recommendation when available

## Scenario Impact on Backend Process
- Stage 1: signal-to-scenario transformation
  - after market/social/confidence signals are computed, backend runs scenario evaluation
  - computes bull/base/bear scores and weighted recommendation for the active risk profile
- Stage 2: prompt augmentation
  - backend appends a `Scenario analysis` block to LLM user prompt
  - includes scenario scores, weights, weighted score, recommendation, and rationale
- Stage 3: response metadata enrichment
  - backend appends `Scenario weighted score` to `signals` returned in response metadata
- Stage 4: fallback behavior override
  - if LLM request fails/unavailable, fallback recommendation uses scenario recommendation/confidence first
  - this replaces earlier simple sentiment-only fallback when scenario output exists

## Financial Model Rebuild (Opt-In)
- Activation:
  - request field `use_financial_model_rebuild` (default: `false`)
  - optional `financial_model_input` payload:
    - `periods[]` with fields such as `year`, `revenue`, `net_income`, `total_assets`, `total_liabilities`, `total_equity`, `operating_cash_flow`, `capex`
    - `forecast_years` (1-5)
- Behavior when enabled:
  - with valid input:
    - runs rebuild/validation + base/bull/bear forecast
    - appends `Financial model weighted score` to signals
    - appends `Financial model analysis` block into LLM prompt
  - without input:
    - does not break existing flow
    - adds neutral model signal and explanatory issue message
- Fallback recommendation behavior:
  - when scenario + valid financial model are available, fallback blends scores:
    - `0.6 * scenario_weighted_score + 0.4 * financial_model_weighted_score`

## Advanced Financial Engine (Opt-In)
- Activation:
  - request field `use_advanced_financial_engine` (default: `false`)
  - optional `advanced_financial_input` payload
- Behavior:
  - executes explicit linked schedule model for each forecast period
  - supports bull/base/bear assumption transforms from base schedules
  - validates forecast balance linkage by reporting `balance_check_gap` per period
  - when enabled with `use_financial_model_rebuild=true`, advanced engine output replaces legacy model output
  - when structured valuation is enabled, valuation uses advanced model output if available

### Advanced Financial Input Requirements
- Root object:
  - `initial_state` (required object)
  - `forecast` (required array, at least 1 period)
- `initial_state` required fields:
  - `year` (int)
  - `cash` (number)
  - `debt` (number)
  - `retained_earnings` (number)
  - `share_capital` (number)
  - `ppe_net` (number)
  - `other_assets` (number)
  - `other_liabilities` (number)
  - `shares_outstanding` (number, > 0)
- `forecast[]` required fields per period:
  - `year` (int)
  - `volume` (number)
  - `price` (number)
- `forecast[]` optional but recommended fields:
  - `other_revenue`, `gross_margin`, `opex_ratio`
  - `ar_days`, `inventory_days`, `ap_days`
  - `capex_pct_revenue`, `depreciation_pct_ppe`
  - `new_borrowing`, `debt_repayment`, `interest_rate`
  - `tax_rate`, `dividends`

### How To Create `advanced_financial_input` (Step-by-Step)
1. Pick base year and forecast horizon:
   - Use latest reported year for `initial_state.year`.
   - Create one `forecast[]` row per forward year (`2025`, `2026`, `2027`, ...).
2. Fill opening balance state from latest statements:
   - `cash`, `debt`, `retained_earnings`, `share_capital`, `ppe_net`, `other_assets`, `other_liabilities`, `shares_outstanding`.
3. Set revenue drivers per forecast year:
   - `volume`, `price`, `other_revenue`.
   - Revenue model in engine: `revenue = (volume * price) + other_revenue`.
4. Set operating assumptions:
   - `gross_margin` (gross profit / revenue).
   - `opex_ratio` (operating expense / revenue).
5. Set working-capital assumptions:
   - `ar_days = accounts_receivable / revenue * 365`
   - `inventory_days = inventory / COGS * 365`
   - `ap_days = accounts_payable / COGS * 365`
6. Set capex/depreciation assumptions:
   - `capex_pct_revenue = capex / revenue`
   - `depreciation_pct_ppe = depreciation / net_ppe`.
7. Set financing assumptions:
   - `new_borrowing`, `debt_repayment`.
   - `interest_rate = interest_expense / average_debt`.
8. Set tax and payout assumptions:
   - `tax_rate = income_tax_expense / pre_tax_income`.
   - `dividends` as planned annual payout.
9. Validate before submit:
   - Keep rates as decimals (`0.21` means 21%).
   - Keep days in day units (`45`, `30`, `28`).
   - Ensure forecast years are sequential and numeric.
10. Submit in request:
   - set `use_financial_model_rebuild=true`
   - set `use_advanced_financial_engine=true`
   - include `advanced_financial_input`.

### If You Do Not Have Detailed Schedules Yet
- You can still enable `use_advanced_financial_engine=true` and provide only `financial_model_input`.
- Backend will auto-convert basic financial input into conservative advanced assumptions as fallback.

### Advanced Financial Input Sample JSON
```json
{
  "initial_state": {
    "year": 2024,
    "cash": 300.0,
    "debt": 500.0,
    "retained_earnings": 1200.0,
    "share_capital": 600.0,
    "ppe_net": 900.0,
    "other_assets": 400.0,
    "other_liabilities": 300.0,
    "shares_outstanding": 2500.0
  },
  "forecast": [
    {
      "year": 2025,
      "volume": 15.0,
      "price": 100.0,
      "other_revenue": 20.0,
      "gross_margin": 0.60,
      "opex_ratio": 0.30,
      "ar_days": 45.0,
      "inventory_days": 30.0,
      "ap_days": 28.0,
      "capex_pct_revenue": 0.08,
      "depreciation_pct_ppe": 0.12,
      "new_borrowing": 0.0,
      "debt_repayment": 40.0,
      "interest_rate": 0.04,
      "tax_rate": 0.21,
      "dividends": 0.0
    }
  ]
}
```

## Structured Valuation (Opt-In)
- Activation:
  - request field `use_structured_valuation` (default: `false`)
  - optional `valuation_input` payload:
    - `current_price`
    - `shares_outstanding`
    - `net_debt`
    - `wacc`
    - `terminal_growth`
    - `terminal_fcf_multiple`
    - `peer_pe`
    - `peer_ev_ebitda`
    - `peer_p_fcf`
    - `peer_ev_fcf`
- Behavior:
  - uses financial-model base-case free-cash-flow forecast as valuation foundation
  - if financial model rebuild is not separately enabled but `financial_model_input` exists, backend still runs the model internally for valuation
  - computes:
    - DCF equity value and implied price/share
    - relative comps implied price/share (`P/E`, `EV/EBITDA`, `P/FCF`, `EV/FCF`)
    - blended target price and upside/downside vs current price
    - bull/base/bear implied target prices
    - scenario-weighted target by risk profile weights
    - sensitivity grid over WACC and terminal growth assumptions
  - appends valuation block into LLM prompt section: `Structured valuation analysis`
  - appends response signal: `Structured valuation upside (%)`
  - includes optional `valuation` object in API response metadata with:
    - DCF/comps/blended outputs
    - valuation recommendation + confidence
    - sensitivity grid rows (`wacc`, `terminal_growth`, `implied_price`)
- Fallback recommendation behavior:
  - when scenario + financial model + valuation are available, fallback recommendation uses weighted blend:
    - `0.5 * scenario + 0.3 * financial_model + 0.2 * valuation_score`
  - when scenario + valuation are available (without valid financial model):
    - `0.75 * scenario + 0.25 * valuation_score`

### Structured Valuation Sample JSON
- `valuation_input` example:
```json
{
  "current_price": 120.5,
  "shares_outstanding": 2490.0,
  "net_debt": 2100.0,
  "wacc": 0.10,
  "terminal_growth": 0.03,
  "terminal_fcf_multiple": 18.0,
  "peer_pe": 24.0,
  "peer_ev_ebitda": 14.0,
  "peer_p_fcf": 18.0,
  "peer_ev_fcf": 21.0
}
```

- `POST /api/chat/stream` example with structured valuation enabled:
```json
{
  "ticker": "NVDA",
  "company_name": "NVIDIA",
  "market": "US",
  "question": "Provide valuation-based recommendation.",
  "horizon_days": 180,
  "risk_tolerance": "moderate",
  "bypass_web_search": false,
  "use_query_decomposition": true,
  "use_primary_source_ingestion": true,
  "use_financial_model_rebuild": true,
  "use_advanced_financial_engine": true,
  "use_structured_valuation": true,
  "financial_model_input": {
    "forecast_years": 3,
    "periods": [
      {
        "year": 2022,
        "revenue": 1000,
        "net_income": 120,
        "total_assets": 2000,
        "total_liabilities": 900,
        "total_equity": 1100,
        "cash": 220,
        "operating_cash_flow": 180,
        "capex": 70,
        "debt": 500
      },
      {
        "year": 2023,
        "revenue": 1150,
        "net_income": 150,
        "total_assets": 2150,
        "total_liabilities": 940,
        "total_equity": 1210,
        "cash": 250,
        "operating_cash_flow": 215,
        "capex": 80,
        "debt": 480
      },
      {
        "year": 2024,
        "revenue": 1300,
        "net_income": 185,
        "total_assets": 2320,
        "total_liabilities": 980,
        "total_equity": 1340,
        "cash": 290,
        "operating_cash_flow": 250,
        "capex": 92,
        "debt": 460
      }
    ]
  },
  "advanced_financial_input": {
    "initial_state": {
      "year": 2024,
      "cash": 300.0,
      "debt": 500.0,
      "retained_earnings": 1200.0,
      "share_capital": 600.0,
      "ppe_net": 900.0,
      "other_assets": 400.0,
      "other_liabilities": 300.0,
      "shares_outstanding": 2490.0
    },
    "forecast": [
      {
        "year": 2025,
        "volume": 15.0,
        "price": 100.0,
        "other_revenue": 20.0,
        "gross_margin": 0.60,
        "opex_ratio": 0.30,
        "ar_days": 45.0,
        "inventory_days": 30.0,
        "ap_days": 28.0,
        "capex_pct_revenue": 0.08,
        "depreciation_pct_ppe": 0.12,
        "new_borrowing": 0.0,
        "debt_repayment": 40.0,
        "interest_rate": 0.04,
        "tax_rate": 0.21,
        "dividends": 0.0
      }
    ]
  },
  "valuation_input": {
    "current_price": 120.5,
    "shares_outstanding": 2490.0,
    "net_debt": 2100.0,
    "wacc": 0.10,
    "terminal_growth": 0.03,
    "terminal_fcf_multiple": 18.0,
    "peer_pe": 24.0,
    "peer_ev_ebitda": 14.0,
    "peer_p_fcf": 18.0,
    "peer_ev_fcf": 21.0
  },
  "chat_history": [],
  "mcp_calls": [],
  "a2a_calls": []
}
```

### Structured Valuation Multipart Upload Sample (`/api/chat/stream/upload`)
```bash
curl -N -X POST "http://localhost:8000/api/chat/stream/upload" \
  -F 'ticker=NVDA' \
  -F 'company_name=NVIDIA' \
  -F 'market=US' \
  -F 'question=Provide valuation-based recommendation with document context.' \
  -F 'horizon_days=180' \
  -F 'risk_tolerance=moderate' \
  -F 'bypass_web_search=false' \
  -F 'use_query_decomposition=true' \
  -F 'use_primary_source_ingestion=true' \
  -F 'use_financial_model_rebuild=true' \
  -F 'use_advanced_financial_engine=true' \
  -F 'use_structured_valuation=true' \
  -F 'financial_model_input={"forecast_years":3,"periods":[{"year":2022,"revenue":1000,"net_income":120,"total_assets":2000,"total_liabilities":900,"total_equity":1100,"cash":220,"operating_cash_flow":180,"capex":70,"debt":500},{"year":2023,"revenue":1150,"net_income":150,"total_assets":2150,"total_liabilities":940,"total_equity":1210,"cash":250,"operating_cash_flow":215,"capex":80,"debt":480},{"year":2024,"revenue":1300,"net_income":185,"total_assets":2320,"total_liabilities":980,"total_equity":1340,"cash":290,"operating_cash_flow":250,"capex":92,"debt":460}]}' \
  -F 'advanced_financial_input={"initial_state":{"year":2024,"cash":300.0,"debt":500.0,"retained_earnings":1200.0,"share_capital":600.0,"ppe_net":900.0,"other_assets":400.0,"other_liabilities":300.0,"shares_outstanding":2490.0},"forecast":[{"year":2025,"volume":15.0,"price":100.0,"other_revenue":20.0,"gross_margin":0.60,"opex_ratio":0.30,"ar_days":45.0,"inventory_days":30.0,"ap_days":28.0,"capex_pct_revenue":0.08,"depreciation_pct_ppe":0.12,"new_borrowing":0.0,"debt_repayment":40.0,"interest_rate":0.04,"tax_rate":0.21,"dividends":0.0}]}' \
  -F 'valuation_input={"current_price":120.5,"shares_outstanding":2490.0,"net_debt":2100.0,"wacc":0.10,"terminal_growth":0.03,"terminal_fcf_multiple":18.0,"peer_pe":24.0,"peer_ev_ebitda":14.0,"peer_p_fcf":18.0,"peer_ev_fcf":21.0}' \
  -F 'chat_history=[]' \
  -F 'mcp_calls=[]' \
  -F 'a2a_calls=[]' \
  -F 'files=@/absolute/path/to/earnings-note.pdf;type=application/pdf'
```

## What Financial Model Rebuild Adds to Research Quality
- Adds quantitative discipline beyond text retrieval:
  - transforms historical financial input into structured model outputs
  - validates accounting consistency per period before forecasting
- Adds forward-looking depth:
  - produces explicit base/bull/bear projections for revenue, net income, and free cash flow
  - computes a weighted model score with recommendation/confidence
- Improves recommendation grounding:
  - injects `Financial model analysis` into LLM prompt so recommendations can reference modeled fundamentals
  - exposes `Financial model weighted score` in response signals for UI/traceability
- Improves resilience in fallback mode:
  - when LLM is unavailable, fallback recommendation can blend scenario + financial-model scores
  - reduces reliance on sentiment-only heuristics
- Supports A/B validation:
  - because feature is opt-in (`use_financial_model_rebuild`), output quality can be compared with feature on/off
## Web Search Logic
- Provider selection order:
  1. Exa (`EXA_API_KEY`)
  2. Tavily (`TAVILY_API_KEY`)
  3. Serper (`SERPER_API_KEY`)
  4. DuckDuckGo fallback
- Query groups:
  - Market queries (news, earnings/guidance, industry trend)
  - Social queries (x/reddit sentiment + investor sentiment)

## Vector Search Logic
- Query basis:
  - Embedding input is built from request-level intent:
    - `ticker + company_name + question`
- Qdrant search behavior:
  - Primary endpoint: `/collections/{collection}/points/search`
  - Fallback endpoint: `/collections/{collection}/points/query`
  - Result limit: `4` (default in current pipeline)
- Vector upsert behavior:
  - Attachments, web sources, and external MCP/A2A context are embedded and upserted as points with payload:
    - `title`, `url`, `text`, `source_type`, `ticker`

## Use Cases Covered
- Generate a full stock research brief from a single ticker question.
- Stream research response token/chunk-by-chunk for chat UX.
- Continue analysis across follow-up turns using conversation memory.
- Invoke MCP tools (e.g., custom market-data tools) and blend outputs into recommendation.
- Invoke partner/remote agents (A2A) such as risk agent or portfolio agent for collaborative analysis.
- Enrich research using uploaded documents (e.g., earnings PDF).
- Perform social sentiment-aware recommendation output.
- Augment responses with vector-store context when configured.
- Run with primary web search providers or fallback search mode.
- Return source traceability with URLs/snippets for user review.
- Reject unsafe/oversized/unsupported uploads with descriptive `400` errors.

## Backend Test Cases
- Test file: `backend/tests/test_main_api.py`
  - `test_health_returns_ok`:
    - validates `GET /health` returns `200` and `{"status":"ok"}`
  - `test_stream_endpoint_emits_chunk_meta_done`:
    - validates SSE event sequence includes `chunk`, `meta`, `done`
    - validates streamed assistant content assembly path
  - `test_upload_endpoint_parses_form_data_and_forwards_request`:
    - validates multipart parsing for:
      - `bypass_web_search`
      - `use_query_decomposition`
      - `use_financial_model_rebuild`
      - `chat_history`
      - `mcp_calls`
      - `a2a_calls`
      - `attachment_texts`
      - `financial_model_input`
  - `test_upload_endpoint_rejects_invalid_json`:
    - validates `400` behavior on malformed JSON form fields
- Test file: `backend/tests/test_file_parser.py`
  - `test_extract_text_from_txt_file`:
    - validates text extraction success for `.txt`
  - `test_rejects_unsupported_extension`:
    - validates extension allowlist enforcement
  - `test_rejects_oversize_file`:
    - validates max-file-size guardrail enforcement
- Test file: `backend/tests/test_scenario_analyzer.py`
  - `test_aggressive_profile_biases_bull_weight`:
    - validates risk-profile weighting scheme
  - `test_weighted_score_maps_to_hold_for_neutral_signals`:
    - validates neutral signal path maps to `Hold`
  - `test_positive_signals_raise_buy_probability`:
    - validates positive inputs bias recommendation toward `Buy`
- Test file: `backend/tests/test_financial_model.py`
  - `test_rebuild_with_valid_history_produces_forecast`:
    - validates forecast generation on valid multi-year financial input
  - `test_rebuild_flags_balance_sheet_mismatch`:
    - validates accounting-identity validation flags inconsistent periods
- Test file: `backend/tests/test_sec_ingestion.py`
  - `test_search_primary_sources_returns_filings`:
    - validates SEC ticker resolution + filings mapping into `Source`
  - `test_search_primary_sources_returns_empty_when_ticker_unknown`:
    - validates safe skip path when CIK cannot be resolved
  - `test_extract_recent_filings_filters_forms`:
    - validates canonical-form filtering behavior
- Execution command:
  - `PYTHONPATH=backend /Users/hinadome/.pyenv/versions/3.12.5/envs/awsworkshop/bin/python -m unittest discover -s backend/tests -v`

## Outputs Produced
- Markdown report with fixed analysis sections:
  - Executive Summary
  - Market and Company Trend Analysis
  - Social Sentiment Analysis
  - Risks and Catalysts
  - Recommendation
  - Sources
- Structured response metadata:
  - ticker/company
  - generated timestamp
  - signals
  - source list

## Troubleshooting Matrix
- Symptom: `OPTIONS /api/chat/stream 400 Bad Request`
  Likely cause: CORS origin mismatch between frontend URL and backend CORS config.
  Fix: Update `CORS_ORIGINS`/`CORS_ORIGIN_REGEX`, restart backend.
- Symptom: `MCP configured servers=[]` and `server_not_configured`
  Likely cause: `MCP_SERVERS_JSON` missing/overridden in `.env` (duplicate keys, invalid JSON, alias mismatch).
  Fix: Keep one valid `MCP_SERVERS_JSON` entry and ensure frontend `server` value matches alias.
- Symptom: A2A payload seen but no A2A server request
  Likely cause: `A2A_AGENTS_JSON` empty/invalid or agent alias mismatch.
  Fix: Set valid `A2A_AGENTS_JSON` and match frontend `agent` value exactly.
- Symptom: `401 Unauthorized` from embeddings/chat endpoint
  Likely cause: invalid API key, wrong base URL, or provider/model mismatch.
  Fix: Verify `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and model names for your provider.
- Symptom: vector retrieval warning after Qdrant request
  Likely cause: Qdrant auth/collection mismatch or endpoint compatibility issue.
  Fix: Verify `QDRANT_URL`, `QDRANT_API_KEY`, collection exists, and inspect logged error details.
- Symptom: files uploaded but not used in final output
  Likely cause: upload endpoint not used, extraction produced empty text, or parsing rejected.
  Fix: Use `/api/chat/stream/upload`, check attachment extraction logs and 400 details.
- Symptom: no MCP/A2A logs in console
  Likely cause: app not running in dev mode or logger output not from expected process.
  Fix: set `APP_ENV=dev`, restart processes, and verify the correct process/port is targeted.
