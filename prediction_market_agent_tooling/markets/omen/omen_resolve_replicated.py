from prediction_market_agent_tooling.gtypes import (
    HexAddress,
    HexBytes,
    PrivateKey,
    xDai,
)
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.manifold.utils import (
    find_resolution_on_manifold,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.markets.omen.omen import (
    OMEN_DEFAULT_REALITIO_BOND_VALUE,
    get_omen_binary_markets,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenRealitioContract,
)
from prediction_market_agent_tooling.markets.polymarket.utils import (
    find_resolution_on_polymarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import (
    private_key_to_public_key,
    xdai_to_wei,
)


def omen_resolve_all_markets_based_on_others_tx(
    from_private_key: PrivateKey,
    last_n_omen_markets_to_fetch: int = 1000,
) -> list[HexAddress]:
    # Fetch markets created by us that are already open for the final outcome.
    created_already_opened_markets = get_omen_binary_markets(
        limit=last_n_omen_markets_to_fetch,
        creator=private_key_to_public_key(from_private_key),
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.NONE,
        opened_before=utcnow(),
    )
    print(f"Found {len(created_already_opened_markets)} markets created by us.")
    if len(created_already_opened_markets) == last_n_omen_markets_to_fetch:
        raise ValueError(
            "TODO: Switch to paged version (once available) to fetch all markets, we don't know if we aren't creating duplicates now."
        )

    # Filter for only markets without any outcome proposal.
    # TODO: Switch to on-graph filtering after subground PR is in.
    created_already_opened_without_set_outcome = [
        m for m in created_already_opened_markets if not m.has_bonded_outcome
    ]
    print(
        f"Filtered down to {len(created_already_opened_without_set_outcome)} markets that don't have any resolution yet."
    )

    resolved_addressses: list[HexAddress] = []

    for market in created_already_opened_without_set_outcome:
        print(f"Looking into {market.id=} {market.question_title=}")
        resolution = find_resolution_on_other_markets(market)
        if resolution is not None:
            print(f"Found resolution {resolution.value=} for {market.id=}")
            omen_resolve_market_tx(
                market, resolution, OMEN_DEFAULT_REALITIO_BOND_VALUE, from_private_key
            )
            resolved_addressses.append(market.id)

    return resolved_addressses


def omen_resolve_market_tx(
    market: OmenMarket,
    resolution: Resolution,
    bond: xDai,
    from_private_key: PrivateKey,
) -> None:
    realitio_contract = OmenRealitioContract()

    realitio_contract.submitAnswer(
        question_id=HexBytes(market.question.id),  # TODO: Remove HexBytes.
        answer=resolution.value,
        outcomes=market.question.outcomes,
        bond=xdai_to_wei(bond),
        from_private_key=from_private_key,
    )


def find_resolution_on_other_markets(market: OmenMarket) -> Resolution | None:
    resolution: Resolution | None = None

    for market_type in MarketType:
        match market_type:
            case MarketType.OMEN:
                # We are going to resolve it on Omen, so we can't find the answer there.
                continue

            case MarketType.MANIFOLD:
                resolution = find_resolution_on_manifold(market.question)

            case MarketType.POLYMARKET:
                resolution = find_resolution_on_polymarket(market.question)

            case _:
                raise ValueError(
                    f"Unknown market type {market_type} in replication resolving."
                )

        if resolution is not None:
            return resolution

    return resolution
