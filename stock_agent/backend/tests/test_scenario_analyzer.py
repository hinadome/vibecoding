import unittest

from app.models import RiskTolerance, Signal, Source
from app.services.scenario_analyzer import ScenarioAnalyzer


class ScenarioAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = ScenarioAnalyzer()

    def test_aggressive_profile_biases_bull_weight(self) -> None:
        result = self.analyzer.evaluate(
            risk_tolerance=RiskTolerance.aggressive,
            signals=[
                Signal(label="Market sentiment", value=0.5, rationale=""),
                Signal(label="Social sentiment", value=0.3, rationale=""),
                Signal(label="Research confidence", value=0.8, rationale=""),
            ],
            sources=[Source(title="s", url="https://example.com", snippet="x", source_type="web")],
        )
        self.assertEqual(result.bull_weight, 0.45)
        self.assertEqual(result.base_weight, 0.40)
        self.assertEqual(result.bear_weight, 0.15)

    def test_weighted_score_maps_to_hold_for_neutral_signals(self) -> None:
        result = self.analyzer.evaluate(
            risk_tolerance=RiskTolerance.moderate,
            signals=[
                Signal(label="Market sentiment", value=0.0, rationale=""),
                Signal(label="Social sentiment", value=0.0, rationale=""),
                Signal(label="Research confidence", value=0.5, rationale=""),
            ],
            sources=[],
        )
        self.assertEqual(result.recommendation, "Hold")
        self.assertTrue(-0.2 < result.weighted_score < 0.2)

    def test_positive_signals_raise_buy_probability(self) -> None:
        result = self.analyzer.evaluate(
            risk_tolerance=RiskTolerance.moderate,
            signals=[
                Signal(label="Market sentiment", value=0.7, rationale=""),
                Signal(label="Social sentiment", value=0.6, rationale=""),
                Signal(label="Research confidence", value=0.9, rationale=""),
            ],
            sources=[
                Source(title="s1", url="https://example.com/1", snippet="x", source_type="web"),
                Source(title="s2", url="https://example.com/2", snippet="x", source_type="web"),
            ],
        )
        self.assertEqual(result.recommendation, "Buy")
        self.assertGreaterEqual(result.confidence_pct, 35)
