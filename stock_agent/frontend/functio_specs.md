# Frontend Functional Specs

## Implemented Functionalities
- Chat-style stock research interface at `/stock-assistant`.
- Sidebar context controls per research turn:
  - ticker
  - company name
  - market
  - investment horizon (days)
  - risk tolerance
  - `Bypass Web Search` checkbox (default checked)
  - `Use Query Decomposition` checkbox (default unchecked)
  - `Use Primary Source Ingestion (SEC/EDGAR)` checkbox (default unchecked)
  - `Use Financial Model Rebuild` checkbox (default unchecked)
  - `Use Advanced Financial Engine` checkbox (default unchecked)
  - `Use Structured Valuation (DCF + Comps)` checkbox (default unchecked)
  - financial input mode selector:
    - `Form Builder`
    - `Raw JSON`
  - dedicated financial period form-builder (shown when financial model rebuild is enabled):
    - forecast years
    - repeatable period rows
    - year, revenue, net income, total assets, total liabilities, total equity
    - optional cash, operating cash flow, capex, debt
  - valuation input mode selector (shown when structured valuation is enabled):
    - `Form Builder`
    - `Raw JSON`
  - dedicated valuation assumptions form-builder:
    - current price
    - shares outstanding
    - net debt
    - WACC
    - terminal growth
    - terminal FCF multiple
    - peer P/E
    - peer EV/EBITDA
    - peer P/FCF
    - peer EV/FCF
  - advanced financial JSON input area (shown when advanced engine is enabled)
  - optional MCP call builder rows (server/tool/arguments)
  - optional A2A call builder rows (agent/task/context)
- Multi-turn conversation UI with message history:
  - user messages
  - assistant messages
- Streaming assistant output rendering (incremental updates while backend generates).
- SSE event handling for:
  - `chunk` (append streamed markdown text)
  - `meta` (attach final structured response)
  - `error` (show failure state)
- File attachment from UI (multi-file):
  - accepted extensions: `.pdf`, `.txt`, `.md`, `.csv`
  - sends files as multipart request when selected
  - client-side validation for count/type/size
    - max 5 files
    - max 5MB per file
- Fallback transport behavior:
  - no files: JSON request to `/api/chat/stream`
  - files attached: multipart request to `/api/chat/stream/upload`
- Chat history forwarding to backend for context memory (`chat_history`).
- MCP/A2A forwarding to backend:
  - sends `mcp_calls` and `a2a_calls` in JSON stream mode
  - sends `mcp_calls` and `a2a_calls` as form fields in upload mode
  - rows with empty required fields are not sent
  - invalid JSON in row object fields blocks submit with frontend error
- Web bypass forwarding:
  - sends `bypass_web_search` in both JSON and multipart modes
- Query decomposition forwarding:
  - sends `use_query_decomposition` in both JSON and multipart modes
- Primary-source ingestion forwarding:
  - sends `use_primary_source_ingestion` in both JSON and multipart modes

## Primary Source Ingestion Toggle Flow (Frontend -> Backend)
1. User enables `Use Primary Source Ingestion (SEC/EDGAR)` checkbox in sidebar.
2. Frontend includes `use_primary_source_ingestion: true` in request payload:
   - JSON mode: `POST /api/chat/stream`
   - multipart mode: `POST /api/chat/stream/upload`
3. Backend executes SEC/EDGAR primary filing retrieval stage before vector search.
4. Retrieved SEC filings are merged into backend evidence and can appear in response `sources` list as `source_type=sec_filing`.
5. Assistant markdown output uses that SEC evidence as part of recommendation context.
- Financial model forwarding:
  - sends `use_financial_model_rebuild` in both JSON and multipart modes
  - if mode is `Form Builder`, builds and sends `financial_model_input` from period rows
  - if mode is `Raw JSON`, parses and sends `financial_model_input` from textarea
  - invalid row values or invalid JSON block submit with frontend error
- Structured valuation forwarding:
  - sends `use_structured_valuation` in both JSON and multipart modes
  - if valuation mode is `Form Builder`, builds and sends `valuation_input` from assumptions fields
  - if valuation mode is `Raw JSON`, parses and sends `valuation_input` from textarea
  - invalid valuation values or invalid JSON block submit with frontend error
- Advanced financial forwarding:
  - sends `use_advanced_financial_engine` in both JSON and multipart modes
  - parses/sends `advanced_financial_input` JSON when provided
  - invalid advanced financial JSON blocks submit with frontend error

## Advanced Financial Input (What To Provide)
- Root keys:
  - `initial_state`
  - `forecast` (array of yearly periods)
- `initial_state` keys:
  - required: `year`, `cash`, `debt`, `retained_earnings`, `share_capital`, `ppe_net`, `other_assets`, `other_liabilities`, `shares_outstanding`
- `forecast[]` minimal keys per period:
  - `year`, `volume`, `price`
- strongly recommended forecast keys:
  - `gross_margin`, `opex_ratio`, `tax_rate`
  - `ar_days`, `inventory_days`, `ap_days`
  - `capex_pct_revenue`, `depreciation_pct_ppe`
  - `new_borrowing`, `debt_repayment`, `interest_rate`, `dividends`
- input tips:
  - Use sequential years (`2025`, `2026`, `2027`...)
  - Keep rates as decimals (example: `0.21` for 21%)
  - Keep day assumptions in day units (`45`, `30`, `28`)

## Advanced Financial Input (Step-by-Step)
1. Enable:
   - `Use Financial Model Rebuild`
   - `Use Advanced Financial Engine`
2. Collect latest annual values from filings or financial statements:
   - cash, debt, retained earnings, share capital, net PPE, other assets/liabilities, shares outstanding.
3. Build `initial_state` from those latest values.
4. Add one `forecast` row per future year and set:
   - `year`, `volume`, `price` (minimum required).
5. Add recommended operating assumptions:
   - `gross_margin`, `opex_ratio`, `tax_rate`.
6. Add working-capital assumptions:
   - `ar_days`, `inventory_days`, `ap_days`.
7. Add capex/depreciation and financing assumptions:
   - `capex_pct_revenue`, `depreciation_pct_ppe`, `new_borrowing`, `debt_repayment`, `interest_rate`, `dividends`.
8. Paste JSON into `Advanced Financial Input JSON` field and send request.

### Quick Mapping Formulas
- `gross_margin = gross_profit / revenue`
- `opex_ratio = operating_expense / revenue`
- `ar_days = accounts_receivable / revenue * 365`
- `inventory_days = inventory / COGS * 365`
- `ap_days = accounts_payable / COGS * 365`
- `capex_pct_revenue = capex / revenue`
- `depreciation_pct_ppe = depreciation / net_ppe`
- `interest_rate = interest_expense / average_debt`
- `tax_rate = income_tax_expense / pre_tax_income`

### Minimal Path (No Detailed Schedule Yet)
- Keep `Use Advanced Financial Engine` on.
- Provide only `financial_model_input` (builder or JSON).
- Backend auto-converts to conservative advanced assumptions.

## Structured Valuation Raw JSON Samples
- Raw JSON for `valuation_input` textarea:
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

- Example JSON request body sent to `/api/chat/stream`:
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

- Multipart example sent to `/api/chat/stream/upload` (used when files are attached):
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
- Markdown-style assistant rendering (lightweight parser for):
  - headings (`#`, `##`, `###`)
  - bullet lists (`- item`)
  - blockquotes (`> text`)
  - paragraphs
- Per-response analytics panes in chat cards:
  - signals
  - structured valuation summary (when backend returns `valuation`)
  - valuation sensitivity grid table (WACC x terminal growth -> implied price)
  - retrieved sources
- Loading and error states for user feedback.
- Session control actions:
  - `New Chat` resets current conversation state
  - `Download Markdown` exports latest assistant output as `.md`
- Auto-scroll to newest message during streaming and after response completion.
- Dynamic UI builders:
  - add/remove MCP call rows
  - add/remove A2A call rows

## Conversation Memory Model (Current)
- Memory ownership:
  - conversation is stored in frontend React state (`messages`)
  - initialized with a local `WELCOME_MESSAGE`
- Conversation tracking key model:
  - no persistent `conversation_id`/session key is implemented
  - each message uses ephemeral UI ids only:
    - user message id: `u-${Date.now()}`
    - assistant message id: `a-${Date.now()}-${random}`
  - backend context continuity is driven by ordered `chat_history` turns, not by stable key lookup
- Per-turn tracking:
  - on submit, frontend appends current user message + placeholder assistant message
  - streaming chunks continuously update assistant message text
  - final `meta` event binds structured response data to that assistant turn
- Backend context forwarding:
  - frontend sends `chat_history` on every request
  - excludes welcome message
  - sends only latest 12 turns (`slice(-12)`)
- Reset behavior:
  - `New Chat` clears local messages back to welcome state
  - effectively starts a new conversation context for subsequent backend requests
- Persistence notes:
  - no localStorage/sessionStorage/database persistence for chat history in current implementation
  - page refresh starts a fresh in-memory session

## Use Cases Covered
- User asks for stock recommendation and receives streaming research response.
- User asks follow-up questions; prior turns are sent for context continuity.
- User attaches a quarterly report PDF to enrich analysis context.
- User attaches notes/CSV/TXT alongside query for deeper recommendation input.
- User reviews confidence/sentiment signals and source links per assistant response.
- User retries with modified settings (e.g., risk tolerance, horizon) for comparison.
- User invokes external MCP tools and A2A agents as part of one research turn.
- User enables SEC/EDGAR primary-source ingestion to bring canonical filings into analysis context.
- User enables financial-model rebuild and sends historical financial periods for scenario-aware analysis.
- User enables structured valuation and sends valuation assumptions to generate DCF/comps target-price context.
- User enables advanced financial engine and submits period-level schedule assumptions for deeper linked modeling.
- User reviews valuation sensitivity table directly in chat response card.
- User starts a fresh session without reloading the page.
- User downloads generated report markdown for sharing or archival.

## Frontend Test Cases
- Test file: `frontend/tests/stock-assistant-helpers.test.mjs`
  - `parseSseEvent parses JSON event payload`:
    - validates SSE parsing for JSON `data:` blocks
  - `parseSseEvent returns raw string when data is not JSON`:
    - validates SSE parsing fallback for non-JSON payload
  - `buildMcpCalls filters incomplete rows and parses arguments`:
    - validates MCP builder row filtering and JSON conversion
  - `buildA2aCalls filters incomplete rows and parses context`:
    - validates A2A builder row filtering and JSON conversion
  - `validateAttachedFiles rejects unsupported extension`:
    - validates client-side extension guardrail
  - `validateAttachedFiles accepts valid files`:
    - validates positive attachment validation path
  - `toReadableRequestError returns network-focused message for TypeError`:
    - validates readable message mapping for fetch/network failures
- Covered helper module:
  - `frontend/lib/stock-assistant-helpers.mjs`
  - used by `frontend/pages/stock-assistant.tsx`
- Execution command:
  - `pnpm --dir frontend test`

## API Dependencies (from frontend perspective)
- `POST /api/chat/stream` for JSON-based streaming chat research.
- `POST /api/chat/stream/upload` for multipart + file-assisted streaming chat research.

## MCP Input Mapping
- MCP builder rows are translated to payload entries:
  - `server` -> MCP server alias configured on backend
  - `tool` -> MCP tool name
  - `arguments JSON` -> MCP `arguments` object
- Backend consumes these entries as `mcp_calls` and executes remote MCP `tools/call`.
- Returned MCP data is not shown as a separate frontend panel by default; it is injected into backend LLM prompt context and reflected in assistant output.

## A2A Input Mapping
- A2A builder rows are translated to payload entries:
  - `agent` -> A2A alias configured on backend
  - `task` -> remote agent task text
  - `context JSON` -> A2A `context` object
- Returned A2A data is injected into backend LLM prompt context and reflected in assistant output.

## Troubleshooting Matrix
- Symptom: UI error `Research request failed: Load failed` or network error
  Likely cause: backend unreachable or CORS preflight blocked.
  Fix: verify backend is running, confirm `NEXT_PUBLIC_BACKEND_URL`, and check backend CORS config.
- Symptom: MCP/A2A row entered but backend shows `mcp_calls=0` or `a2a_calls=0`
  Likely cause: required row fields left empty or row removed by filtering.
  Fix: ensure MCP has `server` + `tool`, A2A has `agent` + `task`.
- Symptom: Submit blocked with JSON parse error
  Likely cause: invalid JSON in MCP `arguments` or A2A `context`.
  Fix: provide valid JSON object syntax (e.g. `{\"ticker\":\"NVDA\"}`).
- Symptom: MCP/A2A payload appears in backend but no remote server request
  Likely cause: backend alias config mismatch (`MCP_SERVERS_JSON`/`A2A_AGENTS_JSON`).
  Fix: align frontend alias values with backend `.env` map keys.
- Symptom: Web search expected but no web data used
  Likely cause: `Bypass Web Search` remains checked.
  Fix: uncheck `Bypass Web Search` and resend request.
- Symptom: Attachment chosen but no attachment effect
  Likely cause: file type/size rejected or empty extraction text.
  Fix: use allowed file types and check upload/attachment logs on backend.
- Symptom: Structured valuation enabled but output looks neutral
  Likely cause: missing/invalid financial model input or valuation assumptions.
  Fix: provide financial periods (or raw financial model JSON) and optional valuation assumptions.
- Symptom: Download Markdown button fails to export
  Likely cause: no assistant response generated yet.
  Fix: run at least one successful request before download.
