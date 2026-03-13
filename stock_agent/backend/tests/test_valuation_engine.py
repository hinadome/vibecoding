import unittest

from app.models import RiskTolerance, ValuationInput
from app.services.financial_model import FinancialForecastPoint, FinancialModelResult
from app.services.valuation_engine import StructuredValuationEngine


class StructuredValuationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = StructuredValuationEngine()

    def test_evaluate_with_base_case_outputs_target_price(self) -> None:
        model_result = FinancialModelResult(
            is_valid=True,
            issues=[],
            historical_summary="ok",
            base_case=[
                FinancialForecastPoint(year=2025, revenue=1500, net_income=180, free_cash_flow=210),
                FinancialForecastPoint(year=2026, revenue=1650, net_income=210, free_cash_flow=245),
                FinancialForecastPoint(year=2027, revenue=1800, net_income=230, free_cash_flow=275),
            ],
            bull_case=[],
            bear_case=[],
            weighted_score=0.3,
            recommendation="Buy",
            confidence_pct=72,
        )
        valuation_input = ValuationInput(
            current_price=120,
            shares_outstanding=2500,
            net_debt=1000,
            wacc=0.10,
            terminal_growth=0.03,
            terminal_fcf_multiple=18,
            peer_pe=25,
            peer_ev_fcf=21,
        )

        result = self.engine.evaluate(
            model_result=model_result,
            valuation_input=valuation_input,
            risk_tolerance=RiskTolerance.moderate,
        )

        self.assertGreater(result.blended_target_price, 0.0)
        self.assertGreater(result.scenario_weighted_target_price, 0.0)
        self.assertGreater(result.ev_ebitda_price_per_share, 0.0)
        self.assertGreater(result.p_fcf_price_per_share, 0.0)
        self.assertEqual(len(result.sensitivity_grid), 9)
        self.assertIn(result.recommendation, {"Buy", "Hold", "Sell"})

    def test_evaluate_without_forecast_returns_neutral(self) -> None:
        model_result = FinancialModelResult(
            is_valid=False,
            issues=["missing input"],
            historical_summary="none",
            base_case=[],
            bull_case=[],
            bear_case=[],
            weighted_score=0.0,
            recommendation="Hold",
            confidence_pct=35,
        )

        result = self.engine.evaluate(
            model_result=model_result,
            valuation_input=None,
            risk_tolerance=RiskTolerance.moderate,
        )

        self.assertEqual(result.blended_target_price, 0.0)
        self.assertEqual(result.scenario_weighted_target_price, 0.0)
        self.assertEqual(result.upside_pct, 0.0)
        self.assertEqual(result.recommendation, "Hold")
