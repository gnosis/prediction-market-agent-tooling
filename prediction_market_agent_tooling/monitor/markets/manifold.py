from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.manifold import (
    get_resolved_manifold_bets,
    manifold_to_generic_resolved_bet,
)
from prediction_market_agent_tooling.monitor.monitor import DeployedAgent


class DeployedManifoldAgent(DeployedAgent):
    manifold_user_id: str

    def get_resolved_bets(self) -> list[ResolvedBet]:
        manifold_bets = get_resolved_manifold_bets(
            user_id=self.manifold_user_id,
            start_time=self.start_time,
            end_time=None,
        )
        return [manifold_to_generic_resolved_bet(b) for b in manifold_bets]
