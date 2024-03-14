import typing as t

from google.cloud.functions_v2.types.functions import Function
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.constants import MARKET_TYPE_KEY
from prediction_market_agent_tooling.gtypes import ChecksumAddress, DatetimeWithTimezone
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
)


class DeployedPolymarketAgent(DeployedAgent):
    # Note: Public key seems like the right option to identify agent, but as we aren't implementing rest of the logic right now,
    # it might not be the correct one and it's okay to change this (and related stuff) if needed.
    polymarket_public_key: ChecksumAddress

    def get_resolved_bets(self) -> list[ResolvedBet]:
        raise NotImplementedError(
            "TODO: Not implemented as we aren't planning to bet on Polymarket any time soon."
        )

    @staticmethod
    def from_api_keys(
        name: str,
        deployableagent_class_name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedPolymarketAgent":
        return DeployedPolymarketAgent(
            name=name,
            deployableagent_class_name=deployableagent_class_name,
            start_time=start_time,
            polymarket_public_key=api_keys.bet_from_address,
        )

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: DatetimeWithTimezone
    ) -> list[DeployedAgent]:
        return [
            DeployedPolymarketAgent(
                name=f"PolymarketAgent-{idx}",
                deployableagent_class_name="deployableagent_class_name",
                start_time=start_time,
                polymarket_public_key=Web3.to_checksum_address(polymarket_public_key),
            )
            for idx, polymarket_public_key in enumerate(settings.POLYMARKET_PUBLIC_KEYS)
        ]

    @classmethod
    def from_all_gcp_functions(
        cls: t.Type["DeployedPolymarketAgent"],
        filter_: t.Callable[[Function], bool] = lambda function: function.labels[
            MARKET_TYPE_KEY
        ]
        == MarketType.POLYMARKET.value,
    ) -> t.Sequence["DeployedPolymarketAgent"]:
        return super().from_all_gcp_functions(filter_=filter_)
