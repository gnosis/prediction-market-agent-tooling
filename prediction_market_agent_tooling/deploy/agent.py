import inspect
import os
import tempfile
import time
import typing as t
from datetime import datetime

import git
from pydantic import BaseModel

from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    get_binary_markets,
)


class MonitorConfig(BaseModel):
    LABEL_PREFIX: t.ClassVar[str] = "monitor_config_"

    start_time: datetime
    end_time: t.Optional[datetime] = (
        None  # TODO: If we want end time, we need to store agents somewhere, not just query them from functions.
    )
    manifold_user_id: str | None = None
    omen_public_key: str | None = None

    def validate_monitor_config(self, market_type: MarketType) -> None:
        if market_type == MarketType.MANIFOLD and not self.manifold_user_id:
            raise ValueError(
                "You must provide a manifold_user_id when deploying a Manifold agent"
            )

        if market_type == MarketType.OMEN and not self.omen_public_key:
            raise ValueError(
                "You must provide a omen_public_key when deploying a Omen agent"
            )


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
        monitor_config: MonitorConfig | None = None,
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
            "market_type": market_type.value,
        }
        env_vars = (env_vars or {}) | {
            "repository": repository,
            "commit": git.Repo(search_parent_directories=True).head.object.hexsha,
            "agent_class": self.__class__.__name__,
        }

        if monitor_config is not None:
            monitor_config.validate_monitor_config(market_type)
            env_vars |= {
                f"{MonitorConfig.LABEL_PREFIX}{k}": (
                    v.strftime("%Y-%m-%dT%H:%M:%S")
                    if isinstance(v, datetime)
                    else str(v)
                )
                for k, v in monitor_config.model_dump().items()
                if v is not None
            }

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

    def run(self, market_type: MarketType, _place_bet: bool = True) -> None:
        available_markets = get_binary_markets(market_type)
        markets = self.pick_markets(available_markets)
        for market in markets:
            result = self.answer_binary_market(market)
            if _place_bet:
                print(f"Placing bet on {market} with result {result}")
                market.place_bet(
                    amount=market.get_tiny_bet_amount(),
                    outcome=result,
                )

    def get_gcloud_fname(self, market_type: MarketType) -> str:
        return f"{self.__class__.__name__.lower()}-{market_type}-{int(time.time())}"
