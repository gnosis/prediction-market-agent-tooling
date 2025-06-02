import typing as t

from prediction_market_agent_tooling.gtypes import OutcomeStr
from prediction_market_agent_tooling.markets.data_models import Resolution

MANIFOLD_CANCEL_OUTCOME = "CANCEL"


def validate_manifold_resolution(v: t.Any) -> Resolution:
    if isinstance(v, str):
        return (
            Resolution(outcome=OutcomeStr(v), invalid=False)
            if v != MANIFOLD_CANCEL_OUTCOME
            else Resolution(outcome=None, invalid=True)
        )
    raise ValueError(f"Expected a string, got {v} {type(v)}")
