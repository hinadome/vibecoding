from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskTolerance(str, Enum):
    conservative = "conservative"
    moderate = "moderate"
    aggressive = "aggressive"


class Source(BaseModel):
    title: str
    url: str
    snippet: str
    source_type: str = "web"


class Signal(BaseModel):
    label: str
    value: float
    rationale: str


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8000)


class MCPToolCall(BaseModel):
    server: str = Field(..., min_length=1, max_length=128)
    tool: str = Field(..., min_length=1, max_length=128)
    arguments: Dict[str, Any] = Field(default_factory=dict)


class A2AAgentCall(BaseModel):
    agent: str = Field(..., min_length=1, max_length=128)
    task: str = Field(..., min_length=1, max_length=4000)
    context: Dict[str, Any] = Field(default_factory=dict)


class FinancialInputPeriod(BaseModel):
    year: int = Field(..., ge=1900, le=2200)
    revenue: float
    net_income: float
    total_assets: float
    total_liabilities: float
    total_equity: float
    cash: float = 0.0
    operating_cash_flow: float = 0.0
    capex: float = 0.0
    debt: float = 0.0


class FinancialModelInput(BaseModel):
    periods: List[FinancialInputPeriod] = Field(default_factory=list)
    forecast_years: int = Field(default=3, ge=1, le=5)


class AdvancedFinancialInitialState(BaseModel):
    year: int = Field(..., ge=1900, le=2200)
    cash: float = 0.0
    debt: float = 0.0
    retained_earnings: float = 0.0
    share_capital: float = 0.0
    ppe_net: float = 0.0
    other_assets: float = 0.0
    other_liabilities: float = 0.0
    shares_outstanding: float = Field(default=1.0, gt=0.0)


class AdvancedFinancialForecastAssumption(BaseModel):
    year: int = Field(..., ge=1900, le=2200)
    volume: float = 0.0
    price: float = 0.0
    other_revenue: float = 0.0
    gross_margin: float = Field(default=0.55, ge=-1.0, le=1.0)
    opex_ratio: float = Field(default=0.30, ge=-1.0, le=1.0)
    ar_days: float = Field(default=45.0, ge=0.0, le=365.0)
    inventory_days: float = Field(default=35.0, ge=0.0, le=365.0)
    ap_days: float = Field(default=30.0, ge=0.0, le=365.0)
    capex_pct_revenue: float = Field(default=0.08, ge=0.0, le=2.0)
    depreciation_pct_ppe: float = Field(default=0.12, ge=0.0, le=1.0)
    new_borrowing: float = 0.0
    debt_repayment: float = 0.0
    interest_rate: float = Field(default=0.04, ge=0.0, le=1.0)
    tax_rate: float = Field(default=0.21, ge=0.0, le=0.60)
    dividends: float = 0.0


class AdvancedFinancialModelInput(BaseModel):
    initial_state: AdvancedFinancialInitialState
    forecast: List[AdvancedFinancialForecastAssumption] = Field(default_factory=list)


class ValuationInput(BaseModel):
    current_price: float = Field(default=0.0, ge=0.0)
    shares_outstanding: float = Field(default=1.0, gt=0.0)
    net_debt: float = 0.0
    wacc: float = Field(default=0.10, gt=0.0, lt=0.30)
    terminal_growth: float = Field(default=0.03, ge=0.0, lt=0.10)
    terminal_fcf_multiple: float = Field(default=18.0, gt=0.0, lt=100.0)
    peer_pe: float = Field(default=20.0, gt=0.0, lt=200.0)
    peer_ev_ebitda: float = Field(default=14.0, gt=0.0, lt=200.0)
    peer_p_fcf: float = Field(default=18.0, gt=0.0, lt=200.0)
    peer_ev_fcf: float = Field(default=22.0, gt=0.0, lt=200.0)


class ResearchRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=12)
    company_name: Optional[str] = Field(default=None, max_length=128)
    market: str = Field(default="US", max_length=32)
    question: Optional[str] = Field(default=None, max_length=2000)
    horizon_days: int = Field(default=90, ge=1, le=1825)
    risk_tolerance: RiskTolerance = RiskTolerance.moderate
    bypass_web_search: bool = True
    use_query_decomposition: bool = False
    use_primary_source_ingestion: bool = False
    use_financial_model_rebuild: bool = False
    use_advanced_financial_engine: bool = False
    use_structured_valuation: bool = False
    chat_history: List[ChatTurn] = Field(default_factory=list)
    attachment_texts: List[str] = Field(default_factory=list)
    mcp_calls: List[MCPToolCall] = Field(default_factory=list)
    a2a_calls: List[A2AAgentCall] = Field(default_factory=list)
    financial_model_input: Optional[FinancialModelInput] = None
    advanced_financial_input: Optional[AdvancedFinancialModelInput] = None
    valuation_input: Optional[ValuationInput] = None


class ValuationSensitivityPoint(BaseModel):
    wacc: float
    terminal_growth: float
    implied_price: float


class ValuationSummary(BaseModel):
    dcf_equity_value: float
    dcf_price_per_share: float
    comps_price_per_share: float
    blended_target_price: float
    bull_target_price: float = 0.0
    base_target_price: float = 0.0
    bear_target_price: float = 0.0
    scenario_weighted_target_price: float = 0.0
    scenario_bull_weight: float = 0.0
    scenario_base_weight: float = 0.0
    scenario_bear_weight: float = 0.0
    ev_ebitda_price_per_share: float = 0.0
    p_fcf_price_per_share: float = 0.0
    upside_pct: float
    recommendation: str
    confidence_pct: int
    assumptions: Dict[str, float] = Field(default_factory=dict)
    sensitivity_grid: List[ValuationSensitivityPoint] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    generated_at: str
    markdown: str
    signals: List[Signal]
    sources: List[Source]
    valuation: Optional[ValuationSummary] = None

    @classmethod
    def from_payload(
        cls,
        ticker: str,
        company_name: Optional[str],
        markdown: str,
        signals: List[Signal],
        sources: List[Source],
        valuation: Optional[ValuationSummary] = None,
    ) -> "ResearchResponse":
        """
        Purpose: Build a response object and stamp it with current UTC generation time.
        Args/Params:
        - `cls` (Any): Class reference for class-level behavior.
        - `ticker` (str): Input parameter used by this function.
        - `company_name` (Optional[str]): Input parameter used by this function.
        - `markdown` (str): Input parameter used by this function.
        - `signals` (List[Signal]): Input parameter used by this function.
        - `sources` (List[Source]): Input parameter used by this function.
        - `valuation` (Optional[ValuationSummary]): Input parameter used by this function.
        Returns:
        - `'ResearchResponse'`: Function output value.
        Raises/Exceptions:
        - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
        Examples:
        - `from_payload(ticker=..., company_name=..., markdown=..., signals=...)`
        """
        return cls(
            ticker=ticker,
            company_name=company_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            markdown=markdown,
            signals=signals,
            sources=sources,
            valuation=valuation,
        )
