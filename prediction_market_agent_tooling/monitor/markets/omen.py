import typing as t

from google.cloud.functions_v2.types.functions import Function
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.constants import MARKET_TYPE_KEY
from prediction_market_agent_tooling.gtypes import ChecksumAddress, DatetimeWithTimezone
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
    KubernetesCronJob,
)


class DeployedOmenAgent(DeployedAgent):
    omen_public_key: ChecksumAddress

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
            and api_keys.bet_from_address is not None
            and api_keys.bet_from_address
            != APIKeys().bet_from_address  # Check that it didn't get if from the default env.
        ):
            env_vars["omen_public_key"] = api_keys.bet_from_address
        return super().from_env_vars_without_prefix(
            env_vars=env_vars, extra_vars=extra_vars
        )

    @staticmethod
    def from_api_keys(
        name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedOmenAgent":
        return DeployedOmenAgent(
            name=name,
            start_time=start_time,
            omen_public_key=api_keys.bet_from_address,
        )

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: DatetimeWithTimezone
    ) -> list[DeployedAgent]:
        return [
            DeployedOmenAgent(
                name=f"OmenAgent-{idx}",
                start_time=start_time,
                omen_public_key=Web3.to_checksum_address(omen_public_key),
            )
            for idx, omen_public_key in enumerate(settings.OMEN_PUBLIC_KEYS)
        ]

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
        filter_: t.Callable[
            [KubernetesCronJob], bool
        ] = lambda cronjob: cronjob.metadata.labels[MARKET_TYPE_KEY]
        == MarketType.OMEN.value,
    ) -> t.Sequence["DeployedOmenAgent"]:
        return super().from_all_gcp_cronjobs(filter_=filter_)
