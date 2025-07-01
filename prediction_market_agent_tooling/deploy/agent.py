import getpass
import time
import typing as t
from datetime import timedelta
from enum import Enum
from functools import cached_property

from pydantic import computed_field

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    MultiCategoricalMaxAccuracyBettingStrategy,
    TradeType,
)
from prediction_market_agent_tooling.deploy.trade_interval import (
    FixedInterval,
    TradeInterval,
)
from prediction_market_agent_tooling.gtypes import USD, OutcomeToken, xDai
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    ProcessedMarket,
    ProcessedTradedMarket,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
    ExistingPosition,
    PlacedTrade,
    ProbabilisticAnswer,
    Trade,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.omen import (
    send_keeping_token_to_eoa_xdai,
)
from prediction_market_agent_tooling.tools.custom_exceptions import (
    CantPayForGasError,
    OutOfFundsError,
)
from prediction_market_agent_tooling.tools.is_invalid import is_invalid
from prediction_market_agent_tooling.tools.is_predictable import is_predictable_binary
from prediction_market_agent_tooling.tools.langfuse_ import langfuse_context, observe
from prediction_market_agent_tooling.tools.tokens.main_token import (
    MINIMUM_NATIVE_TOKEN_IN_EOA_FOR_FEES,
)
from prediction_market_agent_tooling.tools.utils import (
    DatetimeUTC,
    check_not_none,
    utcnow,
)

MAX_AVAILABLE_MARKETS = 1000


def initialize_langfuse(enable_langfuse: bool) -> None:
    # Configure Langfuse singleton with our APIKeys.
    # If langfuse is disabled, it will just ignore all the calls, so no need to do if-else around the code.
    keys = APIKeys()
    if enable_langfuse:
        langfuse_context.configure(
            public_key=keys.langfuse_public_key,
            secret_key=keys.langfuse_secret_key.get_secret_value(),
            host=keys.langfuse_host,
            enabled=enable_langfuse,
        )
    else:
        langfuse_context.configure(enabled=enable_langfuse)


class AnsweredEnum(str, Enum):
    ANSWERED = "answered"
    NOT_ANSWERED = "not_answered"


class AgentTagEnum(str, Enum):
    PREDICTOR = "predictor"
    TRADER = "trader"


class DeployableAgent:
    """
    Subclass this class to create agent with standardized interface.
    """

    def __init__(
        self,
        enable_langfuse: bool = APIKeys().default_enable_langfuse,
    ) -> None:
        self.start_time = utcnow()
        self.enable_langfuse = enable_langfuse
        self.api_keys = APIKeys()
        self.initialize_langfuse()
        self.load()

    def initialize_langfuse(self) -> None:
        initialize_langfuse(self.enable_langfuse)

    def langfuse_update_current_trace(
        self,
        name: str | None = None,
        input: t.Any | None = None,
        output: t.Any | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        version: str | None = None,
        release: str | None = None,
        metadata: t.Any | None = None,
        tags: list[str] | None = None,
        public: bool | None = None,
    ) -> None:
        """
        Provide some useful default arguments when updating the current trace in our agents.
        """
        langfuse_context.update_current_trace(
            name=name,
            input=input,
            output=output,
            user_id=user_id or getpass.getuser(),
            session_id=session_id or self.session_id,
            # All traces within a single run execution will be grouped under a single session.
            version=version or APIKeys().LANGFUSE_DEPLOYMENT_VERSION,
            # Optionally, mark the current deployment with version (e.g. add git commit hash during docker building).
            release=release,
            metadata=metadata,
            tags=tags,
            public=public,
        )

    @computed_field  # type: ignore[prop-decorator] # Mypy issue: https://github.com/python/mypy/issues/14461
    @cached_property
    def session_id(self) -> str:
        # Each agent should be an unique class.
        return f"{self.__class__.__name__} - {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}"

    def __init_subclass__(cls, **kwargs: t.Any) -> None:
        if (
            "DeployableAgent" not in str(cls.__init__)
            and "DeployableTraderAgent" not in str(cls.__init__)
            and "DeployablePredictionAgent" not in str(cls.__init__)
        ):
            raise TypeError(
                "Cannot override __init__ method of deployable agent class, please override the `load` method to set up the agent."
            )

    def load(self) -> None:
        """
        Implement this method to load arbitrary instances needed across the whole run of the agent.

        Do not customize __init__ method.
        """

    def deploy_local(
        self,
        market_type: MarketType,
        sleep_time: float,
        run_time: float | None,
    ) -> None:
        """
        Run the agent in the forever cycle every `sleep_time` seconds, until the `run_time` is met.
        """
        start_time = time.time()
        while run_time is None or time.time() - start_time < run_time:
            self.run(market_type=market_type)
            time.sleep(sleep_time)

    def run(self, market_type: MarketType) -> None:
        """
        Run single iteration of the agent.
        """
        raise NotImplementedError("This method must be implemented by the subclass.")

    def get_gcloud_fname(self, market_type: MarketType) -> str:
        return f"{self.__class__.__name__.lower()}-{market_type}-{utcnow().strftime('%Y-%m-%d--%H-%M-%S')}"


class DeployablePredictionAgent(DeployableAgent):
    """
    Subclass this class to create your own prediction market agent.

    The agent will process markets and make predictions.
    """

    AGENT_TAG: AgentTagEnum = AgentTagEnum.PREDICTOR

    bet_on_n_markets_per_run: int = 1

    # Agent behaviour when fetching markets
    n_markets_to_fetch: int = MAX_AVAILABLE_MARKETS
    trade_on_markets_created_after: DatetimeUTC | None = None
    get_markets_sort_by: SortBy = SortBy.CLOSING_SOONEST
    get_markets_filter_by: FilterBy = FilterBy.OPEN

    # Agent behaviour when filtering fetched markets
    allow_invalid_questions: bool = False
    same_market_trade_interval: TradeInterval = FixedInterval(timedelta(hours=24))

    min_balance_to_keep_in_native_currency: xDai | None = (
        MINIMUM_NATIVE_TOKEN_IN_EOA_FOR_FEES
    )

    # Only Metaculus allows to post predictions without trading (buying/selling of outcome tokens).
    supported_markets: t.Sequence[MarketType] = [MarketType.METACULUS]

    def __init__(
        self,
        enable_langfuse: bool = APIKeys().default_enable_langfuse,
        store_predictions: bool = True,
    ) -> None:
        super().__init__(enable_langfuse=enable_langfuse)
        self.store_predictions = store_predictions

    def initialize_langfuse(self) -> None:
        super().initialize_langfuse()
        # Auto-observe all the methods where it makes sense, so that subclassses don't need to do it manually.
        self.verify_market = observe()(self.verify_market)  # type: ignore[method-assign]
        self.answer_binary_market = observe()(self.answer_binary_market)  # type: ignore[method-assign]
        self.answer_categorical_market = observe()(self.answer_categorical_market)  # type: ignore[method-assign]
        self.process_market = observe()(self.process_market)  # type: ignore[method-assign]

    def update_langfuse_trace_by_market(
        self, market_type: MarketType, market: AgentMarket
    ) -> None:
        self.langfuse_update_current_trace(
            # UI allows to do filtering by these.
            metadata={
                "agent_class": self.__class__.__name__,
                "market_id": market.id,
                "market_question": market.question,
                "market_outcomes": market.outcomes,
            },
        )

    def update_langfuse_trace_by_processed_market(
        self, market_type: MarketType, processed_market: ProcessedMarket | None
    ) -> None:
        self.langfuse_update_current_trace(
            tags=[
                self.AGENT_TAG,
                (
                    AnsweredEnum.ANSWERED
                    if processed_market is not None
                    else AnsweredEnum.NOT_ANSWERED
                ),
                market_type.value,
            ]
        )

    @property
    def agent_name(self) -> str:
        return self.__class__.__name__

    def check_min_required_balance_to_operate(self, market_type: MarketType) -> None:
        api_keys = APIKeys()

        if not market_type.market_class.verify_operational_balance(api_keys):
            raise CantPayForGasError(
                f"{api_keys=} doesn't have enough operational balance."
            )

    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        """
        Subclasses can implement their own logic instead of this one, or on top of this one.
        By default, it allows only markets where user didn't bet recently and it's a reasonable question.
        """
        if market.have_bet_on_market_since(
            keys=APIKeys(), since=self.same_market_trade_interval.get(market=market)
        ):
            logger.info(
                f"Market already bet on within {self.same_market_trade_interval}."
            )
            return False

        # Manifold allows to bet only on markets with probability between 1 and 99.
        if market_type == MarketType.MANIFOLD:
            probability_yes = market.probabilities[
                market.get_outcome_str_from_bool(True)
            ]
            if not probability_yes or not 1 < probability_yes < 99:
                logger.info("Manifold's market probability not in the range 1-99.")
                return False

        # Do as a last check, as it uses paid OpenAI API.
        if not is_predictable_binary(market.question):
            logger.info("Market question is not predictable.")
            return False

        if not self.allow_invalid_questions and is_invalid(market.question):
            logger.info("Market question is invalid.")
            return False

        return True

    def answer_categorical_market(
        self, market: AgentMarket
    ) -> CategoricalProbabilisticAnswer | None:
        raise NotImplementedError("This method must be implemented by the subclass")

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        """
        Answer the binary market.

        If this method is not overridden by the subclass, it will fall back to using
        answer_categorical_market(). Therefore, subclasses only need to implement
        answer_categorical_market() if they want to handle both types of markets.
        """
        raise NotImplementedError(
            "Either this method, or answer_categorical_market, must be implemented by the subclass."
        )

    @property
    def fetch_categorical_markets(self) -> bool:
        # Check if the subclass has implemented the answer_categorical_market method, if yes, fetch categorical markets as well.
        if (
            self.answer_categorical_market.__wrapped__.__func__  # type: ignore[attr-defined] # This works just fine, but mypy doesn't know about it for some reason.
            is not DeployablePredictionAgent.answer_categorical_market
        ):
            return True
        return False

    def get_markets(
        self,
        market_type: MarketType,
    ) -> t.Sequence[AgentMarket]:
        """
        Override this method to customize what markets will fetch for processing.
        """
        cls = market_type.market_class
        # Fetch the soonest closing markets to choose from
        available_markets = cls.get_markets(
            limit=self.n_markets_to_fetch,
            sort_by=self.get_markets_sort_by,
            filter_by=self.get_markets_filter_by,
            created_after=self.trade_on_markets_created_after,
            fetch_categorical_markets=self.fetch_categorical_markets,
        )
        return available_markets

    def before_process_market(
        self, market_type: MarketType, market: AgentMarket
    ) -> None:
        """
        Executed before processing of each market.
        """
        api_keys = APIKeys()

        if market_type.is_blockchain_market:
            # Exchange wxdai back to xdai if the balance is getting low, so we can keep paying for fees.
            if self.min_balance_to_keep_in_native_currency is not None:
                send_keeping_token_to_eoa_xdai(
                    api_keys,
                    min_required_balance=self.min_balance_to_keep_in_native_currency,
                    multiplier=3,
                )

    def build_answer(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ) -> CategoricalProbabilisticAnswer | None:
        if verify_market and not self.verify_market(market_type, market):
            logger.info(f"Market '{market.question}' doesn't meet the criteria.")
            return None

        logger.info(f"Answering market '{market.question}'.")

        if market.is_binary:
            try:
                binary_answer = self.answer_binary_market(market)
                return (
                    CategoricalProbabilisticAnswer.from_probabilistic_answer(
                        binary_answer,
                        market.outcomes,
                    )
                    if binary_answer is not None
                    else None
                )
            except NotImplementedError:
                logger.info(
                    "answer_binary_market() not implemented, falling back to answer_categorical_market()"
                )

        return self.answer_categorical_market(market)

    def verify_answer_outcomes(
        self, market: AgentMarket, answer: CategoricalProbabilisticAnswer
    ) -> None:
        outcomes_from_prob_map = list(answer.probabilities.keys())

        if any(
            outcome_from_answer not in market.outcomes
            for outcome_from_answer in outcomes_from_prob_map
        ):
            raise ValueError(
                f"Some of generated outcomes ({outcomes_from_prob_map=}) in probability map doesn't match with market's outcomes ({market.outcomes=})."
            )

        if any(
            market_outcome not in outcomes_from_prob_map
            for market_outcome in market.outcomes
        ):
            logger.warning(
                f"Some of market's outcomes ({market.outcomes=}) isn't included in the probability map ({outcomes_from_prob_map=})."
            )

    def process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ) -> ProcessedMarket | None:
        self.update_langfuse_trace_by_market(market_type, market)
        logger.info(
            f"Processing market {market.question=} from {market.url=} with liquidity {market.get_liquidity()}."
        )

        answer = self.build_answer(
            market=market, market_type=market_type, verify_market=verify_market
        )
        if answer is not None:
            self.verify_answer_outcomes(market=market, answer=answer)

        processed_market = (
            ProcessedMarket(answer=answer) if answer is not None else None
        )

        self.update_langfuse_trace_by_processed_market(market_type, processed_market)
        logger.info(
            f"Processed market {market.question=} from {market.url=} with {processed_market=}."
        )
        return processed_market

    def after_process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        processed_market: ProcessedMarket | None,
    ) -> None:
        """
        Executed after processing of each market.
        """
        keys = APIKeys()
        if self.store_predictions:
            market.store_prediction(
                processed_market=processed_market, keys=keys, agent_name=self.agent_name
            )
        else:
            logger.info(
                f"Prediction {processed_market} not stored because {self.store_predictions=}."
            )

    def before_process_markets(self, market_type: MarketType) -> None:
        """
        Executed before market processing loop starts.
        """
        api_keys = APIKeys()
        self.check_min_required_balance_to_operate(market_type)
        market_type.market_class.redeem_winnings(api_keys)

    def process_markets(self, market_type: MarketType) -> None:
        """
        Processes bets placed by agents on a given market.
        """
        logger.info("Start processing of markets.")
        available_markets = self.get_markets(market_type)

        logger.info(
            f"Fetched {len(available_markets)=} markets to process, going to process {self.bet_on_n_markets_per_run=}."
        )
        processed = 0

        for market_idx, market in enumerate(available_markets):
            logger.info(
                f"Going to process market {market.url}: {market_idx+1} / {len(available_markets)}."
            )
            self.before_process_market(market_type, market)
            processed_market = self.process_market(market_type, market)
            self.after_process_market(market_type, market, processed_market)

            if processed_market is not None:
                processed += 1

            if processed == self.bet_on_n_markets_per_run:
                break

        logger.info(
            f"All markets processed. Successfully processed {processed}/{len(available_markets)}."
        )

    def after_process_markets(self, market_type: MarketType) -> None:
        """
        Executed after market processing loop ends.
        """

    def run(self, market_type: MarketType) -> None:
        if market_type not in self.supported_markets:
            raise ValueError(
                f"Only {self.supported_markets} are supported by this agent."
            )
        self.before_process_markets(market_type)
        self.process_markets(market_type)
        self.after_process_markets(market_type)


class DeployableTraderAgent(DeployablePredictionAgent):
    """
    Subclass this class to create your own prediction market trading agent.

    The agent will process markets, make predictions and place trades (bets) based off these predictions.
    """

    AGENT_TAG: AgentTagEnum = AgentTagEnum.TRADER

    # These markets require place of bet, not just predictions.
    supported_markets: t.Sequence[MarketType] = [
        MarketType.OMEN,
        MarketType.MANIFOLD,
        MarketType.POLYMARKET,
        MarketType.SEER,
    ]

    def __init__(
        self,
        enable_langfuse: bool = APIKeys().default_enable_langfuse,
        store_predictions: bool = True,
        store_trades: bool = True,
        place_trades: bool = True,
    ) -> None:
        super().__init__(
            enable_langfuse=enable_langfuse, store_predictions=store_predictions
        )
        self.store_trades = store_trades
        self.place_trades = place_trades

    def initialize_langfuse(self) -> None:
        super().initialize_langfuse()
        # Auto-observe all the methods where it makes sense, so that subclassses don't need to do it manually.
        self.build_trades = observe()(self.build_trades)  # type: ignore[method-assign]

    def check_min_required_balance_to_trade(self, market: AgentMarket) -> None:
        api_keys = APIKeys()

        # Get the strategy to know how much it will bet.
        strategy = self.get_betting_strategy(market)
        # Have a little bandwidth after the bet.
        min_required_balance_to_trade = strategy.maximum_possible_bet_amount * 1.01

        if market.get_trade_balance(api_keys) < min_required_balance_to_trade:
            raise OutOfFundsError(
                f"Minimum required balance {min_required_balance_to_trade} for agent {api_keys.bet_from_address=} is not met."
            )

    @staticmethod
    def get_total_amount_to_bet(market: AgentMarket) -> USD:
        user_id = market.get_user_id(api_keys=APIKeys())

        total_amount = market.get_in_usd(market.get_tiny_bet_amount())
        existing_position = market.get_position(user_id=user_id)
        if existing_position and existing_position.total_amount_current > USD(0):
            total_amount += existing_position.total_amount_current
        return total_amount

    def get_betting_strategy(self, market: AgentMarket) -> BettingStrategy:
        """
        Override this method to customize betting strategy of your agent.

        Given the market and prediction, agent uses this method to calculate optimal outcome and bet size.
        """
        total_amount = self.get_total_amount_to_bet(market)
        return MultiCategoricalMaxAccuracyBettingStrategy(
            max_position_amount=total_amount
        )

    def build_trades(
        self,
        market: AgentMarket,
        answer: CategoricalProbabilisticAnswer,
        existing_position: ExistingPosition | None,
    ) -> list[Trade]:
        strategy = self.get_betting_strategy(market=market)
        trades = strategy.calculate_trades(existing_position, answer, market)
        return trades

    def before_process_market(
        self, market_type: MarketType, market: AgentMarket
    ) -> None:
        super().before_process_market(market_type, market)
        self.check_min_required_balance_to_trade(market)

    def process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ) -> ProcessedTradedMarket | None:
        processed_market = super().process_market(market_type, market, verify_market)
        if processed_market is None:
            return None

        api_keys = APIKeys()
        user_id = market.get_user_id(api_keys=api_keys)

        existing_position = market.get_position(user_id=user_id)
        trades = self.build_trades(
            market=market,
            answer=processed_market.answer,
            existing_position=existing_position,
        )

        # It can take quite some time before agent processes all the markets, recheck here if the market didn't get closed in the meantime, to not error out completely.
        # Unfortunately, we can not just add some room into closing time of the market while fetching them, because liquidity can be removed at any time by the liquidity providers.
        still_tradeable = market.can_be_traded()
        if not still_tradeable:
            logger.warning(
                f"Market {market.question=} ({market.url}) was selected to processing, but is not tradeable anymore."
            )

        placed_trades = []
        for trade in trades:
            logger.info(f"Executing trade {trade} on market {market.id} ({market.url})")

            if self.place_trades and still_tradeable:
                match trade.trade_type:
                    case TradeType.BUY:
                        id = market.buy_tokens(
                            outcome=trade.outcome, amount=trade.amount
                        )
                    case TradeType.SELL:
                        # Get actual value of the position we are going to sell, and if it's less than we wanted to sell, simply sell all of it.
                        current_position = check_not_none(
                            market.get_position(user_id),
                            "Should exists if we are going to sell outcomes.",
                        )

                        current_position_value_usd = current_position.amounts_current[
                            trade.outcome
                        ]
                        amount_to_sell: USD | OutcomeToken
                        if current_position_value_usd <= trade.amount:
                            logger.warning(
                                f"Current value of position {trade.outcome=}, {current_position_value_usd=} is less than the desired selling amount {trade.amount=}. Selling all."
                            )
                            # In case the agent asked to sell too much, provide the amount to sell as all outcome tokens, instead of in USD, to minimze fx fluctuations when selling.
                            amount_to_sell = current_position.amounts_ot[trade.outcome]
                        else:
                            amount_to_sell = trade.amount
                        id = market.sell_tokens(
                            outcome=trade.outcome,
                            amount=amount_to_sell,
                        )
                    case _:
                        raise ValueError(f"Unexpected trade type {trade.trade_type}.")
                placed_trades.append(PlacedTrade.from_trade(trade, id))
            else:
                logger.info(
                    f"Trade execution skipped because, {self.place_trades=} or {still_tradeable=}."
                )

        traded_market = ProcessedTradedMarket(
            answer=processed_market.answer, trades=placed_trades
        )
        logger.info(f"Traded market {market.question=} from {market.url=}.")
        return traded_market

    def after_process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        processed_market: ProcessedMarket | None,
    ) -> None:
        api_keys = APIKeys()
        super().after_process_market(
            market_type,
            market,
            processed_market,
        )
        if isinstance(processed_market, ProcessedTradedMarket):
            if self.store_trades:
                market.store_trades(processed_market, api_keys, self.agent_name)
            else:
                logger.info(
                    f"Trades {processed_market.trades} not stored because {self.store_trades=}."
                )
