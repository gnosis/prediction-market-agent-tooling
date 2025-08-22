from cachetools import TTLCache, cached
from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.deploy.constants import is_invalid_outcome, INVALID_OUTCOME_LOWERCASE_IDENTIFIER
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
    HexAddress,
    OutcomeStr,
    OutcomeToken,
    Probability,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.seer.data_models import SeerMarket
from prediction_market_agent_tooling.markets.seer.exceptions import (
    PriceCalculationError,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_buy_token_amount_else_raise,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


class Prices(BaseModel):
    priceOfCollateralInAskingToken: CollateralToken
    priceOfAskingTokenInCollateral: CollateralToken


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
                f"{price_diff_pct=} larger than {max_price_diff=} for seer market {self.seer_market.id.to_0x_hex()} "
            )

    def get_price_for_token(self, token: ChecksumAddress) -> CollateralToken | None:
        return self.get_amount_of_token_in_collateral(token, CollateralToken(1))

    @cached(TTLCache(maxsize=100, ttl=5 * 60))
    def get_amount_of_collateral_in_token(
        self,
        token: ChecksumAddress,
        collateral_exchange_amount: CollateralToken,
    ) -> CollateralToken | None:
        if token == self.seer_market.collateral_token_contract_address_checksummed:
            return collateral_exchange_amount

        try:
            buy_token_amount = get_buy_token_amount_else_raise(
                sell_amount=collateral_exchange_amount.as_wei,
                sell_token=self.seer_market.collateral_token_contract_address_checksummed,
                buy_token=token,
            )
            return buy_token_amount.as_token

        except Exception as e:
            logger.warning(
                f"Could not get quote for {token=} from Cow, exception {e=}. Falling back to pools. "
            )
            prices = self.get_token_price_from_pools(token=token)
            return (
                prices.priceOfCollateralInAskingToken * collateral_exchange_amount
                if prices
                else None
            )

    @cached(TTLCache(maxsize=100, ttl=5 * 60))
    def get_amount_of_token_in_collateral(
        self,
        token: ChecksumAddress,
        token_exchange_amount: CollateralToken,
    ) -> CollateralToken | None:
        if token == self.seer_market.collateral_token_contract_address_checksummed:
            return token_exchange_amount

        try:
            buy_collateral_amount = get_buy_token_amount_else_raise(
                sell_amount=token_exchange_amount.as_wei,
                sell_token=token,
                buy_token=self.seer_market.collateral_token_contract_address_checksummed,
            )
            return buy_collateral_amount.as_token

        except Exception as e:
            logger.warning(
                f"Could not get quote for {token=} from Cow, exception {e=}. Falling back to pools. "
            )
            prices = self.get_token_price_from_pools(token=token)
            return (
                prices.priceOfAskingTokenInCollateral * token_exchange_amount
                if prices
                else None
            )

    def get_token_price_from_pools(
        self,
        token: ChecksumAddress,
    ) -> Prices | None:
        pool = SeerSubgraphHandler().get_pool_by_token(
            token_address=token,
            collateral_address=self.seer_market.collateral_token_contract_address_checksummed,
        )

        if not pool:
            logger.warning(f"Could not find a pool for {token=}")
            return None

        if (
            Web3.to_checksum_address(pool.token0.id)
            == self.seer_market.collateral_token_contract_address_checksummed
        ):
            price_coll_in_asking = (
                pool.token1Price
            )  # how many outcome tokens per 1 collateral
            price_asking_in_coll = (
                pool.token0Price
            )  # how many collateral tokens per 1 outcome
        else:
            price_coll_in_asking = pool.token0Price
            price_asking_in_coll = pool.token1Price

        return Prices(
            priceOfCollateralInAskingToken=price_coll_in_asking,
            priceOfAskingTokenInCollateral=price_asking_in_coll,
        )

    def build_probability_map(self) -> dict[OutcomeStr, Proba<<<<<<< HEAD
ca682153a6b4d4dd3dcc4ad8bdcbe32202fc8fe7/web/src/hooks/useMarketOdds.ts#L15
        price_data: dict[HexAddress, CollateralToken] = {}

        for idx, wrapped_token in enumerate(self.seer_market.wrapped_tokens):
            price = self.get_price_for_token(
                token=Web3.to_checksum_address(wrapped_token),
            )
            # It's okay if invalid (last) outcome has price 0, but not the other outcomes.
            if price is None and idx != len(self.seer_market.wrapped_tokens) - 1:
                raise PriceCalculationError(
                    f"Couldn't get price for {wrapped_token} for market {self.seer_market.url}."
                )
            price_data[wrapped_token] = (
                price if price is not None else CollateralToken.zero()
            )

        # We normalize the prices to sum up to 1.
        normalized_prices = {}

        if not price_data or (
            sum(price_data.values(), start=CollateralToken.zero())
            == CollateralToken.zero()
        ):
            raise PriceCalculationError(
                f"All prices for market {self.seer_market.url} are zero. This shouldn't happen."
            )

        for outcome_token, price in price_data.items():
            old_price = price<<<<<<< HEAD

            new_price = Probability(
                price / (sum(price_data.values(), start=CollateralToken.zero()))
            )
            self._log_track_price_normalization_diff(
                old_price=old_price.value, normalized_price=new_price
            )
            outcome = self.seer_market.outcomes[
                self.seer_market.wrapped_tokens.index(outcome_token)
            ]
            normalized_prices[OutcomeStr(str(outcome).strip())] = new_price

        return normalized_prices

    def build_initial_probs_from_pool(
        self, model: SeerMarket, wrapped_tokens: list[ChecksumAddress]
    ) -> tuple[dict[OutcomeStr, Probability], dict[OutcomeStr, OutcomeToken]]:
        """
        Builds a map of outcome to probability and outcome token pool.
        """
        probability_map = {}
        outcome_token_pool = {}
        wrapped_tokens_with_supply = [
            (
                token,
                SeerSubgraphHandler().get_pool_by_token(
                    token, model.collateral_token_contract_address_checksummed
                ),
            )
            for token in wrapped_tokens
        ]
        wrapped_tokens_with_supply = [
            (token, pool)
            for token, pool in wrapped_tokens_with_supply
            if pool is not None
        ]

        for token, pool in wrapped_tokens_with_supply:
            if pool is None or pool.token1.id is None or pool.token0.id is None:
                continue
            if HexBytes(token) == HexBytes(pool.token1.id):
                key_outcome = OutcomeStr(
                    str(model.outcomes[wrapped_tokens.index(token)]).strip()
                )
                outcome_token_pool[key_outcome] = (
                    OutcomeToken(pool.totalValueLockedToken0)
                    if pool.totalValueLockedToken0 is not None
                    else OutcomeToken(0)
                )
                probability_map[key_outcome] = Probability(pool.token0Price.value)
            else:
                key_outcome = OutcomeStr(
                    str(model.outcomes[wrapped_tokens.index(token)]).strip()
                )
                outcome_token_pool[key_outcome] = (
                    OutcomeToken(pool.totalValueLockedToken1)
                    if pool.totalValueLockedToken1 is not None
                    else OutcomeToken(0)
                )
                probability_map[key_outcome] = Probability(pool.token1Price.value)

        for outcome in model.outcomes:
            key_outcome = OutcomeStr(str(outcome).strip())
            if key_outcome not in outcome_token_pool:
                outcome_token_pool[key_outcome] = OutcomeToken(0)
                logger.warning(
                    f"Outcome {key_outcome} not found in outcome_token_pool for market {self.seer_market.url}."
                )
            if key_outcome not in probability_map:
                if INVALID_OUTCOME_LOWERCASE_IDENTIFIER not in key_outcome.lower():
                    raise PriceCalculationError(
                        f"Couldn't get probability for {key_outcome} for market {self.seer_market.url}."
                    )
                else:
                    probability_map[key_outcome] = Probability(0)
        return probability_map, outcome_token_pool
