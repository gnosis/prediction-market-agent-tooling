from datetime import datetime

from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.omen.omen import get_resolved_omen_bets
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
)


class DeployedOmenAgent(DeployedAgent):
    wallet_address: ChecksumAddress

    def get_resolved_bets(self) -> list[ResolvedBet]:
        bets = get_resolved_omen_bets(
            better_address=self.wallet_address,
            start_time=self.start_time,
            end_time=self.end_time,
        )
        return [b.to_generic_resolved_bet() for b in bets]

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: datetime
    ) -> list[DeployedAgent]:
        if settings.BET_FROM_ADDRESS:
            return [
                DeployedOmenAgent(
                    name="OmenAgent",
                    start_time=start_time,
                    wallet_address=Web3.to_checksum_address(settings.BET_FROM_ADDRESS),
                )
            ]
        else:
            return []
