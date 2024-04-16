import os
import random
import typing as t
from datetime import datetime
from enum import Enum

from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexAddress,
    HexBytes,
    HexStr,
    OmenOutcomeToken,
    PrivateKey,
    TxParams,
    TxReceipt,
    Wei,
    int_to_hexbytes,
    wei_type,
    xdai_type,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20OnGnosisChain,
    ContractOnGnosisChain,
    abi_field_validator,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


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
        question_id: HexBytes,
        template_id: int,
        question_raw: str,
        n_outcomes: int,
    ) -> TxReceipt:
        return self.send(
            function_name="resolve",
            function_params=dict(
                questionId=question_id,
                templateId=template_id,
                question=question_raw,
                numOutcomes=n_outcomes,
            ),
        )


class DummyContract(ContractOnGnosisChain):
    pass


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
    ) -> HexBytes:
        id_ = HexBytes(
            self.call(
                "getConditionId",
                [oracle_address, question_id, outcomes_slot_count],
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
        collateral_token_address: ChecksumAddress,
        parent_collection_id: HexStr,
        conditionId: HexBytes,
        index_sets: t.List[int],
        amount: Wei,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
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
        collateral_token_address: HexAddress,
        condition_id: HexBytes,
        parent_collection_id: HexStr,
        index_sets: t.List[int],
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
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
        self,
        condition_id: HexBytes,
    ) -> int:
        count: int = self.call(
            "getOutcomeSlotCount",
            [condition_id],
        )
        return count

    def does_condition_exists(
        self,
        condition_id: HexBytes,
    ) -> bool:
        return self.getOutcomeSlotCount(condition_id) > 0

    def is_condition_resolved(
        self,
        condition_id: HexBytes,
    ) -> bool:
        # from ConditionalTokens.redeemPositions:
        # uint den = payoutDenominator[conditionId]; require(den > 0, "result for condition not received yet");
        payout_for_condition = self.payoutDenominator(condition_id)
        return payout_for_condition > 0

    def payoutDenominator(self, condition_id: HexBytes) -> int:
        payoutForCondition: int = self.call(
            "payoutDenominator",
            [condition_id],
        )
        return payoutForCondition

    def setApprovalForAll(
        self,
        for_address: ChecksumAddress,
        approve: bool,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            function_name="setApprovalForAll",
            function_params=[
                for_address,
                approve,
            ],
            tx_params=tx_params,
        )

    def prepareCondition(
        self,
        oracle_address: ChecksumAddress,
        question_id: HexBytes,
        outcomes_slot_count: int,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            function_name="prepareCondition",
            function_params=[
                oracle_address,
                question_id,
                outcomes_slot_count,
            ],
            tx_params=tx_params,
        )


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
        self,
        investment_amount: Wei,
        outcome_index: int,
    ) -> OmenOutcomeToken:
        """
        Returns amount of shares we will get for the given outcome_index for the given investment amount.
        """
        calculated_shares: OmenOutcomeToken = self.call(
            "calcBuyAmount",
            [investment_amount, outcome_index],
        )
        return calculated_shares

    def calcSellAmount(
        self,
        return_amount: Wei,
        outcome_index: int,
    ) -> OmenOutcomeToken:
        """
        Returns amount of shares we will sell for the requested wei.
        """
        calculated_shares: OmenOutcomeToken = self.call(
            "calcSellAmount",
            [return_amount, outcome_index],
        )
        return calculated_shares

    def conditionalTokens(
        self,
    ) -> HexAddress:
        address: HexAddress = self.call(
            "conditionalTokens",
        )
        return address

    def buy(
        self,
        amount_wei: Wei,
        outcome_index: int,
        min_outcome_tokens_to_buy: OmenOutcomeToken,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        return self.send(
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
        amount_wei: Wei,
        outcome_index: int,
        max_outcome_tokens_to_sell: OmenOutcomeToken,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            function_name="sell",
            function_params=[
                amount_wei,
                outcome_index,
                max_outcome_tokens_to_sell,
            ],
            tx_params=tx_params,
        )

    def addFunding(
        self,
        add_funding: Wei,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        """
        Funding is added in Weis (xDai) and then converted to shares.
        """
        # `addFunding` with `distribution_hint` can be used only during the market creation, so forcing empty here.
        distribution_hint: list[int] = []
        return self.send(
            function_name="addFunding",
            function_params=[add_funding, distribution_hint],
            tx_params=tx_params,
        )

    def removeFunding(
        self,
        remove_funding: Wei,
        tx_params: t.Optional[TxParams] = None,
        web3: Web3 | None = None,
    ) -> TxReceipt:
        """
        Remove funding is done in shares.
        """
        return self.send(
            function_name="removeFunding",
            function_params=[remove_funding],
            tx_params=tx_params,
            web3=web3,
        )

    def totalSupply(self) -> Wei:
        # This is the liquidity you seen on the Omen website (but in Wei).
        total_supply: Wei = self.call("totalSupply")
        return total_supply


class WrappedxDaiContract(ContractERC20OnGnosisChain):
    # File content taken from https://gnosisscan.io/address/0xe91d153e0b41518a2ce8dd3d7944fa863463a97d#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "../../abis/wxdai.abi.json"
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d"
    )


# Collateral token used on Omen is wrapped xDai.
OmenCollateralTokenContract = WrappedxDaiContract

OMEN_DEFAULT_MARKET_FEE = 0.02  # 2% fee from the buying shares amount.


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
        condition_id: HexBytes,
        initial_funds_wei: Wei,
        fee: float = OMEN_DEFAULT_MARKET_FEE,
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        fee_wei = xdai_to_wei(
            xdai_type(fee)
        )  # We need to convert this to the wei units, but in reality it's % fee as stated in the `OMEN_DEFAULT_MARKET_FEE` variable.
        return self.send(
            function_name="create2FixedProductMarketMaker",
            function_params=dict(
                saltNonce=random.randint(
                    0, 1000000
                ),  # See https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942.
                conditionalTokens=OmenConditionalTokenContract().address,
                collateralToken=OmenCollateralTokenContract().address,
                conditionIds=[condition_id],
                fee=fee_wei,
                initialFunds=initial_funds_wei,
                distributionHint=[],
            ),
            tx_params=tx_params,
        )


class Arbitrator(str, Enum):
    KLEROS = "kleros"
    DXDAO = "dxdao"


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
    address: ChecksumAddress = Web3.to_checksum_address(
        "0xe40DD83a262da3f56976038F1554Fe541Fa75ecd"
    )


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
        if arbitrator == Arbitrator.KLEROS:
            return OmenKlerosContract()
        if arbitrator == Arbitrator.DXDAO:
            return OmenDxDaoContract()
        raise ValueError(f"Unknown arbitrator: {arbitrator}")

    def askQuestion(
        self,
        question: str,
        category: str,
        outcomes: list[str],
        language: str,
        arbitrator: Arbitrator,
        opening: datetime,
        nonce: int | None = None,
        tx_params: t.Optional[TxParams] = None,
    ) -> HexBytes:
        """
        After the question is created, you can find it at https://reality.eth.link/app/#!/creator/{from_address}.
        """
        arbitrator_contract_address = self.get_arbitrator_contract(arbitrator).address
        # See https://realitio.github.io/docs/html/contracts.html#templates
        # for possible template ids and how to format the question.
        template_id = 2
        realitio_question = "␟".join(
            [
                question,
                ",".join(f'"{o}"' for o in outcomes),
                category,
                language,
            ]
        )
        receipt_tx = self.send(
            function_name="askQuestion",
            function_params=dict(
                template_id=template_id,
                question=realitio_question,
                arbitrator=arbitrator_contract_address,
                timeout=86400,  # See https://github.com/protofire/omen-exchange/blob/2cfdf6bfe37afa8b169731d51fea69d42321d66c/app/src/util/networks.ts#L278.
                opening_ts=int(opening.timestamp()),
                nonce=(
                    nonce if nonce is not None else random.randint(0, 1000000)
                ),  # Two equal questions need to have different nonces.
            ),
            tx_params=tx_params,
        )
        question_id = HexBytes(
            receipt_tx["logs"][0]["topics"][1]
        )  # The question id is available in the first emitted log, in the second topic.
        return question_id

    def submitAnswer(
        self,
        question_id: HexBytes,
        answer: str,
        outcomes: list[str],
        bond: Wei,
        from_private_key: PrivateKey,
        max_previous: Wei | None = None,
    ) -> TxReceipt:
        if max_previous is None:
            # If not provided, defaults to 0, which means no checking,
            # same as on Omen website: https://github.com/protofire/omen-exchange/blob/763d9c9d05ebf9edacbc1dbaa561aa5d08813c0f/app/src/services/realitio.ts#L363.
            max_previous = Wei(0)

        # Normalise the answer to lowercase, to match Enum values as [YES, NO] against outcomes as ["Yes", "No"].
        answer = answer.lower()
        outcomes = [o.lower() for o in outcomes]

        return self.send_with_value(
            function_name="submitAnswer",
            function_params=dict(
                question_id=question_id,
                answer=int_to_hexbytes(
                    outcomes.index(answer)
                ),  # Contract's method expects answer index in bytes.
                max_previous=max_previous,
            ),
            amount_wei=bond,
        )

    def claimWinnings(
        self,
        question_id: HexBytes,
        history_hashes: list[HexBytes],
        addresses: list[ChecksumAddress],
        bonds: list[Wei],
        answers: list[HexBytes],
        tx_params: t.Optional[TxParams] = None,
    ) -> TxReceipt:
        return self.send(
            function_name="claimWinnings",
            function_params=dict(
                question_id=question_id,
                history_hashes=history_hashes,
                addrs=addresses,
                bonds=bonds,
                answers=answers,
            ),
            tx_params=tx_params,
        )

    def balanceOf(self, from_address: ChecksumAddress) -> Wei:
        balance = wei_type(self.call("balanceOf", [from_address]))
        return balance

    def withdraw(self) -> TxReceipt:
        return self.send(
            function_name="withdraw",
        )
