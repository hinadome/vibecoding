from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.models import RiskTolerance, Signal, Source


@dataclass
class ScenarioResult:
    bull_score: float
    base_score: float
    bear_score: float
    bull_weight: float
    base_weight: float
    bear_weight: float
    weighted_score: float
    recommendation: str
    confidence_pct: int
    rationale: str

    def to_block(self) -> str:
        """
        Purpose: Render a compact markdown block for prompt augmentation.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `to_block()`
        """
        return "\n".join(
            [
                f"- Bull scenario score: {self.bull_score:.3f} (weight {self.bull_weight:.2f})",
                f"- Base scenario score: {self.base_score:.3f} (weight {self.base_weight:.2f})",
                f"- Bear scenario score: {self.bear_score:.3f} (weight {self.bear_weight:.2f})",
                f"- Weighted scenario score: {self.weighted_score:.3f}",
                f"- Scenario recommendation: {self.recommendation} ({self.confidence_pct}% confidence)",
                f"- Scenario rationale: {self.rationale}",
            ]
        )


class ScenarioAnalyzer:
    """Compute bull/base/bear scenario scores and weighted recommendation."""

    def evaluate(
        self,
        risk_tolerance: RiskTolerance,
        signals: Iterable[Signal],
        sources: Iterable[Source],
    ) -> ScenarioResult:
        """
        Purpose: Create scenario scores from signal strength and evidence breadth.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `risk_tolerance` (RiskTolerance): Input parameter used by this function.
        - `signals` (Iterable[Signal]): Input parameter used by this function.
        - `sources` (Iterable[Source]): Input parameter used by this function.
        Returns:
        - `ScenarioResult`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `evaluate(risk_tolerance=..., signals=..., sources=...)`
        """
        signal_map = {signal.label.lower(): signal for signal in signals}
        market = signal_map.get("market sentiment", Signal(label="", value=0.0, rationale="")).value
        social = signal_map.get("social sentiment", Signal(label="", value=0.0, rationale="")).value
        confidence = signal_map.get("research confidence", Signal(label="", value=0.4, rationale="")).value
        source_count = len(list(sources))

        evidence_adjust = min(0.15, source_count / 100)
        bull = self._clamp((market * 0.60) + (social * 0.40) + evidence_adjust)
        base = self._clamp((market * 0.50) + (social * 0.25) + (confidence * 0.25))
        bear = self._clamp((-market * 0.65) + (-social * 0.35) + ((1 - confidence) * 0.20))

        bull_weight, base_weight, bear_weight = self._weights_for_risk(risk_tolerance)
        weighted_score = self._clamp(
            (bull * bull_weight) + (base * base_weight) - (bear * bear_weight)
        )

        if weighted_score >= 0.20:
            recommendation = "Buy"
        elif weighted_score <= -0.20:
            recommendation = "Sell"
        else:
            recommendation = "Hold"

        confidence_pct = min(
            95,
            max(35, int((confidence * 55) + (abs(weighted_score) * 35) + 10)),
        )

        rationale = (
            f"Risk profile={risk_tolerance.value}, market={market:.3f}, social={social:.3f}, "
            f"confidence={confidence:.3f}, evidence_sources={source_count}"
        )

        return ScenarioResult(
            bull_score=round(bull, 3),
            base_score=round(base, 3),
            bear_score=round(bear, 3),
            bull_weight=bull_weight,
            base_weight=base_weight,
            bear_weight=bear_weight,
            weighted_score=round(weighted_score, 3),
            recommendation=recommendation,
            confidence_pct=confidence_pct,
            rationale=rationale,
        )

    @staticmethod
    def _weights_for_risk(risk_tolerance: RiskTolerance) -> tuple[float, float, float]:
        """
        Purpose: Return scenario weights tuned for conservative/moderate/aggressive profiles.
        Args/Params:
        - `risk_tolerance` (RiskTolerance): Input parameter used by this function.
        Returns:
        - `tuple[float, float, float]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_weights_for_risk(risk_tolerance=...)`
        """
        if risk_tolerance == RiskTolerance.conservative:
            return (0.20, 0.55, 0.25)
        if risk_tolerance == RiskTolerance.aggressive:
            return (0.45, 0.40, 0.15)
        return (0.30, 0.50, 0.20)

    @staticmethod
    def _clamp(value: float, min_value: float = -1.0, max_value: float = 1.0) -> float:
        """
        Purpose: Clamp score into expected normalized range.
        Args/Params:
        - `value` (float): Input parameter used by this function.
        - `min_value` (float): Input parameter used by this function.
        - `max_value` (float): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_clamp(value=..., min_value=..., max_value=...)`
        """
        return max(min_value, min(max_value, value))
