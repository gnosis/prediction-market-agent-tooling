import inspect
import os
import tempfile
import time
import typing as t
from datetime import datetime, timedelta

from pydantic import BaseModel, BeforeValidator
from typing_extensions import Annotated

from prediction_market_agent_tooling.config import APIKeys, PrivateCredentials
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
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import BetAmount
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    have_bet_on_market_since,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    redeem_from_all_user_positions,
)
from prediction_market_agent_tooling.monitor.langfuse.langfuse_wrapper import (
    LangfuseWrapper,
)
from prediction_market_agent_tooling.monitor.monitor_app import (
    MARKET_TYPE_TO_DEPLOYED_AGENT,
)
from prediction_market_agent_tooling.tools.is_predictable import is_predictable_binary
from prediction_market_agent_tooling.tools.utils import DatetimeWithTimezone, utcnow

MAX_AVAILABLE_MARKETS = 20


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


Decision = Annotated[bool, BeforeValidator(to_boolean_outcome)]


class Answer(BaseModel):
    decision: Decision  # Warning: p_yes > 0.5 doesn't necessarily mean decision is True! For example, if our p_yes is 55%, but market's p_yes is 80%, then it might be profitable to bet on False.
    p_yes: Probability
    confidence: float
    reasoning: str | None = None

    @property
    def p_no(self) -> Probability:
        return Probability(1 - self.p_yes)


class DeployableRunAgent:
    def __init__(self) -> None:
        self.langfuse_wrapper = LangfuseWrapper(agent_name=self.__class__.__name__)
        self.load()

    def __init_subclass__(cls, **kwargs: t.Any) -> None:
        if "DeployableRunAgent" not in str(
            cls.__init__
        ) and "DeployableBetAgent" not in str(cls.__init__):
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


class DeployableBetAgent(DeployableRunAgent):
    bet_on_n_markets_per_run: int = 1

    def __init__(self, place_bet: bool = True) -> None:
        super().__init__()
        self.place_bet = place_bet

    def have_bet_on_market_since(self, market: AgentMarket, since: timedelta) -> bool:
        return have_bet_on_market_since(keys=APIKeys(), market=market, since=since)

    def pick_markets(self, markets: t.Sequence[AgentMarket]) -> t.Sequence[AgentMarket]:
        """
        Subclasses can implement their own logic instead of this one, or on top of this one.
        By default, it picks only the first {n_markets_per_run} markets where user didn't bet recently and it's a reasonable question.
        """
        picked: list[AgentMarket] = []

        for market in markets:
            if len(picked) >= self.bet_on_n_markets_per_run:
                break

            if self.have_bet_on_market_since(market, since=timedelta(hours=24)):
                continue

            # Do as a last check, as it uses paid OpenAI API.
            if not is_predictable_binary(market.question):
                continue

            picked.append(market)

        return picked

    def answer_binary_market(self, market: AgentMarket) -> Answer | None:
        """
        Answer the binary market. This method must be implemented by the subclass.
        """
        raise NotImplementedError("This method must be implemented by the subclass")

    def calculate_bet_amount(self, answer: Answer, market: AgentMarket) -> BetAmount:
        """
        Calculate the bet amount. By default, it returns the minimum bet amount.
        """
        return market.get_tiny_bet_amount()

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

    def before(self, market_type: MarketType) -> None:
        """
        Executes actions that occur before bets are placed.
        """
        private_credentials = PrivateCredentials.from_api_keys(APIKeys())

        if market_type == MarketType.OMEN:
            # Omen is specific, because the user (agent) needs to manually withdraw winnings from the market.
            redeem_from_all_user_positions(private_credentials)

    def process_bets(self, market_type: MarketType) -> None:
        """
        Processes bets placed by agents on a given market.
        """
        available_markets = self.get_markets(market_type)
        markets = self.pick_markets(available_markets)
        for market in markets:
            result = self.answer_binary_market(market)
            if result is None:
                logger.debug(f"Skipping market {market} as no answer was provided")
                continue
            if self.place_bet:
                amount = self.calculate_bet_amount(result, market)
                logger.debug(
                    f"Placing bet on {market} with result {result} and amount {amount}"
                )
                market.place_bet(
                    amount=amount,
                    outcome=result.decision,
                )

    def after(self, market_type: MarketType) -> None:
        pass

    def run(self, market_type: MarketType) -> None:
        self.before(market_type)
        self.process_bets(market_type)
        self.after(market_type)
