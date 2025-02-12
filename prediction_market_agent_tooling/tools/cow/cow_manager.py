import asyncio

from cowdao_cowpy.common.api.errors import UnexpectedResponseError
from cowdao_cowpy.common.config import SupportedChainId
from cowdao_cowpy.cow.swap import get_order_quote
from cowdao_cowpy.order_book.api import OrderBookApi
from cowdao_cowpy.order_book.config import OrderBookAPIConfigFactory, Envs
from cowdao_cowpy.order_book.generated.model import (
    OrderQuoteResponse,
    OrderQuoteRequest,
    OrderQuoteSide1,
    OrderQuoteSideKindSell,
)
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.gtypes import ChecksumAddress, Wei
from prediction_market_agent_tooling.loggers import logger

COW_ENV: Envs = "prod"


class NoLiquidityAvailableOnCowException(Exception):
    """Custom exception for handling case where no liquidity available."""

    pass


class CowManager:
    def __init__(self) -> None:
        self.order_book_api = OrderBookApi(
            OrderBookAPIConfigFactory.get_config(COW_ENV, SupportedChainId.GNOSIS_CHAIN)
        )
        self.precision = 18  # number of token decimals from ERC1155 wrapped tokens.

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(2),
        retry=retry_if_not_exception_type(NoLiquidityAvailableOnCowException),
    )
    def get_quote(
        self,
        collateral_token: ChecksumAddress,
        buy_token: ChecksumAddress,
        sell_amount: Wei,
    ) -> OrderQuoteResponse:
        """
        Quote the price for a sell order.

        Parameters:
        - collateral_token: The token being sold.
        - buy_token: The token being bought.
        - sell_amount: The amount of collateral to sell in atoms.

        Returns:
        - An OrderQuoteResponse containing the quote information.

        Raises:
        - NoLiquidityAvailableOnCowException if no liquidity is available on CoW.
        """

        order_quote_request = OrderQuoteRequest(
            buyToken=buy_token,
            sellToken=collateral_token,
            from_=ADDRESS_ZERO,
        )

        order_side = OrderQuoteSide1(
            kind=OrderQuoteSideKindSell.sell, sellAmountBeforeFee=str(sell_amount)
        )
        try:
            return asyncio.run(
                get_order_quote(
                    order_quote_request=order_quote_request,
                    order_side=order_side,
                    order_book_api=self.order_book_api,
                )
            )

        except UnexpectedResponseError as e1:
            logger.error(f"Unexpected response error: {e1.message}")
            if "NoLiquidity" in e1.message:
                raise NoLiquidityAvailableOnCowException(e1.message)
            raise e1
