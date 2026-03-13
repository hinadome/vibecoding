import Head from "next/head";
import { FormEvent, Fragment, useEffect, useRef, useState } from "react";
import {
  MAX_ATTACH_BYTES,
  MAX_ATTACH_FILES,
  buildA2aCalls,
  buildMcpCalls,
  parseSseEvent,
  toReadableRequestError,
  validateAttachedFiles,
} from "../lib/stock-assistant-helpers.mjs";

type RiskTolerance = "conservative" | "moderate" | "aggressive";
type ChatRole = "user" | "assistant";
type FinancialInputMode = "builder" | "json";
type ValuationInputMode = "builder" | "json";

interface ResearchSource {
  title: string;
  url: string;
  snippet: string;
  source_type: string;
}

interface ResearchSignal {
  label: string;
  value: number;
  rationale: string;
}

interface ResearchResponse {
  ticker: string;
  company_name?: string | null;
  generated_at: string;
  markdown: string;
  signals: ResearchSignal[];
  sources: ResearchSource[];
  valuation?: {
    dcf_equity_value: number;
    dcf_price_per_share: number;
    comps_price_per_share: number;
    blended_target_price: number;
    bull_target_price: number;
    base_target_price: number;
    bear_target_price: number;
    scenario_weighted_target_price: number;
    scenario_bull_weight: number;
    scenario_base_weight: number;
    scenario_bear_weight: number;
    ev_ebitda_price_per_share: number;
    p_fcf_price_per_share: number;
    upside_pct: number;
    recommendation: string;
    confidence_pct: number;
    assumptions: Record<string, number>;
    sensitivity_grid: Array<{
      wacc: number;
      terminal_growth: number;
      implied_price: number;
    }>;
  } | null;
}

interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  result?: ResearchResponse;
}

interface MCPCallRow {
  id: string;
  server: string;
  tool: string;
  argumentsJson: string;
}

interface A2ACallRow {
  id: string;
  agent: string;
  task: string;
  contextJson: string;
}

interface FinancialPeriodRow {
  id: string;
  year: string;
  revenue: string;
  netIncome: string;
  totalAssets: string;
  totalLiabilities: string;
  totalEquity: string;
  cash: string;
  operatingCashFlow: string;
  capex: string;
  debt: string;
}

interface ValuationInputFields {
  currentPrice: string;
  sharesOutstanding: string;
  netDebt: string;
  wacc: string;
  terminalGrowth: string;
  terminalFcfMultiple: string;
  peerPe: string;
  peerEvEbitda: string;
  peerPFcf: string;
  peerEvFcf: string;
}

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Ask about a stock and I will run deep research with market trend analysis, social sentiment scanning, and a markdown recommendation.",
};
const newMcpRow = (): MCPCallRow => ({
  id: `mcp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  server: "",
  tool: "",
  argumentsJson: "{}",
});
const newA2aRow = (): A2ACallRow => ({
  id: `a2a-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  agent: "",
  task: "",
  contextJson: "{}",
});
const newFinancialPeriodRow = (): FinancialPeriodRow => ({
  id: `fin-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
  year: "",
  revenue: "",
  netIncome: "",
  totalAssets: "",
  totalLiabilities: "",
  totalEquity: "",
  cash: "",
  operatingCashFlow: "",
  capex: "",
  debt: "",
});
const defaultValuationInput = (): ValuationInputFields => ({
  currentPrice: "",
  sharesOutstanding: "",
  netDebt: "",
  wacc: "",
  terminalGrowth: "",
  terminalFcfMultiple: "",
  peerPe: "",
  peerEvEbitda: "",
  peerPFcf: "",
  peerEvFcf: "",
});

/**
 * Purpose: Describe what `StockAssistantPage` does within the frontend flow.
 * Args/Params:
 * - None.
 * Returns:
 * - Varies by usage (UI element, transformed payload, or helper value).
 * Raises/Exceptions:
 * - Propagates runtime errors when invalid input/state is provided.
 * Examples:
 * - `StockAssistantPage()`
 */
export default function StockAssistantPage() {
  // Main chat page: manages settings, history, streaming state, and rendering.
  const [ticker, setTicker] = useState("NVDA");
  const [companyName, setCompanyName] = useState("NVIDIA");
  const [market, setMarket] = useState("US");
  const [horizonDays, setHorizonDays] = useState(180);
  const [riskTolerance, setRiskTolerance] = useState<RiskTolerance>("moderate");
  const [bypassWebSearch, setBypassWebSearch] = useState(true);
  const [useQueryDecomposition, setUseQueryDecomposition] = useState(false);
  const [usePrimarySourceIngestion, setUsePrimarySourceIngestion] = useState(false);
  const [useFinancialModelRebuild, setUseFinancialModelRebuild] = useState(false);
  const [useAdvancedFinancialEngine, setUseAdvancedFinancialEngine] = useState(false);
  const [useStructuredValuation, setUseStructuredValuation] = useState(false);
  const [financialInputMode, setFinancialInputMode] = useState<FinancialInputMode>("builder");
  const [financialModelInputJson, setFinancialModelInputJson] = useState("");
  const [advancedFinancialInputJson, setAdvancedFinancialInputJson] = useState("");
  const [valuationInputMode, setValuationInputMode] = useState<ValuationInputMode>("builder");
  const [valuationInputJson, setValuationInputJson] = useState("");
  const [valuationInput, setValuationInput] = useState<ValuationInputFields>(defaultValuationInput());
  const [forecastYears, setForecastYears] = useState(3);
  const [financialPeriodRows, setFinancialPeriodRows] = useState<FinancialPeriodRow[]>([
    newFinancialPeriodRow(),
    newFinancialPeriodRow(),
    newFinancialPeriodRow(),
  ]);
  const [prompt, setPrompt] = useState(
    "Should I consider a medium-term position based on current trend and sentiment?"
  );
  const [mcpRows, setMcpRows] = useState<MCPCallRow[]>([newMcpRow()]);
  const [a2aRows, setA2aRows] = useState<A2ACallRow[]>([newA2aRow()]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const [resolvedBackendUrl, setResolvedBackendUrl] = useState(BACKEND_URL);

  const backendStreamUrl = `${resolvedBackendUrl}/api/chat/stream`;
  const backendStreamUploadUrl = `${resolvedBackendUrl}/api/chat/stream/upload`;

  useEffect(() => {
    // Keep the latest streaming/final message in view as chat grows.
    chatScrollRef.current?.scrollTo({
      top: chatScrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, loading]);

  useEffect(() => {
    // Resolve backend URL dynamically for remote/browser access when env var is not set.
    if (process.env.NEXT_PUBLIC_BACKEND_URL) {
      setResolvedBackendUrl(process.env.NEXT_PUBLIC_BACKEND_URL);
      return;
    }
    if (typeof window !== "undefined") {
      const protocol = window.location.protocol === "https:" ? "https" : "http";
      setResolvedBackendUrl(`${protocol}://${window.location.hostname}:8000`);
    }
  }, []);

  /**
   * Purpose: Describe what `onSubmit` does within the frontend flow.
   * Args/Params:
   * - event: Value consumed by `onSubmit`.
   * Returns:
   * - Varies by usage (UI element, transformed payload, or helper value).
   * Raises/Exceptions:
   * - Propagates runtime errors when invalid input/state is provided.
   * Examples:
   * - `onSubmit(value)`
   */
  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    // Send one user turn to backend streaming endpoint and progressively render response.
    event.preventDefault();
    if (!prompt.trim() || loading) {
      return;
    }

    const userText = prompt.trim();
    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text: userText,
    };
    const assistantId = `a-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

    const historyTurns = [...messages, userMessage]
      .filter((message) => message.id !== "welcome")
      .slice(-12)
      .map((message) => ({ role: message.role, content: message.text }));

    let mcpCalls: Array<{ server: string; tool: string; arguments: object }> = [];
    let a2aCalls: Array<{ agent: string; task: string; context: object }> = [];
    let financialModelInput: object | undefined;
    let advancedFinancialInput: object | undefined;
    let valuationInputPayload: object | undefined;
    try {
      mcpCalls = buildMcpCalls(mcpRows);
      a2aCalls = buildA2aCalls(a2aRows);
      if (useFinancialModelRebuild) {
        if (financialInputMode === "json") {
          if (financialModelInputJson.trim()) {
            financialModelInput = JSON.parse(financialModelInputJson);
          }
        } else {
          const periods = financialPeriodRows
            .filter(
              (row) =>
                row.year.trim() ||
                row.revenue.trim() ||
                row.netIncome.trim() ||
                row.totalAssets.trim() ||
                row.totalLiabilities.trim() ||
                row.totalEquity.trim()
            )
            .map((row) => ({
              year: Number.parseInt(row.year, 10),
              revenue: Number.parseFloat(row.revenue),
              net_income: Number.parseFloat(row.netIncome),
              total_assets: Number.parseFloat(row.totalAssets),
              total_liabilities: Number.parseFloat(row.totalLiabilities),
              total_equity: Number.parseFloat(row.totalEquity),
              cash: row.cash.trim() ? Number.parseFloat(row.cash) : 0,
              operating_cash_flow: row.operatingCashFlow.trim()
                ? Number.parseFloat(row.operatingCashFlow)
                : 0,
              capex: row.capex.trim() ? Number.parseFloat(row.capex) : 0,
              debt: row.debt.trim() ? Number.parseFloat(row.debt) : 0,
            }));
          const invalidRow = periods.find(
            (period) =>
              !Number.isFinite(period.year) ||
              !Number.isFinite(period.revenue) ||
              !Number.isFinite(period.net_income) ||
              !Number.isFinite(period.total_assets) ||
              !Number.isFinite(period.total_liabilities) ||
              !Number.isFinite(period.total_equity) ||
              !Number.isFinite(period.cash) ||
              !Number.isFinite(period.operating_cash_flow) ||
              !Number.isFinite(period.capex) ||
              !Number.isFinite(period.debt)
          );
          if (invalidRow) {
            throw new Error(
              "Invalid financial model row values. Fill required numeric fields (year, revenue, net income, assets, liabilities, equity)."
            );
          }
          if (periods.length > 0) {
            financialModelInput = { periods, forecast_years: forecastYears };
          }
        }
      }
      if (useAdvancedFinancialEngine && advancedFinancialInputJson.trim()) {
        advancedFinancialInput = JSON.parse(advancedFinancialInputJson);
      }
      if (useStructuredValuation) {
        if (valuationInputMode === "json") {
          if (valuationInputJson.trim()) {
            valuationInputPayload = JSON.parse(valuationInputJson);
          }
        } else {
          const candidateEntries: Array<[string, string]> = [
            ["current_price", valuationInput.currentPrice],
            ["shares_outstanding", valuationInput.sharesOutstanding],
            ["net_debt", valuationInput.netDebt],
            ["wacc", valuationInput.wacc],
            ["terminal_growth", valuationInput.terminalGrowth],
            ["terminal_fcf_multiple", valuationInput.terminalFcfMultiple],
            ["peer_pe", valuationInput.peerPe],
            ["peer_ev_ebitda", valuationInput.peerEvEbitda],
            ["peer_p_fcf", valuationInput.peerPFcf],
            ["peer_ev_fcf", valuationInput.peerEvFcf],
          ];
          const candidatePayload: Record<string, number> = {};
          for (const [key, rawValue] of candidateEntries) {
            if (!rawValue.trim()) {
              continue;
            }
            const parsedValue = Number.parseFloat(rawValue);
            if (!Number.isFinite(parsedValue)) {
              throw new Error(`Invalid valuation input for ${key}.`);
            }
            candidatePayload[key] = parsedValue;
          }
          if (Object.keys(candidatePayload).length > 0) {
            valuationInputPayload = candidatePayload;
          }
        }
      }
    } catch (jsonError) {
      setError(
        jsonError instanceof Error
          ? `Invalid JSON input: ${jsonError.message}`
          : "Invalid JSON input"
      );
      return;
    }

    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantId, role: "assistant", text: "" },
    ]);
    setPrompt("");
    setError(null);
    setLoading(true);

    try {
      let response: Response;
      if (attachedFiles.length > 0) {
        const formData = new FormData();
        formData.append("ticker", ticker);
        formData.append("company_name", companyName || "");
        formData.append("market", market);
        formData.append("question", userText);
        formData.append("horizon_days", String(horizonDays));
        formData.append("risk_tolerance", riskTolerance);
        formData.append("bypass_web_search", String(bypassWebSearch));
        formData.append("use_query_decomposition", String(useQueryDecomposition));
        formData.append("use_primary_source_ingestion", String(usePrimarySourceIngestion));
        formData.append("use_financial_model_rebuild", String(useFinancialModelRebuild));
        formData.append("use_advanced_financial_engine", String(useAdvancedFinancialEngine));
        formData.append("use_structured_valuation", String(useStructuredValuation));
        if (financialModelInput) {
          formData.append("financial_model_input", JSON.stringify(financialModelInput));
        }
        if (advancedFinancialInput) {
          formData.append("advanced_financial_input", JSON.stringify(advancedFinancialInput));
        }
        if (valuationInputPayload) {
          formData.append("valuation_input", JSON.stringify(valuationInputPayload));
        }
        formData.append("chat_history", JSON.stringify(historyTurns));
        formData.append("mcp_calls", JSON.stringify(mcpCalls));
        formData.append("a2a_calls", JSON.stringify(a2aCalls));
        attachedFiles.forEach((file) => formData.append("files", file));

        response = await fetch(backendStreamUploadUrl, {
          method: "POST",
          body: formData,
        });
      } else {
        response = await fetch(backendStreamUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            ticker,
            company_name: companyName || undefined,
            market,
            question: userText,
            horizon_days: horizonDays,
            risk_tolerance: riskTolerance,
            bypass_web_search: bypassWebSearch,
            use_query_decomposition: useQueryDecomposition,
            use_primary_source_ingestion: usePrimarySourceIngestion,
            use_financial_model_rebuild: useFinancialModelRebuild,
            use_advanced_financial_engine: useAdvancedFinancialEngine,
            use_structured_valuation: useStructuredValuation,
            chat_history: historyTurns,
            mcp_calls: mcpCalls,
            a2a_calls: a2aCalls,
            financial_model_input: financialModelInput,
            advanced_financial_input: advancedFinancialInput,
            valuation_input: valuationInputPayload,
          }),
        });
      }

      if (!response.ok || !response.body) {
        const text = await response.text();
        throw new Error(`API ${response.status}: ${text}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const eventChunk of events) {
          const parsed = parseSseEvent(eventChunk);
          if (!parsed) {
            continue;
          }

          if (parsed.event === "chunk") {
            const content = parsed.data?.content;
            if (typeof content === "string" && content.length > 0) {
              setMessages((prev) =>
                prev.map((message) =>
                  message.id === assistantId
                    ? { ...message, text: message.text + content }
                    : message
                )
              );
            }
          }

          if (parsed.event === "meta") {
            const result = parsed.data as ResearchResponse;
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantId
                  ? { ...message, result, text: result.markdown || message.text }
                  : message
              )
            );
          }

          if (parsed.event === "error") {
            const message =
              typeof parsed.data?.message === "string"
                ? parsed.data.message
                : "Unknown stream error";
            throw new Error(message);
          }
        }
      }
      setAttachedFiles([]);
    } catch (submitError) {
      const message = toReadableRequestError(submitError, resolvedBackendUrl);
      setError(message);
      setMessages((prev) =>
        prev.map((entry) =>
          entry.id === assistantId
            ? { ...entry, text: `Research request failed: ${message}` }
            : entry
        )
      );
    } finally {
      setLoading(false);
    }
  };

  /**
   * Purpose: Describe what `onFileChange` does within the frontend flow.
   * Args/Params:
   * - event: Value consumed by `onFileChange`.
   * Returns:
   * - Varies by usage (UI element, transformed payload, or helper value).
   * Raises/Exceptions:
   * - Propagates runtime errors when invalid input/state is provided.
   * Examples:
   * - `onFileChange(value)`
   */
  const onFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    // Track selected files and include them in the next request payload.
    const selected = Array.from(event.target.files || []);
    const validationError = validateAttachedFiles(selected);
    if (validationError) {
      setError(validationError);
      setAttachedFiles(selected.slice(0, MAX_ATTACH_FILES));
      return;
    }

    setError(null);
    setAttachedFiles(selected);
  };

  /**
   * Purpose: Describe what `onResetChat` does within the frontend flow.
   * Args/Params:
   * - None.
   * Returns:
   * - Varies by usage (UI element, transformed payload, or helper value).
   * Raises/Exceptions:
   * - Propagates runtime errors when invalid input/state is provided.
   * Examples:
   * - `onResetChat()`
   */
  const onResetChat = () => {
    // Start a fresh conversation while preserving current sidebar settings.
    setMessages([WELCOME_MESSAGE]);
    setPrompt("");
    setAttachedFiles([]);
    setMcpRows([newMcpRow()]);
    setA2aRows([newA2aRow()]);
    setFinancialInputMode("builder");
    setFinancialModelInputJson("");
    setUseAdvancedFinancialEngine(false);
    setAdvancedFinancialInputJson("");
    setUseStructuredValuation(false);
    setValuationInputMode("builder");
    setValuationInputJson("");
    setValuationInput(defaultValuationInput());
    setForecastYears(3);
    setFinancialPeriodRows([newFinancialPeriodRow(), newFinancialPeriodRow(), newFinancialPeriodRow()]);
    setError(null);
  };

  /**
   * Purpose: Describe what `onDownloadLatestMarkdown` does within the frontend flow.
   * Args/Params:
   * - None.
   * Returns:
   * - Varies by usage (UI element, transformed payload, or helper value).
   * Raises/Exceptions:
   * - Propagates runtime errors when invalid input/state is provided.
   * Examples:
   * - `onDownloadLatestMarkdown()`
   */
  const onDownloadLatestMarkdown = () => {
    // Export latest assistant markdown response as a local .md file.
    const latestAssistant = [...messages]
      .reverse()
      .find((message) => message.role === "assistant" && message.text.trim().length > 0);
    if (!latestAssistant) {
      setError("No assistant output available to download.");
      return;
    }

    const date = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    const filename = `${ticker || "stock"}-research-${date}.md`;
    const blob = new Blob([latestAssistant.text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <Head>
        <title>Deep Research Stock Assistant</title>
      </Head>
      <main className="min-h-screen bg-[radial-gradient(circle_at_10%_20%,#0b223f_0,#0a1726_40%,#0f1117_100%)] text-slate-100">
        <div className="mx-auto grid min-h-screen max-w-7xl gap-4 p-4 lg:grid-cols-[320px_1fr] lg:p-6">
          <aside className="rounded-3xl border border-slate-700/60 bg-slate-900/75 p-4 lg:p-5">
            <p className="text-xs uppercase tracking-[0.2em] text-cyan-200/80">
              Assistant Settings
            </p>
            <h1 className="mt-2 text-xl font-semibold">Stock Research Chat</h1>
            <p className="mt-2 text-sm text-slate-300">
              Configure context for each research turn.
            </p>

            <div className="mt-5 space-y-3">
              <Field label="Ticker">
                <input
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  className={inputClass}
                  required
                />
              </Field>

              <Field label="Company Name">
                <input
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className={inputClass}
                />
              </Field>

              <Field label="Market">
                <input
                  value={market}
                  onChange={(e) => setMarket(e.target.value)}
                  className={inputClass}
                  required
                />
              </Field>

              <Field label="Horizon (days)">
                <input
                  type="number"
                  min={1}
                  max={1825}
                  value={horizonDays}
                  onChange={(e) => setHorizonDays(Number(e.target.value))}
                  className={inputClass}
                  required
                />
              </Field>

              <Field label="Risk Tolerance">
                <select
                  value={riskTolerance}
                  onChange={(e) => setRiskTolerance(e.target.value as RiskTolerance)}
                  className={inputClass}
                >
                  <option value="conservative">Conservative</option>
                  <option value="moderate">Moderate</option>
                  <option value="aggressive">Aggressive</option>
                </select>
              </Field>

              <label className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-950/40 px-3 py-2">
                <input
                  type="checkbox"
                  checked={bypassWebSearch}
                  onChange={(e) => setBypassWebSearch(e.target.checked)}
                />
                <span className="text-xs uppercase tracking-[0.12em] text-slate-300">
                  Bypass Web Search
                </span>
              </label>

              <label className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-950/40 px-3 py-2">
                <input
                  type="checkbox"
                  checked={useQueryDecomposition}
                  onChange={(e) => setUseQueryDecomposition(e.target.checked)}
                />
                <span className="text-xs uppercase tracking-[0.12em] text-slate-300">
                  Use Query Decomposition
                </span>
              </label>

              <label className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-950/40 px-3 py-2">
                <input
                  type="checkbox"
                  checked={useFinancialModelRebuild}
                  onChange={(e) => setUseFinancialModelRebuild(e.target.checked)}
                />
                <span className="text-xs uppercase tracking-[0.12em] text-slate-300">
                  Use Financial Model Rebuild
                </span>
              </label>

              {useFinancialModelRebuild ? (
                <>
                  <Field label="Financial Input Mode">
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setFinancialInputMode("builder")}
                        className={`rounded-lg border px-2 py-1 text-xs ${
                          financialInputMode === "builder"
                            ? "border-cyan-400 bg-cyan-400/20 text-cyan-100"
                            : "border-slate-500 bg-slate-800 text-slate-100 hover:bg-slate-700"
                        }`}
                      >
                        Form Builder
                      </button>
                      <button
                        type="button"
                        onClick={() => setFinancialInputMode("json")}
                        className={`rounded-lg border px-2 py-1 text-xs ${
                          financialInputMode === "json"
                            ? "border-cyan-400 bg-cyan-400/20 text-cyan-100"
                            : "border-slate-500 bg-slate-800 text-slate-100 hover:bg-slate-700"
                        }`}
                      >
                        Raw JSON
                      </button>
                    </div>
                  </Field>
                  {financialInputMode === "builder" ? (
                    <BuilderBlock
                      title="Financial Periods"
                      actionLabel="+ Add Period"
                      onAdd={() => setFinancialPeriodRows((prev) => [...prev, newFinancialPeriodRow()])}
                    >
                      <Field label="Forecast Years">
                        <input
                          type="number"
                          min={1}
                          max={5}
                          value={forecastYears}
                          onChange={(e) => setForecastYears(Number(e.target.value))}
                          className={inputClass}
                        />
                      </Field>
                      {financialPeriodRows.map((row) => (
                        <div key={row.id} className="rounded-xl border border-slate-700/70 p-2 space-y-2">
                          <div className="grid grid-cols-2 gap-2">
                            <input
                              value={row.year}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, year: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Year* (e.g. 2024)"
                            />
                            <input
                              value={row.revenue}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, revenue: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Revenue*"
                            />
                            <input
                              value={row.netIncome}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, netIncome: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Net Income*"
                            />
                            <input
                              value={row.totalAssets}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, totalAssets: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Total Assets*"
                            />
                            <input
                              value={row.totalLiabilities}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, totalLiabilities: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Total Liabilities*"
                            />
                            <input
                              value={row.totalEquity}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, totalEquity: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Total Equity*"
                            />
                            <input
                              value={row.cash}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, cash: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Cash"
                            />
                            <input
                              value={row.operatingCashFlow}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id
                                      ? { ...item, operatingCashFlow: e.target.value }
                                      : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Operating Cash Flow"
                            />
                            <input
                              value={row.capex}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, capex: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Capex"
                            />
                            <input
                              value={row.debt}
                              onChange={(e) =>
                                setFinancialPeriodRows((prev) =>
                                  prev.map((item) =>
                                    item.id === row.id ? { ...item, debt: e.target.value } : item
                                  )
                                )
                              }
                              className={inputClass}
                              placeholder="Debt"
                            />
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              setFinancialPeriodRows((prev) =>
                                prev.length === 1
                                  ? [newFinancialPeriodRow()]
                                  : prev.filter((item) => item.id !== row.id)
                              )
                            }
                            className="rounded-lg border border-slate-500 bg-slate-800 px-2 py-1 text-xs text-slate-100 hover:bg-slate-700"
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </BuilderBlock>
                  ) : (
                    <Field label="Financial Model JSON">
                      <textarea
                        value={financialModelInputJson}
                        onChange={(e) => setFinancialModelInputJson(e.target.value)}
                        className={`${inputClass} min-h-24`}
                        placeholder='{"periods":[{"year":2022,"revenue":1000,"net_income":120,"total_assets":2000,"total_liabilities":900,"total_equity":1100}],"forecast_years":3}'
                      />
                    </Field>
                  )}
                </>
              ) : null}

              <label className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-950/40 px-3 py-2">
                <input
                  type="checkbox"
                  checked={useAdvancedFinancialEngine}
                  onChange={(e) => setUseAdvancedFinancialEngine(e.target.checked)}
                />
                <span className="text-xs uppercase tracking-[0.12em] text-slate-300">
                  Use Advanced Financial Engine
                </span>
              </label>

              {useAdvancedFinancialEngine ? (
                <Field label="Advanced Financial Input JSON">
                  <textarea
                    value={advancedFinancialInputJson}
                    onChange={(e) => setAdvancedFinancialInputJson(e.target.value)}
                    className={`${inputClass} min-h-28`}
                    placeholder='{"initial_state":{"year":2024,"cash":300,"debt":500,"retained_earnings":1200,"share_capital":600,"ppe_net":900,"other_assets":400,"other_liabilities":300,"shares_outstanding":2500},"forecast":[{"year":2025,"volume":15,"price":100,"other_revenue":20,"gross_margin":0.6,"opex_ratio":0.3,"ar_days":45,"inventory_days":30,"ap_days":28,"capex_pct_revenue":0.08,"depreciation_pct_ppe":0.12,"new_borrowing":0,"debt_repayment":40,"interest_rate":0.04,"tax_rate":0.21,"dividends":0}]}'
                  />
                </Field>
              ) : null}

              <label className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-950/40 px-3 py-2">
                <input
                  type="checkbox"
                  checked={useStructuredValuation}
                  onChange={(e) => setUseStructuredValuation(e.target.checked)}
                />
                <span className="text-xs uppercase tracking-[0.12em] text-slate-300">
                  Use Structured Valuation (DCF + Comps)
                </span>
              </label>

              {useStructuredValuation ? (
                <>
                  <p className="rounded-xl border border-amber-600/50 bg-amber-900/20 px-3 py-2 text-xs text-amber-200">
                    Structured valuation works best with financial model input (historical periods).
                  </p>
                  <Field label="Valuation Input Mode">
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setValuationInputMode("builder")}
                        className={`rounded-lg border px-2 py-1 text-xs ${
                          valuationInputMode === "builder"
                            ? "border-cyan-400 bg-cyan-400/20 text-cyan-100"
                            : "border-slate-500 bg-slate-800 text-slate-100 hover:bg-slate-700"
                        }`}
                      >
                        Form Builder
                      </button>
                      <button
                        type="button"
                        onClick={() => setValuationInputMode("json")}
                        className={`rounded-lg border px-2 py-1 text-xs ${
                          valuationInputMode === "json"
                            ? "border-cyan-400 bg-cyan-400/20 text-cyan-100"
                            : "border-slate-500 bg-slate-800 text-slate-100 hover:bg-slate-700"
                        }`}
                      >
                        Raw JSON
                      </button>
                    </div>
                  </Field>
                  {valuationInputMode === "builder" ? (
                    <BuilderBlock title="Valuation Assumptions">
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          value={valuationInput.currentPrice}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, currentPrice: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Current Price"
                        />
                        <input
                          value={valuationInput.sharesOutstanding}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, sharesOutstanding: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Shares Outstanding"
                        />
                        <input
                          value={valuationInput.netDebt}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, netDebt: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Net Debt"
                        />
                        <input
                          value={valuationInput.wacc}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, wacc: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="WACC (e.g. 0.10)"
                        />
                        <input
                          value={valuationInput.terminalGrowth}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, terminalGrowth: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Terminal Growth (e.g. 0.03)"
                        />
                        <input
                          value={valuationInput.terminalFcfMultiple}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, terminalFcfMultiple: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Terminal FCF Multiple"
                        />
                        <input
                          value={valuationInput.peerPe}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, peerPe: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Peer P/E"
                        />
                        <input
                          value={valuationInput.peerEvEbitda}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, peerEvEbitda: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Peer EV/EBITDA"
                        />
                        <input
                          value={valuationInput.peerPFcf}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, peerPFcf: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Peer P/FCF"
                        />
                        <input
                          value={valuationInput.peerEvFcf}
                          onChange={(e) =>
                            setValuationInput((prev) => ({ ...prev, peerEvFcf: e.target.value }))
                          }
                          className={inputClass}
                          placeholder="Peer EV/FCF"
                        />
                      </div>
                    </BuilderBlock>
                  ) : (
                    <Field label="Valuation JSON">
                      <textarea
                        value={valuationInputJson}
                        onChange={(e) => setValuationInputJson(e.target.value)}
                        className={`${inputClass} min-h-24`}
                        placeholder='{"current_price":120,"shares_outstanding":2500,"net_debt":2000,"wacc":0.1,"terminal_growth":0.03,"terminal_fcf_multiple":18,"peer_pe":24,"peer_ev_ebitda":14,"peer_p_fcf":18,"peer_ev_fcf":20}'
                      />
                    </Field>
                  )}
                </>
              ) : null}

              <label className="flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-950/40 px-3 py-2">
                <input
                  type="checkbox"
                  checked={usePrimarySourceIngestion}
                  onChange={(e) => setUsePrimarySourceIngestion(e.target.checked)}
                />
                <span className="text-xs uppercase tracking-[0.12em] text-slate-300">
                  Use Primary Source Ingestion (SEC/EDGAR)
                </span>
              </label>

              <BuilderBlock
                title="MCP Calls"
                actionLabel="+ Add MCP Call"
                onAdd={() => setMcpRows((prev) => [...prev, newMcpRow()])}
              >
                {mcpRows.map((row) => (
                  <div key={row.id} className="rounded-xl border border-slate-700/70 p-2 space-y-2">
                    <input
                      value={row.server}
                      onChange={(e) =>
                        setMcpRows((prev) =>
                          prev.map((item) =>
                            item.id === row.id ? { ...item, server: e.target.value } : item
                          )
                        )
                      }
                      className={inputClass}
                      placeholder="server (e.g. market-mcp)"
                    />
                    <input
                      value={row.tool}
                      onChange={(e) =>
                        setMcpRows((prev) =>
                          prev.map((item) =>
                            item.id === row.id ? { ...item, tool: e.target.value } : item
                          )
                        )
                      }
                      className={inputClass}
                      placeholder="tool (e.g. get_earnings_calendar)"
                    />
                    <textarea
                      value={row.argumentsJson}
                      onChange={(e) =>
                        setMcpRows((prev) =>
                          prev.map((item) =>
                            item.id === row.id ? { ...item, argumentsJson: e.target.value } : item
                          )
                        )
                      }
                      className={`${inputClass} min-h-20`}
                      placeholder='arguments JSON (e.g. {"ticker":"NVDA"})'
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setMcpRows((prev) =>
                          prev.length === 1 ? [newMcpRow()] : prev.filter((item) => item.id !== row.id)
                        )
                      }
                      className="rounded-lg border border-slate-500 bg-slate-800 px-2 py-1 text-xs text-slate-100 hover:bg-slate-700"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </BuilderBlock>

              <BuilderBlock
                title="A2A Calls"
                actionLabel="+ Add A2A Call"
                onAdd={() => setA2aRows((prev) => [...prev, newA2aRow()])}
              >
                {a2aRows.map((row) => (
                  <div key={row.id} className="rounded-xl border border-slate-700/70 p-2 space-y-2">
                    <input
                      value={row.agent}
                      onChange={(e) =>
                        setA2aRows((prev) =>
                          prev.map((item) =>
                            item.id === row.id ? { ...item, agent: e.target.value } : item
                          )
                        )
                      }
                      className={inputClass}
                      placeholder="agent (e.g. risk-agent)"
                    />
                    <textarea
                      value={row.task}
                      onChange={(e) =>
                        setA2aRows((prev) =>
                          prev.map((item) =>
                            item.id === row.id ? { ...item, task: e.target.value } : item
                          )
                        )
                      }
                      className={`${inputClass} min-h-20`}
                      placeholder="task for remote agent"
                    />
                    <textarea
                      value={row.contextJson}
                      onChange={(e) =>
                        setA2aRows((prev) =>
                          prev.map((item) =>
                            item.id === row.id ? { ...item, contextJson: e.target.value } : item
                          )
                        )
                      }
                      className={`${inputClass} min-h-20`}
                      placeholder='context JSON (e.g. {"ticker":"NVDA"})'
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setA2aRows((prev) =>
                          prev.length === 1 ? [newA2aRow()] : prev.filter((item) => item.id !== row.id)
                        )
                      }
                      className="rounded-lg border border-slate-500 bg-slate-800 px-2 py-1 text-xs text-slate-100 hover:bg-slate-700"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </BuilderBlock>
            </div>
          </aside>

          <section className="flex min-h-[80vh] flex-col rounded-3xl border border-slate-700/60 bg-slate-900/75">
            <header className="border-b border-slate-700/60 px-4 py-4 lg:px-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-sm text-slate-300">
                  Streaming chat with markdown-formatted deep-research output.
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={onDownloadLatestMarkdown}
                    className="rounded-lg border border-slate-500 bg-slate-800 px-3 py-1 text-xs text-slate-100 hover:bg-slate-700"
                  >
                    Download Markdown
                  </button>
                  <button
                    type="button"
                    onClick={onResetChat}
                    className="rounded-lg border border-slate-500 bg-slate-800 px-3 py-1 text-xs text-slate-100 hover:bg-slate-700"
                  >
                    New Chat
                  </button>
                </div>
              </div>
            </header>

            <div ref={chatScrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4 lg:px-6">
              {messages.map((message) => (
                <article
                  key={message.id}
                  className={`max-w-4xl rounded-2xl border p-4 ${
                    message.role === "user"
                      ? "ml-auto border-cyan-400/40 bg-cyan-500/10"
                      : "mr-auto border-slate-700/70 bg-slate-950/60"
                  }`}
                >
                  <p className="mb-2 text-xs uppercase tracking-[0.12em] text-slate-400">
                    {message.role === "user" ? "You" : "Assistant"}
                  </p>

                  {message.role === "assistant" ? (
                    <MarkdownRenderer markdown={message.text || "..."} />
                  ) : (
                    <p className="whitespace-pre-wrap text-sm leading-6 text-slate-100">
                      {message.text}
                    </p>
                  )}

                  {message.result ? (
                    <div className="mt-4 space-y-3 border-t border-slate-700/60 pt-4">
                      <section>
                        <h3 className="text-sm font-semibold">Signals</h3>
                        <div className="mt-2 grid gap-2 md:grid-cols-3">
                          {message.result.signals.map((signal) => (
                            <div
                              key={`${message.id}-${signal.label}`}
                              className="rounded-xl border border-slate-700/70 bg-slate-950/70 p-2"
                            >
                              <p className="text-xs text-slate-400">{signal.label}</p>
                              <p className="text-lg font-semibold">{signal.value}</p>
                              <p className="text-xs text-slate-300">{signal.rationale}</p>
                            </div>
                          ))}
                        </div>
                      </section>

                      {message.result.valuation ? (
                        <section>
                          <h3 className="text-sm font-semibold">Structured Valuation</h3>
                          <div className="mt-2 grid gap-2 md:grid-cols-3">
                            <div className="rounded-xl border border-slate-700/70 bg-slate-950/70 p-2">
                              <p className="text-xs text-slate-400">Blended Target Price</p>
                              <p className="text-lg font-semibold">
                                {message.result.valuation.blended_target_price.toFixed(2)}
                              </p>
                              <p className="text-xs text-slate-300">
                                {message.result.valuation.recommendation} (
                                {message.result.valuation.confidence_pct}%)
                              </p>
                            </div>
                            <div className="rounded-xl border border-slate-700/70 bg-slate-950/70 p-2">
                              <p className="text-xs text-slate-400">DCF Price/Share</p>
                              <p className="text-lg font-semibold">
                                {message.result.valuation.dcf_price_per_share.toFixed(2)}
                              </p>
                              <p className="text-xs text-slate-300">
                                Equity Value {message.result.valuation.dcf_equity_value.toFixed(2)}
                              </p>
                            </div>
                            <div className="rounded-xl border border-slate-700/70 bg-slate-950/70 p-2">
                              <p className="text-xs text-slate-400">Comps Price/Share</p>
                              <p className="text-lg font-semibold">
                                {message.result.valuation.comps_price_per_share.toFixed(2)}
                              </p>
                              <p className="text-xs text-slate-300">
                                Upside {message.result.valuation.upside_pct.toFixed(2)}%
                              </p>
                            </div>
                            <div className="rounded-xl border border-slate-700/70 bg-slate-950/70 p-2 md:col-span-3">
                              <p className="text-xs text-slate-400">Scenario-Weighted Target</p>
                              <p className="text-lg font-semibold">
                                {(message.result.valuation.scenario_weighted_target_price ?? 0).toFixed(2)}
                              </p>
                              <p className="text-xs text-slate-300">
                                Bull/Base/Bear: {(message.result.valuation.bull_target_price ?? 0).toFixed(2)}/
                                {(message.result.valuation.base_target_price ?? 0).toFixed(2)}/
                                {(message.result.valuation.bear_target_price ?? 0).toFixed(2)} (weights{" "}
                                {(message.result.valuation.scenario_bull_weight ?? 0).toFixed(2)}/
                                {(message.result.valuation.scenario_base_weight ?? 0).toFixed(2)}/
                                {(message.result.valuation.scenario_bear_weight ?? 0).toFixed(2)})
                              </p>
                            </div>
                          </div>
                          {message.result.valuation.sensitivity_grid.length > 0 ? (
                            <div className="mt-3">
                              <p className="text-xs uppercase tracking-[0.12em] text-slate-300">
                                Sensitivity Grid (WACC x Terminal Growth)
                              </p>
                              <div className="mt-2 overflow-x-auto rounded-xl border border-slate-700/70 bg-slate-950/70">
                                <table className="min-w-full text-left text-xs">
                                  <thead className="bg-slate-900/80 text-slate-300">
                                    <tr>
                                      <th className="px-3 py-2">WACC</th>
                                      <th className="px-3 py-2">Terminal Growth</th>
                                      <th className="px-3 py-2">Implied Price</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {message.result.valuation.sensitivity_grid.map((row, index) => (
                                      <tr
                                        key={`${message.id}-valuation-${index}`}
                                        className="border-t border-slate-800/80"
                                      >
                                        <td className="px-3 py-2">{(row.wacc * 100).toFixed(2)}%</td>
                                        <td className="px-3 py-2">
                                          {(row.terminal_growth * 100).toFixed(2)}%
                                        </td>
                                        <td className="px-3 py-2">{row.implied_price.toFixed(2)}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          ) : null}
                        </section>
                      ) : null}

                      <section>
                        <h3 className="text-sm font-semibold">Sources</h3>
                        <ul className="mt-2 space-y-2">
                          {message.result.sources.slice(0, 8).map((source) => (
                            <li
                              key={`${message.id}-${source.url}`}
                              className="rounded-xl border border-slate-700/70 bg-slate-950/70 p-2"
                            >
                              <a
                                href={source.url}
                                target="_blank"
                                rel="noreferrer"
                                className="text-cyan-300 hover:text-cyan-200"
                              >
                                {source.title}
                              </a>
                              <p className="text-xs text-slate-400">{source.source_type}</p>
                              <p className="text-sm text-slate-300">{source.snippet}</p>
                            </li>
                          ))}
                        </ul>
                      </section>
                    </div>
                  ) : null}
                </article>
              ))}

              {loading ? (
                <article className="mr-auto max-w-4xl rounded-2xl border border-slate-700/70 bg-slate-950/60 p-4">
                  <p className="mb-2 text-xs uppercase tracking-[0.12em] text-slate-400">
                    Assistant
                  </p>
                  <p className="text-sm text-slate-300">Running deep research...</p>
                </article>
              ) : null}
            </div>

            <footer className="border-t border-slate-700/60 p-4 lg:p-6">
              <form onSubmit={onSubmit} className="space-y-3">
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className={`${inputClass} min-h-28`}
                  placeholder="Ask about a stock trend, social sentiment, or recommendation..."
                  required
                />

                <div className="flex items-center justify-between gap-3">
                  {error ? (
                    <p className="text-sm text-rose-300">{error}</p>
                  ) : (
                    <p className="text-xs text-slate-400">Stream: {backendStreamUrl}</p>
                  )}
                  <button
                    type="submit"
                    disabled={loading}
                    className="rounded-xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:bg-slate-600 disabled:text-slate-300"
                  >
                    {loading ? "Researching..." : "Send"}
                  </button>
                </div>

                <div className="rounded-xl border border-slate-700/70 bg-slate-950/40 p-3">
                  <label className="mb-2 block text-xs uppercase tracking-[0.12em] text-slate-300">
                    Attach files (pdf/txt/md/csv)
                  </label>
                  <input
                    type="file"
                    multiple
                    accept=".pdf,.txt,.md,.csv"
                    onChange={onFileChange}
                    className="block w-full text-xs text-slate-300 file:mr-3 file:rounded-lg file:border file:border-slate-500 file:bg-slate-800 file:px-3 file:py-1 file:text-xs file:text-slate-100"
                  />
                  {attachedFiles.length > 0 ? (
                    <p className="mt-2 text-xs text-slate-400">
                      Attached: {attachedFiles.map((file) => file.name).join(", ")}
                    </p>
                  ) : (
                    <p className="mt-2 text-xs text-slate-500">
                      Up to {MAX_ATTACH_FILES} files, {Math.floor(MAX_ATTACH_BYTES / (1024 * 1024))}
                      MB each. Selected files are added as research context.
                    </p>
                  )}
                </div>
              </form>
            </footer>
          </section>
        </div>
      </main>
    </>
  );
}

/**
 * Purpose: Render a labeled form control wrapper used in the settings sidebar.
 * Args/Params:
 * - label: Display label shown above the field content.
 * - children: Input/control node rendered under the label.
 * Returns:
 * - React.ReactNode label wrapper with provided content.
 * Raises/Exceptions:
 * - None directly; React rendering errors propagate if invalid children are passed.
 * Examples:
 * - `Field({ label: "Ticker", children: <input /> })`
 */
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  // Reusable label wrapper for sidebar form controls.
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-[0.12em] text-slate-300">
        {label}
      </span>
      {children}
    </label>
  );
}

/**
 * Purpose: Render a bordered builder section with optional add-action button.
 * Args/Params:
 * - title: Section header text.
 * - actionLabel: Optional button caption for append actions.
 * - onAdd: Optional callback invoked when action button is clicked.
 * - children: Nested builder controls rendered inside the block.
 * Returns:
 * - React.ReactNode for grouped builder UI controls.
 * Raises/Exceptions:
 * - None directly; callback/runtime errors from `onAdd` propagate.
 * Examples:
 * - `BuilderBlock({ title: "MCP Calls", actionLabel: "+ Add", onAdd, children })`
 */
function BuilderBlock({
  title,
  actionLabel,
  onAdd,
  children,
}: {
  title: string;
  actionLabel?: string;
  onAdd?: () => void;
  children: React.ReactNode;
}) {
  // Builder section for dynamic or static grouped input controls.
  return (
    <div className="rounded-xl border border-slate-700/60 p-2">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.12em] text-slate-300">{title}</p>
        {actionLabel && onAdd ? (
          <button
            type="button"
            onClick={onAdd}
            className="rounded-lg border border-slate-500 bg-slate-800 px-2 py-1 text-xs text-slate-100 hover:bg-slate-700"
          >
            {actionLabel}
          </button>
        ) : null}
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

/**
 * Purpose: Describe what `MarkdownRenderer` does within the frontend flow.
 * Args/Params:
 * - destructured_param: Value consumed by `MarkdownRenderer`.
 * Returns:
 * - Varies by usage (UI element, transformed payload, or helper value).
 * Raises/Exceptions:
 * - Propagates runtime errors when invalid input/state is provided.
 * Examples:
 * - `MarkdownRenderer(value)`
 */
function MarkdownRenderer({ markdown }: { markdown: string }) {
  // Lightweight markdown renderer for headings, lists, blockquotes, and paragraphs.
  const lines = markdown.split("\n");
  const blocks: React.ReactNode[] = [];
  let listBuffer: string[] = [];

  /**
   * Purpose: Describe what `flushList` does within the frontend flow.
   * Args/Params:
   * - None.
   * Returns:
   * - Varies by usage (UI element, transformed payload, or helper value).
   * Raises/Exceptions:
   * - Propagates runtime errors when invalid input/state is provided.
   * Examples:
   * - `flushList()`
   */
  const flushList = () => {
    // Convert buffered list lines into a rendered <ul> block.
    if (!listBuffer.length) {
      return;
    }
    blocks.push(
      <ul key={`list-${blocks.length}`} className="mb-3 list-disc space-y-1 pl-6 text-sm text-slate-200">
        {listBuffer.map((item, index) => (
          <li key={`item-${index}`}>{item}</li>
        ))}
      </ul>
    );
    listBuffer = [];
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();

    if (!trimmed) {
      flushList();
      blocks.push(<div key={`sp-${index}`} className="h-2" />);
      return;
    }

    if (trimmed.startsWith("- ")) {
      listBuffer.push(trimmed.slice(2));
      return;
    }

    flushList();

    if (trimmed.startsWith("### ")) {
      blocks.push(
        <h4 key={`h3-${index}`} className="mb-2 mt-3 text-base font-semibold text-cyan-200">
          {trimmed.slice(4)}
        </h4>
      );
      return;
    }

    if (trimmed.startsWith("## ")) {
      blocks.push(
        <h3 key={`h2-${index}`} className="mb-2 mt-3 text-lg font-semibold text-cyan-100">
          {trimmed.slice(3)}
        </h3>
      );
      return;
    }

    if (trimmed.startsWith("# ")) {
      blocks.push(
        <h2 key={`h1-${index}`} className="mb-2 mt-3 text-xl font-semibold text-white">
          {trimmed.slice(2)}
        </h2>
      );
      return;
    }

    if (trimmed.startsWith("> ")) {
      blocks.push(
        <blockquote
          key={`q-${index}`}
          className="mb-2 border-l-2 border-slate-500 pl-3 text-sm italic text-slate-300"
        >
          {trimmed.slice(2)}
        </blockquote>
      );
      return;
    }

    blocks.push(
      <p key={`p-${index}`} className="mb-2 whitespace-pre-wrap text-sm leading-6 text-slate-100">
        {trimmed}
      </p>
    );
  });

  flushList();

  return <div>{blocks.map((block, idx) => <Fragment key={`b-${idx}`}>{block}</Fragment>)}</div>;
}

const inputClass =
  "w-full rounded-xl border border-slate-600 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-cyan-400";
