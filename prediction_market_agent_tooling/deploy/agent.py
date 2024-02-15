import time
import os
import tempfile
import inspect
from decimal import Decimal

from prediction_market_agent_tooling.markets.data_models import (
    AgentMarket,
    BetAmount,
    Currency,
)
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    get_binary_markets,
    place_bet,
)
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
)
from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active


class DeployableAgent:

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
    ) -> None:
        path_to_agent_file = os.path.relpath(inspect.getfile(self.__class__))

        entrypoint_template = f"""
from {path_to_agent_file.replace("/", ".").replace(".py", "")} import *
import functions_framework
from prediction_market_agent_tooling.markets.markets import MarketType

@functions_framework.http
def main(request) -> str:
    {self.__class__.__name__}().run(market_type=market_type)
    return "Success"
"""

        gcp_fname = self.get_gcloud_fname(market_type)

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
        available_markets = [
            x.to_agent_market() for x in get_binary_markets(market_type)
        ]
        markets = self.pick_markets(available_markets)
        for market in markets:
            result = self.answer_binary_market(market)
            if _place_bet:
                print(f"Placing bet on {market} with result {result}")
                place_bet(
                    market=market.original_market,
                    amount=get_tiny_bet(market_type),
                    outcome=result,
                    omen_auto_deposit=True,
                )

    @classmethod
    def get_gcloud_fname(cls, market_type: MarketType) -> str:
        return f"{cls.__class__.__name__.lower()}-{market_type}-{int(time.time())}"


def get_tiny_bet(market_type: MarketType) -> BetAmount:
    if market_type == MarketType.OMEN:
        return BetAmount(amount=Decimal(0.00001), currency=Currency.xDai)
    elif market_type == MarketType.MANIFOLD:
        return BetAmount(amount=Decimal(1), currency=Currency.Mana)
    else:
        raise ValueError(f"Unknown market type: {market_type}")
