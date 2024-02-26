from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.manifold.api import (
    get_resolved_manifold_bets,
    manifold_to_generic_resolved_bet,
)
from prediction_market_agent_tooling.monitor.monitor import DeployedAgent, MarketType
from prediction_market_agent_tooling.tools.utils import check_not_none


class DeployedManifoldAgent(DeployedAgent):
    @property
    def manifold_user_id(self) -> str:
        return check_not_none(
            self.monitor_config.manifold_user_id,
            "Agent isn't deployed on Manifold, or the config is missing.",
        )

    def get_resolved_bets(self) -> list[ResolvedBet]:
        manifold_bets = get_resolved_manifold_bets(
            user_id=self.manifold_user_id,
            start_time=self.monitor_config.start_time,
            end_time=None,
        )
        return [manifold_to_generic_resolved_bet(b) for b in manifold_bets]

    @staticmethod
    def get_all_deployed_agents_gcp() -> list["DeployedManifoldAgent"]:
        return [
            DeployedManifoldAgent(**agent.model_dump())
            for agent in DeployedAgent.get_all_deployed_agents_gcp()
            if agent.market_type == MarketType.MANIFOLD
        ]
