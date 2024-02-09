from datetime import datetime
from pydantic import BaseModel
import typing as t

from prediction_market_agent_tooling.markets.data_models import Bet, ManifoldUser
from prediction_market_agent_tooling.markets.manifold import get_bets


class DeployedAgent(BaseModel):
    name: str
    start_time: datetime
    end_time: t.Optional[datetime] = None

    def get_bets(self) -> list[Bet]:
        raise NotImplementedError("Subclasses must implement this method.")


class DeployedManifoldAgent(DeployedAgent):
    manifold_user: ManifoldUser

    def get_bets(self) -> list[Bet]:
        return get_bets(self.manifold_user.id)


def monitor_agent(agent: DeployedAgent) -> None:
    agent_bets = agent.get_bets()
    print(f"Agent {agent.name} has {len(agent_bets)} bets.")
    print(f"bet0: {agent_bets[0]}")
    # TODO Get the bets from agent.starttime to agent.endtime (or now if endtime is None)
    # TODO calculate the accuracy of last 10 bets for every day, and display it in a graph in streamlit app
