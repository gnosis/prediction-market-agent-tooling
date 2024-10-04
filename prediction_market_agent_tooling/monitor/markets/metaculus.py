import typing as t

from google.cloud.functions_v2.types.functions import Function

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.constants import MARKET_TYPE_KEY
from prediction_market_agent_tooling.gtypes import DatetimeUTC
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.monitor import DeployedAgent


class DeployedMetaculusAgent(DeployedAgent):
    user: int

    @property
    def public_id(self) -> str:
        return str(self.user)

    def get_resolved_bets(self) -> list[ResolvedBet]:
        raise NotImplementedError("TODO: Implement to allow betting on Metaculus.")

    @staticmethod
    def from_api_keys(
        name: str,
        start_time: DatetimeUTC,
        api_keys: APIKeys,
    ) -> "DeployedMetaculusAgent":
        return DeployedMetaculusAgent(
            name=name,
            start_time=start_time,
            user=api_keys.metaculus_user_id,
        )

    @classmethod
    def from_all_gcp_functions(
        cls: t.Type["DeployedMetaculusAgent"],
        filter_: t.Callable[[Function], bool] = lambda function: function.labels[
            MARKET_TYPE_KEY
        ]
        == MarketType.METACULUS.value,
    ) -> t.Sequence["DeployedMetaculusAgent"]:
        return super().from_all_gcp_functions(filter_=filter_)
