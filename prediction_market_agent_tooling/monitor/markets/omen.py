from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.omen.omen import get_resolved_bets
from prediction_market_agent_tooling.monitor.monitor import DeployedAgent


class DeployedOmenAgent(DeployedAgent):
    wallet_address: str  # TODO conver to checksummed in validator

    def get_resolved_bets(self) -> list[ResolvedBet]:
        bets = get_resolved_bets(
            better_address=self.wallet_address,
            start_time=self.start_time,
            end_time=None,
        )
        return [b.to_generic_resolved_bet() for b in bets]
