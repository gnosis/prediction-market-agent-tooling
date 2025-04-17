import typing as t
from enum import Enum

from eth_typing import ChecksumAddress
from pydantic import BaseModel, field_validator, model_validator
from pydantic_core.core_schema import FieldValidationInfo
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    OutcomeStr,
    OutcomeToken,
    Probability,
)
from prediction_market_agent_tooling.markets.data_models import (
    USD,
    Bet,
    CollateralToken,
    ExistingPosition,
    PlacedTrade,
    ProbabilisticAnswer,
    Resolution,
    ResolvedBet,
)
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.tools.utils import (
    DatetimeUTC,
    check_not_none,
    should_not_happen,
    utcnow,
)


class ProcessedMarket(BaseModel):
    answer: ProbabilisticAnswer


class ProcessedTradedMarket(ProcessedMarket):
    trades: list[PlacedTrade]


class SortBy(str, Enum):
    CLOSING_SOONEST = "closing-soonest"
    NEWEST = "newest"
    HIGHEST_LIQUIDITY = "highest_liquidity"
    LOWEST_LIQUIDITY = "lowest_liquidity"
    NONE = "none"


class FilterBy(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    NONE = "none"


class AgentMarket(BaseModel):
    """
    Common market class that can be created from vendor specific markets.
    Contains everything that is needed for an agent to make a prediction.
    """

    base_url: t.ClassVar[str]

    id: str
    question: str
    description: str | None
    outcomes: t.Sequence[OutcomeStr]
    outcome_token_pool: dict[OutcomeStr, OutcomeToken] | None
    resolution: Resolution | None
    created_time: DatetimeUTC | None
    close_time: DatetimeUTC | None
    current_p_yes: Probability | None = None
    probability_map: dict[OutcomeStr, Probability]
    url: str
    volume: CollateralToken | None
    fees: MarketFees

    @field_validator("outcome_token_pool")
    def validate_outcome_token_pool(
        cls,
        outcome_token_pool: dict[str, OutcomeToken] | None,
        info: FieldValidationInfo,
    ) -> dict[str, OutcomeToken] | None:
        outcomes: t.Sequence[OutcomeStr] = check_not_none(info.data.get("outcomes"))
        if outcome_token_pool is not None:
            outcome_keys = set(outcome_token_pool.keys())
            expected_keys = set(outcomes)
            if outcome_keys != expected_keys:
                raise ValueError(
                    f"Keys of outcome_token_pool ({outcome_keys}) do not match outcomes ({expected_keys})."
                )
        return outcome_token_pool

    @model_validator(mode="before")
    def handle_legacy_fee(cls, data: dict[str, t.Any]) -> dict[str, t.Any]:
        # Backward compatibility for older `AgentMarket` without `fees`.
        if "fees" not in data and "fee" in data:
            data["fees"] = MarketFees(absolute=0.0, bet_proportion=data["fee"])
            del data["fee"]
        return data

    @property
    def current_p_no(self) -> Probability:
        return Probability(1 - self.current_p_yes)

    @property
    def yes_outcome_price(self) -> CollateralToken:
        """
        Price at prediction market is equal to the probability of given outcome.
        Keep as an extra property, in case it wouldn't be true for some prediction market platform.
        """
        return CollateralToken(self.current_p_yes)

    @property
    def yes_outcome_price_usd(self) -> USD:
        return self.get_token_in_usd(self.yes_outcome_price)

    @property
    def no_outcome_price(self) -> CollateralToken:
        """
        Price at prediction market is equal to the probability of given outcome.
        Keep as an extra property, in case it wouldn't be true for some prediction market platform.
        """
        return CollateralToken(self.current_p_no)

    @property
    def no_outcome_price_usd(self) -> USD:
        return self.get_token_in_usd(self.no_outcome_price)

    @property
    def probable_resolution(self) -> Resolution:
        if self.is_resolved():
            if self.has_successful_resolution():
                return check_not_none(self.resolution)
            else:
                raise ValueError(f"Unknown resolution: {self.resolution}")
        else:
            return Resolution.YES if self.current_p_yes > 0.5 else Resolution.NO

    @property
    def boolean_outcome(self) -> bool:
        if self.resolution:
            if self.resolution == Resolution.YES:
                return True
            elif self.resolution == Resolution.NO:
                return False
        should_not_happen(f"Market {self.id} does not have a successful resolution.")

    def get_last_trade_p_yes(self) -> Probability | None:
        """
        Get the last trade price for the YES outcome. This can be different from the current p_yes, for example if market is closed and it's probabilities are fixed to 0 and 1.
        Could be None if no trades were made.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_last_trade_p_no(self) -> Probability | None:
        """
        Get the last trade price for the NO outcome. This can be different from the current p_yes, for example if market is closed and it's probabilities are fixed to 0 and 1.
        Could be None if no trades were made.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_last_trade_yes_outcome_price(self) -> CollateralToken | None:
        # Price on prediction markets are, by definition, equal to the probability of an outcome.
        # Just making it explicit in this function.
        if last_trade_p_yes := self.get_last_trade_p_yes():
            return CollateralToken(last_trade_p_yes)
        return None

    def get_last_trade_yes_outcome_price_usd(self) -> USD | None:
        if last_trade_yes_outcome_price := self.get_last_trade_yes_outcome_price():
            return self.get_token_in_usd(last_trade_yes_outcome_price)
        return None

    def get_last_trade_no_outcome_price(self) -> CollateralToken | None:
        # Price on prediction markets are, by definition, equal to the probability of an outcome.
        # Just making it explicit in this function.
        if last_trade_p_no := self.get_last_trade_p_no():
            return CollateralToken(last_trade_p_no)
        return None

    def get_last_trade_no_outcome_price_usd(self) -> USD | None:
        if last_trade_no_outcome_price := self.get_last_trade_no_outcome_price():
            return self.get_token_in_usd(last_trade_no_outcome_price)
        return None

    def get_liquidatable_amount(self) -> OutcomeToken:
        tiny_amount = self.get_tiny_bet_amount()
        return OutcomeToken.from_token(tiny_amount / 10)

    def get_token_in_usd(self, x: CollateralToken) -> USD:
        """
        Token of this market can have whatever worth (e.g. sDai and ETH markets will have different worth of 1 token). Use this to convert it to USD.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_usd_in_token(self, x: USD) -> CollateralToken:
        """
        Markets on a single platform can have different tokens as collateral (sDai, wxDai, GNO, ...). Use this to convert USD to the token of this market.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_sell_value_of_outcome_token(
        self, outcome: str, amount: OutcomeToken
    ) -> CollateralToken:
        """
        When you hold OutcomeToken(s), it's easy to calculate how much you get at the end if you win (1 OutcomeToken will equal to 1 Token).
        But use this to figure out, how much are these outcome tokens worth right now (for how much you can sell them).
        """
        raise NotImplementedError("Subclasses must implement this method")

    def get_in_usd(self, x: USD | CollateralToken) -> USD:
        if isinstance(x, USD):
            return x
        return self.get_token_in_usd(x)

    def get_in_token(self, x: USD | CollateralToken) -> CollateralToken:
        if isinstance(x, CollateralToken):
            return x
        return self.get_usd_in_token(x)

    def get_tiny_bet_amount(self) -> CollateralToken:
        """
        Tiny bet amount that the platform still allows us to do.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def liquidate_existing_positions(self, outcome: bool) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def place_bet(self, outcome: OutcomeStr, amount: USD) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def buy_tokens(self, outcome: OutcomeStr, amount: USD) -> str:
        return self.place_bet(outcome=outcome, amount=amount)

    def get_buy_token_amount(
        self, bet_amount: USD | CollateralToken, direction: bool
    ) -> OutcomeToken | None:
        raise NotImplementedError("Subclasses must implement this method")

    def sell_tokens(self, outcome: OutcomeStr, amount: USD | OutcomeToken) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        fetch_categorical_markets: bool = False,
    ) -> t.Sequence["AgentMarket"]:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_binary_market(id: str) -> "AgentMarket":
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def redeem_winnings(api_keys: APIKeys) -> None:
        """
        On some markets (like Omen), it's needed to manually claim the winner bets. If it's not needed, just implement with `pass`.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @classmethod
    def get_trade_balance(cls, api_keys: APIKeys) -> USD:
        """
        Return balance that can be used to trade on the given market.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def verify_operational_balance(api_keys: APIKeys) -> bool:
        """
        Return `True` if the user has enough of operational balance. If not needed, just return `True`.
        For example: Omen needs at least some xDai in the wallet to execute transactions.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def store_prediction(
        self,
        processed_market: ProcessedMarket | None,
        keys: APIKeys,
        agent_name: str,
    ) -> None:
        """
        If market allows to upload predictions somewhere, implement it in this method.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def store_trades(
        self,
        traded_market: ProcessedTradedMarket | None,
        keys: APIKeys,
        agent_name: str,
        web3: Web3 | None = None,
    ) -> None:
        """
        If market allows to upload trades somewhere, implement it in this method.
        """
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_bets_made_since(
        better_address: ChecksumAddress, start_time: DatetimeUTC
    ) -> list[Bet]:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_resolved_bets_made_since(
        better_address: ChecksumAddress,
        start_time: DatetimeUTC,
        end_time: DatetimeUTC | None,
    ) -> list[ResolvedBet]:
        raise NotImplementedError("Subclasses must implement this method")

    def is_closed(self) -> bool:
        return self.close_time is not None and self.close_time <= utcnow()

    def is_resolved(self) -> bool:
        return self.resolution is not None

    def get_liquidity(self) -> CollateralToken:
        raise NotImplementedError("Subclasses must implement this method")

    def has_liquidity(self) -> bool:
        return self.get_liquidity() > 0

    def has_successful_resolution(self) -> bool:
        return self.resolution in [Resolution.YES, Resolution.NO]

    def has_unsuccessful_resolution(self) -> bool:
        return self.resolution in [Resolution.CANCEL, Resolution.MKT]

    @staticmethod
    def get_outcome_str_from_bool(outcome: bool) -> OutcomeStr:
        raise NotImplementedError("Subclasses must implement this method")

    def get_outcome_str(self, outcome_index: int) -> OutcomeStr:
        try:
            return self.outcomes[outcome_index]
        except IndexError:
            raise IndexError(
                f"Outcome index `{outcome_index}` out of range for `{self.outcomes}`: `{self.outcomes}`."
            )

    def get_outcome_index(self, outcome: OutcomeStr) -> int:
        try:
            return self.outcomes.index(outcome)
        except ValueError:
            raise ValueError(f"Outcome `{outcome}` not found in `{self.outcomes}`.")

    def get_token_balance(self, user_id: str, outcome: str) -> OutcomeToken:
        raise NotImplementedError("Subclasses must implement this method")

    def get_position(self, user_id: str) -> ExistingPosition | None:
        raise NotImplementedError("Subclasses must implement this method")

    @classmethod
    def get_positions(
        cls,
        user_id: str,
        liquid_only: bool = False,
        larger_than: OutcomeToken = OutcomeToken(0),
    ) -> t.Sequence[ExistingPosition]:
        """
        Get all non-zero positions a user has in any market.

        If `liquid_only` is True, only return positions that can be sold.

        If `larger_than` is not None, only return positions with a larger number
        of tokens than this amount.
        """
        raise NotImplementedError("Subclasses must implement this method")

    def can_be_traded(self) -> bool:
        if self.is_closed() or not self.has_liquidity():
            return False
        return True

    @classmethod
    def get_user_url(cls, keys: APIKeys) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def has_token_pool(self) -> bool:
        return self.outcome_token_pool is not None

    def get_pool_tokens(self, outcome: str) -> OutcomeToken:
        if not self.outcome_token_pool:
            raise ValueError("Outcome token pool is not available.")

        return self.outcome_token_pool[outcome]

    @staticmethod
    def get_user_balance(user_id: str) -> float:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_user_id(api_keys: APIKeys) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def get_most_recent_trade_datetime(self, user_id: str) -> DatetimeUTC | None:
        raise NotImplementedError("Subclasses must implement this method")
