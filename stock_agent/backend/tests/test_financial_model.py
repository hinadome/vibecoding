import unittest

from app.models import FinancialInputPeriod, FinancialModelInput
from app.services.financial_model import FinancialModelRebuilder


class FinancialModelRebuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rebuilder = FinancialModelRebuilder()

    def test_rebuild_with_valid_history_produces_forecast(self) -> None:
        model_input = FinancialModelInput(
            periods=[
                FinancialInputPeriod(
                    year=2022,
                    revenue=1000,
                    net_income=120,
                    total_assets=2000,
                    total_liabilities=900,
                    total_equity=1100,
                    cash=200,
                    operating_cash_flow=180,
                    capex=60,
                    debt=500,
                ),
                FinancialInputPeriod(
                    year=2023,
                    revenue=1120,
                    net_income=140,
                    total_assets=2150,
                    total_liabilities=940,
                    total_equity=1210,
                    cash=230,
                    operating_cash_flow=205,
                    capex=70,
                    debt=490,
                ),
                FinancialInputPeriod(
                    year=2024,
                    revenue=1260,
                    net_income=175,
                    total_assets=2330,
                    total_liabilities=980,
                    total_equity=1350,
                    cash=260,
                    operating_cash_flow=245,
                    capex=82,
                    debt=470,
                ),
            ],
            forecast_years=3,
        )
        result = self.rebuilder.evaluate(model_input)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.base_case), 3)
        self.assertIn(result.recommendation, {"Buy", "Hold", "Sell"})

    def test_rebuild_flags_balance_sheet_mismatch(self) -> None:
        model_input = FinancialModelInput(
            periods=[
                FinancialInputPeriod(
                    year=2022,
                    revenue=1000,
                    net_income=120,
                    total_assets=2000,
                    total_liabilities=1200,
                    total_equity=1000,
                ),
                FinancialInputPeriod(
                    year=2023,
                    revenue=1050,
                    net_income=100,
                    total_assets=2100,
                    total_liabilities=1000,
                    total_equity=900,
                ),
                FinancialInputPeriod(
                    year=2024,
                    revenue=1100,
                    net_income=90,
                    total_assets=2200,
                    total_liabilities=1050,
                    total_equity=950,
                ),
            ]
        )
        result = self.rebuilder.evaluate(model_input)
        self.assertFalse(result.is_valid)
        self.assertGreaterEqual(len(result.issues), 1)
