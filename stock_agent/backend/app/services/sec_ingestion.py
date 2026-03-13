from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import Source

logger = logging.getLogger("uvicorn.error")

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik_no_zero}/{accession_no_dash}/{primary_doc}"
DEFAULT_FORMS = {"10-K", "10-Q", "8-K", "DEF 14A", "20-F", "6-K"}


class SecEdgarIngestionService:
    """Fetch and normalize SEC/EDGAR primary filings into source objects."""

    def __init__(self, settings: Settings) -> None:
        """
        Purpose: Initialize service with SEC access settings and in-memory ticker cache.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `settings` (Settings): Input parameter used by this function.
        Returns:
        - `None`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `__init__(settings=...)`
        """
        self.settings = settings
        self._ticker_cache: Optional[Dict[str, str]] = None
        self._ticker_cache_loaded_at: float = 0.0

    async def search_primary_sources(
        self,
        ticker: str,
        company_name: str | None = None,
    ) -> List[Source]:
        """
        Purpose: Retrieve recent SEC primary filings for a ticker and map to Source entries.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `ticker` (str): Input parameter used by this function.
        - `company_name` (str | None): Input parameter used by this function.
        Returns:
        - `List[Source]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `search_primary_sources(ticker=..., company_name=...)`
        """
        symbol = ticker.upper().strip()
        if not symbol:
            return []

        started = time.perf_counter()
        cik = await self._resolve_cik(symbol)
        if not cik:
            logger.warning("SEC ingestion skipped ticker=%s reason=cik_not_found", symbol)
            return []

        submissions_url = SUBMISSIONS_URL_TEMPLATE.format(cik=cik)
        try:
            submissions = await self._fetch_json(submissions_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "SEC submissions fetch failed ticker=%s cik=%s error=%s",
                symbol,
                cik,
                str(exc),
            )
            return []

        filings = self._extract_recent_filings(
            submissions=submissions,
            max_filings=max(1, self.settings.sec_max_filings),
        )
        sources: List[Source] = []
        for filing in filings:
            form_type = filing["form"]
            filing_date = filing["filing_date"]
            accession_number = filing["accession_number"]
            primary_doc = filing["primary_doc"]
            if not self._is_safe_accession(accession_number):
                continue
            if not self._is_safe_primary_doc(primary_doc):
                continue
            filing_url = ARCHIVES_URL_TEMPLATE.format(
                cik_no_zero=str(int(cik)),
                accession_no_dash=accession_number.replace("-", ""),
                primary_doc=primary_doc,
            )
            index_url = (
                f"https://www.sec.gov/Archives/edgar/data/{str(int(cik))}/"
                f"{accession_number.replace('-', '')}/{accession_number}-index.html"
            )
            snippet = (
                f"Primary SEC filing for {symbol}: form={form_type}, filing_date={filing_date}, "
                f"accession={accession_number}."
            )

            filing_text = ""
            try:
                filing_text = await self._fetch_text(filing_url)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SEC filing body fetch failed ticker=%s accession=%s error=%s",
                    symbol,
                    accession_number,
                    str(exc),
                )
                try:
                    filing_text = await self._fetch_text(index_url)
                except Exception:
                    filing_text = ""
            if filing_text:
                cleaned = self._extract_filing_snippet(
                    filing_text, max_chars=max(200, self.settings.sec_filing_excerpt_chars)
                )
                if cleaned:
                    snippet = cleaned

            title_company = company_name or symbol
            title = f"{title_company} {form_type} ({filing_date})"
            sources.append(
                Source(
                    title=title,
                    url=filing_url,
                    snippet=snippet,
                    source_type="sec_filing",
                )
            )

        if self.settings.app_env == "dev":
            logger.info(
                "SEC ingestion completed ticker=%s cik=%s filings=%d elapsed_ms=%d",
                symbol,
                cik,
                len(sources),
                int((time.perf_counter() - started) * 1000),
            )
        return sources

    async def _resolve_cik(self, ticker: str) -> Optional[str]:
        """
        Purpose: Resolve ticker to zero-padded SEC CIK using SEC company ticker map.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `ticker` (str): Input parameter used by this function.
        Returns:
        - `Optional[str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_resolve_cik(ticker=...)`
        """
        now = time.time()
        ttl_sec = max(60, int(self.settings.sec_ticker_cache_ttl_sec))
        if self._ticker_cache is None or (now - self._ticker_cache_loaded_at) > ttl_sec:
            data = await self._fetch_json(TICKER_MAP_URL)
            self._ticker_cache = self._build_ticker_cache(data)
            self._ticker_cache_loaded_at = now
        return self._ticker_cache.get(ticker.upper()) if self._ticker_cache else None

    @staticmethod
    def _build_ticker_cache(data: Any) -> Dict[str, str]:
        """
        Purpose: Build ticker->CIK dictionary from SEC company tickers payload.
        Args/Params:
        - `data` (Any): Input parameter used by this function.
        Returns:
        - `Dict[str, str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_build_ticker_cache(data=...)`
        """
        cache: Dict[str, str] = {}
        if isinstance(data, dict):
            values = data.values()
            for item in values:
                if not isinstance(item, dict):
                    continue
                ticker = str(item.get("ticker", "")).upper().strip()
                cik = item.get("cik_str")
                if ticker and cik is not None:
                    try:
                        cache[ticker] = str(int(cik)).zfill(10)
                    except (TypeError, ValueError):
                        continue
        return cache

    @staticmethod
    def _extract_recent_filings(
        submissions: Any,
        max_filings: int,
        allowed_forms: Optional[set[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Purpose: Extract recent canonical filing tuples from SEC submissions payload.
        Args/Params:
        - `submissions` (Any): Input parameter used by this function.
        - `max_filings` (int): Input parameter used by this function.
        - `allowed_forms` (Optional[set[str]]): Input parameter used by this function.
        Returns:
        - `List[Dict[str, str]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_extract_recent_filings(submissions=..., max_filings=..., allowed_forms=...)`
        """
        if not isinstance(submissions, dict):
            return []
        allowed = allowed_forms or DEFAULT_FORMS
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])

        count = min(len(forms), len(filing_dates), len(accession_numbers), len(primary_docs))
        filings: List[Dict[str, str]] = []
        seen_accessions: set[str] = set()
        for idx in range(count):
            form_type = str(forms[idx] or "").strip()
            if form_type not in allowed:
                continue
            accession = str(accession_numbers[idx] or "")
            if accession in seen_accessions:
                continue
            seen_accessions.add(accession)
            filings.append(
                {
                    "form": form_type,
                    "filing_date": str(filing_dates[idx] or ""),
                    "accession_number": accession,
                    "primary_doc": str(primary_docs[idx] or ""),
                }
            )
            if len(filings) >= max_filings:
                break
        return filings

    def _headers(self, url: str) -> Dict[str, str]:
        """
        Purpose: Return SEC-compliant request headers.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `url` (str): Input parameter used by this function.
        Returns:
        - `Dict[str, str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_headers(url=...)`
        """
        host = urlparse(url).netloc or "www.sec.gov"
        return {
            "User-Agent": self.settings.sec_user_agent,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.sec.gov/",
            "Host": host,
        }

    async def _fetch_json(self, url: str) -> Any:
        """
        Purpose: Fetch JSON document from SEC endpoint.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `url` (str): Input parameter used by this function.
        Returns:
        - `Any`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_fetch_json(url=...)`
        """
        response = await self._request_with_retry("GET", url)
        return response.json()

    async def _fetch_text(self, url: str) -> str:
        """
        Purpose: Fetch filing body text/html from SEC archives endpoint.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `url` (str): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_fetch_text(url=...)`
        """
        response = await self._request_with_retry("GET", url)
        return response.text

    async def _request_with_retry(self, method: str, url: str) -> httpx.Response:
        """
        Purpose: Execute outbound SEC request with bounded retry/backoff for transient failures.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `method` (str): Input parameter used by this function.
        - `url` (str): Input parameter used by this function.
        Returns:
        - `httpx.Response`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_request_with_retry(method=..., url=...)`
        """
        retries = max(0, int(self.settings.sec_request_retries))
        backoff_ms = max(100, int(self.settings.sec_retry_backoff_ms))
        attempts = retries + 1
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self.settings.outbound_timeout_sec) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.request(method, url, headers=self._headers(url))
                    response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    retryable = status in {429, 500, 502, 503, 504}
                    if attempt >= attempts or not retryable:
                        raise
                except httpx.RequestError as exc:
                    last_error = exc
                    if attempt >= attempts:
                        raise

                sleep_sec = (backoff_ms * attempt) / 1000
                await asyncio.sleep(sleep_sec)

        if last_error is not None:
            raise last_error
        raise RuntimeError("SEC request failed without explicit error")

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Purpose: Normalize raw filing HTML/text into compact plain text snippet.
        Args/Params:
        - `text` (str): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_normalize_text(text=...)`
        """
        without_tags = re.sub(r"<[^>]+>", " ", text)
        collapsed = re.sub(r"\s+", " ", without_tags).strip()
        return collapsed

    @classmethod
    def _extract_filing_snippet(cls, text: str, max_chars: int) -> str:
        """
        Purpose: Extract high-signal excerpt from filing text for retrieval/prompt context.
        Args/Params:
        - `cls` (Any): Class reference for class-level behavior.
        - `text` (str): Input parameter used by this function.
        - `max_chars` (int): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_extract_filing_snippet(text=..., max_chars=...)`
        """
        normalized = cls._normalize_text(text)
        if not normalized:
            return ""

        anchors = [
            "item 1. business",
            "item 1a. risk factors",
            "management's discussion and analysis",
            "results of operations",
            "liquidity and capital resources",
        ]
        lowered = normalized.lower()
        for anchor in anchors:
            idx = lowered.find(anchor)
            if idx >= 0:
                return normalized[idx : idx + max_chars]
        return normalized[:max_chars]

    @staticmethod
    def _is_safe_primary_doc(primary_doc: str) -> bool:
        """
        Purpose: Validate primary document path shape from SEC payload.
        Args/Params:
        - `primary_doc` (str): Input parameter used by this function.
        Returns:
        - `bool`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_is_safe_primary_doc(primary_doc=...)`
        """
        doc = primary_doc.strip()
        if not doc or "/" in doc or "\\" in doc:
            return False
        return bool(re.fullmatch(r"[A-Za-z0-9._\-]+", doc))

    @staticmethod
    def _is_safe_accession(accession: str) -> bool:
        """
        Purpose: Validate accession number shape from SEC payload.
        Args/Params:
        - `accession` (str): Input parameter used by this function.
        Returns:
        - `bool`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_is_safe_accession(accession=...)`
        """
        return bool(re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession.strip()))
