import typing as t

from google.cloud.functions_v2.types.functions import Function

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.constants import MARKET_TYPE_KEY
from prediction_market_agent_tooling.gtypes import ChecksumAddress, DatetimeWithTimezone
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.monitor import DeployedAgent


class DeployedPolymarketAgent(DeployedAgent):
    # Note: Public key seems like the right option to identify agent, but as we aren't implementing rest of the logic right now,
    # it might not be the correct one and it's okay to change this (and related stuff) if needed.
    polymarket_public_key: ChecksumAddress

    @property
    def public_id(self) -> str:
        return self.polymarket_public_key

    def get_resolved_bets(self) -> list[ResolvedBet]:
        raise NotImplementedError("TODO: Implement to allow betting on Polymarket.")

    @staticmethod
    def from_api_keys(
        name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedPolymarketAgent":
        return DeployedPolymarketAgent(
            name=name,
            start_time=start_time,
            polymarket_public_key=api_keys.bet_from_address,
        )

    @classmethod
    def from_all_gcp_functions(
        cls: t.Type["DeployedPolymarketAgent"],
        filter_: t.Callable[[Function], bool] = lambda function: function.labels[
            MARKET_TYPE_KEY
        ]
        == MarketType.POLYMARKET.value,
    ) -> t.Sequence["DeployedPolymarketAgent"]:
        return super().from_all_gcp_functions(filter_=filter_)

    @staticmethod
    def get_user_id(api_keys: APIKeys) -> str:
        return api_keys.bet_from_address
