from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.models import (
    AdvancedFinancialForecastAssumption,
    AdvancedFinancialModelInput,
    FinancialModelInput,
)
from app.services.financial_model import FinancialForecastPoint, FinancialModelResult


@dataclass
class _BalanceState:
    year: int
    cash: float
    debt: float
    retained_earnings: float
    share_capital: float
    ppe_net: float
    other_assets: float
    other_liabilities: float
    ar: float
    inventory: float
    ap: float


class AdvancedFinancialModelEngine:
    """Run a more explicit linked 3-statement forecast with schedule assumptions."""

    def evaluate(
        self,
        advanced_input: AdvancedFinancialModelInput | None,
        fallback_input: FinancialModelInput | None = None,
    ) -> FinancialModelResult:
        """
        Purpose: Build base/bull/bear forecasts using explicit financial schedules.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `advanced_input` (AdvancedFinancialModelInput | None): Input parameter used by this function.
        - `fallback_input` (FinancialModelInput | None): Input parameter used by this function.
        Returns:
        - `FinancialModelResult`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `evaluate(advanced_input=..., fallback_input=...)`
        """
        if advanced_input is None:
            if fallback_input is None or not fallback_input.periods:
                return FinancialModelResult(
                    is_valid=False,
                    issues=["Advanced engine enabled but no advanced_financial_input provided."],
                    historical_summary="No advanced financial input supplied.",
                    base_case=[],
                    bull_case=[],
                    bear_case=[],
                    weighted_score=0.0,
                    recommendation="Hold",
                    confidence_pct=35,
                )
            advanced_input = self._from_basic_input(fallback_input)

        assumptions = sorted(advanced_input.forecast, key=lambda row: row.year)
        if not assumptions:
            return FinancialModelResult(
                is_valid=False,
                issues=["Advanced financial forecast assumptions are empty."],
                historical_summary="No forecast assumptions provided.",
                base_case=[],
                bull_case=[],
                bear_case=[],
                weighted_score=0.0,
                recommendation="Hold",
                confidence_pct=35,
            )

        base_state = self._initial_state_from_input(advanced_input)
        issues: List[str] = []
        base = self._project_case(base_state, assumptions, issues)
        bull = self._project_case(base_state, [self._to_bull(a) for a in assumptions], issues)
        bear = self._project_case(base_state, [self._to_bear(a) for a in assumptions], issues)

        score = 0.0
        if base and bull and bear:
            expected_fcf = (bull[-1].free_cash_flow * 0.30) + (base[-1].free_cash_flow * 0.50) + (bear[-1].free_cash_flow * 0.20)
            baseline = max(1.0, abs(base[0].free_cash_flow))
            score = (expected_fcf - baseline) / baseline

        if score >= 0.20:
            recommendation = "Buy"
        elif score <= -0.10:
            recommendation = "Sell"
        else:
            recommendation = "Hold"

        confidence = max(35, min(92, 64 + (4 if len(assumptions) >= 3 else 0) - (len(issues) * 4)))
        summary = (
            f"Advanced linked engine periods={len(assumptions)}, "
            f"starting_year={base_state.year}, starting_cash={base_state.cash:.2f}, "
            f"starting_debt={base_state.debt:.2f}"
        )
        return FinancialModelResult(
            is_valid=len(issues) == 0,
            issues=issues,
            historical_summary=summary,
            base_case=base,
            bull_case=bull,
            bear_case=bear,
            weighted_score=round(score, 3),
            recommendation=recommendation,
            confidence_pct=confidence,
        )

    def _project_case(
        self,
        initial_state: _BalanceState,
        assumptions: List[AdvancedFinancialForecastAssumption],
        issues: List[str],
    ) -> List[FinancialForecastPoint]:
        """
        Purpose: Project one scenario case with schedule-level accounting linkages.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `initial_state` (_BalanceState): Input parameter used by this function.
        - `assumptions` (List[AdvancedFinancialForecastAssumption]): Input parameter used by this function.
        - `issues` (List[str]): Input parameter used by this function.
        Returns:
        - `List[FinancialForecastPoint]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_project_case(initial_state=..., assumptions=..., issues=...)`
        """
        state = _BalanceState(**initial_state.__dict__)
        points: List[FinancialForecastPoint] = []
        prev_nwc = state.ar + state.inventory - state.ap
        for row in assumptions:
            revenue = max(0.0, (row.volume * row.price) + row.other_revenue)
            gross_profit = revenue * row.gross_margin
            opex = revenue * row.opex_ratio
            ebitda = gross_profit - opex

            depreciation = max(0.0, state.ppe_net * row.depreciation_pct_ppe)
            ebit = ebitda - depreciation
            interest_expense = max(0.0, state.debt * row.interest_rate)
            pre_tax_income = ebit - interest_expense
            tax_expense = max(0.0, pre_tax_income * row.tax_rate)
            net_income = pre_tax_income - tax_expense

            ar = revenue * (row.ar_days / 365.0)
            inventory = revenue * (row.inventory_days / 365.0)
            ap = revenue * (row.ap_days / 365.0)
            nwc = ar + inventory - ap
            delta_nwc = nwc - prev_nwc
            prev_nwc = nwc

            capex = max(0.0, revenue * row.capex_pct_revenue)
            operating_cash_flow = net_income + depreciation - delta_nwc
            free_cash_flow = operating_cash_flow - capex

            debt = max(0.0, state.debt + row.new_borrowing - row.debt_repayment)
            cash = state.cash + free_cash_flow + row.new_borrowing - row.debt_repayment - row.dividends
            ppe_net = max(0.0, state.ppe_net + capex - depreciation)
            retained_earnings = state.retained_earnings + net_income - row.dividends

            total_assets = cash + ar + inventory + ppe_net + state.other_assets
            total_liabilities = debt + ap + state.other_liabilities
            total_equity = state.share_capital + retained_earnings
            gap = total_assets - (total_liabilities + total_equity)
            if abs(gap) > max(1.0, abs(total_assets) * 0.02):
                issues.append(f"Forecast year {row.year} balance gap={gap:.2f}")

            points.append(
                FinancialForecastPoint(
                    year=row.year,
                    revenue=round(revenue, 2),
                    net_income=round(net_income, 2),
                    free_cash_flow=round(free_cash_flow, 2),
                    ebitda=round(ebitda, 2),
                    total_assets=round(total_assets, 2),
                    total_liabilities=round(total_liabilities, 2),
                    total_equity=round(total_equity, 2),
                    cash=round(cash, 2),
                    debt=round(debt, 2),
                    operating_cash_flow=round(operating_cash_flow, 2),
                    capex=round(capex, 2),
                    depreciation=round(depreciation, 2),
                    tax_expense=round(tax_expense, 2),
                    working_capital=round(nwc, 2),
                    retained_earnings=round(retained_earnings, 2),
                    balance_check_gap=round(gap, 2),
                    interest_expense=round(interest_expense, 2),
                )
            )

            state = _BalanceState(
                year=row.year,
                cash=cash,
                debt=debt,
                retained_earnings=retained_earnings,
                share_capital=state.share_capital,
                ppe_net=ppe_net,
                other_assets=state.other_assets,
                other_liabilities=state.other_liabilities,
                ar=ar,
                inventory=inventory,
                ap=ap,
            )
        return points

    @staticmethod
    def _initial_state_from_input(advanced_input: AdvancedFinancialModelInput) -> _BalanceState:
        """
        Purpose: Convert validated initial state payload to mutable balance state.
        Args/Params:
        - `advanced_input` (AdvancedFinancialModelInput): Input parameter used by this function.
        Returns:
        - `_BalanceState`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_initial_state_from_input(advanced_input=...)`
        """
        init = advanced_input.initial_state
        return _BalanceState(
            year=init.year,
            cash=init.cash,
            debt=init.debt,
            retained_earnings=init.retained_earnings,
            share_capital=init.share_capital,
            ppe_net=init.ppe_net,
            other_assets=init.other_assets,
            other_liabilities=init.other_liabilities,
            ar=0.0,
            inventory=0.0,
            ap=0.0,
        )

    @staticmethod
    def _to_bull(row: AdvancedFinancialForecastAssumption) -> AdvancedFinancialForecastAssumption:
        """
        Purpose: Apply modest upside assumption adjustments for bull case.
        Args/Params:
        - `row` (AdvancedFinancialForecastAssumption): Input parameter used by this function.
        Returns:
        - `AdvancedFinancialForecastAssumption`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_to_bull(row=...)`
        """
        data = row.model_dump()
        data["volume"] = data["volume"] * 1.05
        data["price"] = data["price"] * 1.02
        data["gross_margin"] = min(0.95, data["gross_margin"] + 0.02)
        data["opex_ratio"] = max(0.0, data["opex_ratio"] - 0.01)
        data["tax_rate"] = max(0.0, data["tax_rate"] - 0.01)
        data["interest_rate"] = max(0.0, data["interest_rate"] - 0.005)
        return AdvancedFinancialForecastAssumption(**data)

    @staticmethod
    def _to_bear(row: AdvancedFinancialForecastAssumption) -> AdvancedFinancialForecastAssumption:
        """
        Purpose: Apply modest downside assumption adjustments for bear case.
        Args/Params:
        - `row` (AdvancedFinancialForecastAssumption): Input parameter used by this function.
        Returns:
        - `AdvancedFinancialForecastAssumption`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_to_bear(row=...)`
        """
        data = row.model_dump()
        data["volume"] = data["volume"] * 0.94
        data["price"] = data["price"] * 0.98
        data["gross_margin"] = max(-1.0, data["gross_margin"] - 0.03)
        data["opex_ratio"] = min(1.0, data["opex_ratio"] + 0.02)
        data["tax_rate"] = min(0.60, data["tax_rate"] + 0.01)
        data["interest_rate"] = min(1.0, data["interest_rate"] + 0.007)
        data["capex_pct_revenue"] = max(0.0, data["capex_pct_revenue"] - 0.01)
        return AdvancedFinancialForecastAssumption(**data)

    @staticmethod
    def _from_basic_input(model_input: FinancialModelInput) -> AdvancedFinancialModelInput:
        """
        Purpose: Create conservative default advanced assumptions from basic financial input.
        Args/Params:
        - `model_input` (FinancialModelInput): Input parameter used by this function.
        Returns:
        - `AdvancedFinancialModelInput`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_from_basic_input(model_input=...)`
        """
        periods = sorted(model_input.periods, key=lambda p: p.year)
        last = periods[-1]
        volume = max(1.0, last.revenue / 100.0)
        initial = {
            "year": last.year,
            "cash": last.cash,
            "debt": last.debt,
            "retained_earnings": max(0.0, last.total_equity * 0.7),
            "share_capital": max(0.0, last.total_equity * 0.3),
            "ppe_net": max(0.0, last.total_assets * 0.35),
            "other_assets": max(0.0, last.total_assets * 0.20),
            "other_liabilities": max(0.0, last.total_liabilities * 0.25),
            "shares_outstanding": 1.0,
        }
        assumptions: List[dict] = []
        growth = 0.06
        for idx in range(1, model_input.forecast_years + 1):
            assumptions.append(
                {
                    "year": last.year + idx,
                    "volume": round(volume * ((1 + growth) ** idx), 3),
                    "price": 100.0,
                    "other_revenue": 0.0,
                    "gross_margin": 0.58,
                    "opex_ratio": 0.32,
                    "ar_days": 45.0,
                    "inventory_days": 35.0,
                    "ap_days": 30.0,
                    "capex_pct_revenue": 0.08,
                    "depreciation_pct_ppe": 0.12,
                    "new_borrowing": 0.0,
                    "debt_repayment": min(last.debt * 0.08, last.debt),
                    "interest_rate": 0.04,
                    "tax_rate": 0.21,
                    "dividends": 0.0,
                }
            )
        return AdvancedFinancialModelInput(
            initial_state=initial,
            forecast=assumptions,
        )

