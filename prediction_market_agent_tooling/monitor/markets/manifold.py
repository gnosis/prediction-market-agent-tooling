from datetime import datetime

from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.manifold.api import (
    get_authenticated_user,
    get_resolved_manifold_bets,
    manifold_to_generic_resolved_bet,
)
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
)


class DeployedManifoldAgent(DeployedAgent):
    manifold_user_id: str

    def get_resolved_bets(self) -> list[ResolvedBet]:
        manifold_bets = get_resolved_manifold_bets(
            user_id=self.manifold_user_id,
            start_time=self.start_time,
            end_time=None,
        )
        return [manifold_to_generic_resolved_bet(b) for b in manifold_bets]

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: datetime
    ) -> list[DeployedAgent]:
        agents = []
        for key in settings.MANIFOLD_API_KEYS:
            agents.append(
                DeployedManifoldAgent(
                    name="ManifoldAgent",
                    start_time=start_time,
                    manifold_user_id=get_authenticated_user(key).id,
                )
            )
        else:
            return []
