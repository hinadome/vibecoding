from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


POSITIVE_WORDS = {
    "beat",
    "growth",
    "upside",
    "surge",
    "bullish",
    "profit",
    "upgrade",
    "buy",
    "strong",
    "record",
    "outperform",
}

NEGATIVE_WORDS = {
    "miss",
    "drop",
    "downside",
    "slump",
    "bearish",
    "loss",
    "downgrade",
    "sell",
    "weak",
    "risk",
    "lawsuit",
}


@dataclass
class SentimentScore:
    positive_hits: int
    negative_hits: int

    @property
    def score(self) -> float:
        """
        Purpose: Return normalized sentiment in range [-1, 1] based on hit counts.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `score()`
        """
        total = self.positive_hits + self.negative_hits
        if total == 0:
            return 0.0
        return (self.positive_hits - self.negative_hits) / total


class SentimentAnalyzer:
    def score_text(self, text: str) -> SentimentScore:
        """
        Purpose: Score one text block by counting positive/negative keyword hits.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `text` (str): Input parameter used by this function.
        Returns:
        - `SentimentScore`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `score_text(text=...)`
        """
        tokens = [token.strip(".,:;!?()[]{}\"'`).").lower() for token in text.split()]
        positives = sum(token in POSITIVE_WORDS for token in tokens)
        negatives = sum(token in NEGATIVE_WORDS for token in tokens)
        return SentimentScore(positive_hits=positives, negative_hits=negatives)

    def score_texts(self, texts: Iterable[str]) -> SentimentScore:
        """
        Purpose: Aggregate sentiment counts across multiple text blocks.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `texts` (Iterable[str]): Input parameter used by this function.
        Returns:
        - `SentimentScore`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `score_texts(texts=...)`
        """
        positive_hits = 0
        negative_hits = 0
        for text in texts:
            score = self.score_text(text)
            positive_hits += score.positive_hits
            negative_hits += score.negative_hits
        return SentimentScore(positive_hits=positive_hits, negative_hits=negative_hits)
