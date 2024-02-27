import typing as t
from datetime import datetime

from google.cloud.functions_v2.types.functions import Function
from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.deploy.agent import (
    MARKET_TYPE_KEY,
    DeployableAgent,
)
from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.omen import get_bets
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
)


class DeployedOmenAgentParams(BaseModel):
    omen_public_key: ChecksumAddress


class DeployedOmenAgent(DeployedAgent):
    omen_public_key: ChecksumAddress | None = None

    def get_resolved_bets(self) -> list[ResolvedBet]:
        bets = (
            get_bets(
                better_address=self.omen_public_key,
                start_time=self.start_time,
                end_time=self.end_time,
            )
            if self.omen_public_key
            else []
        )
        return [b.to_generic_resolved_bet() for b in bets if b.fpmm.is_resolved]

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: datetime
    ) -> list[DeployedAgent]:
        return [
            DeployedOmenAgent(
                name=f"OmenAgent-{idx}",
                deployableagent_class_name=DeployableAgent.__name__,
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
