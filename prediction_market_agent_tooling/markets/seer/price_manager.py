import typing as t

from cachetools import cached
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
    Probability,
    HexAddress,
    OutcomeStr,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.seer.cache import FSLRUCache
from prediction_market_agent_tooling.markets.seer.data_models import (
    SeerMarket,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import SeerPool
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_buy_token_amount_else_raise,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


def _make_cache_key(
    *args: t.Any,
    token: ChecksumAddress,
    collateral_exchange_amount: CollateralToken | None = None,
) -> str:
    """
    Generate a unique cache key based on a token address and optional collateral token.
    """

    if collateral_exchange_amount is None:
        return f"{token}-no_collateral"

    return "-".join(
        [
            token,
            collateral_exchange_amount.symbol,
            str(collateral_exchange_amount.value),
        ]
    )


class PriceManager:
    def __init__(self, seer_market: SeerMarket, seer_subgraph: SeerSubgraphHandler):
        self.seer_market = seer_market
        self.seer_subgraph = seer_subgraph

    @staticmethod
    def build(market_id: HexBytes) -> "PriceManager":
        s = SeerSubgraphHandler()
        market = s.get_market_by_id(market_id=market_id)
        return PriceManager(seer_market=market, seer_subgraph=s)

    def _log_track_price_normalization_diff(
        self, old_price: float, normalized_price: float, max_price_diff: float = 0.05
    ) -> None:
        # We add max(price,0.01) to avoid division by 0
        price_diff_pct = abs(old_price - normalized_price) / max(old_price, 0.01)
        if price_diff_pct > max_price_diff:
            logger.info(
                f"{price_diff_pct=} larger than {max_price_diff=} for seer market {self.seer_market.id.hex()} "
            )

    # @cached(TTLCache(maxsize=100, ttl=5 * 60), key=_make_cache_key)
    @cached(cache=FSLRUCache(maxsize=32, ttl=5 * 60 * 60), key=_make_cache_key)
    def get_price_for_token(
        self,
        token: ChecksumAddress,
        collateral_exchange_amount: CollateralToken | None = None,
    ) -> CollateralToken | None:
        collateral_exchange_amount = (
            collateral_exchange_amount
            if collateral_exchange_amount is not None
            else CollateralToken(1)
        )

        try:
            buy_token_amount = get_buy_token_amount_else_raise(
                sell_amount=collateral_exchange_amount.as_wei,
                sell_token=self.seer_market.collateral_token_contract_address_checksummed,
                buy_token=token,
            )
            price = collateral_exchange_amount.as_wei / buy_token_amount
            return CollateralToken(price)

        except Exception as e:
            logger.warning(
                f"Could not get quote for {token=} from Cow, exception {e=}. Falling back to pools. "
            )
            return self.get_token_price_from_pools(token=token)

    @staticmethod
    def _pool_token0_matches_token(token: ChecksumAddress, pool: SeerPool) -> bool:
        return pool.token0.id.hex().lower() == token.lower()

    def get_token_price_from_pools(
        self,
        token: ChecksumAddress,
    ) -> CollateralToken | None:
        pool = SeerSubgraphHandler().get_pool_by_token(
            token_address=token,
            collateral_address=self.seer_market.collateral_token_contract_address_checksummed,
        )

        if not pool:
            logger.warning(f"Could not find a pool for {token=}")
            return None

        # The mapping below is odd but surprisingly the Algebra subgraph delivers the token1Price
        # for the token0 and the token0Price for the token1 pool.
        # For example, in a outcomeYES (token0)/sDAI pool (token1), token1Price is the price of outcomeYES in units of sDAI.
        price = (
            pool.token1Price
            if self._pool_token0_matches_token(token=token, pool=pool)
            else pool.token0Price
        )
        return price

    def probability_map(self) -> dict[OutcomeStr, Probability]:
        # Inspired by https://github.com/seer-pm/demo/blob/ca682153a6b4d4dd3dcc4ad8bdcbe32202fc8fe7/web/src/hooks/useMarketOdds.ts#L15
        price_data: dict[HexAddress, CollateralToken | None] = {}
        # we ignore the invalid outcome.
        # Seer hardcodes `invalid outcome` as the latest one (https://github.com/seer-pm/demo/blob/45f4fc59fb521154f914a372b17192812f512fb3/web/src/lib/market.ts#L123).
        valid_wrapped_tokens = self.seer_market.wrapped_tokens[:-1]

        for wrapped_token in valid_wrapped_tokens:
            price = self.get_price_for_token(
                token=Web3.to_checksum_address(wrapped_token),
            )
            price_data[wrapped_token] = price

        # Exclude outcomes which have unavailable prices.
        price_data = {k: v for k, v in price_data.items() if v is not None}

        # We normalize the prices to sum up to 1.
        normalized_prices = {}
        for outcome_token, price in price_data.items():
            old_price = price
            new_price = Probability(price / (sum(price_data.values())))
            self._log_track_price_normalization_diff(
                old_price=old_price.value, normalized_price=new_price
            )
            outcome = self.seer_market.outcomes[
                self.seer_market.wrapped_tokens.index(outcome_token)
            ]
            normalized_prices[OutcomeStr(outcome)] = new_price

        return normalized_prices
