from pydantic import BaseModel

from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


class SimulationDetail(BaseModel):
    strategy: str
    url: str
    market_p_yes: float
    agent_p_yes: float
    agent_conf: float
    org_bet: float
    sim_bet: float
    org_dir: bool
    sim_dir: bool
    org_profit: float
    sim_profit: float
    timestamp: DatetimeUTC


class SharpeOutput(BaseModel):
    annualized_volatility: float
    mean_daily_return: float
    annualized_sharpe_ratio: float
