from abc import ABC, abstractmethod
from typing import Literal, TypeVar, Generic

from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    TokenAmountAndDirection,
    Resolution,
)
from prediction_market_agent_tooling.markets.manifold.api import get_manifold_market
from prediction_market_agent_tooling.markets.manifold.data_models import ManifoldMarket
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenFixedProductMarketMakerContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)

T = TypeVar(
    "T"
)  # Not possible to use bound due to OmenMarket and ManifoldMarket not sharing a base class


class BaseCalculator(ABC, Generic[T]):
    choices: dict[Resolution, str]

    @abstractmethod
    def calculate_shares_for_outcome(
        self, market: T, bet_amount: float, bet_choice: str
    ) -> float:
        pass

    def calculate_direction(self, market: T, estimate_p_yes: float) -> bool:
        fixed_bet_amount = (
            100  # as example, does not affect the calculation of Expected Value below.
        )
        num_tokens_yes = self.calculate_shares_for_outcome(
            market, fixed_bet_amount, self.choices[Resolution.YES]
        )
        num_tokens_no = self.calculate_shares_for_outcome(
            market, fixed_bet_amount, self.choices[Resolution.NO]
        )
        return (estimate_p_yes * num_tokens_yes) - (
            (1 - estimate_p_yes) * num_tokens_no
        ) > 0


class OmenCalculator(BaseCalculator[OmenMarket]):
    choices: dict[Resolution, str] = {
        Resolution.YES: "Yes",
        Resolution.NO: "No",
    }

    def calculate_shares_for_outcome(
        self, market: OmenMarket, bet_amount: float, bet_choice: Literal["Yes", "No"]
    ) -> float:
        contract = OmenFixedProductMarketMakerContract(
            address=market.market_maker_contract_address_checksummed
        )
        outcome_idx = market.outcomes.index(bet_choice)
        outcome_tokens = contract.calcBuyAmount(Wei(int(bet_amount)), outcome_idx)
        return outcome_tokens


class ManifoldCalculator(BaseCalculator[ManifoldMarket]):
    choices: dict[Resolution, str] = {
        Resolution.YES: "YES",
        Resolution.NO: "NO",
    }

    def calculate_shares_for_outcome(
        self, market: ManifoldMarket, bet_amount: float, bet_choice: str
    ) -> float:
        # from https://github.com/manifoldmarkets/manifold/blob/main/common/src/calculate-cpmm.ts#L58
        if bet_amount == 0:
            return 0

        y = market.pool.YES
        n = market.pool.NO
        p = market.p
        k = y**p * n ** (1 - p)

        if bet_choice == self.choices[Resolution.YES]:
            return y + bet_amount - (k * (bet_amount + n) ** (p - 1)) ** (1 / p)
        else:
            return n + bet_amount - (k * (bet_amount + y) ** -p) ** (1 / (1 - p))


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        pass


class FixedBetBettingStrategy(BettingStrategy):
    def calculate_direction(self, market: AgentMarket, estimate_p_yes: float) -> bool:
        if isinstance(market, ManifoldAgentMarket):
            calculator = ManifoldCalculator()
            manifold_data_model = get_manifold_market(market.id)
            return calculator.calculate_direction(manifold_data_model, estimate_p_yes)
        elif isinstance(market, OmenAgentMarket):
            calculator = OmenCalculator()
            sh = OmenSubgraphHandler()
            omen_market = sh.get_omen_market_by_market_id(
                market.market_maker_contract_address_checksummed
            )
            return calculator.calculate_direction(omen_market, estimate_p_yes)
        else:
            raise ValueError(f"Could not calculate direction for market {market}")

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        bet_amount = market.get_tiny_bet_amount().amount
        # ToDO - Define logic here

        direction = self.calculate_direction(market.current_p_yes, answer.p_yes)
        return TokenAmountAndDirection(
            amount=bet_amount,
            currency=market.currency,
            direction=direction,
        )


class KellyBettingStrategy(BettingStrategy):
    @staticmethod
    def get_max_bet_amount_for_market() -> float:
        # No difference between markets.
        return 10  # Mana or xDAI

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        max_bet_amount = self.get_max_bet_amount_for_market()
        kelly_bet = get_kelly_bet(
            max_bet_amount, market.current_p_yes, answer.p_yes, answer.confidence
        )
        return TokenAmountAndDirection(
            amount=kelly_bet.size,
            currency=market.currency,
            direction=kelly_bet.direction,
        )
