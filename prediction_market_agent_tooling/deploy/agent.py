import time
from enum import Enum
from pydantic import BaseModel
from decimal import Decimal
from prediction_market_agent_tooling.markets.data_models import AgentMarket
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    get_binary_markets,
    place_bet,
)
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
)


class DeploymentType(str, Enum):
    GOOGLE_CLOUD = "google_cloud"
    LOCAL = "local"


class DeployableAgent(BaseModel):
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

    def deploy(
        self,
        market_type: MarketType,
        deployment_type: DeploymentType,
        sleep_time: float,
        timeout: float,
        place_bet: bool,
    ) -> None:
        if deployment_type == DeploymentType.GOOGLE_CLOUD:
            # Deploy to Google Cloud Functions, and use Google Cloud Scheduler to run the function
            raise NotImplementedError(
                "TODO not currently possible via DeployableAgent class. See examples/cloud_deployment/ instead."
            )
        elif deployment_type == DeploymentType.LOCAL:
            start_time = time.time()
            while True:
                self.run(market_type=market_type, _place_bet=place_bet)
                time.sleep(sleep_time)
                if time.time() - start_time > timeout:
                    break

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
