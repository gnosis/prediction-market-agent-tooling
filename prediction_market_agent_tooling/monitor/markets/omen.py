import typing as t

from google.cloud.functions_v2.types.functions import Function
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.constants import MARKET_TYPE_KEY
from prediction_market_agent_tooling.gtypes import ChecksumAddress, DatetimeWithTimezone
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
)


class DeployedOmenAgent(DeployedAgent):
    omen_public_key: ChecksumAddress

    def get_resolved_bets(self) -> list[ResolvedBet]:
        # For monitoring of deployed agent, return only resolved bets with valid answer.
        subgraph_handler = OmenSubgraphHandler()
        bets = subgraph_handler.get_resolved_bets_with_valid_answer(
            better_address=self.omen_public_key,
            start_time=self.start_time,
            end_time=self.end_time,
        )
        return [b.to_generic_resolved_bet() for b in bets]

    @staticmethod
    def from_api_keys(
        name: str,
        deployableagent_class_name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedOmenAgent":
        return DeployedOmenAgent(
            name=name,
            deployableagent_class_name=deployableagent_class_name,
            start_time=start_time,
            omen_public_key=api_keys.bet_from_address,
        )

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: DatetimeWithTimezone
    ) -> list[DeployedAgent]:
        return [
            DeployedOmenAgent(
                name=f"OmenAgent-{idx}",
                deployableagent_class_name="deployableagent_class_name",
                start_time=start_time,
                omen_public_key=Web3.to_checksum_address(omen_public_key),
            )
            for idx, omen_public_key in enumerate(settings.OMEN_PUBLIC_KEYS)
        ]

    @classmethod
    def from_all_gcp_functions(
        cls: t.Type["DeployedOmenAgent"],
        filter_: t.Callable[[Function], bool] = lambda function: function.labels[
            MARKET_TYPE_KEY
        ]
        == MarketType.OMEN.value,
    ) -> t.Sequence["DeployedOmenAgent"]:
        return super().from_all_gcp_functions(filter_=filter_)
