import unittest

from app.models import (
    AdvancedFinancialForecastAssumption,
    AdvancedFinancialInitialState,
    AdvancedFinancialModelInput,
    FinancialInputPeriod,
    FinancialModelInput,
)
from app.services.advanced_financial_model import AdvancedFinancialModelEngine


class AdvancedFinancialModelEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = AdvancedFinancialModelEngine()

    def test_evaluate_with_advanced_input_returns_linked_forecasts(self) -> None:
        advanced_input = AdvancedFinancialModelInput(
            initial_state=AdvancedFinancialInitialState(
                year=2024,
                cash=350,
                debt=520,
                retained_earnings=1400,
                share_capital=700,
                ppe_net=900,
                other_assets=450,
                other_liabilities=280,
                shares_outstanding=2500,
            ),
            forecast=[
                AdvancedFinancialForecastAssumption(year=2025, volume=15, price=100, other_revenue=30),
                AdvancedFinancialForecastAssumption(year=2026, volume=16, price=102, other_revenue=32),
                AdvancedFinancialForecastAssumption(year=2027, volume=17, price=104, other_revenue=35),
            ],
        )

        result = self.engine.evaluate(advanced_input=advanced_input)
        self.assertEqual(len(result.base_case), 3)
        self.assertEqual(len(result.bull_case), 3)
        self.assertEqual(len(result.bear_case), 3)
        self.assertIn(result.recommendation, {"Buy", "Hold", "Sell"})
        self.assertTrue(hasattr(result.base_case[0], "working_capital"))

    def test_evaluate_falls_back_to_basic_input_when_advanced_missing(self) -> None:
        basic_input = FinancialModelInput(
            periods=[
                FinancialInputPeriod(
                    year=2022,
                    revenue=1000,
                    net_income=120,
                    total_assets=2000,
                    total_liabilities=900,
                    total_equity=1100,
                    cash=220,
                    operating_cash_flow=180,
                    capex=70,
                    debt=500,
                ),
                FinancialInputPeriod(
                    year=2023,
                    revenue=1100,
                    net_income=140,
                    total_assets=2150,
                    total_liabilities=950,
                    total_equity=1200,
                    cash=245,
                    operating_cash_flow=205,
                    capex=78,
                    debt=470,
                ),
                FinancialInputPeriod(
                    year=2024,
                    revenue=1250,
                    net_income=170,
                    total_assets=2320,
                    total_liabilities=1000,
                    total_equity=1320,
                    cash=280,
                    operating_cash_flow=245,
                    capex=90,
                    debt=440,
                ),
            ],
            forecast_years=3,
        )
        result = self.engine.evaluate(advanced_input=None, fallback_input=basic_input)
        self.assertEqual(len(result.base_case), 3)
        self.assertIn(result.recommendation, {"Buy", "Hold", "Sell"})

