import typing as t
from abc import ABC, abstractmethod

from pydantic import BaseModel

from prediction_market_agent_tooling.deploy.betting_strategy import (
    CategoricalProbabilisticAnswer,
)
from prediction_market_agent_tooling.gtypes import USD, Probability
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    ProcessedTradedMarket,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class SimpleJob(BaseModel):
    id: str
    job: str
    reward: USD
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
    def get_reward(self, max_bond: USD) -> USD:
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

    @staticmethod
    @abstractmethod
    def get_job(id: str) -> "JobAgentMarket":
        """Get a single job by its id."""

    @abstractmethod
    def submit_job_result(
        self, agent_name: str, max_bond: USD, result: str
    ) -> ProcessedTradedMarket:
        """Submit the completed result for this job."""

    def to_simple_job(self, max_bond: USD) -> SimpleJob:
        return SimpleJob(
            id=self.id,
            job=self.job,
            reward=self.get_reward(max_bond),
            deadline=self.deadline,
        )

    def get_job_answer(self, result: str) -> CategoricalProbabilisticAnswer:
        # Just return 100% yes with 100% confidence, because we assume the job is completed correctly.
        return CategoricalProbabilisticAnswer(
            probabilities={
                OMEN_TRUE_OUTCOME: Probability(1.0),
                OMEN_FALSE_OUTCOME: Probability(0.0),
            },
            confidence=1.0,
            reasoning=result,
        )
