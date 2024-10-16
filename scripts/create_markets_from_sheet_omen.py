import pandas as pd
import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
    OmenMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import omen_create_market_tx
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    COLLATERAL_TOKEN_CHOICE_TO_ADDRESS,
    OMEN_DEFAULT_MARKET_FEE_PERC,
    CollateralTokenChoice,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC

QUESTION_COLUMN = "Question"
CLOSING_DATE_COLUMN = "Closing date"


def main(
    path: str,
    category: str = typer.Option(),
    initial_funds: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(None),
    cl_token: CollateralTokenChoice = CollateralTokenChoice.sdai,
    fee_perc: float = typer.Option(OMEN_DEFAULT_MARKET_FEE_PERC),
    language: str = typer.Option("en"),
    outcomes: list[str] = typer.Option(OMEN_BINARY_MARKET_OUTCOMES),
    auto_deposit: bool = typer.Option(False),
) -> None:
    """
    Helper script to create markets on Omen, usage:

    ```bash
    python scripts/create_markets_from_sheet_omen.py \
        devconflict.csv \
        --category devconflict \
        --initial-funds 10 \
        --from-private-key your-private-key
    ```
    """
    data = pd.read_csv(path)

    required_columns = [QUESTION_COLUMN, CLOSING_DATE_COLUMN]
    if not all(column in data.columns for column in required_columns):
        missing_cols = [col for col in required_columns if col not in data.columns]
        raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")

    # Remove potential missing markets.
    data = data[data[QUESTION_COLUMN].notnull()]
    # Sanitize questions.
    data[QUESTION_COLUMN] = data[QUESTION_COLUMN].apply(lambda x: x.strip())
    # Remove empty strings.
    data = data[data[QUESTION_COLUMN] != ""]
    # Parse closing dates using DatetimeUTC.
    data[CLOSING_DATE_COLUMN] = data[CLOSING_DATE_COLUMN].apply(
        lambda x: DatetimeUTC.to_datetime_utc(x)
    )

    logger.info(f"Will create {len(data)} markets:")
    logger.info(data)

    safe_address_checksum = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        SAFE_ADDRESS=safe_address_checksum,
    )

    for _, row in data.iterrows():
        logger.info(
            f"Going to create `{row[QUESTION_COLUMN]}` with closing time `{row[CLOSING_DATE_COLUMN]}`."
        )
        market = OmenMarket.from_created_market(
            omen_create_market_tx(
                api_keys=api_keys,
                collateral_token_address=COLLATERAL_TOKEN_CHOICE_TO_ADDRESS[cl_token],
                initial_funds=xdai_type(initial_funds),
                fee_perc=fee_perc,
                question=row[QUESTION_COLUMN],
                closing_time=row["Created date"],
                category=category,
                language=language,
                outcomes=outcomes,
                auto_deposit=auto_deposit,
            )
        )
        logger.info(f"Market '{row['Question']}' created at url: {market.url}.")


if __name__ == "__main__":
    typer.run(main)
