from datetime import timedelta

from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexBytes,
    PrivateKey,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.manifold.utils import (
    find_resolution_on_manifold,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.data_models import (
    OmenMarket,
    RealityQuestion,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OMEN_DEFAULT_REALITIO_BOND_VALUE,
    get_omen_binary_markets,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenOracleContract,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.markets.polymarket.utils import (
    find_resolution_on_polymarket,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.utils import deduplicate_by, utcnow
from prediction_market_agent_tooling.tools.web3_utils import (
    ZERO_BYTES,
    private_key_to_public_key,
    xdai_to_wei,
)


class FinalizeAndResolveResult(BaseModel):
    finalized: list[HexAddress]
    resolved: list[HexAddress]
    claimed_question_ids: list[HexBytes]


def omen_finalize_and_resolve_all_markets_based_on_others_tx(
    from_private_key: PrivateKey,
) -> FinalizeAndResolveResult:
    public_key = private_key_to_public_key(from_private_key)
    balances_start = get_balances(public_key)
    print(f"{balances_start=}")

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
    balances_after_finalization = get_balances(public_key)
    print(f"{balances_after_finalization=}")

    # Fetch markets created by us that are already open, and we already submitted an answer more than a day ago, but they aren't resolved yet.
    created_finalized_markets = get_omen_binary_markets(
        limit=None,
        creator=public_key,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.NONE,
        finalized_before=before - timedelta(hours=24),
        resolved=False,
    )
    # Resolve them (resolve them on Oracle).
    resolved_markets = resolve_markets(
        created_finalized_markets, from_private_key=from_private_key
    )
    balances_after_resolution = get_balances(public_key)
    print(f"{balances_after_resolution=}")

    # Fetch answers that are already resolved, but we didn't claim the bonded xDai yet.
    # And deduplicate them into a list of unique questions.
    created_resolved_not_claimed_questions: list[RealityQuestion] = deduplicate_by(
        [
            a.question
            for a in OmenSubgraphHandler().get_answers(user=public_key, claimed=False)
        ],
        lambda x: x.questionId,
    )
    claimed_question_ids = claim_bonds_on_realitio_quetions(
        created_resolved_not_claimed_questions, from_private_key, auto_withdraw=True
    )
    balances_after_claiming = get_balances(public_key)
    print(f"{balances_after_claiming=}")

    return FinalizeAndResolveResult(
        finalized=finalized_markets,
        resolved=resolved_markets,
        claimed_question_ids=claimed_question_ids,
    )


def claim_bonds_on_realitio_quetions(
    questions: list[RealityQuestion], from_private_key: PrivateKey, auto_withdraw: bool
) -> list[HexBytes]:
    claimed_questions: list[HexBytes] = []

    for idx, question in enumerate(questions):
        print(f"[{idx+1} / {len(questions)}] Claiming bond for {question.questionId=}")
        claim_bonds_on_realitio_question(
            question, from_private_key, auto_withdraw=auto_withdraw
        )
        claimed_questions.append(question.questionId)

    return claimed_questions


def claim_bonds_on_realitio_question(
    question: RealityQuestion,
    from_private_key: PrivateKey,
    auto_withdraw: bool,
) -> None:
    public_key = private_key_to_public_key(from_private_key)
    realitio_contract = OmenRealitioContract()

    # Get all answers for the question.
    answers_objects = OmenSubgraphHandler().get_answers(question_id=question.questionId)

    if not answers_objects:
        raise ValueError(f"No answers found for {question.questionId=}")

    if answers_objects[-1].question.historyHash == ZERO_BYTES:
        raise ValueError(f"Already claimed {question.questionId=}.")

    if len(answers_objects) > 1:
        # As you can see below, we need `history_hash` for every answer.
        # The trouble is, that historyHash is updated after each new answer and the contract holds only the latest one.
        # So if we have more than 1 answer, we missing the historyHash n-1 of them and this would fail.
        # You can find how to calculate history hash at https://realitio.github.io/docs/html/contract_explanation.html#answer-history-entries.
        # At the moment, we support only 1 answer, as for that one answer we will have the hash.
        raise NotImplementedError()

    # Logic taken from packages/valory/skills/decision_maker_abci/models.py in `def claim_params`.
    history_hashes: list[HexBytes] = []
    addresses: list[ChecksumAddress] = []
    bonds: list[Wei] = []
    answers: list[HexBytes] = []

    for i, answer in enumerate(reversed(answers_objects)):
        # history_hashes second-last-to-first, the hash of each history entry, calculated as described here:
        # https://realitio.github.io/docs/html/contract_explanation.html#answer-history-entries.
        if i == len(answers_objects) - 1:
            history_hashes.append(ZERO_BYTES)
        else:
            # TODO: See `if len(answers_objects) > 1` above.
            # This is from the original Olas implementation (https://github.com/kongzii/trader/blob/700af475a4538cc3d5d22caf9dec9e9d22d72af1/packages/valory/skills/market_manager_abci/graph_tooling/requests.py#L297),
            # but it's most probably wrong (see comment above).
            history_hashes.append(answers_objects[i + 1].question.historyHash)

        # last-to-first, the address of each answerer or commitment sender
        addresses.append(Web3.to_checksum_address(answer.question.user))
        # last-to-first, the bond supplied with each answer or commitment
        bonds.append(answer.lastBond)
        # last-to-first, each answer supplied, or commitment ID if the answer was supplied with commit->reveal
        answers.append(answer.answer)

    realitio_contract.claimWinnings(
        question_id=question.questionId,
        history_hashes=history_hashes,
        addresses=addresses,
        bonds=bonds,
        answers=answers,
        from_private_key=from_private_key,
    )

    current_balance = realitio_contract.balanceOf(public_key)
    # Keeping balance on Realitio is not useful, so it's recommended to just withdraw it.
    if current_balance > 0 and auto_withdraw:
        print(f"Withdrawing remaining balance {current_balance=}")
        realitio_contract.withdraw(from_private_key)


def finalize_markets(
    markets: list[OmenMarket], from_private_key: PrivateKey
) -> list[HexAddress]:
    finalized_markets: list[HexAddress] = []

    for idx, market in enumerate(markets):
        print(
            f"[{idx+1} / {len(markets)}] Looking into {market.url=} {market.question_title=}"
        )
        resolution = find_resolution_on_other_markets(market)

        if resolution is None:
            print(f"Error: No resolution found for {market.url=}")

        elif resolution in (Resolution.YES, Resolution.NO):
            print(f"Found resolution {resolution.value=} for {market.url=}")
            omen_submit_answer_market_tx(
                market, resolution, OMEN_DEFAULT_REALITIO_BOND_VALUE, from_private_key
            )
            finalized_markets.append(market.id)
            print(f"Finalized {market.url=}")

        else:
            print(f"Error: Invalid resolution found, {resolution=}, for {market.url=}")

    return finalized_markets


def resolve_markets(
    markets: list[OmenMarket], from_private_key: PrivateKey
) -> list[HexAddress]:
    resolved_markets: list[HexAddress] = []

    for idx, market in enumerate(markets):
        print(
            f"[{idx+1} / {len(markets)}] Resolving {market.url=} {market.question_title=}"
        )
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
                print(f"Looking on Manifold for {market.question_title=}")
                resolution = find_resolution_on_manifold(market.question_title)

            case MarketType.POLYMARKET:
                print(f"Looking on Polymarket for {market.question_title=}")
                resolution = find_resolution_on_polymarket(market.question_title)

            case _:
                raise ValueError(
                    f"Unknown market type {market_type} in replication resolving."
                )

        if resolution is not None:
            return resolution

    return resolution
