from datetime import timedelta

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import HexAddress, PrivateKey, xDai
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
    OmenOracleContract,
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


class FinalizeAndResolveResult(BaseModel):
    finalized: list[HexAddress]
    resolved: list[HexAddress]


def omen_finalize_and_resolve_all_markets_based_on_others_tx(
    from_private_key: PrivateKey,
) -> FinalizeAndResolveResult:
    public_key = private_key_to_public_key(from_private_key)

    # Just to be friendly with timezones.
    before = utcnow() - timedelta(hours=8)

    # Fetch markets created by us that are already open, but no answer was submitted yet.
    created_opened_markets = get_omen_binary_markets(
        limit=None,
        creator=public_key,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.NONE,
        opened_before=before,
        finalized=False,
    )
    # Finalize them (set answer on Realitio).
    finalized_markets = finalize_markets(
        created_opened_markets, from_private_key=from_private_key
    )

    # Fetch markets created by us that are already open, and we already submitted an answer more than a day ago, but they aren't resolved yet.
    created_finalized_markets = get_omen_binary_markets(
        limit=None,
        creator=public_key,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.NONE,
        finalized_before=before,
        resolved=False,
    )
    # Resolve them (resolve them on Oracle).
    resolved_markets = resolve_markets(
        created_finalized_markets, from_private_key=from_private_key
    )

    # TODO: Claim winnings on Realitio after resolution.

    return FinalizeAndResolveResult(
        finalized=finalized_markets, resolved=resolved_markets
    )


def finalize_markets(
    markets: list[OmenMarket], from_private_key: PrivateKey
) -> list[HexAddress]:
    finalized_markets: list[HexAddress] = []

    for market in markets:
        print(f"Looking into {market.url=} {market.question_title=}")
        resolution = find_resolution_on_other_markets(market)

        if resolution is None:
            print(f"Error: No resolution found for {market.url=}")

        elif resolution in (Resolution.YES, Resolution.NO):
            print(f"Found resolution {resolution.value=} for {market.url=}")
            omen_submit_answer_market_tx(
                market, resolution, OMEN_DEFAULT_REALITIO_BOND_VALUE, from_private_key
            )
            finalized_markets.append(market.id)
            print(f"Resolved {market.url=}")

        else:
            print(f"Error: Invalid resolution found, {resolution=}, for {market.url=}")

    return finalized_markets


def resolve_markets(
    markest: list[OmenMarket], from_private_key: PrivateKey
) -> list[HexAddress]:
    resolved_markets: list[HexAddress] = []

    for market in markest:
        print(f"Resolving {market.url=} {market.question_title=}")
        omen_resolve_market_tx(market, from_private_key)
        resolved_markets.append(market.id)

    return resolved_markets


def omen_submit_answer_market_tx(
    market: OmenMarket,
    resolution: Resolution,
    bond: xDai,
    from_private_key: PrivateKey,
) -> None:
    """
    After the answer is submitted, there is 24h waiting period where the answer can be challenged by others.
    And after the period is over, you need to resolve the market using `omen_resolve_market_tx`.
    """
    realitio_contract = OmenRealitioContract()
    realitio_contract.submitAnswer(
        question_id=market.question.id,
        answer=resolution.value,
        outcomes=market.question.outcomes,
        bond=xdai_to_wei(bond),
        from_private_key=from_private_key,
    )


def omen_resolve_market_tx(
    market: OmenMarket,
    from_private_key: PrivateKey,
) -> None:
    """
    Market can be resolved 24h after last answer was submitted via `omen_submit_answer_market_tx`.
    """
    oracle_contract = OmenOracleContract()
    oracle_contract.resolve(
        question_id=market.question.id,
        template_id=market.question.templateId,
        question_raw=market.question.question_raw,
        n_outcomes=market.question.n_outcomes,
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
                print(f"Looing on Manifold for {market.question_title=}")
                resolution = find_resolution_on_manifold(market.question_title)

            case MarketType.POLYMARKET:
                print(f"Looing on Polymarket for {market.question_title=}")
                resolution = find_resolution_on_polymarket(market.question_title)

            case _:
                raise ValueError(
                    f"Unknown market type {market_type} in replication resolving."
                )

        if resolution is not None:
            return resolution

    return resolution
