from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.models import RiskTolerance, ValuationInput
from app.services.financial_model import FinancialModelResult


@dataclass
class ValuationResult:
    dcf_equity_value: float
    dcf_price_per_share: float
    comps_price_per_share: float
    blended_target_price: float
    bull_target_price: float
    base_target_price: float
    bear_target_price: float
    scenario_weighted_target_price: float
    scenario_bull_weight: float
    scenario_base_weight: float
    scenario_bear_weight: float
    ev_ebitda_price_per_share: float
    p_fcf_price_per_share: float
    upside_pct: float
    recommendation: str
    confidence_pct: int
    assumptions: Dict[str, float]
    sensitivity_grid: List[Dict[str, float]]

    def to_prompt_block(self) -> str:
        """
        Purpose: Render valuation outputs and assumptions for prompt context.
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
            f"- DCF equity value: {self.dcf_equity_value:.2f}",
            f"- DCF implied price/share: {self.dcf_price_per_share:.2f}",
            f"- Relative comps implied price/share: {self.comps_price_per_share:.2f}",
            f"- Blended target price: {self.blended_target_price:.2f}",
            (
                f"- Scenario targets (bull/base/bear): "
                f"{self.bull_target_price:.2f}/{self.base_target_price:.2f}/{self.bear_target_price:.2f}"
            ),
            (
                f"- Scenario-weighted target price: {self.scenario_weighted_target_price:.2f} "
                f"(weights bull/base/bear: {self.scenario_bull_weight:.2f}/"
                f"{self.scenario_base_weight:.2f}/{self.scenario_bear_weight:.2f})"
            ),
            f"- EV/EBITDA implied price/share: {self.ev_ebitda_price_per_share:.2f}",
            f"- P/FCF implied price/share: {self.p_fcf_price_per_share:.2f}",
            f"- Upside vs current price: {self.upside_pct:.2f}%",
            f"- Valuation recommendation: {self.recommendation} ({self.confidence_pct}% confidence)",
            "- Valuation assumptions:",
            (
                f"  - current_price={self.assumptions['current_price']:.2f}, "
                f"shares={self.assumptions['shares_outstanding']:.2f}, "
                f"net_debt={self.assumptions['net_debt']:.2f}, "
                f"wacc={self.assumptions['wacc']:.3f}, "
                f"terminal_growth={self.assumptions['terminal_growth']:.3f}, "
                f"terminal_fcf_multiple={self.assumptions['terminal_fcf_multiple']:.2f}, "
                f"peer_pe={self.assumptions['peer_pe']:.2f}, "
                f"peer_ev_ebitda={self.assumptions['peer_ev_ebitda']:.2f}, "
                f"peer_p_fcf={self.assumptions['peer_p_fcf']:.2f}, "
                f"peer_ev_fcf={self.assumptions['peer_ev_fcf']:.2f}"
            ),
            "- Sensitivity sample (wacc/g -> implied price):",
        ]
        for row in self.sensitivity_grid[:9]:
            lines.append(
                f"  - wacc={row['wacc']:.3f}, g={row['terminal_growth']:.3f}, price={row['implied_price']:.2f}"
            )
        return "\n".join(lines)


class StructuredValuationEngine:
    """Run DCF + relative comps valuation with sensitivity analysis."""

    def evaluate(
        self,
        model_result: FinancialModelResult,
        valuation_input: ValuationInput | None,
        risk_tolerance: RiskTolerance,
    ) -> ValuationResult:
        """
        Purpose: Compute valuation outputs from financial-model projections.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `model_result` (FinancialModelResult): Input parameter used by this function.
        - `valuation_input` (ValuationInput | None): Input parameter used by this function.
        - `risk_tolerance` (RiskTolerance): Input parameter used by this function.
        Returns:
        - `ValuationResult`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `evaluate(model_result=..., valuation_input=..., risk_tolerance=...)`
        """
        assumptions = valuation_input or ValuationInput()
        base_case = model_result.base_case
        if not base_case:
            return ValuationResult(
                dcf_equity_value=0.0,
                dcf_price_per_share=0.0,
                comps_price_per_share=0.0,
                blended_target_price=0.0,
                bull_target_price=0.0,
                base_target_price=0.0,
                bear_target_price=0.0,
                scenario_weighted_target_price=0.0,
                scenario_bull_weight=0.0,
                scenario_base_weight=0.0,
                scenario_bear_weight=0.0,
                ev_ebitda_price_per_share=0.0,
                p_fcf_price_per_share=0.0,
                upside_pct=0.0,
                recommendation="Hold",
                confidence_pct=35,
                assumptions=assumptions.model_dump(),
                sensitivity_grid=[],
            )

        scenario_targets = {
            "base": self._scenario_target_price(base_case, assumptions),
            "bull": self._scenario_target_price(model_result.bull_case or base_case, assumptions),
            "bear": self._scenario_target_price(model_result.bear_case or base_case, assumptions),
        }
        base_target = scenario_targets["base"]
        bull_target = scenario_targets["bull"]
        bear_target = scenario_targets["bear"]
        bull_w, base_w, bear_w = self._weights_for_risk(risk_tolerance)
        scenario_weighted_target = (bull_target["blended"] * bull_w) + (base_target["blended"] * base_w) + (
            bear_target["blended"] * bear_w
        )

        dcf_equity = base_target["dcf_equity"]
        dcf_price = base_target["dcf_price"]
        comps_price = base_target["comps_price"]
        blended = base_target["blended"]
        upside_pct = 0.0
        if assumptions.current_price > 0:
            upside_pct = ((scenario_weighted_target - assumptions.current_price) / assumptions.current_price) * 100

        rec = self._recommendation(upside_pct=upside_pct, risk_tolerance=risk_tolerance)
        fcf_values = [max(-1e9, min(1e9, point.free_cash_flow)) for point in base_case]
        confidence = self._confidence(
            model_valid=model_result.is_valid,
            sensitivity_spread=self._sensitivity_spread(
                assumptions=assumptions,
                fcf_values=fcf_values,
            ),
        )
        return ValuationResult(
            dcf_equity_value=round(dcf_equity, 2),
            dcf_price_per_share=round(dcf_price, 2),
            comps_price_per_share=round(comps_price, 2),
            blended_target_price=round(blended, 2),
            bull_target_price=round(bull_target["blended"], 2),
            base_target_price=round(base_target["blended"], 2),
            bear_target_price=round(bear_target["blended"], 2),
            scenario_weighted_target_price=round(scenario_weighted_target, 2),
            scenario_bull_weight=round(bull_w, 3),
            scenario_base_weight=round(base_w, 3),
            scenario_bear_weight=round(bear_w, 3),
            ev_ebitda_price_per_share=round(base_target["ev_ebitda_price"], 2),
            p_fcf_price_per_share=round(base_target["p_fcf_price"], 2),
            upside_pct=round(upside_pct, 2),
            recommendation=rec,
            confidence_pct=confidence,
            assumptions=assumptions.model_dump(),
            sensitivity_grid=self._sensitivity_grid(assumptions, fcf_values),
        )

    def _scenario_target_price(
        self,
        case_points: List,
        assumptions: ValuationInput,
    ) -> Dict[str, float]:
        """
        Purpose: Compute DCF/comps/blended price for one scenario case.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `case_points` (List): Input parameter used by this function.
        - `assumptions` (ValuationInput): Input parameter used by this function.
        Returns:
        - `Dict[str, float]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_scenario_target_price(case_points=..., assumptions=...)`
        """
        points = case_points or []
        if not points:
            return {
                "dcf_equity": 0.0,
                "dcf_price": 0.0,
                "comps_price": 0.0,
                "blended": 0.0,
                "ev_ebitda_price": 0.0,
                "p_fcf_price": 0.0,
            }

        fcf_values = [max(-1e9, min(1e9, point.free_cash_flow)) for point in points]
        dcf_enterprise = self._discount_cash_flows(
            fcf_values=fcf_values,
            wacc=assumptions.wacc,
            terminal_growth=assumptions.terminal_growth,
            terminal_multiple=assumptions.terminal_fcf_multiple,
        )
        dcf_equity = dcf_enterprise - assumptions.net_debt
        dcf_price = dcf_equity / assumptions.shares_outstanding

        terminal_point = points[-1]
        eps = terminal_point.net_income / assumptions.shares_outstanding
        pe_price = eps * assumptions.peer_pe

        terminal_fcf = terminal_point.free_cash_flow
        ev_fcf_price = ((terminal_fcf * assumptions.peer_ev_fcf) - assumptions.net_debt) / assumptions.shares_outstanding
        p_fcf_price = (terminal_fcf / assumptions.shares_outstanding) * assumptions.peer_p_fcf
        ebitda = self._point_ebitda(terminal_point)
        ev_ebitda_price = ((ebitda * assumptions.peer_ev_ebitda) - assumptions.net_debt) / assumptions.shares_outstanding

        comps_price = (pe_price + ev_fcf_price + p_fcf_price + ev_ebitda_price) / 4.0
        blended = (dcf_price * 0.6) + (comps_price * 0.4)
        return {
            "dcf_equity": dcf_equity,
            "dcf_price": dcf_price,
            "comps_price": comps_price,
            "blended": blended,
            "ev_ebitda_price": ev_ebitda_price,
            "p_fcf_price": p_fcf_price,
        }

    @staticmethod
    def _point_ebitda(point) -> float:
        """
        Purpose: Resolve EBITDA from point fields with fallback approximation.
        Args/Params:
        - `point` (Any): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_point_ebitda(point=...)`
        """
        direct = float(getattr(point, "ebitda", 0.0) or 0.0)
        if abs(direct) > 1e-9:
            return direct
        net_income = float(getattr(point, "net_income", 0.0) or 0.0)
        interest = float(getattr(point, "interest_expense", 0.0) or 0.0)
        tax = float(getattr(point, "tax_expense", 0.0) or 0.0)
        depreciation = float(getattr(point, "depreciation", 0.0) or 0.0)
        return net_income + interest + tax + depreciation

    def _discount_cash_flows(
        self,
        fcf_values: List[float],
        wacc: float,
        terminal_growth: float,
        terminal_multiple: float,
    ) -> float:
        """
        Purpose: Compute enterprise value using blended perpetuity and terminal multiple.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `fcf_values` (List[float]): Input parameter used by this function.
        - `wacc` (float): Input parameter used by this function.
        - `terminal_growth` (float): Input parameter used by this function.
        - `terminal_multiple` (float): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_discount_cash_flows(fcf_values=..., wacc=..., terminal_growth=..., terminal_multiple=...)`
        """
        pv = 0.0
        for idx, value in enumerate(fcf_values, start=1):
            pv += value / ((1 + wacc) ** idx)

        terminal_fcf = fcf_values[-1] * (1 + terminal_growth)
        denominator = max(0.01, wacc - terminal_growth)
        perpetuity_terminal = terminal_fcf / denominator
        multiple_terminal = fcf_values[-1] * terminal_multiple
        blended_terminal = (perpetuity_terminal * 0.6) + (multiple_terminal * 0.4)
        terminal_pv = blended_terminal / ((1 + wacc) ** len(fcf_values))
        return pv + terminal_pv

    def _sensitivity_grid(self, assumptions: ValuationInput, fcf_values: List[float]) -> List[Dict[str, float]]:
        """
        Purpose: Generate a small sensitivity grid over WACC and terminal growth.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `assumptions` (ValuationInput): Input parameter used by this function.
        - `fcf_values` (List[float]): Input parameter used by this function.
        Returns:
        - `List[Dict[str, float]]`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_sensitivity_grid(assumptions=..., fcf_values=...)`
        """
        wacc_values = [
            max(0.05, assumptions.wacc - 0.02),
            assumptions.wacc,
            min(0.20, assumptions.wacc + 0.02),
        ]
        growth_values = [
            max(0.00, assumptions.terminal_growth - 0.01),
            assumptions.terminal_growth,
            min(0.08, assumptions.terminal_growth + 0.01),
        ]
        rows: List[Dict[str, float]] = []
        for wacc in wacc_values:
            for growth in growth_values:
                ev = self._discount_cash_flows(
                    fcf_values=fcf_values,
                    wacc=wacc,
                    terminal_growth=growth,
                    terminal_multiple=assumptions.terminal_fcf_multiple,
                )
                eq = ev - assumptions.net_debt
                rows.append(
                    {
                        "wacc": round(wacc, 4),
                        "terminal_growth": round(growth, 4),
                        "implied_price": round(eq / assumptions.shares_outstanding, 2),
                    }
                )
        return rows

    def _sensitivity_spread(self, assumptions: ValuationInput, fcf_values: List[float]) -> float:
        """
        Purpose: Return spread between low/high implied prices from sensitivity grid.
        Args/Params:
        - `self` (Any): Instance of the containing class.
        - `assumptions` (ValuationInput): Input parameter used by this function.
        - `fcf_values` (List[float]): Input parameter used by this function.
        Returns:
        - `float`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_sensitivity_spread(assumptions=..., fcf_values=...)`
        """
        grid = self._sensitivity_grid(assumptions, fcf_values)
        if not grid:
            return 0.0
        prices = [row["implied_price"] for row in grid]
        return max(prices) - min(prices)

    @staticmethod
    def _recommendation(upside_pct: float, risk_tolerance: RiskTolerance) -> str:
        """
        Purpose: Map valuation upside to recommendation with risk-profile sensitivity.
        Args/Params:
        - `upside_pct` (float): Input parameter used by this function.
        - `risk_tolerance` (RiskTolerance): Input parameter used by this function.
        Returns:
        - `str`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_recommendation(upside_pct=..., risk_tolerance=...)`
        """
        buy_threshold = 10.0
        sell_threshold = -12.0
        if risk_tolerance == RiskTolerance.aggressive:
            buy_threshold = 7.0
        elif risk_tolerance == RiskTolerance.conservative:
            buy_threshold = 12.0
            sell_threshold = -8.0
        if upside_pct >= buy_threshold:
            return "Buy"
        if upside_pct <= sell_threshold:
            return "Sell"
        return "Hold"

    @staticmethod
    def _weights_for_risk(risk_tolerance: RiskTolerance) -> tuple[float, float, float]:
        """
        Purpose: Return bull/base/bear scenario weights by risk profile.
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
    def _confidence(model_valid: bool, sensitivity_spread: float) -> int:
        """
        Purpose: Estimate valuation confidence from model validity and sensitivity stability.
        Args/Params:
        - `model_valid` (bool): Input parameter used by this function.
        - `sensitivity_spread` (float): Input parameter used by this function.
        Returns:
        - `int`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `_confidence(model_valid=..., sensitivity_spread=...)`
        """
        base = 70 if model_valid else 45
        penalty = min(25, int(sensitivity_spread / 5))
        return max(35, min(92, base - penalty))
