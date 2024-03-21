from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.manifold.utils import (
    find_resolution_on_manifold,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.markets.omen.omen import get_omen_binary_markets
from prediction_market_agent_tooling.markets.polymarket.utils import (
    find_resolution_on_polymarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import private_key_to_public_key


def omen_resolve_all_markets_based_on_others_tx(
    from_private_key: PrivateKey,
    last_n_omen_markets_to_fetch: int = 1000,
) -> list[ChecksumAddress]:
    # Fetch markets created by us that are already open for the final outcome.
    created_already_opened_markets = get_omen_binary_markets(
        limit=last_n_omen_markets_to_fetch,
        creator=private_key_to_public_key(from_private_key),
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.NONE,
        opened_before=utcnow(),
    )
    if len(created_already_opened_markets) == last_n_omen_markets_to_fetch:
        raise ValueError(
            "TODO: Switch to paged version (once available) to fetch all markets, we don't know if we aren't creating duplicates now."
        )

    # Filter for only markets without any outcome proposal.
    created_already_opened_without_set_outcome = [
        m for m in created_already_opened_markets if not m.has_bonded_outcome
    ]

    resolved_addressses: list[ChecksumAddress] = []

    for market in created_already_opened_without_set_outcome:
        resolution = find_resolution_on_other_markets(market)
        if resolution is not None:
            omen_resolve_market_tx(from_private_key, market, resolution)

    return resolved_addressses


def omen_resolve_market_tx(
    from_private_key: PrivateKey,
    market: OmenMarket,
    resolution: Resolution,
) -> None:
    # TODO: Finish this.
    pass


def find_resolution_on_other_markets(market: OmenMarket) -> Resolution | None:
    resolution: Resolution | None = None

    for market_type in MarketType:
        # We are going to resolve it on Omen, so we can't find the answer there.
        if market_type == MarketType.OMEN:
            continue

        elif market_type == MarketType.MANIFOLD:
            resolution = find_resolution_on_manifold(market.question)

        elif market_type == MarketType.POLYMARKET:
            resolution = find_resolution_on_polymarket(market.question)

        else:
            raise ValueError(
                f"Unknown market type {market_type} in replication resolving."
            )

        if resolution is not None:
            return resolution

    return resolution
