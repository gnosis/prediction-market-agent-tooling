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
    send_keeping_token_to_eoa_xdai,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenOracleContract,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.tokens.main_token import (
    MINIMUM_NATIVE_TOKEN_IN_EOA_FOR_FEES,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import (
    ZERO_BYTES,
    wei_to_xdai,
    xdai_to_wei,
    xdai_type,
)


def claim_bonds_on_realitio_questions(
    api_keys: APIKeys,
    questions: list[RealityQuestion],
    auto_withdraw: bool,
    web3: Web3 | None = None,
    skip_failed: bool = False,
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
            if not skip_failed:
                raise e
            logger.warning(
                f"Failed to claim bond for {question.url=}, {question.questionId=}: {e}"
            )

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
    responses = OmenSubgraphHandler().get_responses(
        limit=None, question_id=question.questionId
    )

    # They need to be processed in order.
    responses = sorted(responses, key=lambda x: x.timestamp)

    if not responses:
        raise ValueError(f"No answers found for {question.questionId.hex()=}")

    if responses[-1].question.historyHash == ZERO_BYTES:
        raise ValueError(f"Already claimed {question.questionId.hex()=}.")

    history_hashes: list[HexBytes] = []
    addresses: list[ChecksumAddress] = []
    bonds: list[Wei] = []
    answers: list[HexBytes] = []

    # Caller must provide the answer history, in reverse order.
    # See https://gnosisscan.io/address/0x79e32aE03fb27B07C89c0c568F80287C01ca2E57#code#L625 for the `claimWinnings` logic.
    reversed_responses = list(reversed(responses))

    for i, response in enumerate(reversed_responses):
        # second-last-to-first, the hash of each history entry. (Final one should be empty).
        if i == len(reversed_responses) - 1:
            history_hashes.append(ZERO_BYTES)
        else:
            history_hashes.append(reversed_responses[i + 1].historyHash)

        # last-to-first, the address of each answerer or commitment sender
        addresses.append(Web3.to_checksum_address(response.user))
        # last-to-first, the bond supplied with each answer or commitment
        bonds.append(response.bond)
        # last-to-first, each answer supplied, or commitment ID if the answer was supplied with commit->reveal
        answers.append(response.answer)

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
        logger.info(
            f"Withdrawing remaining balance {wei_to_xdai(current_balance)} xDai from Realitio."
        )
        realitio_contract.withdraw(api_keys, web3=web3)


def finalize_markets(
    api_keys: APIKeys,
    markets_with_resolutions: list[tuple[OmenMarket, Resolution | None]],
    realitio_bond: xDai,
    wait_n_days_before_invalid: int = 30,
    web3: Web3 | None = None,
) -> list[HexAddress]:
    finalized_markets: list[HexAddress] = []

    for idx, (market, resolution) in enumerate(markets_with_resolutions):
        logger.info(
            f"[{idx+1} / {len(markets_with_resolutions)}] Looking into {market.url=} {market.question_title=}"
        )

        # If we don't have enough of xDai for bond, try to get it from the keeping token.
        send_keeping_token_to_eoa_xdai(
            api_keys=api_keys,
            min_required_balance=xdai_type(
                realitio_bond + MINIMUM_NATIVE_TOKEN_IN_EOA_FOR_FEES
            ),
            web3=web3,
        )

        closed_before_days = (utcnow() - market.close_time).days

        if resolution is None:
            if closed_before_days > wait_n_days_before_invalid:
                logger.warning(
                    f"Finalizing as invalid, market closed before {closed_before_days} days: {market.url=}"
                )
                omen_submit_invalid_answer_market_tx(
                    api_keys,
                    market,
                    realitio_bond,
                    web3=web3,
                )

            else:
                logger.warning(
                    f"Skipping, no resolution provided, market closed before {closed_before_days} days: {market.url=}"
                )

        elif resolution in (Resolution.YES, Resolution.NO):
            logger.info(f"Found resolution {resolution.value=} for {market.url=}")
            omen_submit_answer_market_tx(
                api_keys,
                market,
                resolution,
                realitio_bond,
                web3=web3,
            )
            finalized_markets.append(market.id)
            logger.info(f"Finalized {market.url=}")

        else:
            logger.warning(
                f"Invalid resolution found, {resolution=}, for {market.url=}, finalizing as invalid."
            )
            omen_submit_invalid_answer_market_tx(
                api_keys,
                market,
                realitio_bond,
                web3=web3,
            )

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
    After the answer is submitted, there is waiting period where the answer can be challenged by others.
    And after the period is over, you need to resolve the market using `omen_resolve_market_tx`.
    """
    realitio_contract = OmenRealitioContract()
    realitio_contract.submit_answer(
        api_keys=api_keys,
        question_id=market.question.id,
        answer=resolution.value,
        outcomes=market.question.outcomes,
        bond=xdai_to_wei(bond),
        web3=web3,
    )


def omen_submit_invalid_answer_market_tx(
    api_keys: APIKeys,
    market: OmenMarket,
    bond: xDai,
    web3: Web3 | None = None,
) -> None:
    """
    After the answer is submitted, there is waiting period where the answer can be challenged by others.
    And after the period is over, you need to resolve the market using `omen_resolve_market_tx`.
    """
    realitio_contract = OmenRealitioContract()
    realitio_contract.submit_answer_invalid(
        api_keys=api_keys,
        question_id=market.question.id,
        bond=xdai_to_wei(bond),
        web3=web3,
    )


def omen_resolve_market_tx(
    api_keys: APIKeys,
    market: OmenMarket,
    web3: Web3 | None = None,
) -> None:
    """
    Market can be resolved after the answer if finalized on Reality.
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

            # TODO: Uncomment after https://github.com/gnosis/prediction-market-agent-tooling/issues/459 is done.
            # case MarketType.POLYMARKET:
            #     logger.info(f"Looking on Polymarket for {market.question_title=}")
            #     resolution = find_resolution_on_polymarket(market.question_title)

            case _:
                logger.warning(
                    f"Unknown market type {market_type} in replication resolving."
                )
                continue

        if resolution is not None:
            return resolution

    return resolution
