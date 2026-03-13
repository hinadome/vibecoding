from __future__ import annotations

from typing import Iterable, List

from app.models import Signal, Source
from app.services.sentiment import SentimentAnalyzer


class MarketAnalyzer:
    def __init__(self) -> None:
        """
        Purpose: Create analyzer with shared keyword-based sentiment engine.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `None`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `__init__()`
        """
        self.sentiment = SentimentAnalyzer()

    def evaluate_market_sentiment(self, sources: Iterable[Source]) -> Signal:
        """
        Purpose: Compute market sentiment signal from all retrieved source snippets.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `sources` (Iterable[Source]): Input parameter used by this function.
        Returns:
        - `Signal`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `evaluate_market_sentiment(sources=...)`
        """
        texts = [f"{item.title} {item.snippet}" for item in sources]
        score = self.sentiment.score_texts(texts)
        return Signal(
            label="Market sentiment",
            value=round(score.score, 3),
            rationale=(
                f"Detected {score.positive_hits} positive and {score.negative_hits} "
                "negative market terms across research sources."
            ),
        )

    def evaluate_social_sentiment(self, social_sources: Iterable[Source]) -> Signal:
        """
        Purpose: Compute social sentiment signal from social-focused evidence.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `social_sources` (Iterable[Source]): Input parameter used by this function.
        Returns:
        - `Signal`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `evaluate_social_sentiment(social_sources=...)`
        """
        texts = [f"{item.title} {item.snippet}" for item in social_sources]
        score = self.sentiment.score_texts(texts)
        return Signal(
            label="Social sentiment",
            value=round(score.score, 3),
            rationale=(
                f"Detected {score.positive_hits} positive and {score.negative_hits} "
                "negative social-trend terms."
            ),
        )

    def evaluate_source_strength(self, all_sources: List[Source]) -> Signal:
        """
        Purpose: Estimate confidence from source count and domain diversity.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `all_sources` (List[Source]): Input parameter used by this function.
        Returns:
        - `Signal`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `evaluate_source_strength(all_sources=...)`
        """
        source_count = len(all_sources)
        unique_domains = len({self._extract_domain(source.url) for source in all_sources})
        score = min(1.0, (source_count / 12) * 0.6 + (unique_domains / 10) * 0.4)
        return Signal(
            label="Research confidence",
            value=round(score, 3),
            rationale=(
                f"Used {source_count} sources across {unique_domains} domains "
                "for evidence breadth."
            ),
        )

    @staticmethod
    def _extract_domain(url: str) -> str:
        """
        Purpose: Extract normalized domain from a URL string.
        Args/Params:
        - `url` (str): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_extract_domain(url=...)`
        """
        if "//" not in url:
            return "unknown"
        domain = url.split("//", 1)[1].split("/", 1)[0].lower()
        if domain.startswith("www."):
            return domain[4:]
        return domain
