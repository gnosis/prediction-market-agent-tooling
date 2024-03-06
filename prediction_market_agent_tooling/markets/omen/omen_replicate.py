from datetime import datetime, timedelta

import pytz

from prediction_market_agent_tooling.benchmark.utils import (
    MarketFilter,
    MarketSort,
    MarketSource,
    get_markets,
)
from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey, xDai
from prediction_market_agent_tooling.markets.categorize import infer_category
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


def omen_replicate_from_tx(
    market_source: MarketSource,
    n_to_replicate: int,
    initial_funds: xDai,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    last_n_omen_markets_to_fetch: int = 1000,
    close_time_before: datetime | None = None,
    auto_deposit: bool = False,
) -> list[ChecksumAddress]:
    already_created_markets = get_omen_binary_markets(
        limit=last_n_omen_markets_to_fetch,
        creator=from_address,
    )
    if len(already_created_markets) == last_n_omen_markets_to_fetch:
        raise ValueError(
            "TODO: Switch to paged version (once available) to fetch all markets, we don't know if we aren't creating duplicates now."
        )

    markets = get_markets(
        100,
        market_source,
        filter_=(
            MarketFilter.closing_this_month
            if market_source == MarketSource.MANIFOLD
            else MarketFilter.open
        ),
        sort=MarketSort.newest if market_source == MarketSource.MANIFOLD else None,
        excluded_questions=set(m.question for m in already_created_markets),
    )
    markets_sorted = sorted(
        markets,
        key=lambda m: m.volume,
        reverse=True,
    )
    markets_to_replicate = [
        m
        for m in markets_sorted
        if close_time_before is None or m.close_time <= close_time_before
    ]
    if not markets_to_replicate:
        print(f"No markets found for {market_source}")
        return []

    print(f"Found {len(markets_to_replicate)} markets to replicate.")

    # Get a set of possible categories from existing markets (but created by anyone, not just your agent)
    existing_categories = set(
        m.category
        for m in get_omen_binary_markets(
            limit=last_n_omen_markets_to_fetch,
        )
    )

    created_addresses: list[ChecksumAddress] = []

    for market in markets_to_replicate:
        if not is_predictable(market.question):
            print(
                f"Skipping `{market.question}` because it seems to not be predictable."
            )
            continue
        # Close a day sooner than the original market, because of timezone differences.
        closing_time = market.close_time - timedelta(hours=24)
        # Force at least 24 hours of open market.
        soonest_allowed_closing_time = datetime.utcnow().replace(
            tzinfo=pytz.UTC
        ) + timedelta(hours=24)
        if closing_time <= soonest_allowed_closing_time:
            print(
                f"Skipping `{market.question}` because it closes sooner than {soonest_allowed_closing_time}."
            )
            continue
        category = infer_category(market.question, existing_categories)
        market_address = omen_create_market_tx(
            initial_funds=initial_funds,
            fee=OMEN_DEFAULT_MARKET_FEE,
            question=market.question,
            closing_time=closing_time,
            category=category,
            language="en",
            from_address=from_address,
            from_private_key=from_private_key,
            outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
            auto_deposit=auto_deposit,
        )
        created_addresses.append(market_address)
        print(
            f"Created `https://aiomen.eth.limo/#/{market_address}` for `{market.question}` in category {category} out of {market.url}."
        )

        if len(created_addresses) >= n_to_replicate:
            print(
                f"Replicated {len(created_addresses)} from {market_source}, breaking."
            )
            break

    return created_addresses
