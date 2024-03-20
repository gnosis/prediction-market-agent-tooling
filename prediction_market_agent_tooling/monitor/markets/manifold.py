import typing as t

from google.cloud.functions_v2.types.functions import Function

from prediction_market_agent_tooling.config import APIKeys
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
from prediction_market_agent_tooling.tools.utils import DatetimeWithTimezone


class DeployedManifoldAgent(DeployedAgent):
    manifold_user_id: str

    def get_resolved_bets(self) -> list[ResolvedBet]:
        bets, markets = get_resolved_manifold_bets(
            user_id=self.manifold_user_id,
            start_time=self.start_time,
            end_time=self.end_time,
        )
        return [manifold_to_generic_resolved_bet(b, m) for b, m in zip(bets, markets)]

    @staticmethod
    def from_api_keys(
        name: str,
        deployableagent_class_name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedManifoldAgent":
        return DeployedManifoldAgent(
            name=name,
            deployableagent_class_name=deployableagent_class_name,
            start_time=start_time,
            manifold_user_id=get_authenticated_user(
                api_key=api_keys.manifold_api_key.get_secret_value()
            ).id,
        )

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: DatetimeWithTimezone
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
