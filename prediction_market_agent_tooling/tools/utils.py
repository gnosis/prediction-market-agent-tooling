import os
import subprocess
from datetime import datetime
from typing import NoReturn, Optional, Type, TypeVar, cast

import git
import pytz

from prediction_market_agent_tooling.gtypes import DatetimeWithTimezone, SecretStr

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
    print(f"Saved requirements to {output_dir}/requirements.txt")


def add_utc_timezone_validator(value: datetime) -> DatetimeWithTimezone:
    """
    If datetime doesn't come with a timezone, we assume it to be UTC.
    Note: Not great, but at least the error will be constant.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=pytz.UTC)
    if value.tzinfo != pytz.UTC:
        value = value.astimezone(pytz.UTC)
    return cast(DatetimeWithTimezone, value)


def utcnow() -> DatetimeWithTimezone:
    return add_utc_timezone_validator(datetime.utcnow())


def get_current_git_commit_sha() -> str:
    return git.Repo(search_parent_directories=True).head.commit.hexsha


def get_current_git_branch() -> str:
    return git.Repo(search_parent_directories=True).active_branch.name


def get_current_git_url() -> str:
    return git.Repo(search_parent_directories=True).remotes.origin.url


def secret_str_from_env(key: str) -> SecretStr | None:
    value = os.getenv(key)
    return SecretStr(value) if value else None
