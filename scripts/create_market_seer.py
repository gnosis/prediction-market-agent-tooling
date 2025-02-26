from datetime import datetime

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
)
from prediction_market_agent_tooling.markets.seer.seer import seer_create_market_tx
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


def main(
    question: str = typer.Option(),
    opening_time: datetime = typer.Option(),
    category: str = typer.Option(),
    initial_funds: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(None),
    min_bond_xdai: int = typer.Option(0.01),
    language: str = typer.Option("en_US"),
    outcomes: list[str] = typer.Option(OMEN_BINARY_MARKET_OUTCOMES),
    auto_deposit: bool = typer.Option(True),
) -> None:
    """
    Creates a market on Seer.

    Args:
        question (str): The question for the market.
        opening_time (datetime): The opening time for the market.
        category (str): The category of the market.
        initial_funds (str): The initial funds for the market.
        from_private_key (str): The private key to use for transactions.
        safe_address (str, optional): The safe address for transactions. Defaults to None.
        min_bond_xdai (int, optional): The minimum bond in xDai. Defaults to 0.01 xDai.
        language (str, optional): The language of the market. Defaults to "en".
        outcomes (list[str], optional): The outcomes for the market. Defaults to OMEN_BINARY_MARKET_OUTCOMES.
        auto_deposit (bool, optional): Whether to automatically deposit funds. Defaults to False.

    Returns:
        None
    """
    safe_address_checksum = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        SAFE_ADDRESS=safe_address_checksum,
    )
    market = seer_create_market_tx(
        api_keys=api_keys,
        initial_funds=xdai_type(initial_funds),
        question=question,
        opening_time=DatetimeUTC.from_datetime(opening_time),
        category=category,
        language=language,
        outcomes=outcomes,
        auto_deposit=auto_deposit,
        min_bond_xdai=xdai_type(min_bond_xdai),
    )
    logger.info(f"Market created: {market}")


if __name__ == "__main__":
    typer.run(main)
