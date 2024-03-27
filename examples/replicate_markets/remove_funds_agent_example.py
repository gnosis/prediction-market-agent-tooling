import sys

import functions_framework
from flask import Request
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent import DeployableAgent
from prediction_market_agent_tooling.markets.agent_market import FilterBy
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.omen import (
    omen_remove_fund_market_tx,
    OmenAgentMarket,
)


class ReplicateSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    N_TO_REPLICATE: int
    INITIAL_FUNDS: str
    CLOSE_TIME_UP_TO_N_DAYS: int


class DeployableRemoveFundsFromResolvedOmenMarketsAgent(DeployableAgent):
    def run(
        self, market_type: MarketType = MarketType.OMEN, _place_bet: bool = False
    ) -> None:
        keys = APIKeys()

        logger.info(
            f"Removing funds from resolved Omen markets, created by {keys.bet_from_address}"
        )

        markets = self.get_markets(
            market_type=MarketType.OMEN, limit=sys.maxsize, filter_by=FilterBy.RESOLVED
        )
        # ToDo - How to best handle types here?
        # ToDo - Filter by creator
        resolved_omen_markets = []
        for m in markets:
            if (
                isinstance(m, OmenAgentMarket)
                and m.is_resolved()
                and m.creator == keys.bet_from_address
            ):
                resolved_omen_markets.append(m)

        # for each resolved market, remove all funds
        for market in resolved_omen_markets:
            omen_remove_fund_market_tx(
                market=market,
                shares=None,
                from_private_key=keys.bet_from_private_key,
            )

        logger.debug("Done.")


@functions_framework.http
def main(request: Request) -> str:
    DeployableRemoveFundsFromResolvedOmenMarketsAgent().run()
    return "Success"
