import getpass
import inspect
import os
import tempfile
import time
import typing as t
from datetime import datetime, timedelta
from enum import Enum
from functools import cached_property

from pydantic import BaseModel, BeforeValidator, computed_field
from typing_extensions import Annotated

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    MaxAccuracyBettingStrategy,
)
from prediction_market_agent_tooling.deploy.constants import (
    MARKET_TYPE_KEY,
    REPOSITORY_KEY,
)
from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import (
    gcp_function_is_active,
    gcp_resolve_api_keys_secrets,
)
from prediction_market_agent_tooling.gtypes import xDai, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    ProbabilisticAnswer,
    TokenAmount,
    TokenAmountAndDirection,
)
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    have_bet_on_market_since,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    is_minimum_required_balance,
    redeem_from_all_user_positions,
    withdraw_wxdai_to_xdai_to_keep_balance,
)
from prediction_market_agent_tooling.monitor.monitor_app import (
    MARKET_TYPE_TO_DEPLOYED_AGENT,
)
from prediction_market_agent_tooling.tools.is_predictable import is_predictable_binary
from prediction_market_agent_tooling.tools.langfuse_ import langfuse_context, observe
from prediction_market_agent_tooling.tools.utils import DatetimeWithTimezone, utcnow

MAX_AVAILABLE_MARKETS = 20
TRADER_TAG = "trader"


def to_boolean_outcome(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value

    elif isinstance(value, str):
        value = value.lower().strip()

        if value in {"true", "yes", "y", "1"}:
            return True

        elif value in {"false", "no", "n", "0"}:
            return False

        else:
            raise ValueError(f"Expected a boolean string, but got {value}")

    else:
        raise ValueError(f"Expected a boolean or a string, but got {value}")


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


Decision = Annotated[bool, BeforeValidator(to_boolean_outcome)]


class CantPayForGasError(ValueError):
    pass


class OutOfFundsError(ValueError):
    pass


class ProcessedMarket(BaseModel):
    answer: ProbabilisticAnswer
    amount: BetAmount


class AnsweredEnum(str, Enum):
    ANSWERED = "answered"
    NOT_ANSWERED = "not_answered"


class DeployableAgent:
    def __init__(
        self,
        enable_langfuse: bool = APIKeys().default_enable_langfuse,
    ) -> None:
        self.start_time = utcnow()
        self.enable_langfuse = enable_langfuse
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
            session_id=session_id
            or self.session_id,  # All traces within a single run execution will be grouped under a single session.
            version=version
            or APIKeys().LANGFUSE_DEPLOYMENT_VERSION,  # Optionally, mark the current deployment with version (e.g. add git commit hash during docker building).
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
        if "DeployableAgent" not in str(
            cls.__init__
        ) and "DeployableTraderAgent" not in str(cls.__init__):
            raise TypeError(
                "Cannot override __init__ method of deployable agent class, please override the `load` method to set up the agent."
            )

    def load(self) -> None:
        pass

    def deploy_local(
        self,
        market_type: MarketType,
        sleep_time: float,
        timeout: float,
    ) -> None:
        start_time = time.time()
        while True:
            self.run(market_type=market_type)
            time.sleep(sleep_time)
            if time.time() - start_time > timeout:
                break

    def deploy_gcp(
        self,
        repository: str,
        market_type: MarketType,
        api_keys: APIKeys,
        memory: int,
        labels: dict[str, str] | None = None,
        env_vars: dict[str, str] | None = None,
        secrets: dict[str, str] | None = None,
        cron_schedule: str | None = None,
        gcp_fname: str | None = None,
        start_time: DatetimeWithTimezone | None = None,
        timeout: int = 180,
    ) -> None:
        path_to_agent_file = os.path.relpath(inspect.getfile(self.__class__))

        entrypoint_function_name = "main"
        entrypoint_template = f"""
from {path_to_agent_file.replace("/", ".").replace(".py", "")} import *
import functions_framework
from prediction_market_agent_tooling.markets.markets import MarketType

@functions_framework.http
def {entrypoint_function_name}(request) -> str:
    {self.__class__.__name__}().run(market_type={market_type.__class__.__name__}.{market_type.name})
    return "Success"
"""

        gcp_fname = gcp_fname or self.get_gcloud_fname(market_type)

        # For labels, only hyphens (-), underscores (_), lowercase characters, and numbers are allowed in values.
        labels = (labels or {}) | {
            MARKET_TYPE_KEY: market_type.value,
        }
        env_vars = (env_vars or {}) | {
            REPOSITORY_KEY: repository,
        }
        secrets = secrets or {}

        env_vars |= api_keys.model_dump_public()
        secrets |= api_keys.model_dump_secrets()

        monitor_agent = MARKET_TYPE_TO_DEPLOYED_AGENT[market_type].from_api_keys(
            name=gcp_fname,
            start_time=start_time or utcnow(),
            api_keys=gcp_resolve_api_keys_secrets(api_keys),
        )
        env_vars |= monitor_agent.model_dump_prefixed()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as f:
            f.write(entrypoint_template)
            f.flush()

            fname = deploy_to_gcp(
                gcp_fname=gcp_fname,
                requirements_file=None,
                extra_deps=[repository],
                function_file=f.name,
                labels=labels,
                env_vars=env_vars,
                secrets=secrets,
                memory=memory,
                entrypoint_function_name=entrypoint_function_name,
                timeout=timeout,
            )

        # Check that the function is deployed
        if not gcp_function_is_active(fname):
            raise RuntimeError("Failed to deploy the function")

        # Run the function
        response = run_deployed_gcp_function(fname)
        if not response.ok:
            raise RuntimeError("Failed to run the deployed function")

        # Schedule the function
        if cron_schedule:
            schedule_deployed_gcp_function(fname, cron_schedule=cron_schedule)

    def run(self, market_type: MarketType) -> None:
        raise NotImplementedError("This method must be implemented by the subclass.")

    def get_gcloud_fname(self, market_type: MarketType) -> str:
        return f"{self.__class__.__name__.lower()}-{market_type}-{datetime.now().strftime('%Y-%m-%d--%H-%M-%S')}"


class DeployableTraderAgent(DeployableAgent):
    bet_on_n_markets_per_run: int = 1
    min_required_balance_to_operate: xDai | None = xdai_type(1)
    min_balance_to_keep_in_native_currency: xDai | None = xdai_type(0.1)
    strategy: BettingStrategy = MaxAccuracyBettingStrategy()
    allow_opposite_bets: bool = False

    def __init__(
        self,
        enable_langfuse: bool = APIKeys().default_enable_langfuse,
        place_bet: bool = True,
    ) -> None:
        super().__init__(enable_langfuse=enable_langfuse)
        self.place_bet = place_bet

    def initialize_langfuse(self) -> None:
        super().initialize_langfuse()
        # Auto-observe all the methods where it makes sense, so that subclassses don't need to do it manually.
        self.have_bet_on_market_since = observe()(self.have_bet_on_market_since)  # type: ignore[method-assign]
        self.verify_market = observe()(self.verify_market)  # type: ignore[method-assign]
        self.answer_binary_market = observe()(self.answer_binary_market)  # type: ignore[method-assign]
        self.calculate_bet_amount_and_direction = observe()(self.calculate_bet_amount_and_direction)  # type: ignore[method-assign]
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

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        amount_and_direction = self.strategy.calculate_bet_amount_and_direction(
            answer, market
        )
        if amount_and_direction.currency != market.currency:
            raise ValueError(
                f"Currency mismatch. Strategy yields {amount_and_direction.currency}, market has currency {market.currency}"
            )
        return amount_and_direction

    def update_langfuse_trace_by_processed_market(
        self, market_type: MarketType, processed_market: ProcessedMarket | None
    ) -> None:
        self.langfuse_update_current_trace(
            tags=[
                TRADER_TAG,
                (
                    AnsweredEnum.ANSWERED
                    if processed_market is not None
                    else AnsweredEnum.NOT_ANSWERED
                ),
                market_type.value,
            ]
        )

    def check_min_required_balance_to_operate(
        self,
        market_type: MarketType,
        check_for_gas: bool = True,
        check_for_trades: bool = True,
    ) -> None:
        api_keys = APIKeys()
        if (
            market_type == MarketType.OMEN
            and check_for_gas
            and not is_minimum_required_balance(
                api_keys.public_key,
                min_required_balance=xdai_type(0.001),
                sum_wxdai=False,
            )
        ):
            raise CantPayForGasError(
                f"{api_keys.public_key=} doesn't have enough xDai to pay for gas."
            )
        if self.min_required_balance_to_operate is None:
            return
        if (
            market_type == MarketType.OMEN
            and check_for_trades
            and not is_minimum_required_balance(
                api_keys.bet_from_address,
                min_required_balance=self.min_required_balance_to_operate,
            )
        ):
            raise OutOfFundsError(
                f"Minimum required balance {self.min_required_balance_to_operate} "
                f"for agent with address {api_keys.bet_from_address=} is not met."
            )

    def have_bet_on_market_since(self, market: AgentMarket, since: timedelta) -> bool:
        return have_bet_on_market_since(keys=APIKeys(), market=market, since=since)

    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        """
        Subclasses can implement their own logic instead of this one, or on top of this one.
        By default, it allows only markets where user didn't bet recently and it's a reasonable question.
        """
        if self.have_bet_on_market_since(market, since=timedelta(hours=24)):
            return False

        # Manifold allows to bet only on markets with probability between 1 and 99.
        if market_type == MarketType.MANIFOLD and not (1 < market.current_p_yes < 99):
            return False

        # Do as a last check, as it uses paid OpenAI API.
        if not is_predictable_binary(market.question):
            return False

        return True

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        """
        Answer the binary market. This method must be implemented by the subclass.
        """
        raise NotImplementedError("This method must be implemented by the subclass")

    def get_markets(
        self,
        market_type: MarketType,
        limit: int = MAX_AVAILABLE_MARKETS,
        sort_by: SortBy = SortBy.CLOSING_SOONEST,
        filter_by: FilterBy = FilterBy.OPEN,
    ) -> t.Sequence[AgentMarket]:
        cls = market_type.market_class
        # Fetch the soonest closing markets to choose from
        available_markets = cls.get_binary_markets(
            limit=limit, sort_by=sort_by, filter_by=filter_by
        )
        return available_markets

    def before_process_market(
        self, market_type: MarketType, market: AgentMarket
    ) -> None:
        self.update_langfuse_trace_by_market(market_type, market)

    def process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ) -> ProcessedMarket | None:
        self.before_process_market(market_type, market)

        if verify_market and not self.verify_market(market_type, market):
            logger.info(f"Market '{market.question}' doesn't meet the criteria.")
            self.update_langfuse_trace_by_processed_market(market_type, None)
            return None

        answer = self.answer_binary_market(market)

        if answer is None:
            logger.info(f"No answer for market '{market.question}'.")
            self.update_langfuse_trace_by_processed_market(market_type, None)
            return None

        amount_and_direction = self.calculate_bet_amount_and_direction(answer, market)

        if self.place_bet:
            logger.info(
                f"Placing bet on {market} with direction {amount_and_direction.direction} and amount {amount_and_direction.amount}"
            )

            if not self.allow_opposite_bets:
                logger.info(
                    f"Liquidating existing positions contrary to direction {amount_and_direction.direction}"
                )
                # If we have an existing position, sell it first if they bet on a different outcome.
                market.liquidate_existing_positions(amount_and_direction.direction)

            market.place_bet(
                amount=TokenAmount(
                    amount=amount_and_direction.amount,
                    currency=amount_and_direction.currency,
                ),
                outcome=amount_and_direction.direction,
            )

        self.after_process_market(market_type, market)

        processed_market = ProcessedMarket(
            answer=answer,
            amount=amount_and_direction,
        )
        self.update_langfuse_trace_by_processed_market(market_type, processed_market)

        return processed_market

    def after_process_market(
        self, market_type: MarketType, market: AgentMarket
    ) -> None:
        pass

    def before_process_markets(self, market_type: MarketType) -> None:
        """
        Executes actions that occur before bets are placed.
        """
        api_keys = APIKeys()
        if market_type == MarketType.OMEN:
            # First, check if we have enough xDai to pay for gas, there is no way of doing anything without it.
            self.check_min_required_balance_to_operate(
                market_type, check_for_trades=False
            )
            # Omen is specific, because the user (agent) needs to manually withdraw winnings from the market.
            redeem_from_all_user_positions(api_keys)
            # After redeeming, check if we have enough xDai to pay for gas and place bets.
            self.check_min_required_balance_to_operate(market_type)
            # Exchange wxdai back to xdai if the balance is getting low, so we can keep paying for fees.
            if self.min_balance_to_keep_in_native_currency is not None:
                withdraw_wxdai_to_xdai_to_keep_balance(
                    api_keys,
                    min_required_balance=self.min_balance_to_keep_in_native_currency,
                    withdraw_multiplier=2,
                )

    def process_markets(self, market_type: MarketType) -> None:
        """
        Processes bets placed by agents on a given market.
        """
        available_markets = self.get_markets(market_type)
        processed = 0

        for market in available_markets:
            # We need to check it again before each market bet, as the balance might have changed.
            self.check_min_required_balance_to_operate(market_type)

            processed_market = self.process_market(market_type, market)

            if processed_market is not None:
                processed += 1

            if processed == self.bet_on_n_markets_per_run:
                break

    def after_process_markets(self, market_type: MarketType) -> None:
        pass

    def run(self, market_type: MarketType) -> None:
        self.before_process_markets(market_type)
        self.process_markets(market_type)
        self.after_process_markets(market_type)
