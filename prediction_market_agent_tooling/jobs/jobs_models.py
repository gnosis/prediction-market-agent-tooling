import typing as t
from abc import ABC, abstractmethod

from pydantic import BaseModel

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class SimpleJob(BaseModel):
    id: str
    job: str
    reward: float
    currency: str
    deadline: DatetimeUTC


class JobAgentMarket(AgentMarket, ABC):
    CATEGORY: t.ClassVar[str]

    @property
    @abstractmethod
    def job(self) -> str:
        """Holds description of the job that needs to be done."""

    @property
    @abstractmethod
    def deadline(self) -> DatetimeUTC:
        """Deadline for the job completion."""

    @abstractmethod
    def get_reward(self, max_bond: float) -> float:
        """Reward for completing this job."""

    @classmethod
    @abstractmethod
    def get_jobs(
        cls, limit: int | None, filter_by: FilterBy, sort_by: SortBy
    ) -> t.Sequence["JobAgentMarket"]:
        """Get all available jobs."""

    def to_simple_job(self, max_bond: float) -> SimpleJob:
        return SimpleJob(
            id=self.id,
            job=self.job,
            reward=self.get_reward(max_bond),
            currency=self.currency.value,
            deadline=self.deadline,
        )
