import typing as t
from abc import ABC, abstractmethod

from pydantic import BaseModel

from prediction_market_agent_tooling.deploy.betting_strategy import ProbabilisticAnswer
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    ProcessedTradedMarket,
)
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
        cls,
        limit: int | None,
        filter_by: FilterBy = FilterBy.OPEN,
        sort_by: SortBy = SortBy.CLOSING_SOONEST,
    ) -> t.Sequence["JobAgentMarket"]:
        """Get all available jobs."""

    @abstractmethod
    def submit_job_result(self, max_bond: float, result: str) -> ProcessedTradedMarket:
        """Submit the completed result for this job."""

    def to_simple_job(self, max_bond: float) -> SimpleJob:
        return SimpleJob(
            id=self.id,
            job=self.job,
            reward=self.get_reward(max_bond),
            currency=self.currency.value,
            deadline=self.deadline,
        )

    def get_job_answer(self, result: str) -> ProbabilisticAnswer:
        # Just return 100% yes with 100% confidence, because we assume the job is completed correctly.
        return ProbabilisticAnswer(
            p_yes=Probability(1.0), confidence=1.0, reasoning=result
        )
