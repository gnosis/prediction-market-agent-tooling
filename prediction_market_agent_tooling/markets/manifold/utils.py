import typing as t

from prediction_market_agent_tooling.gtypes import OutcomeStr
from prediction_market_agent_tooling.markets.data_models import Resolution


def validate_resolution(v: t.Any) -> Resolution:
    if isinstance(v, str):
        return Resolution(outcome=OutcomeStr(v), invalid=False)
    raise ValueError(f"Expected a string, got {v} {type(v)}")
