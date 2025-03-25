from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.gtypes import Probability, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.seer.data_models import (
    SeerMarket,
    SeerOutcomeEnum,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import SeerPool
from prediction_market_agent_tooling.tools.caches.inmemory_cache import (
    persistent_inmemory_cache,
)
from prediction_market_agent_tooling.tools.cow.cow_manager import CowManager
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


class PriceManager:
    def __init__(self, market: SeerMarket):
        self.seer_market = market
        self.subgraph_handler = SeerSubgraphHandler()

    def fetch_outcome_price_for_seer_market(self) -> float:
        price_data = {}
        for idx in range(len(self.seer_market.outcomes)):
            wrapped_token = self.seer_market.wrapped_tokens[idx]
            price = self.get_price_for_token(
                token=Web3.to_checksum_address(wrapped_token)
            )
            price_data[idx] = price

        if sum(price_data.values()) == 0:
            logger.warning(
                f"Could not get p_yes for market {self.seer_market.id.hex()}, all price quotes are 0."
            )
            return Probability(0)

        yes_idx = self.seer_market.outcome_as_enums[SeerOutcomeEnum.YES]
        price_yes = price_data[yes_idx] / sum(price_data.values())
        return Probability(price_yes)

    def current_market_p_yes(self) -> Probability:
        price_data = {}
        for idx in range(len(self.seer_market.outcomes)):
            wrapped_token = self.seer_market.wrapped_tokens[idx]
            price = self.get_price_for_token(
                token=Web3.to_checksum_address(wrapped_token)
            )
            price_data[idx] = price

        if sum(price_data.values()) == 0:
            logger.warning(
                f"Could not get p_yes for market {self.seer_market.id.hex()}, all price quotes are 0."
            )
            return Probability(0)

        yes_idx = self.seer_market.outcome_as_enums[SeerOutcomeEnum.YES]
        no_idx = self.seer_market.outcome_as_enums[SeerOutcomeEnum.NO]
        price_yes = price_data[yes_idx]
        price_no = price_data[no_idx]
        if price_yes and not price_no:
            # We simply return p_yes since it's probably a bug that p_no wasn't found.
            return Probability(price_yes)
        elif price_no and not price_yes:
            # We return the complement of p_no (and ignore invalid).
            return Probability(1.0 - price_no)
        else:
            # If all prices are available, we normalize price_yes by the other prices for the final probability.
            price_yes = price_yes / sum(price_data.values())
            return Probability(price_yes)

    @persistent_inmemory_cache
    def get_price_for_token(self, token: ChecksumAddress) -> float:
        collateral_exchange_amount = xdai_to_wei(xdai_type(1))
        try:
            quote = CowManager().get_quote(
                collateral_token=self.seer_market.collateral_token_contract_address_checksummed,
                buy_token=token,
                sell_amount=collateral_exchange_amount,
            )
        except Exception as e:
            logger.warning(
                f"Could not get quote for {token=} from Cow, exception {e=}. Falling back to pools. "
            )
            price = self.get_token_price_from_pools(token=token)
            return price

        return collateral_exchange_amount / float(quote.quote.buyAmount.root)

    @staticmethod
    def _pool_token0_matches_token(token: ChecksumAddress, pool: SeerPool) -> bool:
        return pool.token0.id.hex().lower() == token.lower()

    def get_token_price_from_pools(self, token: ChecksumAddress) -> float:
        pool = self.subgraph_handler.get_pool_by_token(token_address=token)

        if not pool:
            logger.warning(f"Could not find a pool for {token=}, returning 0.")
            return 0
        # Check if other token is market's collateral (sanity check).

        collateral_address = (
            pool.token0.id
            if self._pool_token0_matches_token(token=token, pool=pool)
            else pool.token1.id
        )
        if (
            collateral_address.hex().lower()
            != self.seer_market.collateral_token.lower()
        ):
            logger.warning(
                f"Pool {pool.id.hex()} has collateral mismatch with market. Collateral from pool {collateral_address.hex()}, collateral from market {self.seer_market.collateral_token}, returning 0."
            )
            return 0

        price_in_collateral_units = (
            pool.token0Price
            if self._pool_token0_matches_token(pool)
            else pool.token1Price
        )
        return price_in_collateral_units
