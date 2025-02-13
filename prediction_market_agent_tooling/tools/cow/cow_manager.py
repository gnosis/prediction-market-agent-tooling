import asyncio

from cowdao_cowpy.common.api.errors import UnexpectedResponseError
from cowdao_cowpy.common.config import SupportedChainId
from cowdao_cowpy.cow.swap import get_order_quote
from cowdao_cowpy.order_book.api import OrderBookApi
from cowdao_cowpy.order_book.config import Envs, OrderBookAPIConfigFactory
from cowdao_cowpy.order_book.generated.model import (
    Address,
    OrderMetaData,
    OrderQuoteRequest,
    OrderQuoteResponse,
    OrderQuoteSide1,
    OrderQuoteSideKindSell,
)
from cowdao_cowpy.order_book.generated.model import TokenAmount as TokenAmountCow
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_fixed
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, Wei, xDai
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.cow.cow_order import swap_tokens_waiting
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei

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
            buyToken=Address(buy_token),
            sellToken=Address(collateral_token),
            from_=Address(ADDRESS_ZERO),
        )

        order_side = OrderQuoteSide1(
            kind=OrderQuoteSideKindSell.sell,
            sellAmountBeforeFee=TokenAmountCow(str(sell_amount)),
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

    @staticmethod
    def swap(
        amount: xDai,
        sell_token: ChecksumAddress,
        buy_token: ChecksumAddress,
        api_keys: APIKeys,
        web3: Web3 | None = None,
    ) -> OrderMetaData:
        order_metadata = swap_tokens_waiting(
            amount_wei=xdai_to_wei(amount),
            sell_token=sell_token,
            buy_token=buy_token,
            api_keys=api_keys,
            web3=web3,
        )
        logger.debug(
            f"Purchased {buy_token} in exchange for {sell_token}. Order details {order_metadata}"
        )
        return order_metadata
