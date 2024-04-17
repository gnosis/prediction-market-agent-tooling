from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
)
from prediction_market_agent_tooling.monitor.markets.omen import DeployedOmenAgent
from prediction_market_agent_tooling.monitor.markets.polymarket import (
    DeployedPolymarketAgent,
)


class MonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.monitor", env_file_encoding="utf-8", extra="ignore"
    )

    LOAD_FROM_GCF: bool = False
    LOAD_FROM_GCK: bool = False
    LOAD_FROM_GCK_NAMESPACE: str = "agents"
    MANIFOLD_AGENTS: list[DeployedManifoldAgent] = []
    OMEN_AGENTS: list[DeployedOmenAgent] = []
    POLYMARKET_AGENTS: list[DeployedPolymarketAgent] = []
    PAST_N_WEEKS: int = 1

    @property
    def has_manual_agents(self) -> bool:
        return bool(self.MANIFOLD_AGENTS or self.OMEN_AGENTS or self.POLYMARKET_AGENTS)
