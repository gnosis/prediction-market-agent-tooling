import os
import random
import typing as t
from datetime import timedelta
from enum import Enum

from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexAddress,
    HexBytes,
    HexStr,
    IPFSCIDVersion0,
    OmenOutcomeToken,
    TxParams,
    TxReceipt,
    Wei,
    int_to_hexbytes,
    wei_type,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    INVALID_ANSWER_HEX_BYTES,
    ConditionPreparationEvent,
    ContractPrediction,
    FPMMFundingAddedEvent,
    OmenFixedProductMarketMakerCreationEvent,
    RealitioLogNewQuestionEvent,
    format_realitio_question,
)
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    SDAI_CONTRACT_ADDRESS,
    WRAPPED_XDAI_CONTRACT_ADDRESS,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20OnGnosisChain,
    ContractERC20OnGnosisChain,
    ContractERC4626OnGnosisChain,
    ContractOnGnosisChain,
    abi_field_validator,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC
from prediction_market_agent_tooling.tools.web3_utils import (
    ZERO_BYTES,
    byte32_to_ipfscidv0,
    ipfscidv0_to_byte32,
)


class OmenOracleContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xAB16D643bA051C11962DA645f74632d3130c81E2#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_oracle.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xAB16D643bA051C11962DA645f74632d3130c81E2"
    )

    def realitio(self) -> ChecksumAddress:
        realitio_address: ChecksumAddress = self.call("realitio")
        return realitio_address

    def conditionalTokens(self) -> ChecksumAddress:
        realitio_address: ChecksumAddress = self.call("conditionalTokens")
        return realitio_address

    def resolve(
        self,
        api_keys: APIKeys,
        question_id: HexBytes,
        template_id: int,
        question_raw: str,
        n_outcomes: int,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="resolve",
            function_params=dict(
                questionId=question_id,
                templateId=template_id,
                question=question_raw,
                numOutcomes=n_outcomes,
            ),
            web3=web3,
        )


def build_parent_collection_id() -> HexStr:
    return HASH_ZERO  # Taken from Olas


class OmenConditionalTokenContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_fpmm_conditionaltokens.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce"
    )

    def getConditionId(
        self,
        question_id: HexBytes,
        oracle_address: ChecksumAddress,
        outcomes_slot_count: int,
        web3: Web3 | None = None,
    ) -> HexBytes:
        id_ = HexBytes(
            self.call(
                "getConditionId",
                [oracle_address, question_id, outcomes_slot_count],
                web3=web3,
            )
        )
        return id_

    def balanceOf(
        self, from_address: ChecksumAddress, position_id: int, web3: Web3 | None = None
    ) -> Wei:
        balance = wei_type(
            self.call("balanceOf", [from_address, position_id], web3=web3)
        )
        return balance

    def getCollectionId(
        self,
        parent_collection_id: HexStr,
        condition_id: HexBytes,
        index_set: int,
        web3: Web3 | None = None,
    ) -> HexBytes:
        collection_id = HexBytes(
            self.call(
                "getCollectionId",
                [parent_collection_id, condition_id, index_set],
                web3=web3,
            )
        )
        return collection_id

    def getPositionId(
        self,
        collateral_token_address: ChecksumAddress,
        collection_id: HexBytes,
        web3: Web3 | None = None,
    ) -> int:
        position_id: int = self.call(
            "getPositionId",
            [collateral_token_address, collection_id],
            web3=web3,
        )
        return position_id

    def mergePositions(
        self,
        api_keys: APIKeys,
        collateral_token_address: ChecksumAddress,
        conditionId: HexBytes,
        index_sets: t.List[int],
        amount: Wei,
        parent_collection_id: HexStr = build_parent_collection_id(),
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="mergePositions",
            function_params=[
                collateral_token_address,
                parent_collection_id,
                conditionId,
                index_sets,
                amount,
            ],
            web3=web3,
        )

    def redeemPositions(
        self,
        api_keys: APIKeys,
        collateral_token_address: HexAddress,
        condition_id: HexBytes,
        index_sets: t.List[int],
        parent_collection_id: HexStr = build_parent_collection_id(),
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="redeemPositions",
            function_params=[
                collateral_token_address,
                parent_collection_id,
                condition_id,
                index_sets,
            ],
            web3=web3,
        )

    def getOutcomeSlotCount(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> int:
        count: int = self.call("getOutcomeSlotCount", [condition_id], web3=web3)
        return count

    def does_condition_exists(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> bool:
        return self.getOutcomeSlotCount(condition_id, web3=web3) > 0

    def is_condition_resolved(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> bool:
        # from ConditionalTokens.redeemPositions:
        # uint den = payoutDenominator[conditionId]; require(den > 0, "result for condition not received yet");
        payout_for_condition = self.payoutDenominator(condition_id, web3=web3)
        return payout_for_condition > 0

    def payoutDenominator(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> int:
        payoutForCondition: int = self.call(
            "payoutDenominator", [condition_id], web3=web3
        )
        return payoutForCondition

    def setApprovalForAll(
        self,
        api_keys: APIKeys,
        for_address: ChecksumAddress,
        approve: bool,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="setApprovalForAll",
            function_params=[
                for_address,
                approve,
            ],
            tx_params=tx_params,
            web3=web3,
        )

    def prepareCondition(
        self,
        api_keys: APIKeys,
        oracle_address: ChecksumAddress,
        question_id: HexBytes,
        outcomes_slot_count: int,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> ConditionPreparationEvent:
        receipt_tx = self.send(
            api_keys=api_keys,
            function_name="prepareCondition",
            function_params=[
                oracle_address,
                question_id,
                outcomes_slot_count,
            ],
            tx_params=tx_params,
            web3=web3,
        )

        event_logs = (
            self.get_web3_contract(web3=web3)
            .events.ConditionPreparation()
            .process_receipt(receipt_tx)
        )
        cond_event = ConditionPreparationEvent(**event_logs[0]["args"])

        return cond_event


class OmenFixedProductMarketMakerContract(ContractOnGnosisChain):
    # File content taken from https://github.com/protofire/omen-exchange/blob/master/app/src/abi/marketMaker.json.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../../abis/omen_fpmm.abi.json"
        )
    )

    # ! Note: This doesn't have a fixed contract address, as this is something created by the `OmenFixedProductMarketMakerFactory`.
    # Factory contract at https://gnosisscan.io/address/0x9083a2b699c0a4ad06f63580bde2635d26a3eef0.

    def balanceOf(self, for_address: ChecksumAddress, web3: Web3 | None = None) -> Wei:
        balance: Wei = self.call("balanceOf", [for_address], web3=web3)
        return balance

    def calcBuyAmount(
        self, investment_amount: Wei, outcome_index: int, web3: Web3 | None = None
    ) -> OmenOutcomeToken:
        """
        Returns amount of shares we will get for the given outcome_index for the given investment amount.
        """
        calculated_shares: OmenOutcomeToken = self.call(
            "calcBuyAmount", [investment_amount, outcome_index], web3=web3
        )
        return calculated_shares

    def calcSellAmount(
        self, return_amount: Wei, outcome_index: int, web3: Web3 | None = None
    ) -> OmenOutcomeToken:
        """
        Returns amount of shares we will sell for the requested wei.
        """
        calculated_shares: OmenOutcomeToken = self.call(
            "calcSellAmount", [return_amount, outcome_index], web3=web3
        )
        return calculated_shares

    def conditionalTokens(self, web3: Web3 | None = None) -> ChecksumAddress:
        address: HexAddress = self.call("conditionalTokens", web3=web3)
        return Web3.to_checksum_address(address)

    def collateralToken(self, web3: Web3 | None = None) -> ChecksumAddress:
        address: HexAddress = self.call("collateralToken", web3=web3)
        return Web3.to_checksum_address(address)

    def buy(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        outcome_index: int,
        min_outcome_tokens_to_buy: OmenOutcomeToken,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="buy",
            function_params=[
                amount_wei,
                outcome_index,
                min_outcome_tokens_to_buy,
            ],
            tx_params=tx_params,
            web3=web3,
        )

    def sell(
        self,
        api_keys: APIKeys,
        amount_wei: Wei,
        outcome_index: int,
        max_outcome_tokens_to_sell: OmenOutcomeToken,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="sell",
            function_params=[
                amount_wei,
                outcome_index,
                max_outcome_tokens_to_sell,
            ],
            tx_params=tx_params,
            web3=web3,
        )

    def addFunding(
        self,
        api_keys: APIKeys,
        add_funding: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Funding is added in Weis (xDai) and then converted to shares.
        """
        # `addFunding` with `distribution_hint` can be used only during the market creation, so forcing empty here.
        distribution_hint: list[int] = []
        return self.send(
            api_keys=api_keys,
            function_name="addFunding",
            function_params=[add_funding, distribution_hint],
            tx_params=tx_params,
            web3=web3,
        )

    def removeFunding(
        self,
        api_keys: APIKeys,
        remove_funding: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Remove funding is done in shares.
        """
        return self.send(
            api_keys=api_keys,
            function_name="removeFunding",
            function_params=[remove_funding],
            tx_params=tx_params,
            web3=web3,
        )

    def totalSupply(self, web3: Web3 | None = None) -> Wei:
        # This is the liquidity you seen on the Omen website (but in Wei).
        total_supply: Wei = self.call("totalSupply", web3=web3)
        return total_supply

    def get_collateral_token_contract(
        self, web3: Web3 | None = None
    ) -> ContractERC20OnGnosisChain:
        web3 = web3 or self.get_web3()
        return to_gnosis_chain_contract(
            init_collateral_token_contract(self.collateralToken(web3=web3), web3)
        )


class GNOContract(ContractERC20OnGnosisChain):
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x9c58bacc331c9aa871afd802db6379a98e80cedb"
    )


class WETHContract(ContractERC20OnGnosisChain):
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x6a023ccd1ff6f2045c3309768ead9e68f978f6e1"
    )


class WrappedxDaiContract(ContractDepositableWrapperERC20OnGnosisChain):
    address: ChecksumAddress = WRAPPED_XDAI_CONTRACT_ADDRESS


class sDaiContract(ContractERC4626OnGnosisChain):
    address: ChecksumAddress = SDAI_CONTRACT_ADDRESS


OMEN_DEFAULT_MARKET_FEE_PERC = 0.02  # 2% fee from the buying shares amount.
REALITY_DEFAULT_FINALIZATION_TIMEOUT = timedelta(days=3)


class OmenFixedProductMarketMakerFactoryContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_fpmm_factory.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0"
    )

    def create2FixedProductMarketMaker(
        self,
        api_keys: APIKeys,
        condition_id: HexBytes,
        initial_funds_wei: Wei,
        collateral_token_address: ChecksumAddress,
        fee: Wei,  # This is actually fee in %, 'where 100% == 1 xDai'.
        distribution_hint: list[OmenOutcomeToken] | None = None,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> tuple[
        OmenFixedProductMarketMakerCreationEvent, FPMMFundingAddedEvent, TxReceipt
    ]:
        web3 = web3 or self.get_web3()
        receipt_tx = self.send(
            api_keys=api_keys,
            function_name="create2FixedProductMarketMaker",
            function_params=dict(
                saltNonce=random.randint(
                    0, 1000000
                ),  # See https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942.
                conditionalTokens=OmenConditionalTokenContract().address,
                collateralToken=collateral_token_address,
                conditionIds=[condition_id],
                fee=fee,
                initialFunds=initial_funds_wei,
                distributionHint=distribution_hint or [],
            ),
            tx_params=tx_params,
            web3=web3,
        )

        market_event_logs = (
            self.get_web3_contract(web3=web3)
            .events.FixedProductMarketMakerCreation()
            .process_receipt(receipt_tx)
        )
        market_event = OmenFixedProductMarketMakerCreationEvent(
            **market_event_logs[0]["args"]
        )
        funding_event_logs = (
            self.get_web3_contract(web3=web3)
            .events.FPMMFundingAdded()
            .process_receipt(receipt_tx)
        )
        funding_event = FPMMFundingAddedEvent(**funding_event_logs[0]["args"])

        return market_event, funding_event, receipt_tx


class Arbitrator(str, Enum):
    KLEROS_511_JURORS_WITHOUT_APPEAL = "kleros_511_jurors_without_appeal"
    KLEROS_31_JURORS_WITH_APPEAL = "kleros_31_jurors_with_appeal"
    DXDAO = "dxdao"

    @property
    def is_kleros(self) -> bool:
        return self.value.startswith("kleros")


class OmenDxDaoContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xFe14059344b74043Af518d12931600C0f52dF7c5#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_dxdao.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xFe14059344b74043Af518d12931600C0f52dF7c5"
    )


class OmenKlerosContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0xe40DD83a262da3f56976038F1554Fe541Fa75ecd#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_kleros.abi.json",
        )
    )

    @staticmethod
    def from_arbitrator(arbitrator: "Arbitrator") -> "OmenKlerosContract":
        """
        See https://docs.kleros.io/developer/deployment-addresses for all available addresses.
        """
        if arbitrator == Arbitrator.KLEROS_511_JURORS_WITHOUT_APPEAL:
            address = "0xe40DD83a262da3f56976038F1554Fe541Fa75ecd"

        elif arbitrator == Arbitrator.KLEROS_31_JURORS_WITH_APPEAL:
            address = "0x5562Ac605764DC4039fb6aB56a74f7321396Cdf2"

        else:
            raise ValueError(f"Unsupported arbitrator: {arbitrator=}")

        return OmenKlerosContract(address=Web3.to_checksum_address(address))


class OmenRealitioContract(ContractOnGnosisChain):
    # Contract ABI taken from https://gnosisscan.io/address/0x79e32aE03fb27B07C89c0c568F80287C01ca2E57#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_realitio.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x79e32aE03fb27B07C89c0c568F80287C01ca2E57"
    )

    @staticmethod
    def get_arbitrator_contract(
        arbitrator: Arbitrator,
    ) -> ContractOnGnosisChain:
        if arbitrator.is_kleros:
            return OmenKlerosContract.from_arbitrator(arbitrator)
        if arbitrator == Arbitrator.DXDAO:
            return OmenDxDaoContract()
        raise ValueError(f"Unknown arbitrator: {arbitrator}")

    def askQuestion(
        self,
        api_keys: APIKeys,
        question: str,
        category: str,
        outcomes: list[str],
        language: str,
        arbitrator: Arbitrator,
        opening: DatetimeUTC,
        timeout: timedelta,
        nonce: int | None = None,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> RealitioLogNewQuestionEvent:
        """
        After the question is created, you can find it at https://reality.eth.link/app/#!/creator/{from_address}.
        """
        web3 = web3 or self.get_web3()
        arbitrator_contract_address = self.get_arbitrator_contract(arbitrator).address
        # See https://realitio.github.io/docs/html/contracts.html#templates
        # for possible template ids and how to format the question.
        template_id = 2
        realitio_question = format_realitio_question(
            question=question,
            outcomes=outcomes,
            category=category,
            language=language,
            template_id=template_id,
        )
        receipt_tx = self.send(
            api_keys=api_keys,
            function_name="askQuestion",
            function_params=dict(
                template_id=template_id,
                question=realitio_question,
                arbitrator=arbitrator_contract_address,
                timeout=int(timeout.total_seconds()),
                opening_ts=int(opening.timestamp()),
                nonce=(
                    nonce if nonce is not None else random.randint(0, 1000000)
                ),  # Two equal questions need to have different nonces.
            ),
            tx_params=tx_params,
            web3=web3,
        )

        event_logs = (
            self.get_web3_contract(web3=web3)
            .events.LogNewQuestion()
            .process_receipt(receipt_tx)
        )
        question_event = RealitioLogNewQuestionEvent(**event_logs[0]["args"])

        return question_event

    def submitAnswer(
        self,
        api_keys: APIKeys,
        question_id: HexBytes,
        answer: HexBytes,
        bond: Wei,
        max_previous: Wei | None = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        if max_previous is None:
            # If not provided, defaults to 0, which means no checking,
            # same as on Omen website: https://github.com/protofire/omen-exchange/blob/763d9c9d05ebf9edacbc1dbaa561aa5d08813c0f/app/src/services/realitio.ts#L363.
            max_previous = Wei(0)

        return self.send_with_value(
            api_keys=api_keys,
            function_name="submitAnswer",
            function_params=dict(
                question_id=question_id,
                answer=answer,
                max_previous=max_previous,
            ),
            amount_wei=bond,
            web3=web3,
        )

    def submit_answer(
        self,
        api_keys: APIKeys,
        question_id: HexBytes,
        answer: str,
        outcomes: list[str],
        bond: Wei,
        max_previous: Wei | None = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        # Normalise the answer to lowercase, to match Enum values as [YES, NO] against outcomes as ["Yes", "No"].
        answer = answer.lower()
        outcomes = [o.lower() for o in outcomes]

        return self.submitAnswer(
            api_keys=api_keys,
            question_id=question_id,
            answer=int_to_hexbytes(
                outcomes.index(answer)
            ),  # Contract's method expects answer index in bytes.
            bond=bond,
            max_previous=max_previous,
            web3=web3,
        )

    def submit_answer_invalid(
        self,
        api_keys: APIKeys,
        question_id: HexBytes,
        bond: Wei,
        max_previous: Wei | None = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.submitAnswer(
            api_keys=api_keys,
            question_id=question_id,
            answer=INVALID_ANSWER_HEX_BYTES,
            bond=bond,
            max_previous=max_previous,
            web3=web3,
        )

    def claimWinnings(
        self,
        api_keys: APIKeys,
        question_id: HexBytes,
        history_hashes: list[HexBytes],
        addresses: list[ChecksumAddress],
        bonds: list[Wei],
        answers: list[HexBytes],
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="claimWinnings",
            function_params=dict(
                question_id=question_id,
                history_hashes=history_hashes,
                addrs=addresses,
                bonds=bonds,
                answers=answers,
            ),
            tx_params=tx_params,
            web3=web3,
        )

    def balanceOf(
        self,
        from_address: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> Wei:
        balance = wei_type(self.call("balanceOf", [from_address], web3=web3))
        return balance

    def withdraw(
        self,
        api_keys: APIKeys,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(api_keys=api_keys, function_name="withdraw", web3=web3)

    def getOpeningTS(
        self,
        question_id: HexBytes,
        web3: Web3 | None = None,
    ) -> int:
        ts: int = self.call(
            function_name="getOpeningTS",
            function_params=[question_id],
            web3=web3,
        )
        return ts

    def getFinalizeTS(
        self,
        question_id: HexBytes,
        web3: Web3 | None = None,
    ) -> int:
        ts: int = self.call(
            function_name="getFinalizeTS",
            function_params=[question_id],
            web3=web3,
        )
        return ts

    def isFinalized(
        self,
        question_id: HexBytes,
        web3: Web3 | None = None,
    ) -> bool:
        is_finalized: bool = self.call(
            function_name="isFinalized",
            function_params=[question_id],
            web3=web3,
        )
        return is_finalized

    def isPendingArbitration(
        self,
        question_id: HexBytes,
        web3: Web3 | None = None,
    ) -> bool:
        is_pending_arbitration: bool = self.call(
            function_name="isPendingArbitration",
            function_params=[question_id],
            web3=web3,
        )
        return is_pending_arbitration


class OmenAgentResultMappingContract(ContractOnGnosisChain):
    # Contract ABI taken from built https://github.com/gnosis/labs-contracts.

    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_agentresultmapping.abi.json",
        )
    )

    address: ChecksumAddress = Web3.to_checksum_address(
        "0x260E1077dEA98e738324A6cEfB0EE9A272eD471a"
    )

    def get_predictions(
        self,
        market_address: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> list[ContractPrediction]:
        prediction_tuples = self.call(
            "getPredictions", function_params=[market_address], web3=web3
        )
        return [ContractPrediction.from_tuple(p) for p in prediction_tuples]

    def add_prediction(
        self,
        api_keys: APIKeys,
        market_address: ChecksumAddress,
        prediction: ContractPrediction,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="addPrediction",
            function_params=[market_address, prediction.model_dump(by_alias=True)],
            web3=web3,
        )


class OmenThumbnailMapping(ContractOnGnosisChain):
    # Contract ABI taken from built https://github.com/gnosis/labs-contracts.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_thumbnailmapping.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xe0cf08311F03850497B0ed6A2cf067f1750C3eFc"
    )

    @staticmethod
    def construct_ipfs_url(ipfs_hash: IPFSCIDVersion0) -> str:
        return f"https://ipfs.io/ipfs/{ipfs_hash}"

    def get(
        self,
        market_address: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> IPFSCIDVersion0 | None:
        hash_bytes = HexBytes(
            self.call("get", function_params=[market_address], web3=web3)
        )
        return byte32_to_ipfscidv0(hash_bytes) if hash_bytes != ZERO_BYTES else None

    def get_url(
        self,
        market_address: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> str | None:
        hash_ = self.get(market_address, web3)
        return self.construct_ipfs_url(hash_) if hash_ is not None else None

    def set(
        self,
        api_keys: APIKeys,
        market_address: ChecksumAddress,
        image_hash: IPFSCIDVersion0,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="set",
            function_params=[market_address, ipfscidv0_to_byte32(image_hash)],
            web3=web3,
        )

    def remove(
        self,
        api_keys: APIKeys,
        market_address: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
            api_keys=api_keys,
            function_name="remove",
            function_params=[market_address],
            web3=web3,
        )


class CowGPv2SettlementContract(ContractOnGnosisChain):
    # Contract ABI taken from https://github.com/cowprotocol/cow-sdk/blob/main/abi/GPv2Settlement.json.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/gvp2_settlement.abi.json",
        )
    )

    def setPreSignature(
        self,
        api_keys: APIKeys,
        orderId: HexBytes,
        signed: bool,
        web3: Web3 | None = None,
    ) -> None:
        self.send(
            api_keys=api_keys,
            function_name="setPreSignature",
            function_params=[orderId, signed],
            web3=web3,
        )


class CollateralTokenChoice(str, Enum):
    wxdai = "wxdai"
    sdai = "sdai"


COLLATERAL_TOKEN_CHOICE_TO_ADDRESS = {
    CollateralTokenChoice.wxdai: WrappedxDaiContract().address,
    CollateralTokenChoice.sdai: sDaiContract().address,
}
