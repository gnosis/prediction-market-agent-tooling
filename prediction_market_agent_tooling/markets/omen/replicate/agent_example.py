from datetime import datetime, timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.benchmark.utils import MarketSource
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent import DeployableAgent, MarketType
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.omen.replicate.replicate import (
    omen_replicate_from_tx,
)


class ReplicateSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    N_TO_REPLICATE: int
    INITIAL_FUNDS: str
    CLOSE_TIME_UP_TO_N_DAYS: int


class DeployableReplicateToOmenAgent(DeployableAgent):
    def run(self, market_type: MarketType, _place_bet: bool = True) -> None:
        keys = APIKeys()
        settings = ReplicateSettings()
        close_time_before = datetime.utcnow() + timedelta(
            days=settings.CLOSE_TIME_UP_TO_N_DAYS
        )

        print(f"Replicating from {MarketSource.MANIFOLD}.")
        omen_replicate_from_tx(
            market_source=MarketSource.MANIFOLD,
            n_to_replicate=settings.N_TO_REPLICATE,
            initial_funds=xdai_type(settings.INITIAL_FUNDS),
            from_address=keys.bet_from_address,
            from_private_key=keys.bet_from_private_key,
            close_time_before=close_time_before,
        )
        print(f"Replicating from {MarketSource.POLYMARKET}.")
        omen_replicate_from_tx(
            market_source=MarketSource.POLYMARKET,
            n_to_replicate=settings.N_TO_REPLICATE,
            initial_funds=xdai_type(settings.INITIAL_FUNDS),
            from_address=keys.bet_from_address,
            from_private_key=keys.bet_from_private_key,
            close_time_before=close_time_before,
        )
