from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.models import FinancialInputPeriod, FinancialModelInput


@dataclass
class FinancialForecastPoint:
    year: int
    revenue: float
    net_income: float
    free_cash_flow: float
    ebitda: float = 0.0
    total_assets: float = 0.0
    total_liabilities: float = 0.0
    total_equity: float = 0.0
    cash: float = 0.0
    debt: float = 0.0
    operating_cash_flow: float = 0.0
    capex: float = 0.0
    depreciation: float = 0.0
    tax_expense: float = 0.0
    working_capital: float = 0.0
    retained_earnings: float = 0.0
    balance_check_gap: float = 0.0
    interest_expense: float = 0.0


@dataclass
class FinancialModelResult:
    is_valid: bool
    issues: List[str]
    historical_summary: str
    base_case: List[FinancialForecastPoint]
    bull_case: List[FinancialForecastPoint]
    bear_case: List[FinancialForecastPoint]
    weighted_score: float
    recommendation: str
    confidence_pct: int

    def to_prompt_block(self) -> str:
        """
        Purpose: Render financial model result for prompt augmentation.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `to_prompt_block()`
        """
        lines = [
            f"- Model valid: {self.is_valid}",
            f"- Issues: {', '.join(self.issues) if self.issues else 'None'}",
            f"- Historical summary: {self.historical_summary}",
            f"- Weighted model score: {self.weighted_score:.3f}",
            f"- Model recommendation: {self.recommendation} ({self.confidence_pct}% confidence)",
            "- Base case forecast:",
        ]
        lines.extend([self._point_line(point) for point in self.base_case])
        lines.append("- Bull case forecast:")
        lines.extend([self._point_line(point) for point in self.bull_case])
        lines.append("- Bear case forecast:")
        lines.extend([self._point_line(point) for point in self.bear_case])
        return "\n".join(lines)

    @staticmethod
    def _point_line(point: FinancialForecastPoint) -> str:
        """
        Purpose: Convert one forecast point to markdown line.
        Args/Params:
        - `point` (FinancialForecastPoint): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_point_line(point=...)`
        """
        return (
            f"  - {point.year}: revenue={point.revenue:.2f}, "
            f"net_income={point.net_income:.2f}, ebitda={point.ebitda:.2f}, fcf={point.free_cash_flow:.2f}, "
            f"assets={point.total_assets:.2f}, liabilities={point.total_liabilities:.2f}, "
            f"equity={point.total_equity:.2f}"
        )


class FinancialModelRebuilder:
    """Rebuild linked 3-statement style forecasts from historical financial inputs."""

    def evaluate(self, model_input: FinancialModelInput) -> FinancialModelResult:
        """
        Purpose: Validate historical periods and build base/bull/bear linked forecasts.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `model_input` (FinancialModelInput): Input parameter used by this function.
        Returns:
        - `FinancialModelResult`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `evaluate(model_input=...)`
        """
        periods = sorted(model_input.periods, key=lambda item: item.year)
        issues = self._validate_periods(periods)
        if not periods:
            return FinancialModelResult(
                is_valid=False,
                issues=["No financial periods provided."],
                historical_summary="No historical data provided.",
                base_case=[],
                bull_case=[],
                bear_case=[],
                weighted_score=0.0,
                recommendation="Hold",
                confidence_pct=35,
            )

        last = periods[-1]
        growth = self._average_growth(periods)
        margin = self._average_margin(periods)
        ocf_margin = self._average_ocf_margin(periods)
        capex_margin = self._average_capex_margin(periods)
        interest_rate = self._average_interest_rate(periods)

        base_case = self._forecast_linked(
            base=last,
            years=model_input.forecast_years,
            growth=growth,
            margin=margin,
            ocf_margin=ocf_margin,
            capex_margin=capex_margin,
            interest_rate=interest_rate,
        )
        bull_case = self._forecast_linked(
            base=last,
            years=model_input.forecast_years,
            growth=growth + 0.03,
            margin=min(0.40, margin + 0.01),
            ocf_margin=min(0.35, ocf_margin + 0.01),
            capex_margin=min(0.20, capex_margin + 0.005),
            interest_rate=max(0.01, interest_rate - 0.005),
        )
        bear_case = self._forecast_linked(
            base=last,
            years=model_input.forecast_years,
            growth=growth - 0.04,
            margin=max(-0.10, margin - 0.015),
            ocf_margin=max(-0.10, ocf_margin - 0.015),
            capex_margin=max(0.01, capex_margin - 0.005),
            interest_rate=min(0.18, interest_rate + 0.01),
        )

        base_last = base_case[-1] if base_case else None
        bull_last = bull_case[-1] if bull_case else None
        bear_last = bear_case[-1] if bear_case else None
        score = 0.0
        if base_last and bull_last and bear_last:
            weighted_fcf = (
                (bull_last.free_cash_flow * 0.30)
                + (base_last.free_cash_flow * 0.50)
                + (bear_last.free_cash_flow * 0.20)
            )
            baseline_fcf = max(1.0, last.operating_cash_flow - abs(last.capex))
            score = (weighted_fcf - baseline_fcf) / baseline_fcf

        if score >= 0.20:
            recommendation = "Buy"
        elif score <= -0.10:
            recommendation = "Sell"
        else:
            recommendation = "Hold"

        confidence = max(35, min(90, 60 + (5 if len(periods) >= 4 else 0) - (len(issues) * 5)))
        summary = (
            f"Periods={len(periods)}, avg_growth={growth:.3f}, avg_net_margin={margin:.3f}, "
            f"avg_ocf_margin={ocf_margin:.3f}, avg_capex_margin={capex_margin:.3f}, interest_rate={interest_rate:.3f}"
        )

        return FinancialModelResult(
            is_valid=len(issues) == 0,
            issues=issues,
            historical_summary=summary,
            base_case=base_case,
            bull_case=bull_case,
            bear_case=bear_case,
            weighted_score=round(score, 3),
            recommendation=recommendation,
            confidence_pct=confidence,
        )

    def _validate_periods(self, periods: List[FinancialInputPeriod]) -> List[str]:
        """
        Purpose: Validate accounting identities and minimum history requirements.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `periods` (List[FinancialInputPeriod]): Input parameter used by this function.
        Returns:
        - `List[str]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_validate_periods(periods=...)`
        """
        issues: List[str] = []
        if len(periods) < 3:
            issues.append("At least 3 historical periods are recommended.")
        for period in periods:
            rhs = period.total_liabilities + period.total_equity
            if abs(period.total_assets - rhs) > max(1.0, abs(period.total_assets) * 0.03):
                issues.append(f"Balance sheet mismatch in {period.year} (assets != liabilities + equity).")
        return issues

    @staticmethod
    def _average_growth(periods: List[FinancialInputPeriod]) -> float:
        """
        Purpose: Compute average revenue growth across adjacent periods.
        Args/Params:
        - `periods` (List[FinancialInputPeriod]): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_average_growth(periods=...)`
        """
        rates: List[float] = []
        for idx in range(1, len(periods)):
            prev = periods[idx - 1].revenue
            curr = periods[idx].revenue
            if prev > 0:
                rates.append((curr - prev) / prev)
        if not rates:
            return 0.05
        return sum(rates) / len(rates)

    @staticmethod
    def _average_margin(periods: List[FinancialInputPeriod]) -> float:
        """
        Purpose: Compute average net income margin from history.
        Args/Params:
        - `periods` (List[FinancialInputPeriod]): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_average_margin(periods=...)`
        """
        margins: List[float] = []
        for period in periods:
            if period.revenue != 0:
                margins.append(period.net_income / period.revenue)
        if not margins:
            return 0.10
        return sum(margins) / len(margins)

    @staticmethod
    def _average_ocf_margin(periods: List[FinancialInputPeriod]) -> float:
        """
        Purpose: Compute average operating cash flow margin from history.
        Args/Params:
        - `periods` (List[FinancialInputPeriod]): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_average_ocf_margin(periods=...)`
        """
        margins: List[float] = []
        for period in periods:
            if period.revenue != 0:
                margins.append(period.operating_cash_flow / period.revenue)
        if not margins:
            return 0.16
        return sum(margins) / len(margins)

    @staticmethod
    def _average_capex_margin(periods: List[FinancialInputPeriod]) -> float:
        """
        Purpose: Compute average capex margin from history.
        Args/Params:
        - `periods` (List[FinancialInputPeriod]): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_average_capex_margin(periods=...)`
        """
        margins: List[float] = []
        for period in periods:
            if period.revenue != 0:
                margins.append(abs(period.capex) / period.revenue)
        if not margins:
            return 0.08
        return sum(margins) / len(margins)

    @staticmethod
    def _average_interest_rate(periods: List[FinancialInputPeriod]) -> float:
        """
        Purpose: Estimate debt interest rate from history.
        Args/Params:
        - `periods` (List[FinancialInputPeriod]): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_average_interest_rate(periods=...)`
        """
        rates: List[float] = []
        for period in periods:
            if period.debt > 0 and period.total_assets > 0:
                proxy = (period.debt / period.total_assets) * 0.04
                rates.append(proxy)
        if not rates:
            return 0.04
        return max(0.01, min(0.18, sum(rates) / len(rates)))

    @staticmethod
    def _forecast_linked(
        base: FinancialInputPeriod,
        years: int,
        growth: float,
        margin: float,
        ocf_margin: float,
        capex_margin: float,
        interest_rate: float,
    ) -> List[FinancialForecastPoint]:
        """
        Purpose: Project linked 3-statement style values with accounting identity tie-out.
        Args/Params:
        - `base` (FinancialInputPeriod): Input parameter used by this function.
        - `years` (int): Input parameter used by this function.
        - `growth` (float): Input parameter used by this function.
        - `margin` (float): Input parameter used by this function.
        - `ocf_margin` (float): Input parameter used by this function.
        - `capex_margin` (float): Input parameter used by this function.
        - `interest_rate` (float): Input parameter used by this function.
        Returns:
        - `List[FinancialForecastPoint]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_forecast_linked(base=..., years=..., growth=..., margin=...)`
        """
        points: List[FinancialForecastPoint] = []
        revenue = base.revenue
        cash = base.cash
        debt = max(0.0, base.debt)
        equity = base.total_equity
        liabilities = base.total_liabilities

        for step in range(1, years + 1):
            revenue = revenue * (1 + growth)
            interest_expense = debt * interest_rate
            net_income = (revenue * margin) - interest_expense
            operating_cash_flow = revenue * ocf_margin
            capex = revenue * capex_margin
            free_cash_flow = operating_cash_flow - capex
            ebitda = net_income + interest_expense

            if free_cash_flow >= 0:
                debt_repay = min(debt, free_cash_flow * 0.35)
                debt = max(0.0, debt - debt_repay)
                cash = cash + free_cash_flow - debt_repay
            else:
                new_borrowing = abs(free_cash_flow) * 0.60
                debt = debt + new_borrowing
                cash = max(0.0, cash + free_cash_flow + new_borrowing)

            equity = equity + net_income
            liabilities = max(0.0, liabilities + (debt - liabilities * 0.02))
            assets = liabilities + equity

            points.append(
                FinancialForecastPoint(
                    year=base.year + step,
                    revenue=round(revenue, 2),
                    net_income=round(net_income, 2),
                    free_cash_flow=round(free_cash_flow, 2),
                    ebitda=round(ebitda, 2),
                    total_assets=round(assets, 2),
                    total_liabilities=round(liabilities, 2),
                    total_equity=round(equity, 2),
                    cash=round(cash, 2),
                    debt=round(debt, 2),
                    operating_cash_flow=round(operating_cash_flow, 2),
                    capex=round(capex, 2),
                    retained_earnings=round(equity, 2),
                    interest_expense=round(interest_expense, 2),
                )
            )
        return points
