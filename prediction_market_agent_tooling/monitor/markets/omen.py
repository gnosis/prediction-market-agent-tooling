from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.omen.omen import get_resolved_bets
from prediction_market_agent_tooling.monitor.monitor import DeployedAgent, MarketType
from prediction_market_agent_tooling.tools.utils import check_not_none


class DeployedOmenAgent(DeployedAgent):
    @property
    def wallet_address(self) -> ChecksumAddress:
        return Web3.to_checksum_address(
            check_not_none(
                self.monitor_config.omen_public_key,
                "Agent isn't deployed on Omen, or the config is missing.",
            )
        )

    def get_resolved_bets(self) -> list[ResolvedBet]:
        bets = get_resolved_bets(
            better_address=self.wallet_address,
            start_time=self.monitor_config.start_time,
            end_time=None,
        )
        return [b.to_generic_resolved_bet() for b in bets]

    @staticmethod
    def get_all_deployed_agents_gcp() -> list["DeployedOmenAgent"]:
        return [
            DeployedOmenAgent(**agent.model_dump())
            for agent in DeployedAgent.get_all_deployed_agents_gcp()
            if agent.market_type == MarketType.OMEN
        ]
