import typing as t
from datetime import datetime

from google.cloud.functions_v2.types.functions import Function
from pydantic import BaseModel

from prediction_market_agent_tooling.deploy.constants import MARKET_TYPE_KEY
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.manifold.api import (
    get_authenticated_user,
    get_resolved_manifold_bets,
    manifold_to_generic_resolved_bet,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
)


class DeployedManifoldAgentParams(BaseModel):
    manifold_user_id: str


class DeployedManifoldAgent(DeployedAgent):
    manifold_user_id: str | None = None

    def get_resolved_bets(self) -> list[ResolvedBet]:
        manifold_bets = (
            get_resolved_manifold_bets(
                user_id=self.manifold_user_id,
                start_time=self.start_time,
                end_time=self.end_time,
            )
            if self.manifold_user_id
            else []
        )
        return [manifold_to_generic_resolved_bet(b) for b in manifold_bets]

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: datetime
    ) -> list[DeployedAgent]:
        return [
            DeployedManifoldAgent(
                name=f"ManifoldAgent-{idx}",
                deployableagent_class_name="deployableagent_class_name",
                start_time=start_time,
                manifold_user_id=get_authenticated_user(key).id,
            )
            for idx, key in enumerate(settings.MANIFOLD_API_KEYS)
        ]

    @classmethod
    def from_all_gcp_functions(
        cls: t.Type["DeployedManifoldAgent"],
        filter_: t.Callable[[Function], bool] = lambda function: function.labels[
            MARKET_TYPE_KEY
        ]
        == MarketType.MANIFOLD.value,
    ) -> t.Sequence["DeployedManifoldAgent"]:
        return super().from_all_gcp_functions(filter_=filter_)
