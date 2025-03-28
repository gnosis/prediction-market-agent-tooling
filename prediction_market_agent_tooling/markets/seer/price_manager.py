from functools import lru_cache

from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    Probability,
    xdai_type,
    Wei,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.seer.data_models import (
    SeerMarket,
    SeerOutcomeEnum,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import SeerPool
from prediction_market_agent_tooling.tools.cow.cow_order import get_quote
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


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
        price_diff_pct = abs(old_price - normalized_price) / old_price
        if price_diff_pct > max_price_diff:
            logger.info(
                f"{price_diff_pct=} larger than {max_price_diff=} for seer market {self.seer_market.id.hex()} "
            )

    def current_p_yes(self) -> Probability | None:
        # Inspired by https://github.com/seer-pm/demo/blob/ca682153a6b4d4dd3dcc4ad8bdcbe32202fc8fe7/web/src/hooks/useMarketOdds.ts#L15
        price_data = {}
        for idx, wrapped_token in enumerate(self.seer_market.wrapped_tokens):
            price = self.get_price_for_token(
                token=Web3.to_checksum_address(wrapped_token),
            )

            price_data[idx] = price

        price_yes = price_data[self.seer_market.outcome_as_enums[SeerOutcomeEnum.YES]]
        price_no = price_data[self.seer_market.outcome_as_enums[SeerOutcomeEnum.NO]]

        # We only return a probability if we have both price_yes and price_no, since we could place bets
        # in both sides hence we need current probabilities for both outcomes.
        if price_yes and price_no:
            # If other outcome`s price is None, we set it to 0.
            total_price = sum(
                price if price is not None else 0.0 for price in price_data.values()
            )
            normalized_price_yes = price_yes / total_price
            self._log_track_price_normalization_diff(
                old_price=price_yes, normalized_price=normalized_price_yes
            )
            return Probability(normalized_price_yes)
        else:
            return None

    @lru_cache(typed=True)
    def get_price_for_token(
        self,
        token: ChecksumAddress,
        collateral_exchange_amount: Wei = xdai_to_wei(xdai_type(1)),
    ) -> float | None:
        try:
            quote = get_quote(
                amount_wei=collateral_exchange_amount,
                sell_token=self.seer_market.collateral_token_contract_address_checksummed,
                buy_token=token,
            )

        except Exception as e:
            logger.warning(
                f"Could not get quote for {token=} from Cow, exception {e=}. Falling back to pools. "
            )
            return self.get_token_price_from_pools(token=token)

        return collateral_exchange_amount / float(quote.quote.buyAmount.root)

    @staticmethod
    def _pool_token0_matches_token(token: ChecksumAddress, pool: SeerPool) -> bool:
        return pool.token0.id.hex().lower() == token.lower()

    def get_token_price_from_pools(
        self,
        token: ChecksumAddress,
    ) -> float | None:
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
        price_in_collateral_units = (
            pool.token1Price
            if self._pool_token0_matches_token(token=token, pool=pool)
            else pool.token0Price
        )
        return price_in_collateral_units
