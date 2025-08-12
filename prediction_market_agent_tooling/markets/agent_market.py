import typing as t
from datetime import timedelta
from enum import Enum
from math import prod

from eth_typing import ChecksumAddress
from pydantic import BaseModel, field_validator, model_validator
from pydantic_core.core_schema import FieldValidationInfo
from web3 import Web3

from prediction_market_agent_tooling.benchmark.utils import get_most_probable_outcome
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.constants import (
    DOWN_OUTCOME_LOWERCASE_IDENTIFIER,
    INVALID_OUTCOME_LOWERCASE_IDENTIFIER,
    NO_OUTCOME_LOWERCASE_IDENTIFIER,
    UP_OUTCOME_LOWERCASE_IDENTIFIER,
    YES_OUTCOME_LOWERCASE_IDENTIFIER,
)
from prediction_market_agent_tooling.gtypes import (
    OutcomeStr,
    OutcomeToken,
    OutcomeWei,
    Probability,
    Wei,
)
from prediction_market_agent_tooling.markets.data_models import (
    USD,
    Bet,
    CategoricalProbabilisticAnswer,
    CollateralToken,
    ExistingPosition,
    PlacedTrade,
    Resolution,
    ResolvedBet,
)
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.tools.utils import (
    DatetimeUTC,
    check_not_none,
    utcnow,
)


class ProcessedMarket(BaseModel):
    answer: CategoricalProbabilisticAnswer


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


class ParentMarket(BaseModel):
    market: "AgentMarket"
    parent_outcome: int


class QuestionType(str, Enum):
    ALL = "all"
    CATEGORICAL = "categorical"
    SCALAR = "scalar"
    BINARY = "binary"


class ConditionalFilterType(Enum):
    ALL = 1
    ONLY_CONDITIONAL = 2
    ONLY_NOT_CONDITIONAL = 3


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

    probabilities: dict[OutcomeStr, Probability]
    url: str
    volume: CollateralToken | None
    fees: MarketFees

    upper_bound: Wei | None = None
    lower_bound: Wei | None = None

    parent: ParentMarket | None = None

    @field_validator("probabilities")
    def validate_probabilities(
        cls,
        probs: dict[OutcomeStr, Probability],
        info: FieldValidationInfo,
    ) -> dict[OutcomeStr, Probability]:
        outcomes: t.Sequence[OutcomeStr] = check_not_none(info.data.get("outcomes"))
        if set(probs.keys()) != set(outcomes):
            raise ValueError("Keys of `probabilities` must match `outcomes` exactly.")
        return probs

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

    def have_bet_on_market_since(self, keys: APIKeys, since: timedelta) -> bool:
        raise NotImplementedError("Subclasses must implement this method")

    def get_outcome_token_pool_by_outcome(self, outcome: OutcomeStr) -> OutcomeToken:
        if self.outcome_token_pool is None or not self.outcome_token_pool:
            return OutcomeToken(0)

        # We look up by index to avoid having to deal with case sensitivity issues.
        outcome_idx = self.get_outcome_index(outcome)
        return list(self.outcome_token_pool.values())[outcome_idx]

    @model_validator(mode="before")
    def handle_legacy_fee(cls, data: dict[str, t.Any]) -> dict[str, t.Any]:
        # Backward compatibility for older `AgentMarket` without `fees`.
        if "fees" not in data and "fee" in data:
            data["fees"] = MarketFees(absolute=0.0, bet_proportion=data["fee"])
            del data["fee"]
        # Backward compatibility for older `AgentMarket` without `probabilities`.
        if "probabilities" not in data and "current_p_yes" in data:
            yes_outcome = data["outcomes"][
                [o.lower() for o in data["outcomes"]].index(
                    YES_OUTCOME_LOWERCASE_IDENTIFIER
                )
            ]
            no_outcome = data["outcomes"][
                [o.lower() for o in data["outcomes"]].index(
                    NO_OUTCOME_LOWERCASE_IDENTIFIER
                )
            ]
            data["probabilities"] = {
                yes_outcome: data["current_p_yes"],
                no_outcome: 1 - data["current_p_yes"],
            }
            del data["current_p_yes"]
        return data

    def market_outcome_for_probability_key(
        self, probability_key: OutcomeStr
    ) -> OutcomeStr:
        for market_outcome in self.outcomes:
            if market_outcome.lower() == probability_key.lower():
                return market_outcome
        raise ValueError(
            f"Could not find probability for probability key {probability_key}"
        )

    def probability_for_market_outcome(self, market_outcome: OutcomeStr) -> Probability:
        for k, v in self.probabilities.items():
            if k.lower() == market_outcome.lower():
                return v
        raise ValueError(
            f"Could not find probability for market outcome {market_outcome}"
        )

    @property
    def question_type(self) -> QuestionType:
        if self.is_binary:
            return QuestionType.BINARY

        elif self.is_scalar:
            return QuestionType.SCALAR

        else:
            return QuestionType.CATEGORICAL

    @property
    def is_binary(self) -> bool:
        # 3 outcomes can also be binary if 3rd outcome is invalid (Seer)
        if len(self.outcomes) not in [2, 3]:
            return False

        lowercase_outcomes = [outcome.lower() for outcome in self.outcomes]

        has_yes = YES_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes
        has_no = NO_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes

        if len(lowercase_outcomes) == 3:
            invalid_outcome = lowercase_outcomes[-1]
            has_invalid = INVALID_OUTCOME_LOWERCASE_IDENTIFIER in invalid_outcome
            return has_yes and has_no and has_invalid

        return has_yes and has_no

    @property
    def is_scalar(self) -> bool:
        # 3 outcomes can also be binary if 3rd outcome is invalid (Seer)
        if len(self.outcomes) not in [2, 3]:
            return False

        lowercase_outcomes = [outcome.lower() for outcome in self.outcomes]

        has_up = UP_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes
        has_down = DOWN_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes

        if len(lowercase_outcomes) == 3:
            invalid_outcome = lowercase_outcomes[-1]
            has_invalid = INVALID_OUTCOME_LOWERCASE_IDENTIFIER in invalid_outcome
            return has_up and has_down and has_invalid

        return has_up and has_down

    @property
    def p_up(self) -> Probability:
        probs_lowercase = {o.lower(): p for o, p in self.probabilities.items()}
        return check_not_none(probs_lowercase.get(UP_OUTCOME_LOWERCASE_IDENTIFIER))

    @property
    def p_down(self) -> Probability:
        probs_lowercase = {o.lower(): p for o, p in self.probabilities.items()}
        return check_not_none(probs_lowercase.get(DOWN_OUTCOME_LOWERCASE_IDENTIFIER))

    @property
    def p_yes(self) -> Probability:
        probs_lowercase = {o.lower(): p for o, p in self.probabilities.items()}
        return check_not_none(probs_lowercase.get(YES_OUTCOME_LOWERCASE_IDENTIFIER))

    @property
    def p_no(self) -> Probability:
        probs_lowercase = {o.lower(): p for o, p in self.probabilities.items()}
        return check_not_none(probs_lowercase.get(NO_OUTCOME_LOWERCASE_IDENTIFIER))

    @property
    def probable_resolution(self) -> Resolution:
        if self.is_resolved():
            if self.has_successful_resolution():
                return check_not_none(self.resolution)
            else:
                raise ValueError(f"Unknown resolution: {self.resolution}")
        else:
            outcome = get_most_probable_outcome(self.probabilities)
            return Resolution(outcome=outcome, invalid=False)

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
        self, outcome: OutcomeStr, amount: OutcomeToken
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

    def liquidate_existing_positions(self, outcome: OutcomeStr) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    def place_bet(self, outcome: OutcomeStr, amount: USD) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    def buy_tokens(self, outcome: OutcomeStr, amount: USD) -> str:
        return self.place_bet(outcome=outcome, amount=amount)

    def get_buy_token_amount(
        self, bet_amount: USD | CollateralToken, outcome: OutcomeStr
    ) -> OutcomeToken | None:
        raise NotImplementedError("Subclasses must implement this method")

    def sell_tokens(self, outcome: OutcomeStr, amount: USD | OutcomeToken) -> str:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def compute_fpmm_probabilities(balances: list[OutcomeWei]) -> list[Probability]:
        """
        Compute the implied probabilities in a Fixed Product Market Maker.

        Args:
            balances (List[float]): Balances of outcome tokens.

        Returns:
            List[float]: Implied probabilities for each outcome.
        """
        if all(x.value == 0 for x in balances):
            return [Probability(0.0)] * len(balances)

        # converting to standard values for prod compatibility.
        values_balance = [i.value for i in balances]
        # Compute product of balances excluding each outcome
        excluded_products = []
        for i in range(len(values_balance)):
            other_balances = values_balance[:i] + values_balance[i + 1 :]
            excluded_products.append(prod(other_balances))

        # Normalize to sum to 1
        total = sum(excluded_products)
        if total == 0:
            return [Probability(0.0)] * len(balances)
        probabilities = [Probability(p / total) for p in excluded_products]

        return probabilities

    @staticmethod
    def build_probability_map_from_p_yes(
        p_yes: Probability,
    ) -> dict[OutcomeStr, Probability]:
        return {
            OutcomeStr(YES_OUTCOME_LOWERCASE_IDENTIFIER): p_yes,
            OutcomeStr(NO_OUTCOME_LOWERCASE_IDENTIFIER): Probability(1.0 - p_yes),
        }

    @staticmethod
    def build_probability_map(
        outcome_token_amounts: list[OutcomeWei], outcomes: list[OutcomeStr]
    ) -> dict[OutcomeStr, Probability]:
        probs = AgentMarket.compute_fpmm_probabilities(outcome_token_amounts)
        return {outcome: prob for outcome, prob in zip(outcomes, probs)}

    @staticmethod
    def get_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        question_type: QuestionType = QuestionType.ALL,
        conditional_filter_type: ConditionalFilterType = ConditionalFilterType.ONLY_NOT_CONDITIONAL,
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
        return (
            self.resolution is not None
            and self.resolution.outcome is not None
            and not self.resolution.invalid
        )

    def has_unsuccessful_resolution(self) -> bool:
        return self.resolution is not None and self.resolution.invalid

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
        outcomes_lowercase = [o.lower() for o in self.outcomes]
        try:
            return outcomes_lowercase.index(outcome.lower())
        except ValueError:
            raise ValueError(f"Outcome `{outcome}` not found in `{self.outcomes}`.")

    def get_token_balance(self, user_id: str, outcome: OutcomeStr) -> OutcomeToken:
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

    def get_pool_tokens(self, outcome: OutcomeStr) -> OutcomeToken:
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
