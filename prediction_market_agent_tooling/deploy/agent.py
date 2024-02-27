import inspect
import os
import tempfile
import time
import typing as t
from datetime import datetime

import git

from prediction_market_agent_tooling.deploy.constants import (
    COMMIT_KEY,
    MARKET_TYPE_KEY,
    REPOSITORY_KEY,
)
from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import BetAmount
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    get_binary_markets,
)
from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
    DeployedManifoldAgentParams,
)
from prediction_market_agent_tooling.monitor.markets.omen import (
    DeployedOmenAgent,
    DeployedOmenAgentParams,
)
from prediction_market_agent_tooling.tools.utils import should_not_happen


class DeployableAgent:
    def __init__(self) -> None:
        self.load()

    def __init_subclass__(cls, **kwargs: t.Any) -> None:
        if cls.__init__ is not DeployableAgent.__init__:
            raise TypeError(
                "Cannot override __init__ method of DeployableAgent class, please override the `load` method to set up the agent."
            )

    def load(self) -> None:
        pass

    def pick_markets(self, markets: list[AgentMarket]) -> list[AgentMarket]:
        """
        This method should be implemented by the subclass to pick the markets to bet on. By default, it picks only the first market.
        """
        return markets[:1]

    def answer_binary_market(self, market: AgentMarket) -> bool:
        """
        Answer the binary market. This method must be implemented by the subclass.
        """
        raise NotImplementedError("This method must be implemented by the subclass")

    def deploy_local(
        self,
        market_type: MarketType,
        sleep_time: float,
        timeout: float,
        place_bet: bool,
    ) -> None:
        start_time = time.time()
        while True:
            self.run(market_type=market_type, _place_bet=place_bet)
            time.sleep(sleep_time)
            if time.time() - start_time > timeout:
                break

    def deploy_gcp(
        self,
        repository: str,
        market_type: MarketType,
        memory: int,
        labels: dict[str, str] | None = None,
        env_vars: dict[str, str] | None = None,
        secrets: dict[str, str] | None = None,
        cron_schedule: str | None = None,
        gcp_fname: str | None = None,
        start_time: datetime | None = None,
        monitor_params: (
            DeployedOmenAgentParams | DeployedManifoldAgentParams | None
        ) = None,
    ) -> None:
        path_to_agent_file = os.path.relpath(inspect.getfile(self.__class__))

        entrypoint_function_name = "main"
        entrypoint_template = f"""
from {path_to_agent_file.replace("/", ".").replace(".py", "")} import *
import functions_framework
from prediction_market_agent_tooling.markets.markets import MarketType

@functions_framework.http
def {entrypoint_function_name}(request) -> str:
    {self.__class__.__name__}().run(market_type={market_type.__class__.__name__}.{market_type.name})
    return "Success"
"""

        gcp_fname = gcp_fname or self.get_gcloud_fname(market_type)

        # For labels, only hyphens (-), underscores (_), lowercase characters, and numbers are allowed in values.
        labels = (labels or {}) | {
            MARKET_TYPE_KEY: market_type.value,
        }
        env_vars = (env_vars or {}) | {
            REPOSITORY_KEY: repository,
            COMMIT_KEY: git.Repo(search_parent_directories=True).head.object.hexsha,
        }

        monitor_agent = (
            DeployedOmenAgent(
                name=gcp_fname,
                deployableagent_class_name=self.__class__.__name__,
                start_time=start_time or datetime.utcnow(),
                omen_public_key=(
                    monitor_params.omen_public_key if monitor_params else None
                ),
            )
            if market_type == MarketType.OMEN
            and (
                monitor_params is None
                or isinstance(monitor_params, DeployedOmenAgentParams)
            )
            else (
                DeployedManifoldAgent(
                    name=gcp_fname,
                    deployableagent_class_name=self.__class__.__name__,
                    start_time=start_time or datetime.utcnow(),
                    manifold_user_id=(
                        monitor_params.manifold_user_id if monitor_params else None
                    ),
                )
                if market_type == MarketType.MANIFOLD
                and (
                    monitor_params is None
                    or isinstance(monitor_params, DeployedManifoldAgentParams)
                )
                else (
                    None
                    if market_type is None
                    else should_not_happen("Unknown market type.")
                )
            )
        )

        if monitor_agent is not None:
            env_vars |= monitor_agent.model_dump_prefixed()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as f:
            f.write(entrypoint_template)
            f.flush()

            fname = deploy_to_gcp(
                gcp_fname=gcp_fname,
                requirements_file=None,
                extra_deps=[repository],
                function_file=f.name,
                labels=labels,
                env_vars=env_vars,
                secrets=secrets,
                memory=memory,
                entrypoint_function_name=entrypoint_function_name,
            )

        # Check that the function is deployed
        if not gcp_function_is_active(fname):
            raise RuntimeError("Failed to deploy the function")

        # Run the function
        response = run_deployed_gcp_function(fname)
        if not response.ok:
            raise RuntimeError("Failed to run the deployed function")

        # Schedule the function
        if cron_schedule:
            schedule_deployed_gcp_function(fname, cron_schedule=cron_schedule)

    def calculate_bet_amount(self, answer: bool, market: AgentMarket) -> BetAmount:
        """
        Calculate the bet amount. By default, it returns the minimum bet amount.
        """
        return market.get_tiny_bet_amount()

    def run(self, market_type: MarketType, _place_bet: bool = True) -> None:
        available_markets = get_binary_markets(market_type)
        markets = self.pick_markets(available_markets)
        for market in markets:
            result = self.answer_binary_market(market)
            if _place_bet:
                print(f"Placing bet on {market} with result {result}")
                market.place_bet(
                    amount=self.calculate_bet_amount(result, market),
                    outcome=result,
                )

    def get_gcloud_fname(self, market_type: MarketType) -> str:
        return f"{self.__class__.__name__.lower()}-{market_type}-{int(time.time())}"
