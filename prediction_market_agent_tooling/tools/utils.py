import os
import subprocess
from datetime import datetime
from math import prod
from typing import Any, NoReturn, Optional, Type, TypeVar

import pytz
import requests
from pydantic import BaseModel, ValidationError
from scipy.optimize import newton
from scipy.stats import entropy
from tenacity import RetryError

from prediction_market_agent_tooling.gtypes import (
    CollateralToken,
    DatetimeUTC,
    OutcomeToken,
    Probability,
    SecretStr,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.market_fees import MarketFees

T = TypeVar("T")

# t=0 is mathematically impossible and it's not clear how OpenAI (and others) handle it, as a result, even with t=0, gpt-4-turbo produces very different outputs,
# see this experiment to figure out if you should use LLM_SUPER_LOW_TEMPERATURE or just 0: https://github.com/gnosis/prediction-market-agent/pull/438.
LLM_SUPER_LOW_TEMPERATURE = 0.00000001
# For consistent results, also include seed for models that supports it.
LLM_SEED = 0

BPS_CONSTANT = 10000


def check_not_none(
    value: Optional[T],
    msg: str = "Value shouldn't be None.",
    exp: Type[ValueError] = ValueError,
) -> T:
    """
    Utility to remove optionality from a variable.

    Useful for cases like this:

    ```
    keys = pma.utils.get_keys()
    pma.omen.omen_buy_outcome_tx(
        from_address=check_not_none(keys.bet_from_address),  # <-- No more Optional[HexAddress], so type checker will be happy.
        ...,
    )
    ```
    """
    if value is None:
        should_not_happen(msg=msg, exp=exp)
    return value


def should_not_happen(
    msg: str = "Should not happen.", exp: Type[ValueError] = ValueError
) -> NoReturn:
    """
    Utility function to raise an exception with a message.

    Handy for cases like this:

    ```
    return (
        1 if variable == X
        else 2 if variable == Y
        else 3 if variable == Z
        else should_not_happen(f"Variable {variable} is unknown.")
    )
    ```

    To prevent silent bugs with useful error message.
    """
    raise exp(msg)


def export_requirements_from_toml(output_dir: str) -> None:
    if not os.path.exists(output_dir):
        raise ValueError(f"Directory {output_dir} does not exist")
    output_file = f"{output_dir}/requirements.txt"
    subprocess.run(
        f"poetry export -f requirements.txt --without-hashes --output {output_file}",
        shell=True,
        check=True,
    )
    logger.debug(f"Saved requirements to {output_dir}/requirements.txt")


def utcnow() -> DatetimeUTC:
    return DatetimeUTC.from_datetime(datetime.now(pytz.UTC))


def utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    microsecond: int = 0,
    *,
    fold: int = 0,
) -> DatetimeUTC:
    dt = datetime(
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        microsecond=microsecond,
        tzinfo=pytz.UTC,
        fold=fold,
    )
    return DatetimeUTC.from_datetime(dt)


def get_current_git_commit_sha() -> str:
    # Import here to avoid erroring out if git repository is not present, but the function is not used anyway.
    import git

    return git.Repo(search_parent_directories=True).head.commit.hexsha


def to_int_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())


def get_current_git_branch() -> str:
    # Import here to avoid erroring out if git repository is not present, but the function is not used anyway.
    import git

    return git.Repo(search_parent_directories=True).active_branch.name


def get_current_git_url() -> str:
    # Import here to avoid erroring out if git repository is not present, but the function is not used anyway.
    import git

    return git.Repo(search_parent_directories=True).remotes.origin.url


def response_to_json(response: requests.models.Response) -> dict[str, Any]:
    response.raise_for_status()
    response_json: dict[str, Any] = response.json()
    return response_json


BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


def response_to_model(
    response: requests.models.Response, model: Type[BaseModelT]
) -> BaseModelT:
    response_json = response_to_json(response)
    try:
        return model.model_validate(response_json)
    except ValidationError as e:
        raise ValueError(f"Unable to validate: `{response_json}`") from e


def response_list_to_model(
    response: requests.models.Response, model: Type[BaseModelT]
) -> list[BaseModelT]:
    response_json = response_to_json(response)
    try:
        return [model.model_validate(x) for x in response_json]
    except ValidationError as e:
        raise ValueError(f"Unable to validate: `{response_json}`") from e


def secret_str_from_env(key: str) -> SecretStr | None:
    value = os.getenv(key)
    return SecretStr(value) if value else None


def prob_uncertainty(prob: Probability) -> float:
    """
    Returns a value between 0 and 1, where 0 means the market is not uncertain at all and 1 means it's completely uncertain.

    Examples:
        - Market's probability is 0.5, so the market is completely uncertain: prob_uncertainty(0.5) == 1
        - Market's probability is 0.1, so the market is quite certain about NO: prob_uncertainty(0.1) == 0.468
        - Market's probability is 0.95, so the market is quite certain about YES: prob_uncertainty(0.95) == 0.286
    """
    return float(entropy([prob, 1 - prob], base=2))


def calculate_sell_amount_in_collateral(
    shares_to_sell: OutcomeToken,
    outcome_index: int,
    pool_balances: list[OutcomeToken],
    fees: MarketFees,
) -> CollateralToken:
    """
    Computes the amount of collateral that needs to be sold to get `shares`
    amount of shares. Returns None if the amount can't be computed.

    Taken from https://github.com/protofire/omen-exchange/blob/29d0ab16bdafa5cc0d37933c1c7608a055400c73/app/src/util/tools/fpmm/trading/index.ts#L99
    Simplified for binary markets.
    """

    if shares_to_sell == 0:
        return CollateralToken(0)

    if not (0 <= outcome_index < len(pool_balances)):
        raise IndexError("Invalid outcome index")

    if any([v <= 0 for v in pool_balances]):
        raise ValueError("All pool balances must be greater than 0")

    holdings = pool_balances[outcome_index]
    other_holdings = [v for i, v in enumerate(pool_balances) if i != outcome_index]

    def f(r: float) -> float:
        R = (r + fees.absolute) / (1 - fees.bet_proportion)

        # First term: product of (h_i - R) for i != outcome_index
        first_term = prod(h.value - R for h in other_holdings)

        # Second term: (h_o + s - R)
        second_term = holdings.value + shares_to_sell.value - R

        # Third term: product of all holdings (including outcome_index)
        total_product = prod(h.value for h in pool_balances)

        return (first_term * second_term) - total_product

    amount_to_sell = newton(f, 0)
    return CollateralToken(float(amount_to_sell) * 0.999999)  # Avoid rounding errors


def extract_error_from_retry_error(e: BaseException | RetryError) -> BaseException:
    if (
        isinstance(e, RetryError)
        and (exp_from_retry := e.last_attempt.exception()) is not None
    ):
        e = exp_from_retry
    return e
