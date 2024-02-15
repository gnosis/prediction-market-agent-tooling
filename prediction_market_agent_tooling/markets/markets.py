import typing as t
from decimal import Decimal
from enum import Enum

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Mana, xDai
from prediction_market_agent_tooling.markets import manifold, omen
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.tools.utils import (
    check_not_none,
    should_not_happen,
)


class MarketType(str, Enum):
    MANIFOLD = "manifold"
    OMEN = "omen"


def get_bet_amount(amount: Decimal, market_type: MarketType) -> BetAmount:
    if market_type == MarketType.OMEN:
        return BetAmount(amount=amount, currency=Currency.xDai)
    elif market_type == MarketType.MANIFOLD:
        return BetAmount(amount=amount, currency=Currency.Mana)
    else:
        raise ValueError(f"Unknown market type: {market_type}")


@t.overload
def get_binary_markets(
    market_type: t.Literal[MarketType.MANIFOLD],
) -> list[manifold.ManifoldMarket]:
    ...


@t.overload
def get_binary_markets(
    market_type: t.Literal[MarketType.OMEN],
) -> list[omen.OmenMarket]:
    ...


@t.overload
def get_binary_markets(
    market_type: MarketType,
) -> t.Union[list[manifold.ManifoldMarket], list[omen.OmenMarket]]:
    ...


def get_binary_markets(
    market_type: MarketType, limit: int = 20
) -> t.Union[list[manifold.ManifoldMarket], list[omen.OmenMarket]]:
    if market_type == MarketType.MANIFOLD:
        return manifold.get_manifold_binary_markets(
            limit=limit, sort="close-date"
        )  # Pick markets closing soonest
    elif market_type == MarketType.OMEN:
        return omen.get_omen_binary_markets(limit=limit)
    else:
        raise ValueError(f"Unknown market type: {market_type}")


def place_bet(
    market: t.Union[omen.OmenMarket, manifold.ManifoldMarket],
    outcome: bool,
    omen_auto_deposit: bool,
    amount: BetAmount,
) -> None:
    keys = APIKeys()
    if isinstance(market, manifold.ManifoldMarket):
        if amount.currency != Currency.Mana:
            raise ValueError(f"Manifold bets are made in Mana. Got {amount.currency}.")
        amount_mana = Mana(amount.amount)
        manifold.place_bet(
            amount=check_not_none(amount_mana),
            market_id=market.id,
            outcome=outcome,
        )
    elif isinstance(market, omen.OmenMarket):
        if amount.currency != Currency.xDai:
            raise ValueError(f"Omen bets are made in xDai. Got {amount.currency}.")
        amount_xdai = xDai(amount.amount)
        omen.binary_omen_buy_outcome_tx(
            amount=check_not_none(amount_xdai),
            from_address=check_not_none(keys.bet_from_address),
            from_private_key=check_not_none(keys.bet_from_private_key),
            market=market,
            binary_outcome=outcome,
            auto_deposit=omen_auto_deposit,
        )
    else:
        should_not_happen(f"Unknown market {market}.")
