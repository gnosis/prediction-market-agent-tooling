import os
import subprocess
import typing as t
from datetime import datetime
from typing import Any, NoReturn, Optional, Type, TypeVar, cast

import git
import pytz
import requests
from loguru import logger
from pydantic import BaseModel, ValidationError

from prediction_market_agent_tooling.gtypes import (
    DatetimeWithTimezone,
    Probability,
    SecretStr,
)

T = TypeVar("T")


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
        from_addres=check_not_none(keys.bet_from_address),  # <-- No more Optional[HexAddress], so type checker will be happy.
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
        else should_not_happen(f"Variable {variable} is uknown.")
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


@t.overload
def add_utc_timezone_validator(value: datetime) -> DatetimeWithTimezone: ...


@t.overload
def add_utc_timezone_validator(value: None) -> None: ...


def add_utc_timezone_validator(value: datetime | None) -> DatetimeWithTimezone | None:
    """
    If datetime doesn't come with a timezone, we assume it to be UTC.
    Note: Not great, but at least the error will be constant.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=pytz.UTC)
    if value.tzinfo != pytz.UTC:
        value = value.astimezone(pytz.UTC)
    return cast(DatetimeWithTimezone, value)


def utcnow() -> DatetimeWithTimezone:
    return add_utc_timezone_validator(datetime.utcnow())


def get_current_git_commit_sha() -> str:
    return git.Repo(search_parent_directories=True).head.commit.hexsha


def to_int_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())


def get_current_git_branch() -> str:
    return git.Repo(search_parent_directories=True).active_branch.name


def get_current_git_url() -> str:
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
        - Market's probability is 0.1, so the market is quite certain about NO: prob_uncertainty(0.1) == 0.36
        - Market's probability is 0.95, so the market is quite certain about YES: prob_uncertainty(0.95) == 0.19
    """
    return -4 * (prob - 0.5) ** 2 + 1
