from datetime import datetime, timedelta

from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey, xDai
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.categorize import infer_category
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    get_binary_markets,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OMEN_DEFAULT_MARKET_FEE,
    get_omen_binary_markets,
    omen_create_market_tx,
)
from prediction_market_agent_tooling.tools.is_predictable import is_predictable
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import private_key_to_public_key


def omen_replicate_from_tx(
    market_type: MarketType,
    n_to_replicate: int,
    initial_funds: xDai,
    from_private_key: PrivateKey,
    last_n_omen_markets_to_fetch: int = 1000,
    close_time_before: datetime | None = None,
    auto_deposit: bool = False,
) -> list[ChecksumAddress]:
    from_address = private_key_to_public_key(from_private_key)

    already_created_markets = get_omen_binary_markets(
        limit=last_n_omen_markets_to_fetch,
        creator=from_address,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.NONE,
    )
    if len(already_created_markets) == last_n_omen_markets_to_fetch:
        raise ValueError(
            "TODO: Switch to paged version (once available) to fetch all markets, we don't know if we aren't creating duplicates now."
        )

    markets = get_binary_markets(
        # Polymarket is slow to get, so take only 10 candidates for him.
        10 if market_type == MarketType.POLYMARKET else 100,
        market_type,
        filter_by=FilterBy.OPEN,
        sort_by=SortBy.NONE,
        excluded_questions=set(m.question_title for m in already_created_markets),
    )
    markets_sorted = sorted(
        markets,
        key=lambda m: m.volume or 0,
        reverse=True,
    )
    markets_to_replicate = [
        m
        for m in markets_sorted
        if close_time_before is None
        or (m.close_time is not None and m.close_time <= close_time_before)
    ]
    if not markets_to_replicate:
        print(f"No markets found for {market_type}")
        return []

    print(f"Found {len(markets_to_replicate)} markets to replicate.")

    # Get a set of possible categories from existing markets (but created by anyone, not just your agent)
    existing_categories = set(
        m.category
        for m in get_omen_binary_markets(
            limit=last_n_omen_markets_to_fetch,
            sort_by=SortBy.NEWEST,
            filter_by=FilterBy.NONE,
        )
    )

    created_addresses: list[ChecksumAddress] = []

    for market in markets_to_replicate:
        if market.close_time is None:
            print(
                f"Skipping `{market.question}` because it's missing the closing time."
            )
            continue

        # According to Omen's recommendation, closing time of the market should be at least 6 days after the outcome is known.
        # That is because at the closing time, the question will open on Realitio, and we don't want it to be resolved as unknown/invalid.
        safe_closing_time = market.close_time + timedelta(days=6)
        # Force at least 48 hours of time where the resolution is unknown.
        soonest_allowed_resolution_known_time = utcnow() + timedelta(hours=48)
        if market.close_time <= soonest_allowed_resolution_known_time:
            print(
                f"Skipping `{market.question}` because it closes sooner than {soonest_allowed_resolution_known_time}."
            )
            continue

        latest_allowed_resolution_known_time = utcnow() + timedelta(days=365)
        if market.close_time > latest_allowed_resolution_known_time:
            print(
                f"Skipping `{market.question}` because it closes later than {latest_allowed_resolution_known_time}."
            )
            continue

        # Do as the last step, becuase it calls OpenAI (costly & slow).
        if not is_predictable(market.question):
            print(
                f"Skipping `{market.question}` because it seems to not be predictable."
            )
            continue

        category = infer_category(market.question, existing_categories)
        market_address = omen_create_market_tx(
            initial_funds=initial_funds,
            fee=OMEN_DEFAULT_MARKET_FEE,
            question=market.question,
            closing_time=safe_closing_time,
            category=category,
            language="en",
            from_private_key=from_private_key,
            outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
            auto_deposit=auto_deposit,
        )
        created_addresses.append(market_address)
        print(
            f"Created `https://aiomen.eth.limo/#/{market_address}` for `{market.question}` in category {category} out of {market.url}."
        )

        if len(created_addresses) >= n_to_replicate:
            print(f"Replicated {len(created_addresses)} from {market_type}, breaking.")
            break

    return created_addresses
