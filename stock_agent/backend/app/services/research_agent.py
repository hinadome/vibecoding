from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator, List, Optional

from app.models import (
    ResearchRequest,
    ResearchResponse,
    Signal,
    Source,
    ValuationSensitivityPoint,
    ValuationSummary,
)
from app.services.a2a_client import A2AClient
from app.services.advanced_financial_model import AdvancedFinancialModelEngine
from app.services.dev_log_sink import append_ab_metric
from app.services.financial_model import FinancialModelRebuilder, FinancialModelResult
from app.services.market_analyzer import MarketAnalyzer
from app.services.mcp_client import MCPClient
from app.services.openai_client import OpenAICompatibleClient
from app.services.scenario_analyzer import ScenarioResult, ScenarioAnalyzer
from app.services.sec_ingestion import SecEdgarIngestionService
from app.services.valuation_engine import StructuredValuationEngine, ValuationResult
from app.services.vector_store import VectorRetriever
from app.services.web_search import WebSearcher


SYSTEM_PROMPT_FILE = Path(__file__).resolve().parents[2] / "system_prompt.md"
DEFAULT_SYSTEM_PROMPT = """You are a senior buy-side equity research analyst.
Return only markdown.
Use the exact headings below in order:
1. Executive Summary
2. Market and Company Trend Analysis
3. Social Sentiment Analysis
4. Risks and Catalysts
5. Recommendation
6. Sources
Recommendation should be one of: Buy, Hold, Sell.
Include confidence (0-100%) and justify with data points from sources.
"""

logger = logging.getLogger("uvicorn.error")


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    """
    Purpose: Load system prompt from markdown file with fallback to default prompt.
    Args/Params:
    - None.
    Returns:
    - `str`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `load_system_prompt()`
    """
    try:
        content = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
        if content:
            return content
        logger.warning("System prompt file is empty, using default prompt: %s", SYSTEM_PROMPT_FILE)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read system prompt file=%s error=%s", SYSTEM_PROMPT_FILE, str(exc))
    return DEFAULT_SYSTEM_PROMPT


@dataclass
class ResearchContext:
    company: str
    signals: List[Signal]
    sources: List[Source]
    social_sources: List[Source]
    external_contexts: List[str]
    decomposition_blocks: List[str]
    scenario_result: Optional[ScenarioResult] = None
    financial_model_result: Optional[FinancialModelResult] = None
    valuation_result: Optional[ValuationResult] = None


class DeepResearchAgent:
    def __init__(
        self,
        web_searcher: WebSearcher,
        vector_retriever: VectorRetriever,
        llm_client: OpenAICompatibleClient,
        mcp_client: MCPClient,
        a2a_client: A2AClient,
        sec_ingestor: SecEdgarIngestionService,
    ) -> None:
        """
        Purpose: Compose retrieval, analysis, and generation services into one agent.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `web_searcher` (WebSearcher): Input parameter used by this function.
        - `vector_retriever` (VectorRetriever): Input parameter used by this function.
        - `llm_client` (OpenAICompatibleClient): Input parameter used by this function.
        - `mcp_client` (MCPClient): Input parameter used by this function.
        - `a2a_client` (A2AClient): Input parameter used by this function.
        - `sec_ingestor` (SecEdgarIngestionService): Input parameter used by this function.
        Returns:
        - `None`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `__init__(web_searcher=..., vector_retriever=..., llm_client=..., mcp_client=...)`
        """
        self.web_searcher = web_searcher
        self.vector_retriever = vector_retriever
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.a2a_client = a2a_client
        self.sec_ingestor = sec_ingestor
        self.analyzer = MarketAnalyzer()
        self.scenario_analyzer = ScenarioAnalyzer()
        self.financial_model_rebuilder = FinancialModelRebuilder()
        self.advanced_financial_engine = AdvancedFinancialModelEngine()
        self.valuation_engine = StructuredValuationEngine()

    async def run(self, req: ResearchRequest) -> ResearchResponse:
        """
        Purpose: Execute full non-streaming pipeline and return final response model.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `ResearchResponse`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `run(req=...)`
        """
        context = await self.prepare_context(req)
        markdown = await self.generate_markdown(req, context)
        return self.build_response(req, context, markdown)

    async def prepare_context(self, req: ResearchRequest) -> ResearchContext:
        """
        Purpose: Gather web/vector evidence and compute analysis signals for the request.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `ResearchContext`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `prepare_context(req=...)`
        """
        started = time.perf_counter()
        company = req.company_name or req.ticker.upper()
        research_queries = self._build_queries(req)

        all_sources: List[Source] = []
        social_sources: List[Source] = []
        decomposition_blocks: List[str] = []
        vector_sources: List[Source] = []
        financial_model_result: Optional[FinancialModelResult] = None
        valuation_result: Optional[ValuationResult] = None
        decomposition_source_count = 0
        web_source_count = 0
        sec_source_count = 0
        attachment_points = 0
        web_points = 0
        sec_points = 0
        external_points = 0
        attachment_ms = 0
        web_ms = 0
        sec_ms = 0
        decomposition_ms = 0
        external_ms = 0
        vector_ms = 0

        attachment_started = time.perf_counter()
        attachment_points = await self._ingest_attachments_to_vector_db(req)
        attachment_ms = int((time.perf_counter() - attachment_started) * 1000)

        if req.use_primary_source_ingestion:
            sec_started = time.perf_counter()
            sec_sources = await self.sec_ingestor.search_primary_sources(
                ticker=req.ticker,
                company_name=req.company_name,
            )
            sec_source_count = len(sec_sources)
            if sec_sources:
                all_sources.extend(sec_sources)
                all_sources = self._dedupe_sources(all_sources)
                sec_points = await self._ingest_sources_to_vector_db(req, sec_sources)
            sec_ms = int((time.perf_counter() - sec_started) * 1000)
            logger.info(
                "Primary source ingestion completed ticker=%s sources=%d points=%d elapsed_ms=%d",
                req.ticker.upper(),
                sec_source_count,
                sec_points,
                sec_ms,
            )

        if not req.bypass_web_search:
            web_started = time.perf_counter()
            logger.info(
                "Web search enabled for ticker=%s. Executing %d market and %d social queries.",
                req.ticker.upper(),
                len(research_queries["market"]),
                len(research_queries["social"]),
            )
            for query in research_queries["market"]:
                all_sources.extend(await self.web_searcher.search(query, limit=5))

            for query in research_queries["social"]:
                result = await self.web_searcher.search(query, limit=5)
                social_sources.extend(result)
                all_sources.extend(result)
            logger.info(
                "Web search completed for ticker=%s. Retrieved sources=%d social_sources=%d.",
                req.ticker.upper(),
                len(all_sources),
                len(social_sources),
            )
            all_sources = self._dedupe_sources(all_sources)
            social_sources = self._dedupe_sources(social_sources)
            web_source_count = len(all_sources)
            web_points = await self._ingest_sources_to_vector_db(req, all_sources)
            if req.use_query_decomposition:
                decomposition_started = time.perf_counter()
                decomp_sources, decomposition_blocks = await self._run_query_decomposition(req)
                decomposition_ms = int((time.perf_counter() - decomposition_started) * 1000)
                if decomp_sources:
                    decomposition_source_count = len(decomp_sources)
                    all_sources.extend(decomp_sources)
                    all_sources = self._dedupe_sources(all_sources)
                    web_points += await self._ingest_sources_to_vector_db(req, decomp_sources)
            web_ms = int((time.perf_counter() - web_started) * 1000)
        else:
            logger.info("Web search bypassed for ticker=%s by request flag.", req.ticker.upper())

        external_started = time.perf_counter()
        external_contexts = await self._collect_external_context(req)
        external_points = await self._ingest_external_contexts_to_vector_db(req, external_contexts)
        external_ms = int((time.perf_counter() - external_started) * 1000)

        try:
            vector_started = time.perf_counter()
            embedding = await self.llm_client.embed(
                f"{req.ticker} {req.company_name or ''} {req.question or ''}".strip()
            )
            vector_sources = await self.vector_retriever.search(embedding, limit=4)
            all_sources.extend(vector_sources)
            vector_ms = int((time.perf_counter() - vector_started) * 1000)
            if req.bypass_web_search and logger.isEnabledFor(logging.INFO):
                logger.info(
                    "Context built without web search ticker=%s vector_sources=%d",
                    req.ticker.upper(),
                    len(vector_sources),
                )
        except Exception as exc:
            # Keep research flow alive even when embedding provider auth/config fails.
            logger.warning(
                "Embedding/vector retrieval skipped due to provider/config error for ticker=%s error=%s",
                req.ticker.upper(),
                str(exc),
            )
            pass

        all_sources = self._dedupe_sources(all_sources)
        social_sources = self._dedupe_sources(social_sources)

        signals = [
            self.analyzer.evaluate_market_sentiment(all_sources),
            self.analyzer.evaluate_social_sentiment(social_sources),
            self.analyzer.evaluate_source_strength(all_sources),
        ]
        scenario_result = self.scenario_analyzer.evaluate(
            risk_tolerance=req.risk_tolerance,
            signals=signals,
            sources=all_sources,
        )
        signals.append(
            Signal(
                label="Scenario weighted score",
                value=round(scenario_result.weighted_score, 3),
                rationale=(
                    f"{scenario_result.recommendation} with {scenario_result.confidence_pct}% "
                    f"confidence from bull/base/bear weighted analysis."
                ),
            )
        )
        if req.use_financial_model_rebuild:
            financial_model_result = self._run_financial_model(req)
            signals.append(
                Signal(
                    label="Financial model weighted score",
                    value=round(financial_model_result.weighted_score, 3),
                    rationale=(
                        f"{financial_model_result.recommendation} with "
                        f"{financial_model_result.confidence_pct}% confidence from 3-statement forecast."
                    ),
                )
            )
        if req.use_structured_valuation:
            valuation_model_input = financial_model_result
            if valuation_model_input is None:
                if req.financial_model_input or req.advanced_financial_input:
                    valuation_model_input = self._run_financial_model(req)
                    financial_model_result = valuation_model_input
                else:
                    valuation_model_input = FinancialModelResult(
                        is_valid=False,
                        issues=["Structured valuation enabled but no financial_model_input provided."],
                        historical_summary="No financial input supplied.",
                        base_case=[],
                        bull_case=[],
                        bear_case=[],
                        weighted_score=0.0,
                        recommendation="Hold",
                        confidence_pct=35,
                    )

            valuation_result = self.valuation_engine.evaluate(
                model_result=valuation_model_input,
                valuation_input=req.valuation_input,
                risk_tolerance=req.risk_tolerance,
            )
            signals.append(
                Signal(
                    label="Structured valuation upside (%)",
                    value=round(valuation_result.upside_pct, 2),
                    rationale=(
                        f"{valuation_result.recommendation} with blended target "
                        f"{valuation_result.blended_target_price:.2f}."
                    ),
                )
            )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "AB_METRIC context_build ticker=%s decomposition=%s bypass_web_search=%s primary_source_ingestion=%s advanced_financial_engine=%s structured_valuation=%s sources_total=%d sec_sources=%d web_sources=%d social_sources=%d decomposition_sources=%d vector_sources=%d external_contexts=%d points_attachment=%d points_sec=%d points_web=%d points_external=%d latency_total_ms=%d latency_attachment_ms=%d latency_sec_ms=%d latency_web_ms=%d latency_decomposition_ms=%d latency_external_ms=%d latency_vector_ms=%d",
            req.ticker.upper(),
            req.use_query_decomposition,
            req.bypass_web_search,
            req.use_primary_source_ingestion,
            req.use_advanced_financial_engine,
            req.use_structured_valuation,
            len(all_sources),
            sec_source_count,
            web_source_count,
            len(social_sources),
            decomposition_source_count,
            len(vector_sources),
            len(external_contexts),
            attachment_points,
            sec_points,
            web_points,
            external_points,
            elapsed_ms,
            attachment_ms,
            sec_ms,
            web_ms,
            decomposition_ms,
            external_ms,
            vector_ms,
        )
        append_ab_metric(
            app_env=self.llm_client.settings.app_env,
            event="context_build",
            payload={
                "ticker": req.ticker.upper(),
                "decomposition": req.use_query_decomposition,
                "bypass_web_search": req.bypass_web_search,
                "primary_source_ingestion": req.use_primary_source_ingestion,
                "advanced_financial_engine": req.use_advanced_financial_engine,
                "structured_valuation": req.use_structured_valuation,
                "sources_total": len(all_sources),
                "sec_sources": sec_source_count,
                "web_sources": web_source_count,
                "social_sources": len(social_sources),
                "decomposition_sources": decomposition_source_count,
                "vector_sources": len(vector_sources),
                "external_contexts": len(external_contexts),
                "points_attachment": attachment_points,
                "points_sec": sec_points,
                "points_web": web_points,
                "points_external": external_points,
                "latency_total_ms": elapsed_ms,
                "latency_attachment_ms": attachment_ms,
                "latency_sec_ms": sec_ms,
                "latency_web_ms": web_ms,
                "latency_decomposition_ms": decomposition_ms,
                "latency_external_ms": external_ms,
                "latency_vector_ms": vector_ms,
            },
        )

        return ResearchContext(
            company=company,
            signals=signals,
            sources=all_sources,
            social_sources=social_sources,
            external_contexts=external_contexts,
            decomposition_blocks=decomposition_blocks,
            scenario_result=scenario_result,
            financial_model_result=financial_model_result,
            valuation_result=valuation_result,
        )

    async def generate_markdown(self, req: ResearchRequest, context: ResearchContext) -> str:
        """
        Purpose: Generate final markdown with LLM, or return deterministic fallback text.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `context` (ResearchContext): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `generate_markdown(req=..., context=...)`
        """
        user_prompt = self._build_user_prompt(req, context)
        system_prompt = load_system_prompt()

        if self.llm_client.is_enabled:
            try:
                return await self.llm_client.chat_markdown(system_prompt, user_prompt)
            except Exception as exc:  # noqa: BLE001
                return self._fallback_markdown(req, context, error=str(exc))

        return self._fallback_markdown(req, context, error="LLM endpoint not configured")

    async def generate_markdown_stream(
        self,
        req: ResearchRequest,
        context: ResearchContext,
    ) -> AsyncIterator[str]:
        """
        Purpose: Yield markdown chunks from streaming LLM output, with fallback chunking.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `context` (ResearchContext): Input parameter used by this function.
        Returns:
        - `AsyncIterator[str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `generate_markdown_stream(req=..., context=...)`
        """
        user_prompt = self._build_user_prompt(req, context)
        system_prompt = load_system_prompt()

        if self.llm_client.is_enabled:
            try:
                async for chunk in self.llm_client.chat_markdown_stream(system_prompt, user_prompt):
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001
                fallback = self._fallback_markdown(req, context, error=str(exc))
        else:
            fallback = self._fallback_markdown(req, context, error="LLM endpoint not configured")

        for chunk in self._chunk_text(fallback, chunk_size=80):
            yield chunk

    def build_response(
        self,
        req: ResearchRequest,
        context: ResearchContext,
        markdown: str,
    ) -> ResearchResponse:
        """
        Purpose: Package markdown + computed context into API response schema.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `context` (ResearchContext): Input parameter used by this function.
        - `markdown` (str): Input parameter used by this function.
        Returns:
        - `ResearchResponse`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `build_response(req=..., context=..., markdown=...)`
        """
        valuation_summary: ValuationSummary | None = None
        if context.valuation_result is not None:
            valuation_summary = ValuationSummary(
                dcf_equity_value=context.valuation_result.dcf_equity_value,
                dcf_price_per_share=context.valuation_result.dcf_price_per_share,
                comps_price_per_share=context.valuation_result.comps_price_per_share,
                blended_target_price=context.valuation_result.blended_target_price,
                bull_target_price=context.valuation_result.bull_target_price,
                base_target_price=context.valuation_result.base_target_price,
                bear_target_price=context.valuation_result.bear_target_price,
                scenario_weighted_target_price=context.valuation_result.scenario_weighted_target_price,
                scenario_bull_weight=context.valuation_result.scenario_bull_weight,
                scenario_base_weight=context.valuation_result.scenario_base_weight,
                scenario_bear_weight=context.valuation_result.scenario_bear_weight,
                ev_ebitda_price_per_share=context.valuation_result.ev_ebitda_price_per_share,
                p_fcf_price_per_share=context.valuation_result.p_fcf_price_per_share,
                upside_pct=context.valuation_result.upside_pct,
                recommendation=context.valuation_result.recommendation,
                confidence_pct=context.valuation_result.confidence_pct,
                assumptions=context.valuation_result.assumptions,
                sensitivity_grid=[
                    ValuationSensitivityPoint(
                        wacc=float(row.get("wacc", 0.0)),
                        terminal_growth=float(row.get("terminal_growth", 0.0)),
                        implied_price=float(row.get("implied_price", 0.0)),
                    )
                    for row in context.valuation_result.sensitivity_grid
                ],
            )
        return ResearchResponse.from_payload(
            ticker=req.ticker.upper(),
            company_name=req.company_name,
            markdown=markdown,
            signals=context.signals,
            sources=context.sources,
            valuation=valuation_summary,
        )

    def _build_user_prompt(self, req: ResearchRequest, context: ResearchContext) -> str:
        """
        Purpose: Construct a structured prompt including history, signals, and sources.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `context` (ResearchContext): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_build_user_prompt(req=..., context=...)`
        """
        source_block = "\n".join(
            [
                f"- [{source.title}]({source.url}) - {source.snippet[:220]}"
                for source in context.sources[:18]
            ]
        )
        social_block = "\n".join(
            [f"- {source.title}: {source.snippet[:160]}" for source in context.social_sources[:8]]
        )
        signal_block = "\n".join(
            [f"- {signal.label}: {signal.value} ({signal.rationale})" for signal in context.signals]
        )

        history = req.chat_history[-12:]
        history_block = "\n".join(
            [f"- {turn.role}: {turn.content[:300]}" for turn in history]
        )
        attachment_block = "\n\n".join(
            [f"Document {idx + 1}:\n{text[:4000]}" for idx, text in enumerate(req.attachment_texts[:4])]
        )
        external_block = "\n\n".join([ctx[:3500] for ctx in context.external_contexts[:8]])
        decomposition_block = "\n\n".join(context.decomposition_blocks[:8])
        scenario_block = (
            context.scenario_result.to_block()
            if context.scenario_result
            else "- Scenario module not available."
        )
        financial_model_block = (
            context.financial_model_result.to_prompt_block()
            if context.financial_model_result
            else "- Financial model rebuild not enabled."
        )
        valuation_block = (
            context.valuation_result.to_prompt_block()
            if context.valuation_result
            else "- Structured valuation not enabled."
        )
        if logger.isEnabledFor(logging.INFO):
            logger.info(
                "Prompt context summary ticker=%s attachment_count=%d attachment_chars=%d external_context_count=%d decomposition_blocks=%d source_count=%d valuation_enabled=%s",
                req.ticker.upper(),
                len(req.attachment_texts),
                sum(len(text) for text in req.attachment_texts),
                len(context.external_contexts),
                len(context.decomposition_blocks),
                len(context.sources),
                context.valuation_result is not None,
            )

        return f"""
Ticker: {req.ticker.upper()}
Company: {context.company}
Market: {req.market}
Risk tolerance: {req.risk_tolerance.value}
Investment horizon days: {req.horizon_days}
Research question: {req.question or 'General deep research and trade recommendation'}

Recent chat history:
{history_block or '- No previous chat context.'}

Computed signals:
{signal_block}

Market + company sources:
{source_block}

Social evidence:
{social_block or '- No social-specific evidence retrieved.'}

Attached document context:
{attachment_block or '- No attached document text provided.'}

External MCP/A2A context:
{external_block or '- No external agent/tool context provided.'}

Decomposed query evidence:
{decomposition_block or '- Query decomposition not used for this request.'}

Scenario analysis:
{scenario_block}

Financial model analysis:
{financial_model_block}

Structured valuation analysis:
{valuation_block}
""".strip()

    def _fallback_markdown(
        self,
        req: ResearchRequest,
        context: ResearchContext,
        error: str,
    ) -> str:
        """
        Purpose: Return deterministic markdown when LLM call fails or is unavailable.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `context` (ResearchContext): Input parameter used by this function.
        - `error` (str): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_fallback_markdown(req=..., context=..., error=...)`
        """
        scenario = context.scenario_result
        financial_model = context.financial_model_result
        valuation = context.valuation_result
        valuation_score = 0.0
        if valuation:
            valuation_score = max(-1.0, min(1.0, valuation.upside_pct / 25.0))
        if scenario and financial_model and financial_model.is_valid:
            if valuation:
                blended_score = round(
                    (scenario.weighted_score * 0.5)
                    + (financial_model.weighted_score * 0.3)
                    + (valuation_score * 0.2),
                    3,
                )
            else:
                blended_score = round((scenario.weighted_score * 0.6) + (financial_model.weighted_score * 0.4), 3)
            if blended_score >= 0.2:
                recommendation = "Buy"
            elif blended_score <= -0.2:
                recommendation = "Sell"
            else:
                recommendation = "Hold"
            if valuation:
                confidence = min(
                    95,
                    max(
                        35,
                        int(
                            (scenario.confidence_pct * 0.5)
                            + (financial_model.confidence_pct * 0.3)
                            + (valuation.confidence_pct * 0.2)
                        ),
                    ),
                )
            else:
                confidence = min(
                    95,
                    max(35, int((scenario.confidence_pct * 0.6) + (financial_model.confidence_pct * 0.4))),
                )
        elif scenario:
            if valuation:
                blended_score = round((scenario.weighted_score * 0.75) + (valuation_score * 0.25), 3)
                if blended_score >= 0.2:
                    recommendation = "Buy"
                elif blended_score <= -0.2:
                    recommendation = "Sell"
                else:
                    recommendation = "Hold"
                confidence = min(
                    95,
                    max(35, int((scenario.confidence_pct * 0.75) + (valuation.confidence_pct * 0.25))),
                )
            else:
                recommendation = scenario.recommendation
                confidence = scenario.confidence_pct
        elif valuation:
            recommendation = valuation.recommendation
            confidence = valuation.confidence_pct
        else:
            score = sum(signal.value for signal in context.signals[:2]) / 2
            if score >= 0.2:
                recommendation = "Buy"
            elif score <= -0.2:
                recommendation = "Sell"
            else:
                recommendation = "Hold"
            confidence = min(90, max(40, int((context.signals[2].value * 100))))

        lines = [
            "# Executive Summary",
            (
                f"Research on **{req.ticker.upper()} ({context.company})** indicates a "
                f"**{recommendation}** stance with **{confidence}% confidence** "
                f"for a {req.horizon_days}-day horizon."
            ),
            "",
            "# Market and Company Trend Analysis",
            f"- Market sentiment score: **{context.signals[0].value}**",
            f"- Research confidence score: **{context.signals[2].value}**",
            "",
            "# Social Sentiment Analysis",
            f"- Social sentiment score: **{context.signals[1].value}**",
            "",
            "# Risks and Catalysts",
            "- Validate earnings quality, macro headwinds, and sector rotation before execution.",
            "- Monitor guidance changes, regulatory updates, and major management commentary.",
            "",
            "# Recommendation",
            f"**{recommendation}** (confidence: **{confidence}%**) for risk profile **{req.risk_tolerance.value}**.",
        ]
        if scenario:
            lines.append(
                f"- Scenario weighted score: **{scenario.weighted_score}** "
                f"(bull/base/bear: {scenario.bull_score}/{scenario.base_score}/{scenario.bear_score})"
            )
        if financial_model:
            lines.append(
                f"- Financial model weighted score: **{financial_model.weighted_score}** "
                f"({financial_model.recommendation}, confidence {financial_model.confidence_pct}%)"
            )
        if valuation:
            lines.append(
                f"- Structured valuation target: **{valuation.blended_target_price}** "
                f"(upside {valuation.upside_pct}%, {valuation.recommendation}, "
                f"confidence {valuation.confidence_pct}%)"
            )
            lines.append(
                f"- Scenario-weighted valuation target: **{valuation.scenario_weighted_target_price}** "
                f"(bull/base/bear {valuation.bull_target_price}/{valuation.base_target_price}/{valuation.bear_target_price})"
            )
        lines.extend(["", "# Sources"])

        if context.sources:
            for source in context.sources[:15]:
                lines.append(f"- [{source.title}]({source.url})")
        else:
            lines.append("- No sources were retrieved.")

        lines.extend(["", f"> Fallback mode used: {error}"])
        return "\n".join(lines)

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 80) -> List[str]:
        """
        Purpose: Split text into fixed-size chunks for fallback streaming output.
        Args/Params:
        - `text` (str): Input parameter used by this function.
        - `chunk_size` (int): Input parameter used by this function.
        Returns:
        - `List[str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_chunk_text(text=..., chunk_size=...)`
        """
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    @staticmethod
    def _build_queries(req: ResearchRequest) -> dict[str, list[str]]:
        """
        Purpose: Create market and social search queries from user input.
        Args/Params:
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `dict[str, list[str]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_build_queries(req=...)`
        """
        symbol = req.ticker.upper()
        company = req.company_name or symbol
        return {
            "market": [
                f"{symbol} stock latest news",
                f"{company} earnings guidance analysis",
                f"{company} industry trend {req.market}",
            ],
            "social": [
                f"{symbol} sentiment site:x.com OR site:reddit.com",
                f"{company} investor sentiment social media",
            ],
        }

    @staticmethod
    def _dedupe_sources(sources: List[Source]) -> List[Source]:
        """
        Purpose: Remove duplicate sources by URL while preserving original order.
        Args/Params:
        - `sources` (List[Source]): Input parameter used by this function.
        Returns:
        - `List[Source]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_dedupe_sources(sources=...)`
        """
        unique_urls: set[str] = set()
        deduped: List[Source] = []
        for source in sources:
            if source.url in unique_urls:
                continue
            unique_urls.add(source.url)
            deduped.append(source)
        return deduped

    async def _collect_external_context(self, req: ResearchRequest) -> List[str]:
        """
        Purpose: Collect context snippets from configured MCP servers and A2A agents.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `List[str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_collect_external_context(req=...)`
        """
        logger.info(
            "External context dispatch ticker=%s mcp_calls=%d a2a_calls=%d",
            req.ticker.upper(),
            len(req.mcp_calls),
            len(req.a2a_calls),
        )
        tasks = [self.mcp_client.call_tool(call) for call in req.mcp_calls] + [
            self.a2a_client.invoke(call) for call in req.a2a_calls
        ]
        if not tasks:
            logger.info("External context skipped ticker=%s no MCP/A2A calls", req.ticker.upper())
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        contexts: List[str] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "External integration call failed ticker=%s error=%s",
                    req.ticker.upper(),
                    str(result),
                )
                contexts.append(f"External integration call failed: {result}")
            elif isinstance(result, str) and result.strip():
                contexts.append(result.strip())
        logger.info(
            "External context completed ticker=%s context_items=%d",
            req.ticker.upper(),
            len(contexts),
        )
        return contexts

    async def _ingest_attachments_to_vector_db(self, req: ResearchRequest) -> int:
        """
        Purpose: Persist uploaded attachment text into vector database before other retrieval.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `int`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_ingest_attachments_to_vector_db(req=...)`
        """
        if not self.vector_retriever.is_enabled or not req.attachment_texts:
            return 0

        targets: List[tuple[str, str, str, str]] = []
        for idx, attachment in enumerate(req.attachment_texts):
            text = attachment.strip()
            if not text:
                continue
            targets.append(
                (
                    f"Attachment {idx + 1}",
                    f"attachment://{req.ticker.upper()}/{idx + 1}",
                    text,
                    "attachment",
                )
            )

        return await self._upsert_targets(req, targets, max_targets=12, stage="attachments")

    async def _ingest_sources_to_vector_db(
        self,
        req: ResearchRequest,
        sources: List[Source],
    ) -> int:
        """
        Purpose: Persist web-search sources into vector database before vector retrieval.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `sources` (List[Source]): Input parameter used by this function.
        Returns:
        - `int`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_ingest_sources_to_vector_db(req=..., sources=...)`
        """
        if not self.vector_retriever.is_enabled:
            return 0

        ingest_targets: List[tuple[str, str, str, str]] = []
        for source in sources:
            if source.source_type == "vector":
                continue
            text = f"{source.title}\n{source.snippet}".strip()
            if not text:
                continue
            ingest_targets.append((source.title, source.url, text, source.source_type))

        return await self._upsert_targets(req, ingest_targets, max_targets=24, stage="web_sources")

    async def _ingest_external_contexts_to_vector_db(
        self,
        req: ResearchRequest,
        contexts: List[str],
    ) -> int:
        """
        Purpose: Persist MCP/A2A context text into vector DB before vector retrieval.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `contexts` (List[str]): Input parameter used by this function.
        Returns:
        - `int`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_ingest_external_contexts_to_vector_db(req=..., contexts=...)`
        """
        if not self.vector_retriever.is_enabled or not contexts:
            return 0

        ingest_targets: List[tuple[str, str, str, str]] = []
        for idx, text in enumerate(contexts):
            content = text.strip()
            if not content:
                continue
            ingest_targets.append(
                (
                    f"External Context {idx + 1}",
                    f"external://{req.ticker.upper()}/{idx + 1}",
                    content,
                    "external_context",
                )
            )

        return await self._upsert_targets(req, ingest_targets, max_targets=16, stage="external_context")

    async def _run_query_decomposition(
        self,
        req: ResearchRequest,
    ) -> tuple[List[Source], List[str]]:
        """
        Purpose: Execute structured sub-query retrieval by analysis dimensions and return evidence blocks.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `tuple[List[Source], List[str]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_run_query_decomposition(req=...)`
        """
        plan = self._build_decomposition_plan(req)
        logger.info(
            "Query decomposition enabled ticker=%s categories=%s",
            req.ticker.upper(),
            sorted(plan.keys()),
        )
        sources: List[Source] = []
        blocks: List[str] = []

        for category, config in plan.items():
            objective = str(config.get("objective", "")).strip()
            queries = [str(query) for query in config.get("queries", []) if str(query).strip()]
            result_limit = int(config.get("result_limit", 2))
            category_sources: List[Source] = []
            for query in queries:
                category_sources.extend(await self.web_searcher.search(query, limit=result_limit))
            category_sources = self._dedupe_sources(category_sources)
            sources.extend(category_sources)

            summary_lines = [
                f"### {category.title()}",
                f"- Objective: {objective or 'N/A'}",
                f"- Query count: {len(queries)}",
                f"- Retrieved sources: {len(category_sources)}",
            ]
            for source in category_sources[:3]:
                summary_lines.append(
                    f"- [{source.title}]({source.url}) - {source.snippet[:180]}"
                )
            blocks.append("\n".join(summary_lines))

        return self._dedupe_sources(sources), blocks

    def _build_decomposition_plan(self, req: ResearchRequest) -> dict[str, dict[str, Any]]:
        """
        Purpose: Build a professional-style decomposition plan spanning core equity research dimensions.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `dict[str, dict[str, Any]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_build_decomposition_plan(req=...)`
        """
        symbol = req.ticker.upper()
        company = req.company_name or symbol
        user_query = req.question or "stock recommendation"
        return {
            "mandate_screening": {
                "objective": "Quick sanity checks on size, liquidity, leverage, and profitability.",
                "result_limit": 2,
                "queries": [
                    f"{symbol} market cap average volume debt ratio profitability metrics",
                    f"{company} liquidity leverage return on equity return on invested capital",
                ],
            },
            "business_industry": {
                "objective": "Understand business model, market structure, and competitive positioning.",
                "result_limit": 2,
                "queries": [
                    f"{company} business model revenue drivers customer segments",
                    f"{company} industry outlook market share competition value chain",
                ],
            },
            "core_documents": {
                "objective": "Gather canonical primary sources (filings, transcripts, investor materials).",
                "result_limit": 2,
                "queries": [
                    f"{company} 10-K 10-Q annual report investor presentation site:sec.gov OR site:{symbol.lower()}.com",
                    f"{company} earnings call transcript guidance management commentary",
                ],
            },
            "historical_financials": {
                "objective": "Assess multi-year trends in growth, margins, returns, and cash generation.",
                "result_limit": 2,
                "queries": [
                    f"{symbol} 5 year revenue margin free cash flow trend",
                    f"{company} ROE ROIC capex buyback dividend M&A history",
                ],
            },
            "sentiment": {
                "objective": "Capture social and analyst tone drift around the name.",
                "result_limit": 2,
                "queries": [
                    f"{symbol} investor sentiment site:x.com OR site:reddit.com",
                    f"{company} analyst sentiment upgrades downgrades outlook",
                ],
            },
            "valuation": {
                "objective": "Build relative and intrinsic valuation context.",
                "result_limit": 2,
                "queries": [
                    f"{symbol} valuation PE EV/EBITDA price to free cash flow peers",
                    f"{company} DCF assumptions growth margin terminal value {user_query}",
                ],
            },
            "catalysts_risks": {
                "objective": "Identify upside drivers, downside risks, and trigger events.",
                "result_limit": 2,
                "queries": [
                    f"{company} key catalysts and risks next 12 months",
                    f"{symbol} regulatory litigation supply chain macro risk",
                ],
            },
            "thesis_testing": {
                "objective": "Stress-test thesis against opposing views and scenario outcomes.",
                "result_limit": 2,
                "queries": [
                    f"{symbol} bear case short thesis counter argument",
                    f"{company} bull base bear scenario sensitivity analysis",
                ],
            },
            "portfolio_fit": {
                "objective": "Assess position sizing and portfolio interaction considerations.",
                "result_limit": 2,
                "queries": [
                    f"{symbol} beta volatility drawdown correlation sector",
                    f"{company} risk adjusted return portfolio fit concentration risk",
                ],
            },
        }

    async def _upsert_targets(
        self,
        req: ResearchRequest,
        ingest_targets: List[tuple[str, str, str, str]],
        max_targets: int,
        stage: str,
    ) -> int:
        """
        Purpose: Embed and upsert target text blocks into vector database.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        - `ingest_targets` (List[tuple[str, str, str, str]]): Input parameter used by this function.
        - `max_targets` (int): Input parameter used by this function.
        - `stage` (str): Input parameter used by this function.
        Returns:
        - `int`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_upsert_targets(req=..., ingest_targets=..., max_targets=..., stage=...)`
        """
        points: List[dict] = []
        if not ingest_targets:
            return 0

        ingest_targets = ingest_targets[:max_targets]
        if logger.isEnabledFor(logging.INFO):
            logger.info(
                "Vector ingestion started ticker=%s stage=%s targets=%d",
                req.ticker.upper(),
                stage,
                len(ingest_targets),
            )

        for title, url, text, source_type in ingest_targets:
            try:
                vector = await self.llm_client.embed(text[:6000])
            except Exception as exc:
                logger.warning(
                    "Vector ingestion embedding failed ticker=%s title=%s error=%s",
                    req.ticker.upper(),
                    title[:80],
                    str(exc),
                )
                continue

            if not vector:
                continue

            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}:{text[:500]}"))
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "title": title[:256],
                        "url": url[:512],
                        "text": text[:6000],
                        "source_type": source_type,
                        "ticker": req.ticker.upper(),
                    },
                }
            )

        if not points:
            return 0

        try:
            ingested = await self.vector_retriever.upsert_points(points)
            if logger.isEnabledFor(logging.INFO):
                logger.info(
                    "Vector ingestion completed ticker=%s stage=%s ingested_points=%d",
                    req.ticker.upper(),
                    stage,
                    ingested,
                )
            return ingested
        except Exception as exc:
            logger.warning(
                "Vector ingestion upsert failed ticker=%s stage=%s error=%s",
                req.ticker.upper(),
                stage,
                str(exc),
            )
            return 0

    def _run_financial_model(self, req: ResearchRequest) -> FinancialModelResult:
        """
        Purpose: Execute selected financial engine while preserving backward compatibility.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `req` (ResearchRequest): Input parameter used by this function.
        Returns:
        - `FinancialModelResult`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_run_financial_model(req=...)`
        """
        if req.use_advanced_financial_engine:
            return self.advanced_financial_engine.evaluate(
                advanced_input=req.advanced_financial_input,
                fallback_input=req.financial_model_input,
            )
        if req.financial_model_input:
            return self.financial_model_rebuilder.evaluate(req.financial_model_input)
        return FinancialModelResult(
            is_valid=False,
            issues=["Financial model rebuild enabled but no financial_model_input provided."],
            historical_summary="No financial input supplied.",
            base_case=[],
            bull_case=[],
            bear_case=[],
            weighted_score=0.0,
            recommendation="Hold",
            confidence_pct=35,
        )
