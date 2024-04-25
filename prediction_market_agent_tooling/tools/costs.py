import typing as t
from contextlib import contextmanager
from time import time

from langchain_community.callbacks import get_openai_callback
from pydantic import BaseModel

from prediction_market_agent_tooling.benchmark.utils import get_llm_api_call_cost


class Costs(BaseModel):
    time: float
    cost: float


@contextmanager
def openai_costs(model: str | None = None) -> t.Generator[Costs, None, None]:
    costs = Costs(time=0, cost=0)
    start_time = time()

    with get_openai_callback() as cb:
        yield costs
        if cb.total_tokens > 0 and cb.total_cost == 0 and model is not None:
            # TODO: this is a hack to get the cost for an unsupported model
            cb.total_cost = get_llm_api_call_cost(
                model=model,
                prompt_tokens=cb.prompt_tokens,
                completion_tokens=cb.completion_tokens,
            )
        costs.time = time() - start_time
        costs.cost = cb.total_cost
