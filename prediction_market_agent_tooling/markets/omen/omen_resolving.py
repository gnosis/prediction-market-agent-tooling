from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexBytes,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.loggers import logger
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
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import ZERO_BYTES, xdai_to_wei


def claim_bonds_on_realitio_questions(
    api_keys: APIKeys,
    questions: list[RealityQuestion],
    auto_withdraw: bool,
    web3: Web3 | None = None,
    silent_errors: bool = False,
) -> list[HexBytes]:
    claimed_questions: list[HexBytes] = []

    for idx, question in enumerate(questions):
        logger.info(
            f"[{idx+1} / {len(questions)}] Claiming bond for {question.questionId=} {question.url=}"
        )
        try:
            claim_bonds_on_realitio_question(
                api_keys, question, auto_withdraw=auto_withdraw, web3=web3
            )
            claimed_questions.append(question.questionId)
        except Exception as e:
            # TODO: This shouldn't be required once `claim_bonds_on_realitio_question` below is fixed.
            if silent_errors:
                logger.warning(
                    f"Error while claiming bond for {question.questionId=} {question.url=}: {e}"
                )
            else:
                raise

    return claimed_questions


def claim_bonds_on_realitio_question(
    api_keys: APIKeys,
    question: RealityQuestion,
    auto_withdraw: bool,
    web3: Web3 | None = None,
) -> None:
    public_key = api_keys.bet_from_address
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
            history_hashes.append(
                check_not_none(
                    answers_objects[i + 1].question.historyHash,
                    "Shouldn't be None here.",
                )
            )

        # last-to-first, the address of each answerer or commitment sender
        addresses.append(Web3.to_checksum_address(answer.question.user))
        # last-to-first, the bond supplied with each answer or commitment
        bonds.append(answer.lastBond)
        # last-to-first, each answer supplied, or commitment ID if the answer was supplied with commit->reveal
        answers.append(answer.answer)

    realitio_contract.claimWinnings(
        api_keys=api_keys,
        question_id=question.questionId,
        history_hashes=history_hashes,
        addresses=addresses,
        bonds=bonds,
        answers=answers,
        web3=web3,
    )

    current_balance = realitio_contract.balanceOf(public_key, web3=web3)
    # Keeping balance on Realitio is not useful, so it's recommended to just withdraw it.
    if current_balance > 0 and auto_withdraw:
        logger.info(f"Withdrawing remaining balance {current_balance=}")
        realitio_contract.withdraw(api_keys, web3=web3)


def finalize_markets(
    api_keys: APIKeys,
    markets_with_resolutions: list[tuple[OmenMarket, Resolution | None]],
    web3: Web3 | None = None,
) -> list[HexAddress]:
    finalized_markets: list[HexAddress] = []

    for idx, (market, resolution) in enumerate(markets_with_resolutions):
        logger.info(
            f"[{idx+1} / {len(markets_with_resolutions)}] Looking into {market.url=} {market.question_title=}"
        )

        if resolution is None:
            logger.warning(f"No resolution provided for {market.url=}")

        elif resolution in (Resolution.YES, Resolution.NO):
            logger.info(f"Found resolution {resolution.value=} for {market.url=}")
            omen_submit_answer_market_tx(
                api_keys,
                market,
                resolution,
                OMEN_DEFAULT_REALITIO_BOND_VALUE,
                web3=web3,
            )
            finalized_markets.append(market.id)
            logger.info(f"Finalized {market.url=}")

        else:
            logger.error(f"Invalid resolution found, {resolution=}, for {market.url=}")

    return finalized_markets


def resolve_markets(
    api_keys: APIKeys,
    markets: list[OmenMarket],
    web3: Web3 | None = None,
) -> list[HexAddress]:
    resolved_markets: list[HexAddress] = []

    for idx, market in enumerate(markets):
        logger.info(
            f"[{idx+1} / {len(markets)}] Resolving {market.url=} {market.question_title=}"
        )
        omen_resolve_market_tx(api_keys, market, web3=web3)
        resolved_markets.append(market.id)

    return resolved_markets


def omen_submit_answer_market_tx(
    api_keys: APIKeys,
    market: OmenMarket,
    resolution: Resolution,
    bond: xDai,
    web3: Web3 | None = None,
) -> None:
    """
    After the answer is submitted, there is 24h waiting period where the answer can be challenged by others.
    And after the period is over, you need to resolve the market using `omen_resolve_market_tx`.
    """
    realitio_contract = OmenRealitioContract()
    realitio_contract.submitAnswer(
        api_keys=api_keys,
        question_id=market.question.id,
        answer=resolution.value,
        outcomes=market.question.outcomes,
        bond=xdai_to_wei(bond),
        web3=web3,
    )


def omen_resolve_market_tx(
    api_keys: APIKeys,
    market: OmenMarket,
    web3: Web3 | None = None,
) -> None:
    """
    Market can be resolved 24h after last answer was submitted via `omen_submit_answer_market_tx`.
    """
    oracle_contract = OmenOracleContract()
    oracle_contract.resolve(
        api_keys=api_keys,
        question_id=market.question.id,
        template_id=market.question.templateId,
        question_raw=market.question.question_raw,
        n_outcomes=market.question.n_outcomes,
        web3=web3,
    )


def find_resolution_on_other_markets(market: OmenMarket) -> Resolution | None:
    resolution: Resolution | None = None

    for market_type in MarketType:
        match market_type:
            case MarketType.OMEN:
                # We are going to resolve it on Omen, so we can't find the answer there.
                continue

            case MarketType.MANIFOLD:
                logger.info(f"Looking on Manifold for {market.question_title=}")
                resolution = find_resolution_on_manifold(market.question_title)

            case MarketType.POLYMARKET:
                logger.info(f"Looking on Polymarket for {market.question_title=}")
                resolution = find_resolution_on_polymarket(market.question_title)

            case _:
                logger.warning(
                    f"Unknown market type {market_type} in replication resolving."
                )
                continue

        if resolution is not None:
            return resolution

    return resolution
