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
    KubernetesCronJob,
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

    @classmethod
    def from_env_vars_without_prefix(
        cls: t.Type["DeployedManifoldAgent"],
        env_vars: dict[str, t.Any] | None = None,
        extra_vars: dict[str, t.Any] | None = None,
    ) -> "DeployedManifoldAgent":
        # If manifold_user_id is not provided, try to use it from APIKeys initialized from env_vars (will work in case that secret manifold api key was in the env).
        api_keys = APIKeys(**env_vars) if env_vars else None
        if (
            env_vars
            and "manifold_user_id" not in env_vars
            and api_keys
            and api_keys.MANIFOLD_API_KEY is not None
            and api_keys.MANIFOLD_API_KEY
            != APIKeys().MANIFOLD_API_KEY  # Check that it didn't get if from the default env.
        ):
            env_vars["manifold_user_id"] = api_keys.manifold_user_id
        return super().from_env_vars_without_prefix(
            env_vars=env_vars, extra_vars=extra_vars
        )

    @staticmethod
    def from_api_keys(
        name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedManifoldAgent":
        return DeployedManifoldAgent(
            name=name,
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

    @classmethod
    def from_all_gcp_cronjobs(
        cls: t.Type["DeployedManifoldAgent"],
        filter_: t.Callable[
            [KubernetesCronJob], bool
        ] = lambda cronjob: cronjob.metadata.labels[MARKET_TYPE_KEY]
        == MarketType.MANIFOLD.value,
    ) -> t.Sequence["DeployedManifoldAgent"]:
        return super().from_all_gcp_cronjobs(filter_=filter_)
