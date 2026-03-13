import json
from typing import AsyncIterator
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import app.main as main_module
from app.models import ResearchResponse, Signal, Source, ValuationSensitivityPoint, ValuationSummary
from app.services.research_agent import ResearchContext


class _FakeAgent:
    async def prepare_context(self, req):
        return ResearchContext(
            company=req.company_name or req.ticker.upper(),
            signals=[Signal(label="Market Sentiment", value=0.2, rationale="stub")],
            sources=[
                Source(
                    title="Stub Source",
                    url="https://example.com/stub",
                    snippet="stub snippet",
                    source_type="web",
                )
            ],
            social_sources=[],
            external_contexts=[],
            decomposition_blocks=[],
        )

    async def generate_markdown_stream(self, req, context) -> AsyncIterator[str]:
        yield "Hello "
        yield "world"

    def build_response(self, req, context, markdown):
        return ResearchResponse.from_payload(
            ticker=req.ticker.upper(),
            company_name=req.company_name,
            markdown=markdown,
            signals=context.signals,
            sources=context.sources,
            valuation=ValuationSummary(
                dcf_equity_value=1000.0,
                dcf_price_per_share=120.0,
                comps_price_per_share=118.0,
                blended_target_price=119.2,
                upside_pct=8.3,
                recommendation="Buy",
                confidence_pct=71,
                assumptions={"wacc": 0.1},
                sensitivity_grid=[
                    ValuationSensitivityPoint(wacc=0.1, terminal_growth=0.03, implied_price=119.2)
                ],
            ),
        )


class MainApiTests(TestCase):
    def setUp(self) -> None:
        self.client = TestClient(main_module.app)

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_stream_endpoint_emits_chunk_meta_done(self) -> None:
        request_payload = {
            "ticker": "NVDA",
            "company_name": "NVIDIA",
            "market": "US",
            "question": "hi",
            "horizon_days": 90,
            "risk_tolerance": "moderate",
            "bypass_web_search": False,
            "use_query_decomposition": True,
            "use_primary_source_ingestion": True,
            "use_advanced_financial_engine": True,
            "use_structured_valuation": True,
            "chat_history": [],
            "mcp_calls": [],
            "a2a_calls": [],
        }
        with patch.object(main_module, "agent", _FakeAgent()):
            response = self.client.post("/api/chat/stream", json=request_payload)

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: chunk", response.text)
        self.assertIn("event: meta", response.text)
        self.assertIn("event: done", response.text)
        self.assertIn("Hello world", response.text)
        self.assertIn("valuation", response.text)

    def test_upload_endpoint_parses_form_data_and_forwards_request(self) -> None:
        def _fake_stream_response(req):
            return JSONResponse(req.model_dump())

        form_data = {
            "ticker": "NVDA",
            "company_name": "NVIDIA",
            "market": "US",
            "question": "run with file",
            "horizon_days": "120",
            "risk_tolerance": "moderate",
            "bypass_web_search": "false",
            "use_query_decomposition": "true",
            "use_primary_source_ingestion": "true",
            "use_financial_model_rebuild": "true",
            "use_advanced_financial_engine": "true",
            "use_structured_valuation": "true",
            "financial_model_input": json.dumps(
                {
                    "periods": [
                        {
                            "year": 2022,
                            "revenue": 1000,
                            "net_income": 100,
                            "total_assets": 2000,
                            "total_liabilities": 900,
                            "total_equity": 1100,
                        },
                        {
                            "year": 2023,
                            "revenue": 1100,
                            "net_income": 120,
                            "total_assets": 2100,
                            "total_liabilities": 940,
                            "total_equity": 1160,
                        },
                        {
                            "year": 2024,
                            "revenue": 1200,
                            "net_income": 150,
                            "total_assets": 2250,
                            "total_liabilities": 980,
                            "total_equity": 1270,
                        },
                    ],
                    "forecast_years": 3,
                }
            ),
            "advanced_financial_input": json.dumps(
                {
                    "initial_state": {
                        "year": 2024,
                        "cash": 300,
                        "debt": 500,
                        "retained_earnings": 1200,
                        "share_capital": 600,
                        "ppe_net": 900,
                        "other_assets": 400,
                        "other_liabilities": 300,
                        "shares_outstanding": 2500,
                    },
                    "forecast": [
                        {"year": 2025, "volume": 15, "price": 100},
                        {"year": 2026, "volume": 16, "price": 102},
                    ],
                }
            ),
            "valuation_input": json.dumps(
                {
                    "current_price": 120.0,
                    "shares_outstanding": 2500.0,
                    "net_debt": 2200.0,
                    "wacc": 0.10,
                    "terminal_growth": 0.03,
                    "terminal_fcf_multiple": 18.0,
                    "peer_pe": 24.0,
                    "peer_ev_fcf": 21.0,
                }
            ),
            "chat_history": json.dumps([{"role": "user", "content": "hello"}]),
            "mcp_calls": json.dumps(
                [{"server": "market-mcp", "tool": "get_company_snapshot", "arguments": {"ticker": "NVDA"}}]
            ),
            "a2a_calls": json.dumps(
                [{"agent": "risk-agent", "task": "assess risk", "context": {"ticker": "NVDA"}}]
            ),
        }
        files = [("files", ("note.txt", b"hello", "text/plain"))]

        with patch.object(main_module, "_stream_research_response", side_effect=_fake_stream_response):
            with patch.object(main_module, "extract_text_from_upload", new=AsyncMock(return_value="document body")):
                response = self.client.post("/api/chat/stream/upload", data=form_data, files=files)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ticker"], "NVDA")
        self.assertFalse(payload["bypass_web_search"])
        self.assertTrue(payload["use_query_decomposition"])
        self.assertTrue(payload["use_primary_source_ingestion"])
        self.assertTrue(payload["use_financial_model_rebuild"])
        self.assertTrue(payload["use_advanced_financial_engine"])
        self.assertTrue(payload["use_structured_valuation"])
        self.assertEqual(len(payload["chat_history"]), 1)
        self.assertEqual(len(payload["mcp_calls"]), 1)
        self.assertEqual(len(payload["a2a_calls"]), 1)
        self.assertEqual(len(payload["attachment_texts"]), 1)
        self.assertEqual(payload["financial_model_input"]["forecast_years"], 3)
        self.assertEqual(payload["advanced_financial_input"]["initial_state"]["year"], 2024)
        self.assertEqual(payload["valuation_input"]["peer_pe"], 24.0)
        self.assertIn("note.txt", payload["attachment_texts"][0])

    def test_upload_endpoint_rejects_invalid_json(self) -> None:
        response = self.client.post(
            "/api/chat/stream/upload",
            data={
                "ticker": "NVDA",
                "chat_history": "[invalid",
                "mcp_calls": "[]",
                "a2a_calls": "[]",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid upload payload", response.text)
