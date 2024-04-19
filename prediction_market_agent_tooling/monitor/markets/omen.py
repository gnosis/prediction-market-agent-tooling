import typing as t

from google.cloud.functions_v2.types.functions import Function

from prediction_market_agent_tooling.config import APIKeys, PrivateCredentials
from prediction_market_agent_tooling.deploy.constants import MARKET_TYPE_KEY
from prediction_market_agent_tooling.gtypes import ChecksumAddress, DatetimeWithTimezone
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    KubernetesCronJob,
)


class DeployedOmenAgent(DeployedAgent):
    omen_public_key: ChecksumAddress

    @property
    def public_id(self) -> str:
        return self.omen_public_key

    def get_resolved_bets(self) -> list[ResolvedBet]:
        # For monitoring of deployed agent, return only resolved bets with valid answer.
        subgraph_handler = OmenSubgraphHandler()
        bets = subgraph_handler.get_resolved_bets_with_valid_answer(
            better_address=self.omen_public_key,
            start_time=self.start_time,
            end_time=self.end_time,
        )
        return [b.to_generic_resolved_bet() for b in bets]

    @classmethod
    def from_env_vars_without_prefix(
        cls: t.Type["DeployedOmenAgent"],
        env_vars: dict[str, t.Any] | None = None,
        extra_vars: dict[str, t.Any] | None = None,
    ) -> "DeployedOmenAgent":
        # If omen_public_key is not provided, try to use it from APIKeys initialized from env_vars (will work in case that secret private key was in the env).
        api_keys = APIKeys(**env_vars) if env_vars else None
        if (
            env_vars
            and "omen_public_key" not in env_vars
            and api_keys
            and api_keys.BET_FROM_PRIVATE_KEY is not None
            and api_keys.BET_FROM_PRIVATE_KEY
            != APIKeys().BET_FROM_PRIVATE_KEY  # Check that it didn't get if from the default env.
        ):
            private_credentials = PrivateCredentials.from_api_keys(api_keys)
            env_vars["omen_public_key"] = private_credentials.public_key
        return super().from_env_vars_without_prefix(
            env_vars=env_vars, extra_vars=extra_vars
        )

    @staticmethod
    def from_api_keys(
        name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedOmenAgent":
        private_credentials = PrivateCredentials.from_api_keys(api_keys)
        return DeployedOmenAgent(
            name=name,
            start_time=start_time,
            omen_public_key=private_credentials.public_key,
        )

    @classmethod
    def from_all_gcp_functions(
        cls: t.Type["DeployedOmenAgent"],
        filter_: t.Callable[[Function], bool] = lambda function: function.labels[
            MARKET_TYPE_KEY
        ]
        == MarketType.OMEN.value,
    ) -> t.Sequence["DeployedOmenAgent"]:
        return super().from_all_gcp_functions(filter_=filter_)

    @classmethod
    def from_all_gcp_cronjobs(
        cls: t.Type["DeployedOmenAgent"],
        namespace: str,
        filter_: t.Callable[
            [KubernetesCronJob], bool
        ] = lambda cronjob: cronjob.metadata.labels[MARKET_TYPE_KEY]
        == MarketType.OMEN.value,
    ) -> t.Sequence["DeployedOmenAgent"]:
        return super().from_all_gcp_cronjobs(namespace=namespace, filter_=filter_)
