import unittest
from unittest.mock import AsyncMock

from app.config import Settings
from app.services.sec_ingestion import SecEdgarIngestionService


class SecEdgarIngestionServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_primary_sources_returns_filings(self) -> None:
        service = SecEdgarIngestionService(Settings())

        ticker_map_payload = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        }
        submissions_payload = {
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K"],
                    "filingDate": ["2024-11-01", "2024-12-15"],
                    "accessionNumber": ["0000320193-24-000123", "0000320193-24-000150"],
                    "primaryDocument": ["a10k.htm", "a8k.htm"],
                }
            }
        }

        service._fetch_json = AsyncMock(side_effect=[ticker_map_payload, submissions_payload])  # type: ignore[method-assign]
        service._fetch_text = AsyncMock(return_value="<html><body>Primary filing body text</body></html>")  # type: ignore[method-assign]

        sources = await service.search_primary_sources("AAPL", "Apple")
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0].source_type, "sec_filing")
        self.assertIn("Apple", sources[0].title)
        self.assertTrue(sources[0].url.startswith("https://www.sec.gov/Archives/edgar/data/"))

    async def test_search_primary_sources_returns_empty_when_ticker_unknown(self) -> None:
        service = SecEdgarIngestionService(Settings())
        service._fetch_json = AsyncMock(return_value={})  # type: ignore[method-assign]
        service._fetch_text = AsyncMock(return_value="")  # type: ignore[method-assign]

        sources = await service.search_primary_sources("UNKNOWN")
        self.assertEqual(sources, [])

    def test_extract_recent_filings_filters_forms(self) -> None:
        submissions_payload = {
            "filings": {
                "recent": {
                    "form": ["10-K", "S-3", "10-Q", "10-Q"],
                    "filingDate": ["2024-11-01", "2024-10-11", "2024-08-01", "2024-08-01"],
                    "accessionNumber": [
                        "0000320193-24-000123",
                        "0000320193-24-000124",
                        "0000320193-24-000125",
                        "0000320193-24-000125",
                    ],
                    "primaryDocument": ["a10k.htm", "s3.htm", "a10q.htm", "a10q.htm"],
                }
            }
        }
        filings = SecEdgarIngestionService._extract_recent_filings(submissions_payload, max_filings=5)
        self.assertEqual(len(filings), 2)
        self.assertEqual([item["form"] for item in filings], ["10-K", "10-Q"])

    def test_validate_accession_and_doc_safety(self) -> None:
        self.assertTrue(SecEdgarIngestionService._is_safe_accession("0000320193-24-000123"))
        self.assertFalse(SecEdgarIngestionService._is_safe_accession("bad-value"))
        self.assertTrue(SecEdgarIngestionService._is_safe_primary_doc("a10k.htm"))
        self.assertFalse(SecEdgarIngestionService._is_safe_primary_doc("../etc/passwd"))
